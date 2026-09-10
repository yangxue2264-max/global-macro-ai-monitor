"""Idempotent catch-up runner for the two China-market report stages."""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.trading_calendar import is_a_share_trading_day
from scripts.generate_auction_snapshot import main as generate_auction
from scripts.generate_morning_brief import main as generate_morning

CN = ZoneInfo("Asia/Shanghai")


def _payload(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _morning_valid(day: str) -> bool:
    payload = _payload(BASE / "data" / "latest_morning_brief.json")
    coverage = payload.get("universe_coverage", {})
    return (
        str(payload.get("generated_at", ""))[:10] == day
        and bool(coverage.get("usable", coverage.get("count", 0) >= 4500))
    )


def _auction_valid(day: str) -> bool:
    payload = _payload(BASE / "data" / "latest_auction_snapshot.json")
    coverage = payload.get("auction_coverage", {})
    return (
        payload.get("trade_date") == day
        and bool(coverage.get("usable", coverage.get("count", 0) >= 3500))
    )


def main():
    now = datetime.now(CN)
    day = now.date().isoformat()
    clock = now.time().replace(second=0, microsecond=0)
    if not is_a_share_trading_day(now.date()):
        print(f"skip {day}: not an A-share trading day")
        return
    if clock < time(8, 45) or clock > time(10, 0):
        print(f"skip {now.isoformat()}: outside the useful pre-open catch-up window")
        return

    morning_valid = _morning_valid(day)
    if not morning_valid:
        # After 09:25 the first email is no longer actionable. Still build the
        # baseline silently so the 09:27-stage calculation has current inputs.
        send_morning = clock < time(9, 25)
        print(f"run morning: send_emails={send_morning}")
        generate_morning(send_emails=send_morning)
        morning_valid = _morning_valid(day)

    if clock >= time(9, 27) and not _auction_valid(day):
        if not morning_valid:
            raise SystemExit("current morning baseline unavailable; auction stage stopped")
        print("run auction: send_emails=True")
        generate_auction(send_emails=True)
    else:
        print("auction stage not due or already complete")


if __name__ == "__main__":
    main()
