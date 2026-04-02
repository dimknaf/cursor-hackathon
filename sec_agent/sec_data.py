"""SEC EDGAR data helpers — compliant GETs and filing text extraction."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from sec_agent.config import config

logger = logging.getLogger(__name__)

SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window: float = 1.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self._times: list[float] = []
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            self._times = [t for t in self._times if now - t < self.time_window]
            if len(self._times) >= self.max_requests:
                sleep_s = self.time_window - (now - self._times[0])
                if sleep_s > 0:
                    time.sleep(sleep_s)
                self._times.pop(0)
            self._times.append(time.time())


_rate = RateLimiter()


def _headers() -> dict[str, str]:
    return {"User-Agent": config.sec_user_agent, "Accept-Encoding": "gzip, deflate"}


def cik_path_int(cik: str) -> int:
    return int(str(cik).strip().zfill(10))


def accession_no_dash(accession: str) -> str:
    return accession.replace("-", "").strip()


def archives_document_url(cik: str, accession: str, primary_document: str) -> str:
    return (
        f"{SEC_ARCHIVES_BASE}/{cik_path_int(cik)}/"
        f"{accession_no_dash(accession)}/{primary_document}"
    )


def get_submissions_json(cik: str) -> Optional[dict[str, Any]]:
    cik = str(cik).zfill(10)
    url = f"{SEC_DATA_BASE}/submissions/CIK{cik}.json"
    _rate.wait()
    try:
        r = requests.get(url, headers=_headers(), timeout=45)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("Submissions fetch failed: %s", e)
        return None


def get_company_concept_json(cik: str, taxonomy: str, concept: str) -> Optional[dict[str, Any]]:
    cik = str(cik).zfill(10)
    safe_concept = concept.strip().replace(" ", "")
    url = f"{SEC_DATA_BASE}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{safe_concept}.json"
    _rate.wait()
    try:
        r = requests.get(url, headers=_headers(), timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("Company concept fetch failed: %s", e)
        return None


def fetch_sec_raw_document(cik: str, accession: str, primary_document: str) -> Optional[str]:
    url = archives_document_url(cik, accession, primary_document)
    _rate.wait()
    try:
        r = requests.get(url, headers=_headers(), timeout=120)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        logger.error("Document fetch failed %s: %s", url, e)
        return None


def html_to_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def excerpt_around_anchor(
    text: str,
    anchor: str,
    max_chars: int,
) -> tuple[str, Optional[int]]:
    """Return excerpt centered on first case-insensitive anchor match."""
    if not anchor or not anchor.strip():
        return text[:max_chars] + ("..." if len(text) > max_chars else ""), None
    lower = text.lower()
    idx = lower.find(anchor.strip().lower())
    if idx < 0:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :] if len(text) > max_chars // 2 else ""
        return (
            head
            + "\n\n[anchor not found — start/end excerpt]\n\n"
            + tail
            + ("..." if len(text) > max_chars else ""),
            None,
        )
    half = max_chars // 2
    start = max(0, idx - half)
    end = min(len(text), idx + half)
    chunk = text[start:end]
    if start > 0:
        chunk = "..." + chunk
    if end < len(text):
        chunk = chunk + "..."
    return chunk, idx


def submissions_recent_forms_summary(
    data: dict[str, Any],
    form_filter: Optional[set[str]] = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Build a small JSON-serializable slice for the agent."""
    name = data.get("name", "")
    tickers = data.get("tickers", [])
    recent = data.get("filings", {}).get("recent", {})
    acc = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    reports = recent.get("reportDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    prim = recent.get("primaryDocument", [])

    rows: list[dict[str, Any]] = []
    for i in range(len(acc)):
        f = forms[i] if i < len(forms) else ""
        if form_filter and f not in form_filter:
            continue
        rows.append(
            {
                "form": f,
                "filingDate": dates[i] if i < len(dates) else "",
                "reportDate": reports[i] if i < len(reports) else "",
                "acceptanceDateTime": accepted[i] if i < len(accepted) else "",
                "accessionNumber": acc[i],
                "primaryDocument": prim[i] if i < len(prim) else "",
            }
        )
        if len(rows) >= limit:
            break

    return {
        "entityName": name,
        "tickers": tickers,
        "cik": str(data.get("cik", "")).zfill(10),
        "recent_filings": rows,
    }


def concept_observations_preview(concept_payload: dict[str, Any], max_points: int = 8) -> str:
    """Shrink companyconcept JSON for the agent."""
    if not concept_payload:
        return "{}"
    units = concept_payload.get("units") or {}
    out: dict[str, Any] = {
        "entityName": concept_payload.get("entityName"),
        "tag": concept_payload.get("tag"),
        "taxonomy": concept_payload.get("taxonomy"),
        "points": [],
    }
    for uom, series in units.items():
        if not isinstance(series, list):
            continue
        tail = series[-max_points:]
        for row in tail:
            if not isinstance(row, dict):
                continue
            out["points"].append(
                {
                    "uom": uom,
                    "val": row.get("val"),
                    "end": row.get("end"),
                    "start": row.get("start"),
                    "fp": row.get("fp"),
                    "fy": row.get("fy"),
                    "form": row.get("form"),
                    "filed": row.get("filed"),
                    "accn": row.get("accn"),
                }
            )
        break  # first unit bucket is enough for v1
    return json.dumps(out, indent=2)

