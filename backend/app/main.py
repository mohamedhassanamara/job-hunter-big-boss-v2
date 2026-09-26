import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router as api_router
from app.config import get_settings
from app.db import engine
from app.services import scheduler
from app.services.discovery import mark_stale_runs
from app.services.pipeline import TransitionError

settings = get_settings()



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    mark_stale_runs(engine)
    if settings.scheduler_enabled:
        scheduler.start(engine)
    yield
    scheduler.shutdown()


app = FastAPI(title="Job Hunter v2", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def mock_latency(request: Request, call_next):  # noqa: ANN001
    if settings.mock_latency_ms and request.url.path.startswith("/api"):
        await asyncio.sleep(settings.mock_latency_ms / 1000)
    return await call_next(request)


@app.exception_handler(TransitionError)
async def transition_error(_: Request, exc: TransitionError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(api_router, prefix="/api")
