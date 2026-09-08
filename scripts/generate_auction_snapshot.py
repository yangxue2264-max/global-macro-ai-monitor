"""Generate the second-stage A-share opening-auction snapshot at 09:27 China time."""
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

from core.emailing import send_email
from core.opportunity_model import detect_market_auction_anomalies
from core.providers import fetch_all_auction_quotes
from core.reporting import build_personal_analysis, render_auction_email
from core.subscriptions import get_secret, list_active_subscriptions
from core.trading_calendar import is_a_share_trading_day


CN = ZoneInfo("Asia/Shanghai")


def main(send_emails: bool = False, force: bool = False):
    now = datetime.now(CN)
    if not force and not is_a_share_trading_day(now.date()):
        print(f"skip {now.date()}: not an A-share trading day")
        return
    mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    morning_path = BASE / "data" / "latest_morning_brief.json"
    morning = json.loads(morning_path.read_text(encoding="utf-8")) if morning_path.exists() else {}
    market, news = morning.get("market", {}), morning.get("news", [])
    marketwide_signals = morning.get("signals", [])
    subscriptions = list_active_subscriptions()
    trade_date = now.strftime("%Y-%m-%d")
    quotes, auction_coverage = fetch_all_auction_quotes(
        trade_date, tushare_token=get_secret("TUSHARE_TOKEN")
    )
    anomalies = detect_market_auction_anomalies(quotes)
    payload = {
        "generated_at": now.isoformat(),
        "trade_date": trade_date,
        "quote_count": len(quotes),
        "quotes": quotes,
        "anomalies": anomalies,
        "auction_coverage": auction_coverage,
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
                    subscription["watchlist"], news, market, mapping, quotes,
                    marketwide_signals=marketwide_signals,
                    market_anomalies=anomalies,
                )
                subject, html, text = render_auction_email(
                    alerts, signals, now.isoformat(), app_url, anomalies, auction_coverage
                )
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
