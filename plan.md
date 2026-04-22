# FinOps Resolver Dashboard — Staged Implementation Plan

## Risks & Unknowns (Flag Upfront)

1. **Model availability** — The dashboard assumes `finops-triage` and `finops-resolver` are loaded in Ollama at the endpoint. If either model isn't registered, Stage 1/2 calls will fail. Need a health check + clear error messaging.

2. **Thinking traces in resolver output** — Resolver training data includes `<think>...</think>` blocks before JSON. The dashboard must strip thinking traces and parse only the JSON portion. If the model sometimes omits the trace or emits malformed JSON, we need graceful handling.

3. **Latency** — Complex scenarios (11-28 FTRs) produce long input prompts. On a 4B model over Ollama, response time could be 10-30s. On RunPod via network, add latency. The UI must show progress and not feel broken during inference.

4. **No firm name mapping exists** — Current training data uses opaque DTC numbers (e.g., `DTC-0352`), not human-readable firm names. The dashboard needs a synthetic mapping (DTC number -> realistic broker/dealer name) purely for display purposes.

5. **Triage model prompt format** — Triage expects pipe-delimited plain text input (e.g., `CUSIP: 594918104 | Side: Sell | Qty: 5000 | ...`), while resolver expects JSON. The dashboard must format inputs correctly for each stage.

6. **Resolver expects triage JSON as input** — The resolver's user prompt wraps triage output + inventory + FTRs in a JSON structure. The dashboard must compose this from the generated fail + triage response.

---

## Phase 0 — Scaffold & Data Layer (no AI calls)
**Delivers:** Runnable Streamlit app with fail generation and raw data table. Zero model dependency.

### Tasks:
1. **Create `dashboard.py`** — single-file Streamlit app with page layout:
   - Title bar + summary metrics row (placeholders with zeros)
   - Sidebar: Ollama endpoint URL input (default `http://localhost:11434`), fail count slider (1-50)
   - "Generate Fails" button

2. **Port fail generation logic from `gen_resolver.py`** into a self-contained module within the dashboard (or inline). Adapt it to produce dashboard-friendly data:
   - Generate triage input fields: CUSIP, side, qty, age, market value, reg SHO status, inventory coverage %, CP fail rate, CNS direction, lifecycle state
   - Generate inventory snapshot: box_qty, recall_outstanding, stock_loan_available, pending_receives
   - Generate FTR list (1-28 per fail, complexity distribution matching gen_resolver.py)
   - Add **synthetic firm name pool** — ~30 realistic broker/dealer names (e.g., "Meridian Capital Partners", "Clearview Securities", "Northpoint Financial") mapped to DTC numbers at generation time
   - Add **realistic account number generator** — format like `ACC-XXXXXX`
   - Use real-format CUSIPs (9 chars, digit-heavy, checksum not required for synthetic data)

3. **Raw data table view** — `st.dataframe` with human-readable column headers:
   - "Security" (CUSIP), "Counterparty" (firm name), "Shares", "Age (Days)", "Priority Tier", "Fail Type" (category), "Market Value"
   - Color-code rows: red for CRITICAL, amber for HIGH, green for LOW/MEDIUM
   - No JSON, no field names — clean table with `st.dataframe` or `st.data_editor` styling

**Dependencies:** None — pure Python + Streamlit.

**Exit criteria:** App launches on port 8501, generates 1-50 randomized fails, displays clean table, no model calls.

---

## Phase 1 — Ollama Connectivity & Health Check
**Delivers:** Sidebar connectivity status. Confirms both models are reachable before attempting inference.

### Tasks:
1. **Ollama client utility** — function that calls `GET {endpoint}/api/tags` to list available models. Verify both `finops-triage` and `finops-resolver` appear in the response.

2. **Sidebar status indicators:**
   - Green checkmark + "Connected" when endpoint responds and both models found
   - Yellow warning if endpoint responds but one/both models missing (list which)
   - Red X + "Unreachable" if endpoint times out (5s timeout)
   - "Test Connection" button to re-check

3. **Graceful timeout handling** — wrap all `requests` calls in try/except with user-friendly messages: "Could not reach the AI models. Check that Ollama is running at {url}." Never show stack traces.

**Dependencies:** Phase 0 (app must exist to add sidebar).

**Exit criteria:** Sidebar shows connection status. Works against local Ollama and a configurable remote URL.

