#!/usr/bin/env bash
set -euo pipefail

# Quick smoke test for the external router on confidentiality tasks.
#
# Runs 5 tasks from each confidentiality category:
# - private_customer_information
# - internal_operation_data
# - confidential_company_knowledge
#
# Start an OpenAI-compatible vLLM server first. By default this script expects
# Qwen to be reachable from the current node at:
#   http://127.0.0.1:8001/v1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

CRMARENA_VENV="${CRMARENA_VENV:-$ROOT_DIR/.venv-crm-modern}"
if [[ -f "$CRMARENA_VENV/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$CRMARENA_VENV/bin/activate"
fi

python - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit(
        "CRMArena smoke test requires Python >= 3.10. "
        "Recreate .venv-crm-modern after loading cudatoolkit/25.5_12.9 "
        "and python/miniforge3_pytorch/2.10.0."
    )
PY

QWEN_MODEL="${QWEN_MODEL:-openai/Qwen3.5-35B-A3B}"
QWEN_BASE_URL="${QWEN_BASE_URL:-${AGENT_BASE_URL:-http://127.0.0.1:8001/v1}}"
QWEN_API_KEY="${QWEN_API_KEY:-${AGENT_API_KEY:-dummy}}"

RUN_TAG="${RUN_TAG:-confidentiality_router_smoke_qwen35_$(date +%Y%m%d_%H%M)}"

AGENT_MODEL="$QWEN_MODEL" \
AGENT_PROVIDER="${AGENT_PROVIDER:-openai}" \
AGENT_BASE_URL="$QWEN_BASE_URL" \
AGENT_API_KEY="$QWEN_API_KEY" \
JUDGE_MODEL="${JUDGE_MODEL:-$QWEN_MODEL}" \
JUDGE_PROVIDER="${JUDGE_PROVIDER:-openai}" \
JUDGE_BASE_URL="${JUDGE_BASE_URL:-$QWEN_BASE_URL}" \
JUDGE_API_KEY="${JUDGE_API_KEY:-$QWEN_API_KEY}" \
USER_MODEL="${USER_MODEL:-$QWEN_MODEL}" \
USER_PROVIDER="${USER_PROVIDER:-openai}" \
USER_BASE_URL="${USER_BASE_URL:-$QWEN_BASE_URL}" \
USER_API_KEY="${USER_API_KEY:-$QWEN_API_KEY}" \
TASKS_CSV="${TASKS_CSV:-private_customer_information,internal_operation_data,confidential_company_knowledge}" \
ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}" \
AGENT_STRATEGY=lead_dsl \
USE_EXTERNAL_ROUTER_DSL=true \
USE_KNOWLEDGE_QA_DSL=false \
USE_NED_DSL=false \
INTERACTIVE="${INTERACTIVE:-true}" \
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-5}" \
MAX_TURNS="${MAX_TURNS:-8}" \
MAX_USER_TURNS="${MAX_USER_TURNS:-4}" \
AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-1600}" \
EXTERNAL_ROUTER_MAX_TOKENS="${EXTERNAL_ROUTER_MAX_TOKENS:-900}" \
EXTERNAL_ROUTER_DISABLE_THINKING="${EXTERNAL_ROUTER_DISABLE_THINKING:-true}" \
MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}" \
ROUTING_MODE="${ROUTING_MODE:-none}" \
SCAFFOLD_MODE="${SCAFFOLD_MODE:-none}" \
PRIVACY_AWARE_PROMPT="${PRIVACY_AWARE_PROMPT:-true}" \
RUN_TAG="$RUN_TAG" \
MAX_JOBS="${MAX_JOBS:-1}" \
./run_tasks_crmarena_pro.sh
