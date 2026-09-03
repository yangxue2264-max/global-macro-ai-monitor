import json
from pathlib import Path

from core.decision_engine import cross_market_gaps, decision_queue, evaluate_theses, one_page_markdown


BASE = Path(__file__).resolve().parents[1]


def fake_market():
    watch = json.loads((BASE / "config" / "watchlist.json").read_text(encoding="utf-8"))
    rows = {}
    index = 0
    for group in watch.values():
        for key, meta in group.items():
            rows[key] = {
                **meta,
                "change_pct": ((index % 7) - 3) * 0.4,
                "change_20d_pct": ((index % 9) - 4) * 1.5,
                "status": "demo",
            }
            index += 1
    rows["SMH"]["change_20d_pct"] = 8.0
    rows["VRT"]["change_20d_pct"] = 7.0
    rows["GRID"]["change_20d_pct"] = 4.0
    rows["COPPER"]["change_20d_pct"] = 3.0
    return rows


market = fake_market()
macro = {"VIX": {"value": 18}, "BREAKEVEN10Y": {"value": 2.35}}
news = [{"title": "AI capex", "themes": ["AI资本开支"], "evidence_score": 90}]
mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
thesis_cfg = json.loads((BASE / "config" / "thesis_book.json").read_text(encoding="utf-8"))

gaps = cross_market_gaps(market, news, mapping)
assert len(gaps) == len(mapping)
assert all(0 <= row["priority"] <= 100 for row in gaps)
assert all(set(row["score_breakdown"]) == {"证据", "海外异动", "定价缺口", "A股相关性"} for row in gaps)
assert decision_queue(market, news, mapping)[0]["priority"] >= decision_queue(market, news, mapping)[-1]["priority"]

theses = evaluate_theses(market, macro, thesis_cfg)
assert len(theses) == 4
assert all(row["status"] in {"获得确认", "证据混合", "受到挑战", "待数据"} for row in theses)
assert all(len(row["checks"]) == 4 for row in theses)

brief = {"regime": "信号分化", "regime_score": 0.1, "headline": "测试判断"}
export = one_page_markdown(brief, decision_queue(market, news, mapping), theses, "2026-09-03 08:45 中国时间")
assert "今日决策队列" in export and "反证" in export and "不构成投资建议" in export
print("DECISION_ENGINE_TEST_OK")
