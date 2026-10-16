from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data, set_db, _db_adapter
from app.knowledge_reader import enrich_from_legacy_tables
from app.middleware.auth import AuthMiddleware
from app.middleware.csrf import CsrfMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


async def _warmup_models() -> None:
    """Pre-load embedding + reranker models in a background thread.

    Runs after server startup so the first user request doesn't pay the
    ~20s model-load cost. Non-blocking: failures are logged and swallowed.
    """
    loop = asyncio.get_event_loop()

    def _load_embedder() -> None:
        try:
            from app.embedding import get_embedding_model
            m = get_embedding_model()
            if m.available:
                logger.info("warmup: embedder ready (dim=%d)", m.dim)
        except Exception as exc:
            logger.info("warmup: embedder skipped (%s)", exc)

    def _load_reranker() -> None:
        try:
            from app.search_pipeline import _get_reranker
            r = _get_reranker()
            if r is not None:
                logger.info("warmup: reranker ready")
        except Exception as exc:
            logger.info("warmup: reranker skipped (%s)", exc)

    await loop.run_in_executor(None, _load_embedder)
    await loop.run_in_executor(None, _load_reranker)
from app.middleware.tenant import TenantMiddleware
from app.scheduler import start_scheduler, stop_scheduler


def _apply_pending_restore(db_file: Path) -> None:
    """Apply a staged database restore (`.restore_pending`) before opening the DB.

    The backup router stages decrypted restores as ``.restore_pending`` next to
    the live DB and promises "takes effect after restart". This function makes
    that promise real: on startup, if the pending file exists and passes
    ``PRAGMA integrity_check``, it atomically replaces the live DB (the old DB
    is preserved as ``.pre_restore_bak``). A corrupt pending file is rejected
    with a loud log — never silently applied. A half-done swap is rolled back
    so the app can never boot from an empty/missing DB, and a plaintext backup
    is refused outright on an encrypted deployment.
    """
    pending = db_file.parent / ".restore_pending"
    if not pending.exists():
        return

    # Encrypted-deployment guard: a plaintext backup restored over a
    # SQLCipher-encrypted DB would silently look like total data loss.
    if settings.DB_ENCRYPTION_KEY:
        try:
            with pending.open("rb") as fh:
                header = fh.read(16)
        except OSError as exc:
            logger.error("restore_pending: cannot read header (%s) — refusing to apply", exc)
            _reject_pending(pending)
            return
        if header == b"SQLite format 3\x00":
            logger.error(
                "restore_pending: 明文备份无法恢复到加密实例"
                "（DB_ENCRYPTION_KEY 已配置，pending 是明文 SQLite 库）— 拒绝应用"
            )
            _reject_pending(pending)
            return

    import sqlite3
    from app.db.adapter import _SQLCIPHER_ACTIVE, _pragma_key_sql
    try:
        conn = sqlite3.connect(str(pending))
        try:
            if settings.DB_ENCRYPTION_KEY:
                if not _SQLCIPHER_ACTIVE:
                    raise sqlite3.DatabaseError(
                        "DB_ENCRYPTION_KEY is configured but SQLCipher is unavailable"
                    )
                conn.execute(_pragma_key_sql(settings.DB_ENCRYPTION_KEY))
                conn.execute("PRAGMA cipher_compatibility = 4")
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            # A leaked handle keeps the file locked on Windows and would
            # make the .rejected rename below fail.
            conn.close()
        if result != "ok":
            logger.error("restore_pending: integrity_check failed (%s) — refusing to apply", result)
            _reject_pending(pending)
            return
    except sqlite3.Error as exc:
        logger.error("restore_pending: cannot open for verification (%s) — refusing to apply", exc)
        _reject_pending(pending)
        return

    backup_of_current = db_file.parent / (db_file.name + ".pre_restore_bak")
    try:
        if db_file.exists():
            if backup_of_current.exists():
                backup_of_current.unlink()
            db_file.rename(backup_of_current)
        pending.rename(db_file)
    except OSError as exc:
        logger.error("restore_pending: atomic swap failed (%s) — keeping current DB", exc)
        # If the live DB was already moved aside but the pending file could
        # not be swapped in, put the original back — booting from a missing
        # (=> freshly created empty) DB must never happen.
        if not db_file.exists() and backup_of_current.exists():
            try:
                backup_of_current.rename(db_file)
                logger.info(
                    "restore_pending: rolled back swap — original DB restored from %s",
                    backup_of_current.name,
                )
            except OSError:
                import shutil

                try:
                    shutil.copy2(backup_of_current, db_file)
                    logger.info(
                        "restore_pending: original DB copied back from %s",
                        backup_of_current.name,
                    )
                except OSError:
                    logger.critical(
                        "restore_pending: could not restore the original DB — it is "
                        "preserved at %s; recover it manually before restarting",
                        backup_of_current,
                    )
        # Abandon this restore attempt so a permanently failing swap cannot
        # block every restart (the pending file is preserved as .rejected).
        if pending.exists():
            _reject_pending(pending)
        return

    for suffix in ("-wal", "-shm"):
        sidecar = db_file.parent / (db_file.name + suffix)
        try:
            sidecar.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("restore_pending: could not remove stale %s (%s)", sidecar.name, exc)
    logger.info("restore_pending: applied. Previous DB kept at %s", backup_of_current.name)


