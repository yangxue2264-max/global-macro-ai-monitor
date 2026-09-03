"""Generate the deterministic 09:00 A-share pre-open snapshot.

Run from the repository root. The script does not call the OpenAI API.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.briefing import morning_rule_brief
from core.evidence import add_evidence_scores
from core.market_context import enrich_macro_with_market_proxies
from core.providers import (
    fetch_fred_snapshot, fetch_market_snapshot, fetch_news_bundle,
    fetch_treasury_snapshot, flatten_watchlist, load_watchlist,
)

CN = ZoneInfo("Asia/Shanghai")


def main():
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    universe = flatten_watchlist(cfg)
    market = fetch_market_snapshot(universe)
    macro = enrich_macro_with_market_proxies(fetch_fred_snapshot(), market, fetch_treasury_snapshot())
    news = add_evidence_scores(fetch_news_bundle(max_each=10))
    brief = morning_rule_brief(market, macro, news)
    now = datetime.now(CN)
    payload = {
        "generated_at": now.isoformat(),
        "brief": brief,
        "market": market,
        "macro": macro,
        "news": news[:30],
    }
    outdir = BASE / "data" / "brief_history"
    outdir.mkdir(parents=True, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True)
    (outdir / f"{day}.json").write_text(rendered, encoding="utf-8")
    (BASE / "data" / "latest_morning_brief.json").write_text(rendered, encoding="utf-8")
    print(f"generated {day}: {len(news)} events, {len(market)} market series")


if __name__ == "__main__":
    main()
