"""crawl4ai wrapper — visible Chromium for visit_webpage (markdown extraction)."""

import logging
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from sec_agent.config import SESSION_DIR

logger = logging.getLogger(__name__)
CRAWL_SESSION_DIR = SESSION_DIR / "crawl4ai"


class CrawlBrowserManager:
    def __init__(self):
        self._crawler: Optional[AsyncWebCrawler] = None

    async def launch(self, visible: bool = True):
        CRAWL_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        browser_cfg = BrowserConfig(
            headless=not visible,
            browser_type="chromium",
            enable_stealth=True,
            use_persistent_context=True,
            user_data_dir=str(CRAWL_SESSION_DIR),
        )
        self._crawler = AsyncWebCrawler(config=browser_cfg, verbose=False)
        await self._crawler.start()
        logger.info("Crawl4AI browser launched (visible=%s)", visible)

    async def fetch(self, url: str, wait_until: str = "networkidle") -> str:
        if not self._crawler:
            raise RuntimeError("Crawl4AI not started")
        run_cfg = CrawlerRunConfig(wait_until=wait_until)
        result = await self._crawler.arun(url, config=run_cfg)
        if not result.success:
            return f"ERROR: Failed to fetch (status {result.status_code})"
        md = result.markdown
        content = ""
        if md:
            content = md.fit_markdown or md.raw_markdown or ""
        return content or "ERROR: No markdown extracted"

    async def close(self):
        if self._crawler:
            await self._crawler.close()
            self._crawler = None
            logger.info("Crawl4AI browser closed")
