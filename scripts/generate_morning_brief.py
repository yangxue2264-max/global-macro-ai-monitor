from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from core.providers import load_watchlist, flatten_watchlist, fetch_market_snapshot, fetch_fred_snapshot, fetch_news_bundle
from core.briefing import morning_rule_brief

BASE=Path(__file__).resolve().parents[1]; CN=ZoneInfo("Asia/Shanghai")
cfg=load_watchlist(BASE/"config"/"watchlist.json"); universe=flatten_watchlist(cfg)
market=fetch_market_snapshot(universe); macro=fetch_fred_snapshot(); news=fetch_news_bundle(max_each=10)
brief=morning_rule_brief(market,macro,news)
payload={"generated_at":datetime.now(CN).isoformat(),"brief":brief,"market":{k:v for k,v in market.items() if k in ["SP500","NASDAQ","CSI300","HSI","DXY","USDCNH","GOLD","COPPER","WTI","BTC"]},"macro":macro}
day=datetime.now(CN).strftime("%Y-%m-%d"); outdir=BASE/"data"/"brief_history"; outdir.mkdir(parents=True,exist_ok=True)
(outdir/f"{day}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
(BASE/"data"/"latest_morning_brief.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"generated {day}")
