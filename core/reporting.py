from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .opportunity_model import attach_dynamic_guidance
from .preopen import (
    attach_auction_results,
    attach_auction_to_alerts,
    build_opportunity_signals,
    build_watchlist_alerts,
    rerank_signals_after_auction,
)


CN = ZoneInfo("Asia/Shanghai")


def _merge_personal_signals(common: list[dict], personal: list[dict]) -> list[dict]:
    """Keep full-market discovery and add the recipient's own stocks to those events."""
    merged = [dict(row) for row in common]
    positions = {(row.get("title"), row.get("theme")): index for index, row in enumerate(merged)}
    for signal in personal:
        key = (signal.get("title"), signal.get("theme"))
        if key not in positions:
            positions[key] = len(merged)
            merged.append(dict(signal))
            continue
        index = positions[key]
        row = dict(merged[index])
        targets = [dict(target) for target in row.get("targets", [])]
        by_ticker = {target.get("ticker"): pos for pos, target in enumerate(targets)}
        for target in signal.get("targets", []):
            target = dict(target)
            ticker = target.get("ticker")
            if ticker in by_ticker and target.get("source") == "自选股":
                targets[by_ticker[ticker]] = {**targets[by_ticker[ticker]], **target}
            elif ticker not in by_ticker:
                targets.insert(0, target)
                by_ticker = {item.get("ticker"): pos for pos, item in enumerate(targets)}
        row["targets"] = targets
        row["watchlist_relevant"] = bool(row.get("watchlist_relevant") or signal.get("watchlist_relevant"))
        row["direct_watch_match"] = bool(row.get("direct_watch_match") or signal.get("direct_watch_match"))
        merged[index] = row
    merged.sort(key=lambda row: (row.get("category") != "海外已验证", not row.get("watchlist_relevant"), -int(row.get("priority", 0))))
    return merged


def build_personal_analysis(
    watchlist, news, market, mapping_cfg, auction_quotes=None,
    marketwide_signals: list[dict] | None = None,
    market_anomalies: list[dict] | None = None,
):
    alerts = build_watchlist_alerts(watchlist, news, market, mapping_cfg)
    personal = build_opportunity_signals(news, market, mapping_cfg, watchlist)
    signals = _merge_personal_signals(marketwide_signals or [], personal) if marketwide_signals is not None else personal
    signals = attach_dynamic_guidance(signals, market)
    if auction_quotes is not None:
        signals = attach_auction_results(signals, auction_quotes)
        signals = rerank_signals_after_auction(signals)
        alerts = attach_auction_to_alerts(alerts, signals, auction_quotes, market_anomalies)
    return alerts, signals


def _move_text(rows: list[dict]) -> str:
    return "；".join(f"{row.get('name', row.get('key', ''))} {row.get('move', 0):+.2f}%" + (f"（近一年{row['tail_percentile']:.0%}分位）" if row.get("tail_percentile") is not None else "") for row in rows) or "无有效海外价格"


def _layout(title: str, intro: str, body: str, app_url: str) -> str:
    button = ""
    if app_url:
        button = f'<p><a href="{escape(app_url, quote=True)}" style="display:inline-block;background:#175cd3;color:white;text-decoration:none;padding:10px 16px;border-radius:8px">打开完整机会雷达</a></p>'
    return f"""<!doctype html><html><body style="margin:0;background:#f8fafc">
    <div style="max-width:760px;margin:0 auto;padding:24px;font-family:Arial,'Microsoft YaHei',sans-serif;color:#101828">
      <div style="background:white;border:1px solid #e4e7ec;border-radius:14px;padding:24px">
        <div style="font-size:12px;color:#175cd3;font-weight:700;letter-spacing:.08em">A股盘前机会雷达</div>
        <h1 style="font-size:23px;margin:7px 0 8px">{escape(title)}</h1>
        <p style="color:#475467;line-height:1.6">{escape(intro)}</p>
        {body}{button}
        <hr style="border:0;border-top:1px solid #e4e7ec;margin:24px 0">
        <p style="color:#667085;font-size:12px;line-height:1.6">研究辅助，不构成投资建议。系统只在历史样本达标时提供条件阈值；行业级候选仍须核对主营业务。免费行情或新闻可能延迟，请以邮件中的覆盖范围、时间和原始来源为准。</p>
        <p style="color:#667085;font-size:12px">修改或取消订阅：返回网站，用同一邮箱接收验证码后操作。</p>
      </div>
    </div></body></html>"""


