from __future__ import annotations

from collections import defaultdict
import numpy as np
import pandas as pd

from .ontology import THEMES


def _finite(value, default=np.nan):
    try:
        value=float(value)
        return value if np.isfinite(value) else default
    except Exception:
        return default

def _x(d,key,field):
    try: return float(d[key][field])
    except Exception: return np.nan

def _clip(v,lo=-2,hi=2):
    if v is None or np.isnan(v): return 0.0
    return float(np.clip(v,lo,hi))

def market_implied_states(market,macro):
    sp20=_x(market,"SP500","change_20d_pct")
    ndx20=_x(market,"NASDAQ","change_20d_pct")
    copper20=_x(market,"COPPER","change_20d_pct")
    oil20=_x(market,"WTI","change_20d_pct")
    dxy20=_x(market,"DXY","change_20d_pct")
    gold20=_x(market,"GOLD","change_20d_pct")
    btc20=_x(market,"BTC","change_20d_pct")
    vix=_x(macro,"VIX","value")
    hy=_x(macro,"HYSPREAD","value")
    real10=_x(macro,"USREAL10Y","value")
    bei=_x(macro,"BREAKEVEN10Y","value")
    nfci=_x(macro,"NFCI","value")

    growth=np.mean([_clip(sp20/8),_clip(copper20/10),_clip(ndx20/10)])
    inflation=np.mean([_clip((bei-2.2)/0.35 if not np.isnan(bei) else 0),_clip(oil20/12),_clip(copper20/14)])
    financial=np.mean([_clip((20-vix)/7 if not np.isnan(vix) else 0),_clip((4.0-hy)/1.2 if not np.isnan(hy) else 0),_clip(-nfci/0.4 if not np.isnan(nfci) else 0),_clip(-dxy20/4)])
    duration=np.mean([_clip(-(real10-1.5)/0.7 if not np.isnan(real10) else 0),_clip(ndx20/10)])
    ai_capex=np.mean([_clip(ndx20/8),_clip(copper20/10)])
    dollar_liq=np.mean([_clip(-dxy20/4),_clip((20-vix)/8 if not np.isnan(vix) else 0),_clip(btc20/15)])
    hard_assets=np.mean([_clip(gold20/10),_clip(copper20/12),_clip(oil20/15)])
    return {
        "增长":round(float(growth),2),"通胀压力":round(float(inflation),2),
        "金融条件宽松":round(float(financial),2),"久期友好":round(float(duration),2),
        "AI资本开支":round(float(ai_capex),2),"美元流动性":round(float(dollar_liq),2),
        "实物资产":round(float(hard_assets),2)
    }

def risk_regime(market,macro):
    s=market_implied_states(market,macro)
    score=s["金融条件宽松"]*.35+s["增长"]*.25+s["久期友好"]*.20+s["美元流动性"]*.20
    label="风险偏好" if score>=.65 else "偏防御" if score<=-.65 else "信号分化"
    return label,round(float(score),2)

def radar_rank(market,keys=None):
    keys=keys or list(market.keys()); rows=[]
    for k in keys:
        x=market.get(k,{})
        z=abs(x.get("ret_z",np.nan)); vr=x.get("volume_ratio",np.nan); day=abs(x.get("change_pct",np.nan))
        z=0 if np.isnan(z) else min(z,4)
        vr_component=0 if np.isnan(vr) else max(0,min(vr-1,3))
        day=0 if np.isnan(day) else min(day/2,4)
        score=z*.6+vr_component*.2+day*.2
        rows.append({"key":k,"name":x.get("name",k),"group":x.get("group",""),"theme":x.get("theme",""),"last":x.get("last",np.nan),"day":x.get("change_pct",np.nan),"d20":x.get("change_20d_pct",np.nan),"z":x.get("ret_z",np.nan),"volume_ratio":x.get("volume_ratio",np.nan),"score":round(float(score),2)})
    return sorted(rows,key=lambda x:x["score"],reverse=True)

