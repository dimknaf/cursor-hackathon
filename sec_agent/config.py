"""Configuration for SEC filing research agent (Gemini + OpenAI Agents SDK)."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    _PKG_DIR = Path(__file__).resolve().parent
    _REPO_DIR = _PKG_DIR.parent
    # Repo root `.env` first, then `sec_agent/.env` — already-set env vars are not overwritten.
    load_dotenv(_REPO_DIR / ".env")
    load_dotenv(_PKG_DIR / ".env")
except ImportError:
    _PKG_DIR = Path(__file__).resolve().parent
    _REPO_DIR = _PKG_DIR.parent

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "session"
OUTPUT_DIR = BASE_DIR / "output"


@dataclass
class Config:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    agent_model: str = os.getenv(
        "AGENT_MODEL", "gemini/gemini-3.1-flash-lite-preview"
    )
    reasoning_effort: str = os.getenv("REASONING_EFFORT", "low")
    agent_max_turns: int = int(os.getenv("AGENT_MAX_TURNS", "40"))

    # SEC EDGAR: no API key; fair access requires a descriptive User-Agent (name + email).
    # Override with env SEC_USER_AGENT only if you need to rotate contact.
    sec_user_agent: str = os.getenv(
        "SEC_USER_AGENT", "Dimitris dimknaf@gmail.com"
    )

    # Browser
    min_navigation_delay: float = float(os.getenv("MIN_NAVIGATION_DELAY", "2.0"))
    max_navigation_delay: float = float(os.getenv("MAX_NAVIGATION_DELAY", "4.5"))
    google_requests_per_minute: int = int(os.getenv("GOOGLE_REQUESTS_PER_MINUTE", "10"))
    page_load_timeout: int = int(os.getenv("PAGE_LOAD_TIMEOUT_MS", "60000"))

    # Content limits (tools)
    google_body_max_chars: int = int(os.getenv("GOOGLE_BODY_MAX_CHARS", "9000"))
    visit_webpage_max_chars: int = int(os.getenv("VISIT_WEBPAGE_MAX_CHARS", "14000"))
    sec_filing_max_chars: int = int(os.getenv("SEC_FILING_MAX_CHARS", "28000"))

    # Visible browsers (demo / debugging)
    browser_visible: bool = os.getenv("BROWSER_VISIBLE", "true").lower() == "true"

    debug_mode: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"


config = Config()
