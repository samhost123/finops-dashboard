# FinOps Dashboard — Project Status

**Last updated:** 2026-04-22
**Repo:** `samhost123/finops-dashboard` (private, GitHub)
**Branch:** `main` — all work committed and pushed
**Main file:** `dashboard.py` (~2,200 lines, single-file Streamlit app)

---

## Phase Completion

| Phase | Status | Commit |
|-------|--------|--------|
| 0 — Scaffold & Data Layer | Done | `a8b372e` |
| 1 — Ollama Connectivity | Done | `d5ba8ab` |
| 2 — Stage 1 Triage Pipeline | Done | `dab6534` |
| 3 — Stage 2 Resolver Pipeline | Done | `5b15f9b`, `e6acbef` |
| UI — Trader-Desk Redesign | Done | `b77f209`, `00e3f79`, `d71b5f1` |
| 4 — Batch Processing & KPI Metrics | Done | `defd810` |
| 5 — Polish & Deployment | Done | *(this commit)* |

---

## What's Built (Phases 0-5)

### Data Generation
- Generates 1-50 synthetic settlement fails with realistic data
- Five fail categories: CNS Fail, DVP Fail, B2B Pending, Corporate Action, Trade Dispute (DK)
- Two firm name pools: PRIME_BROKERS (10, stock loan contexts) and EXECUTION_BROKERS (41, all other)
- DTC-to-firm-name mapping stored in session_state for consistent display
- Related fails generated with gridlock-aware logic
- Real-format CUSIPs, synthetic accounts (ACC-XXXXXX), market values across tiers

### UI — Trader-Desk Redesign (2026-04-22)
- Ported HTML/React design (`fails monitorimg/`) to Streamlit presentation layer
- Dark trader-desk theme: `#0a0b0d` background, `#4ED6C9` cyan accent, JetBrains Mono font
- Custom CSS overrides for Streamlit internals (hidden header/footer, reduced padding)
- **Top bar** with branding, model status indicators, Ollama connection, UTC clock
- **KPI strip** — 7 metrics: Open Fails, Critical, Needs Escalation, Avg Coverage, Gridlock, Reg SHO, Notional Exposure
- **Inline controls** — generate (count + button), filter radio (ALL/CRITICAL/HIGH/MEDIUM/LOW/REG SHO/GRIDLOCK), stage toggle (Both/Stage 1/Stage 2), Analyze All/Cancel, Test Ollama — no sidebar needed
- **Selectable queue table** — `st.dataframe` with `on_select="rerun"` and `selection_mode="single-row"` for click-to-select rows; coverage column as progress bar; STATUS column showing analysis state per fail
- **Two-pane layout** — `st.columns([1.1, 1])`: queue table (left) + detail panel (right)
- **Detail panel** — fail header with tier/REG SHO/gridlock chips, 6-cell metric strip (priority, tier, age, coverage, reg sho, flags)
- **Stage cards** — Stage 1 (Triage) and Stage 2 (Resolution) side by side via nested `st.columns(2)`
- **AI reasoning trace** — collapsible expander showing resolver thinking steps
- **Status bar** — environment, data source, pipeline info, analyzed count
- CUSIP-to-ticker/name mapping (`CUSIP_INFO`) for human-readable security display
- All CSS classes prefixed `fo-` to avoid Streamlit conflicts

### Data Generation Updates (2026-04-22)
- CNS fails show "vs CNS" — no counterparty firm assigned
- CNS category splits into `CNS_FTD` (Fail to Deliver) and `CNS_FTR` (Fail to Receive)
- FTR fails: side forced to "Buy", quantities swapped
- Null-safe triage field rendering — `or "—"` fallback instead of `.get()` default (handles explicit None values)

### Stage 1: Triage Pipeline
- Formats pipe-delimited prompt per category (CNS adds CNS Position/Direction, DVP adds Settlement Type, etc.)
- Calls `finops-triage` via Ollama `/api/chat`
- Displays: priority score (large colored number), tier (colored badge), escalation level (plain English), assessment, deadline, flags (translated to human-readable)
- Case-insensitive display lookups (model returns lowercase)
- Connection gate — warns if Ollama not connected before calling

### Stage 2: Resolver Pipeline
- "Run Stage 2: Resolution" button appears only after Stage 1 completes
- Composes resolver JSON input from triage output + fail data (cusip, ftd_qty, inventory, ftrs, related_fails)
- Calls `finops-resolver` via Ollama `/api/chat` (180s timeout)
- Separates `<think>...</think>` reasoning from JSON output (does NOT strip — preserves thinking)
- **"View AI Reasoning"** expander (collapsed by default) shows the model's thinking trace
- **Pipeline flow** — two-column layout: Stage 1 summary | Stage 2 summary
- **Resolution steps** — numbered plain English list with DTC-to-firm-name translation, per-step progress bars
- **Coverage summary** — large colored percentage + residual short + overall progress bar
- **Gridlock banner** — red with firm names if detected, green if not
- **Escalation banner** — amber with reason if required, green if not
- **Fallback strategy** — plain English paragraph
- **Narrative** — model's resolution summary
- Null-safe: handles model returning None for numeric fields

