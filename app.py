from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import secrets
import time

import pandas as pd
import streamlit as st

from core.briefing import morning_rule_brief
from core.demo import demo_macro, demo_market, demo_news
from core.evidence import add_evidence_scores
from core.market_context import enrich_macro_with_market_proxies
from core.opportunity_model import attach_dynamic_guidance, detect_market_auction_anomalies, discover_market_targets
from core.preopen import (
    auction_status_counts,
    build_opportunity_signals,
    decode_watchlist,
    encode_watchlist,
    normalize_watchlist_rows,
    watchlist_editor_rows,
    watchlist_inputs_from_editor,
)
from core.providers import (
    FRED_SERIES,
    data_health,
    fetch_a_share_universe,
    fetch_all_auction_quotes,
    fetch_fred_snapshot,
    fetch_auction_quotes,
    fetch_market_snapshot,
    fetch_news_bundle,
    fetch_treasury_snapshot,
    flatten_watchlist,
    load_watchlist,
)
from core.reporting import build_personal_analysis
from core.emailing import email_configured, send_email, send_verification_code
from core.stock_enrichment import enrich_watchlist_inputs
from core.subscriptions import (
    deactivate_subscription,
    normalize_email,
    subscriptions_configured,
    upsert_subscription,
)


BASE = Path(__file__).resolve().parent
CN_TZ = ZoneInfo("Asia/Shanghai")


