from __future__ import annotations

import json
import os
import re
from typing import Iterable

import requests

from .preopen import normalize_a_share_ticker, normalize_watchlist_rows
from .providers import HEADERS


def _secret(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


def build_profile_catalog(defaults: Iterable[dict], universe: dict, mapping_cfg: dict) -> dict[str, dict]:
    """Build deterministic profiles from the maintained A-share mapping first."""
    catalog: dict[str, dict] = {}
    for row in normalize_watchlist_rows(defaults):
        catalog[row["ticker"]] = {
            **row,
            "profile_source": row.get("profile_source") or "维护规则库",
            "profile_confidence": row.get("profile_confidence") or "高",
            "profile_reason": row.get("profile_reason") or "根据维护的公司与海外资产映射自动生成。",
        }

    for theme, mapping in mapping_cfg.items():
        for key in mapping.get("a_share_assets", []):
            meta = universe.get(key, {})
            ticker = normalize_a_share_ticker(str(meta.get("ticker") or ""))
            if not ticker.endswith((".SS", ".SZ", ".BJ")):
                continue
            beta = mapping.get("target_beta", {}).get(key, 0)
            relation = "同向" if beta == 1 else "反向" if beta == -1 else "需判断"
            generated = {
                "ticker": ticker,
                "name": meta.get("name") or ticker,
                "theme": theme,
                "relation": relation,
                "overseas_assets": mapping.get("global_assets", [])[:4],
                "keywords": [meta.get("name") or "", ticker.split(".")[0]],
                "profile_source": "维护规则库",
                "profile_confidence": "高",
                "profile_reason": mapping.get("direction_note", "根据维护的A股主题映射自动生成。"),
            }
            catalog.setdefault(ticker, generated)

    by_name = {str(row.get("name", "")).strip().lower(): row for row in catalog.values() if row.get("name")}
    return {**catalog, **{f"name:{name}": row for name, row in by_name.items()}}


def _tencent_symbol(ticker: str) -> str:
    digits = ticker.split(".")[0]
    if ticker.endswith(".SS"):
        return f"sh{digits}"
    if ticker.endswith((".SZ", ".BJ")):
        return f"sz{digits}" if ticker.endswith(".SZ") else f"bj{digits}"
    return ""


def fetch_stock_names(tickers: Iterable[str]) -> dict[str, str]:
    symbols = {_tencent_symbol(ticker): ticker for ticker in tickers}
    symbols.pop("", None)
    if not symbols:
        return {}
    try:
        response = requests.get(
            "https://qt.gtimg.cn/q=" + ",".join(symbols), headers=HEADERS, timeout=25
        )
        response.raise_for_status()
        response.encoding = "gbk"
    except Exception:
        return {}
    names = {}
    for line in response.text.split(";"):
        match = re.search(r'v_([a-z]{2}\d+)="(.*)"', line.strip())
        if not match:
            continue
        symbol, body = match.groups()
        fields = body.split("~")
        if len(fields) > 2 and fields[1].strip():
            names[symbols.get(symbol, "")] = fields[1].strip()
    return {ticker: name for ticker, name in names.items() if ticker}


def search_a_share_by_name(query: str) -> tuple[str, str] | None:
    try:
        response = requests.get(
            "https://smartbox.gtimg.cn/s3/", params={"q": query, "t": "all"}, headers=HEADERS, timeout=25
        )
        response.raise_for_status()
        text = response.content.decode("gbk", errors="ignore")
        match = re.search(r'v_hint="(.*)"', text)
        if not match:
            return None
        decoded = bytes(match.group(1), "utf-8").decode("unicode_escape")
        for candidate in decoded.split("^"):
            fields = candidate.split("~")
            if len(fields) < 3:
                continue
            exchange, code, name = fields[:3]
            if len(code) == 6 and exchange in {"sh", "sz", "bj"}:
                suffix = ".SS" if exchange == "sh" else ".BJ" if exchange == "bj" else ".SZ"
                return f"{code}{suffix}", name
    except Exception:
        return None
    return None


def _fallback_profile(ticker: str, name: str, mapping_cfg: dict) -> dict:
    patterns = [
        (("黄金", "金矿", "贵金属"), "黄金与美元信用"),
        (("石油", "能源", "煤", "油气"), "油价与通胀"),
        (("农业", "种业", "粮", "农"), "天气与农业"),
        (("芯", "半导体", "光电", "激光", "科技", "电子", "通信"), "AI资本开支"),
    ]
    theme = next((theme for words, theme in patterns if any(word in name for word in words)), "中国增长与政策")
    mapping = mapping_cfg.get(theme, {})
    return {
        "ticker": ticker,
        "name": name,
        "theme": theme,
        "relation": "需判断",
        "overseas_assets": mapping.get("global_assets", [])[:4],
        "keywords": [name, ticker.split(".")[0]],
        "profile_source": "自动保守映射",
        "profile_confidence": "低",
        "profile_reason": "未取得可靠的公司专属映射；系统按名称与大类主题保守归类，方向不自动下结论。",
    }


def _ai_profiles(stocks: list[dict], mapping_cfg: dict, universe: dict) -> dict[str, dict]:
    key = _secret("OPENAI_API_KEY")
    if not key or not stocks:
        return {}
    allowed_themes = list(mapping_cfg)
    allowed_assets = sorted(
        key_name
        for key_name, meta in universe.items()
        if not str(meta.get("ticker", "")).endswith((".SS", ".SZ", ".BJ"))
    )
    prompt = f"""为A股盘前研究工具自动补齐自选股配置。输入股票：{json.dumps(stocks, ensure_ascii=False)}

只能从这些主题中选一个：{json.dumps(allowed_themes, ensure_ascii=False)}
海外代理只能从这些代码中选2至4个：{json.dumps(allowed_assets, ensure_ascii=False)}

返回纯JSON数组，每项必须包含 ticker、name、theme、relation、overseas_assets、keywords、profile_confidence、profile_reason。
relation只能是“同向”“反向”“需判断”；keywords仅放公司中文名、英文名、常用简称，不放宽泛行业词；
profile_confidence只能是“高”“中”“低”。判断公司基本业务、海外可比资产和受益/受损方向；如果方向并不单一，必须用“需判断”。
不要编造公司事实，不确定时降低置信度。不要输出Markdown。"""
    try:
        from openai import OpenAI

        response = OpenAI(api_key=key).responses.create(
            model=_secret("OPENAI_MODEL", "gpt-5.6-luna"),
            instructions="你是严谨的A股与海外资产映射研究员，只输出可解析JSON。",
            input=prompt,
        )
        raw = response.output_text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.I | re.M).strip()
        rows = json.loads(raw)
    except Exception:
        return {}

    output = {}
    for row in rows if isinstance(rows, list) else []:
        ticker = normalize_a_share_ticker(str(row.get("ticker") or ""))
        theme = row.get("theme") if row.get("theme") in allowed_themes else "中国增长与政策"
        relation = row.get("relation") if row.get("relation") in {"同向", "反向", "需判断"} else "需判断"
        assets = [item for item in row.get("overseas_assets", []) if item in allowed_assets][:4]
        if len(assets) < 2:
            assets = mapping_cfg.get(theme, {}).get("global_assets", [])[:4]
        output[ticker] = {
            **row,
            "ticker": ticker,
            "theme": theme,
            "relation": relation,
            "overseas_assets": assets,
            "keywords": [item for item in row.get("keywords", []) if str(item).strip()][:6],
            "profile_source": "AI自动研究",
        }
    return output


