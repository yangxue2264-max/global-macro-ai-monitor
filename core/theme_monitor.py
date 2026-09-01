from __future__ import annotations
import numpy as np

AI_CHAIN = [
    ("需求/平台", ["MSFT","GOOGL","AMZN","META","ORCL"]),
    ("GPU/半导体", ["NVDA","AVGO","AMD","TSM","ASML","SMH"]),
    ("服务器/电力设备", ["FOXCONN","VRT","GRID"]),
    ("数据中心/公用事业", ["DLR","XLU"]),
    ("实体原料", ["COPPER","NATGAS","WTI"]),
    ("融资/贴现率", [])
]

def _mean(market, keys, field="change_20d_pct"):
    vals = []
    for k in keys:
        try:
            v = float(market[k][field])
            if not np.isnan(v):
                vals.append(v)
        except Exception:
            pass
    return float(np.mean(vals)) if vals else np.nan

def ai_chain_snapshot(market, macro):
    rows = []
    for layer, keys in AI_CHAIN:
        if layer == "融资/贴现率":
            try:
                real = float(macro["USREAL10Y"]["value"])
            except Exception:
                real = np.nan
            try:
                hy = float(macro["HYSPREAD"]["value"])
            except Exception:
                hy = np.nan
            parts = []
            if not np.isnan(real):
                parts.append(-(real - 1.5) * 5)
            if not np.isnan(hy):
                parts.append(-(hy - 4.0) * 3)
            perf = float(np.mean(parts)) if parts else np.nan
            members = "美国实际10Y / HY OAS"
        else:
            perf = _mean(market, keys)
            members = " · ".join(market.get(k, {}).get("name", k) for k in keys)

        if np.isnan(perf):
            state = "暂无"
        elif perf >= 5:
            state = "强"
        elif perf <= -5:
            state = "弱"
        else:
            state = "中性"

        rows.append({
            "链条": layer,
            "20日代理变化%": perf,
            "状态": state,
            "代理资产": members
        })
    return rows

def ai_chain_bottlenecks(market, macro):
    notes = []
    def d20(k):
        try:
            return float(market[k]["change_20d_pct"])
        except Exception:
            return np.nan

    semis = _mean(market, ["NVDA","AVGO","AMD","SMH"])
    grid = _mean(market, ["VRT","GRID","XLU"])
    copper = d20("COPPER")
    gas = d20("NATGAS")
    software = _mean(market, ["IGV","MSFT","GOOGL"])

    if not np.isnan(semis) and not np.isnan(grid) and semis > 8 and grid > 5:
        notes.append("算力与电力/电网同时走强：市场在交易AI资本开支向物理基础设施扩散。")
    if not np.isnan(copper) and copper > 8:
        notes.append("铜20日明显走强：需要区分AI/电网结构性需求、美元因素与传统全球增长因子。")
    if not np.isnan(gas) and gas > 12:
        notes.append("天然气显著走强：若同时出现数据中心电力需求叙事，需验证发电燃料端是否成为二阶约束。")
    if not np.isnan(semis) and not np.isnan(software) and semis - software > 10:
        notes.append("半导体显著跑赢软件：AI价值链仍偏重资本开支/基础设施，软件盈利兑现相对不足。")
    if not notes:
        notes.append("AI链暂未出现极端共振；继续观察“算力→电力/电网→铜/能源→融资成本”的扩散顺序。")
    return notes

THEME_LEDGER = {
    "AI资本开支": {
        "question":"AI投资是否从芯片扩散到电力、铜、数据中心，并最终转化为可持续现金流？",
        "leading":["Hyperscaler Capex指引","半导体/服务器相对收益","铜与电网代理","电力/天然气","实际利率与信用融资"],
        "assets":["NVDA","SMH","VRT","GRID","XLU","DLR","COPPER","NATGAS"],
        "invalidate":"Capex指引下修、芯片需求转弱、实体约束资产不再确认、自由现金流恶化且融资成本上升。"
    },
    "流动性与信用": {
        "question":"风险资产上涨是现金流改善，还是金融条件宽松推动的估值扩张？",
        "leading":["DXY","VIX","HY OAS","NFCI","实际利率","BTC"],
        "assets":["SP500","NASDAQ","BTC","GOLD","DXY"],
        "invalidate":"股价上涨同时信用利差持续扩大、美元和实际利率同步急升。"
    },
    "天气与农业": {
        "question":"气候事件是否足以改变单产、库存与食品通胀，而不是短期标题噪声？",
        "leading":["ENSO概率","主产区天气","库存消费比","农产品期货曲线","食品CPI"],
        "assets":["CORN","SOY","GOLD"],
        "invalidate":"主产区天气改善、库存缓冲充足、期货曲线不确认供给冲击。"
    },
    "贸易与关税": {
        "question":"贸易政策冲击最终落在价格、利润率、供应链迁移还是汇率？",
        "leading":["关税覆盖范围","企业转嫁能力","贸易量","供应链投资","USD/CNH"],
        "assets":["USDCNH","DXY","TSM","ASML","BABA","TCEHY"],
        "invalidate":"豁免范围扩大、企业吸收成本、贸易量和供应链数据不支持冲击扩大。"
    },
    "油价与通胀": {
        "question":"油价是供给冲击还是需求走强？它会不会进入核心通胀和政策反应？",
        "leading":["OPEC+","库存","期限结构","裂解价差","通胀预期"],
        "assets":["WTI","BRENT","XLE","GOLD","DXY"],
        "invalidate":"库存累积、期限结构转弱、通胀预期没有跟随。"
    }
}

def theme_ledger_rows(market, macro):
    out = []
    for name, cfg in THEME_LEDGER.items():
        perf = _mean(market, [k for k in cfg["assets"] if k in market])
        out.append({
            "主题": name,
            "20日资产确认%": perf,
            "核心问题": cfg["question"],
            "领先验证": "；".join(cfg["leading"]),
            "反证": cfg["invalidate"]
        })
    return out
