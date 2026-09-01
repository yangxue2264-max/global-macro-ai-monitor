from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.providers import FRED_SERIES, data_health, fetch_fred_snapshot, fetch_market_snapshot, fetch_news_bundle, fetch_price_history, flatten_watchlist, load_watchlist
from core.briefing import morning_rule_brief, radar_rank, build_a_share_mapping, morning_markdown
from core.ai import analyze_event, generate_ai_morning_brief
from core.ontology import MACRO_MODULES
from core.utils import fmt_num, fmt_pct, signal_emoji
from core.theme_monitor import ai_chain_snapshot, ai_chain_bottlenecks, theme_ledger_rows
from core.demo import demo_market, demo_macro, demo_news
from core.evidence import add_evidence_scores
from core.climate import fetch_enso_summary, agriculture_transmission
from core.cn_mapping import cn_watch_rows

BASE=Path(__file__).resolve().parent
CN_TZ=ZoneInfo("Asia/Shanghai")

st.set_page_config(page_title="Global Macro AI Monitor",page_icon="🌐",layout="wide",initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root { --muted:#6B7280; --border:rgba(17,24,39,.10); }
.block-container{padding-top:1.1rem;padding-bottom:2.5rem;max-width:1500px}
[data-testid="stMetric"]{border:1px solid var(--border);padding:12px 14px;border-radius:14px;background:white}
[data-testid="stMetricLabel"]{font-size:.82rem}
h1{letter-spacing:-.025em}
.section{font-size:1.05rem;font-weight:760;margin:12px 0 8px}
.muted{color:var(--muted);font-size:.82rem}
.card{border:1px solid var(--border);border-radius:14px;padding:14px 16px;background:#fff;margin-bottom:8px}
.kicker{font-size:.76rem;color:#6B7280;text-transform:uppercase;letter-spacing:.07em}
.bigline{font-size:1.03rem;font-weight:650;line-height:1.5}
.chain{font-size:.9rem;line-height:1.55;color:#374151}
.pill{display:inline-block;border:1px solid rgba(17,24,39,.13);border-radius:999px;padding:2px 8px;margin-right:5px;font-size:.72rem;color:#4B5563}
a{text-decoration:none}
</style>
""",unsafe_allow_html=True)

@st.cache_data(ttl=900,show_spinner=False)
def get_watch():
    cfg=load_watchlist(BASE/"config"/"watchlist.json")
    return cfg,flatten_watchlist(cfg)

@st.cache_data(ttl=900,show_spinner=False)
def get_market(universe): return fetch_market_snapshot(universe)

@st.cache_data(ttl=3600,show_spinner=False)
def get_macro(): return fetch_fred_snapshot(FRED_SERIES)

@st.cache_data(ttl=900,show_spinner=False)
def get_news(): return fetch_news_bundle(max_each=10)

cfg,universe=get_watch()
with open(BASE/"config"/"a_share_map.json","r",encoding="utf-8") as f:
    ashare_cfg=json.load(f)
with st.spinner("更新全球市场、宏观状态与新闻…"):
    market=get_market(universe); macro=get_macro(); news=get_news()
health=data_health(market,macro,news)

if health["market_ok"] < max(5, int(health["market_total"]*0.5)):
    st.warning("部分市场免费行情当前不可用；页面会保留结构，但请不要把缺失值当作真实市场信号。")

now=datetime.now(CN_TZ)
c1,c2=st.columns([5,1.2])
with c1:
    st.title("Global Macro AI Monitor")
    st.caption("A股开盘前 · 全球宏观 × 跨资产 × 主流个股 × AI传导分析")
    if DEMO_FALLBACK:
        st.warning("当前免费行情源不可用，页面自动切换到 DEMO FALLBACK。所有示例数值均非实时数据。", icon="⚠️")
with c2:
    st.metric("北京时间",now.strftime("%H:%M"))
    st.caption(now.strftime("%Y-%m-%d"))

tabs=st.tabs(["晨间一页","研究流","跨资产","宏观七维","AI资本开支","异动雷达","事件实验室","方法与数据"])

with tabs[0]:
    brief=morning_rule_brief(market,macro,news); states=brief["states"]
    st.markdown("#### 今日总判断"); st.info(brief["headline"])
    a,b,c,d,e=st.columns(5)
    a.metric("风险状态",brief["regime"],f"{brief['regime_score']:+.2f}")
    b.metric("S&P 500",fmt_num(market.get("SP500",{}).get("last")),fmt_pct(market.get("SP500",{}).get("change_pct")))
    c.metric("美元指数",fmt_num(market.get("DXY",{}).get("last")),fmt_pct(market.get("DXY",{}).get("change_pct")))
    d.metric("美国实际10Y",fmt_num(macro.get("USREAL10Y",{}).get("value")),f"{macro.get('USREAL10Y',{}).get('delta',0):+.2f}")
    e.metric("铜",fmt_num(market.get("COPPER",{}).get("last")),fmt_pct(market.get("COPPER",{}).get("change_pct")))
    left,right=st.columns([1.05,1])
    with left:
        st.markdown('<div class="section">市场隐含状态向量</div>',unsafe_allow_html=True)
        names=list(states.keys()); vals=list(states.values())
        fig=go.Figure()
        fig.add_trace(go.Scatterpolar(r=vals+[vals[0]],theta=names+[names[0]],fill="toself",name="状态"))
        fig.update_layout(height=330,margin=dict(l=30,r=30,t=20,b=20),polar=dict(radialaxis=dict(visible=True,range=[-2,2],tickvals=[-2,-1,0,1,2])),showlegend=False)
        st.plotly_chart(fig,use_container_width=True)
        st.caption("这是市场价格推导出的研究状态，不是对真实经济状态的机械估计。")
    with right:
        st.markdown('<div class="section">A股开盘前：五个验证点</div>',unsafe_allow_html=True)
        for i,x in enumerate(brief["checklist"],1): st.markdown(f"**{i}.** {x}")
        st.markdown('<div class="section">市场叙事 vs 价格</div>',unsafe_allow_html=True)
        for x in brief["divergences"][:3]: st.markdown(f"- {x}")
    st.markdown('<div class="section">全球资产温度计</div>',unsafe_allow_html=True)
    temp_keys=["SP500","NASDAQ","CSI300","HSI","NIKKEI","DXY","USDCNH","GOLD","COPPER","WTI","BTC"]
    rows=[]
    for k in temp_keys:
        x=market.get(k,{})
        rows.append({"信号":signal_emoji(x.get("change_pct")),"资产":x.get("name",k),"最新":x.get("last"),"日涨跌%":x.get("change_pct"),"5日%":x.get("change_5d_pct"),"20日%":x.get("change_20d_pct")})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,column_config={"最新":st.column_config.NumberColumn(format="%.2f"),"日涨跌%":st.column_config.NumberColumn(format="%.2f%%"),"5日%":st.column_config.NumberColumn(format="%.2f%%"),"20日%":st.column_config.NumberColumn(format="%.2f%%")})
    st.caption("免费市场数据可能延迟；FRED宏观数据按各序列最新发布日期更新。")

    st.markdown('<div class="section">A股开盘前映射</div>',unsafe_allow_html=True)
    ashare_rows=build_a_share_mapping(market,news,ashare_cfg)
    mapcols=st.columns(3)
    for i,r in enumerate(ashare_rows[:3]):
        with mapcols[i]:
            themes=" · ".join(r["a_share_themes"])
            verifies=" · ".join(r["verify"][:3])
            st.markdown(f"""<div class="card">
            <div class="kicker">研究优先级 {r['score']:.1f}</div>
            <div class="bigline">{r['name']}</div>
            <div class="chain" style="margin-top:6px">{r['logic']}</div>
            <div class="muted" style="margin-top:8px"><b>A股主题：</b>{themes}</div>
            <div class="muted" style="margin-top:6px"><b>验证：</b>{verifies}</div>
            </div>""",unsafe_allow_html=True)

    md_export=morning_markdown(brief,market,macro,ashare_rows)
    st.download_button("下载今日晨报 Markdown",data=md_export,file_name=f"morning_brief_{now.strftime('%Y%m%d')}.md",mime="text/markdown")

    st.markdown('<div class="section">今日事件 → 传导 → 资产</div>',unsafe_allow_html=True)
    evcols=st.columns(2)
    for i,ev in enumerate(brief["events"]):
        with evcols[i%2]:
            mods=" ".join([f'<span class="pill">{x}</span>' for x in ev.get("modules",[])[:2]])
            ths=" ".join([f'<span class="pill">{x}</span>' for x in ev.get("themes",[])[:2]])
            link=ev.get("url",""); title=ev.get("title",""); source=ev.get("source","")
            html=f"""<div class="card">
            <div class="kicker">{source} · evidence {ev.get("evidence_label","初步")}</div>
            <div class="bigline"><a href="{link}" target="_blank">{title}</a></div>
            <div style="margin:6px 0">{mods}{ths}</div>
            <div class="chain">{ev.get("mechanism","")}</div>
            </div>"""
            st.markdown(html,unsafe_allow_html=True)
    st.markdown('<div class="section">隔夜主题 → A股/中国资产观察池</div>',unsafe_allow_html=True)
    st.caption("只做传导验证，不把主题映射直接当成交易建议。")
    cn_rows = cn_watch_rows(news, market)
    if cn_rows:
        st.dataframe(
            pd.DataFrame(cn_rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "日涨跌%":st.column_config.NumberColumn(format="%.2f%%"),
                "20日%":st.column_config.NumberColumn(format="%.2f%%"),
            }
        )

    st.markdown('<div class="section">AI晨报（可选）</div>',unsafe_allow_html=True)
    with st.expander("生成AI版本：把价格、宏观状态和新闻重新压缩成研究结论"):
        market_text="; ".join(f"{market[k]['name']} {fmt_pct(market[k].get('change_pct'))}" for k in ["SP500","NASDAQ","DXY","USDCNH","GOLD","COPPER","WTI","BTC"] if k in market)
        news_text="\n".join(f"- {n.get('title')} | {n.get('source')}" for n in news[:12])
        if st.button("生成 AI 晨报",type="primary"):
            result=generate_ai_morning_brief(market_text,news_text,use_ai=True)
            if result: st.markdown(result)
            else: st.warning("尚未配置 OPENAI_API_KEY；当前页面的规则式晨报仍可正常使用。")


with tabs[1]:
    st.markdown("#### 研究流：机器筛信息，人只处理高价值事件")
    st.caption("不是按时间无限下拉新闻，而是先按宏观模块、研究主题和来源压缩，再进入传导分析。")
    module_options = ["全部"] + list(MACRO_MODULES.keys())
    theme_options = ["全部","AI资本开支","天气与农业","贸易与关税","油价与通胀","流动性与信用"]
    f1, f2 = st.columns(2)
    module_filter = f1.selectbox("宏观模块", module_options)
    theme_filter = f2.selectbox("研究主题", theme_options)

    filtered = []
    for n in news:
        if module_filter != "全部" and module_filter not in n.get("modules", []):
            continue
        if theme_filter != "全部" and theme_filter not in n.get("themes", []):
            continue
        filtered.append(n)

    if not filtered:
        st.info("当前筛选暂没有新闻；免费新闻源可能存在延迟。")

    for n in filtered[:24]:
        mods = " ".join([f'<span class="pill">{x}</span>' for x in n.get("modules", [])[:3]])
        ths = " ".join([f'<span class="pill">{x}</span>' for x in n.get("themes", [])[:2]])
        html = (
            '<div class="card">'
            f'<div class="kicker">{n.get("bucket","")} · {n.get("source","")} · score {n.get("score","")}</div>'
            f'<div class="bigline"><a href="{n.get("url","")}" target="_blank">{n.get("title","")}</a></div>'
            f'<div style="margin-top:7px">{mods}{ths}</div>'
            '</div>'
        )
        st.markdown(html, unsafe_allow_html=True)

with tabs[2]:
    st.markdown("#### 跨资产：不要只看一张股票走势图")
    groups=[("全球股指",list(cfg["indices"].keys())),("汇率",list(cfg["fx"].keys())),("商品",list(cfg["commodities"].keys())),("Crypto",list(cfg["crypto"].keys()))]
    for title,keys in groups:
        st.markdown(f"##### {title}")
        cols=st.columns(min(5,len(keys)))
        for i,k in enumerate(keys):
            x=market.get(k,{})
            cols[i%len(cols)].metric(x.get("name",k),fmt_num(x.get("last")),fmt_pct(x.get("change_pct")))
    st.divider()
    all_keys=list(cfg["indices"])+list(cfg["fx"])+list(cfg["commodities"])+list(cfg["crypto"])
    pick=st.selectbox("查看 6 个月走势",all_keys,format_func=lambda k:universe[k]["name"])
    hist=fetch_price_history(universe[pick]["ticker"],period="6mo")
    if not hist.empty:
        close=hist["Close"]
        if isinstance(close,pd.DataFrame): close=close.iloc[:,0]
        fig=go.Figure(go.Scatter(x=hist.index,y=close,mode="lines"))
        fig.update_layout(height=360,margin=dict(l=20,r=20,t=20,b=20),xaxis_title="",yaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
    else: st.warning("该资产行情暂时不可用。")

with tabs[3]:
    st.markdown("#### 宏观七维框架")
    st.caption("宏观不是指标清单，而是从状态变量到资产的传导系统。")
    for name,meta in MACRO_MODULES.items():
        with st.expander(f"{name}｜{meta['question']}",expanded=name in ["增长","金融状况","实体瓶颈"]):
            st.write(" · ".join(meta["items"]))
    st.markdown("##### 气候 → 农业 → 通胀：把导师举的厄尔尼诺例子做成真实模块")
    agri = agriculture_transmission(enso, market)
    e1,e2,e3 = st.columns([1.1,1,1])
    e1.metric("NOAA ENSO状态", enso.get("status","—")[:38])
    e2.metric("Niño-3.4", enso.get("nino34","—"))
    e3.metric("数据模式", "LIVE" if enso.get("mode")=="live" else "DEMO")
    st.write(enso.get("synopsis",""))
    st.caption(agri["chain"])
    st.info(agri["market_check"])
    with st.expander("下一步需要验证的数据"):
        for x in agri["next_checks"]:
            st.markdown(f"- {x}")
        st.markdown(f'[NOAA Climate Prediction Center 官方来源]({enso.get("url")})')

    st.markdown("##### 当前可自动更新的宏观状态")
    rows=[]
    for k,m in FRED_SERIES.items():
        x=macro.get(k,{})
        rows.append({"变量":m["name"],"最新":x.get("value"),"日/期变化":x.get("delta"),"单位":m["unit"],"发布日期":x.get("date")})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)


with tabs[4]:
    st.markdown("#### AI资本开支链：从模型追到物理世界与融资端")
    st.caption("把会议材料里的核心逻辑做成可监控结构：AI不是单一科技板块，而是资本开支、能源、电网、商品、信用与估值的共同变量。")

    chain_df = pd.DataFrame(ai_chain_snapshot(market, macro))
    st.dataframe(
        chain_df,
        hide_index=True,
        use_container_width=True,
        column_config={"20日代理变化%": st.column_config.NumberColumn(format="%.2f%%")}
    )

    st.markdown("##### 当前需要调查的瓶颈 / 背离")
    for x in ai_chain_bottlenecks(market, macro):
        st.markdown(f"- {x}")

    st.markdown("##### 主题台账")
    ledger_df = pd.DataFrame(theme_ledger_rows(market, macro))
    st.dataframe(
        ledger_df,
        hide_index=True,
        use_container_width=True,
        column_config={"20日资产确认%": st.column_config.NumberColumn(format="%.2f%%")}
    )

    st.markdown("##### AI链条代理资产")
    ai_keys = ["NVDA","SMH","VRT","GRID","XLU","DLR","COPPER","NATGAS"]
    cols = st.columns(4)
    for i, k in enumerate(ai_keys):
        x = market.get(k, {})
        cols[i % 4].metric(x.get("name", k), fmt_num(x.get("last")), fmt_pct(x.get("change_20d_pct")))

with tabs[5]:
    st.markdown("#### 异动雷达")
    st.caption("第一版用“收益异常 z-score + 成交量异常 + 当日绝对涨跌”识别，不以主观新闻热度替代价格。")
    keys=list(cfg["stocks"].keys()); ranked=radar_rank(market,keys)
    df=pd.DataFrame([{"排名":i+1,"公司":r["name"],"主题":r["theme"],"最新":r["last"],"日涨跌%":r["day"],"20日%":r["d20"],"收益z":r["z"],"量比":r["volume_ratio"],"异动分":r["score"]} for i,r in enumerate(ranked)])
    st.dataframe(df,hide_index=True,use_container_width=True,column_config={"最新":st.column_config.NumberColumn(format="%.2f"),"日涨跌%":st.column_config.NumberColumn(format="%.2f%%"),"20日%":st.column_config.NumberColumn(format="%.2f%%"),"收益z":st.column_config.NumberColumn(format="%.2f"),"量比":st.column_config.NumberColumn(format="%.2f"),"异动分":st.column_config.ProgressColumn(min_value=0,max_value=4,format="%.2f")})
    st.info("后续版本会加入：动态入池、新闻事件聚类、财报/指引、A股盘前映射。")

with tabs[6]:
    st.markdown("#### 事件实验室")
    st.caption("输入任何宏观、政策、产业或天气事件，强制转成“可验证的因果链”。")
    examples=["厄尔尼诺概率显著上升","Hyperscaler上调AI资本开支指引","美国扩大先进芯片出口限制","油价两周内快速上涨"]
    chosen=st.selectbox("快速例子",["自定义"]+examples); default="" if chosen=="自定义" else chosen
    event=st.text_area("事件",value=default,height=90,placeholder="例如：大型云厂商上调未来一年AI资本开支…")
    use_ai=st.toggle("调用 OpenAI",value=True)
    if st.button("生成传导链",type="primary",disabled=not event.strip()):
        context=f"S&P500 {fmt_pct(market.get('SP500',{}).get('change_pct'))}; DXY {fmt_pct(market.get('DXY',{}).get('change_pct'))}; Copper {fmt_pct(market.get('COPPER',{}).get('change_pct'))}; US real 10Y {fmt_num(macro.get('USREAL10Y',{}).get('value'))}%"
        with st.spinner("构建因果链…"): st.markdown(analyze_event(event,market_context=context,use_ai=use_ai))

with tabs[7]:
    st.markdown("#### 产品逻辑")
    st.markdown("""
**目标不是“替你预测市场”，而是把有限注意力配置到最值得验证的变量上。**

每天开盘前的最小闭环：

**全球发生了什么 → 哪些状态变量改变 → 通过什么机制传导 → 哪些资产已经反应 → 哪些资产尚未反应 → 今天验证什么**

1. **机器做高频工作：** 拉行情、宏观数据、新闻去重、初步分类、异动筛选；
2. **AI做结构化工作：** 把事件放入因果链、区分事实/推断、找二阶变量和反证；
3. **人做判断：** 决定哪个叙事值得相信、仓位和风险如何处理。
""")
    st.markdown("#### 数据健康")
    st.json(health)
    asof_rows=[]
    for k in ["SP500","NASDAQ","CSI300","HSI","DXY","GOLD","COPPER","WTI"]:
        x=market.get(k,{})
        asof_rows.append({
            "资产":x.get("name",k),
            "行情日期":x.get("asof",""),
            "状态":x.get("status","")
        })
    st.dataframe(pd.DataFrame(asof_rows),hide_index=True,use_container_width=True)
    st.markdown("#### 当前免费数据")
    st.write("- Yahoo Finance / yfinance：跨资产与个股（非交易级）")
    st.write("- FRED：美国利率、通胀预期、信用与流动性状态")
    st.write("- NOAA CPC：ENSO官方诊断，用于气候→农业→食品通胀传导")
    st.write("- GDELT：全球新闻标题/来源；失败时回退 Google News RSS")
    st.write("- OpenAI Responses API：可选AI传导与晨报")
    st.write("- 证据分层：来源质量 + 信息结构化程度 + 跨来源确认；DEMO不参与置信度判断")
    st.warning("免费数据可能延迟、缺失或临时不可用。本项目用于研究与信息整理，不构成投资建议。")
