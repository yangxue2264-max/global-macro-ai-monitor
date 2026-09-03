from __future__ import annotations

from .ontology import TRUSTED_DOMAINS, source_domain, tag_modules, tag_themes


OFFICIAL_HINTS = ("federal reserve", "treasury", "imf", "bis", "world bank", "ecb", "pboc", "noaa")


def score_evidence(item):
    domain = source_domain(item.get("url", ""))
    source = (item.get("source") or "").lower()
    domain_weight = TRUSTED_DOMAINS.get(domain, 1.0)
    official = domain_weight >= 2.8 or any(hint in source for hint in OFFICIAL_HINTS)
    if official:
        score, label, reason = 90, "A·原始/官方", "官方或原始发布机构"
    elif domain_weight >= 2.3 or any(name in source for name in ("reuters", "bloomberg", "financial times", "wall street journal")):
        score, label, reason = 78, "B·可靠报道", "高可信财经媒体，仍应回看原始文件"
    elif item.get("source"):
        score, label, reason = 58, "C·线索", "可用于发现事件，关键数字需二次核实"
    else:
        score, label, reason = 40, "D·待核实", "来源信息不足"
    return score, label, reason


def add_evidence_scores(news):
    rows = []
    for item in news:
        enriched = dict(item)
        text = f"{enriched.get('title', '')} {enriched.get('source', '')}"
        if not enriched.get("modules") or enriched.get("modules") == ["待分类"]:
            enriched["modules"] = tag_modules(text)
        if not enriched.get("themes") or enriched.get("themes") == ["待分类"]:
            enriched["themes"] = tag_themes(text)
        score, label, reason = score_evidence(enriched)
        enriched.update(evidence_score=score, evidence_label=label, evidence_reason=reason)
        rows.append(enriched)
    return rows
