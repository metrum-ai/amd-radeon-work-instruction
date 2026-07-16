#!/usr/bin/env bash

# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

# =============================================================================
# Manufacturing Work Instruction Generator (WIG) — Setup & Launch
# Checks prerequisites, configures environment, builds images, and starts
# the full stack (Postgres, NATS, Milvus/RustFS RAG store, machine simulator,
# GPU model servers, OpenClaw agents, and the frontend).
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[FAIL]${NC}  $*"; }
die()   { error "$*"; exit 1; }
hr()    { echo -e "${BOLD}────────────────────────────────────────────────────${NC}"; }

retry_command() {
    local label="$1" attempts="${2:-3}" delay_s="${3:-15}"
    shift 3
    local attempt=1
    while true; do
        if "$@"; then return 0; fi
        [ "$attempt" -ge "$attempts" ] && return 1
        warn "${label} failed (attempt ${attempt}/${attempts}); retrying in ${delay_s}s..."
        sleep "$delay_s"
        attempt=$((attempt + 1))
    done
}

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

DISK_MIN_GB=60
RAM_MIN_GB=48
MIN_REQUIRED_GPUS=4
SETUP_DOCKER_RETRY_ATTEMPTS="${SETUP_DOCKER_RETRY_ATTEMPTS:-3}"
SETUP_DOCKER_RETRY_DELAY_S="${SETUP_DOCKER_RETRY_DELAY_S:-20}"

add_or_replace() {
    local key="$1" value="$2"
    if [ -f .env ] && awk -F= -v k="$key" '$1 == k { found=1 } END { exit found ? 0 : 1 }' .env; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        [ -s .env ] && printf '\n' >> .env
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

# gen_token — emit a strong random secret (hex via openssl, base64 fallback).
gen_token() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32
    fi
}

# gen_short_token — short 4-5 char alphanumeric key (local, unauthenticated
# model servers just need a placeholder value, not a real secret).
gen_short_token() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 4 | head -c 5
    else
        head -c 8 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 5
    fi
}

echo ""
hr
echo -e "  ${BOLD}Manufacturing Work Instruction Generator — Setup & Launch${NC}"
hr
echo ""

# =============================================================================
# STEP 1: PREREQUISITES
# =============================================================================
echo -e "${BOLD}[1/3] Checking prerequisites...${NC}"
echo ""
PREREQ_FAIL=0

# --- Docker ---
if ! command -v docker &>/dev/null; then
    error "docker not found — install: https://docs.docker.com/get-docker/"
    PREREQ_FAIL=1
elif ! docker info &>/dev/null 2>&1; then
    error "Docker daemon not running — start: sudo systemctl start docker"
    PREREQ_FAIL=1
else
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

# --- Docker Compose v2 ---
if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose $(docker compose version --short 2>/dev/null || echo 'v2')"
else
    error "Docker Compose v2 not found — install: https://docs.docker.com/compose/install/"
    PREREQ_FAIL=1
fi

# --- Git LFS (oem_ingest/documents/**/*.pdf are stored via LFS) ---
if ! command -v git-lfs &>/dev/null; then
    warn "git-lfs not found — installing..."
    sudo apt-get update -qq && sudo apt-get install -y git-lfs
    if command -v git-lfs &>/dev/null; then
        git lfs install
        ok "git-lfs $(git lfs version 2>/dev/null | awk '{print $1}') installed"
    else
        error "git-lfs install failed — install manually: https://git-lfs.com then re-run"
        PREREQ_FAIL=1
    fi
else
    ok "git-lfs $(git lfs version 2>/dev/null | awk '{print $1}')"
fi

# --- AMD GPUs ---
DETECTED_GPU_COUNT=0
if command -v rocm-smi &>/dev/null; then
    DETECTED_GPU_COUNT=$(rocm-smi --showid 2>/dev/null | grep -o "GPU\[[0-9]*\]" | sort -u | wc -l || echo 0)
fi
if [ "$DETECTED_GPU_COUNT" -eq 0 ] && [ -d /sys/class/drm ]; then
    DETECTED_GPU_COUNT=$(for f in /sys/class/drm/card*/device/vendor; do
        [ -f "$f" ] && cat "$f" 2>/dev/null; done | grep -c "0x1002" || echo 0)
fi

if [ "$DETECTED_GPU_COUNT" -lt "$MIN_REQUIRED_GPUS" ]; then
    error "${DETECTED_GPU_COUNT} AMD GPU(s) detected — minimum ${MIN_REQUIRED_GPUS} required"
    error "  GPU 0 → Qwen3.5-9B (VLM/translation)  |  GPU 1 → Gemma-4-E2B-it x2 (authoring)"
    error "  GPU 2,3 → Flux (illustration, via Lemonade)"
    PREREQ_FAIL=1
