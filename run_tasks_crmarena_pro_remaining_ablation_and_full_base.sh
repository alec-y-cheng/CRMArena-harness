#!/usr/bin/env bash
set -uo pipefail

# Run remaining 30-sample ablations, then a clean full unmodified baseline.
# Designed to be launched directly on the Qwen compute node, where
# AGENT_BASE_URL=http://127.0.0.1:8001/v1 reaches the local vLLM server.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

LLAMA_HOST="${LLAMA_HOST:-c638-031.vista.tacc.utexas.edu}"
LLAMA_PORT="${LLAMA_PORT:-8002}"
AGENT_MODEL="${AGENT_MODEL:-openai/Qwen3.5-35B-A3B}"
AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:8001/v1}"
LLAMA_MODEL="${LLAMA_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
TASKS_CSV="${TASKS_CSV:-quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge}"
ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}"
MAX_TURNS="${MAX_TURNS:-20}"
MAX_USER_TURNS="${MAX_USER_TURNS:-10}"
AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-950}"
MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}"
BASE_TAG_PREFIX="${BASE_TAG_PREFIX:-q35_858267_llama_858420}"
STATUS_DIR="${STATUS_DIR:-logs/remaining_ablation_status}"
STATUS_FILE="$STATUS_DIR/${BASE_TAG_PREFIX}_$(date +%Y%m%d_%H%M%S).tsv"
mkdir -p "$STATUS_DIR"

echo -e "run\tstatus\texit_code\tstarted_at\tfinished_at" > "$STATUS_FILE"

run_member() {
  local name="$1"
  local max_tasks="$2"
  local use_working_memory="$3"
  local use_syntactic_verifier="$4"
  local routing_mode="$5"
  local scaffold_mode="$6"
  local run_tag="$7"
  local started_at
  local finished_at
  local exit_code

  started_at="$(date -Is)"
  echo "===== Starting $name at $started_at ====="
  echo "run_tag=$run_tag max_tasks_per_category=$max_tasks"
  echo "features: working_memory=$use_working_memory syntactic_verifier=$use_syntactic_verifier routing_mode=$routing_mode scaffold_mode=$scaffold_mode"

  AGENT_MODEL="$AGENT_MODEL" \
  AGENT_BASE_URL="$AGENT_BASE_URL" \
  AGENT_API_KEY="${AGENT_API_KEY:-dummy}" \
  USE_LLAMA_JUDGE=true \
  LLAMA_HOST="$LLAMA_HOST" \
  LLAMA_PORT="$LLAMA_PORT" \
  LLAMA_MODEL="$LLAMA_MODEL" \
  JUDGE_MODEL="$LLAMA_MODEL" \
  USER_MODEL="$LLAMA_MODEL" \
  TASKS_CSV="$TASKS_CSV" \
  ORG_TYPES_CSV="$ORG_TYPES_CSV" \
  INTERACTIVE="${INTERACTIVE:-true}" \
  MAX_TASKS_PER_CATEGORY="$max_tasks" \
  MAX_TURNS="$MAX_TURNS" \
  MAX_USER_TURNS="$MAX_USER_TURNS" \
  AGENT_MAX_TOKENS="$AGENT_MAX_TOKENS" \
  USE_WORKING_MEMORY="$use_working_memory" \
  WORKING_MEMORY_MAX_CHARS="${WORKING_MEMORY_MAX_CHARS:-1200}" \
  USE_SYNTACTIC_VERIFIER="$use_syntactic_verifier" \
  MAX_VERIFIER_RETRIES="$MAX_VERIFIER_RETRIES" \
  ROUTING_MODE="$routing_mode" \
  SCAFFOLD_MODE="$scaffold_mode" \
  RUN_TAG="$run_tag" \
  MAX_JOBS=1 \
  ./run_tasks_crmarena_pro.sh
  exit_code=$?

  finished_at="$(date -Is)"
  if [[ "$exit_code" -eq 0 ]]; then
    echo -e "$name\tok\t$exit_code\t$started_at\t$finished_at" >> "$STATUS_FILE"
    echo "===== Finished $name OK at $finished_at ====="
  else
    echo -e "$name\tfailed\t$exit_code\t$started_at\t$finished_at" >> "$STATUS_FILE"
    echo "===== $name failed exit=$exit_code at $finished_at; continuing =====" >&2
  fi
}

run_member "working_memory_30" 30 true false none none "ablation30_${BASE_TAG_PREFIX}_working_memory_only"
run_member "routing_30" 30 false false deterministic routed "ablation30_${BASE_TAG_PREFIX}_routing_only"
run_member "base_full_unmodified" 0 false false none none "base_full_unmodified_${BASE_TAG_PREFIX}"

echo "Remaining ablations + full baseline complete. Status file: $STATUS_FILE"
cat "$STATUS_FILE"
