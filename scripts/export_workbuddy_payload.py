"""Export the latest site snapshots as a read-only WorkBuddy data feed."""
from __future__ import annotations

from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.workbuddy_export import export_workbuddy_payload


if __name__ == "__main__":
    path = export_workbuddy_payload(BASE)
    print(f"exported {path.relative_to(BASE)}")
