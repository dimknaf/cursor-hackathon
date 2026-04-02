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
from sec_agent.dashboard import generate_html
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

Do a THOROUGH analysis of the most recent 10-Q or 10-K for this company.
Follow the research strategy in your instructions — all steps, no shortcuts.

Step 1: sec_list_recent_filings → find latest 10-Q or 10-K.
Step 2: sec_get_xbrl_concept for EACH of these (separate calls):
   - Revenues (if 404, try RevenueFromContractWithCustomerExcludingAssessedTax)
   - NetIncomeLoss
   - OperatingIncomeLoss
   - EarningsPerShareDiluted
   - Assets
   - CashAndCashEquivalentsAtCarryingValue
Step 3: get_stock_price for {ticker or 'the ticker from submissions'}
Step 4: sec_fetch_filing_excerpt × 3 calls:
   - text_search_anchor="Results of Operations" (MD&A)
   - text_search_anchor="Risk Factors"
   - text_search_anchor="Liquidity"
Step 5: search_google × 2:
   - "{ticker} 10-Q filing earnings reaction"
   - "{ticker} analyst commentary outlook"
Step 6: visit_webpage on the best article from search results.
Step 7: submit_result with ALL fields filled comprehensively.

IMPORTANT:
- key_metrics must have 6-10 entries with real current + prior values and yoy_change_percent.
- All 6 numeric scores (0-100) must be filled based on your research.
- scored_items must have 5-12 entries covering different categories.
- fundamentals_from_sec, management_and_operations, risks_liquidity_capital, market_and_news,
  value_investor_takeaway are each a JSON ARRAY of strings (List[str]), NOT a single string.
  Each element is one bullet point. Provide 6-15 bullet points per field.
- Be explicit about which accession and period you analyzed. Cite every URL."""


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

        data = brief.model_dump()
        out_path = OUTPUT_DIR / f"demo_{ticker or cik}.json"
        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Result → %s", out_path)

        html_path = out_path.with_suffix(".html")
        html_path.write_text(generate_html(data), encoding="utf-8")
        logger.info("Dashboard → %s", html_path)
        import webbrowser
        webbrowser.open(str(html_path))

        # Pretty-print
        sep = "=" * 72
        print(f"\n{sep}")
        print(f"  {brief.entity_name or ticker or cik}  --  {brief.filing_focus}")
        print(f"  {brief.one_line_summary}")
        print(f"  Sentiment: {brief.overall_sentiment.upper()}  |  Importance: {brief.overall_importance.upper()}")
        print(sep)
        if brief.stock_price_snapshot:
            print(f"\nStock Price:\n{brief.stock_price_snapshot}\n")
        print(f"Scores: Revenue={brief.score_revenue_growth} Profit={brief.score_profitability} "
              f"Balance={brief.score_balance_sheet} Mgmt={brief.score_management_quality} "
              f"Sentiment={brief.score_market_sentiment} Risk={brief.score_risk_level}")
        if brief.key_metrics:
            print("\nKey Metrics:")
            for m in brief.key_metrics:
                sign = "+" if m.yoy_change_percent >= 0 else ""
                print(f"  {m.label}: {m.current_value:,.2f} ({m.period_current}) "
                      f"vs {m.prior_value:,.2f} ({m.period_prior}) "
                      f"[{sign}{m.yoy_change_percent:.1f}% YoY]")
        def _print_bullets(title, items):
            print(f"\n{title}:")
            if isinstance(items, list):
                for b in items:
                    print(f"  - {b}")
            else:
                print(f"  {items}")
            print()

        _print_bullets("Fundamentals", brief.fundamentals_from_sec)
        _print_bullets("Management & Ops", brief.management_and_operations)
        _print_bullets("Risks / Liquidity", brief.risks_liquidity_capital)
        _print_bullets("Market & News", brief.market_and_news)
        _print_bullets("Value Takeaway", brief.value_investor_takeaway)
        if brief.scored_items:
            print("Scored Items:")
            for si in brief.scored_items:
                print(f"  [{si.importance.upper():>9}] [{si.sentiment:>8}] [{si.surprise:>18}] "
                      f"{si.category}: {si.item}")
        if brief.action_flags:
            print(f"\nAction Flags:")
            for af in brief.action_flags:
                print(f"  -> {af}")
        print(f"\nCitations:\n{brief.citations}")
        if brief.caveats:
            print(f"\nCaveats:\n{brief.caveats}")
        print(sep)
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
