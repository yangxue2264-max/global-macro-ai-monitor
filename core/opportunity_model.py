from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
import math
import statistics
from typing import Iterable


MIN_HISTORY_PAIRS = 20
MIN_EFFECTIVE_SAMPLE = 8.0
ROUND_TRIP_COST_PCT = 0.18

THEME_INDUSTRY_KEYWORDS = {
    "AI资本开支": ["通信设备", "通信", "半导体", "元器件", "电子", "计算机设备", "软件服务", "电气设备", "电网设备", "专用机械", "工业机械"],
    "流动性与信用": ["证券", "银行", "保险", "多元金融", "房地产", "白酒", "全国地产"],
    "油价与通胀": ["石油开采", "石油加工", "石化", "煤炭", "航空", "机场", "化工", "运输设备"],
    "天气与农业": ["农业综合", "种植业", "种业", "农林牧渔", "饲料", "化肥", "农药"],
    "黄金与美元信用": ["黄金", "贵金属", "有色", "矿物制品"],
    "贸易与关税": ["纺织", "家用电器", "汽车配件", "消费电子", "通信设备", "元器件", "出口"],
    "中国增长与政策": ["工程机械", "建筑", "建材", "房地产", "白酒", "家用电器", "汽车", "证券", "银行"],
}

THEME_HORIZONS = {
    "AI资本开支": [1, 3, 5, 20],
    "流动性与信用": [1, 3, 5],
    "油价与通胀": [1, 3, 5],
    "天气与农业": [3, 5, 20],
    "黄金与美元信用": [1, 3, 5, 20],
    "贸易与关税": [1, 3, 5, 20],
    "中国增长与政策": [3, 5, 20],
}


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _weighted_quantile(values: list[float], weights: list[float], quantile: float) -> float | None:
    pairs = sorted((float(value), max(0.0, float(weight))) for value, weight in zip(values, weights) if _finite(value) is not None and _finite(weight) is not None)
    total = sum(weight for _, weight in pairs)
    if not pairs or total <= 0:
        return None
    cutoff = min(1.0, max(0.0, quantile)) * total
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= cutoff:
            return value
    return pairs[-1][0]


def _effective_sample(weights: list[float]) -> float:
    total = sum(weights)
    denominator = sum(weight * weight for weight in weights)
    return total * total / denominator if denominator else 0.0


def stock_board(ticker: str) -> str:
    code = str(ticker or "").split(".")[0]
    if str(ticker).endswith(".BJ"):
        return "北交所"
    if code.startswith("688"):
        return "科创板"
    if code.startswith("300"):
        return "创业板"
    return "主板"


def _size_bucket(value) -> str:
    cap = _finite(value)
    if cap is None:
        return "规模未知"
    if cap < 5_000_000_000:
        return "小市值"
    if cap < 30_000_000_000:
        return "中市值"
    return "大市值"


def _infer_beta(theme: str, industry: str) -> int:
    text = str(industry or "")
    if theme == "油价与通胀" and any(word in text for word in ("航空", "机场")):
        return -1
    if theme in {"贸易与关税", "流动性与信用", "天气与农业"}:
        return 0
    return 1


def _candidate_score(row: dict, keywords: list[str]) -> float:
    text = f"{row.get('industry', '')} {row.get('name', '')}"
    matches = sum(1 for word in keywords if word and word in text)
    if not matches:
        return -1
    amount = max(_finite(row.get("amount")) or 0, 0)
    turnover = max(_finite(row.get("turnover_rate")) or 0, 0)
    liquidity = min(16.0, math.log10(max(amount, 1)) * 2.0)
    activity = min(8.0, math.sqrt(turnover) * 2.0)
    return matches * 45.0 + liquidity + activity


