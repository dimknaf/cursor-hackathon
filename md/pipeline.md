# Hackathon pipeline: SEC filings × webhooks × FA agent stack

**Track:** Always-on agents — live triggers + actions (see `rules.md`).  
**Theme:** Something useful fires when the outside world changes (e.g. a new **10-K / 10-Q / 8-K** shows up), and an agent runs with real tools — not a one-off manual demo.

---

## 1. Objectives

- Trigger automation from **external events** (webhook and/or schedule), not only from a local CLI.
- Use **SEC filing activity** as the domain signal (filings, form types, accession metadata, optional links to statements).
- Reuse the **linkedin_research-style stack**: OpenAI Agents SDK + LiteLLM/Gemini + Playwright + crawl4ai + Pydantic `submit_result` (see `md/skill-fa-agent-stack/SKILL.md`).
- Learn **EDGAR data access patterns** already documented in `cityfalcon/testing-sec-api` (Submissions API, optional Company Facts).

---

## 2. Constraints and facts

- **Official** `data.sec.gov` APIs are **pull-based** (REST). There is **no** SEC-native “webhook when AAPL files a 10-Q.” Your **ingestion** step is polling, bulk diff, or a third-party stream; your **product** can still expose a **webhook to downstream systems** (“we analyzed filing X”).

- Compliance: **User-Agent** with contact email, **≤10 requests/second** to SEC hosts.

---

## 3. Proposed architecture (high level)

| Stage | Role |
|--------|------|
| **A. Watch** | Scheduled job or lightweight poller: compare last known `accessionNumber` / `acceptanceDateTime`from Submissions API vs stored watermark; optionally filter `form` ∈ {`10-K`, `10-Q`, `8-K`, …}. |
| **B. Normalize** | Resolve CIK, persist accession, primary document, filing URL; optionally prefetch a small JSON slice (metadata only) for the agent prompt. |
| **C. Emit** | POST to your **ingestion webhook** (or enqueue message) with a stable JSON payload. |
| **D. Agent** | FA stack agent: `search_google` / `visit_webpage` + domain instructions; `submit_result` → Pydantic summary (thesis, risks, “what changed”, links). |
| **E. Deliver** | Second webhook or integration: Slack, email, Notion, GitHub issue — “always-on” value after demo. |

---

## 4. Milestones (execution order)

1. [ ] **Spike:** Read one CIK’s `submissions` JSON; print latest `10-Q` accession and `acceptanceDateTime` (reuse patterns from `testing-sec-api` / `sec_client.py`).
2. [ ] **Watermark store:** File, SQLite, or Redis key `last_seen_accession` per CIK (or global queue).
3. [ ] **Poller service:** FastAPI/Flask + APScheduler or external cron → runs watch loop for 1–3 demo tickers.
4. [ ] **Trigger contract:** Define JSON body for “new filing” events (CIK, ticker, form, accession, urls, accepted_at).
5. [ ] **Agent task:** New task folder mirroring `linkedin_research`: `tools.py`, `models.py`, `agent.py`, `config.py`, orchestrator entry that accepts webhook payload.
6. [ ] **Outbound webhook:** Configurable URL + secret; POST structured agent output.
7. [ ] **Demo path:** Show one **scheduled** detection → **internal webhook** → agent run → **outbound** notification.

---

## 5. SEC context reference (internal)

- Deep API reference: `cityfalcon/testing-sec-api/docs/sec-api-guide.md`
- Client helper: `cityfalcon/testing-sec-api/dashboard/backend/api/sec_client.py`
- Use cases: `testing-sec-api/docs/use-case-*.md` (earnings calendar, corporate events, etc.)

---

## 6. Risks / mitigations

| Risk | Mitigation |
|------|------------|
| Rate limits / blocks | Single CIK poll per tick; backoff; cache submissions per run. |
| Large 10-K HTML | Pass excerpt or TOC URLs; cap crawl length; optional offline extract outside agent. |
| Duplicate fires | Idempotency key = accession number. |
| Agent drift | Strong `submit_result` schema; fallback parse path like `linkedin_research`. |

---

## 7. Final solution (fill in after build)

<!-- Document what you actually shipped: repo links, env vars, how to run poller + agent, demo script, and a 2-minute judge narrative. -->

**Summary:**

*(empty — complete post-hackathon)*

**How to run:**

*(empty)*

**Demo checklist:**

*(empty)*

---

## 8. Optional stretch

- Watch **8-K** items (`2.02` earnings-related, `5.02` leadership) via `items` field in submissions columnar data.
- Compare **two consecutive** 10-Q accession metadata and let the agent focus on “what changed” with prefetched diffs.
- Evaluate **third-party** filing streams only if hackathon rules and time allow; prefer free EDGAR polling for the main story.
