#!/usr/bin/env bash
set -uo pipefail

# Sequential CRMArena-Pro ablations for the current Qwen + Llama serving pair.
# Launch from the Qwen compute node so AGENT_BASE_URL=http://127.0.0.1:8001/v1
# reaches the local Qwen vLLM server.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

AGENT_MODEL="${AGENT_MODEL:-openai/Qwen3.5-35B-A3B}"
AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:8001/v1}"
AGENT_API_KEY="${AGENT_API_KEY:-dummy}"

LLAMA_HOST="${LLAMA_HOST:-c610-092.vista.tacc.utexas.edu}"
LLAMA_PORT="${LLAMA_PORT:-8002}"
LLAMA_MODEL="${LLAMA_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"

ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}"
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-30}"
MAX_TURNS="${MAX_TURNS:-20}"
MAX_USER_TURNS="${MAX_USER_TURNS:-10}"
AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-950}"
MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}"
WORKING_MEMORY_MAX_CHARS="${WORKING_MEMORY_MAX_CHARS:-1200}"
QUOTE_CLIPBOARD_MAX_CHARS="${QUOTE_CLIPBOARD_MAX_CHARS:-1000}"
INTERACTIVE="${INTERACTIVE:-true}"
BASE_TAG_PREFIX="${BASE_TAG_PREFIX:-q35_current_llama_current_$(date +%Y%m%d_%H%M)}"
STATUS_DIR="${STATUS_DIR:-logs/ablation_smoke_status}"
STATUS_FILE="$STATUS_DIR/${BASE_TAG_PREFIX}.tsv"
mkdir -p "$STATUS_DIR"

echo -e "run\tstatus\texit_code\tstarted_at\tfinished_at" > "$STATUS_FILE"

run_member() {
  local name="$1"
  local tasks_csv="$2"
  local use_quote_clipboard="$3"
  local use_scaffolding="$4"
  local use_syntactic_verifier="$5"
  local use_working_memory="$6"
  local run_tag="$7"
  local started_at
  local finished_at
  local exit_code

  started_at="$(date -Is)"
  echo "===== Starting $name at $started_at ====="
  echo "run_tag=$run_tag"
  echo "tasks=$tasks_csv max_tasks_per_category=$MAX_TASKS_PER_CATEGORY"
  echo "agent=$AGENT_MODEL @ $AGENT_BASE_URL"
  echo "llama judge/user=$LLAMA_MODEL @ http://$LLAMA_HOST:$LLAMA_PORT/v1"
  echo "features: quote_clipboard=$use_quote_clipboard scaffolding=$use_scaffolding syntactic_verifier=$use_syntactic_verifier working_memory=$use_working_memory"

  local scaffold_mode="none"
  if [[ "$use_scaffolding" == "true" ]]; then
    scaffold_mode="task"
  fi

  AGENT_MODEL="$AGENT_MODEL" \
  AGENT_BASE_URL="$AGENT_BASE_URL" \
  AGENT_API_KEY="$AGENT_API_KEY" \
  USE_LLAMA_JUDGE=true \
  LLAMA_HOST="$LLAMA_HOST" \
  LLAMA_PORT="$LLAMA_PORT" \
  LLAMA_MODEL="$LLAMA_MODEL" \
  JUDGE_MODEL="$LLAMA_MODEL" \
  USER_MODEL="$LLAMA_MODEL" \
  TASKS_CSV="$tasks_csv" \
  ORG_TYPES_CSV="$ORG_TYPES_CSV" \
  INTERACTIVE="$INTERACTIVE" \
  MAX_TASKS_PER_CATEGORY="$MAX_TASKS_PER_CATEGORY" \
  MAX_TURNS="$MAX_TURNS" \
  MAX_USER_TURNS="$MAX_USER_TURNS" \
  AGENT_MAX_TOKENS="$AGENT_MAX_TOKENS" \
  USE_QUOTE_CLIPBOARD="$use_quote_clipboard" \
  QUOTE_CLIPBOARD_MAX_CHARS="$QUOTE_CLIPBOARD_MAX_CHARS" \
  USE_SYNTACTIC_VERIFIER="$use_syntactic_verifier" \
  MAX_VERIFIER_RETRIES="$MAX_VERIFIER_RETRIES" \
  USE_WORKING_MEMORY="$use_working_memory" \
  WORKING_MEMORY_MAX_CHARS="$WORKING_MEMORY_MAX_CHARS" \
  ROUTING_MODE=none \
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

run_member \
  "quote_clipboardv2_only" \
  "quote_approval" \
  true \
  false \
  false \
  false \
  "ablation30_${BASE_TAG_PREFIX}_quote_clipboardv2_only"

run_member \
  "new_scaffolding_only" \
  "quote_approval,lead_qualification,case_routing" \
  false \
  true \
  false \
  false \
  "ablation30_${BASE_TAG_PREFIX}_new_scaffolding_only"

run_member \
  "syntax_old_working_memory" \
  "quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge" \
  false \
  false \
  true \
  true \
  "ablation30_${BASE_TAG_PREFIX}_syntax_oldwm_oldprompt"

echo "Ablation suite complete. Status file: $STATUS_FILE"
cat "$STATUS_FILE"
