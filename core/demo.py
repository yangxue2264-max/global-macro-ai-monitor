from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

CN = ZoneInfo("Asia/Shanghai")

def demo_market(universe):
    # Synthetic values for UI resilience only. They are intentionally labelled DEMO.
    seed = {
        "SP500":(6500,0.42,2.4),"NASDAQ":(23800,0.68,3.6),"CSI300":(4100,-0.25,1.1),
        "SSE":(3700,-0.12,0.8),"CHINEXT":(2550,0.33,2.2),"HSI":(25200,-0.70,-1.4),
        "NIKKEI":(51200,0.55,4.1),"KOSPI":(3300,1.15,3.2),"STOXX50":(5600,0.12,1.3),
        "DXY":(98.8,-0.18,-1.1),"USDCNH":(7.08,0.08,0.6),"USDJPY":(149.2,-0.12,-0.8),
        "EURUSD":(1.17,0.15,1.0),"GOLD":(3580,0.61,5.3),"SILVER":(42.0,0.8,6.1),
        "COPPER":(4.72,1.08,9.2),"WTI":(76.3,-0.52,-3.0),"BRENT":(80.1,-0.40,-2.4),
        "NATGAS":(3.3,0.75,8.4),"CORN":(475,0.30,2.2),"SOY":(1060,-0.15,1.0),
        "BTC":(112000,1.20,7.5),"NVDA":(178,1.9,12.0),"AVGO":(338,1.2,10.0),
        "AMD":(188,1.0,9.0),"MSFT":(525,0.4,4.0),"GOOGL":(206,0.6,5.0),"AMZN":(238,0.5,4.5),
        "META":(785,0.7,6.0),"ORCL":(255,1.1,8.0),"TSM":(270,1.4,11.0),"ASML":(880,0.8,7.5),
        "VRT":(142,2.0,14.0),"TCEHY":(78,-0.2,-1.0),"BABA":(142,-0.4,-2.0),"PDD":(125,-0.6,-3.0),
        "CATL":(310,0.3,2.5),"BYD":(116,-0.2,1.8),"FOXCONN":(62,1.5,10.5),"MOUTAI":(1520,-0.1,0.4),
        "SMH":(330,1.3,10.5),"IGV":(105,0.3,3.2),"XLU":(88,0.7,5.5),"GRID":(145,1.1,7.1),
        "DLR":(190,0.6,4.5),"XLE":(92,-0.3,-2.0),"RUSSELL":(2400,0.20,0.5)
    }
    out = {}
    for i,(k,meta) in enumerate(universe.items()):
        last, day, d20 = seed.get(k,(100+i,0.0,0.0))
        out[k] = {
            "name":meta.get("name",k),"ticker":meta.get("ticker",""),"group":meta.get("group",""),
            "theme":meta.get("theme",""),"region":meta.get("region",""),
            "last":last,"change_pct":day,"change_5d_pct":d20/4,"change_20d_pct":d20,
            "vol_20d":20.0 + (i%8)*2,"ret_z":day/0.8,"volume_ratio":1.0+(i%5)*0.12,
            "status":"demo","asof":"DEMO"
        }
    return out

def demo_macro(series_map):
    values = {
        "US10Y":4.25,"US2Y":3.95,"USREAL10Y":1.88,"BREAKEVEN10Y":2.37,
        "HYSPREAD":3.35,"VIX":16.8,"NFCI":-0.38,"FEDBAL":6640000,
        "RRP":82.0,"UNRATE":4.2,"CPI":327.5
    }
    out={}
    for k,meta in series_map.items():
        v=values.get(k,0.0)
        out[k]={"name":meta["name"],"value":v,"prev":v,"delta":0.0,
                "date":"DEMO","unit":meta.get("unit",""),"status":"demo","asof":"DEMO"}
    return out

def demo_news():
    return [
        {"title":"Hyperscalers discuss higher AI infrastructure spending and data-center power needs",
         "url":"#","source":"DEMO · institutional research","published":"DEMO","modules":["增长","实体瓶颈"],
         "themes":["AI资本开支"],"score":3.5,"lang":"English","bucket":"AI资本开支","status":"demo","asof":"DEMO"},
        {"title":"Policy debate focuses on advanced-chip export controls and supply-chain effects",
         "url":"#","source":"DEMO · policy source","published":"DEMO","modules":["政策","全球化"],
         "themes":["贸易与关税"],"score":3.3,"lang":"English","bucket":"全球宏观","status":"demo","asof":"DEMO"},
        {"title":"Copper strength draws attention to grid investment and data-center infrastructure demand",
         "url":"#","source":"DEMO · market research","published":"DEMO","modules":["实体瓶颈","资产配置"],
         "themes":["AI资本开支"],"score":3.2,"lang":"English","bucket":"商品与瓶颈","status":"demo","asof":"DEMO"},
        {"title":"Markets reassess real yields, credit spreads and the durability of risk appetite",
         "url":"#","source":"DEMO · macro research","published":"DEMO","modules":["金融状况","资产配置"],
         "themes":["流动性与信用"],"score":3.0,"lang":"English","bucket":"全球宏观","status":"demo","asof":"DEMO"},
        {"title":"Weather risks raise questions about crop yields, food prices and inflation transmission",
         "url":"#","source":"DEMO · climate research","published":"DEMO","modules":["实体瓶颈","社会与分配"],
         "themes":["天气与农业"],"score":2.9,"lang":"English","bucket":"商品与瓶颈","status":"demo","asof":"DEMO"},
    ]