def detect_cross_asset_divergences(market,macro):
    out=[]
    def val(k,f="change_pct"): return _x(market,k,f)
    sp,ndx,dxy,gold,copper,wti=[val(k) for k in ["SP500","NASDAQ","DXY","GOLD","COPPER","WTI"]]
    real=_x(macro,"USREAL10Y","value"); vix=_x(macro,"VIX","value"); hy=_x(macro,"HYSPREAD","value")
    if not np.isnan(sp) and not np.isnan(dxy) and sp>.5 and dxy>.4: out.append("美股与美元同涨：可能是美国增长/盈利优势，而不是典型全球流动性 Risk-on。")
    if not np.isnan(ndx) and not np.isnan(real) and ndx>.8 and real>2.0: out.append("高实际利率下科技股仍强：盈利/AI叙事正在压过久期逆风，需关注估值脆弱性。")
    if not np.isnan(gold) and not np.isnan(dxy) and gold>.6 and dxy>.3: out.append("黄金与美元同涨：避险/央行需求可能比传统美元因子更重要。")
    if not np.isnan(copper) and not np.isnan(wti) and copper>.8 and wti<-.8: out.append("铜强油弱：更像电气化/AI基础设施的结构性需求，而非传统总需求全面走强。")
    if not np.isnan(vix) and not np.isnan(hy) and vix<18 and hy>4.5: out.append("股票波动率平静但信用利差偏高：风险资产内部存在背离。")
    if not out: out.append("暂未识别到高置信度跨资产背离；重点观察利率、美元、铜和科技股是否出现新的共振。")
    return out

def top_event_cards(news,limit=6):
    cards=[]
    for n in news:
        theme=n.get("themes",[None])[0] if n.get("themes") else None
        module=n.get("modules",[None])[0] if n.get("modules") else None
        mechanism=THEMES[theme]["mechanism"] if theme in THEMES else "事件 → 现金流 / 贴现率 / 风险溢价 / 供需约束 → 行业与资产"
        cards.append({**n,"theme_primary":theme or "待分类","module_primary":module or "待分类","mechanism":mechanism})
    result=[]; seen=defaultdict(int)
    for c in cards:
        key=(c["theme_primary"],c.get("bucket",""))
        if seen[key]>=2: continue
        seen[key]+=1; result.append(c)
        if len(result)>=limit: break
    return result

def morning_rule_brief(market,macro,news):
    regime,score=risk_regime(market,macro); states=market_implied_states(market,macro); divs=detect_cross_asset_divergences(market,macro)
    def pct(k):
        v=_x(market,k,"change_pct"); return "—" if np.isnan(v) else f"{v:+.2f}%"
    def mval(k):
        v=_x(macro,k,"value"); return "—" if np.isnan(v) else f"{v:.2f}"
    hy_value=_x(macro,"HYSPREAD","value")
    credit_proxy=_x(macro,"CREDIT_PROXY","value")
    credit_text=f"HY OAS {hy_value:.2f}%" if not np.isnan(hy_value) else f"HYG-LQD 20日代理 {credit_proxy:+.2f}pp" if not np.isnan(credit_proxy) else "信用数据待确认"
    stance="隔夜市场偏风险偏好，但要区分“流动性驱动”与“盈利/AI驱动”。" if regime=="风险偏好" else "隔夜市场偏防御，A股开盘前优先检查美元、实际利率与信用是否继续收紧。" if regime=="偏防御" else "隔夜信号分化，单一股指方向不足以概括市场，重点看跨资产共振与背离。"
    headline=f"{stance} S&P 500 {pct('SP500')}，Nasdaq {pct('NASDAQ')}，美元 {pct('DXY')}，铜 {pct('COPPER')}，黄金 {pct('GOLD')}。"
    checklist=[
        f"贴现率：US10Y {mval('US10Y')}%，实际10Y {mval('USREAL10Y')}%。",
        f"风险溢价：VIX {mval('VIX')}，{credit_text}。",
        f"人民币外部条件：USD/CNY代理 {pct('USDCNH')}，美元指数 {pct('DXY')}。",
        f"AI实体约束：铜 {pct('COPPER')}，天然气 {pct('NATGAS')}，AI核心股异动见雷达。",
        "新闻必须先回答“影响现金流、贴现率、风险溢价还是供给约束”，再映射资产。"
    ]
    focus = build_focus_cards(market, macro, news, divs)
    return {"headline":headline,"regime":regime,"regime_score":score,"states":states,"divergences":divs,"checklist":checklist,"events":top_event_cards(news,6),"focus":focus}


