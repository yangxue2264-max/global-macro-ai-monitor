from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from .ontology import tag_modules, tag_themes, TRUSTED_DOMAINS

HEADERS = {"User-Agent": "Mozilla/5.0 (GlobalMacroAIMonitor/0.2; research use)"}
BASE = Path(__file__).resolve().parents[1]
A_SHARE_CACHE = BASE / "data" / "reference" / "a_share_universe.json"
MIN_VALID_A_SHARE_UNIVERSE = int(os.getenv("MIN_VALID_A_SHARE_UNIVERSE", "4500"))

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
        {
            "Open": quote_data.get("open", [None] * len(timestamps)),
            "High": quote_data.get("high", [None] * len(timestamps)),
            "Low": quote_data.get("low", [None] * len(timestamps)),
            "Close": quote_data.get("close", []),
            "Volume": quote_data.get("volume", []),
        },
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


def _eastmoney_index_history(secid: str, limit: int = 260) -> pd.DataFrame:
    response = requests.get(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": secid, "klt": 101, "fqt": 1, "lmt": limit, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56"},
        headers=HEADERS, timeout=12,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("klines", []) or []
    parsed = [str(row).split(",")[:6] for row in rows]
    frame = pd.DataFrame(parsed, columns=["Date", "Open", "Close", "High", "Low", "Volume"])
    if frame.empty:
        return frame
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in ["Open", "Close", "High", "Low", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Date", "Close"]).set_index("Date")


def _tencent_index_history(symbol: str, limit: int = 260) -> pd.DataFrame:
    response = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": f"{symbol},day,,,{limit},qfq"}, headers=HEADERS, timeout=12,
    )
    response.raise_for_status()
    payload = response.json().get("data", {}).get(symbol, {}) or {}
    rows = payload.get("qfqday") or payload.get("day") or []
    parsed = [list(row)[:6] for row in rows]
    frame = pd.DataFrame(parsed, columns=["Date", "Open", "Close", "High", "Low", "Volume"])
    if frame.empty:
        return frame
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in ["Open", "Close", "High", "Low", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Date", "Close"]).set_index("Date")


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
        size = len(timestamps)
        def values(name):
            raw = quotes.get(name) or []
            return list(raw)[:size] + [None] * max(0, size - len(raw))
        frames[symbol] = pd.DataFrame(
            {
                "Open": values("open"),
                "High": values("high"),
                "Low": values("low"),
                "Close": values("close"),
                "Volume": values("volume"),
            },
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

def _snapshot_from_frames(meta, price_df, volume_df=None, source="Yahoo Finance", status="ok", **extra):
    base = {"name":meta.get("name",""),"ticker":meta["ticker"],"group":meta.get("group",""),"theme":meta.get("theme",""),"region":meta.get("region",""),"last":np.nan,"change_pct":np.nan,"change_5d_pct":np.nan,"change_20d_pct":np.nan,"vol_20d":np.nan,"ret_z":np.nan,"volume_ratio":np.nan,"asof":"","history":[],"source":source,"status":"unavailable",**extra}
    try:
        if isinstance(price_df, pd.DataFrame):
            frame = price_df.copy()
            c = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
            opens = pd.to_numeric(frame.get("Open"), errors="coerce") if "Open" in frame else pd.Series(index=frame.index, dtype=float)
            volumes = pd.to_numeric(frame.get("Volume"), errors="coerce") if "Volume" in frame else pd.Series(index=frame.index, dtype=float)
        else:
            c = pd.Series(price_df).dropna()
            opens = pd.Series(index=c.index, dtype=float)
            volumes = pd.Series(volume_df).dropna() if volume_df is not None else pd.Series(index=c.index, dtype=float)
        if len(c)<2:return base
        r=c.pct_change().dropna(); std20=r.tail(20).std() if len(r)>=5 else np.nan
        ret_z=(r.iloc[-1]/std20) if std20 and not np.isnan(std20) and std20!=0 else np.nan
        vr=np.nan
        v=volumes.dropna()
        if len(v)>=5 and v.tail(20).mean()!=0: vr=float(v.iloc[-1]/v.tail(20).mean())
        aligned = pd.DataFrame({"close": c, "open": opens.reindex(c.index), "volume": volumes.reindex(c.index)})
        aligned["return_pct"] = aligned["close"].pct_change() * 100
        aligned["open_gap_pct"] = (aligned["open"] / aligned["close"].shift(1) - 1) * 100
        history=[]
        for idx, item in aligned.tail(260).iterrows():
            def clean(value):
                return round(float(value), 6) if pd.notna(value) and np.isfinite(float(value)) else None
            history.append({
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx)[:10],
                "open": clean(item.get("open")),
                "close": clean(item.get("close")),
                "return_pct": clean(item.get("return_pct")),
                "open_gap_pct": clean(item.get("open_gap_pct")),
                "volume": clean(item.get("volume")),
            })
        base.update({"last":float(c.iloc[-1]),"change_pct":float((c.iloc[-1]/c.iloc[-2]-1)*100),"change_5d_pct":float((c.iloc[-1]/c.iloc[-6]-1)*100) if len(c)>=6 else np.nan,"change_20d_pct":float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else np.nan,"vol_20d":float(r.tail(20).std()*np.sqrt(252)*100) if len(r)>=5 else np.nan,"ret_z":float(ret_z) if not np.isnan(ret_z) else np.nan,"volume_ratio":float(vr) if not np.isnan(vr) else np.nan,"asof":str(c.index[-1].date()) if hasattr(c.index[-1],"date") else str(c.index[-1]),"history":history,"status":status})
        return base
    except Exception:return base

def fetch_market_snapshot(universe: dict):
    entries = list(universe.items())
    chunks = [entries[i:i+20] for i in range(0, len(entries), 20)]

    def one_chunk(chunk):
        try:
            return _yahoo_spark([meta["ticker"] for _, meta in chunk], period="1y")
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
            future_map = {pool.submit(_yahoo_chart, ticker, "1y"): ticker for ticker in missing}
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
        out[key] = _snapshot_from_frames(meta, frame) if frame is not None and not frame.empty else _snapshot_from_frames(meta, None)
    return out


def _a_share_ticker_from_code(value: str) -> str:
    code = "".join(ch for ch in str(value or "") if ch.isdigit())[:6]
    if len(code) != 6:
        return ""
    if code.startswith(("4", "8", "92")):
        return f"{code}.BJ"
    if code.startswith(("5", "6", "9")):
        return f"{code}.SS"
    return f"{code}.SZ"


def _clean_stock_name(value) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"\s+", "", text).strip()


