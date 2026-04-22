# FinOps Dashboard — Project Status

**Last updated:** 2026-04-21
**Repo:** `samhost123/finops-dashboard` (private, GitHub)
**Branch:** `main` — all work committed and pushed
**Main file:** `dashboard.py` (1,205 lines, single-file Streamlit app)

---

## Phase Completion

| Phase | Status | Commit |
|-------|--------|--------|
| 0 — Scaffold & Data Layer | Done | `a8b372e` |
| 1 — Ollama Connectivity | Done | `d5ba8ab` |
| 2 — Stage 1 Triage Pipeline | Done | `dab6534` |
| 3 — Stage 2 Resolver Pipeline | Done | `5b15f9b`, `e6acbef` |
| 4 — Batch Processing & KPI Metrics | **Not started** | — |
| 5 — Polish & Deployment | **Not started** | — |

---

## What's Built (Phases 0-3)

### Data Generation
- Generates 1-50 synthetic settlement fails with realistic data
- Five fail categories: CNS Fail, DVP Fail, B2B Pending, Corporate Action, Trade Dispute (DK)
- Two firm name pools: PRIME_BROKERS (10, stock loan contexts) and EXECUTION_BROKERS (41, all other)
- DTC-to-firm-name mapping stored in session_state for consistent display
- Related fails generated with gridlock-aware logic
- Real-format CUSIPs, synthetic accounts (ACC-XXXXXX), market values across tiers

### Table Display
- Age-based row coloring (red 10+d, amber 7-9d, green 4-6d, deep green 1-3d)
- Input-only columns: Security, Counterparty, Account, Fail Type, Shares, Market Value, Age, Reg SHO, Inventory
- No model-output fields shown before analysis (no fake tiers/scores)
- Summary metrics show "—" until batch analysis runs

### Stage 1: Triage Pipeline
- Formats pipe-delimited prompt per category (CNS adds CNS Position/Direction, DVP adds Settlement Type, etc.)
- Calls `finops-triage` via Ollama `/api/chat`
- Displays: priority score (large colored number), tier (colored badge), escalation level (plain English), assessment, deadline, flags (translated to human-readable)
- Case-insensitive display lookups (model returns lowercase)
- Connection gate — warns if Ollama not connected before calling
- Debug expanders: selected fail verification, triage prompt, raw response

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
- Debug expanders: resolver prompt, raw response (with think block), parsed JSON
- Null-safe: handles model returning None for numeric fields

### Infrastructure
- `.streamlit/config.toml` — dark theme, port 8501, address 0.0.0.0
- `.venv/` — Python virtual environment with streamlit, pandas, requests
- `.gitignore` — excludes `__pycache__/`

---

## What's Next

### Phase 4 — Batch Processing & KPI Metrics
Per `plan.md`:
- "Analyze All Fails" button — runs every generated fail through Stage 1 + Stage 2 sequentially
- Progress bar showing X/N complete with estimated time remaining
- Allow cancellation
- Summary metrics row updates after batch:
  - Total Fails (already works)
  - Critical Priority (count)
  - Escalation Required (count)
  - Avg Coverage (percentage)
  - Gridlock Detected (count)
- Store results in `st.session_state`

### Phase 5 — Polish & Deployment
Per `plan.md`:
- Mobile responsiveness (single-column layout on small screens)
- Error handling sweep (no stack traces ever)
- Session state persistence across reruns
- Export/Download Report:
  - CSV: one row per fail with all pipeline outputs
  - PDF: formatted report with KPI strip + per-fail sections (via reportlab or weasyprint)
  - `st.download_button` for both
  - Filename: `finops-report-YYYY-MM-DD.pdf` / `.csv`
- RunPod deployment readiness

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
├── dashboard.py          # Single-file Streamlit app (1,205 lines)
├── dashboard_status.md   # This file
├── plan.md               # Reference implementation plan
├── requirements.txt      # streamlit, pandas, requests
├── .streamlit/
│   └── config.toml       # Dark theme, port 8501
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

### How to Resume with AI
Tell the assistant:
1. Read `dashboard/plan.md` for the full implementation plan
2. Read `dashboard/dashboard_status.md` (this file) for current state
3. "Begin Phase 4" (or whichever phase is next)
4. Confirm each phase works before proceeding to the next

---

## Commit History
```
e6acbef Preserve resolver thinking trace instead of stripping it
5b15f9b Add Phase 3: Stage 2 resolver pipeline with full two-stage flow
dab6534 Add Phase 2: Stage 1 triage pipeline with plain English display
6d9f95b Update firm pools: prime brokers vs execution brokers
d5ba8ab Add Phase 1: Ollama connectivity health check
a8b372e Add Phase 0: fail generator, dark-themed dashboard, config
23b2c45 Add staged implementation plan for executive dashboard
```
