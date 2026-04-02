"""Always-on webhook server: poller + FastAPI endpoint.

Two modes of operation work together:

1. **Background poller** — polls SEC XBRL RSS every N minutes. When a new
   10-Q / 10-K is found for a watchlisted company, it fires an internal
   POST to /webhook/filing with the FilingEvent JSON.

2. **Webhook endpoint** — receives POST /webhook/filing (from the poller
   *or* from external callers / simulations) and launches the SEC agent
   asynchronously. Results go to sec_agent/output/.

Start:
    python -m sec_agent.webhook_server            # default port 8000
    python -m sec_agent.webhook_server --port 9000 --poll-interval 120

The poller runs in a background thread; the FastAPI server runs in the main
thread via uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import requests
import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from sec_agent.agent import create_sec_agent, run_sec_analysis
from sec_agent.browser import BrowserManager
from sec_agent.config import OUTPUT_DIR, config
from sec_agent.crawl_browser import CrawlBrowserManager
from sec_agent.dashboard import build_all_dashboards, generate_html
from sec_agent.demo import DEMO_CIKS, build_task
from sec_agent.poller import FilingEvent, poll_rss_for_watchlist
from sec_agent.tools import set_browser, set_crawl_browser
from sec_agent.watchlist import (
    build_watchlist,
    cik_set_from_watchlist,
    load_watchlist,
    save_watchlist,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SEC Filing Agent — Webhook Server")

ACTIVE_JOBS: dict[str, dict] = {}


class FilingWebhookPayload(BaseModel):
    cik: str
    ticker: str = ""
    entity_name: str = ""
    form_type: str = ""
    accession_number: str = ""
    filing_date: str = ""
    filing_url: str = ""


# ── Agent runner (runs in background) ──

async def _run_agent_for_filing(payload: FilingWebhookPayload):
    job_id = f"{payload.ticker or payload.cik}_{datetime.utcnow().strftime('%H%M%S')}"
    ACTIVE_JOBS[job_id] = {"status": "running", "started": datetime.utcnow().isoformat(), "payload": payload.model_dump()}
    logger.info("JOB %s: starting agent for %s (%s)", job_id, payload.ticker, payload.cik)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    browser = BrowserManager()
    crawl = CrawlBrowserManager()

    try:
        await browser.launch(visible=config.browser_visible)
        await crawl.launch(visible=config.browser_visible)
        set_browser(browser)
        set_crawl_browser(crawl)

        agent = create_sec_agent()
        task = build_task(payload.cik, payload.ticker)
        brief = await run_sec_analysis(agent, task)

        data = brief.model_dump()
        label = payload.ticker or payload.cik
        out_json = OUTPUT_DIR / f"demo_{label}.json"
        out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        json_files = sorted(OUTPUT_DIR.glob("demo_*.json"))
        out_html = out_json.with_suffix(".html")
        out_html.write_text(generate_html(data, all_files=json_files, current_file=out_json), encoding="utf-8")

        ACTIVE_JOBS[job_id] = {
            "status": "completed",
            "finished": datetime.utcnow().isoformat(),
            "output_json": str(out_json),
            "output_html": str(out_html),
            "sentiment": brief.overall_sentiment,
            "importance": brief.overall_importance,
            "summary": brief.one_line_summary,
        }
        logger.info("JOB %s: completed → %s", job_id, out_json)
    except Exception as e:
        ACTIVE_JOBS[job_id] = {"status": "failed", "error": str(e)}
        logger.exception("JOB %s: failed", job_id)
    finally:
        await crawl.close()
        await browser.close()


# ── Routes ──

@app.post("/webhook/filing")
async def webhook_filing(payload: FilingWebhookPayload, bg: BackgroundTasks):
    """Receive a filing event and start the agent in the background."""
    logger.info("WEBHOOK received: %s %s (%s)", payload.ticker, payload.form_type, payload.cik)
    bg.add_task(asyncio.create_task, _run_agent_for_filing(payload))
    return JSONResponse(
        {"ok": True, "message": f"Agent started for {payload.ticker or payload.cik}"},
        status_code=202,
    )


@app.get("/jobs")
async def list_jobs():
    """Show all jobs and their statuses."""
    return ACTIVE_JOBS


@app.get("/health")
async def health():
    return {"status": "running", "jobs": len(ACTIVE_JOBS), "time": datetime.utcnow().isoformat()}


@app.get("/", response_class=HTMLResponse)
async def index():
    jobs_html = ""
    for jid, info in ACTIVE_JOBS.items():
        status = info.get("status", "unknown")
        color = {"running": "#eab308", "completed": "#22c55e", "failed": "#ef4444"}.get(status, "#8b8d97")
        summary = info.get("summary", info.get("error", ""))
        jobs_html += f'<div style="padding:8px 12px;border-left:3px solid {color};margin:6px 0;background:#1a1d27;border-radius:0 8px 8px 0"><b>{jid}</b> — <span style="color:{color}">{status}</span><br><small>{summary}</small></div>'
    if not jobs_html:
        jobs_html = '<p style="color:#8b8d97">No jobs yet. Send a POST to /webhook/filing or use /simulate/{ticker}</p>'

    return f"""<!DOCTYPE html><html><head><title>SEC Agent Server</title>
