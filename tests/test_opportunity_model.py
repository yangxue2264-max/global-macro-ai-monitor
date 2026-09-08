from datetime import date, timedelta

from core.opportunity_model import (
    attach_dynamic_guidance,
    detect_market_auction_anomalies,
    discover_market_targets,
)
from core.preopen import attach_auction_results, price_confirmation


def histories(days=180):
    start = date(2025, 10, 1)
    proxy, stock = [], []
    stock_close = 100.0
    for index in range(days):
        stamp = (start + timedelta(days=index)).isoformat()
        proxy_return = 0.35 + (index % 7) * 0.12 if index % 3 else -(0.25 + (index % 5) * 0.10)
        proxy.append({"date": stamp, "open": 100, "close": 100, "return_pct": proxy_return, "open_gap_pct": 0, "volume": 1000})
        prior_proxy = proxy[index - 1]["return_pct"] if index else -0.2
        day_return = 1.20 + (index % 4) * 0.18 if prior_proxy > 0 else -(0.45 + (index % 3) * 0.10)
        open_gap = 0.35 + (index % 5) * 0.09 if prior_proxy > 0 else -0.20
        opening = stock_close * (1 + open_gap / 100)
        stock_close *= 1 + day_return / 100
        stock.append({"date": stamp, "open": opening, "close": stock_close, "return_pct": day_return, "open_gap_pct": open_gap, "volume": 2000})
    return proxy, stock


proxy_history, stock_history = histories()
market = {
    "NVDA": {"name": "NVIDIA", "ticker": "NVDA", "change_pct": 3.0, "history": proxy_history},
    "STOCK": {"name": "测试股票", "ticker": "000001.SZ", "last": stock_history[-1]["close"], "history": stock_history},
}
confirmation = price_confirmation(["NVDA"], market)
assert confirmation["confirmed"] is True
assert confirmation["strongest"]["tail_percentile"] >= 0.85

signal = {
    "category": "海外已验证", "theme": "AI资本开支", "title": "AI capex rises",
    "source": "Reuters", "url": "https://example.com", "published": "2026-09-08",
    "evidence": 82, "evidence_label": "B", "price_text": "NVIDIA +3.00%",
    "price_direction": "上涨", "price_moves": [{"key": "NVDA", "name": "NVIDIA", "move": 3.0}],
    "mechanism": "资本开支传导到服务器供应链", "risk": "订单不确认",
    "targets": [{"ticker": "000001.SZ", "name": "测试股票", "beta": 1, "source": "主题映射", "mapping_level": "维护映射"}],
}
guided = attach_dynamic_guidance([signal], market)[0]
guidance = guided["targets"][0]["guidance"]
assert guidance["action"] == "可条件参与"
assert guidance["max_gap_pct"] is not None
assert guidance["sample_count"] >= 20 and guidance["effective_sample"] >= 8
assert guidance["primary_horizon"] in {"T+0", "T+3", "T+5", "T+20"}

target = guided["targets"][0]
low_gap = min(guidance["max_gap_pct"] - 0.05, 0.2)
high_gap = guidance["overpriced_gap_pct"] + 0.1
quotes = {"000001.SZ": {"status": "ok", "gap_pct": low_gap, "auction_price": 100, "pre_close": 100, "source": "test"}}
assert attach_auction_results([guided], quotes)[0]["targets"][0]["auction"]["status"] == "仍有预期差"
quotes["000001.SZ"]["gap_pct"] = high_gap
assert attach_auction_results([guided], quotes)[0]["targets"][0]["auction"]["status"] == "过度定价/追高风险"

thin_market = {"NVDA": market["NVDA"], "STOCK": {**market["STOCK"], "history": stock_history[-12:]}}
thin_guidance = attach_dynamic_guidance([signal], thin_market)[0]["targets"][0]["guidance"]
assert thin_guidance["max_gap_pct"] is None and thin_guidance["action"] == "样本不足"

universe = []
for index in range(45):
    cap = 2_000_000_000 if index < 15 else 12_000_000_000 if index < 30 else 80_000_000_000
    universe.append({"ticker": f"{index:06d}.SZ", "name": f"通信股{index}", "industry": "通信设备", "market_cap": cap, "amount": 10_000_000 + index})
discovered = discover_market_targets([signal], universe, max_per_signal=9)[0]["targets"]
assert {row.get("size_bucket") for row in discovered if row.get("source") == "全市场行业检索"} == {"小市值", "中市值", "大市值"}

auction_quotes = {}
for index in range(120):
    ticker = f"{600000 + index}.SS"
    gap = 0.05 + index * 0.01
    auction_quotes[ticker] = {"ticker": ticker, "name": f"股票{index}", "status": "ok", "gap_pct": gap, "market_cap": 20_000_000_000, "source": "test"}
anomalies = detect_market_auction_anomalies(auction_quotes)
assert anomalies and all(row["dynamic_threshold_pct"] > 0 for row in anomalies)
assert all(row["primary_horizon"] == "T+0" for row in anomalies)

print("OPPORTUNITY_MODEL_TEST_OK")
