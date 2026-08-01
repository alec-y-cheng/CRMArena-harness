#!/usr/bin/env bash
set -euo pipefail

# CRMArena-Pro launcher. This is a thin, configurable wrapper around
# run_tasks.py; it does not implement a separate benchmark path.
#
# Typical Vista local-vLLM usage:
#   AGENT_BASE_URL=http://127.0.0.1:8001/v1 \
#   JUDGE_BASE_URL=http://<llama-node>:8002/v1 \
#   USER_BASE_URL=http://<llama-node>:8002/v1 \
#   TASKS_CSV=quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge \
#   ORG_TYPES_CSV=b2b \
#   ./run_tasks_crmarena_pro.sh

AGENT_MODEL="${AGENT_MODEL:-openai/Qwen3.5-35B-A3B}"
AGENT_PROVIDER="${AGENT_PROVIDER:-openai}"
AGENT_BASE_URL="${AGENT_BASE_URL:-${OPENAI_BASE_URL:-http://127.0.0.1:8001/v1}}"
AGENT_API_KEY="${AGENT_API_KEY:-${OPENAI_API_KEY:-dummy}}"

USE_LLAMA_JUDGE="${USE_LLAMA_JUDGE:-false}"
LLAMA_MODEL="${LLAMA_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
LLAMA_PORT="${LLAMA_PORT:-8002}"
if [[ "$USE_LLAMA_JUDGE" == "true" && -n "${LLAMA_HOST:-}" ]]; then
  JUDGE_MODEL="${JUDGE_MODEL:-$LLAMA_MODEL}"
  JUDGE_BASE_URL="${JUDGE_BASE_URL:-http://$LLAMA_HOST:$LLAMA_PORT/v1}"
  USER_MODEL="${USER_MODEL:-$JUDGE_MODEL}"
  USER_BASE_URL="${USER_BASE_URL:-$JUDGE_BASE_URL}"
fi

JUDGE_MODEL="${JUDGE_MODEL:-$AGENT_MODEL}"
JUDGE_PROVIDER="${JUDGE_PROVIDER:-openai}"
JUDGE_BASE_URL="${JUDGE_BASE_URL:-$AGENT_BASE_URL}"
JUDGE_API_KEY="${JUDGE_API_KEY:-$AGENT_API_KEY}"

USER_MODEL="${USER_MODEL:-$JUDGE_MODEL}"
USER_PROVIDER="${USER_PROVIDER:-$JUDGE_PROVIDER}"
USER_BASE_URL="${USER_BASE_URL:-$JUDGE_BASE_URL}"
USER_API_KEY="${USER_API_KEY:-$JUDGE_API_KEY}"

DEFAULT_TASKS_CSV="quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge"
TASKS_CSV="${TASKS_CSV:-$DEFAULT_TASKS_CSV}"
ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}"
AGENT_STRATEGY="${AGENT_STRATEGY:-react}"
EVAL_MODE="${EVAL_MODE:-default}"
INTERACTIVE="${INTERACTIVE:-true}"
MAX_TURNS="${MAX_TURNS:-20}"
MAX_USER_TURNS="${MAX_USER_TURNS:-10}"
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-0}"
AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-2500}"
LEAD_DSL_EXTRACTOR_MAX_TOKENS="${LEAD_DSL_EXTRACTOR_MAX_TOKENS:-1800}"
LEAD_DSL_DISABLE_THINKING="${LEAD_DSL_DISABLE_THINKING:-true}"
export LEAD_DSL_EXTRACTOR_MAX_TOKENS
export LEAD_DSL_DISABLE_THINKING
USE_SYNTACTIC_VERIFIER="${USE_SYNTACTIC_VERIFIER:-false}"
MAX_VERIFIER_RETRIES="${MAX_VERIFIER_RETRIES:-3}"
USE_WORKING_MEMORY="${USE_WORKING_MEMORY:-false}"
WORKING_MEMORY_MAX_CHARS="${WORKING_MEMORY_MAX_CHARS:-1200}"
USE_QUOTE_CLIPBOARD="${USE_QUOTE_CLIPBOARD:-false}"
QUOTE_CLIPBOARD_MAX_CHARS="${QUOTE_CLIPBOARD_MAX_CHARS:-1000}"
USE_LEAD_CLIPBOARD="${USE_LEAD_CLIPBOARD:-false}"
LEAD_CLIPBOARD_MAX_CHARS="${LEAD_CLIPBOARD_MAX_CHARS:-1000}"
ROUTING_MODE="${ROUTING_MODE:-deterministic}"
ROUTING_MIN_CONFIDENCE="${ROUTING_MIN_CONFIDENCE:-0.55}"
SCAFFOLD_MODE="${SCAFFOLD_MODE:-routed}"
PRIVACY_AWARE_PROMPT="${PRIVACY_AWARE_PROMPT:-false}"
MAX_JOBS="${MAX_JOBS:-1}"
RUN_TAG="${RUN_TAG:-qwen35_llama31_8b_judge_user}"
RESULT_SUFFIX="${RESULT_SUFFIX:-}"

