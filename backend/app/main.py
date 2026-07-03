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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.SECRET_KEY_IS_DEFAULT:
        logger.warning("=" * 60)
        logger.warning("WARNING: SECRET_KEY is still the default value!")
        logger.warning("Anyone can forge JWT tokens. Set HOMEDOCTOR_SECRET_KEY env var.")
        logger.warning("=" * 60)

    db_path = settings.DATABASE_URL
    if db_path != ":memory:":
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    set_db(adapter)

    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await enrich_from_legacy_tables(adapter)

    asyncio.create_task(_warmup_models())

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

    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
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
    app.add_middleware(AuthMiddleware)

    from app.routers import health, auth, herbs, formulas, medicines, medicine_ocr, ai_classify, safety, chat, daily_health, dashboard, reminders, constitution, profile, favorites, bookmarks, comparisons, seasonal_health, family_members, export, backup, account, triage, schemas, prescriptions, therapies, medication_plans, extractor, formulations, remote_assist, reports, voice, knowledge_import, knowledge_graph, knowledge_hub, classics, share_cards, health_logs, rag_search, unified_knowledge, personal_knowledge, medical_visits, model_registry, smart_search, index_management, knowledge_browse, p2_features, p3_features

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
