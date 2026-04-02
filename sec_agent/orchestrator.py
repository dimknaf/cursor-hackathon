"""CLI: launch visible browsers + run SEC filing agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sec_agent.agent import create_sec_agent, run_sec_analysis
from sec_agent.browser import BrowserManager
from sec_agent.config import config, OUTPUT_DIR
from sec_agent.crawl_browser import CrawlBrowserManager
from sec_agent.tools import set_browser, set_crawl_browser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def build_demo_message(cik: str) -> str:
    return f"""CIK to analyze: {cik}

Task:
1) Identify the most recent 10-Q or 10-K for this CIK (prefer 10-Q if it is the latest period).
2) Pull relevant XBRL concepts (at minimum try Revenues and NetIncomeLoss; add Assets or OperatingIncomeLoss if useful).
3) Fetch filing excerpts around Management / MD&A and around Risk or Liquidity as needed using sec_fetch_filing_excerpt.
4) Use Google search for how media/commentary frame the company around this filing (use ticker from submissions if present).
5) Produce a value-focused structured brief via submit_result.

Be explicit about which accession and primary_document you analyzed."""


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="SEC filing research agent (Gemini + tools)")
    parser.add_argument("--cik", type=str, default="0000320193", help="10-digit or numeric CIK")
    parser.add_argument("--message", type=str, default="", help="Override task message (default = demo analysis)")
    parser.add_argument("--headless", action="store_true", help="Hide browser windows")
    args = parser.parse_args()

    if config.debug_mode:
        logging.getLogger().setLevel(logging.DEBUG)

    visible = config.browser_visible and not args.headless
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.message.strip():
        task = args.message.strip()
    else:
        task = build_demo_message(args.cik.strip())

    browser = BrowserManager()
    crawl = CrawlBrowserManager()
    await browser.launch(visible=visible)
    await crawl.launch(visible=visible)
    set_browser(browser)
    set_crawl_browser(crawl)

    try:
        agent = create_sec_agent()
        brief = await run_sec_analysis(agent, task)
        out_path = OUTPUT_DIR / "filing_analysis.json"
        out_path.write_text(
            json.dumps(brief.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Wrote %s", out_path)
        print(json.dumps(brief.model_dump(), indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        logger.exception("Run failed: %s", e)
        return 1
    finally:
        await crawl.close()
        await browser.close()


def main() -> None:
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