def _guidance_text(target: dict) -> str:
    guidance = target.get("guidance") or {}
    if guidance.get("max_gap_pct") is None:
        return f"{guidance.get('action', '仅观察')}｜{guidance.get('reason', '动态样本不足')}"
    price = f"，价格≤{guidance['max_price']:.3f}元" if guidance.get("max_price") else ""
    return (
        f"{guidance.get('action')}｜高开≤{guidance['max_gap_pct']:.2f}%{price}｜"
        f"期限 {guidance.get('primary_horizon')}｜有效样本 {guidance.get('effective_sample')}｜置信度 {guidance.get('confidence')}"
    )


def _market_signal_cards(signals: list[dict], auction: bool = False, limit: int = 6) -> str:
    cards = []
    for row in signals[:limit]:
        targets = []
        for target in row.get("targets", [])[:5]:
            if auction:
                result = target.get("auction") or {}
                gap = "数据缺失" if result.get("gap_pct") is None else f"{result['gap_pct']:+.2f}%"
                detail = f"{result.get('status', '待判断')}｜竞价{gap}｜期限 {result.get('primary_horizon') or target.get('guidance', {}).get('primary_horizon', '未判定')}"
            else:
                detail = _guidance_text(target)
            mapping = target.get("mapping_level") or target.get("source") or ""
            targets.append(f"<li style='margin:5px 0'><b>{escape(target.get('name',''))}</b>（{escape(mapping)}）：{escape(detail)}</li>")
        title = escape(row.get("title", ""))
        if row.get("url"):
            title = f'<a href="{escape(row["url"], quote=True)}" style="color:#175cd3">{title}</a>'
        cards.append(f"""<div style="border:1px solid #e4e7ec;border-left:4px solid {'#12b76a' if row.get('category') == '海外已验证' else '#7f56d9'};padding:12px 14px;margin:12px 0;border-radius:8px;background:#fff">
          <div style="font-weight:700">{escape(row.get('theme',''))} · {escape(row.get('category',''))} · {int(row.get('priority',0))}/100</div>
          <div style="font-size:14px;margin-top:5px">{title}</div>
          <div style="font-size:12px;color:#667085;margin-top:4px">{escape(row.get('source',''))}｜证据 {row.get('evidence',0)}/100｜{escape(row.get('published',''))}</div>
          <div style="font-size:13px;color:#344054;margin-top:6px">海外验证：{escape(_move_text(row.get('price_moves', [])))}</div>
          <div style="font-size:13px;color:#344054">传导：{escape(row.get('mechanism',''))}</div>
          <ul style="padding-left:20px;color:#344054;font-size:13px;line-height:1.45">{''.join(targets) or '<li>暂无通过映射核查的A股候选</li>'}</ul>
          <div style="font-size:12px;color:#b42318">失效条件：{escape(row.get('risk',''))}</div>
        </div>""")
    return "".join(cards) or "<p>今天没有达到证据与价格门槛的全市场事件候选。</p>"


def _watchlist_cards(alerts: list[dict], auction: bool = False) -> str:
    cards = []
    for row in alerts:
        if not auction and row.get("level") == "暂无异动":
            continue
        if auction:
            result = row.get("auction") or {}
            gap = "数据缺失" if result.get("gap_pct") is None else f"{result['gap_pct']:+.2f}%"
            detail = f"{result.get('status', '竞价数据缺失')}｜竞价 {gap}｜{result.get('reason','')}"
        else:
            detail = f"{row.get('level')}｜{row.get('reason')}"
        headline = escape(row.get("headline") or "暂无直接相关新闻")
        if row.get("news_url"):
            headline = f'<a href="{escape(row["news_url"], quote=True)}" style="color:#175cd3">{headline}</a>'
        cards.append(f"""<div style="border-left:4px solid #84adff;padding:10px 14px;margin:10px 0;background:#f9fafb">
          <div style="font-weight:700">{escape(row.get('name',''))} · {escape(row.get('ticker',''))}</div>
          <div style="font-size:13px;color:#475467;margin-top:5px">{escape(detail)}</div>
          <div style="font-size:13px;color:#475467">海外：{escape(_move_text(row.get('overseas_moves', [])))}</div>
          <div style="font-size:13px">新闻：{headline}｜证据 {row.get('evidence_score',0)}/100</div>
        </div>""")
    return "".join(cards) or "<p>自选股暂无达到提示门槛的异动。</p>"


