from __future__ import annotations

from email.message import EmailMessage
from html import escape
import smtplib
import ssl

from .subscriptions import get_secret, normalize_email


def email_configured() -> bool:
    return bool(
        get_secret("SMTP_HOST")
        and get_secret("SMTP_USERNAME")
        and get_secret("SMTP_PASSWORD")
        and get_secret("EMAIL_FROM")
    )


def send_email(to: str, subject: str, html: str, text: str = "") -> None:
    recipient = normalize_email(to)
    if not recipient:
        raise ValueError("收件邮箱格式无效。")
    if not email_configured():
        raise RuntimeError("邮件服务尚未配置。")

    message = EmailMessage()
    message["From"] = get_secret("EMAIL_FROM")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text or "请使用支持HTML的邮件客户端查看这封报告。")
    message.add_alternative(html, subtype="html")

    host = get_secret("SMTP_HOST")
    port = int(get_secret("SMTP_PORT", "465"))
    username = get_secret("SMTP_USERNAME")
    password = get_secret("SMTP_PASSWORD")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(username, password)
            server.send_message(message)


def send_verification_code(to: str, code: str) -> None:
    send_email(
        to,
        "A股盘前机会雷达｜邮箱验证码",
        f"""<div style="font-family:Arial,'Microsoft YaHei',sans-serif;max-width:560px;margin:auto;color:#101828">
        <h2>验证你的订阅邮箱</h2>
        <p>验证码：</p><div style="font-size:30px;font-weight:700;letter-spacing:8px;padding:16px;background:#f2f4f7;border-radius:10px">{escape(code)}</div>
        <p>验证码10分钟内有效。只有完成验证后，系统才会向该地址发送报告。</p>
        <p style="color:#667085;font-size:13px">如果不是你本人操作，请忽略本邮件。</p></div>""",
        f"A股盘前机会雷达验证码：{code}。10分钟内有效。",
    )
