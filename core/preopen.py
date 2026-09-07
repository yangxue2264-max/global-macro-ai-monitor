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
        relation = str(row.get("relation") or "同向").strip()
        if relation not in {"同向", "反向", "需判断"}:
            relation = "需判断"
        overseas_assets = _split_tokens(row.get("overseas_assets"))
        keywords = _split_tokens(row.get("keywords"))
        clean.append(
            {
                "ticker": ticker,
                "name": name,
                "theme": theme,
                "relation": relation,
                "overseas_assets": overseas_assets,
                "keywords": keywords,
                "profile_source": str(row.get("profile_source") or "").strip(),
                "profile_confidence": str(row.get("profile_confidence") or "").strip(),
                "profile_reason": str(row.get("profile_reason") or "").strip(),
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
    """Only expose the user's intent; research fields are system-owned."""
    return [{"股票代码或名称": row["ticker"].split(".")[0]} for row in normalize_watchlist_rows(rows)]


def watchlist_inputs_from_editor(rows: Iterable[dict]) -> list[str]:
    values = []
    for row in rows:
        value = str(row.get("股票代码或名称") or row.get("代码") or "").strip()
        if value and value not in values:
            values.append(value)
    return values[:MAX_USER_STOCKS]


def watchlist_from_editor(rows: Iterable[dict]) -> list[dict]:
    """Legacy parser retained for old encoded links; new UI uses automatic enrichment."""
    return normalize_watchlist_rows(
        {
            "ticker": row.get("代码", ""),
            "name": row.get("名称", ""),
            "theme": row.get("映射主题", ""),
            "relation": row.get("与海外关系", "同向"),
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
        relation = stock.get("relation", "同向")
        beta = 1 if relation == "同向" else -1 if relation == "反向" else 0
        targets.append({"ticker": stock["ticker"], "name": stock["name"], "source": "自选股", "role": "自选", "relation": relation, "beta": beta})
    for key in mapping.get("a_share_assets", []):
        market_item = market.get(key, {})
        ticker = market_item.get("ticker", key)
        name = market_item.get("name", key)
        if not any(row["ticker"] == ticker or row["name"] == name for row in targets):
            beta = mapping.get("target_beta", {}).get(key, 1)
            targets.append({"ticker": ticker, "name": name, "source": "主题映射", "role": mapping.get("target_roles", {}).get(key, ""), "relation": "同向" if beta == 1 else "反向" if beta == -1 else "需判断", "beta": beta})
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


def evaluate_auction_target(signal: dict, target: dict, quote: dict | None) -> dict:
    if not quote or quote.get("status") != "ok":
        return {"status": "竞价数据缺失", "gap_pct": None, "reason": "未取得有效集合竞价价格。", "source": ""}
    gap = _finite(quote.get("gap_pct"))
    if gap is None:
        return {"status": "竞价数据缺失", "gap_pct": None, "reason": "集合竞价涨跌幅无法计算。", "source": quote.get("source", "")}
    if signal.get("category") != "海外已验证":
        return {"status": "等待海外确认", "gap_pct": gap, "reason": "新闻尚未获得海外价格确认，不用A股高开反推交易逻辑。", "source": quote.get("source", "")}
    direction = signal.get("price_direction")
    beta = int(target.get("beta", 1) or 0)
    if direction not in {"上涨", "下跌"} or beta == 0:
        return {"status": "方向需人工判断", "gap_pct": gap, "reason": "该主题包含受益端与受损端，需要先核对公司暴露。", "source": quote.get("source", "")}
    overseas_sign = 1 if direction == "上涨" else -1
    effective_gap = gap * overseas_sign * beta
    overseas_abs = max([abs(_finite(row.get("move")) or 0) for row in signal.get("price_moves", [])] or [0])
    priced_cutoff = max(1.0, overseas_abs * 0.45)
    excessive_cutoff = max(3.0, overseas_abs * 1.25)
    if effective_gap >= excessive_cutoff:
        status = "过度定价/追高风险"
        reason = f"竞价有效反应 {effective_gap:+.2f}%，已超过海外波动对应的高位阈值 {excessive_cutoff:.2f}%。"
    elif effective_gap >= priced_cutoff:
        status = "基本定价"
        reason = f"竞价有效反应 {effective_gap:+.2f}%，已达到基本定价阈值 {priced_cutoff:.2f}%。"
    elif effective_gap <= -0.5:
        status = "A股不确认"
        reason = f"竞价有效反应 {effective_gap:+.2f}%，方向与海外信号相反。"
    else:
        status = "仍有预期差"
        reason = f"竞价有效反应仅 {effective_gap:+.2f}%，尚未达到基本定价阈值 {priced_cutoff:.2f}%。"
    return {"status": status, "gap_pct": round(gap, 3), "effective_gap": round(effective_gap, 3), "reason": reason, "source": quote.get("source", ""), "price": quote.get("auction_price"), "pre_close": quote.get("pre_close")}


def attach_auction_results(signals: Iterable[dict], quotes: dict) -> list[dict]:
    enriched = []
    for signal in signals:
        row = dict(signal)
        targets = []
        for target in signal.get("targets", []):
            item = dict(target)
            item["auction"] = evaluate_auction_target(signal, target, quotes.get(target.get("ticker")))
            targets.append(item)
        row["targets"] = targets
        enriched.append(row)
    return enriched


def auction_status_counts(signals: Iterable[dict]) -> dict:
    counts = {"仍有预期差": 0, "基本定价": 0, "过度定价/追高风险": 0, "A股不确认": 0}
    seen = set()
    for signal in signals:
        if signal.get("category") != "海外已验证":
            continue
        for target in signal.get("targets", []):
            key = target.get("ticker")
            status = target.get("auction", {}).get("status")
            if key not in seen and status in counts:
                counts[status] += 1
                seen.add(key)
    return counts


def rerank_signals_after_auction(signals: Iterable[dict]) -> list[dict]:
    """Put verified opportunities with residual gap first after the auction snapshot."""
    status_rank = {
        "仍有预期差": 0,
        "方向需人工判断": 1,
        "A股不确认": 2,
        "基本定价": 3,
        "过度定价/追高风险": 4,
        "竞价数据缺失": 5,
        "等待海外确认": 6,
    }

    def key(signal):
        target_ranks = [
            status_rank.get(target.get("auction", {}).get("status"), 7)
            for target in signal.get("targets", [])
        ]
        best_target_rank = min(target_ranks or [7])
        return (
            signal.get("category") != "海外已验证",
            best_target_rank,
            not signal.get("watchlist_relevant", False),
            -int(signal.get("priority", 0)),
        )

    return sorted((dict(signal) for signal in signals), key=key)


def attach_auction_to_alerts(alerts: Iterable[dict], signals: Iterable[dict], quotes: dict | None = None) -> list[dict]:
    by_ticker = {}
    for signal in signals:
        if signal.get("category") != "海外已验证":
            continue
        for target in signal.get("targets", []):
            ticker = target.get("ticker")
            assessment = target.get("auction", {})
            if ticker and ticker not in by_ticker and assessment.get("status"):
                by_ticker[ticker] = {**assessment, "signal_title": signal.get("title", ""), "signal_priority": signal.get("priority", 0)}
    output = []
    for alert in alerts:
        row = dict(alert)
        ticker = alert.get("ticker")
        assessment = by_ticker.get(ticker)
        if assessment is None:
            quote = (quotes or {}).get(ticker, {})
            gap = _finite(quote.get("gap_pct")) if quote.get("status") == "ok" else None
            if gap is not None and abs(gap) >= 2.0:
                assessment = {
                    "status": "竞价独立异动",
                    "gap_pct": round(gap, 3),
                    "reason": "集合竞价出现显著跳空，但当前没有对应的海外已验证事件；需反查公司公告、行业消息和资金驱动。",
                    "source": quote.get("source", ""),
                }
            elif gap is not None:
                assessment = {
                    "status": "暂无竞价异动",
                    "gap_pct": round(gap, 3),
                    "reason": "集合竞价未达到独立异动阈值，且当前没有可用于第二阶段判断的海外已验证事件。",
                    "source": quote.get("source", ""),
                }
            else:
                assessment = {
                    "status": "竞价数据缺失",
                    "gap_pct": None,
                    "reason": "当前没有海外已验证事件，且未取得有效集合竞价价格。",
                    "source": "",
                }
        row["auction"] = assessment
        output.append(row)
    return output


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