def _number(value, multiplier: float = 1.0):
    try:
        parsed = float(value) * multiplier
        return parsed if np.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def fetch_sse_a_share_universe() -> list[dict]:
    """Fetch Shanghai main-board and STAR listings from the exchange itself."""
    endpoint = "https://query.sse.com.cn/sseQuery/commonQuery.do"
    headers = {
        **HEADERS,
        "Referer": "https://www.sse.com.cn/assortment/stock/list/share/",
    }

    def one(stock_type: str):
        params = {
            "STOCK_TYPE": stock_type,
            "REG_PROVINCE": "",
            "CSRC_CODE": "",
            "STOCK_CODE": "",
            "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
            "COMPANY_STATUS": "2,4,5,7,8",
            "type": "inParams",
            "isPagination": "true",
            "pageHelp.cacheSize": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.pageSize": "10000",
            "pageHelp.pageNo": "1",
            "pageHelp.endPage": "1",
        }
        response = requests.get(endpoint, params=params, headers=headers, timeout=35)
        response.raise_for_status()
        return response.json().get("result", []) or []

    output = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(one, ("1", "8")))
        for rows in batches:
            for item in rows:
                ticker = _a_share_ticker_from_code(item.get("A_STOCK_CODE"))
                name = _clean_stock_name(item.get("SEC_NAME_CN") or item.get("COMPANY_ABBR"))
                if ticker and name:
                    output.append({
                        "ticker": ticker,
                        "name": name,
                        "industry": str(item.get("CSRC_CODE_DESC") or "").strip(),
                        "industry_code": str(item.get("CSRC_CODE") or "").strip(),
                        "market": "科创板" if ticker.startswith("688") else "沪市主板",
                        "list_date": str(item.get("LIST_DATE") or ""),
                        "source": "上海证券交易所",
                    })
    except Exception:
        return []
    return output


