from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.ai import ai_status, analyze_event, generate_ai_morning_brief
from core.briefing import build_a_share_mapping, morning_markdown, morning_rule_brief, radar_rank, top_event_cards
from core.climate import agriculture_transmission, fetch_enso_summary
from core.demo import demo_macro, demo_market, demo_news
from core.evidence import add_evidence_scores
from core.market_context import enrich_macro_with_market_proxies, source_label
from core.ontology import MACRO_MODULES
from core.providers import (
    FRED_SERIES, data_health, fetch_fred_snapshot, fetch_market_snapshot,
    fetch_news_bundle, fetch_price_history, flatten_watchlist, load_watchlist,
)
from core.research_memory import memory_summary
from core.theme_monitor import ai_chain_bottlenecks, ai_chain_snapshot, theme_ledger_rows
from core.utils import fmt_num, fmt_pct, signal_emoji

BASE = Path(__file__).resolve().parent
CN_TZ = ZoneInfo("Asia/Shanghai")

st.set_page_config(page_title="Global Macro AI Monitor", page_icon="🌐", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
:root{--ink:#101828;--muted:#667085;--border:#e4e7ec;--soft:#f8fafc;--blue:#155eef;--green:#067647}
.block-container{padding-top:.65rem;padding-bottom:3rem;max-width:1440px}header[data-testid="stHeader"]{height:2.2rem;background:transparent}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.02em}h1{margin-bottom:.1rem;font-size:2rem}
[data-testid="stMetric"]{border:1px solid var(--border);padding:11px 13px;border-radius:12px;background:#fff}[data-testid="stMetricLabel"]{font-size:.78rem;color:var(--muted)}
.subhead{color:var(--muted);font-size:.9rem;margin:-.2rem 0 .55rem}.statusbar{display:flex;gap:8px;flex-wrap:wrap;margin:.25rem 0 .75rem}
.badge{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:4px 9px;font-size:.72rem;color:#344054;background:#fff}.badge.live{background:#ecfdf3;color:var(--green);border-color:#abefc6}.badge.warn{background:#fffaeb;color:#b54708;border-color:#fedf89}
.section{font-size:1.05rem;font-weight:750;margin:1.15rem 0 .55rem;color:var(--ink)}.card{border:1px solid var(--border);border-radius:13px;padding:14px 15px;background:#fff;height:100%;margin-bottom:9px}
.card-title{font-size:1rem;font-weight:720;line-height:1.4;color:var(--ink)}.kicker{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}
.body{font-size:.86rem;line-height:1.55;color:#344054}.muted{font-size:.75rem;color:var(--muted);line-height:1.45}.fact{border-left:3px solid #84adff;padding-left:10px;margin:7px 0}.verify{border-left:3px solid #75e0a7;padding-left:10px;margin:7px 0}
.pill{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 7px;margin:2px 4px 2px 0;font-size:.69rem;color:#475467;background:var(--soft)}div[data-testid="stRadio"]>div{gap:.35rem}div[data-testid="stRadio"] label{border:1px solid var(--border);border-radius:9px;padding:4px 10px;background:white}
a{text-decoration:none}.stDataFrame{border:1px solid var(--border);border-radius:12px;overflow:hidden}@media(max-width:800px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:1.65rem}}
</style>
""", unsafe_allow_html=True)


def finite(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def metric_delta(value, suffix=""):
    value = finite(value)
    return None if value is None else f"{value:+.2f}{suffix}"


@st.cache_data(ttl=900, show_spinner=False)
def load_config():
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    with open(BASE / "config" / "a_share_map.json", "r", encoding="utf-8") as handle:
        ashare = json.load(handle)
    return cfg, flatten_watchlist(cfg), ashare


@st.cache_data(ttl=900, show_spinner=False)
def load_snapshot(universe):
    with ThreadPoolExecutor(max_workers=3) as pool:
        market_future = pool.submit(fetch_market_snapshot, universe)
        macro_future = pool.submit(fetch_fred_snapshot, FRED_SERIES)
        news_future = pool.submit(fetch_news_bundle, 8)
        return market_future.result(), macro_future.result(), news_future.result()


@st.cache_data(ttl=3600, show_spinner=False)
def load_enso():
    return fetch_enso_summary()


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker):
    return fetch_price_history(ticker, period="6mo")


def market_context_text(market, macro):
    keys = ["SP500", "NASDAQ", "RUSSELL", "DXY", "USDCNH", "GOLD", "COPPER", "WTI", "BTC", "SMH", "VRT", "GRID"]
    rows = []
    for key in keys:
        item = market.get(key, {})
        rows.append(f"{item.get('name', key)}: 1日 {fmt_pct(item.get('change_pct'))}; 5日 {fmt_pct(item.get('change_5d_pct'))}; 20日 {fmt_pct(item.get('change_20d_pct'))}")
    for key in ["US10Y", "USREAL10Y", "BREAKEVEN10Y", "VIX", "HYSPREAD", "NFCI"]:
        item = macro.get(key, {})
        rows.append(f"{item.get('name', key)}: {fmt_num(item.get('value'))} ({source_label(item)})")
    return "\n".join(rows)


def pricing_check(theme, market):
    mapping = {
        "AI资本开支": ["SMH", "VRT", "GRID", "COPPER"], "流动性与信用": ["DXY", "SP500", "BTC"],
        "油价与通胀": ["WTI", "XLE", "GOLD"], "天气与农业": ["CORN", "SOY"],
        "贸易与关税": ["USDCNH", "TSM", "BABA"],
    }
    parts = []
    for key in mapping.get(theme, ["SP500", "DXY"]):
        item = market.get(key, {})
        parts.append(f"{item.get('name', key)} {fmt_pct(item.get('change_pct'))}")
    return "；".join(parts)


cfg, universe, ashare_cfg = load_config()
st.title("Global Macro AI Monitor")
st.markdown('<div class="subhead">A股开盘前研究工作台 · 事实 → 状态变量 → 传导 → 定价 → 验证</div>', unsafe_allow_html=True)
load_notice = st.empty()
load_notice.info("正在同步行情、宏观与研究流；三类数据并行更新。")
if os.getenv("MACRO_MONITOR_OFFLINE_TEST") == "1":
    market, macro, news = demo_market(universe), demo_macro(FRED_SERIES), demo_news()
else:
    market, macro, news = load_snapshot(universe)
health = data_health(market, macro, news)
demo_mode = health.get("market_live", 0) == 0
if demo_mode:
    market, macro, news = demo_market(universe), demo_macro(FRED_SERIES), demo_news()
macro = enrich_macro_with_market_proxies(macro, market)
news = add_evidence_scores(news)
health = data_health(market, macro, news)
load_notice.empty()

now = datetime.now(CN_TZ)
ai = ai_status()
market_ratio = f"{health.get('market_live', 0)}/{health.get('market_total', 0)}"
macro_available = sum(1 for value in macro.values() if value.get("status") in {"ok", "market_proxy", "derived"})
macro_ratio = f"{macro_available}/{len(macro)}"
badges = [
    f'<span class="badge {"warn" if demo_mode else "live"}">{"DEMO" if demo_mode else "LIVE"} 行情 {market_ratio}</span>',
    f'<span class="badge {"live" if macro_available else "warn"}">宏观 {macro_ratio}</span>',
    f'<span class="badge {"live" if ai["connected"] else "warn"}">AI {escape(ai["model"] if ai["connected"] else "未连接")}</span>',
    f'<span class="badge">北京时间 {now:%m-%d %H:%M}</span>',
]
st.markdown(f'<div class="statusbar">{"".join(badges)}</div>', unsafe_allow_html=True)
if demo_mode:
    st.warning("免费行情源当前整体不可用，页面处于明确标注的演示模式；演示值不会被当作实时判断。")

page = st.radio("主导航", ["晨间简报", "研究流", "跨资产", "主题监控", "事件实验室", "方法与数据"], horizontal=True, label_visibility="collapsed")


if page == "晨间简报":
    brief = morning_rule_brief(market, macro, news)
    states = brief["states"]
    st.markdown('<div class="section">今日总判断</div>', unsafe_allow_html=True)
    st.info(brief["headline"])
    cols = st.columns(6)
    cols[0].metric("市场状态", brief["regime"], metric_delta(brief["regime_score"]))
    cols[1].metric("S&P 500", fmt_num(market.get("SP500", {}).get("last")), fmt_pct(market.get("SP500", {}).get("change_pct")))
    cols[2].metric("美元指数", fmt_num(market.get("DXY", {}).get("last")), fmt_pct(market.get("DXY", {}).get("change_pct")))
    real = macro.get("USREAL10Y", {})
    cols[3].metric(f"实际10Y · {source_label(real)}", fmt_num(real.get("value")), metric_delta(real.get("delta"), "pp"))
    cols[4].metric("USD/CNH", fmt_num(market.get("USDCNH", {}).get("last"), 4), fmt_pct(market.get("USDCNH", {}).get("change_pct")))
    cols[5].metric("铜", fmt_num(market.get("COPPER", {}).get("last")), fmt_pct(market.get("COPPER", {}).get("change_pct")))

    st.markdown('<div class="section">今天最值得回答的三个问题</div>', unsafe_allow_html=True)
    focus_cols = st.columns(3)
    for col, item in zip(focus_cols, brief["focus"]):
        with col:
            st.markdown(f'''<div class="card"><div class="kicker">research question</div><div class="card-title">{escape(item["title"])}</div><div class="fact body"><b>现在：</b>{escape(item["now"])}</div><div class="body"><b>意义：</b>{escape(item["why"])}</div><div class="verify body"><b>验证：</b>{escape(item["verify"])}</div></div>''', unsafe_allow_html=True)

    left, right = st.columns([1, 1.25])
    with left:
        st.markdown('<div class="section">市场隐含状态</div>', unsafe_allow_html=True)
        names, values = list(states.keys()), list(states.values())
        colors = ["#17b26a" if value > .2 else "#f04438" if value < -.2 else "#98a2b3" for value in values]
        fig = go.Figure(go.Bar(x=values, y=names, orientation="h", marker_color=colors, text=[f"{x:+.2f}" for x in values], textposition="auto"))
        fig.update_layout(height=330, margin=dict(l=5, r=15, t=10, b=10), xaxis=dict(range=[-2, 2], zeroline=True), yaxis=dict(autorange="reversed"), showlegend=False)
        st.plotly_chart(fig, width="stretch")
        st.caption("市场价格推导的研究状态，不是对真实经济状态的机械估计。")
    with right:
        st.markdown('<div class="section">开盘前验证清单</div>', unsafe_allow_html=True)
        for index, item in enumerate(brief["checklist"], 1):
            st.markdown(f"**{index}.** {item}")
        st.markdown("**当前背离**")
        for item in brief["divergences"][:2]:
            st.markdown(f"- {item}")

    st.markdown('<div class="section">隔夜资产温度计</div>', unsafe_allow_html=True)
    temp_keys = ["SP500", "NASDAQ", "RUSSELL", "DXY", "USDCNH", "GOLD", "COPPER", "WTI", "BTC"]
    temp_rows = []
    for key in temp_keys:
        item = market.get(key, {})
        temp_rows.append({"信号": signal_emoji(item.get("change_pct")), "资产": item.get("name", key), "最新": item.get("last"), "1日%": item.get("change_pct"), "5日%": item.get("change_5d_pct"), "20日%": item.get("change_20d_pct"), "截至": item.get("asof", "")})
    st.dataframe(pd.DataFrame(temp_rows), hide_index=True, width="stretch", column_config={"最新": st.column_config.NumberColumn(format="%.2f"), "1日%": st.column_config.NumberColumn(format="%.2f%%"), "5日%": st.column_config.NumberColumn(format="%.2f%%"), "20日%": st.column_config.NumberColumn(format="%.2f%%")})

    st.markdown('<div class="section">海外事件 → A股验证</div>', unsafe_allow_html=True)
    ashare_rows = build_a_share_mapping(market, news, ashare_cfg)
    map_cols = st.columns(3)
    for col, row in zip(map_cols, ashare_rows[:3]):
        with col:
            st.markdown(f'''<div class="card"><div class="kicker">优先级 {row["score"]:.1f} · {escape(row["pricing"])}</div><div class="card-title">{escape(row["name"])}</div><div class="body" style="margin-top:6px">{escape(row["logic"])}</div><div class="muted" style="margin-top:8px"><b>A股：</b>{escape(" · ".join(row["a_share_themes"][:4]))}</div><div class="muted" style="margin-top:6px"><b>下一验证：</b>{escape(" · ".join(row["verify"][:3]))}</div></div>''', unsafe_allow_html=True)

    memory = memory_summary(BASE, brief)
    with st.expander(f"研究记忆｜{memory['title']}"):
        for item in memory["items"]:
            st.markdown(f"- {item}")
    export = morning_markdown(brief, market, macro, ashare_rows)
    action1, action2 = st.columns([1, 3])
    action1.download_button("下载晨报 Markdown", data=export, file_name=f"morning_brief_{now:%Y%m%d}.md", mime="text/markdown", width="stretch")
    with action2.expander("AI 压缩版（按需生成，避免每次刷新产生费用）"):
        if not ai["connected"]:
            st.warning("OPENAI_API_KEY 尚未连接。")
        if st.button("生成 90 秒可读 AI 晨报", type="primary", disabled=not ai["connected"]):
            news_text = "\n".join(f"- {item.get('title')} | {item.get('source')} | 证据{item.get('evidence_label')}" for item in news[:12])
            with st.spinner("压缩事实、定价与验证点…"):
                result = generate_ai_morning_brief(market_context_text(market, macro), news_text, use_ai=True)
            st.markdown(result or "AI 暂未返回结果，请稍后重试。")


elif page == "研究流":
    st.markdown("#### 研究流｜先压缩，再判断")
    st.caption("同一事件的转载已合并；每条信息按事实、传导、定价和下一验证组织。")
    f1, f2 = st.columns(2)
    module_filter = f1.selectbox("宏观模块", ["全部"] + list(MACRO_MODULES.keys()))
    theme_filter = f2.selectbox("研究主题", ["全部", "AI资本开支", "天气与农业", "贸易与关税", "油价与通胀", "流动性与信用"])
    filtered = [item for item in news if (module_filter == "全部" or module_filter in item.get("modules", [])) and (theme_filter == "全部" or theme_filter in item.get("themes", []))]
    cards = top_event_cards(filtered, limit=12)
    if not cards:
        st.info("当前筛选没有高价值事件。")
    for item in cards:
        theme = item.get("theme_primary", "待分类")
        tags = "".join(f'<span class="pill">{escape(tag)}</span>' for tag in (item.get("modules", [])[:2] + item.get("themes", [])[:2]))
        st.markdown(f'''<div class="card"><div class="kicker">{escape(item.get("source", ""))} · 证据 {escape(item.get("evidence_label", "初步"))}</div><div class="card-title"><a href="{escape(item.get("url", ""))}" target="_blank">{escape(item.get("title", ""))}</a></div><div style="margin:5px 0">{tags}</div><div class="fact body"><b>为何重要：</b>{escape(item.get("mechanism", "待建立传导链"))}</div><div class="body"><b>价格检查：</b>{escape(pricing_check(theme, market))}</div><div class="verify body"><b>下一步：</b>核对原始来源、事件规模、市场预期差与二阶资产是否确认。</div></div>''', unsafe_allow_html=True)


elif page == "跨资产":
    st.markdown("#### 跨资产｜方向、期限与背离")
    groups = [("全球股指", list(cfg["indices"])), ("汇率", list(cfg["fx"])), ("商品", list(cfg["commodities"])), ("Crypto", list(cfg["crypto"]))]
    for title, keys in groups:
        st.markdown(f"##### {title}")
        cols = st.columns(min(5, len(keys)))
        for index, key in enumerate(keys):
            item = market.get(key, {})
            cols[index % len(cols)].metric(item.get("name", key), fmt_num(item.get("last")), fmt_pct(item.get("change_pct")))
    st.divider()
    all_keys = list(cfg["indices"]) + list(cfg["fx"]) + list(cfg["commodities"]) + list(cfg["crypto"])
    pick = st.selectbox("6个月走势", all_keys, format_func=lambda key: universe[key]["name"])
    if st.button("加载走势图"):
        history = load_history(universe[pick]["ticker"])
        if history.empty:
            st.warning("该资产历史行情暂时不可用。")
        else:
            close = history["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            fig = go.Figure(go.Scatter(x=history.index, y=close, mode="lines", line=dict(color="#155eef", width=2)))
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=15, b=10), xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, width="stretch")
    else:
        st.caption("走势图按需加载，不再拖慢每次冷启动。")


elif page == "主题监控":
    theme_page = st.radio("主题页", ["宏观七维", "AI Capex", "异动雷达"], horizontal=True)
    if theme_page == "宏观七维":
        st.markdown("#### 宏观七维｜从变量到资产")
        for name, meta in MACRO_MODULES.items():
            with st.expander(f"{name}｜{meta['question']}", expanded=name in ["金融状况", "实体瓶颈"]):
                st.write(" · ".join(meta["items"]))
        rows = []
        for key, meta in FRED_SERIES.items():
            item = macro.get(key, {})
            rows.append({"变量": meta["name"], "最新": item.get("value"), "变化": item.get("delta"), "来源层级": source_label(item), "发布日期": item.get("date", ""), "具体来源": item.get("source", "FRED" if item.get("status") == "ok" else "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={"最新": st.column_config.NumberColumn(format="%.3f"), "变化": st.column_config.NumberColumn(format="%.3f")})
        st.markdown("##### 气候 → 农业 → 食品通胀")
        if st.button("加载 NOAA ENSO 官方诊断"):
            enso = load_enso()
            agri = agriculture_transmission(enso, market)
            e1, e2, e3 = st.columns(3)
            e1.metric("ENSO状态", enso.get("status", "—")[:40])
            e2.metric("Niño-3.4", enso.get("nino34", "—"))
            e3.metric("数据模式", "LIVE" if enso.get("mode") == "live" else "DEMO")
            st.write(enso.get("synopsis", ""))
            st.info(agri["market_check"])
            st.caption(agri["chain"])
        else:
            st.caption("NOAA 模块按需加载，避免影响首页速度。")
    elif theme_page == "AI Capex":
        st.markdown("#### AI Money Flow｜需求 → 算力 → 电力 → 原料 → 融资")
        st.caption("价格代理用于发现需要调查的环节，不等同于企业基本面或资本开支数据。")
        st.dataframe(pd.DataFrame(ai_chain_snapshot(market, macro)), hide_index=True, width="stretch", column_config={"20日代理变化%": st.column_config.NumberColumn(format="%.2f%%")})
        st.markdown("##### 当前瓶颈与背离")
        for item in ai_chain_bottlenecks(market, macro):
            st.markdown(f"- {item}")
        st.markdown("##### 主题台账")
        st.dataframe(pd.DataFrame(theme_ledger_rows(market, macro)), hide_index=True, width="stretch", column_config={"20日资产确认%": st.column_config.NumberColumn(format="%.2f%%")})
    else:
        st.markdown("#### 异动雷达｜价格先于叙事")
        ranked = radar_rank(market, list(cfg["stocks"]))
        rows = [{"排名": index + 1, "公司": row["name"], "主题": row["theme"], "最新": row["last"], "1日%": row["day"], "20日%": row["d20"], "收益z": row["z"], "量比": row["volume_ratio"], "异动分": row["score"]} for index, row in enumerate(ranked)]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={"最新": st.column_config.NumberColumn(format="%.2f"), "1日%": st.column_config.NumberColumn(format="%.2f%%"), "20日%": st.column_config.NumberColumn(format="%.2f%%"), "收益z": st.column_config.NumberColumn(format="%.2f"), "量比": st.column_config.NumberColumn(format="%.2f"), "异动分": st.column_config.ProgressColumn(min_value=0, max_value=4, format="%.2f")})


elif page == "事件实验室":
    st.markdown("#### 事件实验室｜把标题变成可证伪链条")
    examples = ["厄尔尼诺概率显著上升", "Hyperscaler上调AI资本开支指引", "美国扩大先进芯片出口限制", "油价两周内快速上涨"]
    chosen = st.selectbox("快速例子", ["自定义"] + examples)
    event = st.text_area("事件", value="" if chosen == "自定义" else chosen, height=90, placeholder="例如：大型云厂商上调未来一年AI资本开支…")
    mode = st.radio("分析模式", ["快速结构化", "Research（联网核实）"], horizontal=True, help="Research 模式会更慢、费用略高，并尝试核实最新公开信息。")
    st.caption(f"AI状态：{'已连接 · ' + ai['model'] if ai['connected'] else '未连接，将使用规则模板'}")
    if st.button("生成传导链", type="primary", disabled=not event.strip()):
        with st.spinner("核对事实并构建传导链…" if mode.startswith("Research") else "构建可验证传导链…"):
            result = analyze_event(event, market_context=market_context_text(market, macro), use_ai=ai["connected"], research_mode=mode.startswith("Research"))
        st.markdown(result)


else:
    st.markdown("#### 方法、来源与数据健康")
    st.markdown("""
**每天开盘前的最小闭环：** 全球发生了什么 → 哪些状态变量改变 → 通过什么机制传导 → 哪些资产已经反应 → 哪些尚未反应 → 今天验证什么。

- 机器负责拉取、去重、分类和异动筛选；
- AI负责结构化因果链、区分事实与推断、提出反证；
- 人负责判断叙事、风险与行动。
""")
    h1, h2, h3 = st.columns(3)
    h1.metric("可用市场资产", market_ratio)
    h2.metric("可用宏观变量", macro_ratio)
    h3.metric("研究流事件", len(news))
    st.markdown("##### 数据来源层级")
    st.write("- **官方：** FRED、NOAA CPC；宏观发布日期与行情日期分开显示。")
    st.write("- **市场代理：** Yahoo Finance；当官方序列缺失时只做明确标注的代理或推导。")
    st.write("- **新闻发现：** GDELT，失败时回退 Google News RSS；同一转载事件合并。")
    st.write("- **AI：** OpenAI Responses API，仅在用户主动生成晨报或事件分析时调用。")
    st.json(health)
    st.warning("免费数据可能延迟、缺失或临时不可用。本项目用于研究与信息整理，不构成投资建议。")
