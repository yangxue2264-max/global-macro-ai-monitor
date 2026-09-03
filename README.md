# Global-to-A Share Decision Monitor

An A-share pre-open research operating system. It does not try to replace a market-data terminal. Its job is to convert overseas events and cross-asset prices into a short, falsifiable daily research queue.

## The product edge

Generic dashboards are already excellent at showing prices, charts, watchlists and news. This project focuses on the layer they do not know about by default: the user's China-specific research process.

1. **Decision queue** — ranks the three questions that deserve attention today.
2. **Cross-market pricing gaps** — compares global theme proxies with mapped A-share proxies and labels confirmation, lag or divergence.
3. **Falsifiable thesis book** — every medium-term narrative has a horizon, observable rules and an explicit invalidation condition.
4. **Research memory** — a weekday snapshot makes yesterday's judgment inspectable instead of generating a context-free new summary each morning.
5. **Human-auditable AI** — the rules dashboard works without AI. AI is called only on demand to structure an event or compress a brief.

The priority score is transparent:

`evidence quality (30) + overseas move (25) + pricing gap (25) + A-share relevance (20)`

It ranks research work. It is not an expected-return forecast or trading signal.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Offline/demo validation:

```bash
MACRO_MONITOR_OFFLINE_TEST=1 streamlit run app.py
PYTHONPATH=. python tests/test_decision_engine.py
PYTHONPATH=. python tests/smoke_test.py
```

## Streamlit Cloud deployment

1. Upload the **contents** of this folder to the root of the existing GitHub repository.
2. Keep `app.py` as the Streamlit entrypoint.
3. In Streamlit Cloud secrets, add only if AI analysis is required:

```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-5.6-luna"
```

The non-AI decision engine remains fully usable without these secrets.

## Daily research memory

`.github/workflows/daily_snapshot.yml` runs at 08:45 China time on weekdays. In the repository settings, GitHub Actions must have read/write workflow permission. The job saves `data/brief_history/YYYY-MM-DD.json` and commits it back to the repository. Streamlit then compares the current state with the previous trading-day snapshot.

## Data policy

- FRED for official US macro series.
- US Treasury curves as an explicitly labelled fallback for yields.
- Yahoo Finance as a market proxy with dates displayed.
- GDELT with Google News RSS fallback for event discovery.
- NOAA CPC for the on-demand ENSO module.
- OpenAI only when a user explicitly requests an AI brief or event analysis.

Free sources can be delayed or unavailable. The interface marks demo, proxy, derived and missing values instead of silently presenting them as live facts.

## 90-second mentor demo

1. Open **决策台**: explain that the first output is three research questions, not a wall of prices.
2. Open **定价缺口**: select one theme and show the global proxy, A-share proxy, next verifier and invalidation condition.
3. Open **主题账本**: show how a narrative can move from confirmed to mixed or challenged.
4. Open **事件实验室**: turn one new headline into a causal chain and counter-evidence checklist.

The intended daily loop is: **fact → state variable → transmission → price confirmation → A-share mapping → invalidation → next-day review**.
