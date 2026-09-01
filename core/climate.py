from __future__ import annotations
import html
import re
import requests

HEADERS = {"User-Agent":"Mozilla/5.0 (GlobalMacroAIMonitor/0.7; research use)"}
ENSO_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.html"

def _clean_html(raw):
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def fetch_enso_summary():
    try:
        r = requests.get(ENSO_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = _clean_html(r.text)

        status = ""
        m = re.search(r"ENSO Alert System Status:\s*([^\.]+?)(?:Synopsis:|$)", text, flags=re.I)
        if m:
            status = m.group(1).strip(" :-")

        synopsis = ""
        m = re.search(r"Synopsis:\s*(.+?)(?:In the past month|During the last month|El Niño|La Niña|The next ENSO)", text, flags=re.I)
        if m:
            synopsis = m.group(1).strip()
        if not synopsis:
            m = re.search(r"Synopsis:\s*(.{0,600}?)(?:The next ENSO|This discussion)", text, flags=re.I)
            if m:
                synopsis = m.group(1).strip()

        nino34 = ""
        m = re.search(r"Niño-3\.4 index value was\s*([+\-]?\d+(?:\.\d+)?)°?C", text, flags=re.I)
        if m:
            nino34 = m.group(1) + "°C"

        # Extract the first forward-looking probability sentence if available.
        probability = ""
        for pat in [
            r"greater than\s+\d+%\s+chance[^\.]*\.",
            r"\d+%\s+chance[^\.]*\.",
            r"El Niño is likely[^\.]*\.",
            r"La Niña is likely[^\.]*\."
        ]:
            m = re.search(pat, text, flags=re.I)
            if m:
                probability = m.group(0).strip()
                break

        return {
            "status": status or "已获取NOAA页面，状态字段未解析",
            "synopsis": synopsis[:700] if synopsis else "NOAA页面已获取，但摘要字段未稳定解析。",
            "nino34": nino34 or "—",
            "probability": probability or "—",
            "url": ENSO_URL,
            "provider":"NOAA Climate Prediction Center",
            "mode":"live"
        }
    except Exception:
        return {
            "status":"DEMO · El Niño / La Niña 状态待联网读取",
            "synopsis":"部署后系统会直接读取 NOAA CPC 官方 ENSO Diagnostic Discussion，并将天气风险映射到农产品、食品通胀与相关资产。",
            "nino34":"DEMO",
            "probability":"DEMO",
            "url":ENSO_URL,
            "provider":"NOAA Climate Prediction Center",
            "mode":"demo"
        }

def agriculture_transmission(enso, market):
    corn = market.get("CORN",{}).get("change_20d_pct")
    soy = market.get("SOY",{}).get("change_20d_pct")
    try: corn_s=f"{float(corn):+.2f}%"
    except Exception: corn_s="—"
    try: soy_s=f"{float(soy):+.2f}%"
    except Exception: soy_s="—"

    return {
        "chain":"ENSO/天气异常 → 主要产区温度与降雨 → 单产/物流 → 玉米/大豆等农产品价格 → 食品通胀 → 企业利润与利率预期",
        "market_check":f"当前价格验证代理：玉米20日 {corn_s}；大豆20日 {soy_s}",
        "next_checks":[
            "NOAA/CPC ENSO概率与Niño-3.4",
            "美国、巴西、阿根廷等主产区降雨/温度异常",
            "USDA库存、产量与库存消费比",
            "农产品期货曲线与隐含波动率",
            "食品CPI与农业投入品价格"
        ]
    }