def discover_market_targets(signals: Iterable[dict], stock_universe: Iterable[dict], max_per_signal: int = 12) -> list[dict]:
    """Expand event signals across the full eligible A-share universe with size-bucket diversity."""
    universe = [dict(row) for row in stock_universe if row.get("ticker") and row.get("name")]
    output = []
    for signal in signals:
        row = dict(signal)
        event_text = f"{signal.get('title', '')} {signal.get('summary', '')}"
        existing = [dict(target) for target in signal.get("targets", [])]
        seen = {target.get("ticker") for target in existing}
        keywords = THEME_INDUSTRY_KEYWORDS.get(signal.get("theme"), [])
        buckets: dict[str, list[tuple[float, dict]]] = defaultdict(list)
        for stock in universe:
            if stock.get("ticker") in seen or "ST" in str(stock.get("name", "")).upper():
                continue
            score = _candidate_score(stock, keywords)
            compact_name = str(stock.get("name", "")).replace("*", "").replace("ST", "")
            if len(compact_name) >= 3 and compact_name in event_text:
                score = max(score, 135.0)
            if score < 0:
                continue
            bucket = _size_bucket(stock.get("float_market_cap") or stock.get("market_cap"))
            buckets[bucket].append((score, stock))
        for bucket in buckets:
            buckets[bucket].sort(key=lambda item: (-item[0], item[1].get("ticker", "")))

        added = []
        order = ["小市值", "中市值", "大市值", "规模未知"]
        while len(added) < max_per_signal and any(buckets.get(bucket) for bucket in order):
            for bucket in order:
                if len(added) >= max_per_signal or not buckets.get(bucket):
                    continue
                score, stock = buckets[bucket].pop(0)
                beta = _infer_beta(signal.get("theme", ""), stock.get("industry", ""))
                added.append({
                    "ticker": stock["ticker"], "name": stock["name"],
                    "source": "全市场行业检索", "role": stock.get("industry") or "行业候选",
                    "relation": "同向" if beta == 1 else "反向" if beta == -1 else "需判断",
                    "beta": beta, "mapping_level": "行业级候选", "size_bucket": bucket,
                    "mapping_score": round(score, 1),
                    "mapping_reason": f"全A股行业字段“{stock.get('industry') or '未知'}”命中{signal.get('theme')}；需再核对主营收入暴露。",
                    "amount": stock.get("amount"), "turnover_rate": stock.get("turnover_rate"),
                    "market_cap": stock.get("market_cap"), "float_market_cap": stock.get("float_market_cap"),
                })
        for target in existing:
            target.setdefault("mapping_level", "维护映射" if target.get("source") != "自选股" else "用户自选")
            target.setdefault("mapping_reason", "来自维护映射或用户自选配置，仍需核对公司最新业务暴露。")
        # Lead with candidates found by today's full-market scan. Personalized
        # self-selected stocks are inserted ahead of these later, while the
        # maintained mappings remain visible as comparison anchors.
        row["targets"] = added[:6] + existing + added[6:]
        row["marketwide_added"] = len(added)
        output.append(row)
    return output


def _market_item_for_ticker(ticker: str, market: dict) -> dict:
    for item in market.values():
        if item.get("ticker") == ticker:
            return item
    return {}


def _history(item: dict) -> list[dict]:
    return sorted(
        [dict(row) for row in item.get("history", []) if row.get("date") and _finite(row.get("close")) is not None],
        key=lambda row: row["date"],
    )


def _paired_history(target_item: dict, proxy_item: dict, horizons: list[int]) -> list[dict]:
    target = _history(target_item)
    proxy = _history(proxy_item)
    if len(target) < max(horizons, default=1) + 2 or len(proxy) < 10:
        return []
    proxy_dates = [row["date"] for row in proxy]
    pairs = []
    for index in range(1, len(target)):
        current = target[index]
        previous_close = _finite(target[index - 1].get("close"))
        opening = _finite(current.get("open"))
        if previous_close is None or previous_close <= 0 or opening is None or opening <= 0:
            continue
        proxy_index = bisect_left(proxy_dates, current["date"]) - 1
        if proxy_index < 0:
            continue
        proxy_move = _finite(proxy[proxy_index].get("return_pct"))
        if proxy_move is None:
            continue
        outcomes = {}
        for horizon in horizons:
            final_index = index + horizon - 1
            if final_index >= len(target):
                continue
            final_close = _finite(target[final_index].get("close"))
            if final_close is not None:
                outcomes[horizon] = (final_close / previous_close - 1) * 100
        if outcomes:
            pairs.append({
                "proxy_move": proxy_move,
                "open_gap": (opening / previous_close - 1) * 100,
                "outcomes": outcomes,
            })
    return pairs


