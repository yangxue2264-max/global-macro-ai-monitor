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
from core.opportunity_model import attach_dynamic_guidance, discover_market_targets
from core.preopen import build_opportunity_signals
from core.reporting import build_personal_analysis, render_morning_email
from core.providers import (
    fetch_a_share_universe, fetch_fred_snapshot, fetch_market_snapshot, fetch_news_bundle,
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
    stock_universe, universe_coverage = fetch_a_share_universe(get_secret("TUSHARE_TOKEN"))
    marketwide_signals = discover_market_targets(
        build_opportunity_signals(news, market, mapping, []), stock_universe
    )
    known_tickers = {item.get("ticker") for item in market.values()}
    stock_lookup = {row.get("ticker"): row for row in stock_universe}
    candidate_market = {}
    for signal in marketwide_signals:
        for target in signal.get("targets", []):
            ticker = target.get("ticker")
            if ticker and ticker not in known_tickers and ticker not in candidate_market:
                stock = stock_lookup.get(ticker, target)
                candidate_market[f"DISCOVERY_{len(candidate_market)}"] = {
                    "name": stock.get("name") or ticker, "ticker": ticker,
                    "theme": signal.get("theme", ""), "region": "CN", "group": "full_market_discovery",
                }
    if candidate_market:
        market.update(fetch_market_snapshot(candidate_market))
    marketwide_signals = attach_dynamic_guidance(marketwide_signals, market)
    brief = morning_rule_brief(market, macro, news)
    payload = {
        "generated_at": now.isoformat(),
        "brief": brief,
        "market": market,
        "macro": macro,
        "news": news[:30],
        "signals": marketwide_signals,
        "universe_coverage": universe_coverage,
        "stage": "08:45",
        "subscriber_count": len(subscriptions),
    }
    outdir = BASE / "data" / "brief_history"
    outdir.mkdir(parents=True, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True)
    compact_history = {
        **payload,
        "market": {
            key: {field: value for field, value in item.items() if field != "history"}
            for key, item in market.items()
        },
    }
    (outdir / f"{day}.json").write_text(
        json.dumps(compact_history, ensure_ascii=False, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    (BASE / "data" / "latest_morning_brief.json").write_text(rendered, encoding="utf-8")
    print(f"generated {day}: {len(news)} events, {len(market)} market series, {len(subscriptions)} subscribers")

    if send_emails:
        failures = 0
        app_url = get_secret("APP_URL")
        for subscription in subscriptions:
            try:
                alerts, signals = build_personal_analysis(
                    subscription["watchlist"], news, market, mapping,
                    marketwide_signals=marketwide_signals,
                )
                subject, html, text = render_morning_email(
                    alerts, signals, now.isoformat(), app_url, universe_coverage
                )
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
