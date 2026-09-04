from core.preopen import (
    attach_auction_results,
    auction_status_counts,
    build_opportunity_signals,
    build_watchlist_alerts,
    decode_watchlist,
    encode_watchlist,
    evaluate_auction_target,
    normalize_a_share_ticker,
    normalize_watchlist_rows,
    rerank_signals_after_auction,
)


watchlist = normalize_watchlist_rows(
    [
        {
            "code": "601138",
            "name": "工业富联",
            "theme": "AI资本开支",
            "overseas_assets": "NVDA, SMH",
            "keywords": "Foxconn Industrial Internet, 工业富联",
        },
        {
            "code": "601899",
            "name": "紫金矿业",
            "theme": "黄金与美元信用",
            "overseas_assets": "GOLD, DXY",
            "keywords": "Zijin Mining, 紫金矿业",
        },
    ]
)

assert normalize_a_share_ticker("601138") == "601138.SS"
assert normalize_a_share_ticker("300750") == "300750.SZ"
assert normalize_a_share_ticker("830001") == "830001.BJ"
assert decode_watchlist(encode_watchlist(watchlist)) == watchlist

market = {
    "NVDA": {"name": "NVIDIA", "ticker": "NVDA", "change_pct": 3.2},
    "SMH": {"name": "Semiconductor ETF", "ticker": "SMH", "change_pct": 2.4},
    "GOLD": {"name": "Gold", "ticker": "GC=F", "change_pct": 0.3},
    "DXY": {"name": "Dollar Index", "ticker": "DX-Y.NYB", "change_pct": -0.2},
    "FOXCONN": {"name": "工业富联", "ticker": "601138.SS", "change_pct": 0.8, "last": 52.1, "asof": "2026-09-02"},
    "ZIJIN": {"name": "紫金矿业", "ticker": "601899.SS", "change_pct": -0.4, "last": 31.8, "asof": "2026-09-02"},
}

mapping = {
    "AI资本开支": {
        "global_assets": ["NVDA", "SMH"],
        "a_share_assets": ["FOXCONN"],
        "logic": "海外AI资本开支 → 服务器订单 → A股供应链",
        "invalidation": "订单与价格均未确认",
    },
    "黄金与美元信用": {
        "global_assets": ["GOLD", "DXY"],
        "a_share_assets": ["ZIJIN"],
        "logic": "黄金定价 → 国内金价 → 矿企利润",
        "invalidation": "金价与矿企盈利均未确认",
    },
}

news = [
    {
        "title": "Hyperscalers raise AI server capex guidance",
        "source": "Reuters",
        "url": "https://example.com/ai",
        "published": "2026-09-03T07:30:00+08:00",
        "themes": ["AI资本开支"],
        "evidence_score": 78,
        "evidence_label": "B·可靠报道",
    },
    {
        "title": "Central banks discuss reserve diversification and gold",
        "source": "Reuters",
        "url": "https://example.com/gold",
        "published": "2026-09-03T08:00:00+08:00",
        "themes": ["黄金与美元信用"],
        "evidence_score": 78,
        "evidence_label": "B·可靠报道",
    },
]

signals = build_opportunity_signals(news, market, mapping, watchlist)
assert len(signals) == 2
assert signals[0]["category"] == "海外已验证"
assert signals[0]["watchlist_relevant"] is True
assert any(row["name"] == "工业富联" for row in signals[0]["targets"])
assert signals[1]["category"] == "传导待验证"

alerts = build_watchlist_alerts(watchlist, news, market, mapping)
assert alerts[0]["name"] == "工业富联"
assert alerts[0]["level"] == "重点异动"
assert any(row["name"] == "紫金矿业" and row["level"] == "需要关注" for row in alerts)

signal = signals[0]
target = signal["targets"][0]
base_quote = {"status": "ok", "source": "test", "auction_price": 100.4, "pre_close": 100}
assert evaluate_auction_target(signal, target, {**base_quote, "gap_pct": 0.4})["status"] == "仍有预期差"
assert evaluate_auction_target(signal, target, {**base_quote, "gap_pct": 2.0})["status"] == "基本定价"
assert evaluate_auction_target(signal, target, {**base_quote, "gap_pct": 5.0})["status"] == "过度定价/追高风险"
assert evaluate_auction_target(signal, target, {**base_quote, "gap_pct": -1.0})["status"] == "A股不确认"
assert evaluate_auction_target(signal, {**target, "beta": -1}, {**base_quote, "gap_pct": -2.0})["status"] == "基本定价"

with_auction = attach_auction_results(signals, {"601138.SS": {**base_quote, "gap_pct": 0.4}})
counts = auction_status_counts(with_auction)
assert counts["仍有预期差"] == 1

priced = attach_auction_results([signals[0]], {"601138.SS": {**base_quote, "gap_pct": 2.0}})[0]
residual = attach_auction_results([signals[0]], {"601138.SS": {**base_quote, "gap_pct": 0.4}})[0]
priced["title"] = "already priced"
residual["title"] = "residual gap"
assert rerank_signals_after_auction([priced, residual])[0]["title"] == "residual gap"

duplicate = dict(residual)
duplicate["title"] = "same stock, second story"
deduplicated_counts = auction_status_counts([residual, duplicate])
assert deduplicated_counts["仍有预期差"] == 1

print("PREOPEN_TEST_OK")
