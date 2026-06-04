import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from api.logging import configure_logging, request_log_level, should_log_request
from api.routes import derivatives, market, pipeline, profiles, sessions
from api.ws import session_stream_handler
from src.config import settings
from src.db.seed import seed_profiles
from src.db.session import engine

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    try:
        async with AsyncSession(engine) as db:
            await seed_profiles(db)
    except Exception as exc:
        log.warning("startup.seed_failed", error=str(exc))
    log.info("startup", environment=settings.environment)
    yield
    log.info("shutdown")


app = FastAPI(title="Signalyst API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(derivatives.router, prefix="/api")
app.add_api_websocket_route("/ws/sessions/{session_id}/stream", session_stream_handler)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = perf_counter()
    response = await call_next(request)
    include_noisy = logging.getLogger().isEnabledFor(logging.DEBUG)
    if should_log_request(request.method, request.url.path, include_noisy=include_noisy):
        duration_ms = round((perf_counter() - start) * 1000, 2)
        log_method = getattr(log, request_log_level(request.method, request.url.path))
        log_method(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
