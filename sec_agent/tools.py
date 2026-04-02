"""Agent tools: SEC EDGAR + Google + crawl4ai visit + structured submit."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from agents import function_tool

from sec_agent.browser import BrowserManager
from sec_agent.config import config
from sec_agent.crawl_browser import CrawlBrowserManager
from sec_agent.models import FilingAnalysisResult
from sec_agent import sec_data

logger = logging.getLogger(__name__)

_browser: Optional[BrowserManager] = None
_crawl_browser: Optional[CrawlBrowserManager] = None


def set_browser(browser: BrowserManager) -> None:
    global _browser
    _browser = browser


def set_crawl_browser(crawl_browser: CrawlBrowserManager) -> None:
    global _crawl_browser
    _crawl_browser = crawl_browser


@function_tool
async def sec_list_recent_filings(cik: str, form_types: str = "10-Q,10-K") -> str:
    """
    List recent SEC filings for a CIK from data.sec.gov (submissions API).
    Use first to pick accession numbers and primary_document filenames.

    Args:
        cik: 10-digit or shorter CIK (e.g. 320193 or 0000320193).
        form_types: Comma-separated forms to include (default 10-Q,10-K).
    """
    flt = {x.strip().upper() for x in form_types.split(",") if x.strip()}
    raw = await asyncio.to_thread(sec_data.get_submissions_json, cik)
    if not raw:
        return "ERROR: Could not fetch submissions (check CIK and network)."
    summary = sec_data.submissions_recent_forms_summary(raw, form_filter=flt, limit=15)
    return json.dumps(summary, indent=2)


@function_tool
async def sec_get_xbrl_concept(
    cik: str,
    concept: str,
    taxonomy: str = "us-gaap",
) -> str:
    """
    Fetch XBRL time-series for one concept via companyconcept API (e.g. Revenues, Assets).

    Args:
        cik: Company CIK.
        concept: XBRL tag name (e.g. Revenues, NetIncomeLoss).
        taxonomy: Usually us-gaap.
    """
    raw = await asyncio.to_thread(
        sec_data.get_company_concept_json, cik, taxonomy, concept
    )
    if not raw:
        return f"ERROR: No data for concept '{concept}' (404 or network)."
    return sec_data.concept_observations_preview(raw, max_points=8)


@function_tool
async def sec_fetch_filing_excerpt(
    cik: str,
    accession_number: str,
    primary_document: str,
    text_search_anchor: str = "",
    max_chars: int = 24000,
) -> str:
    """
    Download a filing document from sec.gov Archives (HTML/XML) and return plain-text excerpt.

    Use accession_number and primary_document from sec_list_recent_filings.
    Optionally set text_search_anchor to jump near text (e.g. 'Management', 'Risk Factors').

    Args:
        cik: Company CIK.
        accession_number: SEC accession (with or without dashes).
        primary_document: Filename from submissions (e.g. nke-20251130.htm).
        text_search_anchor: Case-insensitive substring to center the excerpt.
        max_chars: Hard cap on returned characters (clamped).
    """
    cap = max(4000, min(int(max_chars), config.sec_filing_max_chars))
    html = await asyncio.to_thread(
        sec_data.fetch_sec_raw_document, cik, accession_number, primary_document
    )
    if not html:
        return "ERROR: Could not download filing document."
    text = sec_data.html_to_plain_text(html)
    excerpt, _ = sec_data.excerpt_around_anchor(text, text_search_anchor, cap)
    url = sec_data.archives_document_url(cik, accession_number, primary_document)
    header = f"=== Filing excerpt ===\nURL: {url}\nchars_returned={len(excerpt)}\n\n"
    return header + excerpt


@function_tool
async def search_google(query: str) -> str:
    """
    Google search via visible Playwright window; returns links and page text.
    Use for market reaction and breaking news after a filing.

    Args:
        query: Search query.
    """
    if not _browser:
        return "ERROR: Browser not initialized"
    url = f"https://www.google.com/search?q={query}&num=10"
    try:
        body_text = await _browser.navigate(url)
        page = _browser.page
        links: list[str] = []
        anchors = await page.query_selector_all("a[href]")
        for anchor in anchors[:40]:
            href = await anchor.get_attribute("href")
            text = (await anchor.inner_text()).strip()
            if not href or not text:
                continue
            if href.startswith("http") and "google" not in href:
                links.append(f"{text[:90]} -> {href}")
        cap = config.google_body_max_chars
        if len(body_text) > cap:
            body_text = body_text[:cap] + "\n... [truncated]"
        out = f"=== Google: {query} ===\n\n"
        if links:
            out += "Links:\n" + "\n".join(links[:12]) + "\n\n"
        out += "Page:\n" + body_text
        return out
    except Exception as e:
        logger.exception("Google search failed")
        return f"ERROR: Search failed — {e}"


@function_tool
async def visit_webpage(url: str) -> str:
    """
    Open a URL in crawl4ai's visible Chromium and return cleaned markdown.
    Prefer for long reads (news articles, SEC viewer pages).

    Args:
        url: Full URL.
    """
    cap = config.visit_webpage_max_chars
    if _crawl_browser:
        try:
            md = await _crawl_browser.fetch(url)
            if len(md) > cap:
                md = md[:cap] + "\n... [truncated]"
            return f"=== Page (crawl4ai) ===\n{url}\n\n{md}"
        except Exception as e:
            logger.warning("crawl4ai fetch failed: %s", e)

    if not _browser:
        return "ERROR: No browser available"
    try:
        body = await _browser.navigate(url)
        import re

        body = re.sub(r"\n{3,}", "\n\n", body)
        if len(body) > cap:
            body = body[:cap] + "\n... [truncated]"
        return f"=== Page (playwright) ===\n{url}\n\n{body}"
    except Exception as e:
        return f"ERROR: visit failed — {e}"


@function_tool
async def wait_for_human(reason: str) -> str:
    """Pause for CAPTCHA / consent; press Enter in terminal to continue."""
    if not _browser:
        return "ERROR: Browser not initialized"
    logger.info("Human help: %s", reason)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        input,
        f"\n>>> {reason}\n>>> Press Enter when done... ",
    )
    try:
        body = await _browser.page.inner_text("body")
        cap = config.google_body_max_chars
        if len(body) > cap:
            body = body[:cap] + "\n... [truncated]"
        return "Continued.\n\n" + body
    except Exception:
        return "Continued (could not read page)."


@function_tool
async def get_stock_price(ticker: str) -> str:
    """
    Get live/recent stock price, volume, and key stats from Yahoo Finance.
    Call this to ground your analysis with real price data instead of relying on news.

    Args:
        ticker: Stock ticker symbol (e.g. AAPL, MSFT).
    """
    try:
        import yfinance as yf

        t = await asyncio.to_thread(yf.Ticker, ticker.strip().upper())
        info = await asyncio.to_thread(lambda: t.fast_info)

        parts: list[str] = [f"=== Yahoo Finance: {ticker.upper()} ==="]
        try:
            parts.append(f"Last price: ${info['lastPrice']:.2f}")
        except Exception:
            pass
        try:
            parts.append(f"Previous close: ${info['previousClose']:.2f}")
        except Exception:
            pass
        try:
            parts.append(f"Open: ${info['open']:.2f}")
        except Exception:
            pass
        try:
            parts.append(f"Day range: ${info['dayLow']:.2f} – ${info['dayHigh']:.2f}")
        except Exception:
            pass
        try:
            parts.append(f"52-week range: ${info['fiftyTwoWeekLow']:.2f} – ${info['fiftyTwoWeekHigh']:.2f}")
        except Exception:
            pass
        try:
            parts.append(f"Market cap: ${info['marketCap']:,.0f}")
        except Exception:
            pass
        try:
            parts.append(f"Volume: {info['lastVolume']:,.0f}")
        except Exception:
            pass

        # Recent price history (5 days)
        hist = await asyncio.to_thread(lambda: t.history(period="5d"))
        if hist is not None and not hist.empty:
            parts.append("\nRecent 5-day history:")
            for idx, row in hist.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                parts.append(
                    f"  {date_str}  O=${row['Open']:.2f}  H=${row['High']:.2f}  "
                    f"L=${row['Low']:.2f}  C=${row['Close']:.2f}  Vol={int(row['Volume']):,}"
                )

        return "\n".join(parts) if len(parts) > 1 else f"ERROR: No data for {ticker}"
    except Exception as e:
        logger.exception("yfinance failed for %s", ticker)
        return f"ERROR: Could not fetch price for {ticker} — {e}"


@function_tool
async def submit_result(result: FilingAnalysisResult) -> str:
    """Call exactly once when analysis is complete."""
    return result.model_dump_json()
