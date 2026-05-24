from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import contracts, deviation, evals, qa
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # TODO Week 1: warm async DB connection pool (SQLAlchemy async engine)
    # TODO Week 1: initialize Voyage embedding client
    # TODO Week 1: initialize Langfuse client and attach to app state
    _ = settings  # referenced here so config is validated at startup
    yield
    # TODO Week 1: close DB pool and flush Langfuse on shutdown


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Clauseline",
        description="Contract intelligence with rigorous grounding, honest evals, and observable engineering.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
    app.include_router(qa.router, prefix="/api/qa", tags=["qa"])
    app.include_router(deviation.router, prefix="/api/deviation", tags=["deviation"])
    app.include_router(evals.router, prefix="/api/evals", tags=["evals"])

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "env": settings.app_env,
            "version": "0.1.0",
        }

    return app


app = create_app()