def build_focus_cards(market, macro, news, divergences=None):
    """Three research questions for the morning, ranked by observed signals."""
    divergences = divergences or []
    day = lambda key: _finite(market.get(key,{}).get("change_pct"),0.0)
    d20 = lambda key: _finite(market.get(key,{}).get("change_20d_pct"),0.0)
    real = _finite(macro.get("USREAL10Y",{}).get("value"))
    vix = _finite(macro.get("VIX",{}).get("value"))

    cards=[]
    pressure=abs(day("DXY"))+abs(day("SP500"))+abs(day("NASDAQ"))
    cards.append({
        "score":pressure,
        "title":"金融条件是否继续收紧？",
        "now":f"美元 {day('DXY'):+.2f}%，Nasdaq {day('NASDAQ'):+.2f}%" + (f"，实际10Y {real:.2f}%" if np.isfinite(real) else "，实际利率待确认"),
        "why":"美元、实际利率与风险资产的共振决定外部流动性压力。",
        "verify":"看 USD/CNH、美国长端利率、VIX 与高收益信用是否同向。",
    })
    ai_score=abs(d20("SMH"))+abs(d20("VRT"))+abs(d20("COPPER"))
    cards.append({
        "score":ai_score/3,
        "title":"AI Capex 是否从芯片扩散到实体？",
        "now":f"半导体 {d20('SMH'):+.2f}%，电力设备 {d20('VRT'):+.2f}%，铜 {d20('COPPER'):+.2f}%（20日）",
        "why":"只有算力、电力、电网与原料共同确认，才是更完整的资本开支周期。",
        "verify":"看 hyperscaler 指引、服务器/光模块、电网设备与铜能否接力。",
    })
    risk_score=abs(day("WTI"))+abs(day("GOLD"))+(abs(vix-20)/5 if np.isfinite(vix) else 0)
    cards.append({
        "score":risk_score,
        "title":"油价冲击是供给风险还是增长信号？",
        "now":f"WTI {day('WTI'):+.2f}%，黄金 {day('GOLD'):+.2f}%" + (f"，VIX {vix:.1f}" if np.isfinite(vix) else "，VIX待确认"),
        "why":"供给冲击与需求走强对通胀、利率和A股行业利润的含义相反。",
        "verify":"看期限结构、库存、通胀预期及航空/化工等成本敏感板块。",
    })
    if divergences:
        cards[0]["divergence"]=divergences[0]
    return sorted(cards,key=lambda x:x["score"],reverse=True)[:3]


def build_a_share_mapping(market, news, mapping_cfg):
    """
    Returns ranked research mappings for A-share pre-open use.
    This is thematic research, not stock recommendations.
    """
    news_themes = []
    for n in news:
        news_themes.extend(n.get("themes", []))

    def abs_move(key):
        return abs(_finite(market.get(key,{}).get("change_pct"),0.0))

    rows = []
    for name, cfg in mapping_cfg.items():
        score = 0.0
        if name in news_themes:
            score += 1.5
        # soft matching from known theme names
        if name == "AI资本开支" and "AI资本开支" in news_themes:
            score += 1.5
        if name == "油价与通胀" and "油价与通胀" in news_themes:
            score += 1.5
        if name == "天气与农业" and "天气与农业" in news_themes:
            score += 1.5
        for k in cfg.get("trigger_assets",[]):
            score += min(abs_move(k)/1.5, 1.0)
        moves=[_finite(market.get(k,{}).get("change_20d_pct")) for k in cfg.get("trigger_assets",[])]
        moves=[abs(v) for v in moves if np.isfinite(v)]
        avg20=float(np.mean(moves)) if moves else np.nan
        pricing="高度交易" if np.isfinite(avg20) and avg20>=10 else "部分确认" if np.isfinite(avg20) and avg20>=3 else "尚未确认"
        rows.append({**cfg, "name":name, "score":round(float(score),2),"pricing":pricing,"pricing_move":avg20})
    return sorted(rows, key=lambda x:x["score"], reverse=True)

def morning_markdown(brief, market, macro, ashare_rows):
    def pct(k):
        try:
            v=float(market.get(k,{}).get("change_pct"))
            return f"{v:+.2f}%"
        except Exception:
            return "—"
    lines = [
        "# Global Macro AI Monitor｜A股开盘前晨报",
        "",
        f"**总判断：** {brief['headline']}",
        "",
        "## 跨资产快照",
        f"- S&P 500: {pct('SP500')}",
        f"- Nasdaq 100: {pct('NASDAQ')}",
        f"- DXY: {pct('DXY')}",
        f"- USD/CNH: {pct('USDCNH')}",
        f"- Gold: {pct('GOLD')}",
        f"- Copper: {pct('COPPER')}",
        f"- WTI: {pct('WTI')}",
        "",
        "## A股开盘前验证点",
    ]
    lines += [f"{i}. {x}" for i,x in enumerate(brief["checklist"],1)]
    lines += ["", "## A股主题映射"]
    for r in ashare_rows[:3]:
        lines += [
            f"### {r['name']}",
            f"- 逻辑：{r['logic']}",
            f"- 主题：{'、'.join(r['a_share_themes'])}",
            f"- 验证：{'、'.join(r['verify'])}",
        ]
    lines += ["", "> 研究与信息整理，不构成投资建议。"]
    return "\n".join(lines)
