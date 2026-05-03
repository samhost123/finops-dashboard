#!/usr/bin/env bash
#
# RunPod one-shot deployment for finops-dashboard.
#
# Usage on a fresh RunPod pod:
#   git clone https://github.com/samhost123/finops-dashboard.git
#   bash finops-dashboard/deploy_runpod.sh
#
# Idempotent: re-running on the same pod is a fast no-op.

set -euo pipefail

# ---------- config ----------
WORK="/workspace/finops"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_HOST="http://localhost:11434"
TRIAGE_NAME="finops-triage"
RESOLVER_NAME="finops-resolver"

# ---------- helpers ----------
log()  { printf '\033[1;36m[deploy]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 1. preflight ----------
log "preflight checks"
command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found — is this a GPU pod?"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || die "GPU query failed"

mkdir -p "$WORK"
cd "$WORK"
ok "working dir: $WORK"
ok "script dir:  $SCRIPT_DIR"

# ---------- 2. system deps ----------
if [[ ! -f "$WORK/.deps_done" ]]; then
  log "installing system dependencies"
  apt-get update -qq
  apt-get install -y -qq curl git python3-venv python3-pip zstd
  touch "$WORK/.deps_done"
  ok "system deps installed"
else
  ok "system deps already installed"
fi

# ---------- 3. install + start ollama ----------
if ! command -v ollama >/dev/null 2>&1; then
  log "installing ollama"
  curl -fsSL https://ollama.com/install.sh | sh
  ok "ollama installed"
else
  ok "ollama already installed"
fi

if ! curl -sf "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  log "starting ollama daemon"
  nohup ollama serve > "$WORK/ollama.log" 2>&1 &
  for i in {1..30}; do
    if curl -sf "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
      ok "ollama is up (took ${i}s)"
      break
    fi
    sleep 1
    [[ $i -eq 30 ]] && die "ollama failed to start within 30s — check $WORK/ollama.log"
  done
else
  ok "ollama already running"
fi

# ---------- 4. register models (pulls GGUFs from HF on first run) ----------
have_triage=$(ollama list 2>/dev/null | awk -v n="$TRIAGE_NAME" '$1 ~ n {print 1; exit}')
have_resolver=$(ollama list 2>/dev/null | awk -v n="$RESOLVER_NAME" '$1 ~ n {print 1; exit}')

if [[ "${have_triage:-0}" != "1" ]]; then
  log "creating $TRIAGE_NAME (Ollama will pull GGUF from hf.co/sammiset/finops-fail-triage — ~5.6 GB)"
  ollama create "$TRIAGE_NAME" -f "$SCRIPT_DIR/Modelfile.triage" \
    || die "ollama create $TRIAGE_NAME failed"
  ok "$TRIAGE_NAME registered"
else
  ok "$TRIAGE_NAME already registered"
fi

if [[ "${have_resolver:-0}" != "1" ]]; then
  log "creating $RESOLVER_NAME (Ollama will pull GGUF from hf.co/sammiset/finops-resolver — ~5.0 GB)"
  ollama create "$RESOLVER_NAME" -f "$SCRIPT_DIR/Modelfile.resolver" \
    || die "ollama create $RESOLVER_NAME failed"
  ok "$RESOLVER_NAME registered"
else
  ok "$RESOLVER_NAME already registered"
fi

# Remove the bare auto-created `hf.co/sammiset/...` entries.
# Ollama keeps them as a side-effect of pulling, but they have NO Modelfile
# applied (no SYSTEM prompt, no <think> fix). The dashboard's substring
# matcher can pick them and hang on raw thinking-mode output.
for stray in "hf.co/sammiset/finops-fail-triage:latest" "hf.co/sammiset/finops-resolver:latest"; do
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$stray"; then
    log "removing stray pull: $stray"
    ollama rm "$stray" >/dev/null || warn "could not remove $stray"
  fi
done

# ---------- 5. smoke-test both models ----------
# Use the HTTP API directly: avoids SIGPIPE from `ollama run | head` under
# pipefail, gives a clean error payload, and a generous timeout absorbs the
# cold-start load (~30-60s on first call as the GGUF gets paged into VRAM).
smoke_test() {
  local name="$1"
  local payload resp http
  payload=$(printf '{"model":"%s","prompt":"ping","stream":false,"options":{"num_predict":8}}' "$name")
  resp=$(curl -sS --max-time 180 -w '\n%{http_code}' \
    -H 'Content-Type: application/json' \
    "$OLLAMA_HOST/api/generate" -d "$payload") || {
    die "$name: curl failed — is ollama still running? tail $WORK/ollama.log"
  }
  http=$(printf '%s' "$resp" | tail -n1)
  body=$(printf '%s' "$resp" | sed '$d')
  [[ "$http" == "200" ]] || die "$name: HTTP $http — body: $body"
  printf '%s' "$body"
}

log "smoke-testing $TRIAGE_NAME (cold start may take up to 60s)"
triage_body=$(smoke_test "$TRIAGE_NAME")
if printf '%s' "$triage_body" | grep -q '<think>'; then
  warn "$TRIAGE_NAME response contained <think> — Modelfile fix may not be active"
  printf '%s\n' "$triage_body" | head -c 400; echo
else
  ok "$TRIAGE_NAME responded cleanly (no <think> leak)"
fi

log "smoke-testing $RESOLVER_NAME (cold start may take up to 60s)"
smoke_test "$RESOLVER_NAME" >/dev/null
ok "$RESOLVER_NAME responded"

# ---------- 6. python venv + dashboard deps ----------
cd "$SCRIPT_DIR"
if [[ ! -d ".venv" ]]; then
  log "creating python venv"
  python3 -m venv .venv
  ok "venv created"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -f ".venv/.deps_done" ]]; then
  log "installing python dependencies (this may take 1-3 min)"
  pip install --upgrade pip
  pip install --progress-bar on -r requirements.txt
  touch .venv/.deps_done
  ok "python deps installed"
else
  ok "python deps already installed"
fi

# ---------- 7. launch streamlit ----------
log "launching streamlit on 0.0.0.0:8501"
echo
echo "  ────────────────────────────────────────────────────────────"
echo "  Dashboard URL (RunPod proxy):"
echo "    https://<POD_ID>-8501.proxy.runpod.net"
echo
echo "  Replace <POD_ID> with your RunPod pod ID. Find it under"
echo "  'Connect' → 'HTTP Service [Port 8501]' in the RunPod UI."
echo "  ────────────────────────────────────────────────────────────"
echo

exec streamlit run dashboard.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  --server.enableWebsocketCompression=false
