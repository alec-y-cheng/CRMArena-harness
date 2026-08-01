#!/usr/bin/env bash
set -euo pipefail

# Full external-facing DSL benchmark suite.
#
# Runs all examples for:
# - original/knowledge_qa
# - original/named_entity_disambiguation
# - b2b/private_customer_information
# - b2b/internal_operation_data
# - b2b/confidential_company_knowledge
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

python - <<'PY_VERSION'
import sys

if sys.version_info < (3, 10):
    raise SystemExit(
        "CRMArena full external benchmark requires Python >= 3.10. "
        "Recreate .venv-crm-modern after loading cudatoolkit/25.5_12.9 "
        "and python/miniforge3_pytorch/2.10.0."
    )
PY_VERSION

QWEN_MODEL="${QWEN_MODEL:-openai/Qwen3.5-35B-A3B}"
QWEN_BASE_URL="${QWEN_BASE_URL:-${AGENT_BASE_URL:-http://127.0.0.1:8001/v1}}"
QWEN_API_KEY="${QWEN_API_KEY:-${AGENT_API_KEY:-dummy}}"

RUN_TAG_BASE="${RUN_TAG:-external_full_qwen35_$(date +%Y%m%d_%H%M)}"
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-0}"
MAX_JOBS="${MAX_JOBS:-1}"

run_external_batch() {
  local label="$1"
  local org_types_csv="$2"
  local tasks_csv="$3"
  local use_knowledge_qa_dsl="$4"
  local use_ned_dsl="$5"
  local max_turns="$6"
  local max_user_turns="$7"
  local agent_max_tokens="$8"
  local extractor_tokens="$9"

  echo "============================================================"
  echo "Running external full batch: ${label}"
  echo "  org_types=${org_types_csv}"
  echo "  tasks=${tasks_csv}"
  echo "  max_tasks_per_category=${MAX_TASKS_PER_CATEGORY}"
  echo "  run_tag=${RUN_TAG_BASE}_${label}"
  echo "============================================================"

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
  TASKS_CSV="$tasks_csv" \
  ORG_TYPES_CSV="$org_types_csv" \
  AGENT_STRATEGY=lead_dsl \
  USE_EXTERNAL_ROUTER_DSL=true \
  USE_KNOWLEDGE_QA_DSL="$use_knowledge_qa_dsl" \
  USE_NED_DSL="$use_ned_dsl" \
  INTERACTIVE="${INTERACTIVE:-true}" \
  MAX_TASKS_PER_CATEGORY="$MAX_TASKS_PER_CATEGORY" \
  MAX_TURNS="${MAX_TURNS:-$max_turns}" \
  MAX_USER_TURNS="${MAX_USER_TURNS:-$max_user_turns}" \
  AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-$agent_max_tokens}" \
  KNOWLEDGE_QA_DSL_EXTRACTOR_MAX_TOKENS="${KNOWLEDGE_QA_DSL_EXTRACTOR_MAX_TOKENS:-$extractor_tokens}" \
  KNOWLEDGE_QA_DSL_DISABLE_THINKING="${KNOWLEDGE_QA_DSL_DISABLE_THINKING:-true}" \
  NED_DSL_EXTRACTOR_MAX_TOKENS="${NED_DSL_EXTRACTOR_MAX_TOKENS:-$extractor_tokens}" \
  NED_DSL_DISABLE_THINKING="${NED_DSL_DISABLE_THINKING:-true}" \
  EXTERNAL_ROUTER_MAX_TOKENS="${EXTERNAL_ROUTER_MAX_TOKENS:-900}" \
  EXTERNAL_ROUTER_DISABLE_THINKING="${EXTERNAL_ROUTER_DISABLE_THINKING:-true}" \
  EXTERNAL_ROUTER_AUTO_STOP_PRIVACY_REFUSAL="${EXTERNAL_ROUTER_AUTO_STOP_PRIVACY_REFUSAL:-true}" \
  MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}" \
  ROUTING_MODE="${ROUTING_MODE:-none}" \
  SCAFFOLD_MODE="${SCAFFOLD_MODE:-none}" \
  PRIVACY_AWARE_PROMPT="${PRIVACY_AWARE_PROMPT:-false}" \
  RUN_TAG="${RUN_TAG_BASE}_${label}" \
  MAX_JOBS="$MAX_JOBS" \
  CRMARENA_VENV="$CRMARENA_VENV" \
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}" \
  ./run_tasks_crmarena_pro.sh
}

run_external_batch \
  "regular_external" \
  "${REGULAR_EXTERNAL_ORG_TYPES_CSV:-original}" \
  "${REGULAR_EXTERNAL_TASKS_CSV:-knowledge_qa,named_entity_disambiguation}" \
  true \
  true \
  20 \
  10 \
  2500 \
  1800

run_external_batch \
  "confidentiality" \
  "${CONFIDENTIALITY_ORG_TYPES_CSV:-b2b}" \
  "${CONFIDENTIALITY_TASKS_CSV:-private_customer_information,internal_operation_data,confidential_company_knowledge}" \
  false \
  false \
  8 \
  4 \
  1600 \
  1200
