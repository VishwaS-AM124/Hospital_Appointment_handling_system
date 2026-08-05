"""FastAPI application entrypoint.

Run from the backend/ directory:
    .\\venv\\Scripts\\uvicorn.exe app.main:app --reload --port 8000
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal, engine
from app.services import waitlist_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _waitlist_sweep_loop() -> None:
    """Expire lapsed claim windows and pass each offer to the next patient in line.

    Booking attempts settle a queue lazily, but a queue nobody is trying to book would
    otherwise stall: the patient after a no-show would wait forever for a notification.
    This loop is what makes the hand-off happen on time.
    """
    interval = settings.waitlist_sweep_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            # Blocking DB work off the event loop.
            await asyncio.to_thread(_run_sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed sweep must never kill the loop — the next tick retries.
            logger.exception("Waitlist sweep failed")


def _run_sweep_once() -> None:
    db = SessionLocal()
    try:
        touched = waitlist_service.sweep_expired_offers(db)
        if touched:
            logger.info("Waitlist sweep advanced %d slot queue(s)", touched)
    finally:
        db.close()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task: asyncio.Task | None = None
    if settings.waitlist_sweep_seconds > 0:
        task = asyncio.create_task(_waitlist_sweep_loop())
        logger.info(
            "Waitlist sweep every %ds; claim window %d min",
            settings.waitlist_sweep_seconds,
            settings.waitlist_claim_window_minutes,
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

DESCRIPTION = """
Hospital appointment scheduler with two roles.

**Doctors** publish services and availability slots, and complete or cancel the
appointments on their own schedule. **Patients** browse open slots, book one, and
cancel or review their own history.

Booking is protected against double-booking by three independent layers: a
`SELECT ... FOR UPDATE` row lock, a status re-check inside the locked transaction, and a
`UNIQUE` index on a generated column so the database itself refuses a second live
appointment on one slot.

Losing that race is not a dead end. The loser joins the slot's **FIFO waiting queue** and
is told their position. When the slot is released, the patient at the head of the queue is
notified and gets an exclusive claim window on it.

Every error uses one envelope:
`{"error": {"code": "SLOT_ALREADY_BOOKED", "message": "...", "details": null}}`
"""

app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["meta"], summary="Liveness and database check")
def health() -> dict[str, str]:
    """Reports database reachability so a failing deploy is obvious immediately."""
    database = "up"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logging.getLogger(__name__).exception("Database health check failed")
        database = "down"
    return {"status": "ok", "database": database}


@app.get("/", tags=["meta"], include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_v1_prefix,
    }