### Phase 4: Batch Processing & KPI Metrics
- **"Analyze All"** button runs every generated fail through Stage 1 + Stage 2 sequentially
- **Progress indicator** — `st.progress` bar with current fail info, estimated time remaining
- **Cancel** — `on_click` callback sets `cancel_batch` flag, checked between each fail
- **Batch results** stored in `st.session_state["batch_results"]` — individual runs also write here
- **KPI strip** updates from real AI results after analysis (Critical, Escalation, Avg Coverage, Gridlock, Reg SHO); shows "—" before analysis
- **Queue STATUS column** — per-row status: "✓ Analyzed", "○ Pending", "✗ Triage Err", "⚠ Resolve Err", "½ Triage"
- **Per-fail error handling** — triage errors skip resolver, resolver errors keep triage, never stops entire batch
- **Unified result access** — detail panel checks individual results first, then batch results

### Phase 5: Polish & Deployment Readiness
- **Error handling sweep** — all model calls, JSON parsing, and network requests wrapped in try/except with plain English messages; AI model response validated as dict; no Python tracebacks reach the UI
- **Session state persistence** — all critical state persists across Streamlit reruns; no data loss on interaction
- **CSV export** — one row per fail with: Security, Counterparty, Fail Type, Shares, Market Value, Age, Priority Score, Priority Tier, Escalation Required, Coverage %, Gridlock Detected, Resolution Summary, Reg SHO Flag; filename `finops-report-YYYY-MM-DD.csv`
- **PDF export** — via reportlab: cover page with title/date/KPI summary, one section per fail with triage results, resolution steps in plain English, coverage, escalation status; no JSON or technical jargon; filename `finops-report-YYYY-MM-DD.pdf`
- **Export buttons** — `st.download_button` for CSV and PDF; only visible after analysis has run
- **Debug expanders removed** — all 4 debug expanders (triage prompt, raw triage response, resolver prompt, raw resolver response) removed; "View AI Reasoning" expander preserved as a feature
- **RunPod deployment ready** — `.streamlit/config.toml` has `server.address = 0.0.0.0`, port 8501; `reportlab` added to requirements.txt

### Infrastructure
- `.streamlit/config.toml` — dark theme, port 8501, address 0.0.0.0
- `.venv/` — Python virtual environment with streamlit, pandas, requests, reportlab
- `.gitignore` — excludes `__pycache__/`

---

## Key Technical Details

### Models
- `finops-triage` — Qwen3.5-9B, ~5.7GB GGUF, scores/classifies fails
- `finops-resolver` — Qwen3-8B, ~5.0GB GGUF, recommends resolution steps, enabled thinking tokens
- Both run via Ollama at `http://localhost:11434`
- Resolver outputs `<think>` blocks before JSON — dashboard preserves and displays them

### Model Output Quirks
- Both models return lowercase field values (e.g., "high" not "HIGH") — dashboard uppercases before display lookup
- Resolver sometimes returns null/0 for `total_coverable` and per-step coverage fields — dashboard handles with `or 0` guards
- First call after model load can be slow (cold start) — 120s timeout for triage, 180s for resolver

### Action Code Translations (11 enums)
All translated to plain English in the UI:
`CHASE_FTR`, `APPLY_BOX`, `INITIATE_RECALL`, `SOURCE_BORROW`, `PARTIAL_DELIVER`, `DEPOT_MOVEMENT`, `NET_GRIDLOCK`, `BUY_IN_NOTICE`, `SPO_SETTLEMENT`, `OFFSET_FTR`, `ESCALATE`

### File Structure
```
dashboard/
├── dashboard.py          # Single-file Streamlit app (~2,200 lines)
├── dashboard_status.md   # This file
├── plan.md               # Reference implementation plan
├── requirements.txt      # streamlit, pandas, requests, reportlab
├── .streamlit/
│   └── config.toml       # Dark theme (cyan accent), port 8501
├── fails monitorimg/     # Reference HTML/React design
│   ├── FinOps Resolver.html
│   └── src/
│       ├── app.jsx
│       ├── data.js
│       ├── detail.jsx
│       ├── queue.jsx
│       └── styles.css
├── .gitignore
└── .venv/                # Python virtual environment
```

### How to Run
```bash
cd ~/Documents/Fine-tuning/dashboard
source .venv/bin/activate.fish  # or activate for bash
streamlit run dashboard.py
# Open http://localhost:8501
```

### RunPod Deployment
```bash
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
```

### How to Resume with AI
Tell the assistant:
1. Read `dashboard/plan.md` for the full implementation plan
2. Read `dashboard/dashboard_status.md` (this file) for current state
3. All phases are complete — project is deployment-ready
