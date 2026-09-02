import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import settings
from .routers import recipes
from .seed import DEMO_RECIPES
from .ws import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("popote")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(db.connect)
    if settings.seed_demo_data:
        await asyncio.to_thread(db.seed_if_empty, DEMO_RECIPES)
    yield


app = FastAPI(
    title="PoPote API",
    version="0.1.0",
    lifespan=lifespan,
    # Served behind nginx under /api in docker-compose and in production.
    root_path="",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes.router, prefix="/api", tags=["recipes"])


@app.get("/api/health")
async def health() -> dict[str, object]:
    try:
        count = await asyncio.to_thread(db.count_recipes)
        database_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check could not reach ArangoDB: %s", exc)
        count = 0
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "recipes": count,
        "ws_clients": manager.count,
    }
