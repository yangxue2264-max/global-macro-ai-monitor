from pathlib import Path
import ast, json

BASE = Path(__file__).resolve().parents[1]
required = [
    "app.py", "requirements.txt", "README.md", "DEPLOY.md",
    "config/watchlist.json", "config/a_share_map.json",
    "core/providers.py", "core/briefing.py", "core/ontology.py", "core/ai.py",
    ".github/workflows/morning_brief.yml",
]
missing=[x for x in required if not (BASE/x).exists()]
syntax=[]
for p in BASE.rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e:
        syntax.append((str(p.relative_to(BASE)),str(e)))
print("missing:", missing or "none")
print("syntax:", syntax or "none")
print("ready:", not missing and not syntax)
