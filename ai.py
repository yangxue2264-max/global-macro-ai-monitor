from __future__ import annotations
import os
from .ontology import THEMES, find_theme, tag_modules

SYSTEM = """你是一个跨资产全球宏观研究助手。你的任务不是复述新闻，而是把信息压缩成可验证的投资研究链条。
必须区分：事实、推断、市场定价、待验证假设。不要给出买入卖出指令。"""

def _fallback_event(event):
    theme=find_theme(event); modules=tag_modules(event); cfg=THEMES.get(theme,{})
    mechanism=cfg.get("mechanism","事件 → 现金流 / 贴现率 / 风险溢价 / 供需约束 → 行业与资产")
    assets="、".join(cfg.get("assets",[])) or "相关股指、行业、利率、汇率、商品"
    module_text="、".join(modules[:3]) if modules else "待分类"
    return f"""### 事件定义
{event}

### 宏观归类
{module_text}

### 核心传导链
{mechanism}

### 资产映射
{assets}

### 需要验证
1. 原始信息源是否可靠、事件规模是多少；
2. 市场是否已经提前定价；
3. 影响是一次性冲击还是会改变未来现金流；
4. 是否存在更强的利率、美元、政策或流动性因子；
5. 未来24小时与1–3个月分别用什么数据验证。

### 反证条件
如果相关资产价格、基本面数据和二阶变量没有按传导链变化，应降低该叙事的权重。

> 规则式研究模板；不构成投资建议。"""

def _get_client():
    key=os.getenv("OPENAI_API_KEY",""); model=os.getenv("OPENAI_MODEL","gpt-5.6-luna")
    if not key:
        try:
            import streamlit as st
            key=st.secrets.get("OPENAI_API_KEY",""); model=st.secrets.get("OPENAI_MODEL",model)
        except Exception: pass
    if not key: return None,model
    from openai import OpenAI
    return OpenAI(api_key=key),model


def ai_status():
    client, model = _get_client()
    return {"connected": client is not None, "model": model}

def analyze_event(event,market_context="",use_ai=True,research_mode=False):
    client,model=_get_client()
    if not use_ai or client is None: return _fallback_event(event)
    prompt=f"""事件：
{event}

当前市场上下文：
{market_context}

请用中文输出，结构必须如下：
1. 事实层：目前能确定什么；哪些仍需核实
2. 核心传导链：三到五层，不得只写相关性
3. 资产映射：直接影响 / 二阶影响 / A股映射
4. 市场定价：已反映什么、尚未反映什么
5. 待验证数据：列出5项，注明24小时或1-3个月
6. 反证条件：列出3项
7. 一句话结论

控制在1200个中文字符以内。禁止给出买入卖出建议。若没有实时证据，请明确说明。
{"联网检索最新公开信息并在相关结论后保留来源链接。" if research_mode else "仅基于上方事件与看板上下文推理，不要假装已经联网核实。"}"""
    try:
        kwargs={"model":model,"instructions":SYSTEM,"input":prompt}
        if research_mode:
            kwargs["tools"]=[{"type":"web_search"}]
        try:
            r=client.responses.create(**kwargs)
        except Exception:
            # Some account/model combinations do not expose web search. The
            # structural analysis remains available and stays explicitly labelled.
            kwargs.pop("tools",None)
            r=client.responses.create(**kwargs)
        return r.output_text
    except Exception as e:
        return f"AI调用失败：{e}\n\n"+_fallback_event(event)

def generate_ai_morning_brief(snapshot_text,news_text,use_ai=True):
    client,model=_get_client()
    if not use_ai or client is None: return None
    prompt=f"""你正在为中国投资者生成A股开盘前的全球宏观晨报。

市场快照：
{snapshot_text}

新闻标题与来源：
{news_text}

输出五部分：
A. 一句话总判断（不超过70字）
B. 三个最重要变化（每项：事实→含义→定价）
C. 两条“事件→传导→A股验证”链
D. 三个开盘前验证点
E. 一个最可能被忽略的二阶变量与反证条件

要求：总长度不超过900个中文字符；事实与推断分开；不要堆新闻；不要给买卖建议；对不确定信息标“待验证”。"""
    try:
        r=client.responses.create(model=model,instructions=SYSTEM,input=prompt)
        return r.output_text
    except Exception:
        return None
