import numpy as np

def fmt_pct(x):
    try:
        if np.isnan(float(x)): return "—"
        return f"{float(x):+.2f}%"
    except Exception: return "—"

def fmt_num(x,digits=2):
    try:
        if np.isnan(float(x)): return "—"
        return f"{float(x):,.{digits}f}"
    except Exception: return "—"

def signal_emoji(x,threshold=.8):
    try:
        v=float(x)
        if np.isnan(v): return "⚪"
        if v>=threshold: return "🟢"
        if v<=-threshold: return "🔴"
        return "🟡"
    except Exception: return "⚪"
