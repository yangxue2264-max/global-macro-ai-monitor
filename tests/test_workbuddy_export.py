from core.workbuddy_export import build_workbuddy_payload


watchlist = [
    {
        "ticker": "601138.SS",
        "name": "工业富联",
        "theme": "AI资本开支",
        "relation": "同向",
        "overseas_assets": ["NVDA", "SMH"],
        "keywords": ["工业富联"],
    }
]
mapping = {
    "AI资本开支": {
        "global_assets": ["NVDA", "SMH"],
        "a_share_assets": ["FOXCONN"],
        "logic": "海外AI资本开支 → 服务器订单 → A股供应链",
        "invalidation": "订单与价格均未确认",
    }
}
morning = {
    "generated_at": "2026-09-07T09:00:00+08:00",
    "market": {
        "NVDA": {"name": "NVIDIA", "ticker": "NVDA", "change_pct": 3.2},
        "SMH": {"name": "Semiconductor ETF", "ticker": "SMH", "change_pct": 2.4},
        "FOXCONN": {"name": "工业富联", "ticker": "601138.SS", "change_pct": 0.8, "last": 52.1},
    },
    "news": [
        {
            "title": "Hyperscalers raise AI server capex guidance",
            "source": "Reuters",
            "url": "https://example.com/ai",
            "published": "2026-09-07T07:30:00+08:00",
            "themes": ["AI资本开支"],
            "evidence_score": 78,
            "evidence_label": "B·可靠报道",
        }
    ],
}

stale_auction = {
    "generated_at": "2026-09-04T09:27:00+08:00",
    "trade_date": "2026-09-04",
    "quotes": {"601138.SS": {"status": "ok", "gap_pct": 5.0, "source": "test"}},
}
payload = build_workbuddy_payload(morning, stale_auction, mapping, watchlist)
assert payload["stage"] == "morning_candidates"
assert payload["context"]["auction_quotes"] == {}
assert payload["watchlist_alerts"][0]["auction_status"] == "等待09:27竞价"

current_auction = {
    "generated_at": "2026-09-07T09:27:00+08:00",
    "trade_date": "2026-09-07",
    "quotes": {
        "601138.SS": {
            "status": "ok",
            "gap_pct": 0.4,
            "source": "test",
            "auction_price": 100.4,
            "pre_close": 100,
        }
    },
}
payload = build_workbuddy_payload(morning, current_auction, mapping, watchlist)
assert payload["stage"] == "auction_review"
assert payload["summary"]["auction_status_counts"]["仍有预期差"] == 1
assert payload["watchlist_alerts"][0]["auction_status"] == "仍有预期差"
assert payload["signals"][0]["signal_id"]

print("WORKBUDDY_EXPORT_TEST_OK")
