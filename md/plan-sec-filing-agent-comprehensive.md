# Comprehensive plan: SEC filing → fundamentals → MD&A → market narrative (value lens)

**Purpose:** Single reference for implementation and team discussion — what we parse deterministically, what the agent does with tools, how we run **twice** post-release (≈10 minutes and ≈1 hour), and how outputs stay **structured** and grounded in **real filings + SEC data**, not generic AI prose.

**Hackathon fit:** Always-on trigger (new 10-Q / 10-K on EDGAR) → webhook → pipeline → structured deliverables suitable for judges and for “still useful after demo.”

---

## 1. Product story (one paragraph)

When a watched issuer files a **10-Q** or **10-K**, we (1) **anchor** on SEC-sourced fundamentals and filing text where it matters, (2) **extract** MD&A / risk / liquidity themes from the actual document, (3) **observe** how news and price context evolve with **time-stamped** Google search passes at **T+10m** and **T+1h**, and (4) emit a **fixed schema** brief written in a **value-investor** voice: what changed for the **business economics**, **balance sheet quality**, and **management’s own framing**, with explicit **citations** and **uncertainty** flags.

---

## 2. Scope and non-goals

### In scope (v1)

- Triggers on **filed** 10-Q / 10-K (new `accessionNumber`), not pre-filing prediction (optional stretch).
- **US GAAP** issuers with usable **XBRL** on `data.sec.gov` (handle partial gaps).
- **One** primary filing document path per event (`primaryDocument` from Submissions, typically inline XBRL HTML).
- **English** narrative output; **dual horizon** snapshots: **T+10m** and **T+1h** after our `acceptanceDateTime` (or `filingDate` if we standardize).

### Out of scope (unless time allows)

- Full sell-side model replication, DCF automation, intraday tick data.
- Parsing every exhibit; **Form 4 / 13F**; international **IFRS** edge cases without extra taxonomy handling.
- Guaranteed “market consensus” (we report **what we found in search**, not ground truth).

---

## 3. End-to-end architecture

```
[Poller] → new 10-Q/10-K?
    → persist FilingEvent { accession, cik, form, acceptance_at, primary_document, urls... }
    → POST /hooks/sec-filing  (or internal enqueue)

[Worker / same app]
    Phase 0: Prefetch (deterministic, no LLM)
    Phase 1: Document extraction (deterministic + optional LLM-on-chunks later)
    Phase 2: Agent run A — "T+10m narrative"  (scheduled delay ~10m after acceptance, OR immediately tagged as horizon=10m with search queries that request very recent results)
    Phase 3: Agent run B — "T+1h narrative"  (~60m after acceptance)
    Phase 4: Merge / store StructuredBrief_v1 + audit trail
```

**Discussion point:** Do we literally **sleep** 10m/1h in one long job, or enqueue **two delayed jobs**? Prefer **two jobs** with `run_at` for resilience and simpler timeouts.

---

## 4. Data sources: what we trust for what

| Need | Source | Reliability | Notes |
|------|--------|-------------|--------|
| “Filing happened” | `data.sec.gov/submissions/CIK....json` | High | Columnar `filings.recent`; watermark on `accessionNumber`. |
| Core financial series | Company Facts / Company Concept | High for GAAP tags | Tie facts to `accn` matching this filing when possible. |
| MD&A, Risks, Liquidity | Filing HTML (inline XBRL) | High if extraction is right | Structure is messy; need section detection. |
| “Market / news tone” | `search_google` + optional `visit_webpage` | Medium | Time-sensitive; must log query string + timestamp. |
| Price / volume | Optional free API or “include in search snippets only” | Low–medium for v1 | Discuss: skip price or add one API key. |

---

## 5. Phase 0 — Deterministic prefetch (fundamentals “as SEC says”)

### 5.1 Filing metadata

From Submissions row aligned with accession:

- `form`, `filingDate`, `reportDate`, `acceptanceDateTime`, `primaryDocument`, `isXBRL`, `isInlineXBRL`.

Build:

- **Archives HTML URL** (standard EDGAR URL pattern from CIK without leading zeros for path + accession dashed + primary document — follow existing `sec_client` / team helper).

### 5.2 Fundamentals snapshot (structured)

**Primary approach:** fetch **Company Facts** once per CIK (cached), or **Company Concept** for a **small allowlist** of tags (lighter).

**Allowlist (starter — tune in discussion):**

- Income / health: `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss`, `EarningsPerShareDiluted`, `EarningsPerShareBasic`
- Balance sheet: `Assets`, `Liabilities`, `StockholdersEquity`, `AssetsCurrent`, `LiabilitiesCurrent`, `CashAndCashEquivalentsAtCarryingValue` (or company-specific cash tag — **must** handle alternates)
- Cash flow: `NetCashProvidedByUsedInOperatingActivities`
- Shares & capital: `CommonStockSharesOutstanding` (if available), `Debt*` concepts if material (discuss allowlist)