---

## Phase 2 — Stage 1 Pipeline (Triage)
**Delivers:** For any selected fail, run it through finops-triage and display scored/classified results.

### Tasks:
1. **Format triage prompt** — Convert generated fail data into the pipe-delimited format the triage model expects:
   ```
   Triage this fail record:
   CUSIP: 594918104 | Side: Sell | Qty: 5000 | Counterparty: DTC-0742 | Age: 7 days | Market Value: $2.1M | ...
   ```

2. **Call Ollama generate API** — `POST {endpoint}/api/chat` with the triage system prompt and user message. Parse JSON response from model output.

3. **Display triage results in plain English:**
   - Priority score as a large number with color (red >75, amber 50-75, green <50)
   - Priority tier as a colored badge
   - "Reason" field displayed as a paragraph
   - Flags displayed as plain English tags ("Regulatory watchlist security", "High value position", "Problem counterparty")
   - Escalation level translated: L1 -> "Operations Analyst Review", L2 -> "Senior Ops Review", L3 -> "Management Escalation", L4 -> "Compliance Escalation"

4. **Row selection** — user clicks a row in the raw data table. Selected row expands to show Stage 1 output. Or: multi-select with batch processing.

5. **Loading state** — `st.spinner("Analyzing fail with Stage 1 triage model...")` during inference.

**Dependencies:** Phase 0 (fail data), Phase 1 (connectivity check — warn if not connected before calling).

**Exit criteria:** Select a fail, see triage output in plain English. No JSON visible. Timeout produces friendly message.

---

## Phase 3 — Stage 2 Pipeline (Resolver)
**Delivers:** Full two-stage pipeline. Triage output feeds into resolver. Resolution plan displayed in executive-readable format.

### Tasks:
1. **Compose resolver input** — Build the JSON structure the resolver expects:
   - `triage`: actual Stage 1 output (parsed JSON)
   - `cusip`, `ftd_qty`: from generated fail
   - `inventory`: from generated fail
   - `ftrs`: from generated fail
   - `related_fails`: from generated fail (if any)

2. **Call resolver model** — `POST {endpoint}/api/chat` with resolver system prompt. **Strip `<think>...</think>` blocks** from response before parsing JSON.

3. **Display resolver output in plain English:**
   - **Resolution Steps** — numbered list: "Step 1: Contact Meridian Capital Partners to deliver 12,000 shares (oldest pending receipt, 3 days overdue)" — translate action codes to human language
   - **Coverage progress bar** — `st.progress_bar` showing total_coverable / ftd_qty
   - **Coverage percentage** as large text next to the bar
   - **Gridlock flag** — if detected: red banner "Delivery gridlock detected involving {N} firms. Coordinated outreach recommended to break circular dependency." If not: green "No gridlock detected"
   - **Escalation required** — yes/no with reason in plain English. "Yes — 4,000 shares cannot be sourced through available channels. Manual intervention needed." or "No — all shares can be covered through the recommended steps."
   - **Narrative** — the model's narrative field displayed as a summary paragraph
   - **Fallback strategy** — translated: "If the primary steps are insufficient, the next option is to recall 5,000 shares from lending, followed by sourcing 3,000 shares via external stock loan."

4. **Pipeline flow visualization** — simple visual showing Stage 1 -> Stage 2:
   - Two columns or a horizontal flow with `st.columns`
   - Left: "Stage 1: Triage" card (priority, tier, flags)
   - Arrow or divider
   - Right: "Stage 2: Resolution" card (steps, coverage, escalation)
   - Shows the data flowing from triage -> resolver

5. **Action code translations** — mapping for all 11 action enums to plain English:
   - `CHASE_FTR` -> "Contact counterparty to deliver pending shares"
   - `APPLY_BOX` -> "Use available inventory"
   - `INITIATE_RECALL` -> "Recall shares from lending program"
   - `SOURCE_BORROW` -> "Borrow shares externally"
   - `PARTIAL_DELIVER` -> "Deliver available shares immediately"
   - `DEPOT_MOVEMENT` -> "Transfer shares to depository for settlement"
   - `NET_GRIDLOCK` -> "Propose coordinated settlement across firms"
   - `BUY_IN_NOTICE` -> "Issue formal buy-in notice to counterparty"
   - `SPO_SETTLEMENT` -> "Cash settle via Special Payment Order"
   - `OFFSET_FTR` -> "Apply pending receipt directly against obligation"
   - `ESCALATE` -> "Escalate to management for manual resolution"

