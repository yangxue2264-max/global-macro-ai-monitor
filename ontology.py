from __future__ import annotations

from urllib.parse import urlparse


MACRO_MODULES = {
    "增长": {"question": "增长预期在改善还是恶化？", "items": ["股指广度", "铜与周期品", "就业与PMI"], "keywords": ["growth", "gdp", "jobs", "employment", "pmi", "recession", "增长", "就业"]},
    "通胀": {"question": "价格压力来自需求还是供给？", "items": ["盈亏平衡通胀", "油价", "工资与食品"], "keywords": ["inflation", "cpi", "ppi", "wage", "通胀", "物价"]},
    "货币政策": {"question": "政策路径相对预期有何变化？", "items": ["央行表态", "政策利率", "收益率曲线"], "keywords": ["federal reserve", "fed", "ecb", "pboc", "rate cut", "rate hike", "央行", "降息", "加息"]},
    "金融状况": {"question": "美元、实际利率与信用是否共振？", "items": ["美元", "实际利率", "信用利差", "波动率"], "keywords": ["dollar", "yield", "credit", "liquidity", "vix", "美元", "利率", "流动性"]},
    "财政与监管": {"question": "政策如何改变现金流与风险溢价？", "items": ["财政支出", "税收", "关税", "监管"], "keywords": ["fiscal", "tariff", "regulation", "sanction", "关税", "监管", "财政"]},
    "地缘与供应链": {"question": "冲击卡在哪个物理或制度节点？", "items": ["航运", "出口管制", "能源通道", "库存"], "keywords": ["war", "conflict", "export control", "supply chain", "shipping", "战争", "出口限制", "供应链"]},
    "实体瓶颈": {"question": "资本开支最终受什么约束？", "items": ["电力", "电网", "芯片", "原料", "产能"], "keywords": ["data center", "power", "grid", "copper", "capacity", "semiconductor", "电力", "电网", "铜", "产能"]},
}


THEMES = {
    "AI资本开支": {
        "keywords": ["ai", "artificial intelligence", "gpu", "hyperscaler", "data center", "semiconductor", "算力", "数据中心", "人工智能", "芯片"],
        "mechanism": "AI需求与Capex → 芯片/网络 → 数据中心供电与并网 → 铜与设备 → 海外及A股硬件链",
        "assets": ["SMH", "VRT", "GRID", "COPPER", "工业富联", "中际旭创"],
    },
    "流动性与信用": {
        "keywords": ["liquidity", "credit", "yield", "bond", "dollar", "financial conditions", "流动性", "信用", "利率", "美元"],
        "mechanism": "美元/实际利率/信用 → 全球金融条件 → 风险溢价与估值 → 人民币及A股风格",
        "assets": ["DXY", "USREAL10Y", "HYG", "USD/CNH", "成长股"],
    },
    "油价与通胀": {
        "keywords": ["oil", "opec", "crude", "energy", "inflation", "原油", "油价", "能源", "通胀"],
        "mechanism": "原油供需/通道 → 能源与运输成本 → 通胀和政策预期 → 上游与成本敏感行业分化",
        "assets": ["WTI", "BRENT", "GOLD", "石油石化", "航空", "化工"],
    },
    "天气与农业": {
        "keywords": ["weather", "el nino", "la nina", "enso", "corn", "soy", "agriculture", "天气", "厄尔尼诺", "农业", "玉米", "大豆"],
        "mechanism": "ENSO/天气 → 单产与物流 → 农产品价格 → 食品通胀 → 农业链利润与政策预期",
        "assets": ["CORN", "SOY", "种业", "化肥", "食品"],
    },
    "贸易与关税": {
        "keywords": ["tariff", "trade", "export control", "sanction", "关税", "贸易", "出口管制", "制裁"],
        "mechanism": "贸易规则/关税 → 数量与成本 → 企业利润和供应链迁移 → 汇率与相关行业估值",
        "assets": ["USD/CNH", "TSM", "BABA", "出口制造"],
    },
    "黄金与美元信用": {
        "keywords": ["gold", "central bank buying", "reserve", "de-dollar", "黄金", "央行购金", "储备", "去美元化"],
        "mechanism": "实际利率/美元/储备需求/地缘风险 → 黄金定价 → 国内金价与矿企盈利弹性",
        "assets": ["GOLD", "DXY", "黄金矿业"],
    },
    "中国增长与政策": {
        "keywords": ["china", "pboc", "yuan", "property", "stimulus", "中国", "人民银行", "人民币", "地产", "政策刺激"],
        "mechanism": "中国政策与增长预期 → 人民币/信用/商品需求 → 港股与A股风险偏好及行业轮动",
        "assets": ["CSI300", "HSI", "USD/CNH", "COPPER"],
    },
}


TRUSTED_DOMAINS = {
    "federalreserve.gov": 3.0,
    "home.treasury.gov": 3.0,
    "fred.stlouisfed.org": 3.0,
    "imf.org": 2.8,
    "bis.org": 2.8,
    "worldbank.org": 2.8,
    "reuters.com": 2.5,
    "bloomberg.com": 2.4,
    "ft.com": 2.3,
    "wsj.com": 2.2,
    "cnbc.com": 2.0,
}


def _match(text, keywords):
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def tag_modules(text):
    return [name for name, meta in MACRO_MODULES.items() if _match(text, meta["keywords"])] or ["待分类"]


def tag_themes(text):
    return [name for name, meta in THEMES.items() if _match(text, meta["keywords"])] or ["待分类"]


def find_theme(text):
    tags = tag_themes(text)
    return tags[0] if tags and tags[0] != "待分类" else "待分类"


def source_domain(url):
    return urlparse(url or "").netloc.lower().replace("www.", "")
