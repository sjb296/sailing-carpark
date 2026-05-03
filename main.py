"""FastAPI application serving car park occupancy data from webcam detection."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI

import db
import detector
import scraper

load_dotenv()

CLUB_URL = os.environ["CLUB_URL"]
CLUB_USER = os.environ["CLUB_USER"]
CLUB_PASS = os.environ["CLUB_PASS"]
WEBCAM_PATH = os.environ["WEBCAM_PATH"]
MAX_SPACES = int(os.environ["MAX_SPACES"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def sample_job() -> None:
    """Run a full sampling cycle: capture screenshots, detect cars, store result."""
    logger.info("Starting sampling cycle ...")
    paths: list = []
    try:
        paths = await scraper.login_and_capture(
            CLUB_URL, WEBCAM_PATH, CLUB_USER, CLUB_PASS,
            num_screenshots=10,
            interval_seconds=60
        )

        counts = await asyncio.gather(
            *[asyncio.to_thread(detector.count_cars, p, f"{p}_annotated") for p in paths]
        )

        raw_count = sum(counts) / len(counts)
        occupancy = raw_count / MAX_SPACES
        timestamp = datetime.now(timezone.utc).isoformat()

        await asyncio.to_thread(db.insert_reading, timestamp, raw_count, occupancy)

        logger.info(
            "Sampling complete: raw_count=%.1f, occupancy=%.2f%%",
            raw_count,
            occupancy * 100,
        )
    except Exception:
        logger.exception("Sampling cycle failed")
    finally:
        for p in paths:
            p.unlink(missing_ok=True)


def _compute_status(occupancy: float) -> str:
    """Map occupancy ratio to a human-readable label."""
    if occupancy < 0.4:
        return "quiet"
    if occupancy < 0.75:
        return "moderate"
    return "busy"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the DB table, start the scheduler, and clean up on shutdown."""
    await asyncio.to_thread(db.init_db)
    logger.info("Database initialised")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sample_job,
        "interval",
        minutes=15,
        max_instances=1,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info("Scheduler started (interval=60 min, immediate first run)")

    app.state.scheduler = scheduler

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler shut down")


app = FastAPI(lifespan=lifespan)


@app.get("/carpark")
async def get_carpark():
    """Return the most recent car park reading."""
    reading = await asyncio.to_thread(db.get_latest_reading)

    if reading is None:
        return {
            "status": "no_data",
            "occupancy": 0.0,
            "car_count": 0,
            "sampled_at": None,
        }

    return {
        "status": _compute_status(reading["occupancy"]),
        "occupancy": round(reading["occupancy"], 2),
        "car_count": reading["raw_count"],
        "sampled_at": reading["timestamp"],
    }


@app.post("/carpark/sample-now")
async def trigger_sample():
    """Trigger an immediate sampling cycle (runs in the background)."""
    app.state.scheduler.add_job(sample_job)
    return {"status": "sampling started"}