def fetch_szse_a_share_universe() -> list[dict]:
    """Fetch the complete Shenzhen A-share workbook in one official request."""
    try:
        response = requests.get(
            "https://www.szse.cn/api/report/ShowReport",
            params={"SHOWTYPE": "xlsx", "CATALOGID": "1110", "TABKEY": "tab1"},
            headers={**HEADERS, "Referer": "https://www.szse.cn/market/product/stock/list/index.html"},
            timeout=40,
        )
        response.raise_for_status()
        frame = pd.read_excel(BytesIO(response.content), dtype={"A股代码": str})
        output = []
        for item in frame.to_dict("records"):
            code = str(item.get("A股代码") or "").split(".")[0].zfill(6)
            ticker = _a_share_ticker_from_code(code)
            name = _clean_stock_name(item.get("A股简称"))
            if not ticker or not name:
                continue
            total_shares = _number(item.get("A股总股本"), 100_000_000)
            float_shares = _number(item.get("A股流通股本"), 100_000_000)
            output.append({
                "ticker": ticker,
                "name": name,
                "industry": str(item.get("所属行业") or "").strip(),
                "market": str(item.get("板块") or "深市").strip(),
                "list_date": str(item.get("A股上市日期") or ""),
                "total_shares": total_shares,
                "float_shares": float_shares,
                "source": "深圳证券交易所",
            })
        return output
    except Exception:
        return []


def fetch_bse_a_share_universe() -> list[dict]:
    """Fetch all Beijing Stock Exchange listings from the exchange endpoint."""
    endpoint = "https://www.bse.cn/nqxxController/nqxxCnzq.do"
    headers = {**HEADERS, "Referer": "https://www.bse.cn/nq/listedcompany.html"}

    def page(number: int):
        try:
            response = requests.post(
                endpoint,
                data={
                    "page": str(number), "typejb": "T", "xxfcbj[]": "2",
                    "xxzqdm": "", "sortfield": "xxzqdm", "sorttype": "asc",
                },
                headers=headers,
                timeout=25,
            )
            response.raise_for_status()
            text = response.text
            return json.loads(text[text.find("["):text.rfind("]") + 1])[0]
        except Exception:
            return {}

    try:
        first = page(0)
        if not first:
            return []
        pages = max(1, int(first.get("totalPages") or 1))
        payloads = [first]
        if pages > 1:
            with ThreadPoolExecutor(max_workers=min(18, pages - 1)) as pool:
                payloads.extend(pool.map(page, range(1, pages)))
        output = []
        for payload in (item for item in payloads if item):
            for item in payload.get("content", []) or []:
                ticker = _a_share_ticker_from_code(item.get("xxzqdm"))
                name = _clean_stock_name(item.get("xxzqjc"))
                if ticker and name:
                    output.append({
                        "ticker": ticker,
                        "name": name,
                        "industry": str(item.get("xxsshy") or "").strip(),
                        "market": "北交所",
                        "list_date": str(item.get("fxssrq") or ""),
                        "total_shares": _number(item.get("xxzgb")),
                        "float_shares": _number(item.get("xxltgb")),
                        "source": "北京证券交易所",
                    })
        return output
    except Exception:
        return []


