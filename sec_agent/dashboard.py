"""Generate a beautiful HTML dashboard from FilingAnalysisResult JSON."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

from sec_agent.config import OUTPUT_DIR

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ TITLE }}</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a;
    --text: #e4e6eb; --muted: #8b8d97; --accent: #6366f1;
    --green: #22c55e; --red: #ef4444; --yellow: #eab308; --blue: #3b82f6;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); }
  .container { max-width: 1280px; margin: 0 auto; padding: 24px; }

  /* Header */
  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
  .header h1 { font-size: 28px; font-weight: 700; }
  .header .ticker { color: var(--accent); }
  .header .summary { color: var(--muted); font-size: 14px; margin-top: 4px; max-width: 700px; }
  .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; text-transform: uppercase; }
  .badge-bullish { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge-bearish { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge-neutral { background: rgba(139,141,151,0.15); color: var(--muted); }
  .badge-mixed { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .badge-high { background: rgba(99,102,241,0.15); color: var(--accent); }
  .badge-medium { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .badge-low { background: rgba(139,141,151,0.15); color: var(--muted); }
  .badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

  /* Scores row */
  .scores-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 24px; }
  @media (max-width: 900px) { .scores-row { grid-template-columns: repeat(3, 1fr); } }
  .score-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; text-align: center; }
  .score-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
  .score-ring { width: 72px; height: 72px; margin: 0 auto 8px; position: relative; }
  .score-ring svg { transform: rotate(-90deg); }
  .score-ring .bg { fill: none; stroke: var(--border); stroke-width: 6; }
  .score-ring .fg { fill: none; stroke-width: 6; stroke-linecap: round; transition: stroke-dashoffset 0.8s ease; }
  .score-ring .val { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 20px; font-weight: 700; }

  /* Metrics */
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .metric-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
  .metric-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .metric-card .value { font-size: 22px; font-weight: 700; margin: 4px 0; }
  .metric-card .change { font-size: 13px; font-weight: 600; }
  .metric-card .change.pos { color: var(--green); }
  .metric-card .change.neg { color: var(--red); }
  .metric-card .prior { font-size: 11px; color: var(--muted); }
  .metric-bar { height: 4px; border-radius: 2px; background: var(--border); margin-top: 8px; overflow: hidden; }
  .metric-bar .fill { height: 100%; border-radius: 2px; transition: width 0.6s ease; }

  /* Panels */
  .panel { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .panel h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .panel h2 .icon { font-size: 18px; }
  .panel p { font-size: 14px; line-height: 1.7; color: var(--text); white-space: pre-wrap; }

  /* Scored items */
  .items-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .items-table th { text-align: left; padding: 8px 12px; color: var(--muted); font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--border); }
  .items-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  .items-table tr:last-child td { border-bottom: none; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .pill-critical { background: rgba(239,68,68,0.15); color: var(--red); }
  .pill-important { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .pill-minor { background: rgba(139,141,151,0.15); color: var(--muted); }
  .pill-positive { background: rgba(34,197,94,0.15); color: var(--green); }
  .pill-negative { background: rgba(239,68,68,0.15); color: var(--red); }
  .pill-neutral { background: rgba(139,141,151,0.15); color: var(--muted); }
  .pill-mixed { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .pill-surprise_positive { background: rgba(34,197,94,0.15); color: var(--green); }
  .pill-surprise_negative { background: rgba(239,68,68,0.15); color: var(--red); }
  .pill-expected { background: rgba(139,141,151,0.15); color: var(--muted); }
  .pill-unclear { background: rgba(99,102,241,0.15); color: var(--accent); }

  /* Action flags */
  .flags { display: flex; flex-direction: column; gap: 8px; }
  .flag { background: rgba(99,102,241,0.08); border-left: 3px solid var(--accent); padding: 10px 14px; border-radius: 0 8px 8px 0; font-size: 13px; }

  /* Citations */
  .citations a { color: var(--accent); text-decoration: none; font-size: 13px; }
  .citations a:hover { text-decoration: underline; }

  /* Price bar */
  .price-bar { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 24px; font-size: 14px; line-height: 1.6; }

  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 800px) { .two-col { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <h1><span class="ticker">{{ TICKER }}</span> {{ ENTITY }}</h1>
      <div class="summary">{{ ONE_LINE }}</div>
      <div style="margin-top:8px; font-size:12px; color:var(--muted);">{{ FILING_FOCUS }}</div>
    </div>
    <div class="badges">
      <span class="badge badge-{{ SENTIMENT_CLASS }}">{{ SENTIMENT }}</span>
      <span class="badge badge-{{ IMPORTANCE_CLASS }}">Importance: {{ IMPORTANCE }}</span>
    </div>
  </div>

  <!-- Price -->
  {{ PRICE_HTML }}

  <!-- Score rings -->
  <div class="scores-row">{{ SCORE_CARDS }}</div>

  <!-- Key metrics -->
  <div class="metrics-grid">{{ METRIC_CARDS }}</div>

  <!-- Text panels -->
  <div class="two-col">
    <div class="panel"><h2><span class="icon">&#128202;</span> Fundamentals</h2><p>{{ FUNDAMENTALS }}</p></div>
    <div class="panel"><h2><span class="icon">&#128221;</span> Management &amp; Operations</h2><p>{{ MANAGEMENT }}</p></div>
  </div>
  <div class="two-col">
    <div class="panel"><h2><span class="icon">&#9888;&#65039;</span> Risks / Liquidity / Capital</h2><p>{{ RISKS }}</p></div>
    <div class="panel"><h2><span class="icon">&#128240;</span> Market &amp; News</h2><p>{{ MARKET }}</p></div>
  </div>
  <div class="panel"><h2><span class="icon">&#128161;</span> Value Investor Takeaway</h2><p>{{ TAKEAWAY }}</p></div>

  <!-- Scored items -->
  <div class="panel">
    <h2><span class="icon">&#127919;</span> Scored Findings</h2>
    <table class="items-table">
      <thead><tr><th>Finding</th><th>Category</th><th>Importance</th><th>Sentiment</th><th>Surprise</th></tr></thead>
      <tbody>{{ SCORED_ROWS }}</tbody>
    </table>
  </div>

  <!-- Action flags -->
  {{ FLAGS_HTML }}

  <!-- Citations -->
  <div class="panel citations">
    <h2><span class="icon">&#128279;</span> Citations</h2>
    {{ CITATIONS_HTML }}
  </div>

  <!-- Caveats -->
  {{ CAVEATS_HTML }}

</div>

<script>
document.querySelectorAll('.score-ring').forEach(el => {
  const val = parseInt(el.dataset.val || '0');
  const circ = 2 * Math.PI * 30;
  const fg = el.querySelector('.fg');
  fg.style.strokeDasharray = circ;
  fg.style.strokeDashoffset = circ - (circ * val / 100);
  let color = '#6366f1';
  if (val >= 75) color = '#22c55e';
  else if (val >= 50) color = '#eab308';
  else if (val >= 25) color = '#f97316';
  else color = '#ef4444';
  fg.style.stroke = color;
});
</script>
</body>
</html>
"""