export OPENAI_API_KEY="$AGENT_API_KEY"
export OPENAI_API_BASE="$AGENT_BASE_URL"
export OPENAI_BASE_URL="$AGENT_BASE_URL"
export HF_HOME="${HF_HOME:-/work/hdd/bgtb/acheng11/qwen_agent_ft/cache/huggingface}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HF_HOME/datasets}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"
SKIP_HEALTH_CHECKS="${SKIP_HEALTH_CHECKS:-false}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3 || true)}"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: neither python nor python3 is available on PATH. Load a Python module or set PYTHON_BIN." >&2
  exit 127
fi

check_endpoint() {
  local label="$1"
  local base_url="$2"
  local url="${base_url%/}/models"

  if [[ "$base_url" != http://* && "$base_url" != https://* ]]; then
    echo "ERROR: $label base URL is not an HTTP URL: $base_url" >&2
    return 1
  fi

  if ! curl -fsS --max-time 10 "$url" >/dev/null; then
    echo "ERROR: $label endpoint is not reachable: $url" >&2
    echo "If this is a localhost URL, attach the benchmark to the same Slurm job/node as that vLLM server." >&2
    return 1
  fi
}

if [[ "$SKIP_HEALTH_CHECKS" != "true" ]]; then
  check_endpoint "agent" "$AGENT_BASE_URL"
  check_endpoint "judge" "$JUDGE_BASE_URL"
  check_endpoint "user simulator" "$USER_BASE_URL"
fi

split_csv() {
  local csv="$1"
  csv="${csv// /}"
  IFS=',' read -r -a _split_csv_result <<< "$csv"
}

sanitize_name() {
  printf '%s' "$1" | tr '/:,' '___'
}

running_jobs=0
wait_for_slot() {
  if (( MAX_JOBS <= 1 )); then
    wait
    running_jobs=0
    return
  fi
  while (( running_jobs >= MAX_JOBS )); do
    wait -n
    running_jobs=$((running_jobs - 1))
  done
}

split_csv "$TASKS_CSV"
TASKS=("${_split_csv_result[@]}")
split_csv "$ORG_TYPES_CSV"
ORG_TYPES=("${_split_csv_result[@]}")

MODEL_SAFE="$(sanitize_name "$AGENT_MODEL")"
MODE_LABEL="single-turn"
INTERACTIVE_ARG=()
if [[ "$INTERACTIVE" == "true" ]]; then
  MODE_LABEL="multi-turn"
  INTERACTIVE_ARG=(--interactive)
fi
VERIFIER_ARG=()
VERIFIER_LABEL="noverifier"
if [[ "$USE_SYNTACTIC_VERIFIER" == "true" ]]; then
  VERIFIER_ARG=(--use_syntactic_verifier)
  VERIFIER_LABEL="syntactic_verifier"
fi
MEMORY_ARG=()
MEMORY_LABEL="nowm"
if [[ "$USE_WORKING_MEMORY" == "true" ]]; then
  MEMORY_ARG=(--use_working_memory)
  MEMORY_LABEL="wm"
fi
QUOTE_CLIPBOARD_ARG=()
QUOTE_CLIPBOARD_LABEL=""
if [[ "$USE_QUOTE_CLIPBOARD" == "true" ]]; then
  QUOTE_CLIPBOARD_ARG=(--use_quote_clipboard)
  QUOTE_CLIPBOARD_LABEL="_clipboardv2"
fi
LEAD_CLIPBOARD_ARG=()
LEAD_CLIPBOARD_LABEL=""
if [[ "$USE_LEAD_CLIPBOARD" == "true" ]]; then
  LEAD_CLIPBOARD_ARG=(--use_lead_clipboard)
  LEAD_CLIPBOARD_LABEL="_leadclipboard"
fi

for ORG_TYPE in "${ORG_TYPES[@]}"; do
  for TASK_CATEGORY in "${TASKS[@]}"; do
    FEATURE_SUFFIX="${RESULT_SUFFIX:-_${VERIFIER_LABEL}_${MEMORY_LABEL}${QUOTE_CLIPBOARD_LABEL}${LEAD_CLIPBOARD_LABEL}}"
    RESULT_DIR="results/${ORG_TYPE}_${MODE_LABEL}/${AGENT_STRATEGY}_${MODEL_SAFE}_${RUN_TAG}${FEATURE_SUFFIX}"
    LOG_DIR="logs/${ORG_TYPE}_${MODE_LABEL}/${AGENT_STRATEGY}_${MODEL_SAFE}_${RUN_TAG}${FEATURE_SUFFIX}"
    mkdir -p "$RESULT_DIR" "$LOG_DIR"
    LOG_FILE="${LOG_DIR}/run_${TASK_CATEGORY}_${EVAL_MODE}.log"

    echo "Running org=$ORG_TYPE task=$TASK_CATEGORY strategy=$AGENT_STRATEGY interactive=$INTERACTIVE"
    echo "  agent=$AGENT_MODEL @ $AGENT_BASE_URL"
    echo "  judge=$JUDGE_MODEL @ $JUDGE_BASE_URL"
    echo "  user=$USER_MODEL @ $USER_BASE_URL"
    echo "  agent_max_tokens=$AGENT_MAX_TOKENS"
    echo "  lead_dsl_extractor_max_tokens=$LEAD_DSL_EXTRACTOR_MAX_TOKENS"
    echo "  lead_dsl_disable_thinking=$LEAD_DSL_DISABLE_THINKING"
    echo "  max_tasks_per_category=$MAX_TASKS_PER_CATEGORY"
    echo "  syntactic_verifier=$USE_SYNTACTIC_VERIFIER max_verifier_retries=$MAX_VERIFIER_RETRIES"
    echo "  working_memory=$USE_WORKING_MEMORY max_chars=$WORKING_MEMORY_MAX_CHARS"
    echo "  quote_clipboard=$USE_QUOTE_CLIPBOARD max_chars=$QUOTE_CLIPBOARD_MAX_CHARS"
    echo "  lead_clipboard=$USE_LEAD_CLIPBOARD max_chars=$LEAD_CLIPBOARD_MAX_CHARS"
    echo "  routing_mode=$ROUTING_MODE routing_min_confidence=$ROUTING_MIN_CONFIDENCE"
    echo "  scaffold_mode=$SCAFFOLD_MODE"
    echo "  log=$LOG_FILE"

    "$PYTHON_BIN" -u run_tasks.py \
      --model "$AGENT_MODEL" \
      --task_category "$TASK_CATEGORY" \
      --agent_eval_mode "$EVAL_MODE" \
      --log_dir "$RESULT_DIR" \
      --agent_strategy "$AGENT_STRATEGY" \
      "${INTERACTIVE_ARG[@]}" \
      --llm_provider "$AGENT_PROVIDER" \
      --judge_model "$JUDGE_MODEL" \
      --judge_provider "$JUDGE_PROVIDER" \
      --judge_base_url "$JUDGE_BASE_URL" \
      --judge_api_key "$JUDGE_API_KEY" \
      --user_model "$USER_MODEL" \
      --user_provider "$USER_PROVIDER" \
      --user_base_url "$USER_BASE_URL" \
      --user_api_key "$USER_API_KEY" \
      --max_turns "$MAX_TURNS" \
      --max_user_turns "$MAX_USER_TURNS" \
      --max_tasks_per_category "$MAX_TASKS_PER_CATEGORY" \
      --agent_max_tokens "$AGENT_MAX_TOKENS" \
      --max_verifier_retries "$MAX_VERIFIER_RETRIES" \
      --working_memory_max_chars "$WORKING_MEMORY_MAX_CHARS" \
      --quote_clipboard_max_chars "$QUOTE_CLIPBOARD_MAX_CHARS" \
      --lead_clipboard_max_chars "$LEAD_CLIPBOARD_MAX_CHARS" \
      --routing_mode "$ROUTING_MODE" \
      --routing_min_confidence "$ROUTING_MIN_CONFIDENCE" \
      --scaffold_mode "$SCAFFOLD_MODE" \
      "${VERIFIER_ARG[@]}" \
      "${MEMORY_ARG[@]}" \
      "${QUOTE_CLIPBOARD_ARG[@]}" \
      "${LEAD_CLIPBOARD_ARG[@]}" \
      --reuse_results \
      --privacy_aware_prompt "$PRIVACY_AWARE_PROMPT" \
      --org_type "$ORG_TYPE" > "$LOG_FILE" 2>&1 &

    running_jobs=$((running_jobs + 1))
    wait_for_slot
  done
done

wait
