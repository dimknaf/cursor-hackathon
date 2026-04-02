"""Simulate a filing event by POSTing to the webhook server.

This lets you test the full pipeline end-to-end without waiting for a real
SEC filing to appear. It sends a webhook payload as if the poller had just
detected a new 10-Q from a known company.

Usage:
    python -m sec_agent.simulate_filing                  # Apple 10-Q
    python -m sec_agent.simulate_filing --ticker MSFT    # Microsoft
    python -m sec_agent.simulate_filing --ticker TSLA --form 10-K
    python -m sec_agent.simulate_filing --url http://localhost:9000/webhook/filing
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

from sec_agent.demo import DEMO_CIKS


def main():
    p = argparse.ArgumentParser(description="Simulate a filing event → POST to webhook")
    p.add_argument("--ticker", default="AAPL", help="Ticker to simulate (default: AAPL)")
    p.add_argument("--form", default="10-Q", help="Form type (default: 10-Q)")
    p.add_argument("--url", default="http://127.0.0.1:8000/webhook/filing", help="Webhook URL")
    args = p.parse_args()

    ticker = args.ticker.upper()
    cik = DEMO_CIKS.get(ticker)
    if not cik:
        print(f"Unknown ticker '{ticker}'. Known: {', '.join(sorted(DEMO_CIKS))}")
        sys.exit(1)

    payload = {
        "cik": cik,
        "ticker": ticker,
        "entity_name": f"{ticker} Inc.",
        "form_type": args.form,
        "accession_number": "0000000000-00-000000",
        "filing_date": "2025-01-01",
        "filing_url": "",
    }

    print(f"Sending simulated {args.form} event for {ticker} (CIK={cik})")
    print(f"  → POST {args.url}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")

    try:
        r = requests.post(args.url, json=payload, timeout=10)
        print(f"\nResponse [{r.status_code}]: {r.text}")
        if r.status_code == 202:
            print("\nAgent is now running in the background!")
            print("Check progress: GET http://127.0.0.1:8000/jobs")
            print("Or open:        http://127.0.0.1:8000/")
    except requests.ConnectionError:
        print(f"\nCould not connect to {args.url}")
        print("Is the webhook server running?  Start it with:")
        print("  python -m sec_agent.webhook_server")
        sys.exit(1)


if __name__ == "__main__":
    main()
