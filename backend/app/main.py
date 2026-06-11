from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data, set_db, _db_adapter
from app.middleware.auth import AuthMiddleware
from app.middleware.csrf import CsrfMiddleware
from app.middleware.tenant import TenantMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
    await adapter.execute("COMMIT")

    yield

    await adapter.close()
    set_db(None)  # type: ignore


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(TenantMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(AuthMiddleware)

    from app.routers import health, auth, herbs, formulas, medicines, safety, chat, daily_health, dashboard, reminders, constitution, profile

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(herbs.router)
    app.include_router(formulas.router)
    app.include_router(medicines.router)
    app.include_router(safety.router)
    app.include_router(chat.router)
    app.include_router(daily_health.router)
    app.include_router(dashboard.router)
    app.include_router(reminders.router)
    app.include_router(constitution.router)
    app.include_router(profile.router)

    return app


app = create_app()