**Rules:**

- Prefer facts whose `accn` equals **this filing** for quarter/annual period; if multiple rows, **latest `filed`** for that `end` / `fp`.
- Track **instant vs duration** (per SEC guide); don’t mix balance-sheet snapshots with flow metrics.
- Emit **`FundamentalsTable`** JSON: list of `{ tag, label, value, unit, start?, end?, fy, fp, form, accn, filed }` + **`data_gaps[]`** for missing tags.

**Discussion point:** Do we show **YoY and QoQ** in prefetch? Recommended: compute **one** period comparison in code (prior period match by `end` / `fp`) so the agent doesn’t do arithmetic wrong.

### 5.3 Management discussion & narrative sections (structured extraction)

**Goal:** Pass the agent **real MD&A text** (and adjacent sections), not the whole 200-page file.

**Approach tiers (pick v1):**

1. **Heuristic HTML sectioning (recommended for hackathon)**  
   - Fetch filing HTML (rate-limit, UA).  
   - Strip scripts/styles; locate anchors / TOC patterns for **Item 2** (10-Q MD&A) vs **Item 7** (10-K MD&A), **Item 1A** Risks (10-K), **Item 3** legal (10-Q), etc. (Form-specific map.)  
   - Extract **plain text** per section with **char cap** (e.g. 12–25k per section) + **offsets** (optional) for provenance.

2. **Fallback:** If headings not found, use **first N + last N blocks** strategy + keyword windows around “Liquidity”, “Results of Operations”, “Covenant”, “Risk” — lower precision.

3. **Optional stretch:** Table extraction for **segment revenue** tables via html2text + simple regex / pandas — only if stable.

**Output:** `FilingExcerpts` object:

```json
{
  "accession": "...",
  "form": "10-Q",
  "sections": {
    "md_and_a": { "text": "...", "source": "inline_primary_html", "chars": 18342 },
    "risk_factors": { "text": "..." , "optional": true },
    "liquidity_and_capital_resources": { "text": "...", "optional": true }
  },
  "extraction_warnings": []
}
```

**Discussion point:** Legal sensitivity — we’re using **public filings**; still avoid redistributing full documents externally if product policy requires; for hackathon demo, excerpts + links are enough.

---

## 6. Tools strategy: reuse vs new

### 6.1 Keep from LinkedIn research pattern

- **`search_google(query)`** — for **recency-biased** queries; log every call with ISO time.
- **`visit_webpage(url)`** — follow 1–2 Tier-1 sources when snippets are thin.

### 6.2 New tools (proposal)

| Tool | Owner | Purpose |
|------|--------|---------|
| `get_sec_fundamentals_snapshot` | Deterministic (optional: **not** exposed to agent) | Returns JSON from Phase 0 so the agent does not re-scrape SEC. |
| `get_filing_excerpts` | Deterministic | Given accession (+ cached HTML path), return MD&A / Risk excerpts; **no LLM**. |
| `submit_result` | Agent | Pydantic `ValueBrief` / `HorizonSnapshot` (see §8). |

**Design choice for discussion:**

- **A)** Prefetch everything into the **user message** and give the agent **only** `search_google`, `visit_webpage`, `submit_result` — simplest, fewer moving parts.  
- **B)** Expose `get_filing_excerpts` as a tool so the agent can request **additional** sections if needed — flexible, more turns.  
- **Recommendation:** **A for v1**; **B** if excerpts exceed message budget and we need lazy loading by section.

### 6.3 “Read the file” without a new tool

If we choose **A**: the “file read” is **server-side extraction** into `FilingExcerpts`, injected into prompt.  
If we choose **B**: new tool wraps the same extractor.

---

## 7. Agent design (value investing lens, structured)

### 7.1 System instructions (themes)

- **Epistemic discipline:** Separate **facts in filing / fundamentals JSON** from **interpretation** and **market chatter**.  
- **Materiality:** Focus on **durability of earnings**, **capital intensity**, **balance sheet stress**, **liquidity & covenants**, **unit economics hints**, **guidance / forward statements** only as quoted/paraphrased from MD&A.  
- **No fake precision** on price targets; if search is noisy, say so.  
- **Citations:** Every non-obvious external claim should map to a URL from search/visit; filing claims should reference section labels we provide.  
- **Horizon-specific behavior:**
  - **T+10m:** Emphasize **headline reaction**, wire copy, “first take” summaries; note **incomplete** context.  
  - **T+1h:** Emphasize **follow-on analysis**, deeper articles, duplicates; deduplicate stories.

### 7.2 Search query playbook (examples, parameterized)

- `{ticker} {company} 10-Q filing investor reaction`  
- `{ticker} earnings commentary {filing_date}`  
- `{ticker} shares after hours` (if relevant)  
- `{company} MD&A key points liquidity`  
- `site:sec.gov {company} {accession}` (optional; may be redundant)

