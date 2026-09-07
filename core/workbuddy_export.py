from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterable
import json
import math

from core.preopen import (
    attach_auction_results,
    attach_auction_to_alerts,
    auction_status_counts,
    build_opportunity_signals,
    build_watchlist_alerts,
    normalize_watchlist_rows,
    rerank_signals_after_auction,
)


SCHEMA_VERSION = "1.0"
DEFAULT_SITE_URL = "https://yang-global-macro-ai-monitor.streamlit.app/"


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _date_part(value: str) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return str(value or "")[:10]


def _signal_id(signal: dict) -> str:
    raw = "|".join(
        [
            str(signal.get("theme", "")),
            str(signal.get("url", "")),
            str(signal.get("title", "")),
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _compact_target(target: dict) -> dict:
    auction = target.get("auction", {})
    return _json_safe({
        "ticker": target.get("ticker", ""),
        "name": target.get("name", ""),
        "relation": target.get("relation", "需判断"),
        "source": target.get("source", ""),
        "auction_status": auction.get("status", "等待09:27竞价"),
        "auction_gap_pct": auction.get("gap_pct"),
        "auction_reason": auction.get("reason", ""),
        "auction_source": auction.get("source", ""),
    })


def _compact_signal(signal: dict) -> dict:
    return {
        "signal_id": _signal_id(signal),
        "category": signal.get("category", ""),
        "priority": signal.get("priority", 0),
        "theme": signal.get("theme", ""),
        "title": signal.get("title", ""),
        "source": signal.get("source", ""),
        "published": signal.get("published", ""),
        "url": signal.get("url", ""),
        "evidence_score": signal.get("evidence", 0),
        "evidence_label": signal.get("evidence_label", ""),
        "overseas_validation": signal.get("price_text", ""),
        "overseas_direction": signal.get("price_direction", "中性"),
        "watchlist_relevant": bool(signal.get("watchlist_relevant")),
        "transmission": signal.get("mechanism", ""),
        "direction_note": signal.get("direction_note", ""),
        "next_check": signal.get("next_check", ""),
        "invalidation": signal.get("risk", ""),
        "targets": [_compact_target(row) for row in signal.get("targets", [])],
    }


def _compact_alert(alert: dict) -> dict:
    auction = alert.get("auction", {})
    return {
        "ticker": alert.get("ticker", ""),
        "name": alert.get("name", ""),
        "theme": alert.get("theme", ""),
        "level": alert.get("level", ""),
        "reason": alert.get("reason", ""),
        "headline": alert.get("headline", ""),
        "source": alert.get("source", ""),
        "news_url": alert.get("news_url", ""),
        "overseas_direction": alert.get("price_direction", "中性"),
        "overseas_moves": alert.get("overseas_moves", []),
        "previous_close": alert.get("previous_close"),
        "previous_day_move": alert.get("previous_day_move"),
        "auction_status": auction.get("status", "等待09:27竞价"),
        "auction_gap_pct": auction.get("gap_pct"),
        "auction_reason": auction.get("reason", ""),
        "next_check": alert.get("next_check", ""),
    }


def build_workbuddy_payload(
    morning: dict,
    auction: dict | None,
    mapping: dict,
    watchlist: Iterable[dict],
    site_url: str = DEFAULT_SITE_URL,
) -> dict:
    watchlist = normalize_watchlist_rows(watchlist)
    market = morning.get("market", {})
    news = morning.get("news", [])
    morning_day = _date_part(morning.get("generated_at", ""))
    auction_day = str((auction or {}).get("trade_date", ""))[:10]
    auction_current = bool(morning_day and auction_day == morning_day)
    quotes = (auction or {}).get("quotes", {}) if auction_current else {}

    signals = build_opportunity_signals(news, market, mapping, watchlist)
    alerts = build_watchlist_alerts(watchlist, news, market, mapping)
    if quotes:
        signals = attach_auction_results(signals, quotes)
        signals = rerank_signals_after_auction(signals)
        alerts = attach_auction_to_alerts(alerts, signals)
    else:
        signals = [
            {
                **signal,
                "targets": [
                    {
                        **target,
                        "auction": {
                            "status": "等待09:27竞价",
                            "gap_pct": None,
                            "reason": "09:00先形成海外候选池，09:27后再判断是否已被A股定价。",
                            "source": "",
                        },
                    }
                    for target in signal.get("targets", [])
                ],
            }
            for signal in signals
        ]
        alerts = [
            {
                **row,
                "auction": {
                    "status": "等待09:27竞价",
                    "gap_pct": None,
                    "reason": "09:00先形成海外候选池，09:27后再判断是否已被A股定价。",
                    "source": "",
                },
            }
            for row in alerts
        ]

    verified = [row for row in signals if row.get("category") == "海外已验证"]
    transmission = [row for row in signals if row.get("category") == "传导待验证"]
    counts = auction_status_counts(signals)
    stage = "auction_review" if quotes else "morning_candidates"
    generated_at = (
        (auction or {}).get("generated_at") if quotes else morning.get("generated_at")
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "trade_date": morning_day,
        "stage": stage,
        "stage_label": "09:27集合竞价复核" if quotes else "09:00海外候选池",
        "site_url": site_url,
        "disclaimer": "研究辅助，不构成投资建议；优先级用于安排研究顺序，不是收益预测。",
        "method": {
            "morning": "可靠新闻 + 海外价格确认 + A股传导映射",
            "auction": "用集合竞价区分仍有预期差、基本定价、过度定价/追高风险、A股不确认",
            "missing_data_rule": "关键数据缺失时降低结论，不把旧数据或演示值当作实时信号。",
        },
        "summary": {
            "watchlist_count": len(watchlist),
            "important_watchlist_alerts": sum(row.get("level") == "重点异动" for row in alerts),
            "watchlist_attention": sum(row.get("level") == "需要关注" for row in alerts),
            "overseas_verified": len(verified),
            "transmission_pending": len(transmission),
            "auction_status_counts": counts,
        },
        "watchlist_alerts": [_compact_alert(row) for row in alerts],
        "signals": [_compact_signal(row) for row in signals],
        "context": {
            "default_watchlist": watchlist,
            "mapping": mapping,
            "market": market,
            "news": news,
            "auction_quotes": quotes,
        },
    }
    return _json_safe(payload)


def export_workbuddy_payload(base: Path, site_url: str = DEFAULT_SITE_URL) -> Path:
    morning_path = base / "data" / "latest_morning_brief.json"
    if not morning_path.exists():
        raise FileNotFoundError("data/latest_morning_brief.json does not exist")
    morning = json.loads(morning_path.read_text(encoding="utf-8"))
    auction_path = base / "data" / "latest_auction_snapshot.json"
    auction = json.loads(auction_path.read_text(encoding="utf-8")) if auction_path.exists() else None
    mapping = json.loads((base / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    watchlist = json.loads((base / "config" / "default_user_watchlist.json").read_text(encoding="utf-8"))
    payload = build_workbuddy_payload(morning, auction, mapping, watchlist, site_url=site_url)
    output = base / "static" / "workbuddy" / "latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return output
