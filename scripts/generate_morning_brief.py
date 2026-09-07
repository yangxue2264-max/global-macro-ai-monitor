"""Generate the 08:45 snapshot and optionally email every verified subscriber."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.briefing import morning_rule_brief
from core.emailing import send_email
from core.evidence import add_evidence_scores
from core.market_context import enrich_macro_with_market_proxies
from core.reporting import build_personal_analysis, render_morning_email
from core.providers import (
    fetch_fred_snapshot, fetch_market_snapshot, fetch_news_bundle,
    fetch_treasury_snapshot, flatten_watchlist, load_watchlist,
)
from core.subscriptions import get_secret, list_active_subscriptions
from core.trading_calendar import is_a_share_trading_day

CN = ZoneInfo("Asia/Shanghai")


def _extra_market_items(subscriptions: list[dict], universe: dict) -> dict:
    known_tickers = {meta.get("ticker") for meta in universe.values()}
    extras = {}
    for subscription in subscriptions:
        for index, row in enumerate(subscription.get("watchlist", [])):
            ticker = row.get("ticker", "")
            if ticker and ticker not in known_tickers:
                extras[f"SUB_{len(extras)}_{index}"] = {
                    "name": row.get("name") or ticker,
                    "ticker": ticker,
                    "theme": row.get("theme", ""),
                    "region": "CN",
                    "group": "subscriber_watchlist",
                }
                known_tickers.add(ticker)
    return extras


def main(send_emails: bool = False, force: bool = False):
    now = datetime.now(CN)
    if not force and not is_a_share_trading_day(now.date()):
        print(f"skip {now.date()}: not an A-share trading day")
        return
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    universe = flatten_watchlist(cfg)
    mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    subscriptions = list_active_subscriptions()
    universe.update(_extra_market_items(subscriptions, universe))
    market = fetch_market_snapshot(universe)
    macro = enrich_macro_with_market_proxies(fetch_fred_snapshot(), market, fetch_treasury_snapshot())
    news = add_evidence_scores(fetch_news_bundle(max_each=10))
    brief = morning_rule_brief(market, macro, news)
    payload = {
        "generated_at": now.isoformat(),
        "brief": brief,
        "market": market,
        "macro": macro,
        "news": news[:30],
        "stage": "08:45",
        "subscriber_count": len(subscriptions),
    }
    outdir = BASE / "data" / "brief_history"
    outdir.mkdir(parents=True, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True)
    (outdir / f"{day}.json").write_text(rendered, encoding="utf-8")
    (BASE / "data" / "latest_morning_brief.json").write_text(rendered, encoding="utf-8")
    print(f"generated {day}: {len(news)} events, {len(market)} market series, {len(subscriptions)} subscribers")

    if send_emails:
        failures = 0
        app_url = get_secret("APP_URL")
        for subscription in subscriptions:
            try:
                alerts, signals = build_personal_analysis(
                    subscription["watchlist"], news, market, mapping
                )
                subject, html, text = render_morning_email(alerts, signals, now.isoformat(), app_url)
                send_email(subscription["email"], subject, html, text)
            except Exception as exc:
                failures += 1
                print(f"subscriber delivery failed: {type(exc).__name__}: {exc}")
        print(f"08:45 email delivery complete: {len(subscriptions) - failures}/{len(subscriptions)}")
        if failures:
            raise SystemExit(f"{failures} subscriber emails failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-emails", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(send_emails=args.send_emails, force=args.force)
