from __future__ import annotations

import math
import statistics


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _mean_market(market, keys, field="change_20d_pct"):
    values = [_finite(market.get(key, {}).get(field)) for key in keys]
    values = [value for value in values if value is not None]
    return statistics.fmean(values) if values else None


AI_CHAIN = [
    ("需求", ["MSFT", "GOOGL", "AMZN", "META"], "Hyperscaler资本开支与收入指引"),
    ("算力", ["NVDA", "AVGO", "AMD", "SMH"], "GPU/ASIC、HBM和先进封装"),
    ("网络", ["ZHONGJI", "EOPTOLINK", "WUS"], "光模块、交换与PCB"),
    ("电力", ["VRT", "GRID", "XLU", "XD", "TBEA"], "并网、变压器、冷却与供电"),
    ("原料", ["COPPER", "ZIJIN", "CMOC"], "铜库存、升贴水与矿端供给"),
    ("融资", ["DLR", "HYG", "LQD"], "REIT、信用和资本成本"),
]


def ai_chain_snapshot(market, macro=None):
    rows = []
    for stage, keys, verifier in AI_CHAIN:
        change = _mean_market(market, keys)
        rows.append({"环节": stage, "价格代理": " · ".join(keys), "20日代理变化%": change,
                     "信号": "扩张" if change is not None and change >= 3 else "承压" if change is not None and change <= -3 else "分化/中性",
                     "下一验证": verifier})
    return rows


def ai_chain_bottlenecks(market, macro=None):
    rows = ai_chain_snapshot(market, macro)
    valid = [row for row in rows if row["20日代理变化%"] is not None]
    if not valid:
        return ["价格数据不足，暂时无法识别AI资本开支链条中的定价瓶颈。"]
    strongest = max(valid, key=lambda row: row["20日代理变化%"])
    weakest = min(valid, key=lambda row: row["20日代理变化%"])
    output = [f"最强确认：{strongest['环节']}（20日代理 {strongest['20日代理变化%']:+.2f}%）。",
              f"最弱环节：{weakest['环节']}（20日代理 {weakest['20日代理变化%']:+.2f}%），优先核实是否为真实瓶颈或仅是价格滞后。"]
    if strongest["20日代理变化%"] - weakest["20日代理变化%"] >= 8:
        output.append("链条离散度较高：当前更像局部定价，而不是完整AI Capex扩散。")
    return output


def theme_ledger_rows(market, macro=None):
    return [
        {"主题": "AI芯片 → 电力基础设施", "核心假设": "Capex从算力扩散至电力、电网和铜", "20日资产确认%": _mean_market(market, ["SMH", "VRT", "GRID", "COPPER"]), "反证": "芯片强而电力/铜持续走弱"},
        {"主题": "美元流动性", "核心假设": "美元走弱与信用稳定支持风险资产", "20日资产确认%": _mean_market(market, ["SP500", "BTC", "HYG"]), "反证": "美元与实际利率上升、信用恶化"},
        {"主题": "能源安全溢价", "核心假设": "油价冲击向通胀和行业利润传导", "20日资产确认%": _mean_market(market, ["WTI", "BRENT", "XLE"]), "反证": "原油曲线与能源股不确认"},
        {"主题": "中国风险偏好", "核心假设": "人民币与港股改善向A股传导", "20日资产确认%": _mean_market(market, ["HSI", "BABA", "CSI300"]), "反证": "人民币走弱且A股成交/指数不确认"},
    ]
