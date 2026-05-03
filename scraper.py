"""Playwright-based webcam screenshot capture with login."""

import asyncio
import uuid
from pathlib import Path

# Adjust these selectors to match the real login page once you can inspect it.
SELECTORS = {
    "username": "#username",
    "password": "#password",
    "submit": "button[type='submit']",
}

TEMP_DIR = Path("/tmp")


async def login_and_capture(
    base_url: str,
    webcam_path: str,
    username: str,
    password: str,
    num_screenshots: int = 5,
    interval_seconds: int = 60,
) -> list[Path]:
    """Log into the club site, navigate to the webcam page, and capture screenshots.

    Returns a list of paths to PNG files in /tmp.  The caller is responsible for
    deleting these files after use.
    """
    from playwright.async_api import async_playwright

    paths: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            await page.goto(base_url)
            await page.fill(SELECTORS["username"], username)
            await page.fill(SELECTORS["password"], password)
            await page.click(SELECTORS["submit"])

            await page.wait_for_load_state("networkidle")
            await page.goto(f"{base_url.rstrip('/')}{webcam_path}")
            await page.wait_for_load_state("networkidle")

            for i in range(num_screenshots):
                path = TEMP_DIR / f"screenshot_{uuid.uuid4().hex[:8]}.png"
                await page.screenshot(path=str(path))
                paths.append(path)
                if i < num_screenshots - 1:
                    await asyncio.sleep(interval_seconds)

        finally:
            await browser.close()

    return paths
