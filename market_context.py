from __future__ import annotations

import math


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _macro_ok(macro, key):
    return _finite(macro.get(key, {}).get("value")) is not None


def enrich_macro_with_market_proxies(macro, market, treasury=None):
    """Fill only missing macro observations and label every proxy explicitly."""
    out = {key: dict(value) for key, value in macro.items()}
    treasury = treasury or {}

    # Prefer FRED when available; otherwise use the official Treasury curve.
    for key in ["US10Y", "US2Y", "USREAL10Y", "BREAKEVEN10Y"]:
        if not _macro_ok(out, key) and key in treasury:
            out[key] = dict(treasury[key])

    if not _macro_ok(out, "US10Y"):
        tnx = _finite(market.get("US10Y_PROXY", {}).get("last"))
        if tnx is not None:
            out["US10Y"].update(
                value=tnx / 10.0,
                delta=(_finite(market.get("US10Y_PROXY", {}).get("change_pct")) or 0.0),
                date=market.get("US10Y_PROXY", {}).get("asof", ""),
                status="market_proxy",
                source="Yahoo ^TNX / 10",
            )

    if not _macro_ok(out, "VIX"):
        vix = _finite(market.get("VIX_MARKET", {}).get("last"))
        if vix is not None:
            out["VIX"].update(
                value=vix,
                delta=_finite(market.get("VIX_MARKET", {}).get("change_pct")) or 0.0,
                date=market.get("VIX_MARKET", {}).get("asof", ""),
                status="market_proxy",
                source="Yahoo ^VIX",
            )

    if not _macro_ok(out, "USREAL10Y"):
        nominal = _finite(out.get("US10Y", {}).get("value"))
        breakeven = _finite(out.get("BREAKEVEN10Y", {}).get("value"))
        if nominal is not None and breakeven is not None:
            out["USREAL10Y"].update(
                value=nominal - breakeven,
                delta=0.0,
                date=max(out.get("US10Y", {}).get("date", ""), out.get("BREAKEVEN10Y", {}).get("date", "")),
                status="derived",
                source="美国10Y − 10Y盈亏平衡通胀",
            )

    # An ETF-relative signal is not an OAS level, so it is stored separately
    # and never presented as an official credit spread.
    hyg = _finite(market.get("HYG", {}).get("change_20d_pct"))
    lqd = _finite(market.get("LQD", {}).get("change_20d_pct"))
    out["CREDIT_PROXY"] = {
        "name": "信用风险市场代理",
        "value": (hyg - lqd) if hyg is not None and lqd is not None else float("nan"),
        "delta": float("nan"),
        "date": market.get("HYG", {}).get("asof", ""),
        "unit": "HYG-LQD 20日百分点",
        "status": "market_proxy" if hyg is not None and lqd is not None else "unavailable",
        "source": "HYG相对LQD的20日表现",
    }
    return out


def source_label(item):
    status = item.get("status", "unavailable")
    return {
        "ok": "官方",
        "treasury": "美国财政部",
        "market_proxy": "市场代理",
        "derived": "推导",
        "saved": "最近快照",
        "demo": "演示",
    }.get(status, "缺失")
