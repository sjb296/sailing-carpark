"""Playwright-based webcam screenshot capture with login."""

import asyncio
import logging
import sys
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Adjust these selectors to match the real login page once you can inspect it.
# Run the script with a DEBUG dump first to see what selectors are correct.
SELECTORS = {
    "username": "#email",
    "password": "#password",
    "submit": "input[type='submit']",
}


async def _dump_page_debug(page, label: str, save_dir: Path) -> None:
    """Write a screenshot and print every form element on the current page."""
    debug_path = save_dir / f"debug_{label}.png"
    await page.screenshot(path=str(debug_path))
    print(f"[DEBUG] Screenshot  → {debug_path}", file=sys.stderr)
    print(f"[DEBUG] Page title → {await page.title()}", file=sys.stderr)
    print(f"[DEBUG] URL        → {page.url}", file=sys.stderr)

    info = await page.evaluate(
        """() => {
        const collect = (doc) => {
            const inputs = Array.from(doc.querySelectorAll(
                'input, textarea, select'
            )).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                id: el.id,
                name: el.name,
                class: el.className,
                placeholder: el.placeholder,
                autocomplete: el.autocomplete,
            }));
            const buttons = Array.from(doc.querySelectorAll(
                'button, input[type="submit"], a[role="button"], [role="button"]'
            )).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                id: el.id,
                name: el.name,
                class: el.className,
                text: (el.textContent || el.value || '').trim().replace(/\\s+/g, ' '),
            }));
            // Find anything with play/snap/media in its id
            const videoEls = Array.from(doc.querySelectorAll(
                '[id*="play" i], [id*="snap" i], [id*="media" i], [id*="video" i], ' +
                '[class*="play" i], [class*="snap" i], [class*="media" i], [class*="video" i]'
            )).map(el => ({
                tag: el.tagName.toLowerCase(),
                id: el.id,
                class: el.className,
                text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
            }));
            return { inputs, buttons, videoEls };
        };
        const main = collect(document);
        const iframes = Array.from(document.querySelectorAll('iframe')).map(el => ({
            src: el.src,
            id: el.id,
            name: el.name,
        }));
        return { ...main, iframes };
    }"""
    )

    print(f"[DEBUG] Inputs ({len(info['inputs'])}):", file=sys.stderr)
    for el in info["inputs"]:
        parts = [f"  <{el['tag']}"]
        for attr in ("type", "id", "name", "placeholder", "autocomplete"):
            if el[attr]:
                parts.append(f'{attr}="{el[attr]}"')
        parts.append(f'class="{el["class"]}"')
        print(" ".join(parts) + ">", file=sys.stderr)

    print(f"[DEBUG] Buttons ({len(info['buttons'])}):", file=sys.stderr)
    for el in info["buttons"]:
        print(
            f'  <{el["tag"]} id="{el["id"]}" name="{el["name"]}" '
            f'class="{el["class"]}"> {el["text"]}',
            file=sys.stderr,
        )

    print(f"[DEBUG] Video/media elements ({len(info['videoEls'])}):", file=sys.stderr)
    for el in info["videoEls"]:
        print(
            f'  <{el["tag"]} id="{el["id"]}" class="{el["class"]}"> {el["text"]}',
            file=sys.stderr,
        )

    print(f"[DEBUG] Iframes ({len(info['iframes'])}):", file=sys.stderr)
    for el in info["iframes"]:
        print(
            f'  src="{el["src"]}" id="{el["id"]}" name="{el["name"]}"',
            file=sys.stderr,
        )


async def login_and_capture(
    base_url: str,
    webcam_path: str,
    username: str,
    password: str,
    save_dir: Path,
    num_screenshots: int = 5,
    interval_seconds: int = 60,
    debug: bool = False,
) -> list[Path]:
    """Log into the club site, navigate to the webcam page, and capture screenshots.

    Screenshots are saved to *save_dir*.  Returns a list of paths to the saved files.
    The caller is responsible for deleting these files after use.
    """
    from playwright.async_api import async_playwright

    paths: list[Path] = []
    save_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            # Log in
            logger.info("Navigating to login page: %s/login", base_url)
            await page.goto(f"{base_url}/login")
            await page.wait_for_load_state("networkidle")

            if debug:
                await _dump_page_debug(page, "login_page", save_dir)

            await page.fill(SELECTORS["username"], username)
            await page.fill(SELECTORS["password"], password)
            await page.click(SELECTORS["submit"])

            await page.wait_for_load_state("networkidle")
            logger.info("Login submitted, current URL: %s", page.url)

            if debug:
                await _dump_page_debug(page, "after_login", save_dir)

            # Go to the webcam page
            await page.goto(f"{base_url.rstrip('/')}{webcam_path}")
            await page.wait_for_load_state("networkidle")
            logger.info("Webcam page loaded")

            if debug:
                await _dump_page_debug(page, "webcam_page", save_dir)

            # Find the IPCamLive player iframe
            iframe = page.frame_locator('iframe[src*="ipcamlive.com"]')

            # Start the video stream once
            play_btn = iframe.locator("#mediaplaybackdiv_ipc_ic_bigPlay")
            await play_btn.wait_for(state="visible", timeout=10000)
            await play_btn.click()
            logger.info("Video stream started")

            # Get snapshots of the webcam
            for i in range(num_screenshots):
                await asyncio.sleep(5)

                # Click Download Snapshot and capture the resulting file
                snapshot_btn = iframe.locator("#mediaplaybackdiv_ipc_ic_snapShot")
                await snapshot_btn.wait_for(state="visible", timeout=10000)

                async with page.expect_download() as download_info:
                    await snapshot_btn.click()
                download = await download_info.value

                suggested = download.suggested_filename
                ext = Path(suggested).suffix or ".png"
                path = save_dir / f"screenshot_{uuid.uuid4().hex[:8]}{ext}"
                await download.save_as(str(path))

                paths.append(path)
                logger.info(
                    "Snapshot %d/%d saved: %s (%d bytes)",
                    i + 1,
                    num_screenshots,
                    path.name,
                    path.stat().st_size,
                )

                if i < num_screenshots - 1:
                    await asyncio.sleep(interval_seconds)

        finally:
            await browser.close()

    return paths
