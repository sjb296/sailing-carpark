"""FastAPI application serving car park occupancy data from webcam detection."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response

import db
import detector
import scraper

load_dotenv()

CLUB_URL = os.environ["CLUB_URL"]
CLUB_USER = os.environ["CLUB_USER"]
CLUB_PASS = os.environ["CLUB_PASS"]
WEBCAM_PATH = os.environ["WEBCAM_PATH"]
MAX_SPACES = int(os.environ["MAX_SPACES"])

PROJECT_DIR = Path(__file__).parent
RAW_DIR = PROJECT_DIR / "images" / "raw"
ANNOTATED_DIR = PROJECT_DIR / "images" / "annotated"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_INDEX_HTML = (PROJECT_DIR / "index.html").read_text()


async def sample_job() -> None:
    """Run a full sampling cycle: capture screenshots, detect cars, store result."""
    logger.info("Starting sampling cycle ...")
    paths: list[Path] = []
    try:
        # Clean previous images
        _clean_dir(RAW_DIR)
        _clean_dir(ANNOTATED_DIR)

        logger.info("Step 1/3: Scraping webcam screenshots ...")
        paths = await scraper.login_and_capture(
            CLUB_URL,
            WEBCAM_PATH,
            CLUB_USER,
            CLUB_PASS,
            save_dir=RAW_DIR,
            num_screenshots=3,
            interval_seconds=10,
        )
        logger.info("Scraped %d screenshot(s)", len(paths))

        if not paths:
            logger.warning("No screenshots captured – skipping detection")
            return

        logger.info("Step 2/3: Running car detection on %d image(s) ...", len(paths))
        ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)
        counts = await asyncio.gather(
            *[
                asyncio.to_thread(
                    detector.count_cars,
                    p,
                    str(ANNOTATED_DIR / f"{p.stem}.annotated.png"),
                )
                for p in paths
            ]
        )
        logger.info("Raw counts: %s", counts)

        raw_count = sum(counts) / len(counts)
        occupancy = raw_count / MAX_SPACES
        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info("Step 3/3: Storing reading in database ...")
        await asyncio.to_thread(db.insert_reading, timestamp, raw_count, occupancy)

        logger.info(
            "Sampling complete: raw_count=%.1f, occupancy=%.2f%%",
            raw_count,
            occupancy * 100,
        )
    except Exception:
        logger.exception("Sampling cycle failed")


def _clean_dir(directory: Path) -> None:
    """Remove all files in *directory* if it exists."""
    if directory.exists():
        for f in directory.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)


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
    logger.info("Scheduler started (interval=15 min, immediate first run)")

    app.state.scheduler = scheduler

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler shut down")


app = FastAPI(lifespan=lifespan)


def _latest_annotated_url() -> str | None:
    """Return the URL path for the most recent annotated image, or None."""
    if not ANNOTATED_DIR.exists():
        return None
    files = sorted(ANNOTATED_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return None
    return f"/images/annotated/{files[0].name}"


@app.get("/images/annotated/{filename}")
async def serve_annotated_image(filename: str):
    """Serve an annotated image from the annotated directory."""
    path = ANNOTATED_DIR / filename
    if not path.is_file():
        return Response(status_code=404)
    return FileResponse(path)


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
            "image_url": _latest_annotated_url(),
        }

    return {
        "status": _compute_status(reading["occupancy"]),
        "occupancy": round(reading["occupancy"], 2),
        "car_count": reading["raw_count"],
        "sampled_at": reading["timestamp"],
        "image_url": _latest_annotated_url(),
    }


@app.post("/carpark/sample-now")
async def trigger_sample():
    """Trigger an immediate sampling cycle (runs in the background)."""
    app.state.scheduler.add_job(sample_job, "date", max_instances=1)
    return {"status": "sampling started"}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Render a simple dashboard showing car-park occupancy."""
    return _INDEX_HTML.format(max_spaces=MAX_SPACES)