st.set_page_config(page_title="A股盘前机会雷达", page_icon="◎", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
<style>
:root{--ink:#101828;--muted:#667085;--border:#e4e7ec;--soft:#f8fafc;--blue:#175cd3;--green:#067647;--amber:#b54708;--red:#b42318;--purple:#6941c6}
.block-container{padding-top:.8rem;padding-bottom:3rem;max-width:1420px}header[data-testid="stHeader"]{height:2.1rem;background:transparent}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.025em}.hero{padding:12px 0 7px}.eyebrow{font-size:.72rem;font-weight:760;color:var(--blue);letter-spacing:.11em;text-transform:uppercase}.hero-title{font-size:2rem;font-weight:790;line-height:1.15;color:var(--ink);margin:5px 0}.hero-sub{font-size:.93rem;color:var(--muted);max-width:980px;line-height:1.58}
.statusbar{display:flex;gap:7px;flex-wrap:wrap;margin:.35rem 0 .9rem}.badge{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:4px 9px;font-size:.71rem;color:#344054;background:#fff}.badge.live{background:#ecfdf3;color:var(--green);border-color:#abefc6}.badge.warn{background:#fffaeb;color:var(--amber);border-color:#fedf89}
[data-testid="stMetric"]{border:1px solid var(--border);padding:12px 14px;border-radius:13px;background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.03)}[data-testid="stMetricLabel"]{font-size:.76rem;color:var(--muted)}
.section{font-size:1.08rem;font-weight:770;margin:1.15rem 0 .55rem;color:var(--ink)}.section-note{font-size:.75rem;color:var(--muted);font-weight:400;margin-left:7px}
.card{border:1px solid var(--border);border-radius:14px;padding:15px 16px;background:#fff;margin-bottom:10px;box-shadow:0 1px 2px rgba(16,24,40,.035)}.card.high{border-left:4px solid #f04438}.card.watch{border-left:4px solid #f79009}.card.quiet{border-left:4px solid #98a2b3}.card.verified{border-left:4px solid #12b76a}.card.transmission{border-left:4px solid #7f56d9}
.card-title{font-size:.98rem;font-weight:740;line-height:1.42;color:var(--ink)}.kicker{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}.body{font-size:.84rem;line-height:1.58;color:#344054}.muted{font-size:.73rem;color:var(--muted);line-height:1.48}.fact{border-left:3px solid #84adff;padding-left:9px;margin:8px 0}.verify{border-left:3px solid #75e0a7;padding-left:9px;margin:8px 0}.invalidate{border-left:3px solid #fda29b;padding-left:9px;margin:8px 0}
.pill{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 7px;margin:2px 4px 2px 0;font-size:.67rem;color:#475467;background:var(--soft)}.pill.green{color:#067647;background:#ecfdf3;border-color:#abefc6}.pill.amber{color:#b54708;background:#fffaeb;border-color:#fedf89}.pill.red{color:#b42318;background:#fef3f2;border-color:#fecdca}.pill.purple{color:#6941c6;background:#f4f3ff;border-color:#d9d6fe}
.callout{border:1px solid #b2ddff;background:#f5fbff;border-radius:14px;padding:15px 17px;color:#194185;font-size:.91rem;line-height:1.58}.formula{border:1px solid var(--border);background:var(--soft);border-radius:12px;padding:12px 14px;font-size:.79rem;color:#475467;line-height:1.55}
div[data-testid="stRadio"]>div{gap:.35rem;flex-wrap:wrap}div[data-testid="stRadio"] label{border:1px solid var(--border);border-radius:9px;padding:4px 10px;background:white}.stDataFrame{border:1px solid var(--border);border-radius:12px;overflow:hidden}a{text-decoration:none}
@media(max-width:800px){.block-container{padding-left:1rem;padding-right:1rem}.hero-title{font-size:1.58rem}.hero-sub{font-size:.84rem}}
</style>
""",
    unsafe_allow_html=True,
)


def expected_snapshot_day(now: datetime) -> str:
    day = now.date() if (now.hour, now.minute) >= (8, 45) else (now - timedelta(days=1)).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def parse_generated_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=CN_TZ)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_config():
    cfg = load_watchlist(BASE / "config" / "watchlist.json")
    mapping = json.loads((BASE / "config" / "a_share_map.json").read_text(encoding="utf-8"))
    defaults = json.loads((BASE / "config" / "default_user_watchlist.json").read_text(encoding="utf-8"))
    return cfg, flatten_watchlist(cfg), mapping, normalize_watchlist_rows(defaults)


def _saved_snapshot():
    path = BASE / "data" / "latest_morning_brief.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload.get("market") and payload.get("news") else None
    except Exception:
        return None


def _saved_auction_snapshot(trade_date: str):
    path = BASE / "data" / "latest_auction_snapshot.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload.get("trade_date") == trade_date and payload.get("quotes") else None
    except Exception:
        return None


def auction_is_ready(now: datetime, trade_date: str) -> bool:
    if trade_date < now.date().isoformat():
        return True
    return (now.hour, now.minute) >= (9, 26)


@st.cache_data(ttl=93600, show_spinner=False)
def load_daily_bundle(universe: dict, mapping_cfg: dict, snapshot_key: str):
    if os.getenv("MACRO_MONITOR_OFFLINE_TEST") == "1":
        market = demo_market(universe)
        macro = demo_macro(FRED_SERIES)
        news = add_evidence_scores(demo_news())
        if "NVDA" in market:
            market["NVDA"]["change_pct"] = 3.20
        if "SMH" in market:
            market["SMH"]["change_pct"] = 2.35
        for item in news:
            item.update(evidence_score=78, evidence_label="DEMO · 可靠新闻样例", evidence_reason="仅用于界面与规则验证")
        stock_rows = [dict(meta) for meta in universe.values() if str(meta.get("ticker", "")).endswith((".SS", ".SZ", ".BJ"))]
        signals = attach_dynamic_guidance(discover_market_targets(build_opportunity_signals(news, market, mapping_cfg, []), stock_rows), market)
        return market, macro, news, signals, {"mode": "DEMO_CONFIGURED_UNIVERSE", "count": len(stock_rows)}, "DEMO", "DEMO"

    saved = _saved_snapshot()
    if saved and saved.get("universe_coverage"):
        return (
            saved.get("market", {}),
            saved.get("macro", {}),
            add_evidence_scores(saved.get("news", [])),
            saved.get("signals", []),
            saved.get("universe_coverage", {"mode": "LEGACY_SNAPSHOT", "count": 0}),
            "DAILY_SNAPSHOT",
            saved.get("generated_at", ""),
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        market_future = pool.submit(fetch_market_snapshot, universe)
        macro_future = pool.submit(fetch_fred_snapshot, FRED_SERIES)
        news_future = pool.submit(fetch_news_bundle, 10)
        treasury_future = pool.submit(fetch_treasury_snapshot)
        universe_future = pool.submit(fetch_a_share_universe)
        market = market_future.result()
        macro = enrich_macro_with_market_proxies(macro_future.result(), market, treasury_future.result())
        news = add_evidence_scores(news_future.result())
        stock_rows, coverage = universe_future.result()
    signals = discover_market_targets(build_opportunity_signals(news, market, mapping_cfg, []), stock_rows)
    known = {item.get("ticker") for item in market.values()}
    extras = {}
    for signal in signals:
        for target in signal.get("targets", []):
            ticker = target.get("ticker")
            if ticker and ticker not in known and ticker not in {item.get("ticker") for item in extras.values()}:
                extras[f"DISCOVERY_{len(extras)}"] = {"name": target.get("name") or ticker, "ticker": ticker, "theme": signal.get("theme", ""), "region": "CN", "group": "full_market_discovery"}
    if extras:
        market.update(fetch_market_snapshot(extras))
    signals = attach_dynamic_guidance(signals, market)
    return market, macro, news, signals, coverage, "ON_DEMAND_FALLBACK", datetime.now(CN_TZ).isoformat()


@st.cache_data(ttl=93600, show_spinner=False)
def load_missing_watchlist_market(rows: list[dict], existing_tickers: tuple[str, ...], snapshot_key: str):
    extras = {}
    known = set(existing_tickers)
    for index, row in enumerate(rows):
        if row["ticker"] not in known:
            extras[f"USER_{index}_{row['ticker']}"] = {
                "name": row["name"], "ticker": row["ticker"], "theme": row["theme"],
                "region": "CN", "group": "user_watchlist",
            }
    if not extras:
        return {}
    if os.getenv("MACRO_MONITOR_OFFLINE_TEST") == "1":
        return demo_market(extras)
    return fetch_market_snapshot(extras)


@st.cache_data(ttl=93600, show_spinner=False)
def load_auction_bundle(tickers: tuple[str, ...], trade_date: str):
    if os.getenv("MACRO_MONITOR_OFFLINE_TEST") == "1":
        gaps = [0.45, 1.65, 3.80, -0.90, 0.20, 2.40, -0.30, 5.20]
        quotes = {}
        for index, ticker in enumerate(tickers):
            gap = gaps[index % len(gaps)]
            quotes[ticker] = {
                "ticker": ticker, "name": ticker, "auction_price": round(100 * (1 + gap / 100), 3),
                "pre_close": 100.0, "gap_pct": gap, "date": trade_date, "time": "09:25",
                "source": "DEMO auction", "status": "ok",
            }
        return quotes, [], {"mode": "DEMO_AUCTION", "count": len(quotes)}, "DEMO_AUCTION", f"{trade_date}T09:25:00+08:00"
    saved = _saved_auction_snapshot(trade_date)
    if saved:
        quotes = dict(saved.get("quotes", {}))
        anomalies = list(saved.get("anomalies", []))
        coverage = saved.get("auction_coverage", {"mode": "LEGACY_SNAPSHOT", "count": len(quotes)})
    else:
        quotes, coverage = fetch_all_auction_quotes(trade_date)
        anomalies = detect_market_auction_anomalies(quotes)
    missing = tuple(ticker for ticker in tickers if ticker not in quotes)
    if missing:
        quotes.update(fetch_auction_quotes(missing, trade_date))
    mode = coverage.get("mode") or ("FREE_QUOTE_FALLBACK" if quotes else "AUCTION_UNAVAILABLE")
    generated = saved.get("generated_at", "") if saved else datetime.now(CN_TZ).isoformat()
    return quotes, anomalies, coverage, mode, generated


def snapshot_label(generated_at: str, mode: str, expected_day: str) -> tuple[str, bool]:
    if mode == "DEMO":
        return "DEMO 数据", True
    parsed = parse_generated_at(generated_at)
    if not parsed:
        return "快照时间未知", True
    parsed_cn = parsed.astimezone(CN_TZ)
    age_hours = (datetime.now(CN_TZ) - parsed_cn).total_seconds() / 3600
    late_for_premarket = parsed_cn.date().isoformat() == expected_day and (parsed_cn.hour, parsed_cn.minute) >= (9, 25)
    stale = parsed_cn.date().isoformat() != expected_day or age_hours > 72 or late_for_premarket
    return f"{parsed_cn:%m-%d %H:%M} 快照", stale


def level_pill(level: str) -> str:
    css = "red" if level == "重点异动" else "amber" if level == "需要关注" else ""
    return f'<span class="pill {css}">{escape(level)}</span>'


def auction_pill(status: str) -> str:
    css = "green" if status == "仍有预期差" else "red" if status == "过度定价/追高风险" else "amber" if status in {"A股不确认", "竞价独立异动", "数据不足/仅观察"} else "purple" if status == "方向需人工判断" else ""
    return f'<span class="pill {css}">{escape(status)}</span>'


def target_pills(targets: list[dict]) -> str:
    return "".join(
        f'<span class="pill {"green" if row.get("source") == "自选股" else ""}">{escape(row.get("name", ""))}{" · " + escape(row.get("role", "")) if row.get("role") else ""}</span>'
        for row in targets
    )


def moves_text(moves: list[dict]) -> str:
    if not moves:
        return "暂无有效海外价格"
    return "；".join(f"{row['name']} {row['move']:+.2f}%" + (f"（近一年{row['tail_percentile']:.0%}分位）" if row.get("tail_percentile") is not None else "") for row in moves)


def render_alert(row: dict):
    css = "high" if row["level"] == "重点异动" else "watch" if row["level"] == "需要关注" else "quiet"
    previous = "—" if row["previous_day_move"] is None else f"{row['previous_day_move']:+.2f}%"
    headline = escape(row["headline"] or "无直接相关新闻")
    if row.get("news_url"):
        headline = f'<a href="{escape(row["news_url"])}" target="_blank">{headline}</a>'
    auction = row.get("auction", {})
    auction_gap = auction.get("gap_pct")
    gap_text = "" if auction_gap is None else f" · 竞价 {auction_gap:+.2f}%"
    auction_html = f'<div class="verify body"><b>09:25二次判断：</b>{auction_pill(auction.get("status", "等待09:25竞价"))}{escape(gap_text)}<br>{escape(auction.get("reason", "等待集合竞价形成后判断剩余预期差。"))}</div>'
    st.markdown(
        f'''<div class="card {css}"><div class="kicker">{escape(row['ticker'])} · {escape(row['theme'])} · 上一交易日 {previous} {level_pill(row['level'])}</div><div class="card-title">{escape(row['name'])}</div><div class="fact body"><b>为什么提示：</b>{escape(row['reason'])}</div><div class="body"><b>相关海外：</b>{escape(moves_text(row['overseas_moves']))}</div><div class="body"><b>相关新闻：</b>{headline}</div><div class="muted">来源 {escape(row.get('source','') or '未取得')} · 时间 {escape(row.get('published','') or '未取得')} · 证据 {row.get('evidence_score',0)}/100 · 映射 {escape(row.get('profile_source','') or '系统规则')}</div>{auction_html}<div class="muted"><b>下一步：</b>{escape(row['next_check'])}</div></div>''',
        unsafe_allow_html=True,
    )


def render_signal(row: dict):
    verified = row["category"] == "海外已验证"
    css = "verified" if verified else "transmission"
    category_css = "green" if verified else "purple"
    title = escape(row["title"])
    if row.get("url"):
        title = f'<a href="{escape(row["url"])}" target="_blank">{title}</a>'
    watch_tag = '<span class="pill amber">命中自选股</span>' if row["watchlist_relevant"] else ""
    st.markdown(
        f'''<div class="card {css}"><div class="kicker">优先级 {row['priority']}/100 · {escape(row['theme'])} <span class="pill {category_css}">{escape(row['category'])}</span>{watch_tag}</div><div class="card-title">{title}</div><div class="muted">{escape(row['source'])} · 证据 {row.get('evidence',0)}/100（{escape(row['evidence_label'])}）· {escape(row['published'])}</div><div class="fact body"><b>海外价格验证：</b>{escape(moves_text(row['price_moves']))}</div><div class="body"><b>传导链：</b>{escape(row['mechanism'])}</div><div class="body"><b>方向解释：</b>{escape(row['direction_note'])}</div><div class="invalidate muted"><b>失效条件：</b>{escape(row['risk'])}</div></div>''',
        unsafe_allow_html=True,
    )
    target_rows = []
    for target in row.get("targets", []):
        guidance = target.get("guidance", {})
        auction = target.get("auction", {})
        if guidance.get("max_gap_pct") is None:
            condition = f"{guidance.get('action', '仅观察')}：{guidance.get('reason', '动态样本不足')}"
        else:
            price = f" / ≤{guidance['max_price']:.3f}元" if guidance.get("max_price") else ""
            condition = f"高开≤{guidance['max_gap_pct']:.2f}%{price}"
        gap = auction.get("gap_pct")
        target_rows.append({
            "股票": f"{target.get('name','')}（{target.get('ticker','').split('.')[0]}）",
            "发现方式": target.get("mapping_level") or target.get("source", ""),
            "业务映射依据": target.get("mapping_reason") or target.get("role", ""),
            "08:45参与条件": condition,
            "主要期限": guidance.get("primary_horizon", "未判定"),
            "历史胜率": None if guidance.get("horizons") == [] else next((f"{item.get('positive_probability',0):.0%}" for item in guidance.get("horizons", []) if item.get("label") == guidance.get("primary_horizon")), None),
            "有效样本": guidance.get("effective_sample", 0),
            "置信度": guidance.get("confidence", "不足"),
            "历史数据截至": guidance.get("target_data_asof", "未取得"),
            "09:27结果": auction.get("status", "等待最终竞价"),
            "竞价涨跌": None if gap is None else f"{gap:+.2f}%",
        })
    if target_rows:
        st.dataframe(pd.DataFrame(target_rows), hide_index=True, width="stretch")
    with st.expander("查看完整证据链、期限分布与模型说明"):
        st.dataframe(pd.DataFrame(row.get("evidence_chain", [])), hide_index=True, width="stretch")
        for target in row.get("targets", [])[:8]:
            guidance = target.get("guidance", {})
            st.markdown(f"**{target.get('name','')}｜{guidance.get('primary_horizon','未判定')}** — {guidance.get('reason','')}  ")
            if guidance.get("horizons"):
                st.dataframe(pd.DataFrame(guidance["horizons"]), hide_index=True, width="stretch")
            st.caption(guidance.get("method", "没有足够数据生成动态阈值。"))


def export_markdown(alerts: list[dict], signals: list[dict], generated_at: str) -> str:
    lines = ["# A股盘前机会简报", "", f"快照：{generated_at}", "", "## 自选股异动"]
    for row in alerts:
        if row["level"] != "暂无异动":
            lines.append(f"- **{row['name']}（{row['ticker']}）｜{row['level']}**：{row['reason']}。{row['next_check']}")
    lines.extend(["", "## 今日机会"])
    for row in signals[:10]:
        target_parts = []
        for item in row["targets"]:
            assessment = item.get("auction", {})
            gap = assessment.get("gap_pct")
            gap_text = "" if gap is None else f" {gap:+.2f}%"
            target_parts.append(f"{item['name']}（{assessment.get('status', '等待竞价')}{gap_text}）")
        targets = "、".join(target_parts)
        lines.append(f"- **{row['category']}｜{row['theme']}｜{row['priority']}/100**：{row['title']}；A股：{targets}；海外：{row['price_text']}。")
    lines.extend(["", "> 研究辅助，不构成投资建议。优先级不是收益预测。"])
    return "\n".join(lines)


def render_subscription_panel(user_watchlist: list[dict]):
    st.markdown('<div class="section">邮件订阅<span class="section-note">交易日08:45与09:27发送个人报告</span></div>', unsafe_allow_html=True)
    if not (subscriptions_configured() and email_configured()):
        st.info("邮件订阅服务正在配置中；网页分析仍可正常使用。")
        return

    st.caption("先保存上方自选股，再输入你本人可接收验证码的邮箱。只有验证成功后，订阅或退订操作才会生效。")
    email = st.text_input("接收邮箱", placeholder="name@example.com", key="subscription_email")
    send_col, code_col = st.columns([1, 2])
    if send_col.button("发送验证码", width="stretch"):
        address = normalize_email(email)
        if not address:
            st.error("请输入有效邮箱地址。")
        else:
            last_sent = float(st.session_state.get("verification_sent_at", 0))
            if time.time() - last_sent < 60:
                st.warning("请等待60秒后再重新发送。")
            else:
                code = f"{secrets.randbelow(1_000_000):06d}"
                try:
                    send_verification_code(address, code)
                    st.session_state["verification_email"] = address
                    st.session_state["verification_code"] = code
                    st.session_state["verification_expires"] = time.time() + 600
                    st.session_state["verification_sent_at"] = time.time()
                    st.success("验证码已发送，有效期10分钟。")
                except Exception as exc:
                    st.error(f"验证码发送失败：{exc}")

    code = code_col.text_input("邮箱验证码", max_chars=6, placeholder="6位数字", key="subscription_code")
    action_col, cancel_col = st.columns(2)

    def verified() -> tuple[bool, str]:
        address = normalize_email(email)
        ok = bool(
            address
            and address == st.session_state.get("verification_email")
            and code == st.session_state.get("verification_code")
            and time.time() <= float(st.session_state.get("verification_expires", 0))
        )
        return ok, address

    if action_col.button("订阅或更新", type="primary", width="stretch"):
        ok, address = verified()
        if not ok:
            st.error("验证码不正确、已过期，或邮箱已更改。")
        elif not user_watchlist:
            st.error("请先保存至少一只自选股。")
        else:
            try:
                upsert_subscription(address, user_watchlist)
                st.success("订阅已生效；以后用同一邮箱重新验证，即可覆盖更新自选股。")
                try:
                    send_email(
                        address,
                        "A股盘前机会雷达｜订阅已生效",
                        "<p>订阅已生效。系统将在A股交易日北京时间08:45和09:27，按你当前的自选股发送两阶段报告。</p>",
                        "订阅已生效：A股交易日北京时间08:45和09:27发送两阶段报告。",
                    )
                except Exception:
                    st.warning("订阅已经保存，但确认邮件发送失败；定时报告配置不受影响。")
            except Exception as exc:
                st.error(f"保存订阅失败：{exc}")

    if cancel_col.button("取消订阅", width="stretch"):
        ok, address = verified()
        if not ok:
            st.error("取消订阅也需要先完成邮箱验证。")
        else:
            try:
                deactivate_subscription(address)
                st.success("该邮箱已取消后续推送。")
            except Exception as exc:
                st.error(f"取消订阅失败：{exc}")


cfg, universe, mapping_cfg, default_watchlist = load_config()
watch_payload = st.query_params.get("watch", "")
user_watchlist = decode_watchlist(watch_payload, default_watchlist)
now = datetime.now(CN_TZ)
snapshot_key = expected_snapshot_day(now)

load_notice = st.empty()
load_notice.info("正在读取北京时间 08:45 盘前快照…")
market, macro, news, marketwide_signals, universe_coverage, data_mode, generated_at = load_daily_bundle(
    universe, mapping_cfg, snapshot_key
)
existing_tickers = tuple(item.get("ticker", "") for item in market.values())
market.update(load_missing_watchlist_market(user_watchlist, existing_tickers, snapshot_key))
brief = morning_rule_brief(market, macro, news)
health = data_health(market, macro, news)
auction_ready = auction_is_ready(now, snapshot_key)
auction_quotes, market_anomalies, auction_coverage = {}, [], {"mode": "WAITING_09_26", "count": 0}
auction_mode, auction_generated_at = "WAITING_09_26", ""
if auction_ready:
    auction_tickers = tuple(sorted({
        ticker for ticker in ([row["ticker"] for row in user_watchlist] + [target.get("ticker", "") for signal in marketwide_signals for target in signal.get("targets", [])])
        if str(ticker).endswith((".SS", ".SZ", ".BJ"))
    }))
    auction_quotes, market_anomalies, auction_coverage, auction_mode, auction_generated_at = load_auction_bundle(auction_tickers, snapshot_key)
alerts, signals = build_personal_analysis(
    user_watchlist, news, market, mapping_cfg,
    auction_quotes if auction_ready else None,
    marketwide_signals=marketwide_signals,
    market_anomalies=market_anomalies,
)
if not auction_ready:
    alerts = [{**row, "auction": {"status": "等待09:25竞价", "gap_pct": None, "reason": "08:45已给出动态参与条件；09:27再用最终集合竞价结果复核。", "source": ""}} for row in alerts]
auction_counts = auction_status_counts(signals)
verified = [row for row in signals if row["category"] == "海外已验证"]
transmission = [row for row in signals if row["category"] == "传导待验证"]
important_alerts = [row for row in alerts if row["level"] == "重点异动"]
watch_alerts = [row for row in alerts if row["level"] == "需要关注"]
gap_alerts = [row for row in alerts if row.get("auction", {}).get("status") == "仍有预期差"]
overpriced_alerts = [row for row in alerts if row.get("auction", {}).get("status") == "过度定价/追高风险"]
independent_auction_alerts = [row for row in alerts if row.get("auction", {}).get("status") == "竞价独立异动"]
actionable_targets = [target for row in verified for target in row.get("targets", []) if target.get("guidance", {}).get("action") == "可条件参与"]
gap_targets = [target for row in verified for target in row.get("targets", []) if target.get("auction", {}).get("status") == "仍有预期差"]
overpriced_targets = [target for row in verified for target in row.get("targets", []) if target.get("auction", {}).get("status") == "过度定价/追高风险"]
load_notice.empty()

st.markdown(
    """<div class="hero"><div class="eyebrow">08:45 AUCTION PLAN · 09:27 FINAL CHECK</div><div class="hero-title">A股全市场盘前机会雷达</div><div class="hero-sub">08:45从全部A股中搜索隔夜事件受益与受损标的，并用每只股票自己的历史条件分布给出集合竞价参与上限和观察期限；09:27再用最终竞价结果复核。自选股是额外的个人验证层，不是机会搜索的边界。</div></div>""",
    unsafe_allow_html=True,
)

snapshot_text, stale = snapshot_label(generated_at, data_mode, snapshot_key)
universe_usable = bool(
    universe_coverage.get("usable", universe_coverage.get("count", 0) >= 4500)
)
auction_usable = (data_mode == "DEMO") or bool(
    auction_coverage.get("usable", auction_coverage.get("count", 0) >= 3500)
) if auction_ready else True
current_decision_data = data_mode == "DEMO" or (not stale and universe_usable)
market_ratio = f"{health.get('market_live', 0)}/{health.get('market_total', 0)}"
badges = [
    f'<span class="badge {"warn" if data_mode == "DEMO" else "live"}">{escape(data_mode)} · 行情 {market_ratio}</span>',
    f'<span class="badge {"warn" if stale else "live"}">{escape(snapshot_text)}</span>',
    f'<span class="badge">全A股 {universe_coverage.get("count", 0)} · {escape(universe_coverage.get("mode", "未覆盖"))}</span>',
    '<span class="badge">08:45参与条件 · 09:27最终复核</span>',
    f'<span class="badge {"live" if auction_quotes else "warn"}">{escape(auction_mode)} · 竞价 {len(auction_quotes)}</span>',
    f'<span class="badge">自选股 {len(user_watchlist)}/30</span>',
]
st.markdown(f'<div class="statusbar">{"".join(badges)}</div>', unsafe_allow_html=True)
if data_mode == "DEMO":
    st.warning("当前为明确标注的演示模式；演示值不会被当作真实盘前判断。")
elif stale:
    st.warning("最近快照不是当前应使用的交易日快照，可能遇到节假日、任务排队或自动任务失败，请先核对页面日期。")
if data_mode != "DEMO" and not universe_usable:
    st.error("本次没有完成全A股扫描。页面将数据状态标为“不可用”，不会再把未扫描误报成0个机会。")
if auction_ready and auction_quotes and not auction_usable and data_mode != "DEMO":
    st.error(f"集合竞价只覆盖 {auction_coverage.get('count', 0)} 只，低于完整性门槛；09:27结论已停用。")
if auction_ready and not auction_quotes and data_mode != "DEMO":
    st.warning("09:25集合竞价数据暂不可用，因此今天只能展示海外候选，不能判断是否仍有交易价值。")

page = st.radio("主导航", ["盘前决策台", "机会雷达", "方法与数据"], horizontal=True, label_visibility="collapsed")


if page == "盘前决策台":
    cols = st.columns(4)
    if not current_decision_data:
        cols[0].metric("全市场扫描", "不可用", "等待当日有效快照")
        cols[1].metric("参与条件", "不可用", "禁止据此下单")
        cols[2].metric("事件判断", "不可用", "不是0个机会")
        cols[3].metric("竞价判断", "不可用", "等待完整数据")
    elif auction_ready and auction_quotes and not auction_usable:
        cols[0].metric("仍有预期差", "不可用", "竞价覆盖不足")
        cols[1].metric("基本定价", "不可用", "竞价覆盖不足")
        cols[2].metric("追高风险", "不可用", "竞价覆盖不足")
        cols[3].metric("全市场独立异动", "不可用", f"仅覆盖 {auction_coverage.get('count', 0)} 只")
    elif auction_ready and auction_quotes:
        cols[0].metric("仍有预期差", auction_counts["仍有预期差"], "优先进入开盘观察")
        cols[1].metric("基本定价", auction_counts["基本定价"], "不再视为明显预期差")
        cols[2].metric("追高风险", auction_counts["过度定价/追高风险"], "竞价反应过度")
        cols[3].metric("全市场独立异动", len(market_anomalies), f"竞价覆盖 {auction_coverage.get('count', 0)} 只")
    else:
        cols[0].metric("全市场已验证事件", len(verified), f"覆盖 {universe_coverage.get('count', 0)} 只A股")
        cols[1].metric("可条件参与标的", len(actionable_targets), "每只股票独立阈值")
        cols[2].metric("传导待验证", len(transmission), "不直接作为交易结论")
        cols[3].metric("自选股重点异动", len(important_alerts), f"另有 {len(watch_alerts)} 只需关注")

    st.markdown('<div class="section">今天先处理什么</div>', unsafe_allow_html=True)
    if not current_decision_data:
        st.error("今天尚未生成通过覆盖门槛的盘前快照，因此不能得出“没有机会”的结论，也不能用于集合竞价下单。")
    elif auction_ready and not auction_usable:
        st.error("09:27全市场竞价数据不完整，本次不输出仍有预期差、基本定价或追高风险结论。")
    elif gap_targets:
        top_names = "、".join(row["name"] for row in gap_targets[:6])
        st.markdown(f'<div class="callout"><b>全市场竞价后仍有预期差：</b>{escape(top_names)}。每只标的均沿用08:45动态阈值，并在下方注明主要观察期限。</div>', unsafe_allow_html=True)
    elif overpriced_targets:
        top_names = "、".join(row["name"] for row in overpriced_targets[:6])
        st.markdown(f'<div class="callout"><b>注意追高风险：</b>{escape(top_names)} 已在集合竞价中大幅反应。海外验证成立，但交易价值可能已被高开消耗。</div>', unsafe_allow_html=True)
    elif market_anomalies:
        top_names = "、".join(row["name"] for row in market_anomalies[:6])
        st.markdown(f'<div class="callout"><b>全市场独立竞价异动：</b>{escape(top_names)} 进入同板块×同规模股票的当日异常尾部；目前缺少事件解释，只作为T+0反查线索。</div>', unsafe_allow_html=True)
    elif actionable_targets:
        top_names = "、".join(row["name"] for row in actionable_targets[:6])
        st.markdown(f'<div class="callout"><b>08:45可用于集合竞价计划：</b>{escape(top_names)} 已生成个股动态参与条件。请严格按下方每只股票的上限价格/高开幅度执行条件判断。</div>', unsafe_allow_html=True)
    elif verified:
        st.markdown(f'<div class="callout"><b>自选股暂无重点异动。</b>今日仍有 {len(verified)} 条海外已验证信号，可在“机会雷达”中检查是否值得临时加入观察。</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="callout"><b>今日没有达到强提示阈值的信号。</b>这也是有效结论：不为了每天都有交易机会而降低证据标准。</div>', unsafe_allow_html=True)

    st.markdown('<div class="section">全A股事件机会（主区）<span class="section-note">不是只看大盘股、热门股或自选股；行业级命中必须继续核对主营业务</span></div>', unsafe_allow_html=True)
    if not current_decision_data:
        st.info("等待今天的全A股有效快照；下方不展示旧数据作为今日机会。")
    elif verified:
        for row in verified[:8]:
            render_signal(row)
    elif transmission:
        st.info("今天没有通过海外价格验证的全市场事件，以下线索只能观察，不能直接用于下单。")
        for row in transmission[:4]:
            render_signal(row)
    else:
        st.info("今天没有达到新闻证据门槛的全市场事件机会。")

    if auction_ready and current_decision_data and auction_usable:
        st.markdown('<div class="section">全市场独立竞价异动<span class="section-note">按板块×市值分组的当日95%分位，不使用统一2%阈值</span></div>', unsafe_allow_html=True)
        if market_anomalies:
            st.dataframe(pd.DataFrame([{ "股票": f"{row.get('name')}（{str(row.get('ticker','')).split('.')[0]}）", "竞价涨跌": f"{row.get('gap_pct',0):+.2f}%", "板块": row.get('board'), "规模": row.get('size_bucket'), "当日异常线": f"{row.get('dynamic_threshold_pct',0):.2f}%", "期限": "T+0", "证据状态": row.get('evidence_state')} for row in market_anomalies]), hide_index=True, width="stretch")
        else:
            st.info("未发现进入分组异常尾部的独立竞价标的，或全市场竞价覆盖不足。")

    st.markdown('<div class="section">你的自选股验证<span class="section-note">个人关注层，不限制全市场机会发现</span></div>', unsafe_allow_html=True)
    active_alerts = [
        row for row in alerts
        if row["level"] != "暂无异动" or row.get("auction", {}).get("status") == "竞价独立异动"
    ]
    if active_alerts:
        for row in active_alerts:
            render_alert(row)
    else:
        st.info("当前自选股未发现可靠新闻或显著海外代理波动。")
    remaining_count = len(alerts) - len(active_alerts)
    with st.expander(f"查看其余 {remaining_count} 只暂无异动的自选股", expanded=False):
        for row in alerts:
            if row not in active_alerts:
                render_alert(row)

    st.markdown('<div class="section">管理自选股<span class="section-note">页面内直接增删，无需后台改代码</span></div>', unsafe_allow_html=True)
    with st.expander("打开自选股编辑器"):
        st.caption("只需要输入股票代码或名称。公司名称、主题、海外代理、传导方向和新闻关键词均由系统自动识别与判断。")
        editor = st.data_editor(
            pd.DataFrame(watchlist_editor_rows(user_watchlist)), hide_index=True, num_rows="dynamic", width="stretch",
            column_config={
                "股票代码或名称": st.column_config.TextColumn("股票代码或名称", required=True),
            }, key="watchlist_editor",
        )
        save_col, reset_col, note_col = st.columns([1, 1, 2.3])
        if save_col.button("保存自选股", type="primary", width="stretch"):
            inputs = watchlist_inputs_from_editor(editor.to_dict("records"))
            if not inputs:
                st.error("至少保留一只有效的A股代码。")
            else:
                with st.spinner("正在识别公司并自动完成主题、海外代理与传导关系…"):
                    edited_rows, errors = enrich_watchlist_inputs(
                        inputs, [*default_watchlist, *user_watchlist], universe, mapping_cfg
                    )
                if errors:
                    st.warning("；".join(errors))
                if not edited_rows:
                    st.error("没有识别到有效A股，请检查输入。")
                else:
                    st.query_params["watch"] = encode_watchlist(edited_rows)
                    st.rerun()
        if reset_col.button("恢复默认", width="stretch"):
            if "watch" in st.query_params:
                del st.query_params["watch"]
            st.rerun()
        note_col.caption("网页配置仍保存在当前网址；完成邮箱验证并订阅后，同一份自选股会保存为邮件推送配置。")

        with st.expander("查看系统自动补齐的研究映射"):
            st.dataframe(pd.DataFrame([
                {
                    "股票": f"{row['name']}（{row['ticker'].split('.')[0]}）",
                    "主题": row["theme"],
                    "传导方向": row["relation"],
                    "海外代理": ", ".join(row.get("overseas_assets", [])),
                    "判断来源": row.get("profile_source") or "历史配置",
                    "置信度": row.get("profile_confidence") or "未标注",
                }
                for row in user_watchlist
            ]), hide_index=True, width="stretch")

    render_subscription_panel(user_watchlist)

    export = export_markdown(alerts, signals, generated_at or snapshot_text)
    st.download_button("下载今日盘前简报", data=export, file_name=f"A股盘前简报_{snapshot_key}.md", mime="text/markdown")


elif page == "机会雷达":
    st.markdown('<div class="section">全A股今日机会雷达<span class="section-note">事件→海外价格→全市场行业检索→个股历史阈值→最终竞价</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="callout"><b>08:45不是只建候选池。</b>当事件方向、公司映射和历史样本均达标时，系统已经给出可参与集合竞价的最高高开幅度/价格。09:27用最终成交价复核；样本不足的股票不会套用统一百分比。</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    theme_filter = f1.selectbox("主题", ["全部"] + list(mapping_cfg))
    watch_only = f2.toggle("只看命中自选股", value=False)
    auction_filter = f3.selectbox("竞价判断", ["全部", "仍有预期差", "基本定价", "过度定价/追高风险", "A股不确认", "数据不足/仅观察", "方向需人工判断"])

    def visible(rows):
        output = []
        for row in rows:
            statuses = {target.get("auction", {}).get("status") for target in row.get("targets", [])}
            if theme_filter != "全部" and row["theme"] != theme_filter:
                continue
            if watch_only and not row["watchlist_relevant"]:
                continue
            if auction_filter != "全部" and auction_filter not in statuses:
                continue
            output.append(row)
        return output

    verified_view, transmission_view = visible(verified), visible(transmission)
    tabs = st.tabs([f"海外已验证 · {len(verified_view)}", f"传导待验证 · {len(transmission_view)}"])
    with tabs[0]:
        st.caption("每条事件都展示新闻原文、来源、时间、海外价格、传导链、公司映射、各期限历史分布和最终竞价结果。")
        if not verified_view:
            st.info("当前筛选下没有达到海外价格确认阈值的可靠事件。")
        for row in verified_view:
            render_signal(row)
    with tabs[1]:
        st.caption("有逻辑但尚无价格确认。它们适合加入观察清单，不适合直接当作交易结论。")
        if not transmission_view:
            st.info("当前筛选下没有可靠但尚待价格验证的事件。")
        for row in transmission_view:
            render_signal(row)

    st.markdown('<div class="section">信号如何被保留和复盘</div>', unsafe_allow_html=True)
    st.write("每日08:45快照会保存新闻、海外价格、全A股覆盖、候选映射、动态阈值及期限分布；09:27再保存全市场竞价覆盖与复核结果。后续可以按T+0/T+3/T+5/T+20分别校验命中率，而不是把所有“预期差”混成一个期限。")


else:
    st.markdown('<div class="section">方法与数据<span class="section-note">明确它能做什么，也明确它不能做什么</span></div>', unsafe_allow_html=True)
    st.markdown("#### 产品定位")
    st.write("这是一个A股盘前研究与机会筛选工具，不是行情终端。它从全部上市A股（数据源实际返回的可交易股票）中寻找隔夜事件映射，再按个股历史条件分布形成竞价计划和复核结果。")
    st.markdown("#### 两阶段判断")
    stages = pd.DataFrame([
        {"时间": "08:45", "输出": "全市场事件候选＋竞价参与条件", "判断": "最高可接受高开/价格、主要期限、历史概率、样本与置信度", "不能决定": "订单一定成交或未来一定盈利"},
        {"时间": "09:27", "输出": "最终竞价复核＋全市场独立异动", "判断": "仍有预期差、基本定价、追高风险、不确认、数据不足", "不能决定": "开盘后一定上涨或下跌"},
    ])
    st.dataframe(stages, hide_index=True, width="stretch")
    st.markdown("#### 两类信号")
    method = pd.DataFrame([
        {"类型": "海外已验证", "进入条件": "证据分≥70，且相关海外代理单日显著波动或多个代理同向", "用途": "优先检查A股盘前预期差", "不能代表": "A股一定跟涨或跟跌"},
        {"类型": "传导待验证", "进入条件": "证据分≥70，存在明确A股传导链，但海外价格尚未确认", "用途": "加入盘前观察，等待集合竞价验证", "不能代表": "可直接交易的信号"},
    ])
    st.dataframe(method, hide_index=True, width="stretch")
    st.markdown('<div class="formula"><b>08:45动态参与上限</b>：取该股近一年开盘/收盘历史，与相关海外代理的上一交易日收益对齐；筛选同方向且幅度相近的样本并加权，在满足所需历史正收益概率后，计算可接受开盘缺口分位数并扣除0.18%成本缓冲。行业级映射和较弱证据会提高所需概率。<br><b>硬门槛：</b>同方向样本至少20个、有效样本至少8；不足时显示“样本不足”，不回退到固定阈值。</div>', unsafe_allow_html=True)
    st.markdown("#### 09:27集合竞价判定")
    st.write("系统把最终竞价高开与08:45为该股票计算的动态上限比较：低于上限才可能标记“仍有预期差”；超过上限为“基本定价”，进入该股历史高位尾部为“追高风险”。与海外方向显著相反时标记“A股不确认”。没有动态阈值时只显示“数据不足/仅观察”。")
    st.markdown("#### 预期差的期限")
    st.write("每只股票会分别计算T+0、T+3、T+5或T+20的历史结果，并显示概率经风险惩罚后最优的“主要期限”。这只是模型的复核窗口，不是建议必须持有到该天；事件失效时应提前退出研究假设。")
    st.markdown("#### 全市场发现")
    st.write("系统读取全部A股基础列表与当日市场快照，按事件主题匹配行业，并在小/中/大市值组中轮流选择候选，避免只返回大盘或热门股票。行业字段命中只属于初筛，界面会明确标记“行业级候选”，要求继续核对主营收入和公告。09:27独立异动则按板块×市值组当日95%分位识别，不使用统一2%阈值。")
    st.markdown("#### 自选股异动定义")
    st.write("系统将直接公司新闻、同主题可靠新闻和用户指定的海外代理波动合并判断。出现直接相关新闻，或可靠主题新闻与显著海外波动共同出现时，标记为“重点异动”；只有其中一类证据时，标记为“需要关注”。")
    st.markdown("#### 数据与刷新")
    st.write("- **刷新与邮件：** 每个A股交易日08:45生成海外候选并发送第一封邮件，09:27生成集合竞价复核并发送第二封邮件；不进行15分钟循环刷新。")
    st.write("- **市场代理与历史：** Yahoo Finance，用于海外收盘价格及候选A股近一年开盘/收盘序列；页面显示快照与样本量。")
    st.write("- **新闻发现：** GDELT，失败时回退Google News RSS；只让证据分≥70的新闻进入机会雷达。")
    st.write("- **宏观背景：** FRED与美国财政部，仅用于风险环境，不再提供独立跨资产看板。")
    st.write("- **全A股列表：** 直接读取上交所、深交所、北交所官方上市名单，不需要Token；失败时只允许使用14天内的最近有效缓存。")
    st.write("- **集合竞价：** 使用腾讯免费批量行情获取全市场09:25开盘价，并以东方财富公开行情补缺；覆盖不足3500只时停止输出结论和邮件。")
    st.write("- **用户配置：** 网页只要求输入股票；系统自动补齐研究映射。通过邮箱验证后，订阅配置会持久化保存，用于两次个性化邮件。")
    st.markdown("#### 边界")
    st.write("免费数据源可能延迟或中断；系统会明确标注快照、覆盖数量和DEMO状态。行业映射不是主营业务证明，历史条件概率也不是未来收益保证。最终仍需核对原文、公司公告、涨跌停规则、流动性与实际委托限制。")
    st.caption("研究辅助，不构成投资建议。")
    fetch_a_share_universe,
    fetch_all_auction_quotes,
