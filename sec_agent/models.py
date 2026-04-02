"""Structured output for SEC filing analysis (submit_result tool)."""

from pydantic import BaseModel, Field


class FilingAnalysisResult(BaseModel):
    """One-shot structured brief after the agent finishes tool use."""

    entity_name: str = Field(default="", description="Company name from SEC or search")
    cik: str = Field(default="", description="10-digit CIK")
    tickers: str = Field(default="", description="Comma-separated tickers if known")
    filing_focus: str = Field(
        ...,
        description=(
            "Which filing(s) you analyzed: form, filing date, accession, primary document name"
        ),
    )
    fundamentals_from_sec: str = Field(
        ...,
        description=(
            "What the numbers say — grounded in companyconcept/company facts you pulled; "
            "note period and units; no invented figures"
        ),
    )
    management_and_operations: str = Field(
        ...,
        description=(
            "Material MD&A / ops themes from filing excerpts you fetched — demand, margins, "
            "costs, segments, one-offs"
        ),
    )
    risks_liquidity_capital: str = Field(
        ...,
        description="Risk / liquidity / capital resources highlights if visible in excerpts",
    )
    market_and_news: str = Field(
        ...,
        description="How press/market frame the release — from Google/search pages; note recency",
    )
    value_investor_takeaway: str = Field(
        ...,
        description=(
            "3–6 sentences: business quality, balance sheet stress, durability of economics — "
            "plain language, no price targets unless sourced"
        ),
    )
    citations: str = Field(
        ...,
        description="URLs and section hints you relied on (one per line)",
    )
    caveats: str = Field(
        ...,
        description="What was missing, partial extraction, paywalls, or ambiguous tags",
    )
