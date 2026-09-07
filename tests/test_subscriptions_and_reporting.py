import json
import os
from pathlib import Path

import core.emailing as emailing
import core.subscriptions as subscriptions
from core.providers import flatten_watchlist, load_watchlist
from core.reporting import build_personal_analysis, render_auction_email, render_morning_email
from core.stock_enrichment import enrich_watchlist_inputs
from core.subscriptions import normalize_email


assert normalize_email(" Person@Example.COM ") == "person@example.com"
assert normalize_email("not-an-email") == ""


class FakeResponse:
    content = b"[]"

    def raise_for_status(self):
        return None

    def json(self):
        return []


captured_request = {}
original_request = subscriptions.requests.request
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_SECRET_KEY"] = "sb_secret_test"


def fake_request(method, url, **kwargs):
    captured_request.update(method=method, url=url, **kwargs)
    return FakeResponse()


subscriptions.requests.request = fake_request
assert subscriptions.list_active_subscriptions() == []
assert captured_request["headers"]["apikey"] == "sb_secret_test"
assert "Authorization" not in captured_request["headers"]
subscriptions.requests.request = original_request
del os.environ["SUPABASE_URL"]
del os.environ["SUPABASE_SECRET_KEY"]

base = Path(__file__).resolve().parents[1]
universe = flatten_watchlist(load_watchlist(base / "config" / "watchlist.json"))
mapping = json.loads((base / "config" / "a_share_map.json").read_text(encoding="utf-8"))
defaults = json.loads((base / "config" / "default_user_watchlist.json").read_text(encoding="utf-8"))
watchlist, errors = enrich_watchlist_inputs(
    ["601138", "300502", "大族激光", "002463"], defaults, universe, mapping
)
assert not errors
assert [row["name"] for row in watchlist] == ["工业富联", "新易盛", "大族激光", "沪电股份"]
assert all(row["theme"] and row["overseas_assets"] and row["keywords"] for row in watchlist)
assert all(row["profile_source"] == "维护规则库" for row in watchlist)

market = {
    "NVDA": {"name": "NVIDIA", "ticker": "NVDA", "change_pct": 3.2},
    "AVGO": {"name": "Broadcom", "ticker": "AVGO", "change_pct": 2.4},
    "SMH": {"name": "Semiconductor ETF", "ticker": "SMH", "change_pct": 2.1},
    "FOXCONN": {"name": "工业富联", "ticker": "601138.SS", "change_pct": 0.8, "last": 52.1},
}
news = [{
    "title": "Hyperscalers raise AI server capex guidance",
    "source": "Reuters",
    "url": "https://example.com/ai",
    "themes": ["AI资本开支"],
    "evidence_score": 80,
    "evidence_label": "B·可靠报道",
}]
alerts, signals = build_personal_analysis(watchlist[:1], news, market, mapping)
subject, html, text = render_morning_email(alerts, signals, "2026-09-07T08:45:00+08:00")
assert "08:45" in subject and "工业富联" in html and "最终是否仍有预期差" in html

auction = {"601138.SS": {"status": "ok", "gap_pct": 0.4, "source": "test"}}
alerts, signals = build_personal_analysis(watchlist[:1], news, market, mapping, auction)
subject, html, text = render_auction_email(alerts, signals, "2026-09-07T09:27:00+08:00")
assert "09:27" in subject and "仍有预期差" in html

quiet_alerts, quiet_signals = build_personal_analysis(
    watchlist[1:2], [], market, mapping,
    {"300502.SZ": {"status": "ok", "gap_pct": 3.2, "source": "test"}},
)
assert quiet_alerts[0]["auction"]["status"] == "竞价独立异动"


sent = {}


class FakeSMTP:
    def __init__(self, host, port, context=None, timeout=None):
        sent.update(host=host, port=port)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def login(self, username, password):
        sent.update(username=username, password=password)

    def send_message(self, message):
        sent["to"] = message["To"]


for key, value in {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "465",
    "SMTP_USERNAME": "sender@example.com",
    "SMTP_PASSWORD": "secret",
    "EMAIL_FROM": "Radar <sender@example.com>",
}.items():
    os.environ[key] = value
original_smtp = emailing.smtplib.SMTP_SSL
emailing.smtplib.SMTP_SSL = FakeSMTP
emailing.send_email("Recipient@Example.com", "test", "<p>ok</p>")
assert sent["to"] == "recipient@example.com"
emailing.smtplib.SMTP_SSL = original_smtp
for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"]:
    del os.environ[key]

print("SUBSCRIPTIONS_REPORTING_TEST_OK")
