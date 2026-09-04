"""Generate the second-stage A-share opening-auction snapshot at 09:27 China time."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.providers import fetch_auction_quotes, flatten_watchlist, load_watchlist


CN = ZoneInfo("Asia/Shanghai")


def main():
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    universe = flatten_watchlist(cfg)
    mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    defaults = json.loads((BASE / "config" / "default_user_watchlist.json").read_text(encoding="utf-8"))
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
    tickers = sorted(
        ticker for ticker in candidate_tickers
        if str(ticker).endswith((".SS", ".SZ", ".BJ"))
    )
    now = datetime.now(CN)
    trade_date = now.strftime("%Y-%m-%d")
    quotes = fetch_auction_quotes(tickers, trade_date, tushare_token=os.getenv("TUSHARE_TOKEN", ""))
    payload = {
        "generated_at": now.isoformat(),
        "trade_date": trade_date,
        "quote_count": len(quotes),
        "quotes": quotes,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    outdir = BASE / "data" / "auction_history"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{trade_date}.json").write_text(rendered, encoding="utf-8")
    (BASE / "data" / "latest_auction_snapshot.json").write_text(rendered, encoding="utf-8")
    if not quotes:
        raise SystemExit("No valid auction quotes were returned; snapshot not accepted.")
    print(f"generated {trade_date}: {len(quotes)} auction quotes")


if __name__ == "__main__":
    main()
