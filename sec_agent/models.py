"""Structured output models for SEC filing analysis."""

from typing import List, Literal

from pydantic import BaseModel, Field


class ScoredItem(BaseModel):
    """One scored element from the filing analysis."""

    item: str = Field(..., description="The specific finding or data point (1-2 sentences)")
    category: Literal[
        "revenue", "profitability", "balance_sheet", "cash_flow",
        "management", "risk", "market_reaction", "guidance", "other",
    ] = Field(..., description="Category")
    importance: Literal["critical", "important", "minor"] = Field(
        ..., description="How material is this for an investor"
    )
    sentiment: Literal["positive", "negative", "neutral", "mixed"] = Field(
        ..., description="Directional sentiment"
    )
    surprise: Literal["surprise_positive", "surprise_negative", "expected", "unclear"] = Field(
        ..., description="Was this better/worse than the prior period or market expectations"
    )
    explanation: str = Field(
        ..., description="1-2 sentence reasoning for importance/sentiment/surprise"
    )


class KeyMetric(BaseModel):
    """A single financial metric with current and prior values — for dashboard charts."""

    label: str = Field(..., description="Human-readable name (e.g. 'Revenue', 'Net Income', 'Diluted EPS')")
    current_value: float = Field(..., description="Value for the current reporting period")
    prior_value: float = Field(0.0, description="Value for same period last year (YoY) or prior quarter")
    unit: str = Field("USD", description="USD, shares, ratio, percent, USD_billions, USD_millions")
    period_current: str = Field("", description="e.g. Q1 FY2026")
    period_prior: str = Field("", description="e.g. Q1 FY2025")
    yoy_change_percent: float = Field(
        0.0,
        description="Year-over-year change as percentage (e.g. 16.0 for +16%). Compute from current vs prior.",
    )