def fetch_official_a_share_universe() -> list[dict]:
    """Merge the free official listing feeds of all three mainland exchanges."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(fetch_sse_a_share_universe),
            pool.submit(fetch_szse_a_share_universe),
            pool.submit(fetch_bse_a_share_universe),
        ]
        batches = [future.result() for future in futures]
    merged = {}
    for rows in batches:
        for row in rows:
            if row.get("ticker"):
                merged[row["ticker"]] = row
    return sorted(merged.values(), key=lambda row: row["ticker"])


def load_cached_a_share_universe() -> tuple[list[dict], dict]:
    try:
        payload = json.loads(A_SHARE_CACHE.read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        if len(rows) < MIN_VALID_A_SHARE_UNIVERSE:
            return [], {}
        stamp = datetime.fromisoformat(str(payload.get("generated_at", "")))
        now = datetime.now(stamp.tzinfo or ZoneInfo("Asia/Shanghai"))
        if (now - stamp).total_seconds() > 14 * 86400:
            return [], {}
        return rows, payload
    except Exception:
        return [], {}


def save_a_share_universe_cache(rows: list[dict], sources: list[str] | None = None):
    if len(rows) < MIN_VALID_A_SHARE_UNIVERSE:
        return
    payload = {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "count": len(rows),
        "sources": sources or sorted({row.get("source", "") for row in rows if row.get("source")}),
        "rows": rows,
    }
    try:
        A_SHARE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = A_SHARE_CACHE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(A_SHARE_CACHE)
    except OSError:
        pass


def fetch_eastmoney_a_share_universe() -> list[dict]:
    """Optional quote/industry enrichment; the official exchange list remains authoritative."""
    endpoint = "https://82.push2.eastmoney.com/api/qt/clist/get"
    base_params = {
        "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f6", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f2,f3,f5,f6,f8,f10,f12,f14,f17,f18,f20,f21,f100",
    }

    def get_page(page_number: int):
        params = {**base_params, "pn": page_number}
        for attempt in range(2):
            try:
                response = requests.get(
                    endpoint,
                    params=params,
                    headers={**HEADERS, "Referer": "https://quote.eastmoney.com/"},
                    timeout=12,
                )
                response.raise_for_status()
                return response.json().get("data") or {}
            except Exception:
                if attempt == 0:
                    time.sleep(0.4)
        return {}

    first = get_page(1)
    if not first:
        return []
    total = int(first.get("total") or 0)
    pages = min(65, max(1, math.ceil(total / base_params["pz"])))
    payloads = [first]
    if pages > 1:
        with ThreadPoolExecutor(max_workers=8) as pool:
            payloads.extend(pool.map(get_page, range(2, pages + 1)))
    output = []
    for payload in payloads:
        for item in payload.get("diff", []) or []:
            ticker = _a_share_ticker_from_code(item.get("f12"))
            name = _clean_stock_name(item.get("f14"))
            if not ticker or not name:
                continue
            output.append({
                "ticker": ticker, "name": name, "industry": str(item.get("f100") or "").strip(),
                "last": _number(item.get("f2")), "change_pct": _number(item.get("f3")),
                "volume": _number(item.get("f5")), "amount": _number(item.get("f6")),
                "turnover_rate": _number(item.get("f8")), "volume_ratio": _number(item.get("f10")),
                "open": _number(item.get("f17")), "pre_close": _number(item.get("f18")),
                "market_cap": _number(item.get("f20")), "float_market_cap": _number(item.get("f21")),
                "quote_source": "东方财富公开行情",
            })
    return output


def fetch_a_share_universe(
    token: str = "", include_quotes: bool = True, refresh: bool = False
) -> tuple[list[dict], dict]:
    """Return a no-key full-market universe with a durable last-good fallback.

    The token argument is retained for backwards compatibility but is intentionally
    unused: this path does not require Tushare or another paid credential.
    """
    cached, cache_meta = load_cached_a_share_universe()
    if cached and not refresh:
        official, enrichment = [], []
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            official_future = pool.submit(fetch_official_a_share_universe)
            enrichment_future = pool.submit(fetch_eastmoney_a_share_universe)
            official = official_future.result()
            enrichment = enrichment_future.result()
    fresh = len(official) >= MIN_VALID_A_SHARE_UNIVERSE
    if fresh:
        combined = {row.get("ticker"): row for row in cached if row.get("ticker")}
        combined.update({row.get("ticker"): row for row in official if row.get("ticker")})
        base_rows = sorted(combined.values(), key=lambda row: row["ticker"])
    else:
        base_rows = cached
    if not base_rows:
        partial = official if official else enrichment
        return partial, {
            "mode": "UNAVAILABLE_PARTIAL",
            "count": len(partial),
            "minimum_required": MIN_VALID_A_SHARE_UNIVERSE,
            "usable": False,
            "fresh": False,
        }

    enrichment_by_ticker = {row["ticker"]: row for row in enrichment}
    tencent_by_ticker = (
        fetch_tencent_auction([row["ticker"] for row in base_rows]) if include_quotes else {}
    )
    rows = []
    for base in base_rows:
        quote_row = enrichment_by_ticker.get(base.get("ticker"), {})
        tencent_row = tencent_by_ticker.get(base.get("ticker"), {})
        merged = dict(base)
        for key in (
            "last", "change_pct", "volume", "amount", "turnover_rate", "volume_ratio",
            "open", "pre_close", "market_cap", "float_market_cap", "quote_source",
        ):
            if quote_row.get(key) not in (None, ""):
                merged[key] = quote_row[key]
        if quote_row.get("industry"):
            merged["industry"] = quote_row["industry"]
        for key in (
            "last", "change_pct", "volume", "amount", "turnover_rate",
            "open", "pre_close", "market_cap", "float_market_cap", "quote_source",
        ):
            if tencent_row.get(key) not in (None, ""):
                merged[key] = tencent_row[key]
        if merged.get("market_cap") is None and merged.get("total_shares") and merged.get("last"):
            merged["market_cap"] = merged["total_shares"] * merged["last"]
        if merged.get("float_market_cap") is None and merged.get("float_shares") and merged.get("last"):
            merged["float_market_cap"] = merged["float_shares"] * merged["last"]
        rows.append(merged)

    if fresh:
        save_a_share_universe_cache(rows)
    additions = []
    if tencent_by_ticker:
        additions.append("TENCENT_QUOTES")
    if enrichment:
        additions.append("INDUSTRY_ENRICHMENT")
    mode = "OFFICIAL_EXCHANGES" + ("+" + "+".join(additions) if additions else "")
    if not fresh:
        mode = "LAST_GOOD_CACHE" + ("+" + "+".join(additions) if additions else "")
    minimum_quotes = max(3500, int(len(rows) * 0.65)) if include_quotes else 0
    quote_usable = not include_quotes or len(tencent_by_ticker) >= minimum_quotes
    return rows, {
        "mode": mode,
        "count": len(rows),
        "minimum_required": MIN_VALID_A_SHARE_UNIVERSE,
        "usable": len(rows) >= MIN_VALID_A_SHARE_UNIVERSE and quote_usable,
        "fresh": fresh,
        "fresh_count": len(official),
        "asof": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat() if fresh else cache_meta.get("generated_at", ""),
        "listing_sources": sorted({row.get("source", "") for row in base_rows if row.get("source")}),
        "enrichment_count": len(enrichment),
        "quote_count": len(tencent_by_ticker),
        "minimum_quote_count": minimum_quotes,
        "quote_usable": quote_usable,
    }


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


def _fred_api(series: str, api_key: str) -> pd.DataFrame:
    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series, "api_key": api_key, "file_type": "json", "sort_order": "asc"},
        headers=HEADERS, timeout=12,
    )
    response.raise_for_status()
    frame = pd.DataFrame(response.json().get("observations", []) or [])
    if frame.empty:
        return pd.DataFrame(columns=["DATE", series])
    frame["DATE"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame[series] = pd.to_numeric(frame.get("value"), errors="coerce")
    return frame[["DATE", series]].dropna().sort_values("DATE")


def fetch_fred_snapshot(series_map=None, api_key=""):
    series_map = series_map or FRED_SERIES
    def one(key, meta):
        try:
            df = _fred_api(meta["series"], api_key) if api_key else _fred_csv(meta["series"])
            row = df.iloc[-1]
            previous = df.iloc[-2] if len(df) > 1 else row
            return key, {
                "name": meta["name"], "value": float(row[meta["series"]]),
                "prev": float(previous[meta["series"]]),
                "delta": float(row[meta["series"]] - previous[meta["series"]]),
                "date": row["DATE"].date().isoformat(), "unit": meta.get("unit",""),
                "status":"ok", "source": "FRED API" if api_key else "FRED CSV"
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


def _auction_ticker(value):
    ticker = str(value or "").strip().upper()
    return ticker.replace(".SH", ".SS")


def _quote_symbol(ticker):
    ticker = _auction_ticker(ticker)
    code = ticker.split(".")[0]
    prefix = "sh" if ticker.endswith(".SS") else "bj" if ticker.endswith(".BJ") else "sz"
    return f"{prefix}{code}"


def _auction_row(ticker, name, price, pre_close, date="", time="", source="", **extra):
    try:
        price, pre_close = float(price), float(pre_close)
        if price <= 0 or pre_close <= 0:
            return None
        return {
            "ticker": _auction_ticker(ticker),
            "name": name or _auction_ticker(ticker),
            "auction_price": price,
            "pre_close": pre_close,
            "gap_pct": round((price / pre_close - 1) * 100, 3),
            "date": str(date or ""),
            "time": str(time or ""),
            "source": source,
            "status": "ok",
            **extra,
        }
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _parse_sina_auction(text, symbol_to_ticker):
    out = {}
    for line in (text or "").splitlines():
        match = re.search(r"var hq_str_([a-z]{2}\d+)=\"(.*)\";", line.strip())
        if not match:
            continue
        symbol, body = match.groups()
        fields = body.split(",")
        if len(fields) < 32:
            continue
        ticker = symbol_to_ticker.get(symbol)
        row = _auction_row(
            ticker, fields[0], fields[1], fields[2], date=fields[30], time=fields[31],
            source="Sina public quote fallback", volume=fields[8] or None, amount=fields[9] or None,
        )
        if row:
            out[ticker] = row
    return out


def fetch_sina_auction(tickers):
    symbols = {_quote_symbol(ticker): _auction_ticker(ticker) for ticker in tickers}
    if not symbols:
        return {}
    try:
        response = requests.get(
            "https://hq.sinajs.cn/list=" + ",".join(symbols),
            headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"}, timeout=12,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        return _parse_sina_auction(response.text, symbols)
    except Exception:
        return {}


def _parse_tencent_auction(text, symbol_to_ticker):
    out = {}
    for line in (text or "").split(";"):
        match = re.search(r"v_([a-z]{2}\d+)=\"(.*)\"", line.strip())
        if not match:
            continue
        symbol, body = match.groups()
        fields = body.split("~")
        if len(fields) < 31:
            continue
        ticker = symbol_to_ticker.get(symbol)
        stamp = fields[30] if len(fields) > 30 else ""
        row = _auction_row(
            ticker, fields[1], fields[5], fields[4],
            date=stamp[:8], time=stamp[8:14], source="腾讯免费实时行情",
            last=_number(fields[3]),
            change_pct=_number(fields[32] if len(fields) > 32 else None),
            open=_number(fields[5]),
            quote_source="腾讯免费实时行情",
            volume=_number(fields[6], 100),
            amount=_number(fields[37] if len(fields) > 37 else None, 10_000),
            turnover_rate=_number(fields[38] if len(fields) > 38 else None),
            market_cap=_number(fields[44] if len(fields) > 44 else None, 100_000_000),
            float_market_cap=_number(fields[45] if len(fields) > 45 else None, 100_000_000),
        )
        if row:
            out[ticker] = row
    return out


def fetch_tencent_auction(tickers, batch_size: int = 200):
    """Fetch free quotes in bounded batches so an entire A-share market fits safely."""
    wanted = sorted({_auction_ticker(ticker) for ticker in tickers if ticker})
    chunks = [wanted[index:index + batch_size] for index in range(0, len(wanted), batch_size)]
    if not chunks:
        return {}

    def one(chunk):
        symbols = {_quote_symbol(ticker): ticker for ticker in chunk}
        for attempt in range(3):
            try:
                response = requests.get(
                    "https://qt.gtimg.cn/q=" + ",".join(symbols),
                    headers={**HEADERS, "Referer": "https://gu.qq.com/"},
                    timeout=18,
                )
                response.raise_for_status()
                response.encoding = "gbk"
                parsed = _parse_tencent_auction(response.text, symbols)
                if parsed:
                    return parsed
            except Exception:
                pass
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        return {}

    output = {}
    with ThreadPoolExecutor(max_workers=min(10, len(chunks))) as pool:
        for rows in pool.map(one, chunks):
            output.update(rows)
    return output


def fetch_auction_quotes(tickers, trade_date):
    """Fetch selected 09:25 opening prices without a paid API key."""
    wanted = sorted({ticker for value in tickers if value for ticker in [_auction_ticker(value)] if ticker.endswith((".SS", ".SZ", ".BJ"))})
    out = fetch_tencent_auction(wanted)
    missing = [ticker for ticker in wanted if ticker not in out]
    if missing:
        out.update(fetch_sina_auction(missing))
    return out


def fetch_all_auction_quotes(trade_date):
    """Fetch the full-market 09:25 opening snapshot with explicit completeness gates."""
    universe, universe_coverage = fetch_a_share_universe(include_quotes=False)
    if not universe_coverage.get("usable"):
        return {}, {
            "mode": "UNAVAILABLE_NO_FULL_UNIVERSE",
            "count": 0,
            "universe_count": len(universe),
            "usable": False,
        }

    out = fetch_tencent_auction([row["ticker"] for row in universe])
    expected_date = str(trade_date).replace("-", "")
    current = {
        ticker: row for ticker, row in out.items()
        if not row.get("date") or row.get("date") == expected_date
    }
    universe_by_ticker = {stock.get("ticker"): stock for stock in universe}
    for ticker, row in current.items():
        item = universe_by_ticker.get(ticker, {})
        for key in ("name", "industry", "market"):
            if item.get(key) not in (None, ""):
                row[key] = item[key]
        for key in ("market_cap", "float_market_cap"):
            if item.get(key) not in (None, "") and row.get(key) in (None, ""):
                row[key] = item[key]

    # If Tencent omitted a symbol, an independently obtained Eastmoney opening
    # field may still complete it. This is augmentation, never the stock-list authority.
    for item in universe:
        if item.get("ticker") in current:
            continue
        row = _auction_row(
            item.get("ticker"), item.get("name"), item.get("open"), item.get("pre_close"),
            date=str(trade_date).replace("-", ""), time="09:25",
            source="东方财富免费行情备用",
            volume=item.get("volume"), amount=item.get("amount"),
            turnover_rate=item.get("turnover_rate"), volume_ratio=item.get("volume_ratio"),
            market_cap=item.get("market_cap"), float_market_cap=item.get("float_market_cap"),
            industry=item.get("industry"),
        )
        if row:
            current[row["ticker"]] = row

    minimum = max(3500, int(len(universe) * 0.65))
    usable = len(current) >= minimum
    sources = sorted({row.get("source", "") for row in current.values() if row.get("source")})
    return current, {
        "mode": "FREE_FULL_MARKET" if usable else "UNAVAILABLE_PARTIAL_AUCTION",
        "count": len(current),
        "universe_count": len(universe),
        "minimum_required": minimum,
        "usable": usable,
        "sources": sources,
        "trade_date": str(trade_date),
    }

def data_health(market, macro, news):
    total_m = len(market)
    live_m = sum(1 for v in market.values() if v.get("status")=="ok")
    demo_m = sum(1 for v in market.values() if v.get("status")=="demo")
    total_macro = len(macro)
    live_macro = sum(1 for v in macro.values() if v.get("status") in {"ok", "treasury"})
    demo_macro = sum(1 for v in macro.values() if v.get("status")=="demo")
    proxy_macro = sum(1 for v in macro.values() if v.get("status") in {"market_proxy", "derived"})
    return {
        "market_live": live_m, "market_demo": demo_m, "market_total": total_m,
        "macro_live": live_macro, "macro_demo": demo_macro, "macro_total": total_macro,
        "macro_proxy": proxy_macro,
        "news_count": len(news),
    }
