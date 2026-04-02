# Brainstorming: SEC filings + webhooks + FA browser agent

**Goal:** Fit **Always-on agents** (rules main road):outside trigger → durable automation → clear demo. Learn SEC EDGAR + the same agent/tooling pattern as `fa-automation/tasks/linkedin_research`.

---

## A. What SEC gives you (and what it does not)

**Official EDGAR (`data.sec.gov`):**

- **Submissions** — filing history as columnar arrays: `form`, `filingDate`, `reportDate`, `acceptanceDateTime`, `accessionNumber`, `primaryDocument`, 8-K `items`, etc. **Best source for “something new appeared.”**
- **Company Facts / Concept / Frames** — XBRL numbers and trends; great **context** prefetched into the agent prompt, not necessarily for every tool turn.
- **Updates** — Near real-time during market hours; still **you** must poll or diff.

**There is no official “webhook on new filing.”** “Webhook” in your design = **your** HTTP endpoint that fires when **your poller** sees a new accession (or when a schedule runs and finds delta). Optionally, **third-party** filing streams exist (e.g. commercial APIs with WebSocket/streaming); treat as **optional** if allowed and worth the setup.

*Internal deep dive:* `cityfalcon/testing-sec-api` — `README.md`, `docs/sec-api-guide.md`, demo scripts under `scripts/`.

---

## B. Trigger ideas (outside world → your code)

| Idea | Signal | Pros | Cons |
|------|--------|-----|------|
| **CIK poller** | New `accessionNumber` vs watermark | Free, on-policy, precise | Must schedule; not push |
| **Multi-CIK watchlist** | Same, keyed by ticker | Demo-friendly | More requests; needs CIK map |
| **Form filter** | Only `10-K`, `10-Q`, `8-K` | Narrative is clear | Misses fascinating `DEF 14A`, `4`, `13F` |
| **8-K item filter** | `items` contains `2.02` | Earnings / material ops | Parsing string field carefully |
| **Nightly bulk ZIP** | Diff `submissions.zip` | Good for scale story | Not second-level latency |
| **Earnings-adjacent** | Combine fiscal calendar + 10-Q due window | “Predict + confirm” story | Harder to fit in hours |

**Recommendation for a fast win:** one **scheduled poller** (every 5–15 min) for **1–3 CIKs**, filter **`10-Q` / `10-K`**, emit **one webhook payload per new accession**.

---

## C. Context ideas (what to pass into the agent)

| Context | Source | Use |
|---------|--------|-----|
| Filing metadata | Submissions row | Form, dates, accession |
| Primary doc URL | Built from Archives URL pattern + `primaryDocument` | `visit_webpage` |
| Company name / SIC | Submissions header | Prompt grounding |
| Last N revenue points | Company Concept `Revenues` | “Vs expectations” narrative |
| Prior filing accession | Your DB | “What changed” homework |
| News | `search_google` tool | Post-filing market angle |

Keep **raw XBRL** mostly **outside** the agent; inject **short summaries or tables** in the user message to save tokens and turns.

---

## D. Agent behavior ideas (linkedin_research stack, new domain)

Same tools: `search_google`, `visit_webpage`, `wait_for_human`, `submit_result(YourModel)`.

**Possible `submit_result` schemas (pick one for v1):**

1. **FilingBrief** — `headline`, `three_bullets`, `risk_flags`, `citations: list[{url, note}]`, `suggested_followups`.
2. **InvestorMemo** — `summary`, `financial_highlights`, `management_tone`, `red_flags`, `confidence`.
3. **10-K / 10-Q diff** — `new_risks`, `removed_risks`, `md_and_a_themes` (only if you pass prior text or snippets).

**Instruction tweaks:**

- Mandate **citations** from SEC or company IR when stating facts.
- Cap tool calls (e.g. “complete in ≤8 turns”).
- If HTML is huge, ask agent to **prioritize** TOC sections (Risk Factors, MD&A).

---

## E. “Cool fast” demo narratives (pick one)

1. **“New 10-Q lands → Slack thread”** — Poller → webhook → agent → Slack incoming webhook with summary + link to SEC.
2. **“Watch your portfolio folder”** — YAML list of tickers; first filing of the week triggers digest.
3. **“8-K lightning”** — Only `8-K` with `2.02` or `5.02`; agent explains “what happened” in plain English.
4. **“Analyst assistant”** — On trigger, agent searches news + visits filing HTML for **one** section (e.g. liquidity).

---

## F. Learning outcomes (explicit)

- How **Submissions** columnar arrays work and why **accession** is your idempotency key.
- Why **User-Agent + rate limits** matter on EDGAR.
- How **OpenAI Agents + StopAtTools + Pydantic tool** yields reliable JSON for downstream webhooks.
- Difference between **agentic browse** (flexible) and **prefetch XBRL** (deterministic).

---

## G. Wild ideas (park if time)

- **Form 4** insider burst → agent correlates with 8-K.
- **13F** new holding → agent profiles the issuer (heavier).
- **Fed / macro** unrelated — scope creep unless tied to 10-K Risk Factors.

---

## H. Decisions to lock early

- [ ] Which **forms** in v1?
- [ ] **Watermark** storage: file vs DB?
- [ ] **Outbound** webhook target for judges?
- [ ] **One** Pydantic output schema for `submit_result`

---

*Cross-links: implementation skill → `md/skill-fa-agent-stack/SKILL.md`; execution plan → `md/pipeline.md`; hackathon constraints → `rules.md`.*
