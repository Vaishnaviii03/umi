import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.gmail import router as gmail_router
from app.api.calendar import router as calendar_router
from app.api.google import router as google_router
from app.api.vision import router as vision_router
from app.api.notifications import router as notifications_router
from app.config import settings
from app.db.engine import db_enabled, init_db
from app.services.proactive_scheduler import proactive_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if db_enabled():
        logging.getLogger("umi").info("database connection ready")
    else:
        logging.getLogger("umi").warning("no DATABASE_URL set - running without persistence")
    proactive_scheduler.start()
    yield
    proactive_scheduler.stop()


app = FastAPI(title="Umi Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(gmail_router)
app.include_router(calendar_router)
app.include_router(google_router)
app.include_router(vision_router)
app.include_router(notifications_router)

