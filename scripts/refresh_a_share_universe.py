"""Refresh and validate the free official A-share master list."""
from __future__ import annotations

from pathlib import Path
import json
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.providers import A_SHARE_CACHE, fetch_a_share_universe


def main():
    rows, coverage = fetch_a_share_universe(refresh=True)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    print(f"cache={A_SHARE_CACHE} rows={len(rows)}")
    if not coverage.get("usable"):
        raise SystemExit("A-share master list did not pass the coverage gate")


if __name__ == "__main__":
    main()
