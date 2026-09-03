from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo
import json
import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from .ontology import tag_modules, tag_themes, TRUSTED_DOMAINS

HEADERS = {"User-Agent": "Mozilla/5.0 (GlobalMacroAIMonitor/0.2; research use)"}

FRED_SERIES = {
    "US10Y": {"name":"美国10年期国债收益率", "series":"DGS10", "unit":"%"},
    "US2Y": {"name":"美国2年期国债收益率", "series":"DGS2", "unit":"%"},
    "USREAL10Y": {"name":"美国10年期实际利率", "series":"DFII10", "unit":"%"},
    "BREAKEVEN10Y": {"name":"美国10年期盈亏平衡通胀", "series":"T10YIE", "unit":"%"},
    "HYSPREAD": {"name":"美国高收益债OAS", "series":"BAMLH0A0HYM2", "unit":"%"},
    "VIX": {"name":"VIX", "series":"VIXCLS", "unit":""},
    "NFCI": {"name":"芝加哥联储金融状况指数", "series":"NFCI", "unit":""},
    "FEDBAL": {"name":"美联储资产负债表", "series":"WALCL", "unit":"百万美元"},
    "RRP": {"name":"美联储隔夜逆回购", "series":"RRPONTSYD", "unit":"十亿美元"},
    "UNRATE": {"name":"美国失业率", "series":"UNRATE", "unit":"%"},
    "CPI": {"name":"美国CPI", "series":"CPIAUCSL", "unit":"指数"},
}

def load_watchlist(path: str | Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def flatten_watchlist(cfg):
    out = {}
    for group, items in cfg.items():
        for key, meta in items.items():
            out[key] = {**meta, "group": group}
    return out

def _to_series(x):
    if isinstance(x, pd.DataFrame) and x.shape[1] == 1:
        x = x.iloc[:,0]
    return pd.Series(x).dropna()

def _yahoo_chart(ticker: str, period="3mo") -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}"
    params = {"range": period, "interval": "1d", "events": "history"}
    response = requests.get(url, params=params, headers=HEADERS, timeout=6)
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result", [])
    if not result:
        return pd.DataFrame()
    payload = result[0]
    timestamps = payload.get("timestamp", [])
    quote_data = (payload.get("indicators", {}).get("quote") or [{}])[0]
    if not timestamps or not quote_data.get("close"):
        return pd.DataFrame()
    frame = pd.DataFrame(
        {"Close": quote_data.get("close", []), "Volume": quote_data.get("volume", [])},
        index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
    )
    return frame.dropna(subset=["Close"])


def fetch_price_history(ticker: str, period="3mo") -> pd.DataFrame:
    try:
        return _yahoo_chart(ticker, period=period)
    except Exception:
        try:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=False, threads=False, timeout=8)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df.dropna(how="all")
        except Exception:
            return pd.DataFrame()