def _score_card(label: str, value: int) -> str:
    return f"""<div class="score-card">
  <div class="label">{label}</div>
  <div class="score-ring" data-val="{value}">
    <svg viewBox="0 0 72 72"><circle class="bg" cx="36" cy="36" r="30"/><circle class="fg" cx="36" cy="36" r="30"/></svg>
    <div class="val">{value}</div>
  </div>
</div>"""


def _metric_card(m: dict) -> str:
    cur = m.get("current_value", 0)
    pri = m.get("prior_value", 0)
    yoy = m.get("yoy_change_percent", 0)
    sign = "+" if yoy >= 0 else ""
    cls = "pos" if yoy >= 0 else "neg"
    # Format large numbers
    if abs(cur) >= 1e9:
        cur_str = f"${cur / 1e9:,.1f}B"
        pri_str = f"${pri / 1e9:,.1f}B"
    elif abs(cur) >= 1e6:
        cur_str = f"${cur / 1e6:,.1f}M"
        pri_str = f"${pri / 1e6:,.1f}M"
    elif abs(cur) < 100:
        cur_str = f"${cur:,.2f}"
        pri_str = f"${pri:,.2f}"
    else:
        cur_str = f"${cur:,.0f}"
        pri_str = f"${pri:,.0f}"

    bar_pct = min(100, max(5, abs(yoy) * 2 + 40))
    bar_color = "var(--green)" if yoy >= 0 else "var(--red)"

    return f"""<div class="metric-card">
  <div class="label">{m.get('label','')}</div>
  <div class="value">{cur_str}</div>
  <div class="change {cls}">{sign}{yoy:.1f}% YoY</div>
  <div class="prior">{m.get('period_prior','')}: {pri_str}</div>
  <div class="metric-bar"><div class="fill" style="width:{bar_pct}%;background:{bar_color}"></div></div>
</div>"""