def _empty_guidance(action: str, reason: str, horizon: str = "未判定") -> dict:
    return {
        "action": action, "max_gap_pct": None, "max_price": None,
        "fair_gap_low": None, "fair_gap_high": None, "overpriced_gap_pct": None,
        "required_probability": None, "sample_count": 0, "effective_sample": 0,
        "confidence": "不足", "primary_horizon": horizon, "horizons": [],
        "reason": reason,
        "method": "未达到动态阈值的最低数据要求，因此不提供固定百分比替代值。",
    }


def calibrate_preauction_guidance(signal: dict, target: dict, market: dict) -> dict:
    if signal.get("category") != "海外已验证":
        return _empty_guidance("等待验证", "海外价格尚未确认，08:45不提供集合竞价参与阈值。")
    beta = int(target.get("beta", 0) or 0)
    if beta == 0:
        return _empty_guidance("方向需判断", "该标的可能处于受益端或受损端，未核清方向前不提供买入阈值。")
    moves = sorted(signal.get("price_moves", []), key=lambda row: abs(_finite(row.get("move")) or 0), reverse=True)
    proxy = None
    proxy_move = None
    for move in moves:
        candidate = market.get(move.get("key"), {})
        if len(_history(candidate)) >= 20:
            proxy, proxy_move = candidate, _finite(move.get("move"))
            break
    if not proxy or proxy_move is None:
        return _empty_guidance("样本不足", "相关海外代理缺少可对齐的历史序列，无法量化最高可接受价格。")
    if proxy_move * beta <= 0:
        return _empty_guidance("不参与买入", "海外价格方向与该标的受益方向不一致，本次只作为风险提示。", "T+0风险")

    target_item = _market_item_for_ticker(target.get("ticker", ""), market)
    horizons = THEME_HORIZONS.get(signal.get("theme"), [1, 3, 5])
    pairs = _paired_history(target_item, proxy, horizons)
    same_direction = [row for row in pairs if row["proxy_move"] * proxy_move > 0]
    if len(same_direction) < MIN_HISTORY_PAIRS:
        return _empty_guidance("样本不足", f"只有{len(same_direction)}个同方向历史样本，低于最低要求{MIN_HISTORY_PAIRS}个。")

    scale = max(statistics.median(abs(row["proxy_move"]) for row in same_direction), 0.5)
    weights = [math.exp(-abs(abs(row["proxy_move"]) - abs(proxy_move)) / scale) for row in same_direction]
    effective = _effective_sample(weights)
    if effective < MIN_EFFECTIVE_SAMPLE:
        return _empty_guidance("样本不足", f"相似事件的有效样本量仅{effective:.1f}，不提供看似精确的阈值。")

    mapping_penalty = 0.06 if target.get("mapping_level") == "行业级候选" else 0.0
    evidence_penalty = max(0.0, (85 - int(signal.get("evidence") or 0)) / 100)
    required_probability = min(0.78, 0.62 + mapping_penalty + evidence_penalty)
    primary = horizons[0]
    horizon_stats = []
    for horizon in horizons:
        values, value_weights = [], []
        for row, weight in zip(same_direction, weights):
            if horizon in row["outcomes"]:
                values.append(row["outcomes"][horizon])
                value_weights.append(weight)
        if len(values) < MIN_HISTORY_PAIRS:
            continue
        median = _weighted_quantile(values, value_weights, 0.50)
        low = _weighted_quantile(values, value_weights, 0.25)
        high = _weighted_quantile(values, value_weights, 0.75)
        probability = sum(weight for value, weight in zip(values, value_weights) if value > ROUND_TRIP_COST_PCT) / sum(value_weights)
        horizon_stats.append({
            "days": horizon, "label": "T+0" if horizon == 1 else f"T+{horizon}",
            "median_return_pct": round(median, 2), "low_pct": round(low, 2), "high_pct": round(high, 2),
            "positive_probability": round(probability, 3), "sample_count": len(values),
        })
    if not horizon_stats:
        return _empty_guidance("样本不足", "没有任何持有期限达到最低历史样本要求。")
    primary_stat = max(horizon_stats, key=lambda row: (row["positive_probability"] - 0.015 * row["days"], row["median_return_pct"]))
    primary = primary_stat["days"]
    primary_values, primary_weights = [], []
    for row, weight in zip(same_direction, weights):
        if primary in row["outcomes"]:
            primary_values.append(row["outcomes"][primary])
            primary_weights.append(weight)
    raw_max_gap = (_weighted_quantile(primary_values, primary_weights, 1 - required_probability) or 0) - ROUND_TRIP_COST_PCT
    gaps = [row["open_gap"] for row in same_direction]
    fair_low = _weighted_quantile(gaps, weights, 0.25)
    fair_high = _weighted_quantile(gaps, weights, 0.75)
    gap_cap = _weighted_quantile(gaps, weights, 0.90)
    max_gap = min(raw_max_gap, gap_cap if gap_cap is not None else raw_max_gap)
    previous_close = _finite(target_item.get("last"))
    max_price = previous_close * (1 + max_gap / 100) if previous_close and max_gap > 0 else None
    confidence_score = min(100, int(signal.get("evidence") or 0) * 0.55 + min(effective, 35) + (0 if mapping_penalty else 10))
    confidence = "较高" if confidence_score >= 82 else "中等" if confidence_score >= 68 else "偏低"
    action = "可条件参与" if max_gap > 0 and primary_stat["positive_probability"] >= required_probability else "仅观察"
    reason = (
        f"以{proxy.get('name', proxy.get('ticker', '海外代理'))}同方向历史冲击为条件，"
        f"{primary_stat['label']}扣除成本后的历史正收益概率为{primary_stat['positive_probability']:.0%}。"
    )
    return {
        "action": action,
        "max_gap_pct": round(max_gap, 2) if max_gap > 0 else None,
        "max_price": round(max_price, 3) if max_price else None,
        "fair_gap_low": round(fair_low, 2) if fair_low is not None else None,
        "fair_gap_high": round(fair_high, 2) if fair_high is not None else None,
        "overpriced_gap_pct": round(max(fair_high or 0, gap_cap or 0, max_gap + max(0.5, abs(max_gap) * 0.5)), 2),
        "required_probability": round(required_probability, 3),
        "sample_count": len(same_direction), "effective_sample": round(effective, 1),
        "confidence": confidence, "primary_horizon": primary_stat["label"], "horizons": horizon_stats,
        "reason": reason,
        "method": "按该股近一年开盘/收盘历史，对齐上一海外交易日代理资产；以同方向且幅度相近的样本加权，阈值为达到所需胜率的条件分位数，已扣除0.18%成本缓冲。",
        "proxy_name": proxy.get("name", proxy.get("ticker", "")), "proxy_move": round(proxy_move, 2),
        "target_data_asof": target_item.get("asof", ""), "target_data_source": target_item.get("source", "Yahoo Finance"),
        "proxy_data_asof": proxy.get("asof", ""), "proxy_data_source": proxy.get("source", "Yahoo Finance"),
    }


