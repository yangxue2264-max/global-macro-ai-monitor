from __future__ import annotations

from datetime import datetime, timedelta, timezone


BASE_VALUES = {
    "SP500": 6500, "NASDAQ": 23800, "RUSSELL": 2350, "CSI300": 4300, "SSE": 3900,
    "CHINEXT": 2700, "HSI": 26500, "NIKKEI": 44500, "KOSPI": 3350, "STOXX50": 5450,
    "DXY": 98.5, "USDCNH": 7.08, "USDJPY": 146.0, "EURUSD": 1.16, "GOLD": 3500,
    "SILVER": 42, "COPPER": 5.1, "WTI": 67, "BRENT": 71, "NATGAS": 3.0, "CORN": 425,
    "SOY": 1040, "BTC": 112000, "US10Y_PROXY": 42.1, "VIX_MARKET": 17.8,
}


def demo_market(universe):
    rows = {}
    asof = datetime.now(timezone.utc).date().isoformat()
    for index, (key, meta) in enumerate(universe.items()):
        day = ((index % 9) - 4) * 0.18
        d5 = ((index % 7) - 3) * 0.65
        d20 = ((index % 11) - 5) * 1.25
        history = []
        close = BASE_VALUES.get(key, 80 + index * 3.5)
        start = datetime.now(timezone.utc).date() - timedelta(days=220)
        for offset in range(180):
            move = ((offset + index) % 9 - 4) * 0.28
            opening = close * (1 + move * 0.30 / 100)
            close *= 1 + move / 100
            history.append({
                "date": (start + timedelta(days=offset)).isoformat(),
                "open": round(opening, 6), "close": round(close, 6),
                "return_pct": round(move, 4), "open_gap_pct": round(move * 0.30, 4),
                "volume": 1_000_000 + offset * 1000,
            })
        rows[key] = {
            **meta, "last": BASE_VALUES.get(key, 80 + index * 3.5), "change_pct": day,
            "change_5d_pct": d5, "change_20d_pct": d20, "vol_20d": 18 + index % 12,
            "ret_z": day / 0.7, "volume_ratio": 0.9 + (index % 6) * 0.12,
            "asof": asof, "status": "demo",
            "history": history,
        }
    return rows


def demo_macro(series_map):
    values = {"US10Y": 4.20, "US2Y": 3.82, "USREAL10Y": 1.89, "BREAKEVEN10Y": 2.31,
              "HYSPREAD": 3.35, "VIX": 17.8, "NFCI": -0.25, "FEDBAL": 6580000,
              "RRP": 85, "UNRATE": 4.2, "CPI": 325.1}
    today = datetime.now(timezone.utc).date().isoformat()
    return {key: {"name": meta["name"], "value": values.get(key), "prev": values.get(key),
                  "delta": 0.0, "date": today, "unit": meta.get("unit", ""), "status": "demo"}
            for key, meta in series_map.items()}


def demo_news():
    return [
        {"title": "DEMO · Hyperscalers discuss data-center capex, power and grid constraints", "url": "", "source": "Demonstration item", "published": "", "modules": ["实体瓶颈"], "themes": ["AI资本开支"], "score": 2.0, "bucket": "AI资本开支"},
        {"title": "DEMO · Markets reassess the path of US yields and the dollar", "url": "", "source": "Demonstration item", "published": "", "modules": ["金融状况"], "themes": ["流动性与信用"], "score": 1.9, "bucket": "全球宏观"},
        {"title": "DEMO · Energy supply risk raises questions for inflation-sensitive sectors", "url": "", "source": "Demonstration item", "published": "", "modules": ["通胀", "地缘与供应链"], "themes": ["油价与通胀"], "score": 1.8, "bucket": "商品与瓶颈"},
    ]
