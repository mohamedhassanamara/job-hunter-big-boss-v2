import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Job Hunter v2", version="0.1.0")
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


app.include_router(api_router, prefix="/api")
