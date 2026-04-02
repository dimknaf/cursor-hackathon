"""Poll SEC EDGAR RSS feed for new filings from watched companies.

Instead of hitting /submissions for each of 500 CIKs, we poll ONE RSS feed:
    https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=10-K&dateb=&owner=include&count=40&search_text=&output=atom

Or the XBRL RSS:
    https://www.sec.gov/Archives/edgar/xbrlrss.all.xml

The XBRL feed is updated every 10 minutes (Mon-Fri 6am-10pm ET) and contains
ALL inline-XBRL filings.  We parse, filter by our watchlist CIKs and form type,
and yield FilingEvent objects for new accessions.

Watermark: we track the last-seen accession in a small JSON file so restarts
don't re-fire.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from sec_agent.config import config

logger = logging.getLogger(__name__)

XBRL_RSS_URL = "https://www.sec.gov/Archives/edgar/xbrlrss.all.xml"
LATEST_FILINGS_ATOM_TPL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type={form_type}&dateb=&owner=include"
    "&count={count}&search_text=&output=atom"
)

WATERMARK_PATH = Path(__file__).resolve().parent / "output" / "watermark.json"

FORM_TYPES_DEFAULT = {"10-Q", "10-K", "10-Q/A", "10-K/A", "8-K"}


@dataclass
class FilingEvent:
    cik: str
    entity_name: str
    form_type: str
    accession_number: str
    filing_date: str
    acceptance_datetime: str = ""
    primary_document: str = ""
    filing_url: str = ""
    ticker: str = ""
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _headers() -> dict[str, str]:
    return {"User-Agent": config.sec_user_agent}


# ── Watermark ──

def load_watermark(path: Path | None = None) -> set[str]:
    p = path or WATERMARK_PATH
    if not p.exists():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    return set(data.get("seen_accessions", []))


def save_watermark(seen: set[str], path: Path | None = None, max_keep: int = 2000) -> None:
    p = path or WATERMARK_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(seen)[-max_keep:]
    p.write_text(
        json.dumps({"seen_accessions": trimmed, "updated_at": datetime.utcnow().isoformat()}, indent=2),
        encoding="utf-8",
    )


# ── XBRL RSS parser ──

def fetch_xbrl_rss() -> list[dict]:
    """Fetch and parse the SEC XBRL RSS feed into dicts."""
    r = requests.get(XBRL_RSS_URL, headers=_headers(), timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    ns = {
        "": "http://www.w3.org/2005/Atom",
        "edgar": "http://www.sec.gov/Archives/edgar",
    }

    items: list[dict] = []
    for item in root.iter("item"):
        title_el = item.find("title")
        desc_el = item.find("description")
        link_el = item.find("link")

        edgar_ns = "http://www.sec.gov/Archives/edgar"
        xbrl_filing = item.find(f"{{{edgar_ns}}}xbrlFiling")

        entry: dict = {
            "title": title_el.text.strip() if title_el is not None and title_el.text else "",
            "link": link_el.text.strip() if link_el is not None and link_el.text else "",
        }

        if xbrl_filing is not None:
            entry["cik"] = (xbrl_filing.findtext(f"{{{edgar_ns}}}cikNumber") or "").strip()
            entry["company"] = (xbrl_filing.findtext(f"{{{edgar_ns}}}companyName") or "").strip()
            entry["form"] = (xbrl_filing.findtext(f"{{{edgar_ns}}}formType") or "").strip()
            entry["filingDate"] = (xbrl_filing.findtext(f"{{{edgar_ns}}}filingDate") or "").strip()
            entry["accession"] = (xbrl_filing.findtext(f"{{{edgar_ns}}}accessionNumber") or "").strip()
            entry["acceptanceDatetime"] = (
                xbrl_filing.findtext(f"{{{edgar_ns}}}acceptanceDatetime") or ""
            ).strip()
            # Files list
            files_el = xbrl_filing.find(f"{{{edgar_ns}}}xbrlFiles")
            if files_el is not None:
                for f in files_el.findall(f"{{{edgar_ns}}}xbrlFile"):
                    desc = f.get(f"{{{edgar_ns}}}description", "") or f.get("description", "")
                    if desc and desc.strip().upper() in ("", "COMPLETE SUBMISSION TEXT FILE"):
                        continue
                    url = f.get(f"{{{edgar_ns}}}url", "") or f.get("url", "")
                    ftype = f.get(f"{{{edgar_ns}}}type", "") or f.get("type", "")
                    if ftype and ftype.strip().upper() in ("EX-101.INS", "EX-101.SCH"):
                        continue
                    if url and (url.endswith(".htm") or url.endswith(".html")):
                        entry.setdefault("primaryDocumentUrl", url)
                        break
        items.append(entry)

    logger.info("XBRL RSS: parsed %d items", len(items))
    return items


def poll_rss_for_watchlist(
    watched_ciks: set[str],
    form_types: set[str] | None = None,
) -> list[FilingEvent]:
    """One poll cycle: fetch RSS, filter, return new FilingEvents."""
    forms = form_types or FORM_TYPES_DEFAULT
    seen = load_watermark()
    items = fetch_xbrl_rss()

    new_events: list[FilingEvent] = []
    for item in items:
        accn = item.get("accession", "").strip()
        if not accn or accn in seen:
            continue
        cik_raw = item.get("cik", "").strip()
        if not cik_raw:
            continue
        cik10 = cik_raw.zfill(10)
        if cik10 not in watched_ciks:
            continue
        form = item.get("form", "").strip()
        if form not in forms:
            continue

        primary_url = item.get("primaryDocumentUrl", "")
        primary_doc = primary_url.rsplit("/", 1)[-1] if primary_url else ""

        ev = FilingEvent(
            cik=cik10,
            entity_name=item.get("company", ""),
            form_type=form,
            accession_number=accn,
            filing_date=item.get("filingDate", ""),
            acceptance_datetime=item.get("acceptanceDatetime", ""),
            primary_document=primary_doc,
            filing_url=primary_url or item.get("link", ""),
        )
        new_events.append(ev)
        seen.add(accn)

    if new_events:
        save_watermark(seen)
        logger.info("New filings detected: %d", len(new_events))
    return new_events


# ── Fallback: latest-filings Atom feed (form-specific) ──

def fetch_latest_atom(form_type: str = "10-Q", count: int = 40) -> list[dict]:
    """SEC Atom feed for specific form type (lightweight alternative to XBRL RSS)."""
    url = LATEST_FILINGS_ATOM_TPL.format(form_type=form_type, count=count)
    r = requests.get(url, headers=_headers(), timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items: list[dict] = []
    for entry in root.findall("a:entry", ns):
        title = entry.findtext("a:title", "", ns).strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        updated = entry.findtext("a:updated", "", ns).strip()
        summary = entry.findtext("a:summary", "", ns).strip()
        # Try to extract CIK and accession from the link
        accn = ""
        cik = ""
        if "/Archives/edgar/data/" in link:
            parts = link.split("/Archives/edgar/data/")
            if len(parts) > 1:
                seg = parts[1].strip("/").split("/")
                if seg:
                    cik = seg[0]
                if len(seg) > 1:
                    accn = seg[1]
        items.append({
            "title": title,
            "link": link,
            "updated": updated,
            "summary": summary,
            "cik": cik.zfill(10) if cik else "",
            "accession": accn,
            "form": form_type,
        })
    logger.info("Atom feed (%s): parsed %d entries", form_type, len(items))
    return items


# ── Continuous loop (for demo / background service) ──

def run_poll_loop(
    watched_ciks: set[str],
    interval_seconds: int = 300,
    callback=None,
    max_iterations: int = 0,
):
    """Blocking loop: poll every `interval_seconds`, call `callback(event)` for each new filing."""
    iteration = 0
    while True:
        iteration += 1
        logger.info("Poll iteration %d", iteration)
        try:
            events = poll_rss_for_watchlist(watched_ciks)
            for ev in events:
                logger.info("FILING: %s %s %s [%s]", ev.entity_name, ev.form_type, ev.accession_number, ev.filing_date)
                if callback:
                    callback(ev)
        except Exception:
            logger.exception("Poll error")
        if max_iterations and iteration >= max_iterations:
            break
        logger.info("Sleeping %ds until next poll", interval_seconds)
        time.sleep(interval_seconds)


# ── CLI ──

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from sec_agent.watchlist import load_watchlist, cik_set_from_watchlist, build_watchlist, save_watchlist

    try:
        wl = load_watchlist()
    except FileNotFoundError:
        logger.info("No watchlist found — building...")
        wl = build_watchlist()
        save_watchlist(wl)

    ciks = cik_set_from_watchlist(wl)
    logger.info("Watching %d CIKs", len(ciks))

    def on_filing(ev: FilingEvent):
        print(json.dumps(asdict(ev), indent=2))

    run_poll_loop(ciks, interval_seconds=300, callback=on_filing, max_iterations=1)