def attach_dynamic_guidance(signals: Iterable[dict], market: dict) -> list[dict]:
    output = []
    for signal in signals:
        row = dict(signal)
        targets = []
        for target in signal.get("targets", []):
            item = dict(target)
            item["guidance"] = calibrate_preauction_guidance(signal, item, market)
            targets.append(item)
        row["targets"] = targets
        price_evidence = []
        for move in signal.get("price_moves", []):
            source_item = market.get(move.get("key"), {})
            percentile = move.get("tail_percentile")
            price_evidence.append(
                f"{move.get('name')} {move.get('move', 0):+.2f}%"
                + (f"，近一年{percentile:.0%}分位" if percentile is not None else "，历史分位不足")
                + f"；截至{source_item.get('asof') or '未取得'}；{source_item.get('source') or 'Yahoo Finance'}"
            )
        row["evidence_chain"] = [
            {"label": "原始事件", "value": signal.get("title", ""), "source": signal.get("source", ""), "url": signal.get("url", ""), "time": signal.get("published", "")},
            {"label": "来源证据", "value": f"{signal.get('evidence_label') or '未标注'}（{signal.get('evidence', 0)}/100）"},
            {"label": "海外价格", "value": "；".join(price_evidence) or signal.get("price_text", "暂无有效价格")},
            {"label": "传导机制", "value": signal.get("mechanism", "待核实")},
            {"label": "反方与失效", "value": signal.get("risk", "待核实")},
        ]
        output.append(row)
    return output


