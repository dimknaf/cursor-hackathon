"""Playwright browser for Google search (non-headless, visible window)."""

import asyncio
import logging
import random
import time
from typing import Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from sec_agent.config import config, SESSION_DIR

logger = logging.getLogger(__name__)


class BrowserManager:
    """Persistent Chromium for agent-driven search."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._last_navigation_time: float = 0
        self._google_timestamps: list = []

    async def launch(self, visible: bool = True) -> Page:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        args = ["--disable-blink-features=AutomationControlled"]
        if not visible:
            args.append("--start-minimized")

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR / "playwright"),
            headless=not visible,
            channel="chromium",
            args=args,
        )
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        await self._page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """
        )
        logger.info("Playwright browser launched (visible=%s)", visible)
        return self._page

    async def close(self):
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._playwright = None
        logger.info("Playwright browser closed")

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    async def navigate(self, url: str) -> str:
        await self._enforce_google_rate_limit(url)
        delay = random.uniform(config.min_navigation_delay, config.max_navigation_delay)
        elapsed = time.time() - self._last_navigation_time
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        logger.debug("Navigating to: %s", url)
        try:
            await self.page.goto(url, timeout=config.page_load_timeout)
            await self.page.wait_for_load_state("networkidle", timeout=config.page_load_timeout)
        except Exception as e:
            logger.warning("Navigation issue for %s: %s", url, e)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

        self._last_navigation_time = time.time()
        if "google.com" in url:
            self._google_timestamps.append(time.time())

        return await self.page.inner_text("body")

    async def _enforce_google_rate_limit(self, url: str):
        if "google.com" not in url:
            return
        now = time.time()
        cutoff = now - 60
        self._google_timestamps = [t for t in self._google_timestamps if t > cutoff]
        if len(self._google_timestamps) >= config.google_requests_per_minute:
            wait = 60 - (now - self._google_timestamps[0])
            logger.info("Google rate limit — waiting %.1fs", max(wait, 1))
            await asyncio.sleep(max(wait, 1))
