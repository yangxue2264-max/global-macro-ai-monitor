from __future__ import annotations

import base64
import json
import math
import statistics
import zlib
from typing import Iterable


VERIFIED_MOVE_THRESHOLD = 2.0
RELIABLE_EVIDENCE_THRESHOLD = 70
MAX_USER_STOCKS = 30


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def normalize_a_share_ticker(value: str) -> str:
    """Convert a six-digit A-share code into the Yahoo-style ticker used by the app."""
    raw = (value or "").strip().upper().replace(" ", "")
    if raw.endswith((".SS", ".SZ", ".BJ")):
        return raw
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        return raw
    if digits.startswith(("4", "8", "92")):
        return f"{digits}.BJ"
    if digits.startswith(("5", "6", "9")):
        return f"{digits}.SS"
    return f"{digits}.SZ"


def _split_tokens(value) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = str(value or "").replace("，", ",").split(",")
    return [str(item).strip() for item in values if str(item).strip()]


def normalize_watchlist_rows(rows: Iterable[dict], max_items: int = MAX_USER_STOCKS) -> list[dict]:
    clean = []
    seen = set()
    for row in rows:
        ticker = normalize_a_share_ticker(str(row.get("ticker") or row.get("code") or ""))
        if not ticker or ticker in seen:
            continue
        name = str(row.get("name") or ticker).strip()
        theme = str(row.get("theme") or "待分类").strip()
        overseas_assets = _split_tokens(row.get("overseas_assets"))
        keywords = _split_tokens(row.get("keywords"))
        clean.append(
            {
                "ticker": ticker,
                "name": name,
                "theme": theme,
                "overseas_assets": overseas_assets,
                "keywords": keywords,
            }
        )
        seen.add(ticker)
        if len(clean) >= max_items:
            break
    return clean


