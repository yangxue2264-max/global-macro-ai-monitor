from __future__ import annotations
import numpy as np

THEME_TO_CN = {
    "AI资本开支": [
        ("FOXCONN","AI服务器/整机"),
        ("ZHONGJI","高速光模块"),
        ("EOPTOLINK","高速光模块"),
        ("WUS","高速PCB"),
        ("XD","电网设备"),
        ("TBEA","输变电与能源"),
        ("ZIJIN","铜资源"),
        ("CMOC","铜钴资源")
    ],
    "天气与农业": [
        ("LONGPING","种业"),
        ("BEIDAHUANG","种植业"),
    ],
    "油价与通胀": [
        ("SHENHUA","能源/煤炭"),
        ("ZIJIN","资源品与通胀敏感"),
    ],
    "贸易与关税": [
        ("BABA","中国互联网ADR参考"),
        ("TCEHY","中国互联网ADR参考"),
        ("FOXCONN","全球电子供应链"),
    ],
    "流动性与信用": [
        ("MOUTAI","核心资产风险偏好代理"),
        ("CSI300","A股大盘风险偏好"),
    ]
}

def active_themes(news, limit=3):
    score={}
    for n in news[:20]:
        for t in n.get("themes",[]):
            score[t]=score.get(t,0)+float(n.get("evidence_score",1) or 1)
    ranked=sorted(score.items(),key=lambda x:x[1],reverse=True)
    return [x[0] for x in ranked[:limit]] or ["AI资本开支","流动性与信用"]

def cn_watch_rows(news, market):
    out=[]
    for theme in active_themes(news):
        for key, rationale in THEME_TO_CN.get(theme,[]):
            x=market.get(key,{})
            out.append({
                "隔夜主题":theme,
                "A股/中国资产":x.get("name",key),
                "映射理由":rationale,
                "日涨跌%":x.get("change_pct",np.nan),
                "20日%":x.get("change_20d_pct",np.nan),
                "观察而非建议":"仅用于验证传导"
            })
    # de-dup by asset while keeping first/highest-ranked theme
    seen=set(); dedup=[]
    for r in out:
        if r["A股/中国资产"] in seen: continue
        seen.add(r["A股/中国资产"]); dedup.append(r)
    return dedup[:12]
