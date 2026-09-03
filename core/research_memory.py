from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_recent_briefs(base, limit=2):
    history = Path(base) / "data" / "brief_history"
    files = sorted(history.glob("*.json"), reverse=True) if history.exists() else []
    rows = []
    for path in files:
        payload = _read(path)
        if payload and payload.get("generated_at") != "DEMO":
            rows.append(payload)
        if len(rows) >= limit:
            break
    return rows


def load_previous_brief(base):
    """Return the most recent snapshot before today in China time."""
    history = Path(base) / "data" / "brief_history"
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    files = sorted(history.glob("*.json"), reverse=True) if history.exists() else []
    for path in files:
        if path.stem >= today:
            continue
        payload = _read(path)
        if payload and payload.get("generated_at") != "DEMO":
            return payload
    return None


def memory_summary(base, current_brief):
    previous = load_previous_brief(base)
    if not previous:
        return {
            "available": False,
            "title": "研究记忆将在下一次自动晨报后启用",
            "items": ["系统会保存昨日状态、今日变化与前一叙事的验证结果。"],
        }
    previous_brief = previous.get("brief", {})
    previous_regime = previous_brief.get("regime", "—")
    current_regime = current_brief.get("regime", "—")
    generated = previous.get("generated_at", "")
    try:
        date = datetime.fromisoformat(generated).strftime("%m月%d日 %H:%M")
    except Exception:
        date = generated[:16] or "上一期"
    changed = previous_regime != current_regime
    return {
        "available": True,
        "title": f"相较 {date}：{'状态发生变化' if changed else '状态标签未变'}",
        "items": [
            f"上期状态：{previous_regime} → 当前：{current_regime}",
            f"上期判断：{previous_brief.get('headline','—')}",
            "请用今天的价格、利率与新闻验证上期叙事，而不是只生成一份新摘要。",
        ],
    }
