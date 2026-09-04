from core.briefing import build_a_share_mapping, morning_rule_brief, radar_rank
from core.market_context import enrich_macro_with_market_proxies, source_label
from core.theme_monitor import ai_chain_snapshot, theme_ledger_rows
from core.ontology import tag_modules, tag_themes
from core.climate import agriculture_transmission
from core.cn_mapping import cn_watch_rows

def fake_market():
    keys = ["SP500","NASDAQ","CSI300","HSI","NIKKEI","DXY","USDCNH","GOLD","COPPER","WTI","NATGAS","BTC",
            "NVDA","AVGO","AMD","SMH","MSFT","GOOGL","AMZN","META","ORCL","TSM","ASML","VRT","GRID","XLU","DLR","IGV",
            "FOXCONN","BABA","TCEHY","XLE"]
    out = {}
    for i, k in enumerate(keys):
        out[k] = {"name":k,"change_pct":0.2+i*0.01,"change_5d_pct":1+i*0.05,"change_20d_pct":2+i*0.1,
                  "last":100+i,"ret_z":0.5+i*0.01,"volume_ratio":1.1,"group":"stocks","theme":""}
    out["DXY"]["change_pct"] = -0.2
    return out

def fake_macro():
    vals = {"VIX":17,"HYSPREAD":3.2,"USREAL10Y":1.7,"BREAKEVEN10Y":2.3,"NFCI":-0.2,"US10Y":4.1}
    return {k:{"value":v,"delta":0.01,"unit":"%"} for k,v in vals.items()}

m = fake_market()
macro = fake_macro()
news = [{"title":"Hyperscalers raise AI capex for data centers and power","source":"Reuters","url":"https://example.com",
         "modules":["增长","实体瓶颈"],"themes":["AI资本开支"],"score":3.0,"bucket":"AI资本开支"}]

assert "实体瓶颈" in tag_modules("data center power grid copper")
assert "AI资本开支" in tag_themes("hyperscaler AI capex GPU")
brief = morning_rule_brief(m, macro, news)
assert len(brief["checklist"]) == 5
assert len(brief["focus"]) == 3
assert len(radar_rank(m, ["NVDA","MSFT"])) == 2
assert len(ai_chain_snapshot(m, macro)) >= 5
assert len(theme_ledger_rows(m, macro)) >= 4
enso={"status":"DEMO","nino34":"DEMO","mode":"demo"}
ag=agriculture_transmission(enso,m)
assert "ENSO" in ag["chain"] and len(ag["next_checks"])==5

cn = cn_watch_rows(news,m)
assert isinstance(cn,list)

proxy_market = dict(m)
proxy_market["US10Y_PROXY"] = {"last":42.5,"change_pct":0.2,"asof":"2026-09-01"}
proxy_market["VIX_MARKET"] = {"last":18.2,"change_pct":1.1,"asof":"2026-09-01"}
missing_macro = {"US10Y":{"value":float("nan"),"status":"unavailable"},"VIX":{"value":float("nan"),"status":"unavailable"},"USREAL10Y":{"value":float("nan"),"status":"unavailable"},"BREAKEVEN10Y":{"value":2.3,"status":"ok","date":"2026-09-01"}}
enriched = enrich_macro_with_market_proxies(missing_macro, proxy_market)
assert enriched["US10Y"]["value"] == 4.25
assert source_label(enriched["USREAL10Y"]) == "推导"
assert source_label({"status":"treasury"}) == "美国财政部"

mapping = {"测试":{"trigger_assets":["MISSING"],"global_assets":[],"a_share_themes":[],"logic":"x","verify":[]}}
rows = build_a_share_mapping({"MISSING":{"change_pct":float("nan")}}, news, mapping)
assert rows[0]["score"] == 0.0 and rows[0]["pricing"] == "尚未确认"
print("SMOKE_TEST_OK")