else
    GPU_NAMES=""
    command -v rocm-smi &>/dev/null && \
        GPU_NAMES=$(rocm-smi --showproductname 2>/dev/null | grep "Card Series" \
            | sed 's/.*: *//' | tr '\n' ',' | sed 's/,$//' || true)
    if [ -n "$GPU_NAMES" ]; then
        ok "${DETECTED_GPU_COUNT} AMD GPU(s): ${GPU_NAMES}"
    else
        ok "${DETECTED_GPU_COUNT} AMD GPU(s) detected"
    fi
fi

# --- ROCm device nodes ---
if [ ! -e /dev/kfd ]; then
    error "/dev/kfd not found — ROCm kernel driver not loaded"
    PREREQ_FAIL=1
elif [ ! -d /dev/dri ]; then
    error "/dev/dri not found — DRM subsystem not available"
    PREREQ_FAIL=1
else
    ok "ROCm device nodes (/dev/kfd, /dev/dri)"
fi

# --- Disk ---
FREE_GB=$(df -BG "$SCRIPT_DIR" | awk 'NR==2{gsub("G","",$4); print $4}')
if [ "${FREE_GB:-0}" -lt "$DISK_MIN_GB" ]; then
    error "Only ${FREE_GB} GB free — minimum ${DISK_MIN_GB} GB required (model weights)"
    PREREQ_FAIL=1
else
    ok "${FREE_GB} GB free disk"
fi

