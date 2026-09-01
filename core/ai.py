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

def analyze_event(event,market_context="",use_ai=True):
    client,model=_get_client()
    if not use_ai or client is None: return _fallback_event(event)
    prompt=f"""事件：
{event}

当前市场上下文：
{market_context}

请用中文输出，结构必须如下：
1. 事实层：目前能确定什么；哪些仍需核实
2. 宏观状态变量：增长 / 金融状况 / 政策 / 全球化 / 资产配置 / 实体瓶颈 / 社会与分配
3. 因果传导链：至少三层，不得只写相关性
4. 资产映射：股票/行业、利率、汇率、商品；分别标注“直接/二阶”
5. 市场定价：说明如何判断市场是否已经计价
6. 时间维度：24小时、1-4周、1-3个月分别关注什么
7. 待验证数据：列出5项
8. 反证条件：什么出现时应该推翻或弱化该叙事
9. 一句话结论

禁止给出买入卖出建议。若没有实时证据，请明确说明。"""
    try:
        r=client.responses.create(model=model,instructions=SYSTEM,input=prompt)
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

输出六部分：
A. 一句话总判断（不超过70字）
B. 今日四个核心状态变量（每项：变化→原因→资产含义）
C. 三条“事件→传导→资产”链
D. 市场叙事与价格的两个背离
E. A股开盘前要盯的5个验证点
F. 今天最可能被忽略的二阶变量

要求：事实与推断分开；不要堆新闻；不要给买卖建议；对不确定信息标“待验证”。"""
    try:
        r=client.responses.create(model=model,instructions=SYSTEM,input=prompt)
        return r.output_text
    except Exception:
        return None
