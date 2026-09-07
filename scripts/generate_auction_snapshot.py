"""Generate the second-stage A-share opening-auction snapshot at 09:27 China time."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.emailing import send_email
from core.preopen import build_opportunity_signals
from core.providers import fetch_auction_quotes, flatten_watchlist, load_watchlist
from core.reporting import build_personal_analysis, render_auction_email
from core.subscriptions import get_secret, list_active_subscriptions
from core.trading_calendar import is_a_share_trading_day


CN = ZoneInfo("Asia/Shanghai")


def main(send_emails: bool = False, force: bool = False):
    now = datetime.now(CN)
    if not force and not is_a_share_trading_day(now.date()):
        print(f"skip {now.date()}: not an A-share trading day")
        return
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    universe = flatten_watchlist(cfg)
    mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    defaults = json.loads((BASE / "config" / "default_user_watchlist.json").read_text(encoding="utf-8"))
    morning_path = BASE / "data" / "latest_morning_brief.json"
    morning = json.loads(morning_path.read_text(encoding="utf-8")) if morning_path.exists() else {}
    market, news = morning.get("market", {}), morning.get("news", [])
    subscriptions = list_active_subscriptions()
    mapped_keys = {
        key
        for theme in mapping.values()
        for key in theme.get("a_share_assets", [])
    }
    candidate_tickers = {
        meta.get("ticker", "")
        for key, meta in universe.items()
        if key in mapped_keys or str(meta.get("ticker", "")).endswith((".SS", ".SZ", ".BJ"))
    }
    candidate_tickers.update(row.get("ticker", "") for row in defaults)
    for subscription in subscriptions:
        personal_watchlist = subscription.get("watchlist", [])
        candidate_tickers.update(row.get("ticker", "") for row in personal_watchlist)
        for signal in build_opportunity_signals(news, market, mapping, personal_watchlist):
            candidate_tickers.update(target.get("ticker", "") for target in signal.get("targets", []))
    tickers = sorted(
        ticker for ticker in candidate_tickers
        if str(ticker).endswith((".SS", ".SZ", ".BJ"))
    )
    trade_date = now.strftime("%Y-%m-%d")
    quotes = fetch_auction_quotes(tickers, trade_date, tushare_token=os.getenv("TUSHARE_TOKEN", ""))
    payload = {
        "generated_at": now.isoformat(),
        "trade_date": trade_date,
        "quote_count": len(quotes),
        "quotes": quotes,
        "stage": "09:27",
        "subscriber_count": len(subscriptions),
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    outdir = BASE / "data" / "auction_history"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{trade_date}.json").write_text(rendered, encoding="utf-8")
    (BASE / "data" / "latest_auction_snapshot.json").write_text(rendered, encoding="utf-8")
    print(f"generated {trade_date}: {len(quotes)} auction quotes, {len(subscriptions)} subscribers")

    if send_emails:
        failures = 0
        app_url = get_secret("APP_URL")
        for subscription in subscriptions:
            try:
                alerts, signals = build_personal_analysis(
                    subscription["watchlist"], news, market, mapping, quotes
                )
                subject, html, text = render_auction_email(alerts, signals, now.isoformat(), app_url)
                send_email(subscription["email"], subject, html, text)
            except Exception as exc:
                failures += 1
                print(f"subscriber delivery failed: {type(exc).__name__}: {exc}")
        print(f"09:27 email delivery complete: {len(subscriptions) - failures}/{len(subscriptions)}")
        if failures:
            raise SystemExit(f"{failures} subscriber emails failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-emails", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(send_emails=args.send_emails, force=args.force)