**Log:** `queries[]` with timestamp for reproducibility.

### 7.3 Turn and cost limits

- Cap tool calls (e.g. **6–12** per run).  
- Prefer **2–3** `visit_webpage` max per run (high latency).

---

## 8. Structured outputs (schema to discuss)

Deliver one JSON object per **horizon**; store both under same `filing_event_id`.

### 8.1 `HorizonSnapshot` (per T+10m / T+1h)

Suggested fields (edit together):

| Field | Meaning |
|-------|--------|
| `horizon` | `"t_plus_10m"` \| `"t_plus_1h"` |
| `generated_at` | ISO when agent finished |
| `filing_anchor` | `{ accession, form, acceptanceDateTime, reportDate }` |
| `fundamentals_delta_summary` | Short bullets; **must** restate only from provided fundamentals table |
| `md_and_a_insights` | Bullets tied to **business reality**: demand, margins, costs, segments, one-offs |
| `balance_sheet_and_liquidity` | Working capital, leverage cues, covenant language if present in excerpt |
| `guidance_and_forward_look` | Only if present; else `null` + reason |
| `risk_and_disclosure_notes` | From risk excerpt / MD&A legal language |
| `market_and_news_reaction` | What search shows; cluster duplicate stories |
| `value_lens_takeaway` | 3–5 sentences: would a **long-term owner** care; what changed in **economic reality** |
| `citations` | `[{ kind: "filing_section" \| "web", ref, url?, note }]` |
| `confidence` | One of `high`, `medium`, `low`, plus reason |
| `unknowns` | Explicit gaps (missing tags, extraction failure, paywalled pages) |

### 8.2 Optional merge object

`FilingBrief` containing both horizons + `diff_10m_vs_1h` (what new info appeared).

---

## 9. Scheduling: “10 minutes” vs “1 hour”

### 9.1 Clock anchor

**Default:** `acceptanceDateTime` from Submissions (UTC). If missing in some edge case, fall back to `filingDate` 09:30 ET (discuss).

### 9.2 Job design

On new filing:

1. **Prefetch job (immediate):** fundamentals JSON + `FilingExcerpts` saved to DB/disk.  
2. **Run `Agent_T10` at** `acceptance + 10m` (queue delay).  
3. **Run `Agent_T60` at** `acceptance + 60m`.  
4. **Idempotency:** `(accession, horizon)` unique key.

### 9.3 What if filing is after hours?

Search results differ; instructions should still demand recency labeling (“as of {now} UTC”). Price reaction may be thin — `unknowns` should say so.

---

## 10. Reliability, verification, and judge alignment

- **Verification hooks:** Compare agent’s “fundamentals bullets” against `FundamentalsTable` in code (optional validator: numeric parity check).  
- **Fail gracefully:** If MD&A extraction fails, agent gets `md_and_a` = empty with warning; must not invent.  
- **Tracing:** Persist prompts, tool logs, and raw `submit_result` JSON for demo Q&A.

---

## 11. Implementation milestones (ordered)

1. Watermark poller + `FilingEvent` model + webhook enqueue.  
2. `SECClient` reuse: submissions + company facts with caching + rate limiter.  
3. Fundamentals allowlist + **QoQ/YoY helper** + `FundamentalsTable` JSON.  
4. Filing HTML fetch + **section extractor** for 10-Q and 10-K Item maps.  
5. Prompt pack + Pydantic `HorizonSnapshot` + `Runner.run` path.  
6. Dual delayed workers (10m / 1h).  
7. Minimal UI or Notion/Slack sink for judges.  
8. Optional: validator that rejects agent output if numbers disagree with table.

---

## 12. Open questions for us (discussion checklist)

- [ ] **Watchlist size** and CIK resolution (ticker → CIK file?).  
- [ ] **Price data:** include or explicitly omit for v1?  
- [ ] **Agent model** and cost ceiling per filing (two runs × tools).  
- [ ] **Message size:** full MD&A excerpt vs summarized chunking strategy.  
- [ ] **8-K coordination:** do we ever merge 2.02 press release text into context?  
- [ ] **Compliance:** SEC UA string; store filing HTML locally or stream only excerpts?  
- [ ] **Output destination:** Slack webhook vs DB + small dashboard.  
- [ ] **Definition of “value investing style”** — we use **Buffett/Munger-ish** principles in prompt or cite **Klarman**-style margin of safety language? (Pick one voice.)  
- [ ] **Language guardrails:** avoid investment advice disclaimers for demo jurisdiction?

---

## 13. Relationship to existing docs

- **Stack & tools:** `md/skill-fa-agent-stack/SKILL.md`  
- **High-level milestones:** `md/pipeline.md`  
- **Idea space:** `md/brainstorming.md`  

This document is the **detailed design**; after agreement, we should sync §11 into `pipeline.md` and fill §7 in `pipeline.md` post-build.

---

*Draft for collaborative editing — trim, argue, and tick §12 before coding.*