class FilingAnalysisResult(BaseModel):
    """Complete agent output — research brief + scoring + dashboard numbers. One submit_result call."""

    # ── Identity ──
    entity_name: str = Field(default="", description="Company name from SEC or search")
    cik: str = Field(default="", description="10-digit CIK")
    tickers: str = Field(default="", description="Comma-separated tickers if known")
    filing_focus: str = Field(
        ...,
        description="Which filing you analyzed: form type, filing date, report date, accession number, primary document filename",
    )

    # ── Live price ──
    stock_price_snapshot: str = Field(
        default="",
        description="Current price, previous close, day range, 52-week range, market cap, recent 5-day history from get_stock_price",
    )

    # ── Dashboard numbers (for charts) ──
    key_metrics: List[KeyMetric] = Field(
        ...,
        description=(
            "6-10 metrics extracted from sec_get_xbrl_concept with current + prior values. "
            "MUST include at minimum: Revenue, Net Income, Diluted EPS, Operating Income, "
            "Total Assets, Cash. Add more if available (Gross Profit, Operating Cash Flow, "
            "Total Debt, Shares Outstanding). Use consistent units. "
            "current_value and prior_value must be real numbers from XBRL, not invented."
        ),
    )

    # ── Numeric scores (0-100, for gauges/radar) ──
    score_revenue_growth: int = Field(
        ..., ge=0, le=100,
        description="0-100: How strong is revenue growth? 0=declining badly, 50=flat, 100=exceptional growth",
    )
    score_profitability: int = Field(
        ..., ge=0, le=100,
        description="0-100: How healthy are margins and earnings? 0=deep losses, 50=breakeven, 100=expanding high margins",
    )
    score_balance_sheet: int = Field(
        ..., ge=0, le=100,
        description="0-100: Balance sheet quality. 0=distressed/high leverage, 50=adequate, 100=fortress/net cash",
    )
    score_management_quality: int = Field(
        ..., ge=0, le=100,
        description="0-100: Based on MD&A quality, capital allocation, strategic clarity. 0=concerning, 100=exceptional",
    )
    score_market_sentiment: int = Field(
        ..., ge=0, le=100,
        description="0-100: How positive is market/analyst reaction? 0=very negative, 50=neutral, 100=very positive",
    )
    score_risk_level: int = Field(
        ..., ge=0, le=100,
        description="0-100: Overall risk level INVERTED — 0=very risky, 50=normal risk, 100=very low risk",
    )

    # ── Fundamentals (bullet points) ──
    fundamentals_from_sec: List[str] = Field(
        ...,
        description=(
            "8-15 bullet points covering ALL key metrics from XBRL. Each bullet is one self-contained "
            "data point with the EXACT number, period, and YoY comparison. Examples: "
            "'Revenue: $124.3B in Q1 FY2026 (ended Dec 27 2025), up +4.0% YoY from $119.6B', "
            "'Net Income: $36.3B, up +7.1% YoY from $33.9B', "
            "'Diluted EPS: $2.40, up +10.1% YoY from $2.18'. "
            "Cover: revenue, net income, operating income, EPS, total assets, cash, and any others "
            "you pulled from sec_get_xbrl_concept. Note units (billions/millions)."
        ),
    )

    # ── MD&A (bullet points) ──
    management_and_operations: List[str] = Field(
        ...,
        description=(
            "8-15 bullet points from the actual filing MD&A text via sec_fetch_filing_excerpt. "
            "Each bullet covers one specific theme: revenue drivers by segment, gross margin trends, "
            "operating expense trajectory, geographic performance, management commentary on demand, "
            "pricing, competition, investments, new products, or strategic shifts. "
            "Quote or closely paraphrase specific language from the filing. "
            "Do NOT be vague — each bullet should be an actionable insight."
        ),
    )

    # ── Risks (bullet points) ──
    risks_liquidity_capital: List[str] = Field(
        ...,
        description=(
            "6-12 bullet points from Risk Factors and Liquidity sections of the filing. "
            "Cover: cash position, debt levels and maturities, credit facility status, "
            "capital expenditure plans, share buyback and dividend programs, working capital trends. "
            "Flag any NEW risks. Quote specific risk language if material. "
            "Each bullet should be one distinct risk or liquidity data point."
        ),
    )

    # ── Market reaction (bullet points) ──
    market_and_news: List[str] = Field(
        ...,
        description=(
            "6-12 bullet points from search_google and visit_webpage results. "
            "Name sources (e.g. 'Reuters reported...', 'According to Barron's...'). "
            "Cover: stock price move post-filing, analyst upgrades/downgrades, key commentary quotes, "
            "consensus view on guidance, any controversy. Note dates. "
            "Each bullet is one news item or analyst view with attribution."
        ),
    )

    # ── Value takeaway (bullet points) ──
    value_investor_takeaway: List[str] = Field(
        ...,
        description=(
            "5-10 bullet points written for a long-term value investor. "
            "Address: (1) business quality and competitive moat, (2) balance sheet strength or stress, "
            "(3) durability and predictability of earnings, (4) capital allocation quality, "
            "(5) what changed in the economic reality based on this filing. "
            "No price targets. Plain language. Final bullet: what to WATCH going forward."
        ),
    )

    # ── Scoring (inline) ──
    overall_sentiment: Literal["bullish", "bearish", "neutral", "mixed"] = Field(
        ..., description="Overall tone from the filing and market reaction combined"
    )
    overall_importance: Literal["high", "medium", "low"] = Field(
        ..., description="How significant is this filing for the investment thesis"
    )
    one_line_summary: str = Field(
        ..., description="Single sentence a portfolio manager reads first — what happened and does it matter"
    )
    scored_items: List[ScoredItem] = Field(
        ...,
        description=(
            "5-12 scored elements: the most important findings from your research. "
            "Cover revenue, profitability, balance sheet, management themes, risks, "
            "and market reaction. Each gets importance/sentiment/surprise ratings."
        ),
    )
    action_flags: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 short action items for the investor: what to watch next quarter, "
            "what changed that needs monitoring, what follow-up research to do"
        ),
    )

    # ── Provenance ──
    citations: str = Field(
        ...,
        description="Every URL you visited or used (one per line) — SEC archives, news articles, Yahoo Finance",
    )
    caveats: str = Field(
        ...,
        description="Missing data, partial extractions, 404 XBRL concepts, paywalled articles, anything incomplete",
    )