def enrich_watchlist_inputs(
    inputs: Iterable[str], defaults: Iterable[dict], universe: dict, mapping_cfg: dict
) -> tuple[list[dict], list[str]]:
    catalog = build_profile_catalog(defaults, universe, mapping_cfg)
    resolved: list[dict] = []
    errors: list[str] = []
    seen = set()

    for original in [str(value).strip() for value in inputs if str(value).strip()]:
        by_name = catalog.get(f"name:{original.lower()}")
        if by_name:
            ticker, name = by_name["ticker"], by_name["name"]
        else:
            ticker = normalize_a_share_ticker(original)
            if not ticker.endswith((".SS", ".SZ", ".BJ")):
                match = search_a_share_by_name(original)
                if not match:
                    errors.append(f"无法识别“{original}”，请改填6位A股代码。")
                    continue
                ticker, name = match
            else:
                name = ""
        if ticker in seen:
            continue
        resolved.append({"ticker": ticker, "name": name})
        seen.add(ticker)

    names = fetch_stock_names(row["ticker"] for row in resolved if not row.get("name"))
    unknown = []
    output = []
    for item in resolved:
        ticker = item["ticker"]
        known = catalog.get(ticker)
        if known:
            output.append(known)
            continue
        name = item.get("name") or names.get(ticker)
        if not name:
            errors.append(f"暂时无法取得{ticker.split('.')[0]}的证券名称，请稍后重试。")
            continue
        unknown.append({"ticker": ticker, "name": name})

    ai_rows = _ai_profiles(unknown, mapping_cfg, universe)
    for item in unknown:
        output.append(ai_rows.get(item["ticker"]) or _fallback_profile(item["ticker"], item["name"], mapping_cfg))

    order = {row["ticker"]: index for index, row in enumerate(resolved)}
    output = sorted(normalize_watchlist_rows(output), key=lambda row: order.get(row["ticker"], 999))
    return output, errors
