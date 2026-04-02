---
name: fa-agent-stack-openai-agents-browser
description: Build multi-turn research agents with OpenAI Agents SDK, LiteLLM (Gemini), Playwright + crawl4ai browsing tools, Pydantic structured completion via submit_result, and optional non-agentic structured parsing — matching the fa-automation linkedin_research task pattern.
---

# FA automation pattern: OpenAI Agents + browser tools + structured output

Use this skill when you need an **agent that searches the web and reads pages** with the **same stack** as `fa-automation/tasks/linkedin_research`: predictable tool calls, a terminal tool (`submit_result`) that returns JSON for a Pydantic model, and optional follow-up **non-agentic** structured LLM steps.

**Reference implementation (read these files in the CityFalcon repo):**

- `fa-automation/tasks/linkedin_research/agent.py` — agent factory, instructions, `Runner.run`, parsing path
- `fa-automation/tasks/linkedin_research/tools.py` — `@function_tool` definitions, browser wiring
- `fa-automation/tasks/linkedin_research/models.py` — Pydantic schemas for tools and final payloads
- `fa-automation/tasks/linkedin_research/config.py` — env-driven `Config` dataclass
- `fa-automation/tasks/linkedin_research/orchestrator.py` — lifecycle: init browsers → `set_browser` / `set_crawl_browser` → run agent per task

---

## Stack checklist

| Layer | Choice in linkedin_research |
|-------|-----------------------------|
| Agent runtime | `openai-agents` (`Agent`, `Runner`, `function_tool`) |
| Model backend | `LitellmModel` + `config.agent_model` (e.g. `gemini/...`) and `GEMINI_API_KEY` |
| Reasoning | `ModelSettings(reasoning=Reasoning(effort=...))` when using compatible models |
| Tracing | `set_tracing_disabled(disabled=True)` if you want local/offline quiet runs |
| Browser | Playwright via `BrowserManager` for Google search navigation |
| Extraction | `CrawlBrowserManager` (crawl4ai) preferred for `visit_webpage`; Playwright text fallback |
| Structured agent output | Tool `submit_result(result: YourPydanticModel)`; `tool_use_behavior=StopAtTools(stop_at_tool_names=["submit_result"])` |
| Parse agent JSON | `YourPydanticModel.model_validate_json(result.final_output)` |
| Secondary LLM (optional) | Plain `OpenAI` client pointed at Gemini OpenAI-compatible base URL + `chat.completions.parse` + `response_format=AnotherModel` |

**Dependencies (see `linkedin_research/requirements.txt`):** `openai`, `openai-agents[litellm]`, `pydantic`, `playwright`, `crawl4ai`, `python-dotenv`, plus any task-specific SDKs (e.g. Apify — not required for SEC workflows).

---

## Step 1 — Define Pydantic models (`models.py`)

- Put **everything the agent must return** in one model (e.g. `CompanyInfo`) or a small set of models.
- Use `Field(..., description=...)` generously — the model’s schema is exposed to the LLM via the `submit_result` tool.

---

## Step 2 — Implement tools (`tools.py`)

1. **Module-level placeholders** for resources the orchestrator injects:

   ```python
   _browser: Optional[BrowserManager] = None
   _crawl_browser: Optional[CrawlBrowserManager] = None

   def set_browser(browser): ...
   def set_crawl_browser(crawl_browser): ...
   ```

2. **Decorate each tool** with `@function_tool` from `agents`.

3. **Patterns:**
   - `search_google`: build Google URL, `_browser.navigate`, extract `a[href]` snippets + trimmed body text (cap length, e.g. 8k chars).
   - `visit_webpage`: try `_crawl_browser.fetch(url)` for markdown; on failure or if unset, Playwright body text + whitespace cleanup.
   - `wait_for_human`: optional; `input()` in executor for CAPTCHA/cookies.
   - `submit_result(result: YourModel) -> str`: return `result.model_dump_json()` so `final_output` is valid JSON for `model_validate_json`.

4. Keep tool docstrings **action-oriented** (when to call, args). The agent instructions should mirror them.

---

## Step 3 — Create the agent (`agent.py`)

1. **Instructions** (system-style): role, tool list with **numbered names**, strategy (order of search vs visit), edge cases, and **must call `submit_result` exactly once**.

2. **Factory:**

   ```python
   agent = Agent(
       name="...",
       instructions=INSTRUCTIONS,
       model=LitellmModel(model=config.agent_model, api_key=config.gemini_api_key),
       model_settings=ModelSettings(reasoning=Reasoning(effort=config.reasoning_effort)),
       tools=[search_google, visit_webpage, wait_for_human, submit_result],
       tool_use_behavior=StopAtTools(stop_at_tool_names=["submit_result"]),
   )
   ```

3. **Runner:**

   ```python
   result = await Runner.run(
       starting_agent=agent,
       input=user_message,  # include dynamic context (ticker, CIK, filing URL, etc.)
       max_turns=config.agent_max_turns,
   )
   parsed = YourModel.model_validate_json(result.final_output)
   ```

4. **Non-agentic step (optional):** For batch scoring or merging external structured data (CSV, API payloads), use a **single** `chat.completions.parse` with a large `CompanyResearchResult`-style model instead of more tool turns — cheaper and more deterministic.

---

## Step 4 — Orchestrator wiring (`orchestrator.py`)

1. Load env (`config`); construct `BrowserManager` and optionally `CrawlBrowserManager`.
2. Before any agent run: `set_browser(...)`, `set_crawl_browser(...)`.
3. Build the **user message** from the trigger payload (webhook body, queue message, or CLI args).
4. `asyncio.run` or your framework’s async entrypoint calling `run_company_research`-equivalent.
5. Persist outputs (JSON, DB, downstream webhook).

---

## Adapting for SEC / filing workflows

- Replace “company name + people list” in the prompt with **filing context**: CIK, form type, accession number, primary document URL, filing/acceptance timestamps.
- Tools stay the same: agent can **search** for news/context and **visit** `investor.sec.gov` Archives URLs or company IR pages if you pass URLs in the prompt.
- Prefer giving the agent **direct SEC viewer or `.htm` URLs** when you already resolved them in your poller to save turns.
- Optional: add a **non-tool** prefetch step that calls `data.sec.gov` Submissions/Company Facts and **injects JSON snippets** into the user message so the agent focuses on synthesis and external context rather than duplicating XBRL parsing.

---

## Anti-patterns

- Do not omit `StopAtTools` for `submit_result` — without it, the agent may talk instead of returning structured data.
- Do not skip `set_browser` / `set_crawl_browser` before running — tools will return `ERROR: Browser not initialized`.
- Do not rely on `final_output` as prose if you use `submit_result`; validate JSON and handle parse errors with a fallback model or safe defaults (see `agent.py` `_fallback_result` pattern).

---

## When not to use this skill

- Single-shot classification with no browsing — use a direct completion or `responses.parse` without Agents.
- Hosted Foundry/Cursor MCP-only agents — different deployment model (see Microsoft Foundry skill separately).