def encode_watchlist(rows: Iterable[dict]) -> str:
    payload = json.dumps(normalize_watchlist_rows(rows), ensure_ascii=False, separators=(",", ":"))
    compressed = zlib.compress(payload.encode("utf-8"), level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")


def decode_watchlist(value: str, fallback: Iterable[dict] | None = None) -> list[dict]:
    try:
        padded = str(value or "") + "=" * (-len(str(value or "")) % 4)
        raw = zlib.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8")
        decoded = json.loads(raw)
        if not isinstance(decoded, list):
            raise ValueError("watchlist payload is not a list")
        rows = normalize_watchlist_rows(decoded)
        return rows or normalize_watchlist_rows(fallback or [])
    except Exception:
        return normalize_watchlist_rows(fallback or [])


def watchlist_editor_rows(rows: Iterable[dict]) -> list[dict]:
    return [
        {
            "代码": row["ticker"].split(".")[0],
            "名称": row["name"],
            "映射主题": row["theme"],
            "海外代理": ", ".join(row.get("overseas_assets", [])),
            "新闻关键词": ", ".join(row.get("keywords", [])),
        }
        for row in normalize_watchlist_rows(rows)
    ]


def watchlist_from_editor(rows: Iterable[dict]) -> list[dict]:
    return normalize_watchlist_rows(
        {
            "ticker": row.get("代码", ""),
            "name": row.get("名称", ""),
            "theme": row.get("映射主题", ""),
            "overseas_assets": row.get("海外代理", ""),
            "keywords": row.get("新闻关键词", ""),
        }
        for row in rows
    )


def _news_text(item: dict) -> str:
    return f"{item.get('title', '')} {item.get('source', '')}".lower()


def _direct_match(stock: dict, item: dict) -> bool:
    text = _news_text(item)
    needles = [stock.get("name", ""), stock.get("ticker", "").split(".")[0], *stock.get("keywords", [])]
    return any(str(needle).strip().lower() in text for needle in needles if len(str(needle).strip()) >= 2)


def _theme_match(stock: dict, item: dict) -> bool:
    theme = stock.get("theme")
    return bool(theme and theme != "待分类" and theme in item.get("themes", []))


def _asset_moves(keys: Iterable[str], market: dict) -> list[dict]:
    moves = []
    for key in keys:
        item = market.get(key, {})
        move = _finite(item.get("change_pct"))
        if move is None:
            continue
        moves.append({"key": key, "name": item.get("name", key), "move": round(move, 2)})
    return sorted(moves, key=lambda row: abs(row["move"]), reverse=True)


def price_confirmation(keys: Iterable[str], market: dict) -> dict:
    moves = _asset_moves(keys, market)
    values = [row["move"] for row in moves]
    median = statistics.median(values) if values else None
    strongest = moves[0] if moves else None
    confirmed = bool(
        strongest
        and (
            abs(strongest["move"]) >= VERIFIED_MOVE_THRESHOLD
            or (len(values) >= 2 and median is not None and abs(median) >= 1.0)
        )
    )
    anchor = median if median not in (None, 0) else strongest["move"] if strongest else None
    direction = "上涨" if anchor is not None and anchor > 0 else "下跌" if anchor is not None and anchor < 0 else "中性"
    return {
        "confirmed": confirmed,
        "direction": direction,
        "median": None if median is None else round(median, 2),
        "strongest": strongest,
        "moves": moves,
    }


def _market_item_for_stock(stock: dict, market: dict) -> dict:
    ticker = stock.get("ticker")
    for item in market.values():
        if item.get("ticker") == ticker:
            return item
    return {}


def _targets_for_theme(theme: str, item: dict, mapping: dict, watchlist: list[dict], market: dict) -> list[dict]:
    direct = [stock for stock in watchlist if _direct_match(stock, item)]
    thematic = [stock for stock in watchlist if stock.get("theme") == theme and stock not in direct]
    targets = []
    for stock in direct + thematic:
        targets.append({"ticker": stock["ticker"], "name": stock["name"], "source": "自选股", "role": "自选"})
    for key in mapping.get("a_share_assets", []):
        market_item = market.get(key, {})
        ticker = market_item.get("ticker", key)
        name = market_item.get("name", key)
        if not any(row["ticker"] == ticker or row["name"] == name for row in targets):
            targets.append({"ticker": ticker, "name": name, "source": "主题映射", "role": mapping.get("target_roles", {}).get(key, "")})
    return targets[:8]


def build_opportunity_signals(news: Iterable[dict], market: dict, mapping_cfg: dict, watchlist: Iterable[dict], limit: int = 24) -> list[dict]:
    watchlist = normalize_watchlist_rows(watchlist)
    signals = []
    for item in news:
        evidence = int(item.get("evidence_score") or 0)
        if evidence < RELIABLE_EVIDENCE_THRESHOLD:
            continue
        themes = [theme for theme in item.get("themes", []) if theme in mapping_cfg]
        if not themes:
            continue
        theme = themes[0]
        mapping = mapping_cfg[theme]
        confirmation = price_confirmation(mapping.get("global_assets", []), market)
        targets = _targets_for_theme(theme, item, mapping, watchlist, market)
        if not targets:
            continue
        direct_watch = any(_direct_match(stock, item) for stock in watchlist)
        watch_relevant = direct_watch or any(stock.get("theme") == theme for stock in watchlist)
        category = "海外已验证" if confirmation["confirmed"] else "传导待验证"
        strongest = confirmation.get("strongest")
        move_score = min(abs(strongest["move"]) / 4 * 35, 35) if strongest else 0
        priority = round(min(100, evidence * 0.45 + move_score + (20 if direct_watch else 14 if watch_relevant else 7)))
        if strongest:
            price_text = f"{strongest['name']} {strongest['move']:+.2f}%"
        else:
            price_text = "相关海外代理暂无有效价格"
        signals.append(
            {
                "category": category,
                "priority": priority,
                "theme": theme,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "published": item.get("published", ""),
                "evidence": evidence,
                "evidence_label": item.get("evidence_label", ""),
                "price_text": price_text,
                "price_direction": confirmation["direction"],
                "price_moves": confirmation["moves"][:4],
                "targets": targets,
                "watchlist_relevant": watch_relevant,
                "direct_watch_match": direct_watch,
                "mechanism": mapping.get("logic", "待核实传导链"),
                "direction_note": mapping.get("direction_note", "必须核对A股标的是受益端还是受损端。"),
                "next_check": "集合竞价强弱、开盘量价与板块扩散" if category == "海外已验证" else "先核对原始事实，再等待海外价格或A股集合竞价确认",
                "risk": mapping.get("invalidation", "若后续价格与基本面均不确认，应降低信号权重。"),
            }
        )
    signals.sort(key=lambda row: (row["category"] != "海外已验证", not row["watchlist_relevant"], -row["priority"]))
    return signals[:limit]


def build_watchlist_alerts(watchlist: Iterable[dict], news: Iterable[dict], market: dict, mapping_cfg: dict) -> list[dict]:
    rows = []
    reliable_news = [item for item in news if int(item.get("evidence_score") or 0) >= RELIABLE_EVIDENCE_THRESHOLD]
    for stock in normalize_watchlist_rows(watchlist):
        direct_news = [item for item in reliable_news if _direct_match(stock, item)]
        theme_news = [item for item in reliable_news if _theme_match(stock, item) and item not in direct_news]
        mapping = mapping_cfg.get(stock.get("theme"), {})
        overseas_keys = stock.get("overseas_assets") or mapping.get("global_assets", [])
        confirmation = price_confirmation(overseas_keys, market)
        own_market = _market_item_for_stock(stock, market)
        if direct_news or (confirmation["confirmed"] and (theme_news or mapping)):
            level = "重点异动"
        elif theme_news or confirmation["moves"]:
            level = "需要关注"
        else:
            level = "暂无异动"
        reasons = []
        if direct_news:
            reasons.append(f"发现{len(direct_news)}条直接相关新闻")
        elif theme_news:
            reasons.append(f"发现{len(theme_news)}条{stock['theme']}可靠新闻")
        if confirmation["strongest"]:
            strongest = confirmation["strongest"]
            reasons.append(f"海外代理 {strongest['name']} {strongest['move']:+.2f}%")
        if not reasons:
            reasons.append("未发现可靠新闻或显著海外代理波动")
        headline = (direct_news or theme_news or [{}])[0]
        rows.append(
            {
                "level": level,
                "name": stock["name"],
                "ticker": stock["ticker"],
                "theme": stock["theme"],
                "reason": "；".join(reasons),
                "price_direction": confirmation["direction"],
                "overseas_moves": confirmation["moves"][:4],
                "headline": headline.get("title", ""),
                "news_url": headline.get("url", ""),
                "source": headline.get("source", ""),
                "previous_close": _finite(own_market.get("last")),
                "previous_day_move": _finite(own_market.get("change_pct")),
                "asof": own_market.get("asof", ""),
                "next_check": "09:15后检查集合竞价、开盘量价和所属板块是否同步。" if level != "暂无异动" else "无需优先处理，除非集合竞价出现新的异常。",
            }
        )
    rank = {"重点异动": 0, "需要关注": 1, "暂无异动": 2}
    return sorted(rows, key=lambda row: (rank[row["level"]], -abs(row["previous_day_move"] or 0)))
