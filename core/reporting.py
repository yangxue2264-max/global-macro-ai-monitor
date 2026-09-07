from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .preopen import (
    attach_auction_results,
    attach_auction_to_alerts,
    build_opportunity_signals,
    build_watchlist_alerts,
    rerank_signals_after_auction,
)


CN = ZoneInfo("Asia/Shanghai")


def build_personal_analysis(watchlist, news, market, mapping_cfg, auction_quotes=None):
    alerts = build_watchlist_alerts(watchlist, news, market, mapping_cfg)
    signals = build_opportunity_signals(news, market, mapping_cfg, watchlist)
    if auction_quotes is not None:
        signals = attach_auction_results(signals, auction_quotes)
        signals = rerank_signals_after_auction(signals)
        alerts = attach_auction_to_alerts(alerts, signals, auction_quotes)
    return alerts, signals


def _move_text(rows: list[dict]) -> str:
    return "；".join(f"{row.get('name', row.get('key', ''))} {row.get('move', 0):+.2f}%" for row in rows) or "无有效海外价格"


def _layout(title: str, intro: str, body: str, app_url: str) -> str:
    button = ""
    if app_url:
        button = f'<p><a href="{escape(app_url, quote=True)}" style="display:inline-block;background:#175cd3;color:white;text-decoration:none;padding:10px 16px;border-radius:8px">打开完整机会雷达</a></p>'
    return f"""<!doctype html><html><body style="margin:0;background:#f8fafc">
    <div style="max-width:720px;margin:0 auto;padding:24px;font-family:Arial,'Microsoft YaHei',sans-serif;color:#101828">
      <div style="background:white;border:1px solid #e4e7ec;border-radius:14px;padding:24px">
        <div style="font-size:12px;color:#175cd3;font-weight:700;letter-spacing:.08em">A股盘前机会雷达</div>
        <h1 style="font-size:23px;margin:7px 0 8px">{escape(title)}</h1>
        <p style="color:#475467;line-height:1.6">{escape(intro)}</p>
        {body}{button}
        <hr style="border:0;border-top:1px solid #e4e7ec;margin:24px 0">
        <p style="color:#667085;font-size:12px;line-height:1.6">研究辅助，不构成投资建议。优先级与预期差分类不是收益预测。免费行情或新闻可能延迟；请以邮件中的数据状态和原始来源为准。</p>
        <p style="color:#667085;font-size:12px">修改或取消订阅：返回网站，用同一邮箱接收验证码后操作。</p>
      </div>
    </div></body></html>"""


def render_morning_email(alerts: list[dict], signals: list[dict], generated_at: str, app_url: str = ""):
    important = [row for row in alerts if row.get("level") == "重点异动"]
    relevant = [row for row in signals if row.get("watchlist_relevant")][:6]
    date = datetime.now(CN).strftime("%m月%d日")
    subject = f"{date} 08:45盘前｜{len(important)}只自选股重点异动"
    if not important:
        subject = f"{date} 08:45盘前｜自选股暂无强信号"

    cards = []
    for row in alerts:
        color = "#b42318" if row.get("level") == "重点异动" else "#b54708" if row.get("level") == "需要关注" else "#667085"
        headline = escape(row.get("headline") or "暂无直接相关新闻")
        link = row.get("news_url") or ""
        if link:
            headline = f'<a href="{escape(link, quote=True)}" style="color:#175cd3">{headline}</a>'
        cards.append(f"""<div style="border-left:4px solid {color};padding:10px 14px;margin:12px 0;background:#f9fafb">
          <div style="font-weight:700">{escape(row.get('name',''))} · {escape(row.get('level',''))}</div>
          <div style="font-size:13px;color:#475467;margin-top:5px">{escape(row.get('theme',''))}｜{escape(row.get('reason',''))}</div>
          <div style="font-size:13px;color:#475467;margin-top:5px">海外：{escape(_move_text(row.get('overseas_moves', [])))}</div>
          <div style="font-size:13px;margin-top:5px">新闻：{headline}</div>
        </div>""")
    signal_rows = "".join(
        f"<li style='margin:7px 0'><b>{escape(row.get('category',''))}｜{escape(row.get('theme',''))}</b>：{escape(row.get('title',''))}（优先级 {int(row.get('priority',0))}）</li>"
        for row in relevant
    ) or "<li>今天没有命中自选股且达到证据门槛的主题事件。</li>"
    body = f"""<h2 style="font-size:17px;margin-top:22px">自选股扫描</h2>{''.join(cards)}
    <h2 style="font-size:17px;margin-top:22px">与自选股相关的机会线索</h2><ul style="padding-left:20px;color:#344054;line-height:1.5">{signal_rows}</ul>
    <p style="font-size:12px;color:#667085">快照时间：{escape(generated_at)}</p>"""
    intro = "第一阶段只判断可靠新闻、海外价格是否验证，以及它们与自选股的传导关系；最终是否仍有预期差，要等09:27集合竞价复核。"
    text = "\n".join([subject, intro] + [f"{row['name']}｜{row['level']}｜{row['reason']}" for row in alerts])
    return subject, _layout("08:45 海外候选与自选股扫描", intro, body, app_url), text


def render_auction_email(alerts: list[dict], signals: list[dict], generated_at: str, app_url: str = ""):
    date = datetime.now(CN).strftime("%m月%d日")
    statuses = [row.get("auction", {}).get("status", "竞价数据缺失") for row in alerts]
    gaps = sum(status == "仍有预期差" for status in statuses)
    risks = sum(status == "过度定价/追高风险" for status in statuses)
    standalone = sum(status == "竞价独立异动" for status in statuses)
    subject = f"{date} 09:27竞价｜{gaps}只仍有预期差，{risks}只追高风险，{standalone}只独立异动"

    cards = []
    colors = {
        "仍有预期差": "#067647",
        "基本定价": "#6941c6",
        "过度定价/追高风险": "#b42318",
        "A股不确认": "#b54708",
        "竞价独立异动": "#b54708",
    }
    for row in alerts:
        auction = row.get("auction", {})
        status = auction.get("status", "竞价数据缺失")
        gap = auction.get("gap_pct")
        gap_text = "数据缺失" if gap is None else f"{gap:+.2f}%"
        cards.append(f"""<div style="border-left:4px solid {colors.get(status, '#98a2b3')};padding:10px 14px;margin:12px 0;background:#f9fafb">
          <div style="font-weight:700">{escape(row.get('name',''))} · {escape(status)}</div>
          <div style="font-size:13px;color:#475467;margin-top:5px">集合竞价：{escape(gap_text)}｜{escape(auction.get('reason',''))}</div>
          <div style="font-size:13px;color:#475467;margin-top:5px">此前线索：{escape(row.get('reason',''))}</div>
        </div>""")
    intro = f"第二阶段已用集合竞价检查自选股对隔夜信号的消化程度：{gaps}只仍有预期差，{risks}只出现追高风险，{standalone}只出现无对应海外信号的独立异动。数据缺失时，系统不会强行给出交易结论。"
    body = f"""<h2 style="font-size:17px;margin-top:22px">集合竞价后二次判断</h2>{''.join(cards)}
    <p style="font-size:12px;color:#667085">竞价快照时间：{escape(generated_at)}</p>"""
    text = "\n".join([subject, intro] + [f"{row['name']}｜{row.get('auction',{}).get('status','竞价数据缺失')}" for row in alerts])
    return subject, _layout("09:27 集合竞价复核", intro, body, app_url), text
