"""Build and maintain a watchlist of ~500 top US companies with CIKs.

Data flow:
    1. Fetch https://www.sec.gov/files/company_tickers.json (all SEC-registered tickers).
    2. Match against a built-in S&P-500-style ticker set.
    3. Save as watchlist.json  {ticker: {cik, title}} for the poller.

The S&P 500 constituent list is embedded here (tickers only) because it changes
slowly and there is no stable free API for it.  Re-run `build_watchlist()` to refresh CIKs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from sec_agent.config import config

logger = logging.getLogger(__name__)

WATCHLIST_PATH = Path(__file__).resolve().parent / "watchlist.json"

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# ── S&P 500 tickers (as of early 2025, ~503 tickers including dual-class) ──
# Source: Wikipedia / public reference. Some may rotate out; good enough for hackathon.
SP500_TICKERS: set[str] = {
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "ATVI", "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX",
    "BBWI", "BBY", "BDX", "BEN", "BF.B", "BIO", "BIIB", "BK", "BKNG", "BKR",
    "BLK", "BMY", "BR", "BRK.B", "BRO", "BSX", "BWA", "BXP", "C", "CAG",
    "CAH", "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDAY", "CDNS",
    "CDW", "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI", "CINF",
    "CL", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP",
    "COF", "COO", "COP", "COST", "CPB", "CPRT", "CPT", "CRL", "CRM", "CSCO",
    "CSGP", "CSX", "CTAS", "CTLT", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR",
    "D", "DAL", "DD", "DE", "DFS", "DG", "DGX", "DHI", "DHR", "DIS",
    "DISH", "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA",
    "DVN", "DXC", "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL",
    "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS",
    "ETN", "ETR", "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR", "F",
    "FANG", "FAST", "FBHS", "FCX", "FDS", "FDX", "FE", "FFIV", "FIS", "FISV",
    "FITB", "FLT", "FMC", "FOX", "FOXA", "FRC", "FRT", "FTNT", "FTV", "GD",
    "GE", "GEHC", "GEN", "GILD", "GIS", "GL", "GLW", "GM", "GNRC", "GOOG",
    "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA",
    "HOLX", "HON", "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUM",
    "HWM", "IBM", "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU",
    "INVH", "IP", "IPG", "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ",
    "J", "JBHT", "JCI", "JKHY", "JNJ", "JNPR", "JPM", "K", "KDP", "KEY",
    "KEYS", "KHC", "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR", "L",
    "LDOS", "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNC", "LNT",
    "LOW", "LRCX", "LUMN", "LUV", "LVS", "LW", "LYB", "LYV", "MA", "MAA",
    "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META",
    "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO", "MOH",
    "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRO", "MS", "MSCI", "MSFT", "MSI",
    "MTB", "MTCH", "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX",
    "NI", "NKE", "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA",
    "NVR", "NWL", "NWS", "NWSA", "NXPI", "O", "ODFL", "OGN", "OKE", "OMC",
    "ON", "ORCL", "ORLY", "OTIS", "OXY", "PARA", "PAYC", "PAYX", "PCAR", "PCG",
    "PEAK", "PEG", "PEP", "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG",
    "PKI", "PLD", "PM", "PNC", "PNR", "PNW", "POOL", "PPG", "PPL", "PRU",
    "PSA", "PSX", "PTC", "PVH", "PWR", "PXD", "PYPL", "QCOM", "QRVO", "RCL",
    "RE", "REG", "REGN", "RF", "RHI", "RJF", "RL", "RMD", "ROK", "ROL",
    "ROP", "ROST", "RSG", "RTX", "SBAC", "SBNY", "SBUX", "SCHW", "SEE", "SHW",
    "SIVB", "SJM", "SLB", "SNA", "SNPS", "SO", "SPG", "SPGI", "SRE", "STE",
    "STT", "STX", "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP",
    "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT", "TMO", "TMUS",
    "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO",
    "TXN", "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS",
    "URI", "USB", "V", "VFC", "VICI", "VLO", "VMC", "VNO", "VRSK", "VRSN",
    "VRTX", "VTR", "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC",
    "WELL", "WFC", "WHR", "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW",
    "WY", "WYNN", "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH", "ZBRA", "ZION",
    "ZTS",
}


def fetch_sec_tickers() -> dict[str, Any]:
    """Download the official SEC company_tickers.json."""
    headers = {"User-Agent": config.sec_user_agent}
    r = requests.get(SEC_TICKERS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def build_watchlist(extra_tickers: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Build {TICKER: {cik_str, title}} for S&P 500 (+ extras)."""
    wanted = SP500_TICKERS | (extra_tickers or set())
    raw = fetch_sec_tickers()

    # raw format:  {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    result: dict[str, dict[str, Any]] = {}
    for _idx, entry in raw.items():
        ticker = str(entry.get("ticker", "")).upper()
        if ticker in wanted:
            cik = str(entry.get("cik_str", "")).zfill(10)
            result[ticker] = {"cik": cik, "title": entry.get("title", "")}
    return result


def save_watchlist(watchlist: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    dest = path or WATCHLIST_PATH
    dest.write_text(json.dumps(watchlist, indent=2, sort_keys=True), encoding="utf-8")
    logger.info("Watchlist saved: %d tickers → %s", len(watchlist), dest)
    return dest


def load_watchlist(path: Path | None = None) -> dict[str, dict[str, Any]]:
    src = path or WATCHLIST_PATH
    if not src.exists():
        raise FileNotFoundError(f"No watchlist at {src} — run build_watchlist first")
    return json.loads(src.read_text(encoding="utf-8"))


def cik_set_from_watchlist(watchlist: dict[str, dict[str, Any]]) -> set[str]:
    """Return all 10-digit CIKs for fast membership checks in the poller."""
    return {v["cik"] for v in watchlist.values()}


# ── CLI ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    wl = build_watchlist()
    p = save_watchlist(wl)
    matched = len(wl)
    print(f"Built watchlist: {matched} tickers matched out of {len(SP500_TICKERS)} wanted")
    print(f"Saved to {p}")
    # Show a sample
    for t in sorted(wl)[:10]:
        print(f"  {t:6s}  CIK={wl[t]['cik']}  {wl[t]['title']}")
