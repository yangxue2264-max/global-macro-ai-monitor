from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.ai import ai_status, analyze_event, generate_ai_morning_brief
from core.briefing import morning_rule_brief, radar_rank, top_event_cards
from core.climate import agriculture_transmission, fetch_enso_summary
from core.decision_engine import cross_market_gaps, decision_queue, evaluate_theses, one_page_markdown
from core.demo import demo_macro, demo_market, demo_news
from core.evidence import add_evidence_scores
from core.market_context import enrich_macro_with_market_proxies, source_label
from core.ontology import MACRO_MODULES, THEMES
from core.providers import (
    FRED_SERIES, data_health, fetch_fred_snapshot, fetch_market_snapshot,
    fetch_news_bundle, fetch_price_history, fetch_treasury_snapshot,
    flatten_watchlist, load_watchlist,
)
from core.research_memory import memory_summary
from core.theme_monitor import ai_chain_bottlenecks, ai_chain_snapshot
from core.utils import finite, fmt_num, fmt_pct, signal_emoji

BASE = Path(__file__).resolve().parent
CN_TZ = ZoneInfo("Asia/Shanghai")

st.set_page_config(page_title="Global-to-A Share Decision Monitor", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
:root{--ink:#101828;--muted:#667085;--border:#e4e7ec;--soft:#f8fafc;--blue:#175cd3;--green:#067647;--amber:#b54708;--red:#b42318}
.block-container{padding-top:.8rem;padding-bottom:3rem;max-width:1480px}header[data-testid="stHeader"]{height:2.1rem;background:transparent}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.025em}.hero{padding:12px 0 8px}.eyebrow{font-size:.72rem;font-weight:750;color:var(--blue);letter-spacing:.12em;text-transform:uppercase}.hero-title{font-size:2.05rem;font-weight:780;line-height:1.15;color:var(--ink);margin:5px 0}.hero-sub{font-size:.92rem;color:var(--muted);max-width:900px;line-height:1.55}
.statusbar{display:flex;gap:7px;flex-wrap:wrap;margin:.35rem 0 .8rem}.badge{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:4px 9px;font-size:.71rem;color:#344054;background:#fff}.badge.live{background:#ecfdf3;color:var(--green);border-color:#abefc6}.badge.warn{background:#fffaeb;color:var(--amber);border-color:#fedf89}
[data-testid="stMetric"]{border:1px solid var(--border);padding:12px 14px;border-radius:13px;background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.03)}[data-testid="stMetricLabel"]{font-size:.76rem;color:var(--muted)}
.section{font-size:1.07rem;font-weight:760;margin:1.2rem 0 .55rem;color:var(--ink)}.section-note{font-size:.75rem;color:var(--muted);font-weight:400;margin-left:7px}
.card{border:1px solid var(--border);border-radius:14px;padding:15px 16px;background:#fff;height:100%;margin-bottom:9px;box-shadow:0 1px 2px rgba(16,24,40,.035)}.card.priority{border-top:3px solid #84adff}.card.thesis{border-left:4px solid #d0d5dd}
.card-title{font-size:.98rem;font-weight:740;line-height:1.42;color:var(--ink)}.kicker{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}.body{font-size:.84rem;line-height:1.58;color:#344054}.muted{font-size:.73rem;color:var(--muted);line-height:1.48}.fact{border-left:3px solid #84adff;padding-left:9px;margin:8px 0}.verify{border-left:3px solid #75e0a7;padding-left:9px;margin:8px 0}.invalidate{border-left:3px solid #fda29b;padding-left:9px;margin:8px 0}
.pill{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 7px;margin:2px 4px 2px 0;font-size:.67rem;color:#475467;background:var(--soft)}.pill.green{color:#067647;background:#ecfdf3;border-color:#abefc6}.pill.amber{color:#b54708;background:#fffaeb;border-color:#fedf89}.pill.red{color:#b42318;background:#fef3f2;border-color:#fecdca}
.callout{border:1px solid #b2ddff;background:#f5fbff;border-radius:14px;padding:15px 17px;color:#194185;font-size:.92rem;line-height:1.58}.formula{border:1px solid var(--border);background:var(--soft);border-radius:12px;padding:12px 14px;font-size:.78rem;color:#475467}
div[data-testid="stRadio"]>div{gap:.35rem;flex-wrap:wrap}div[data-testid="stRadio"] label{border:1px solid var(--border);border-radius:9px;padding:4px 10px;background:white}.stDataFrame{border:1px solid var(--border);border-radius:12px;overflow:hidden}a{text-decoration:none}
@media(max-width:800px){.block-container{padding-left:1rem;padding-right:1rem}.hero-title{font-size:1.62rem}.hero-sub{font-size:.84rem}}
</style>
""", unsafe_allow_html=True)


def metric_delta(value, suffix=""):
    number = finite(value)
    return None if number is None else f"{number:+.2f}{suffix}"


def status_pill(status):
    css = "green" if status in {"同步确认", "获得确认"} else "red" if status in {"方向背离", "受到挑战"} else "amber" if status in {"关注缺口", "证据混合", "A股先行"} else ""
    return f'<span class="pill {css}">{escape(status)}</span>'


@st.cache_data(ttl=900, show_spinner=False)
def load_config():
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    ashare = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    theses = json.loads((BASE / "config" / "thesis_book.json").read_text(encoding="utf-8"))
    return cfg, flatten_watchlist(cfg), ashare, theses


@st.cache_data(ttl=900, show_spinner=False)
def load_snapshot(universe):
    with ThreadPoolExecutor(max_workers=4) as pool:
        market_future = pool.submit(fetch_market_snapshot, universe)
        macro_future = pool.submit(fetch_fred_snapshot, FRED_SERIES)
        news_future = pool.submit(fetch_news_bundle, 8)
        treasury_future = pool.submit(fetch_treasury_snapshot)
        return market_future.result(), macro_future.result(), news_future.result(), treasury_future.result()


@st.cache_data(ttl=3600, show_spinner=False)
def load_enso():
    return fetch_enso_summary()


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker):
    return fetch_price_history(ticker, period="6mo")


def market_context_text(market, macro):
    lines = []
    for key in ["SP500", "NASDAQ", "DXY", "USDCNH", "GOLD", "COPPER", "WTI", "SMH", "VRT", "GRID"]:
        item = market.get(key, {})
        lines.append(f"{item.get('name', key)}: 1日 {fmt_pct(item.get('change_pct'))}; 20日 {fmt_pct(item.get('change_20d_pct'))}")
    for key in ["US10Y", "USREAL10Y", "BREAKEVEN10Y", "VIX", "HYSPREAD", "NFCI"]:
        item = macro.get(key, {})
        lines.append(f"{item.get('name', key)}: {fmt_num(item.get('value'))} ({source_label(item)})")
    return "\n".join(lines)


def pricing_check(theme, market):
    mapping = {
        "AI资本开支": ["SMH", "VRT", "GRID", "COPPER"], "流动性与信用": ["DXY", "SP500", "BTC"],
        "油价与通胀": ["WTI", "XLE", "GOLD"], "天气与农业": ["CORN", "SOY"],
        "贸易与关税": ["USDCNH", "TSM", "BABA"], "中国增长与政策": ["USDCNH", "HSI", "CSI300"],
    }
    return "；".join(f"{market.get(key, {}).get('name', key)} {fmt_pct(market.get(key, {}).get('change_pct'))}" for key in mapping.get(theme, ["SP500", "DXY"]))


cfg, universe, ashare_cfg, thesis_cfg = load_config()
st.markdown("""<div class="hero"><div class="eyebrow">Research operating system · A-share pre-open</div><div class="hero-title">Global-to-A Share Decision Monitor</div><div class="hero-sub">不是多一个行情看板：把海外事件压缩为研究优先级，识别跨市场定价缺口，并持续记录哪些假设正在被证实或推翻。</div></div>""", unsafe_allow_html=True)

load_notice = st.empty()
load_notice.info("正在并行同步市场、宏观与研究流…")
if os.getenv("MACRO_MONITOR_OFFLINE_TEST") == "1":
    market, macro, news, treasury = demo_market(universe), demo_macro(FRED_SERIES), demo_news(), {}
else:
    market, macro, news, treasury = load_snapshot(universe)
raw_health = data_health(market, macro, news)
demo_mode = raw_health.get("market_live", 0) == 0
if demo_mode:
    market, macro, news = demo_market(universe), demo_macro(FRED_SERIES), demo_news()
macro = enrich_macro_with_market_proxies(macro, market, treasury)
news = add_evidence_scores(news)
health = data_health(market, macro, news)
load_notice.empty()

now = datetime.now(CN_TZ)
ai = ai_status()
brief = morning_rule_brief(market, macro, news)
all_gaps = cross_market_gaps(market, news, ashare_cfg)
queue = decision_queue(market, news, ashare_cfg)
theses = evaluate_theses(market, macro, thesis_cfg)
market_ratio = f"{health.get('market_live', 0)}/{health.get('market_total', 0)}"
macro_available = sum(1 for item in macro.values() if item.get("status") in {"ok", "treasury", "market_proxy", "derived"})
macro_ratio = f"{macro_available}/{len(macro)}"
badges = [
    f'<span class="badge {"warn" if demo_mode else "live"}">{"DEMO" if demo_mode else "LIVE"} 行情 {market_ratio}</span>',
    f'<span class="badge {"live" if macro_available else "warn"}">宏观 {macro_ratio}</span>',
    f'<span class="badge {"live" if ai["connected"] else "warn"}">AI {escape(ai["model"] if ai["connected"] else "未连接")}</span>',
    f'<span class="badge">北京时间 {now:%m-%d %H:%M}</span>', '<span class="badge">15分钟缓存 · 按需AI</span>',
]
st.markdown(f'<div class="statusbar">{"".join(badges)}</div>', unsafe_allow_html=True)
if demo_mode:
    st.warning("免费行情源本次未返回有效数据，当前为明确标注的演示模式；演示值不会被作为真实判断输出。")

page = st.radio("主导航", ["决策台", "信号流", "定价缺口", "跨资产", "主题账本", "事件实验室", "方法与数据"], horizontal=True, label_visibility="collapsed")


if page == "决策台":
    confirmed = sum(row["status"] == "获得确认" for row in theses)
    cols = st.columns(4)
    cols[0].metric("隔夜市场状态", brief["regime"], metric_delta(brief["regime_score"]))
    cols[1].metric("最高研究优先级", f"{queue[0]['priority']}/100" if queue else "—", queue[0]["name"] if queue else None)
    cols[2].metric("首要跨市场状态", queue[0]["status"] if queue else "—", "不是收益预测")
    cols[3].metric("获确认的主题假设", f"{confirmed}/{len(theses)}", "其余需复核")
    st.markdown('<div class="section">今日总判断</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="callout">{escape(brief["headline"])}</div>', unsafe_allow_html=True)

    st.markdown('<div class="section">今天不是“看什么”，而是“判断什么”<span class="section-note">按研究优先级排序</span></div>', unsafe_allow_html=True)
    decision_cols = st.columns(3)
    for index, (col, row) in enumerate(zip(decision_cols, queue), 1):
        breakdown = "".join(f'<span class="pill">{escape(key)} {value}</span>' for key, value in row["score_breakdown"].items())
        with col:
            st.markdown(f'''<div class="card priority"><div class="kicker">#{index} · PRIORITY {row["priority"]}/100 {status_pill(row["status"])}</div><div class="card-title">{escape(row["question"])}</div><div style="margin:7px 0">{breakdown}</div><div class="fact body"><b>现在：</b>{escape(row["now"])}</div><div class="body"><b>传导：</b>{escape(row["logic"])}</div><div class="verify body"><b>下一验证：</b>{escape(row["next_check"])}</div><div class="invalidate muted"><b>降低权重：</b>{escape(row["invalidation"])}</div></div>''', unsafe_allow_html=True)

    left, right = st.columns([1.18, 1])
    with left:
        st.markdown('<div class="section">跨市场定价缺口</div>', unsafe_allow_html=True)
        gap_rows = [{"主题": row["name"], "优先级": row["priority"], "状态": row["status"], "海外20日中位数%": row["global_median"], "A股20日中位数%": row["china_median"], "证据分": row["evidence"], "关联事件": row["event_count"]} for row in all_gaps[:5]]
        st.dataframe(pd.DataFrame(gap_rows), hide_index=True, width="stretch", column_config={"优先级": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "海外20日中位数%": st.column_config.NumberColumn(format="%+.2f%%"), "A股20日中位数%": st.column_config.NumberColumn(format="%+.2f%%"), "证据分": st.column_config.NumberColumn(format="%d/100")})
        st.caption("缺口用于决定先研究什么；它不等于买卖信号，也不假设A股一定追随海外。")
    with right:
        st.markdown('<div class="section">叙事压力测试</div>', unsafe_allow_html=True)
        for divergence in brief["divergences"][:3]:
            st.markdown(f"- {divergence}")
        challenged = [row for row in theses if row["status"] in {"受到挑战", "证据混合"}]
        if challenged:
            st.markdown("**需要降低确信度**")
            for row in challenged[:2]:
                st.markdown(f"- {row['name']}：{row['status']}；反证检查：{row['invalidation']}")

    st.markdown('<div class="section">导师每天如何使用</div>', unsafe_allow_html=True)
    workflow_cols = st.columns(3)
    workflow = [("08:45–09:05", "先定问题", "只读前三项决策队列，确认海外变化、证据等级和关键背离。"), ("09:15–09:25", "再看A股验证", "观察人民币、集合竞价与主题代理；确认跟随、背离还是已提前定价。"), ("收盘后 5分钟", "记录结果", "回到主题账本，检查反证条件，并把未验证叙事降权。")]
    for col, (time_label, title, body) in zip(workflow_cols, workflow):
        col.markdown(f'<div class="card"><div class="kicker">{time_label}</div><div class="card-title">{title}</div><div class="body">{body}</div></div>', unsafe_allow_html=True)

    export = one_page_markdown(brief, queue, theses, now.strftime("%Y-%m-%d %H:%M 中国时间"))
    action1, action2 = st.columns([1, 2.2])
    action1.download_button("下载一页决策简报", data=export, file_name=f"decision_brief_{now:%Y%m%d}.md", mime="text/markdown", width="stretch")
    with action2.expander("生成90秒AI晨报（按需调用，避免刷新即计费）"):
        if not ai["connected"]:
            st.info("配置 OPENAI_API_KEY 后可用；没有AI时，规则式决策台仍完整运行。")
        if st.button("生成AI压缩版", type="primary", disabled=not ai["connected"]):
            news_text = "\n".join(f"- {item.get('title')} | {item.get('source')} | {item.get('evidence_label')}" for item in news[:12])
            with st.spinner("正在区分事实、定价与待验证假设…"):
                result = generate_ai_morning_brief(market_context_text(market, macro), news_text, use_ai=True)
            st.markdown(result or "AI暂未返回结果，请稍后重试。")


elif page == "信号流":
    st.markdown('<div class="section">信号流<span class="section-note">新闻只是入口，必须进入可验证传导链</span></div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    module_filter = f1.selectbox("宏观模块", ["全部"] + list(MACRO_MODULES))
    theme_filter = f2.selectbox("研究主题", ["全部"] + list(THEMES))
    evidence_filter = f3.selectbox("最低证据等级", ["全部", "A/B", "A"])
    def evidence_ok(item):
        score = item.get("evidence_score", 0)
        return evidence_filter == "全部" or (evidence_filter == "A/B" and score >= 70) or (evidence_filter == "A" and score >= 85)
    filtered = [item for item in news if (module_filter == "全部" or module_filter in item.get("modules", [])) and (theme_filter == "全部" or theme_filter in item.get("themes", [])) and evidence_ok(item)]
    cards = top_event_cards(filtered, limit=15)
    if not cards:
        st.info("当前筛选下没有事件。")
    for item in cards:
        theme = item.get("theme_primary", "待分类")
        title = escape(item.get("title", ""))
        if item.get("url"):
            title = f'<a href="{escape(item["url"])}" target="_blank">{title}</a>'
        tags = "".join(f'<span class="pill">{escape(tag)}</span>' for tag in (item.get("modules", [])[:2] + item.get("themes", [])[:2]))
        st.markdown(f'''<div class="card"><div class="kicker">{escape(item.get("source", ""))} · {escape(item.get("evidence_label", "待核实"))}</div><div class="card-title">{title}</div><div style="margin:5px 0">{tags}</div><div class="fact body"><b>传导假设：</b>{escape(item.get("mechanism", "待建立因果链"))}</div><div class="body"><b>价格检查：</b>{escape(pricing_check(theme, market))}</div><div class="verify body"><b>下一步：</b>回到原始来源，确认规模、预期差与二阶变量。</div><div class="muted">证据说明：{escape(item.get("evidence_reason", ""))}</div></div>''', unsafe_allow_html=True)


elif page == "定价缺口":
    st.markdown('<div class="section">跨市场定价缺口<span class="section-note">本产品最核心的差异化页面</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="callout"><b>核心问题：</b>海外已经发生并被价格确认的变化，是否传导到了A股？若没有，是时差、结构差异、国内因子抵消，还是叙事本身错误？</div>', unsafe_allow_html=True)
    st.markdown(" ")
    overview = [{"主题": row["name"], "研究优先级": row["priority"], "状态": row["status"], "海外方向": row["global_direction"], "海外20日%": row["global_median"], "A股方向": row["china_direction"], "A股20日%": row["china_median"], "证据": row["evidence"], "事件数": row["event_count"]} for row in all_gaps]
    st.dataframe(pd.DataFrame(overview), hide_index=True, width="stretch", column_config={"研究优先级": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "海外20日%": st.column_config.NumberColumn(format="%+.2f%%"), "A股20日%": st.column_config.NumberColumn(format="%+.2f%%"), "证据": st.column_config.NumberColumn(format="%d/100")})
    selected_name = st.selectbox("展开一个主题", [row["name"] for row in all_gaps])
    selected = next(row for row in all_gaps if row["name"] == selected_name)
    lcol, rcol = st.columns([1.25, 1])
    with lcol:
        st.markdown(f"#### {selected['name']} {status_pill(selected['status'])}", unsafe_allow_html=True)
        st.write(selected["logic"])
        st.markdown(f"**A股观察对象：** {'、'.join(selected['a_share_themes'])}")
        st.markdown("**下一验证**")
        for item in selected["verify"]:
            st.markdown(f"- {item}")
        st.error(f"反证条件：{selected['invalidation']}")
    with rcol:
        labels = ["海外代理中位数", "A股代理中位数"]
        values = [selected["global_median"] or 0, selected["china_median"] or 0]
        fig = go.Figure(go.Bar(x=labels, y=values, marker_color=["#175cd3", "#0e7090"], text=[f"{value:+.2f}%" for value in values], textposition="auto"))
        fig.update_layout(height=285, margin=dict(l=10, r=10, t=15, b=10), yaxis_title="20日变化中位数%", showlegend=False)
        st.plotly_chart(fig, width="stretch")
        st.caption(f"海外代理：{' · '.join(selected['global_assets'])}｜A股代理：{' · '.join(selected['a_share_assets'])}")
    breakdown = selected["score_breakdown"]
    st.markdown(f'<div class="formula"><b>研究优先级 {selected["priority"]}/100</b> = 证据 {breakdown["证据"]} + 海外异动 {breakdown["海外异动"]} + 定价缺口 {breakdown["定价缺口"]} + A股相关性 {breakdown["A股相关性"]}。该分数只决定研究顺序。</div>', unsafe_allow_html=True)


elif page == "跨资产":
    st.markdown('<div class="section">跨资产验证<span class="section-note">验证叙事，不替代通用行情终端</span></div>', unsafe_allow_html=True)
    key_assets = ["SP500", "NASDAQ", "RUSSELL", "DXY", "USDCNH", "GOLD", "COPPER", "WTI", "BTC", "SMH", "VRT", "GRID"]
    asset_rows = []
    for key in key_assets:
        item = market.get(key, {})
        asset_rows.append({"信号": signal_emoji(item.get("change_pct")), "资产": item.get("name", key), "最新": item.get("last"), "1日%": item.get("change_pct"), "5日%": item.get("change_5d_pct"), "20日%": item.get("change_20d_pct"), "日期": item.get("asof", "")})
    st.dataframe(pd.DataFrame(asset_rows), hide_index=True, width="stretch", column_config={"最新": st.column_config.NumberColumn(format="%.2f"), "1日%": st.column_config.NumberColumn(format="%+.2f%%"), "5日%": st.column_config.NumberColumn(format="%+.2f%%"), "20日%": st.column_config.NumberColumn(format="%+.2f%%")})
    c1, c2 = st.columns([1, 1])
    with c1:
        pick = st.selectbox("加载6个月走势", key_assets, format_func=lambda key: universe[key]["name"])
        if st.button("加载走势图"):
            history = load_history(universe[pick]["ticker"])
            if history.empty:
                st.warning("该资产历史行情暂不可用。")
            else:
                close = history["Close"]
                if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
                fig = go.Figure(go.Scatter(x=history.index, y=close, mode="lines", line=dict(color="#175cd3", width=2)))
                fig.update_layout(height=335, margin=dict(l=10, r=10, t=15, b=10), xaxis_title="", yaxis_title="")
                st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("##### 当前跨资产背离")
        for item in brief["divergences"]: st.markdown(f"- {item}")
    with st.expander("宏观数据与来源层级"):
        rows = []
        for key, meta in FRED_SERIES.items():
            item = macro.get(key, {})
            rows.append({"变量": meta["name"], "最新": item.get("value"), "变化": item.get("delta"), "来源层级": source_label(item), "发布日期": item.get("date", ""), "具体来源": item.get("source", "FRED" if item.get("status") == "ok" else "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("股票异动雷达"):
        ranked = radar_rank(market, list(cfg["stocks"]))[:20]
        rows = [{"排名": i + 1, "公司": row["name"], "主题": row["theme"], "1日%": row["day"], "20日%": row["d20"], "收益z": row["z"], "量比": row["volume_ratio"], "异动分": row["score"]} for i, row in enumerate(ranked)]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


elif page == "主题账本":
    st.markdown('<div class="section">可证伪主题账本<span class="section-note">看板显示现在；账本检验过去的判断</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="callout">每条主题必须写明时间尺度、支持证据和反证条件。价格只算一票；若反证持续出现，应降低叙事权重，而不是不断换理由。</div>', unsafe_allow_html=True)
    st.markdown(" ")
    for row in theses:
        ratio = None if row["pass_ratio"] is None else round(row["pass_ratio"] * 100)
        ratio_text = "—" if ratio is None else f"{ratio}%"
        st.markdown(f'<div class="card thesis"><div class="kicker">{escape(row["horizon"])} · 规则通过 {ratio_text} {status_pill(row["status"])}</div><div class="card-title">{escape(row["name"])}</div><div class="body" style="margin-top:6px">{escape(row["why"])}</div><div class="invalidate body"><b>反证：</b>{escape(row["invalidation"])}</div></div>', unsafe_allow_html=True)
        check_rows = []
        for check in row["checks"]:
            observed = "—" if check["observed"] is None else f"{check['observed']:.2f}"
            result = "✓ 通过" if check["passed"] is True else "✕ 未通过" if check["passed"] is False else "○ 待数据"
            check_rows.append({"验证项": check["label"], "观察值": observed, "规则": f"{check['key']}.{check['field']} {check['op']} {check['value']}", "结果": result})
        st.dataframe(pd.DataFrame(check_rows), hide_index=True, width="stretch")
    st.markdown("##### AI资本开支链条：哪里最强，哪里最弱")
    st.dataframe(pd.DataFrame(ai_chain_snapshot(market, macro)), hide_index=True, width="stretch", column_config={"20日代理变化%": st.column_config.NumberColumn(format="%+.2f%%")})
    for item in ai_chain_bottlenecks(market, macro): st.markdown(f"- {item}")
    memory = memory_summary(BASE, brief)
    with st.expander(f"昨日判断复盘｜{memory['title']}"):
        for item in memory["items"]: st.markdown(f"- {item}")


elif page == "事件实验室":
    st.markdown('<div class="section">事件实验室<span class="section-note">把一个标题变成可被推翻的研究链条</span></div>', unsafe_allow_html=True)
    examples = ["厄尔尼诺概率显著上升", "Hyperscaler上调AI资本开支指引", "美国扩大先进芯片出口限制", "油价两周内快速上涨"]
    chosen = st.selectbox("快速例子", ["自定义"] + examples)
    event = st.text_area("事件", value="" if chosen == "自定义" else chosen, height=90, placeholder="例如：大型云厂商上调未来一年AI资本开支…")
    mode = st.radio("分析模式", ["快速结构化", "Research（联网核实）"], horizontal=True)
    st.caption(f"AI状态：{'已连接 · ' + ai['model'] if ai['connected'] else '未连接，将使用规则模板'}")
    if st.button("生成传导链", type="primary", disabled=not event.strip()):
        with st.spinner("核对事实并构建传导链…" if mode.startswith("Research") else "构建可验证传导链…"):
            result = analyze_event(event, market_context=market_context_text(market, macro), use_ai=ai["connected"], research_mode=mode.startswith("Research"))
        st.markdown(result)
    st.markdown("##### 气候事件专用验证")
    if st.button("加载NOAA ENSO官方诊断"):
        enso = load_enso(); agri = agriculture_transmission(enso, market)
        e1, e2, e3 = st.columns(3)
        e1.metric("ENSO状态", enso.get("status", "—")[:40]); e2.metric("Niño-3.4", enso.get("nino34", "—")); e3.metric("数据模式", "LIVE" if enso.get("mode") == "live" else "DEMO")
        st.write(enso.get("synopsis", "")); st.info(agri["market_check"]); st.caption(agri["chain"])


else:
    st.markdown('<div class="section">方法与数据<span class="section-note">让导师知道结论是如何形成的</span></div>', unsafe_allow_html=True)
    comparison = pd.DataFrame([
        {"普通市场看板": "把价格、新闻和图表放在一起", "本产品": "先排出今天必须回答的三个问题"},
        {"普通市场看板": "显示哪个资产涨跌", "本产品": "解释事件如何穿过状态变量并传到A股"},
        {"普通市场看板": "强调同步和覆盖面", "本产品": "专门寻找海外与A股之间的定价差与方向背离"},
        {"普通市场看板": "每天刷新后忘记昨天", "本产品": "用主题账本、反证条件和昨日快照追踪判断质量"},
        {"普通市场看板": "AI总结新闻", "本产品": "AI只做结构化与反方审查；规则评分可复核"},
    ])
    st.dataframe(comparison, hide_index=True, width="stretch")
    st.markdown("##### 研究闭环")
    st.markdown("**事实来源 → 状态变量 → 传导机制 → 海外价格确认 → A股映射 → 反证条件 → 次日复盘**")
    st.markdown('<div class="formula"><b>研究优先级（0–100）</b> = 证据质量（30）+ 海外异动（25）+ 跨市场缺口（25）+ A股相关性（20）。<br>分数用于排序调查顺序，不是收益预测、目标价或交易信号。</div>', unsafe_allow_html=True)
    st.markdown("##### 数据来源与刷新策略")
    st.write("- **官方宏观：** FRED；缺失时优先使用美国财政部收益率曲线并明确标注。")
    st.write("- **市场代理：** Yahoo Finance；展示行情日期，不把代理序列伪装成官方数据。")
    st.write("- **新闻发现：** GDELT，失败时回退Google News RSS；证据分只衡量来源层级，不保证结论正确。")
    st.write("- **气候：** NOAA CPC官方ENSO诊断，按需加载。")
    st.write("- **AI：** 仅在用户主动生成晨报或事件分析时调用；基础决策台不依赖AI。")
    st.write("- **刷新：** 行情、宏观与研究流缓存15分钟；自动晨报脚本可在A股开盘前生成每日快照。")
    h1, h2, h3 = st.columns(3)
    h1.metric("可用市场资产", market_ratio); h2.metric("可用宏观变量", macro_ratio); h3.metric("研究流事件", len(news))
    st.json(health)
    st.warning("免费数据可能延迟、缺失或临时不可用。本项目用于研究与信息整理，不构成投资建议。")