def _yahoo_spark(tickers, period="3mo"):
    """Fetch up to 20 symbols in one Yahoo request (the endpoint's hard cap)."""
    endpoint = "https://query1.finance.yahoo.com/v7/finance/spark"
    response = requests.get(
        endpoint,
        params={"symbols": ",".join(tickers), "range": period, "interval": "1d"},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    results = response.json().get("spark", {}).get("result", []) or []
    frames = {}
    for item in results:
        symbol = item.get("symbol")
        payloads = item.get("response") or []
        if not symbol or not payloads:
            continue
        payload = payloads[0]
        timestamps = payload.get("timestamp") or []
        quotes = (payload.get("indicators", {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []
        if not timestamps or not closes:
            continue
        frames[symbol] = pd.DataFrame(
            {"Close": closes},
            index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
        ).dropna(subset=["Close"])
    return frames

def _market_snapshot_one(meta):
    df = fetch_price_history(meta["ticker"], period="6mo")
    base = {
        "name": meta.get("name",""), "ticker": meta["ticker"], "group": meta.get("group",""),
        "theme": meta.get("theme",""), "region": meta.get("region",""),
        "last": np.nan, "change_pct": np.nan, "change_5d_pct": np.nan, "change_20d_pct": np.nan,
        "vol_20d": np.nan, "ret_z": np.nan, "volume_ratio": np.nan, "asof":"", "status":"unavailable"
    }
    if df.empty or "Close" not in df.columns:
        return base
    c = _to_series(df["Close"])
    if len(c) < 2:
        return base
    r = c.pct_change().dropna()
    last_ret = r.iloc[-1] if len(r) else np.nan
    std20 = r.tail(20).std() if len(r) >= 5 else np.nan
    ret_z = last_ret/std20 if std20 and not np.isnan(std20) and std20 != 0 else np.nan
    volume_ratio = np.nan
    if "Volume" in df.columns:
        v = _to_series(df["Volume"])
        if len(v) >= 5 and v.tail(20).mean() != 0:
            volume_ratio = float(v.iloc[-1] / v.tail(20).mean())
    base.update({
        "last": float(c.iloc[-1]),
        "change_pct": float((c.iloc[-1]/c.iloc[-2]-1)*100),
        "change_5d_pct": float((c.iloc[-1]/c.iloc[-6]-1)*100) if len(c)>=6 else np.nan,
        "change_20d_pct": float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else np.nan,
        "vol_20d": float(r.tail(20).std()*np.sqrt(252)*100) if len(r)>=5 else np.nan,
        "ret_z": float(ret_z) if not np.isnan(ret_z) else np.nan,
        "volume_ratio": float(volume_ratio) if not np.isnan(volume_ratio) else np.nan,
        "asof": str(c.index[-1]) if hasattr(c, "index") else "",
        "status":"ok",
    })
    return base

def _snapshot_from_frames(meta, price_df, volume_df=None):
    base = {"name":meta.get("name",""),"ticker":meta["ticker"],"group":meta.get("group",""),"theme":meta.get("theme",""),"region":meta.get("region",""),"last":np.nan,"change_pct":np.nan,"change_5d_pct":np.nan,"change_20d_pct":np.nan,"vol_20d":np.nan,"ret_z":np.nan,"volume_ratio":np.nan,"asof":"","status":"unavailable"}
    try:
        c=pd.Series(price_df).dropna()
        if len(c)<2:return base
        r=c.pct_change().dropna(); std20=r.tail(20).std() if len(r)>=5 else np.nan
        ret_z=(r.iloc[-1]/std20) if std20 and not np.isnan(std20) and std20!=0 else np.nan
        vr=np.nan
        if volume_df is not None:
            v=pd.Series(volume_df).dropna()
            if len(v)>=5 and v.tail(20).mean()!=0: vr=float(v.iloc[-1]/v.tail(20).mean())
        base.update({"last":float(c.iloc[-1]),"change_pct":float((c.iloc[-1]/c.iloc[-2]-1)*100),"change_5d_pct":float((c.iloc[-1]/c.iloc[-6]-1)*100) if len(c)>=6 else np.nan,"change_20d_pct":float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else np.nan,"vol_20d":float(r.tail(20).std()*np.sqrt(252)*100) if len(r)>=5 else np.nan,"ret_z":float(ret_z) if not np.isnan(ret_z) else np.nan,"volume_ratio":float(vr) if not np.isnan(vr) else np.nan,"asof":str(c.index[-1].date()) if hasattr(c.index[-1],"date") else str(c.index[-1]),"status":"ok"})
        return base
    except Exception:return base

def fetch_market_snapshot(universe: dict):
    entries = list(universe.items())
    chunks = [entries[i:i+20] for i in range(0, len(entries), 20)]

    def one_chunk(chunk):
        try:
            return _yahoo_spark([meta["ticker"] for _, meta in chunk], period="3mo")
        except Exception:
            return {}

    frames = {}
    # Four batched requests replace 61 simultaneous single-ticker requests,
    # avoiding Yahoo rate limits while keeping the cold start bounded.
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = [pool.submit(one_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            frames.update(future.result())

    # Spark occasionally omits a small number of symbols. Retry only critical
    # dashboard series, never the full universe, so latency remains bounded.
    critical = {"^GSPC", "^NDX", "DX-Y.NYB", "CNY=X", "GC=F", "HG=F", "CL=F", "^VIX", "^TNX", "399006.SZ"}
    missing = [ticker for ticker in critical if ticker not in frames]
    if missing:
        with ThreadPoolExecutor(max_workers=min(4, len(missing))) as pool:
            future_map = {pool.submit(_yahoo_chart, ticker, "3mo"): ticker for ticker in missing}
            for future in as_completed(future_map):
                try:
                    frame = future.result()
                    if not frame.empty:
                        frames[future_map[future]] = frame
                except Exception:
                    pass

    out = {}
    for key, meta in universe.items():
        frame = frames.get(meta["ticker"])
        out[key] = _snapshot_from_frames(meta, frame["Close"]) if frame is not None and not frame.empty else _snapshot_from_frames(meta, None)
    return out


def fetch_treasury_snapshot():
    """Official US Treasury nominal and real curves; no API key required."""
    year = datetime.now(timezone.utc).year
    base = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all"

    def curve(curve_type):
        response = requests.get(
            base,
            params={"type": curve_type, "field_tdr_date_value": str(year), "page": "", "_format": "csv"},
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        return frame.dropna(subset=["Date"]).sort_values("Date", ascending=False)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            nominal_future = pool.submit(curve, "daily_treasury_yield_curve")
            real_future = pool.submit(curve, "daily_treasury_real_yield_curve")
            nominal, real = nominal_future.result(), real_future.result()
        n0, n1 = nominal.iloc[0], nominal.iloc[min(1, len(nominal)-1)]
        r0, r1 = real.iloc[0], real.iloc[min(1, len(real)-1)]
        date = n0["Date"].date().isoformat()
        real_date = r0["Date"].date().isoformat()
        us10, us2, real10 = float(n0["10 Yr"]), float(n0["2 Yr"]), float(r0["10 YR"])
        return {
            "US10Y": {"name":"美国10年期国债收益率","value":us10,"prev":float(n1["10 Yr"]),"delta":us10-float(n1["10 Yr"]),"date":date,"unit":"%","status":"treasury","source":"US Treasury"},
            "US2Y": {"name":"美国2年期国债收益率","value":us2,"prev":float(n1["2 Yr"]),"delta":us2-float(n1["2 Yr"]),"date":date,"unit":"%","status":"treasury","source":"US Treasury"},
            "USREAL10Y": {"name":"美国10年期实际利率","value":real10,"prev":float(r1["10 YR"]),"delta":real10-float(r1["10 YR"]),"date":real_date,"unit":"%","status":"treasury","source":"US Treasury real yield curve"},
            "BREAKEVEN10Y": {"name":"美国10年期盈亏平衡通胀","value":us10-real10,"prev":float(n1["10 Yr"])-float(r1["10 YR"]),"delta":0.0,"date":max(date,real_date),"unit":"%","status":"derived","source":"Treasury nominal 10Y − real 10Y"},
        }
    except Exception:
        return {}

def _fred_csv(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    r = requests.get(url, headers=HEADERS, timeout=8)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    df.columns = ["DATE", series]
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df[series] = pd.to_numeric(df[series], errors="coerce")
    return df.dropna()

def fetch_fred_snapshot(series_map=None):
    series_map = series_map or FRED_SERIES
    def one(key, meta):
        try:
            df = _fred_csv(meta["series"])
            row = df.iloc[-1]
            previous = df.iloc[-2] if len(df) > 1 else row
            return key, {
                "name": meta["name"], "value": float(row[meta["series"]]),
                "prev": float(previous[meta["series"]]),
                "delta": float(row[meta["series"]] - previous[meta["series"]]),
                "date": row["DATE"].date().isoformat(), "unit": meta.get("unit",""),
                "status":"ok"
            }
        except Exception:
            return key, {
                "name": meta["name"], "value": np.nan, "prev":np.nan, "delta":np.nan,
                "date":"", "unit":meta.get("unit",""), "status":"unavailable"
            }
    out = {}
    # FRED endpoints are independent. Parallel calls cap cold-start latency at
    # one timeout instead of N × timeout.
    with ThreadPoolExecutor(max_workers=min(8, len(series_map))) as pool:
        futures = [pool.submit(one, key, meta) for key, meta in series_map.items()]
        for future in as_completed(futures):
            key, value = future.result()
            out[key] = value
    return {key: out[key] for key in series_map}

def _domain_weight(url):
    domain = urlparse(url or "").netloc.lower().replace("www.","")
    return TRUSTED_DOMAINS.get(domain, 1.0)

def _parse_gdelt_seen(s):
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def fetch_gdelt(query: str, maxrecords=15, timespan="24h"):
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query":query, "mode":"ArtList", "maxrecords":maxrecords, "format":"json", "sort":"HybridRel", "timespan":timespan}
    try:
        r = requests.get(endpoint, params=params, headers=HEADERS, timeout=8)
        r.raise_for_status()
        payload = r.json()
        items = []
        now = datetime.now(timezone.utc)
        for a in payload.get("articles", []):
            title = (a.get("title") or "").strip()
            url = a.get("url") or ""
            dt = _parse_gdelt_seen(a.get("seendate") or "")
            age_h = (now-dt).total_seconds()/3600 if dt else 48
            recency = max(0.0, 2.0-age_h/24)
            text = title+" "+(a.get("domain") or "")
            items.append({
                "title":title, "url":url, "source":a.get("domain") or urlparse(url).netloc,
                "published":dt.isoformat() if dt else "", "modules":tag_modules(text),
                "themes":tag_themes(text), "score":round(float(_domain_weight(url)+recency),3),
                "lang":a.get("language","")
            })
        return items
    except Exception:
        return []

def fetch_google_news(query="global macro markets AI investment when:1d", limit=25):
    endpoint = "https://news.google.com/rss/search"
    params = {"q":query, "hl":"en-US", "gl":"US", "ceid":"US:en"}
    try:
        r = requests.get(endpoint, params=params, headers=HEADERS, timeout=8)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items=[]
        for node in root.findall(".//item")[:limit]:
            title=(node.findtext("title") or "").strip()
            src_node=node.find("source")
            src=src_node.text.strip() if src_node is not None and src_node.text else ""
            items.append({
                "title":title, "url":(node.findtext("link") or "").strip(),
                "source":src, "published":(node.findtext("pubDate") or "").strip(),
                "modules":tag_modules(title), "themes":tag_themes(title),
                "score":1.0, "lang":"English"
            })
        return items
    except Exception:
        return []

NEWS_QUERIES = {
    "AI资本开支": '(AI OR "data center" OR GPU OR hyperscaler) (capex OR investment OR power OR grid OR copper)',
    "全球宏观": '(Federal Reserve OR inflation OR jobs OR GDP OR tariff OR bond yields) markets',
    "政策原文": '(Federal Reserve OR ECB OR BIS OR IMF OR PBOC) (policy OR speech OR report OR outlook)',
    "中国与亚洲": '(China OR PBOC OR yuan OR Japan OR Korea) (economy OR market OR policy OR trade)',
    "商品与瓶颈": '(oil OR copper OR gold OR power OR electricity OR agriculture OR weather) (market OR supply OR demand)',
}

def fetch_news_bundle(max_each=10):
    china_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    lookback_days = 3 if china_now.weekday() == 0 else 1
    gdelt_timespan = f"{lookback_days * 24}h"

    def one(bucket, q):
        items=fetch_gdelt(q,maxrecords=max_each,timespan=gdelt_timespan)
        if not items:
            items=fetch_google_news(q+f" when:{lookback_days}d",limit=max_each)
        for x in items:
            x["bucket"]=bucket
        return items

    all_items=[]
    with ThreadPoolExecutor(max_workers=len(NEWS_QUERIES)) as pool:
        futures=[pool.submit(one,bucket,q) for bucket,q in NEWS_QUERIES.items()]
        for future in as_completed(futures):
            all_items.extend(future.result())
    seen,dedup=set(),[]
    for x in sorted(all_items,key=lambda z:z.get("score",0),reverse=True):
        raw=x.get("title","")
        # Google News commonly appends " - Publisher"; remove it before
        # de-duplicating the same wire story syndicated by many outlets.
        core=re.sub(r"\s+-\s+[^-]{2,45}$","",raw).lower()
        key=re.sub(r"\W+","",core)[:160]
        if not key or key in seen: continue
        if any(SequenceMatcher(None,key,old).ratio()>=0.88 for old in seen):
            continue
        seen.add(key); dedup.append(x)
    return dedup

def data_health(market, macro, news):
    total_m = len(market)
    live_m = sum(1 for v in market.values() if v.get("status")=="ok")
    demo_m = sum(1 for v in market.values() if v.get("status")=="demo")
    total_macro = len(macro)
    live_macro = sum(1 for v in macro.values() if v.get("status")=="ok")
    demo_macro = sum(1 for v in macro.values() if v.get("status")=="demo")
    return {
        "market_live": live_m, "market_demo": demo_m, "market_total": total_m,
        "macro_live": live_macro, "macro_demo": demo_macro, "macro_total": total_macro,
        "news_count": len(news),
    }
