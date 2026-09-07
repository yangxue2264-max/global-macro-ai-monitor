from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
import os
import re
from zoneinfo import ZoneInfo

import requests


CN = ZoneInfo("Asia/Shanghai")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def get_secret(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


def normalize_email(value: str) -> str:
    _, address = parseaddr(str(value or "").strip())
    return address.lower() if EMAIL_RE.fullmatch(address or "") else ""


def subscriptions_configured() -> bool:
    return bool(
        get_secret("SUPABASE_URL")
        and (get_secret("SUPABASE_SECRET_KEY") or get_secret("SUPABASE_SERVICE_ROLE_KEY"))
    )


def _request(method: str, path: str, **kwargs):
    base = get_secret("SUPABASE_URL").rstrip("/")
    key = get_secret("SUPABASE_SECRET_KEY") or get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        raise RuntimeError("订阅存储尚未配置。")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        **kwargs.pop("headers", {}),
    }
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    response = requests.request(method, f"{base}/rest/v1/{path.lstrip('/')}", headers=headers, timeout=20, **kwargs)
    response.raise_for_status()
    if not response.content:
        return None
    return response.json()


def list_active_subscriptions() -> list[dict]:
    if not subscriptions_configured():
        return []
    rows = _request(
        "GET",
        "subscriptions",
        params={"active": "eq.true", "select": "email,watchlist,updated_at"},
    )
    return [row for row in (rows or []) if normalize_email(row.get("email", "")) and row.get("watchlist")]


def upsert_subscription(email: str, watchlist: list[dict]) -> dict:
    address = normalize_email(email)
    if not address:
        raise ValueError("邮箱格式无效。")
    now = datetime.now(CN).isoformat()
    rows = _request(
        "POST",
        "subscriptions",
        params={"on_conflict": "email"},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json={
            "email": address,
            "watchlist": watchlist,
            "active": True,
            "verified_at": now,
            "updated_at": now,
        },
    )
    return (rows or [{}])[0]


def deactivate_subscription(email: str) -> None:
    address = normalize_email(email)
    if not address:
        raise ValueError("邮箱格式无效。")
    _request(
        "PATCH",
        "subscriptions",
        params={"email": f"eq.{address}"},
        headers={"Prefer": "return=minimal"},
        json={"active": False, "updated_at": datetime.now(CN).isoformat()},
    )


SCHEMA_SQL = """create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  watchlist jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  verified_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.subscriptions enable row level security;
-- Do not create anon policies. The Streamlit server and GitHub Actions use the service role key.
"""