def detect_market_auction_anomalies(quotes: dict, limit: int = 24) -> list[dict]:
    rows = []
    for source in quotes.values():
        row = dict(source)
        name = str(row.get("name") or "").upper().replace(" ", "")
        gap = _finite(row.get("gap_pct"))
        # IPOs have no comparable prior-close distribution; ST shares have
        # different price limits. Mixing either into the ordinary cross-section
        # creates spectacular but unusable false positives.
        if (
            row.get("status") != "ok"
            or gap is None
            or "ST" in name
            or name.startswith(("N", "C"))
            or abs(gap) > 20
        ):
            continue
        rows.append(row)
    if len(rows) < 50:
        return []
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        group = (stock_board(row.get("ticker", "")), _size_bucket(row.get("float_market_cap") or row.get("market_cap")))
        groups[group].append(abs(float(row["gap_pct"])))
    overall = [abs(float(row["gap_pct"])) for row in rows]
    candidates = []
    for row in rows:
        group = (stock_board(row.get("ticker", "")), _size_bucket(row.get("float_market_cap") or row.get("market_cap")))
        reference = groups[group] if len(groups[group]) >= 20 else overall
        threshold = statistics.quantiles(reference, n=20, method="inclusive")[18]
        gap = float(row["gap_pct"])
        if abs(gap) < threshold:
            continue
        volume_ratio = max(_finite(row.get("volume_ratio")) or 0, 0)
        turnover = max(_finite(row.get("turnover_rate")) or 0, 0)
        score = abs(gap) / max(threshold, 0.01) + min(volume_ratio, 5) * 0.20 + min(turnover, 10) * 0.05
        near_limit = abs(gap) >= 9.5
        candidates.append({
            "ticker": row.get("ticker"), "name": row.get("name") or row.get("ticker"),
            "gap_pct": round(gap, 2), "auction_price": row.get("auction_price"),
            "amount": row.get("amount"), "turnover_rate": row.get("turnover_rate"), "volume_ratio": row.get("volume_ratio"),
            "board": group[0], "size_bucket": group[1], "dynamic_threshold_pct": round(threshold, 2),
            "score": round(score, 3), "status": "竞价独立异动", "primary_horizon": "T+0",
            "evidence_state": (
                "接近涨跌停，成交能力受限；只有横截面量价异常，不能作为追单依据。"
                if near_limit else
                "只有横截面量价异常，尚无可靠全球事件或公司新闻解释；不能直接视为买入信号。"
            ),
            "tradability": "接近涨跌停/可能无法成交" if near_limit else "需在开盘后复核流动性",
            "source": row.get("source", ""),
        })
    candidates.sort(key=lambda row: (-row["score"], row["ticker"]))
    return candidates[:limit]