# --- RAM ---
TOTAL_RAM_GB=$(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
if [ "${TOTAL_RAM_GB:-0}" -lt "$RAM_MIN_GB" ]; then
    error "${TOTAL_RAM_GB} GB RAM — minimum ${RAM_MIN_GB} GB required"
    PREREQ_FAIL=1
else
    ok "${TOTAL_RAM_GB} GB total RAM"
fi

echo ""
[ "$PREREQ_FAIL" -ne 0 ] && die "Fix the errors above then re-run."

# =============================================================================
# STEP 2: ENVIRONMENT CONFIGURATION
# =============================================================================
echo -e "${BOLD}[2/3] Environment configuration${NC}"
echo ""

SKIP_ENV=0
if [ -f .env ]; then
    warn ".env already exists."
    read -rp "  Overwrite it? [y/N]: " _ow || _ow="N"
    if [[ ! "${_ow:-N}" =~ ^[Yy]$ ]]; then
        info "Keeping existing .env"
        SKIP_ENV=1
        echo ""
    else
        rm .env
    fi
fi

if [ "$SKIP_ENV" -eq 0 ]; then
    : > .env
    echo "  Press Enter to accept the default shown in [brackets]. Secrets have no"
    echo "  default — they must be entered explicitly."
    echo ""

    # --- Database ---
    echo -e "  ${BOLD}Database${NC}"
    while true; do
        read -rsp "  Postgres password (will not be echoed): " _pg_pw; echo ""
        [ -z "${_pg_pw:-}" ] && { error "  Cannot be empty."; continue; }
        read -rsp "  Confirm password: " _pg_pw2; echo ""
        [ "$_pg_pw" != "$_pg_pw2" ] && { error "  Passwords do not match."; continue; }
        break
    done
    add_or_replace "POSTGRES_PASSWORD" "$_pg_pw"
    add_or_replace "DATABASE_URL" "postgresql://wig:${_pg_pw}@postgres:5432/wig?sslmode=disable"
    echo ""

    # --- RustFS object store (Milvus backing store, used by the ingest RAG service) ---
    echo -e "  ${BOLD}RustFS / Milvus object store${NC}"
    while true; do
        read -rp "  RustFS access key: " _rs_key || _rs_key=""
        [ -z "${_rs_key:-}" ] && { error "  Cannot be empty."; continue; }
        break
    done
    while true; do
        read -rsp "  RustFS secret key (will not be echoed): " _rs_secret; echo ""
        [ -z "${_rs_secret:-}" ] && { error "  Cannot be empty."; continue; }
        read -rsp "  Confirm secret key: " _rs_secret2; echo ""
        [ "$_rs_secret" != "$_rs_secret2" ] && { error "  Do not match."; continue; }
        break
    done
    add_or_replace "RUSTFS_ACCESS_KEY" "$_rs_key"
    add_or_replace "RUSTFS_SECRET_KEY" "$_rs_secret"
    echo ""

    # --- Host cache directories ---
    echo -e "  ${BOLD}Host cache directories${NC}"
    DEFAULT_HF="${HOME}/.cache/huggingface"
    read -rp "  HuggingFace cache dir (Qwen3.5-9B, Gemma-4-E2B-it) [${DEFAULT_HF}]: " _hf_dir || _hf_dir=""
    _hf_dir="${_hf_dir:-${DEFAULT_HF}}"
    mkdir -p "$_hf_dir"
    add_or_replace "HF_CACHE_DIR" "$_hf_dir"

    DEFAULT_LLAMA="${HOME}/.cache/lemonade/llama"
    read -rp "  Lemonade llama dir [${DEFAULT_LLAMA}]: " _llama_dir || _llama_dir=""
    _llama_dir="${_llama_dir:-${DEFAULT_LLAMA}}"
    mkdir -p "$_llama_dir"
    add_or_replace "LEMONADE_LLAMA_DIR" "$_llama_dir"

    DEFAULT_RECIPE="${HOME}/.cache/lemonade/recipe"
    read -rp "  Lemonade recipe/model cache dir (Flux) [${DEFAULT_RECIPE}]: " _recipe_dir || _recipe_dir=""
    _recipe_dir="${_recipe_dir:-${DEFAULT_RECIPE}}"
    mkdir -p "$_recipe_dir"
    add_or_replace "LEMONADE_RECIPE_DIR" "$_recipe_dir"
    ok "  Cache directories ready"
    echo ""

    # --- GPU device assignment ---
    echo -e "  ${BOLD}GPU device assignment${NC} (renderD* nodes as shown by \`ls /dev/dri\`)"
    read -rp "  GPU 0 render node — Qwen3.5-9B (VLM/translation) [renderD129]: " _gpu_inf || _gpu_inf=""
    add_or_replace "GPU_INFERENCE_DEVICE" "${_gpu_inf:-renderD129}"
    read -rp "  GPU 1 render node — Gemma-4-E2B-it x2 (authoring) [renderD130]: " _gpu_gemma || _gpu_gemma=""
    add_or_replace "GPU_GEMMA_DEVICE" "${_gpu_gemma:-renderD130}"
    read -rp "  GPU 2 render node — Flux/Lemonade instance 1 [renderD128]: " _gpu_lem1 || _gpu_lem1=""
    add_or_replace "GPU_LEMONADE1_DEVICE" "${_gpu_lem1:-renderD128}"
    read -rp "  GPU 3 render node — Flux/Lemonade instance 2 [renderD131]: " _gpu_lem2 || _gpu_lem2=""
    add_or_replace "GPU_LEMONADE2_DEVICE" "${_gpu_lem2:-renderD131}"
    echo ""

    # --- OpenClaw gateway token ---
    # openclaw-gateway enforces token auth on its HTTP API (see
    # work_instruction_generator/openclaw/openclaw.json). Reject the old
    # checked-in placeholder and require >=16 chars so the gateway is never
    # left fail-open. Pressing Enter mints a strong token.
    echo -e "  ${BOLD}Security${NC}"
    _oc_default="$(gen_token)"
    while true; do
        read -rp "  OpenClaw gateway token [auto-generated strong token]: " _oc_token || _oc_token=""
        _oc_token="${_oc_token:-$_oc_default}"
        [ "$_oc_token" = "wig-openclaw-internal" ] && { error "  'wig-openclaw-internal' is the old insecure placeholder — leave blank to auto-generate."; continue; }
        [ "${#_oc_token}" -lt 16 ] && { error "  Minimum 16 characters — leave blank to auto-generate."; continue; }
        break
    done
    add_or_replace "OPENCLAW_GATEWAY_TOKEN" "$_oc_token"
    echo ""

    # --- Gemma model provider API keys (openclaw.json) ---
    # Local vLLM servers run with no auth, so any placeholder value works
    # unless a real auth layer is added in front of them. Auto-generate a
    # short key if left blank.
    read -rp "  Gemma authoring model API key [auto-generated]: " _gemma_author_key || _gemma_author_key=""
    add_or_replace "GEMMA_AUTHOR_API_KEY" "${_gemma_author_key:-$(gen_short_token)}"
    read -rp "  Translation model API key [auto-generated]: " _translate_gemma_key || _translate_gemma_key=""
    add_or_replace "TRANSLATE_GEMMA_API_KEY" "${_translate_gemma_key:-$(gen_short_token)}"
    read -rp "  Inference (Qwen) model API key [auto-generated]: " _inference_key || _inference_key=""
    add_or_replace "INFERENCE_API_KEY" "${_inference_key:-$(gen_short_token)}"
    echo ""

    ok ".env written"
    echo ""
fi

# Backfill Gemma provider API keys for pre-existing .env files that predate
# this setting (kept via "Keeping existing .env" above).
grep -q "^GEMMA_AUTHOR_API_KEY=" .env 2>/dev/null || add_or_replace "GEMMA_AUTHOR_API_KEY" "$(gen_short_token)"
grep -q "^TRANSLATE_GEMMA_API_KEY=" .env 2>/dev/null || add_or_replace "TRANSLATE_GEMMA_API_KEY" "$(gen_short_token)"
grep -q "^INFERENCE_API_KEY=" .env 2>/dev/null || add_or_replace "INFERENCE_API_KEY" "$(gen_short_token)"

# --- GPU device group GIDs (video / render) ---
# amd-device-metrics-exporter and the GPU-bound containers need the host's
# actual numeric GIDs to access /dev/kfd and /dev/dri.  Auto-detect; fall
# back to the defaults already baked into work_instruction_generator/metrics/docker-compose.yml.
_VIDEO_GID="$(getent group video 2>/dev/null | cut -d: -f3)"
_RENDER_GID="$(getent group render 2>/dev/null | cut -d: -f3)"
[ -z "${_VIDEO_GID:-}" ] && _VIDEO_GID="44"
[ -z "${_RENDER_GID:-}" ] && _RENDER_GID="109"
add_or_replace "VIDEO_GID" "${_VIDEO_GID}"
add_or_replace "RENDER_GID" "${_RENDER_GID}"
ok "GPU groups detected (video=${_VIDEO_GID}, render=${_RENDER_GID})"
echo ""

# =============================================================================
# STEP 3: BUILD & LAUNCH
# =============================================================================
echo -e "${BOLD}[3/3] Building images & starting services...${NC}"
echo ""

if git -C "$SCRIPT_DIR" rev-parse --git-dir &>/dev/null; then
    info "Fetching Git LFS files (OEM manual PDFs)..."
    git -C "$SCRIPT_DIR" lfs pull
    ok "LFS files present"
    echo ""
fi

info "Building all service images..."
if ! retry_command "Docker Compose build" "$SETUP_DOCKER_RETRY_ATTEMPTS" "$SETUP_DOCKER_RETRY_DELAY_S" \
    docker compose build; then
    die "Docker build failed — check output above."
fi
ok "All images built"
echo ""

# When .env was (re)written this run, drop the volume so Postgres
# re-initializes with the current password.
if [ "$SKIP_ENV" -eq 0 ]; then
    docker compose down --remove-orphans >/dev/null 2>&1 || true
    for _vol in $(docker volume ls -q --filter name=postgres-data); do
        docker volume rm "$_vol" >/dev/null 2>&1 || true
    done
fi

info "Starting services (model-downloader fetches Qwen3.5-9B ~19GB on first run)..."
if ! retry_command "Docker Compose startup" "$SETUP_DOCKER_RETRY_ATTEMPTS" "$SETUP_DOCKER_RETRY_DELAY_S" \
    docker compose up -d; then
    die "Docker Compose startup failed — check output above."
fi
ok "Services started"
echo ""

info "vLLM (Qwen3.5-9B, Gemma-4-E2B-it) and Lemonade (Flux) can take 15-30 min to become"
info "healthy on first run while models download and load onto GPU. Track progress with:"
info "  docker compose logs -f inference llm-inference-1 lemonade-1"
echo ""
info "Once models are loaded the UI comes up and is fully usable. OEM reference-doc"
info "ingestion then runs in the background (15-20 min); until it finishes the UI shows"
info "an 'indexing' banner and generated instructions have limited OEM-manual context."
info "  docker compose logs -f oem-ingest"

echo ""
hr
ok "Platform is starting up."
hr
echo ""
echo "  GPU layout:"
echo "    GPU 0  →  Qwen3.5-9B (VLM / translation)"
echo "    GPU 1  →  Gemma-4-E2B-it instance 1 + 2 (instruction authoring)"
echo "    GPU 2  →  Flux via Lemonade instance 1 (illustration generation)"
echo "    GPU 3  →  Flux via Lemonade instance 2 (illustration generation)"
echo ""
echo "  Endpoints:"
LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk 'NR==1{print $4}' | cut -d/ -f1)"
echo "    Frontend →  http://localhost:5173"
[ -n "$LAN_IP" ] && echo "    LAN      →  http://${LAN_IP}:5173"
echo ""
echo "  Only the frontend port is published to the host; Milvus/Attu, NATS,"
echo "  the agent containers, and the model servers are reachable only on"
echo "  the internal wig-net docker network."
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f wig-api"
echo "    docker compose logs -f wig-mcp-tools"
echo "    docker compose logs -f inference llm-inference-1 llm-inference-2"
echo "    docker compose ps"
echo "    docker compose down"
echo ""
