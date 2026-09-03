from __future__ import annotations

import math
import statistics


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _values(market, keys, field="change_20d_pct"):
    values = [_finite(market.get(key, {}).get(field)) for key in keys]
    return [value for value in values if value is not None]


def _median(values):
    return statistics.median(values) if values else None


def _mean_abs(values):
    return statistics.fmean(abs(value) for value in values) if values else None


def _direction(value):
    if value is None:
        return "数据不足"
    if value >= 1.5:
        return "上行"
    if value <= -1.5:
        return "下行"
    return "横盘"


def cross_market_gaps(market, news, mapping_cfg):
    """Rank themes by evidence, price impulse, China relevance and pricing gap.

    The score is a research-priority score, not an expected-return forecast.
    """
    rows = []
    for name, cfg in mapping_cfg.items():
        linked = [item for item in news if name in item.get("themes", [])]
        evidence = max([_finite(item.get("evidence_score")) or 0 for item in linked] or [0])
        global_keys = list(dict.fromkeys(cfg.get("trigger_assets", []) + cfg.get("global_assets", [])))
        china_keys = cfg.get("a_share_assets", [])
        global_values = _values(market, global_keys)
        china_values = _values(market, china_keys)
        global_median, china_median = _median(global_values), _median(china_values)
        global_strength, china_strength = _mean_abs(global_values), _mean_abs(china_values)
        gap = None if global_strength is None or china_strength is None else global_strength - china_strength

        same_direction = (
            global_median is not None and china_median is not None
            and (abs(global_median) < 1.0 or abs(china_median) < 1.0 or global_median * china_median > 0)
        )
        if global_strength is None:
            status = "数据不足"
        elif global_strength < 1.5 and not linked:
            status = "低活跃"
        elif china_strength is None:
            status = "待补A股代理"
        elif not same_direction:
            status = "方向背离"
        elif gap is not None and gap >= 3.0:
            status = "关注缺口"
        elif gap is not None and gap <= -3.0:
            status = "A股先行"
        else:
            status = "同步确认"

        relevance = min(max(float(cfg.get("china_relevance", 2)), 0), 3) / 3
        event_component = evidence / 100
        move_component = min((global_strength or 0) / 8, 1)
        gap_component = min(abs(gap or 0) / 8, 1)
        priority = round(100 * (0.30 * event_component + 0.25 * move_component + 0.25 * gap_component + 0.20 * relevance))
        if linked:
            priority = min(100, priority + min(len(linked), 3) * 3)

        rows.append({
            "name": name,
            "priority": priority,
            "status": status,
            "global_median": global_median,
            "china_median": china_median,
            "global_strength": global_strength,
            "china_strength": china_strength,
            "gap": gap,
            "global_direction": _direction(global_median),
            "china_direction": _direction(china_median),
            "evidence": int(evidence),
            "event_count": len(linked),
            "top_event": linked[0] if linked else None,
            "logic": cfg.get("logic", ""),
            "question": cfg.get("question", f"{name}是否出现新的跨市场定价差？"),
            "verify": cfg.get("verify", []),
            "invalidation": cfg.get("invalidation", "相关价格与基本面数据持续不确认。"),
            "a_share_themes": cfg.get("a_share_themes", []),
            "global_assets": global_keys,
            "a_share_assets": china_keys,
            "score_breakdown": {
                "证据": round(event_component * 30),
                "海外异动": round(move_component * 25),
                "定价缺口": round(gap_component * 25),
                "A股相关性": round(relevance * 20),
            },
        })
    return sorted(rows, key=lambda row: row["priority"], reverse=True)


def decision_queue(market, news, mapping_cfg, limit=3):
    rows = cross_market_gaps(market, news, mapping_cfg)[:limit]
    for row in rows:
        g = "—" if row["global_median"] is None else f"{row['global_median']:+.2f}%"
        c = "—" if row["china_median"] is None else f"{row['china_median']:+.2f}%"
        row["now"] = f"海外代理20日中位数 {g}；A股代理 {c}；状态：{row['status']}"
        row["next_check"] = "；".join(row["verify"][:2]) or "核对原始来源与下一项基本面数据"
    return rows


def _lookup_value(rule, market, macro):
    source = market if rule.get("source", "market") == "market" else macro
    return _finite(source.get(rule["key"], {}).get(rule.get("field", "change_20d_pct")))


def _passes(value, operator, threshold):
    if value is None:
        return None
    return {
        ">": value > threshold,
        ">=": value >= threshold,
        "<": value < threshold,
        "<=": value <= threshold,
    }.get(operator)


def evaluate_theses(market, macro, thesis_cfg):
    rows = []
    for thesis in thesis_cfg:
        checks = []
        for rule in thesis.get("rules", []):
            value = _lookup_value(rule, market, macro)
            passed = _passes(value, rule.get("op", ">="), float(rule.get("value", 0)))
            checks.append({**rule, "observed": value, "passed": passed})
        known = [check for check in checks if check["passed"] is not None]
        pass_ratio = sum(check["passed"] for check in known) / len(known) if known else None
        if pass_ratio is None:
            status = "待数据"
        elif pass_ratio >= 0.75:
            status = "获得确认"
        elif pass_ratio <= 0.25:
            status = "受到挑战"
        else:
            status = "证据混合"
        rows.append({**thesis, "checks": checks, "pass_ratio": pass_ratio, "status": status})
    return rows


def one_page_markdown(brief, gaps, theses, now_text):
    lines = [
        "# Global-to-A Share Decision Brief",
        "",
        f"**生成时间：** {now_text}",
        f"**市场状态：** {brief['regime']}（{brief['regime_score']:+.2f}）",
        f"**一句话判断：** {brief['headline']}",
        "",
        "## 今日决策队列",
    ]
    for index, row in enumerate(gaps[:3], 1):
        lines += [
            f"### {index}. {row['question']}",
            f"- 当前证据：{row['now']}",
            f"- 传导：{row['logic']}",
            f"- A股观察：{'、'.join(row['a_share_themes'])}",
            f"- 下一验证：{row['next_check']}",
            f"- 反证：{row['invalidation']}",
        ]
    lines += ["", "## 主题账本"]
    for row in theses:
        ratio = "—" if row["pass_ratio"] is None else f"{row['pass_ratio']:.0%}"
        lines.append(f"- **{row['name']}**：{row['status']}（规则通过 {ratio}）；反证：{row['invalidation']}")
    lines += ["", "## 使用边界", "研究优先级与跨市场验证工具，不构成投资建议。分数不代表预期收益。"]
    return "\n".join(lines)
