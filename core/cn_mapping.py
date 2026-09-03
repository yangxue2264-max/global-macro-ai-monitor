from __future__ import annotations


def cn_watch_rows(news, market):
    """Compact A-share watch rows kept for smoke tests and downstream reuse."""
    themes = {theme for item in news for theme in item.get("themes", [])}
    mapping = {
        "AI资本开支": ["FOXCONN", "ZHONGJI", "EOPTOLINK", "WUS", "XD", "TBEA"],
        "油价与通胀": ["SHENHUA", "ZIJIN"],
        "天气与农业": ["LONGPING", "BEIDAHUANG"],
        "中国增长与政策": ["CSI300", "HSI", "BABA"],
    }
    rows = []
    for theme in themes:
        for key in mapping.get(theme, []):
            item = market.get(key, {})
            rows.append({"主题": theme, "代码": key, "资产": item.get("name", key),
                         "1日%": item.get("change_pct"), "20日%": item.get("change_20d_pct")})
    return rows
