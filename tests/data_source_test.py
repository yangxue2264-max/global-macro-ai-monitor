from unittest.mock import patch

import pandas as pd

from core.providers import (
    _eastmoney_index_history,
    _fred_api,
    _snapshot_from_frames,
    _tencent_index_history,
    data_health,
    fetch_fred_snapshot,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


fred_payload = {
    "observations": [
        {"date": "2026-09-02", "value": "4.20"},
        {"date": "2026-09-01", "value": "4.10"},
        {"date": "2026-08-31", "value": "."},
    ]
}
with patch("core.providers.requests.get", return_value=FakeResponse(fred_payload)):
    fred_frame = _fred_api("TEST", "a" * 32)
assert list(fred_frame["TEST"]) == [4.10, 4.20]

series = {"TEST": {"name": "测试序列", "series": "TEST", "unit": "%"}}
with patch("core.providers._fred_api", return_value=fred_frame):
    fred = fetch_fred_snapshot(series, "a" * 32)
assert fred["TEST"]["value"] == 4.20
assert abs(fred["TEST"]["delta"] - 0.10) < 1e-9
assert fred["TEST"]["source"] == "FRED API"

eastmoney_payload = {
    "data": {
        "klines": [
            "2026-09-01,100,101,102,99,1000,0,0,0,0,0",
            "2026-09-02,101,103,104,100,1100,0,0,0,0,0",
        ]
    }
}
with patch("core.providers.requests.get", return_value=FakeResponse(eastmoney_payload)):
    eastmoney = _eastmoney_index_history("0.399006")
assert list(eastmoney["Close"]) == [101, 103]

tencent_payload = {
    "data": {
        "sz399006": {
            "qfqday": [
                ["2026-09-01", "100", "101", "102", "99", "1000"],
                ["2026-09-02", "101", "103", "104", "100", "1100"],
            ]
        }
    }
}
with patch("core.providers.requests.get", return_value=FakeResponse(tencent_payload)):
    tencent = _tencent_index_history("sz399006")
assert list(tencent["Close"]) == [101, 103]

snapshot = _snapshot_from_frames(
    {"name": "创业板指", "ticker": "399006.SZ"},
    pd.Series([100.0, 103.0], index=pd.to_datetime(["2026-09-01", "2026-09-02"])),
    source="东方财富",
)
assert snapshot["status"] == "ok" and snapshot["source"] == "东方财富"

proxy_snapshot = _snapshot_from_frames(
    {"name": "科创50", "ticker": "000688.SS"},
    pd.Series([1.00, 1.03], index=pd.to_datetime(["2026-09-01", "2026-09-02"])),
    source="Yahoo Finance · 科创50ETF代理（588000）",
    status="market_proxy",
    proxy_ticker="588000.SS",
)
assert proxy_snapshot["status"] == "market_proxy"
assert proxy_snapshot["proxy_ticker"] == "588000.SS"

health = data_health(
    {"A": {"status": "ok"}},
    {
        "A": {"status": "ok"},
        "B": {"status": "treasury"},
        "C": {"status": "market_proxy"},
        "D": {"status": "derived"},
    },
    [],
)
assert health["macro_live"] == 2
assert health["macro_proxy"] == 2

print("DATA_SOURCE_TEST_OK")
