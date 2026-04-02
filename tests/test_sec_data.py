"""Unit tests for SEC URL + excerpt helpers (no SEC HTTP by default)."""

import pytest

from sec_agent import sec_data


def test_archives_document_url_apple_shape():
    url = sec_data.archives_document_url(
        "0000320193",
        "0000320193-24-000123",
        "aapl-20241228.htm",
    )
    assert "/320193/000032019324000123/aapl-20241228.htm" in url
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/")


def test_cik_path_int():
    assert sec_data.cik_path_int("320193") == 320193
    assert sec_data.cik_path_int("0000320193") == 320193


def test_excerpt_around_anchor():
    text = "AAAA " + "Management Discussion " + "BBBB" * 2000
    ex, idx = sec_data.excerpt_around_anchor(text, "Management", 200)
    assert "Management" in ex
    assert idx is not None


def test_excerpt_anchor_missing():
    text = "x" * 5000
    ex, idx = sec_data.excerpt_around_anchor(text, "ZZZNope", 1000)
    assert idx is None
    assert "[anchor not found" in ex


def test_concept_preview_empty():
    assert sec_data.concept_observations_preview({}) == "{}"


@pytest.mark.integration
def test_live_submissions_apple():
    """Optional live call — set RUN_SEC_LIVE=1."""
    import os

    if os.getenv("RUN_SEC_LIVE") != "1":
        pytest.skip("RUN_SEC_LIVE not set")
    data = sec_data.get_submissions_json("0000320193")
    assert data and "filings" in data
    s = sec_data.submissions_recent_forms_summary(data, {"10-Q", "10-K"}, limit=3)
    assert s["recent_filings"]
