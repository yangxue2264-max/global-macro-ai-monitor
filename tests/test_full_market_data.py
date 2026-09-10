from unittest.mock import patch

from core.providers import fetch_a_share_universe, fetch_all_auction_quotes


official = [
    {
        "ticker": f"{index:06d}.SZ",
        "name": f"测试股票{index}",
        "industry": "电子",
        "market": "主板",
        "source": "交易所",
    }
    for index in range(4600)
]
quotes = {
    row["ticker"]: {
        "ticker": row["ticker"],
        "name": row["name"],
        "auction_price": 10.0,
        "pre_close": 9.9,
        "gap_pct": 1.01,
        "date": "20260910",
        "time": "092700",
        "source": "腾讯免费实时行情",
        "status": "ok",
        "market_cap": 5_000_000_000,
    }
    for row in official[:4000]
}

with (
    patch("core.providers.fetch_official_a_share_universe", return_value=official),
    patch("core.providers.fetch_eastmoney_a_share_universe", return_value=[]),
    patch("core.providers.fetch_tencent_auction", return_value=quotes),
    patch("core.providers.save_a_share_universe_cache"),
    patch("core.providers.load_cached_a_share_universe", return_value=([], {})),
):
    rows, coverage = fetch_a_share_universe()
assert len(rows) == 4600
assert coverage["usable"] is True
assert coverage["quote_count"] == 4000

with (
    patch("core.providers.fetch_a_share_universe", return_value=(official, {"usable": True, "count": 4600})),
    patch("core.providers.fetch_tencent_auction", return_value=quotes),
):
    auction_rows, auction_coverage = fetch_all_auction_quotes("2026-09-10")
assert len(auction_rows) == 4000
assert auction_coverage["usable"] is True
assert auction_coverage["mode"] == "FREE_FULL_MARKET"

print("FULL_MARKET_DATA_TEST_OK")
