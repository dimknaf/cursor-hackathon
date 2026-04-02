"""Real-condition demo: run the full agent on a known filing.

Usage:
    python -m sec_agent.demo                     # Apple latest 10-Q (default)
    python -m sec_agent.demo --cik 789019        # Microsoft
    python -m sec_agent.demo --cik 1318605       # Tesla
    python -m sec_agent.demo --headless          # hide browsers
"""

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
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Well-known CIKs for quick demos
DEMO_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "TSLA": "0001318605",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "JNJ": "0000200406",
    "NKE": "0000320187",
}


def build_task(cik: str, ticker: str = "") -> str:
    label = f" (ticker: {ticker})" if ticker else ""
    return f"""CIK: {cik}{label}

Analyze the most recent 10-Q or 10-K for this company. Steps:

1. Call sec_list_recent_filings to find the latest 10-Q or 10-K (prefer whichever was filed most recently).
2. Use sec_get_xbrl_concept to pull key fundamentals: at minimum try Revenues, NetIncomeLoss.
   Also try OperatingIncomeLoss, EarningsPerShareDiluted, Assets, and CashAndCashEquivalentsAtCarryingValue
   — if a concept 404s, note it in caveats and move on.
3. Use sec_fetch_filing_excerpt to read the filing text:
   - First call with text_search_anchor="Management" or "Results of Operations" for MD&A.
   - Second call with text_search_anchor="Risk" or "Liquidity" for risk/capital discussion.
4. Use search_google for 1-2 queries about market/press reaction to this company's most recent quarterly or annual filing.
   If relevant, visit_webpage on one high-signal article.
5. Synthesize everything and call submit_result.

Be explicit about which accession you analyzed. Cite URLs."""


async def run_demo(cik: str, ticker: str, headless: bool) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    visible = not headless

    browser = BrowserManager()
    crawl = CrawlBrowserManager()
    await browser.launch(visible=visible)
    await crawl.launch(visible=visible)
    set_browser(browser)
    set_crawl_browser(crawl)

    try:
        agent = create_sec_agent()
        task = build_task(cik, ticker)
        logger.info("Starting demo for CIK=%s (%s)", cik, ticker or "?")
        brief = await run_sec_analysis(agent, task)

        out_path = OUTPUT_DIR / f"demo_{ticker or cik}.json"
        out_path.write_text(
            json.dumps(brief.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Result → %s", out_path)

        # Pretty-print key sections
        print("\n" + "=" * 72)
        print(f"  {brief.entity_name or ticker or cik}  —  {brief.filing_focus}")
        print("=" * 72)
        print(f"\n📊 Fundamentals:\n{brief.fundamentals_from_sec}\n")
        print(f"📝 Management & Ops:\n{brief.management_and_operations}\n")
        print(f"⚠️  Risks / Liquidity:\n{brief.risks_liquidity_capital}\n")
        print(f"📰 Market & News:\n{brief.market_and_news}\n")
        print(f"💡 Value Takeaway:\n{brief.value_investor_takeaway}\n")
        print(f"🔗 Citations:\n{brief.citations}\n")
        if brief.caveats:
            print(f"⚙️  Caveats:\n{brief.caveats}\n")
        print("=" * 72)
        return 0
    except Exception as e:
        logger.exception("Demo failed: %s", e)
        return 1
    finally:
        await crawl.close()
        await browser.close()


def main():
    p = argparse.ArgumentParser(description="SEC filing agent — real condition demo")
    p.add_argument("--cik", type=str, default="", help="CIK (numeric or 10-digit)")
    p.add_argument("--ticker", type=str, default="AAPL", help="Ticker shortcut (AAPL, MSFT, TSLA, ...)")
    p.add_argument("--headless", action="store_true", help="Hide browser windows")
    args = p.parse_args()

    if args.cik:
        cik = args.cik.strip().zfill(10)
        ticker = args.ticker.upper() if args.ticker else ""
    else:
        ticker = args.ticker.upper()
        cik = DEMO_CIKS.get(ticker, "")
        if not cik:
            print(f"Unknown ticker '{ticker}'. Known: {', '.join(sorted(DEMO_CIKS))}")
            print("Pass --cik explicitly instead.")
            sys.exit(1)

    sys.exit(asyncio.run(run_demo(cik, ticker, args.headless)))


if __name__ == "__main__":
    main()