def _scored_row(si: dict) -> str:
    return f"""<tr>
  <td>{si.get('item','')}<br><span style="color:var(--muted);font-size:11px">{si.get('explanation','')}</span></td>
  <td><span class="pill">{si.get('category','')}</span></td>
  <td><span class="pill pill-{si.get('importance','')}">{si.get('importance','')}</span></td>
  <td><span class="pill pill-{si.get('sentiment','')}">{si.get('sentiment','')}</span></td>
  <td><span class="pill pill-{si.get('surprise','')}">{si.get('surprise','').replace('_',' ')}</span></td>
</tr>"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_html(data: dict) -> str:
    html = TEMPLATE

    ticker = data.get("tickers", "")
    html = html.replace("{{ TITLE }}", f"{ticker} Filing Analysis")
    html = html.replace("{{ TICKER }}", _esc(ticker))
    html = html.replace("{{ ENTITY }}", _esc(data.get("entity_name", "")))
    html = html.replace("{{ ONE_LINE }}", _esc(data.get("one_line_summary", "")))
    html = html.replace("{{ FILING_FOCUS }}", _esc(data.get("filing_focus", "")))

    sent = data.get("overall_sentiment", "neutral")
    html = html.replace("{{ SENTIMENT }}", sent.upper())
    html = html.replace("{{ SENTIMENT_CLASS }}", sent)
    imp = data.get("overall_importance", "medium")
    html = html.replace("{{ IMPORTANCE }}", imp.upper())
    html = html.replace("{{ IMPORTANCE_CLASS }}", imp)

    price = data.get("stock_price_snapshot", "")
    if price:
        html = html.replace("{{ PRICE_HTML }}",
            f'<div class="price-bar">{_esc(price)}</div>')
    else:
        html = html.replace("{{ PRICE_HTML }}", "")

    scores = [
        ("Revenue Growth", data.get("score_revenue_growth", 0)),
        ("Profitability", data.get("score_profitability", 0)),
        ("Balance Sheet", data.get("score_balance_sheet", 0)),
        ("Management", data.get("score_management_quality", 0)),
        ("Market Sentiment", data.get("score_market_sentiment", 0)),
        ("Risk (inv.)", data.get("score_risk_level", 0)),
    ]
    html = html.replace("{{ SCORE_CARDS }}", "\n".join(_score_card(l, v) for l, v in scores))

    metrics = data.get("key_metrics", [])
    html = html.replace("{{ METRIC_CARDS }}", "\n".join(_metric_card(m) for m in metrics))

    html = html.replace("{{ FUNDAMENTALS }}", _esc(data.get("fundamentals_from_sec", "")))
    html = html.replace("{{ MANAGEMENT }}", _esc(data.get("management_and_operations", "")))
    html = html.replace("{{ RISKS }}", _esc(data.get("risks_liquidity_capital", "")))
    html = html.replace("{{ MARKET }}", _esc(data.get("market_and_news", "")))
    html = html.replace("{{ TAKEAWAY }}", _esc(data.get("value_investor_takeaway", "")))

    items = data.get("scored_items", [])
    html = html.replace("{{ SCORED_ROWS }}", "\n".join(_scored_row(si) for si in items))

    flags = data.get("action_flags", [])
    if flags:
        flags_inner = "\n".join(f'<div class="flag">{_esc(f)}</div>' for f in flags)
        html = html.replace("{{ FLAGS_HTML }}",
            f'<div class="panel"><h2><span class="icon">&#9873;</span> Action Flags</h2><div class="flags">{flags_inner}</div></div>')
    else:
        html = html.replace("{{ FLAGS_HTML }}", "")

    cites = data.get("citations", "")
    cite_lines = [c.strip() for c in cites.split("\n") if c.strip()]
    cite_html = "<br>".join(f'<a href="{c}" target="_blank">{c}</a>' for c in cite_lines)
    html = html.replace("{{ CITATIONS_HTML }}", cite_html)

    caveats = data.get("caveats", "")
    if caveats and caveats.strip().lower() not in ("none", "none.", "n/a"):
        html = html.replace("{{ CAVEATS_HTML }}",
            f'<div class="panel"><h2><span class="icon">&#9881;</span> Caveats</h2><p>{_esc(caveats)}</p></div>')
    else:
        html = html.replace("{{ CAVEATS_HTML }}", "")

    return html


def main():
    """CLI: python -m sec_agent.dashboard [path_to_json]"""
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    else:
        src = OUTPUT_DIR / "demo_AAPL.json"
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))
    html = generate_html(data)

    out = src.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard: {out}")
    webbrowser.open(str(out))


if __name__ == "__main__":
    main()
