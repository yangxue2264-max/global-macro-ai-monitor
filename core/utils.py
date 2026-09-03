from __future__ import annotations

import math


def finite(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def fmt_num(value, digits=2):
    number = finite(value)
    return "—" if number is None else f"{number:,.{digits}f}"


def fmt_pct(value, digits=2):
    number = finite(value)
    return "—" if number is None else f"{number:+.{digits}f}%"


def signal_emoji(value):
    number = finite(value)
    if number is None:
        return "○"
    if number >= 0.75:
        return "▲"
    if number <= -0.75:
        return "▼"
    return "●"