<style>body{{font-family:system-ui;background:#0f1117;color:#e4e6eb;padding:24px;max-width:800px;margin:auto}}
a{{color:#6366f1}}</style></head><body>
<h1>SEC Filing Agent — Webhook Server</h1>
<p>Endpoints:</p>
<ul>
<li><code>POST /webhook/filing</code> — trigger agent (JSON body with cik, ticker, etc.)</li>
<li><code>GET /simulate/AAPL</code> — simulate a filing event for quick testing</li>
<li><code>GET /jobs</code> — list all jobs</li>
<li><code>GET /health</code> — health check</li>
</ul>
<h2>Jobs</h2>
{jobs_html}
</body></html>"""


@app.get("/simulate/{ticker}")
async def simulate(ticker: str, bg: BackgroundTasks):
    """Quick test: simulate a filing event for a known ticker."""
    ticker = ticker.upper()
    cik = DEMO_CIKS.get(ticker, "")
    if not cik:
        return JSONResponse(
            {"error": f"Unknown ticker '{ticker}'. Known: {', '.join(sorted(DEMO_CIKS))}"},
            status_code=400,
        )
    payload = FilingWebhookPayload(cik=cik, ticker=ticker, form_type="10-Q", entity_name=f"{ticker} (simulated)")
    bg.add_task(asyncio.create_task, _run_agent_for_filing(payload))
    return JSONResponse(
        {"ok": True, "message": f"Simulated filing event for {ticker} — agent starting in background"},
        status_code=202,
    )


# ── Poller thread ──

def _poller_thread(port: int, interval: int, watched_ciks: set[str], cik_to_ticker: dict[str, str]):
    """Background thread: poll SEC RSS and POST to our own webhook."""
    logger.info("Poller thread started — interval=%ds, watching %d CIKs", interval, len(watched_ciks))
    webhook_url = f"http://127.0.0.1:{port}/webhook/filing"

    while True:
        try:
            events = poll_rss_for_watchlist(watched_ciks)
            for ev in events:
                ticker = cik_to_ticker.get(ev.cik, "")
                payload = {
                    "cik": ev.cik,
                    "ticker": ticker,
                    "entity_name": ev.entity_name,
                    "form_type": ev.form_type,
                    "accession_number": ev.accession_number,
                    "filing_date": ev.filing_date,
                    "filing_url": ev.filing_url,
                }
                logger.info("POLLER → webhook: %s %s %s", ticker or ev.cik, ev.form_type, ev.accession_number)
                try:
                    r = requests.post(webhook_url, json=payload, timeout=10)
                    logger.info("Webhook response: %d", r.status_code)
                except Exception:
                    logger.exception("Failed to POST to webhook")
            if not events:
                logger.info("Poller: no new filings this cycle")
        except Exception:
            logger.exception("Poller cycle error")
        time.sleep(interval)


# ── Main ──

def main():
    p = argparse.ArgumentParser(description="SEC agent webhook server + poller")
    p.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    p.add_argument("--poll-interval", type=int, default=300, help="Poller interval in seconds (default: 300)")
    p.add_argument("--no-poller", action="store_true", help="Disable background SEC poller (webhook-only mode)")
    args = p.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.no_poller:
        try:
            wl = load_watchlist()
        except FileNotFoundError:
            logger.info("Building watchlist...")
            wl = build_watchlist()
            save_watchlist(wl)

        watched_ciks = cik_set_from_watchlist(wl)
        cik_to_ticker = {v["cik"]: t for t, v in wl.items()}
        logger.info("Watchlist: %d companies loaded", len(wl))

        poller = threading.Thread(
            target=_poller_thread,
            args=(args.port, args.poll_interval, watched_ciks, cik_to_ticker),
            daemon=True,
        )
        poller.start()
    else:
        logger.info("Poller disabled — webhook-only mode")

    logger.info("Starting server on http://127.0.0.1:%d", args.port)
    logger.info("  POST /webhook/filing    — trigger agent")
    logger.info("  GET  /simulate/{ticker} — quick test (AAPL, MSFT, TSLA, ...)")
    logger.info("  GET  /jobs              — check status")
    logger.info("  GET  /                  — dashboard")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
