"""crawl4ai wrapper — visible Chromium for visit_webpage (markdown extraction)."""

import io
import logging
import os
import sys
from typing import Optional

from sec_agent.config import SESSION_DIR

logger = logging.getLogger(__name__)
CRAWL_SESSION_DIR = SESSION_DIR / "crawl4ai"


class CrawlBrowserManager:
    def __init__(self):
        self._crawler = None  # type: ignore[annotation-unchecked]

    async def launch(self, visible: bool = True):
        # crawl4ai's Rich logger crashes on Windows cp1252 terminals with Unicode chars.
        # Force UTF-8 for the subprocess/stdio and wrap stdout temporarily.
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

        from crawl4ai import AsyncWebCrawler, BrowserConfig

        CRAWL_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        browser_cfg = BrowserConfig(
            headless=not visible,
            browser_type="chromium",
            enable_stealth=True,
            use_persistent_context=True,
            user_data_dir=str(CRAWL_SESSION_DIR),
        )
        self._crawler = AsyncWebCrawler(config=browser_cfg, verbose=False)

        old_stdout = sys.stdout
        try:
            wrapper = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            sys.stdout = wrapper
            await self._crawler.start()
        except UnicodeEncodeError:
            logger.warning("crawl4ai startup hit encoding issue — retrying headless")
            browser_cfg = BrowserConfig(
                headless=True,
                browser_type="chromium",
                enable_stealth=True,
                use_persistent_context=True,
                user_data_dir=str(CRAWL_SESSION_DIR),
            )
            self._crawler = AsyncWebCrawler(config=browser_cfg, verbose=False)
            await self._crawler.start()
        finally:
            try:
                sys.stdout.flush()
                sys.stdout.detach()  # detach without closing the underlying buffer
            except Exception:
                pass
            sys.stdout = old_stdout

        logger.info("Crawl4AI browser launched (visible=%s)", visible)

    async def fetch(self, url: str, wait_until: str = "networkidle") -> str:
        if not self._crawler:
            raise RuntimeError("Crawl4AI not started")
        from crawl4ai import CrawlerRunConfig

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
