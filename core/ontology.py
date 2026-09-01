from __future__ import annotations

MACRO_MODULES = {
    "增长": {
        "question": "经济活动是在加速还是减速？AI资本开支是否正在改变增长结构？",
        "items": ["GDP/Nowcast", "就业", "消费", "Capex", "生产率", "产出缺口"],
        "keywords": ["gdp", "growth", "jobs", "employment", "unemployment", "pmi", "consumption", "capex", "productivity", "recession", "增长", "就业", "消费", "资本开支", "生产率"]
    },
    "金融状况": {
        "question": "资金价格、风险溢价和杠杆是否在放松或收紧？",
        "items": ["实际利率", "信用利差", "VIX", "美元", "流动性", "私人信贷", "市场杠杆"],
        "keywords": ["fed", "yield", "real yield", "credit spread", "liquidity", "vix", "private credit", "leverage", "美元", "利率", "信用", "流动性"]
    },
    "政策": {
        "question": "政策正在改变谁的成本、收入或竞争格局？",
        "items": ["货币政策", "财政/补贴", "产业政策", "监管", "关税", "出口管制"],
        "keywords": ["tariff", "subsidy", "fiscal", "regulation", "export control", "sanction", "industrial policy", "关税", "补贴", "财政", "监管", "出口管制", "产业政策"]
    },
    "全球化": {
        "question": "贸易、资本和技术跨境流动是否发生结构变化？",
        "items": ["芯片供应链", "跨境资本", "国际竞争", "AI服务出口", "美元体系"],
        "keywords": ["trade", "supply chain", "cross-border", "semiconductor", "chip export", "dollar system", "贸易", "供应链", "跨境", "芯片"]
    },
    "资产配置": {
        "question": "当前回报来自现金流、贴现率还是风险溢价？跨资产之间有什么共振或背离？",
        "items": ["股债相关性", "实际利率", "风险溢价", "黄金/商品", "区域轮动", "轻重资产"],
        "keywords": ["asset allocation", "equity", "bond", "gold", "commodity", "risk premium", "rotation", "资产配置", "股票", "债券", "黄金", "商品"]
    },
    "实体瓶颈": {
        "question": "资本开支是否撞上物理世界的约束？",
        "items": ["电力", "电网", "数据中心", "铜", "天然气", "土地与水", "技能"],
        "keywords": ["power", "grid", "electricity", "data center", "copper", "natural gas", "water", "land", "电力", "电网", "数据中心", "铜", "天然气", "用水"]
    },
    "社会与分配": {
        "question": "技术和价格变化如何重新分配收入、就业和政治压力？",
        "items": ["收入分配", "就业替代", "工资", "食品通胀", "社会情绪", "政策反应"],
        "keywords": ["wage", "inequality", "automation jobs", "food inflation", "social", "income distribution", "工资", "收入分配", "就业替代", "食品通胀"]
    }
}

THEMES = {
    "AI资本开支": {
        "keywords": ["ai capex", "data center", "gpu", "hyperscaler", "nvidia", "cloud capex", "人工智能", "算力", "数据中心", "资本开支"],
        "assets": ["NVDA", "AVGO", "AMD", "MSFT", "GOOGL", "AMZN", "META", "TSM", "ASML", "VRT", "COPPER", "NATGAS"],
        "mechanism": "AI需求 → 云厂商/模型厂商资本开支 → GPU/网络/服务器 → 数据中心、电网、铜与能源 → 企业现金流/融资 → GDP与资产定价"
    },
    "天气与农业": {
        "keywords": ["el nino", "la nina", "weather", "drought", "flood", "crop", "厄尔尼诺", "拉尼娜", "干旱", "洪水", "农作物"],
        "assets": ["CORN", "SOY", "WTI", "GOLD"],
        "mechanism": "气候异常 → 单产/运输/水电 → 农产品与能源价格 → 食品/能源通胀 → 企业利润和政策预期 → 农业链与利率资产"
    },
    "贸易与关税": {
        "keywords": ["tariff", "trade war", "export control", "sanction", "关税", "贸易战", "出口管制", "制裁"],
        "assets": ["DXY", "USDCNH", "TSM", "ASML", "BABA", "TCEHY"],
        "mechanism": "贸易限制 → 进口成本/供应链迁移 → 企业利润与通胀 → 政策反应与汇率 → 区域/行业相对收益"
    },
    "油价与通胀": {
        "keywords": ["oil", "opec", "brent", "wti", "energy inflation", "原油", "油价", "欧佩克", "能源通胀"],
        "assets": ["WTI", "BRENT", "DXY", "GOLD"],
        "mechanism": "油价 → 能源CPI/运输成本 → 通胀预期/居民实际收入 → 央行反应 → 股债汇与能源行业"
    },
    "流动性与信用": {
        "keywords": ["liquidity", "credit spread", "private credit", "bond issuance", "funding", "流动性", "信用利差", "私人信贷", "融资"],
        "assets": ["SP500", "NASDAQ", "DXY", "BTC", "GOLD"],
        "mechanism": "融资条件 → 杠杆/估值/风险偏好 → 资本开支与并购 → 资产价格 → 财富效应和实体经济"
    }
}

TRUSTED_DOMAINS = {
    "reuters.com": 3.0, "bloomberg.com": 3.0, "ft.com": 2.8, "wsj.com": 2.8,
    "cnbc.com": 1.8, "federalreserve.gov": 3.5, "ecb.europa.eu": 3.5,
    "imf.org": 3.2, "worldbank.org": 3.0, "bis.org": 3.2,
    "pbc.gov.cn": 3.5, "gov.cn": 3.3
}

def tag_modules(text: str):
    t = (text or "").lower()
    hits = []
    for name, cfg in MACRO_MODULES.items():
        n = sum(1 for kw in cfg["keywords"] if kw.lower() in t)
        if n:
            hits.append((name, n))
    return [x[0] for x in sorted(hits, key=lambda z: z[1], reverse=True)]

def tag_themes(text: str):
    t = (text or "").lower()
    hits = []
    for name, cfg in THEMES.items():
        n = sum(1 for kw in cfg["keywords"] if kw.lower() in t)
        if n:
            hits.append((name, n))
    return [x[0] for x in sorted(hits, key=lambda z: z[1], reverse=True)]

def find_theme(text: str):
    tagged = tag_themes(text)
    return tagged[0] if tagged else None
