#!/usr/bin/env bash
set -euo pipefail

# Quick smoke test for the lead-qualification symbolic DSL workflow.
#
# Start an OpenAI-compatible vLLM server first. By default this script expects
# Qwen to be reachable from the current node at:
#   http://127.0.0.1:8001/v1
#
# Example:
#   AGENT_BASE_URL=http://127.0.0.1:8001/v1 \
#   ./run_tasks_crmarena_pro_lead_dsl_smoke.sh

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

RUN_TAG="${RUN_TAG:-lead_dsl_smoke_qwen35_$(date +%Y%m%d_%H%M)}"

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
TASKS_CSV=lead_qualification \
ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}" \
AGENT_STRATEGY=lead_dsl \
INTERACTIVE="${INTERACTIVE:-true}" \
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-30}" \
	MAX_TURNS="${MAX_TURNS:-20}" \
	MAX_USER_TURNS="${MAX_USER_TURNS:-10}" \
	AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-2500}" \
	LEAD_DSL_EXTRACTOR_MAX_TOKENS="${LEAD_DSL_EXTRACTOR_MAX_TOKENS:-1800}" \
	LEAD_DSL_DISABLE_THINKING="${LEAD_DSL_DISABLE_THINKING:-true}" \
	MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}" \
	ROUTING_MODE="${ROUTING_MODE:-none}" \
SCAFFOLD_MODE="${SCAFFOLD_MODE:-none}" \
RUN_TAG="$RUN_TAG" \
MAX_JOBS="${MAX_JOBS:-1}" \
./run_tasks_crmarena_pro.sh