**Dependencies:** Phase 2 (triage output required as resolver input).

**Exit criteria:** Full pipeline runs end-to-end. Executive sees numbered plain-English resolution plan, progress bar, gridlock status, escalation status. No JSON anywhere.

---

## Phase 4 — Summary Metrics & Batch Processing
**Delivers:** Top-of-page KPI strip. Ability to run all generated fails through the pipeline.

### Tasks:
1. **Batch processing** — "Analyze All Fails" button that runs every generated fail through Stage 1 + Stage 2 sequentially. Progress bar showing X/N complete.

2. **Summary metrics row** (top of page, `st.metric` widgets):
   - Total Fails Generated
   - Critical Priority (count, delta indicator)
   - Escalation Required (count)
   - Average Coverage (percentage)
   - Gridlock Detected (count)

3. **Metrics update** — recalculate after each batch run or individual analysis. Store results in `st.session_state`.

4. **Performance consideration** — batch of 50 fails x 2 model calls each = 100 inference calls. At ~10s each = ~16 minutes worst case. Show estimated time remaining. Allow cancellation.

**Dependencies:** Phase 3 (full pipeline must work for individual fails first).

**Exit criteria:** Executives see a KPI row at top. Batch processing works with progress indication. Numbers are accurate.

---

## Phase 5 — Polish & Deployment Readiness
**Delivers:** Mobile-responsive, deploy-ready app.

### Tasks:
1. **Mobile responsiveness** — test `st.columns` layout at narrow widths. Use single-column layout for pipeline view on small screens. Ensure tables scroll horizontally. Large fonts for key metrics.

2. **Streamlit config** — `.streamlit/config.toml` with:
   - `server.port = 8501`
   - `server.address = 0.0.0.0` (for RunPod)
   - Theme settings for professional appearance

3. **Error handling sweep:**
   - Model returns malformed JSON -> "The AI model returned an unexpected response. Please try again."
   - Network timeout -> "Connection to the AI models timed out. Check the Ollama endpoint in the sidebar."
   - Model not found -> "The {model_name} model is not installed. Run `ollama pull {model_name}` on the server."
   - Never show Python tracebacks

4. **RunPod deployment notes** — document the startup command:
   ```bash
   streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
   ```

5. **Session state management** — ensure generated fails, triage results, and resolver results persist across Streamlit reruns. No data loss on interaction.

6. **Final UI pass** — consistent color scheme, no orphaned debug text, all placeholder text removed.

7. **Export / Download Report** — after batch or individual analysis, provide a "Download Report" button that exports results as a clean PDF or CSV:
   - CSV export: one row per fail with all pipeline outputs (priority score, tier, resolution steps summarized, coverage %, escalation required, gridlock detected)
   - PDF export: formatted summary report with KPI strip at top, then one section per fail showing the full pipeline output in plain English. No JSON, no technical field names — same standard as the UI.
   - Use `st.download_button` for both formats
   - PDF generation via `reportlab` or `weasyprint` — choose whichever has fewer dependencies
   - Filename format: `finops-report-YYYY-MM-DD.pdf` / `.csv`

**Dependencies:** Phases 0-4 complete.

**Exit criteria:** App runs locally and is deployable to RunPod. Readable on phone. No raw JSON, no stack traces, no technical jargon in the UI. Download Report button produces a clean PDF and CSV with no raw JSON or technical field names.

---

## Summary

| Phase | What it delivers | Model calls? | Estimated effort |
|-------|-----------------|-------------|-----------------|
| 0 | Working app + fail generator + raw data table | No | Foundation |
| 1 | Ollama connectivity + health check | Metadata only | Light |
| 2 | Stage 1 triage pipeline + display | Yes (triage) | Medium |
| 3 | Stage 2 resolver pipeline + full flow | Yes (both) | Heaviest |
| 4 | Batch processing + KPI metrics | Yes (batch) | Medium |
| 5 | Mobile polish + deploy readiness + PDF/CSV export | No | Medium |

Each phase produces a working, demonstrable increment. Phase 0 works with zero model infrastructure. Phases 1-3 build the pipeline incrementally. Phase 4 adds the executive-summary layer. Phase 5 hardens for demo day.