def _reject_pending(pending: Path) -> None:
    """Rename a refused .restore_pending to .rejected (best-effort)."""
    try:
        pending.rename(pending.with_suffix(".rejected"))
    except OSError:
        logger.warning("restore_pending: could not rename %s to .rejected", pending)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.SECRET_KEY_IS_DEFAULT:
        import os
        if os.environ.get("HOMEDOCTOR_ALLOW_INSECURE_SECRET") == "1":
            logger.warning(
                "SECRET_KEY is the default value — allowed only because "
                "HOMEDOCTOR_ALLOW_INSECURE_SECRET=1 is set (dev/test)."
            )
        else:
            # Knowing the default key lets anyone forge admin JWTs and punch
            # through all tenant isolation — refuse to run in that state.
            raise RuntimeError(
                "SECRET_KEY 未配置：拒绝启动。请在环境变量 HOMEDOCTOR_SECRET_KEY "
                "设置强随机密钥（开发/测试可设 HOMEDOCTOR_ALLOW_INSECURE_SECRET=1 跳过）。"
            )

    db_path = settings.DATABASE_URL
    if db_path != ":memory:":
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        _apply_pending_restore(db_file)

    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    set_db(adapter)

    await init_db(adapter)
    from app.model_registry import migrate_stored_api_keys
    await migrate_stored_api_keys(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await enrich_from_legacy_tables(adapter)

    # Keep a strong reference: asyncio only holds weak refs to tasks — an
    # unreferenced long-running task can be GC'd mid-flight.
    app.state.warmup_task = asyncio.create_task(_warmup_models())

    scheduler_task = start_scheduler(adapter)

    yield

    await stop_scheduler(scheduler_task)
    await adapter.close()
    set_db(None)  # type: ignore


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 轮转文件日志：本地部署经 Start-Process -RedirectStandard* 启动时
    # stderr 日志每次重启被覆盖丢失；此 handler 与 stderr 并存，保留最近
    # 3×5MB 历史，供磁盘/备份/巡检告警事后追查。
    try:
        from logging.handlers import RotatingFileHandler

        _log_dir = Path(os.environ.get("HOMEDOCTOR_LOG_DIR", "logs"))
        _log_dir.mkdir(parents=True, exist_ok=True)
        _file_handler = RotatingFileHandler(
            _log_dir / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        _file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logging.getLogger().addHandler(_file_handler)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "rotating file handler unavailable: %s", exc
        )

    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    _web_port = os.environ.get("HOMEDOCTOR_WEB_PORT", "3000")
    if _web_port.isdigit() and 1 <= int(_web_port) <= 65535:
        _cors_origins.extend(
            [f"http://localhost:{_web_port}", f"http://127.0.0.1:{_web_port}"]
        )
    _extra = os.environ.get("EXTRA_ALLOWED_ORIGINS", "")
    if _extra:
        _cors_origins.extend(
            o.strip() for o in _extra.split(",") if o.strip()
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(CsrfMiddleware)
    from app.middleware.request_audit import RequestAuditMiddleware
    app.add_middleware(RequestAuditMiddleware)
    app.add_middleware(AuthMiddleware)

    from app.routers import health, auth, herbs, formulas, medicines, medicine_ocr, ai_classify, safety, chat, daily_health, dashboard, reminders, constitution, profile, favorites, bookmarks, comparisons, seasonal_health, family_members, export, backup, account, triage, schemas, prescriptions, therapies, medication_plans, extractor, formulations, remote_assist, reports, voice, knowledge_import, knowledge_graph, knowledge_hub, classics, share_cards, health_logs, rag_search, unified_knowledge, personal_knowledge, medical_visits, model_registry, smart_search, index_management, knowledge_browse, p2_features, p3_features
    from app.routers import notifications
    from app.routers import push

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(herbs.router)
    app.include_router(formulas.router)
    app.include_router(medicines.router)
    app.include_router(medicine_ocr.router)
    app.include_router(ai_classify.router)
    app.include_router(safety.router)
    app.include_router(chat.router)
    app.include_router(daily_health.router)
    app.include_router(dashboard.router)
    app.include_router(reminders.router)
    app.include_router(constitution.router)
    app.include_router(profile.router)
    app.include_router(favorites.router)
    app.include_router(bookmarks.router)
    app.include_router(comparisons.router)
    app.include_router(seasonal_health.router)
    app.include_router(family_members.router)
    app.include_router(export.router)
    app.include_router(backup.router)
    app.include_router(account.router)
    app.include_router(notifications.router)
    app.include_router(push.router)
    app.include_router(triage.router)
    app.include_router(schemas.router)
    app.include_router(prescriptions.router)
    app.include_router(therapies.router)
    app.include_router(extractor.router)
    app.include_router(formulations.router)
    app.include_router(medication_plans.router)
    app.include_router(remote_assist.router)
    app.include_router(reports.router)
    app.include_router(voice.router)
    app.include_router(knowledge_import.router)
    app.include_router(knowledge_graph.router)
    app.include_router(knowledge_hub.router)
    app.include_router(classics.router)
    app.include_router(share_cards.router)
    app.include_router(health_logs.router)
    app.include_router(rag_search.router)
    app.include_router(unified_knowledge.router)
    app.include_router(personal_knowledge.router)
    app.include_router(medical_visits.router)
    app.include_router(model_registry.router)
    app.include_router(smart_search.router)
    app.include_router(index_management.router)
    app.include_router(knowledge_browse.router)
    app.include_router(p2_features.router)
    app.include_router(p3_features.router)

    return app


app = create_app()
