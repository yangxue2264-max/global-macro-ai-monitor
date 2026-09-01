from __future__ import annotations
from collections import Counter
from urllib.parse import urlparse
import re

HIGH_TRUST = {
    "federalreserve.gov","ecb.europa.eu","bis.org","imf.org","worldbank.org","pbc.gov.cn","gov.cn",
    "reuters.com","bloomberg.com","ft.com","wsj.com"
}

def normalize_title(title):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+"," ",(title or "").lower()).strip()

def evidence_score(item, all_items=None):
    source = (item.get("source") or "").lower()
    url = item.get("url") or ""
    domain = urlparse(url).netloc.lower().replace("www.","")
    score = float(item.get("score",0) or 0)

    # Source quality
    if domain in HIGH_TRUST or any(x in source for x in ["reuters","bloomberg","federal reserve","ecb","bis","imf"]):
        score += 1.5
    elif source:
        score += 0.4

    # Structure quality
    if item.get("modules"): score += 0.35
    if item.get("themes"): score += 0.35

    # Cross-source confirmation: same key terms across titles
    confirm = 0
    if all_items:
        words = set(normalize_title(item.get("title","")).split())
        words = {w for w in words if len(w)>=5}
        for other in all_items:
            if other is item: continue
            ow = set(normalize_title(other.get("title","")).split())
            overlap = len(words & ow)
            if overlap >= 3:
                confirm += 1
        score += min(confirm,2)*0.45

    if item.get("status")=="demo":
        return 0.0, "DEMO"

    if score >= 4.6:
        label="较高"
    elif score >= 3.0:
        label="中等"
    else:
        label="初步"
    return round(score,2), label

def add_evidence_scores(items):
    out=[]
    for item in items:
        s,label=evidence_score(item,items)
        x=dict(item)
        x["evidence_score"]=s
        x["evidence_label"]=label
        out.append(x)
    return sorted(out,key=lambda z:(z.get("evidence_score",0),z.get("score",0)),reverse=True)