def render_morning_email(alerts: list[dict], signals: list[dict], generated_at: str, app_url: str = "", coverage: dict | None = None):
    verified = [row for row in signals if row.get("category") == "海外已验证"]
    actionable = sum(target.get("guidance", {}).get("action") == "可条件参与" for row in verified for target in row.get("targets", []))
    date = datetime.now(CN).strftime("%m月%d日")
    subject = f"{date} 08:45盘前｜全市场{len(verified)}条已验证事件，{actionable}只具备动态参与条件"
    coverage_text = f"全A股覆盖：{(coverage or {}).get('count', '未记录')}只（{(coverage or {}).get('mode', '覆盖模式未记录')}）"
    intro = "08:45已经给出参与集合竞价的条件参考：只有事件、方向和个股历史样本同时达标时，才显示最高可接受高开幅度/价格；09:27再用最终竞价成交结果复核。"
    body = f"""<p style="font-size:12px;color:#667085">{escape(coverage_text)}｜快照 {escape(generated_at)}</p>
    <h2 style="font-size:18px;margin-top:22px">全A股今日发现（优先）</h2>{_market_signal_cards(signals, auction=False)}
    <h2 style="font-size:18px;margin-top:24px">你的自选股验证</h2>{_watchlist_cards(alerts)}"""
    text = "\n".join([subject, intro, coverage_text] + [f"{row['theme']}｜{row['title']}" for row in signals[:8]])
    return subject, _layout("08:45 全市场发现与集合竞价条件", intro, body, app_url), text


def render_auction_email(alerts: list[dict], signals: list[dict], generated_at: str, app_url: str = "", anomalies: list[dict] | None = None, coverage: dict | None = None):
    all_targets = [target for row in signals for target in row.get("targets", [])]
    gaps = sum(target.get("auction", {}).get("status") == "仍有预期差" for target in all_targets)
    risks = sum(target.get("auction", {}).get("status") == "过度定价/追高风险" for target in all_targets)
    date = datetime.now(CN).strftime("%m月%d日")
    subject = f"{date} 09:27竞价｜全市场{gaps}只仍有预期差，{risks}只追高风险"
    anomaly_rows = "".join(
        f"<li><b>{escape(row.get('name',''))}</b> {row.get('gap_pct',0):+.2f}%｜{escape(row.get('board',''))}×{escape(row.get('size_bucket',''))} 95%分位线 {row.get('dynamic_threshold_pct',0):.2f}%｜仅T+0异动线索</li>"
        for row in (anomalies or [])[:10]
    ) or "<li>全市场竞价中没有达到分组异常尾部的独立标的，或全市场数据不足。</li>"
    coverage_text = f"竞价覆盖：{(coverage or {}).get('count', '未记录')}只（{(coverage or {}).get('mode', '覆盖模式未记录')}）"
    intro = f"09:27已按08:45每只股票自己的动态阈值复核最终集合竞价：{gaps}只仍有预期差，{risks}只出现追高风险。每条结果都标明主要历史观察期限。"
    body = f"""<p style="font-size:12px;color:#667085">{escape(coverage_text)}｜快照 {escape(generated_at)}</p>
    <h2 style="font-size:18px;margin-top:22px">全市场事件候选竞价验证</h2>{_market_signal_cards(signals, auction=True)}
    <h2 style="font-size:18px;margin-top:24px">全市场独立竞价异动</h2><ul style="font-size:13px;color:#344054;line-height:1.55">{anomaly_rows}</ul>
    <h2 style="font-size:18px;margin-top:24px">你的自选股竞价验证</h2>{_watchlist_cards(alerts, auction=True)}"""
    text = "\n".join([subject, intro, coverage_text] + [f"{target.get('name')}｜{target.get('auction',{}).get('status')}｜{target.get('auction',{}).get('primary_horizon','未判定')}" for target in all_targets[:15]])
    return subject, _layout("09:27 全市场集合竞价复核", intro, body, app_url), text
