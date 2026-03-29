"""Playwright-based full-page screenshot capture."""

from __future__ import annotations

import logging
import os

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class ScreenshotService:
    """Captures full-page screenshots of Zhihu content using Playwright."""

    def __init__(
        self,
        cookies: list[dict],
        data_dir: str,
    ) -> None:
        """Initialize screenshot service.

        Args:
            cookies: List of cookie dicts for Playwright context.
            data_dir: Base directory for saving screenshots.
        """
        self._cookies = cookies
        self._screenshot_dir = os.path.join(data_dir, "screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)

    async def capture(self, url: str, filename: str) -> str | None:
        """Take a full-page screenshot of the given URL.

        Args:
            url: Page URL to capture.
            filename: Output filename (without extension).

        Returns:
            File path to the saved screenshot, or None on failure.
        """
        output_path = os.path.join(self._screenshot_dir, f"{filename}.png")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                await context.add_cookies(self._cookies)

                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

                await page.screenshot(
                    path=output_path, full_page=True
                )

                await browser.close()

            logger.info("Screenshot saved: %s", output_path)
            return output_path

        except Exception as e:
            logger.warning("Screenshot failed for %s: %s", url, e)
            return None
