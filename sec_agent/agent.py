"""SEC filing research agent — Gemini via LiteLLM, same pattern as linkedin_research."""

import logging

from agents import Agent, ModelSettings, Runner, StopAtTools, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel
from openai.types.shared import Reasoning

from sec_agent.config import config
from sec_agent.models import FilingAnalysisResult
from sec_agent.tools import (
    search_google,
    sec_fetch_filing_excerpt,
    sec_get_xbrl_concept,
    sec_list_recent_filings,
    submit_result,
    visit_webpage,
    wait_for_human,
)

logger = logging.getLogger(__name__)

AGENT_INSTRUCTIONS = """You are a securities research assistant with a value-investor mindset (business quality,
balance sheet, sustainable economics — not hype).

## Tools (you decide which to call and in what order)

1. `sec_list_recent_filings` — latest filings for a CIK; get accession + primary_document.
2. `sec_get_xbrl_concept` — pull structured XBRL facts (e.g. Revenues, NetIncomeLoss, Assets, OperatingIncomeLoss).
3. `sec_fetch_filing_excerpt` — download the filing HTML from SEC Archives and return plain text. Use
   `text_search_anchor` to zoom in (e.g. "Management", "Risk Factors", "Liquidity", "Results of Operations").
   Call multiple times with different anchors if needed.
4. `search_google` — news, market commentary, reactions (always cite what you found).
5. `visit_webpage` — open specific URLs for deeper reading (crawl4ai markdown).
6. `wait_for_human` — only if blocked by CAPTCHA or consent.
7. `submit_result` — exactly once when finished.

## Rules

- Never invent numbers; fundamentals must trace to `sec_get_xbrl_concept` or filing text.
- If an XBRL concept 404s, try a close alternative or say so in caveats.
- Separate **SEC-grounded facts** from **media interpretation**.
- Keep tool use efficient (typically under ~12 tool calls) but prioritize correctness over brevity.
- For market context, query the ticker + filing type + "filing" or "earnings" and note timing.

## Output

Call `submit_result` with complete `FilingAnalysisResult` fields. Citations must list URLs you used.
"""


def create_sec_agent() -> Agent:
    if not config.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model = LitellmModel(model=config.agent_model, api_key=config.gemini_api_key)
    set_tracing_disabled(disabled=True)

    agent = Agent(
        name="SEC Filing Analyst",
        instructions=AGENT_INSTRUCTIONS,
        model=model,
        model_settings=ModelSettings(reasoning=Reasoning(effort=config.reasoning_effort)),
        tools=[
            sec_list_recent_filings,
            sec_get_xbrl_concept,
            sec_fetch_filing_excerpt,
            search_google,
            visit_webpage,
            wait_for_human,
            submit_result,
        ],
        tool_use_behavior=StopAtTools(stop_at_tool_names=["submit_result"]),
    )
    logger.info("SEC agent model=%s", config.agent_model)
    return agent


async def run_sec_analysis(agent: Agent, task_message: str) -> FilingAnalysisResult:
    """Run agent until submit_result; parse JSON into FilingAnalysisResult."""
    result = await Runner.run(
        starting_agent=agent,
        input=task_message,
        max_turns=config.agent_max_turns,
    )
    try:
        return FilingAnalysisResult.model_validate_json(result.final_output)
    except Exception as e:
        logger.error("Parse failed: %s", e)
        return FilingAnalysisResult(
            filing_focus="(parse error)",
            fundamentals_from_sec=str(result.final_output)[:1500],
            management_and_operations="",
            risks_liquidity_capital="",
            market_and_news="",
            value_investor_takeaway="Agent finished but output was not valid JSON.",
            citations="",
            caveats=str(e),
        )

