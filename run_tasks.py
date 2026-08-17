from dotenv import load_dotenv
import json, os
from crm_sandbox.agents import ChatAgent, ChatAgentDSL, ChatAgentEWM, ChatAgentGeneralRuntimeDSL, ToolCallAgent
from crm_sandbox.agents.utils import BEDROCK_MODELS_MAP, TOGETHER_MODELS_MAP, VERTEX_MODELS_MAP
from crm_sandbox.data.assets import TASKS_ORIGINAL, SCHEMA_ORIGINAL, TASKS_B2B, TASKS_B2B_INTERACTIVE, TASKS_B2C, TASKS_B2C_INTERACTIVE, B2B_SCHEMA, B2C_SCHEMA, EXTERNAL_FACING_TASKS
from crm_sandbox.env.env import ChatEnv, ToolEnv, InteractiveChatEnv
from crm_sandbox.env import TOOLS, TOOLS_FULL
from crm_sandbox.model_client import default_model_for_provider, normalize_model_for_provider
from crm_sandbox.orchestration import route_task, scaffold_for_family, scaffold_for_task
import traceback
import argparse
from datetime import datetime
import time


DEFAULT_FOCUS_TASKS = [
    "quote_approval",
    "lead_qualification",
    "case_routing",
    "private_customer_information",
    "internal_operation_data",
    "confidential_company_knowledge",
]

TASK_CATEGORY_CHOICES = [
    "handle_time", "transfer_count", "knowledge_qa", "best_region_identification",
    "case_routing", "named_entity_disambiguation", "policy_violation_identification",
    "top_issue_identification", "monthly_trend_analysis",
    "sales_amount_understanding", "lead_routing", "sales_cycle_understanding",
    "conversion_rate_comprehension", "wrong_stage_rectification", "sales_insight_mining",
    "quote_approval", "lead_qualification", "activity_priority", "invalid_config",
    "private_customer_information", "internal_operation_data", "confidential_company_knowledge",
    "all",
]

PROVIDER_CHOICES = ["bedrock", "together_ai", "openai", "vertex_ai", "openrouter", "claude_cli", "codex_cli"]


def _resolve_model_for_provider(explicit_model, fallback_model, provider):
    if explicit_model:
        return normalize_model_for_provider(explicit_model, provider)
    provider_default = default_model_for_provider(provider, None)
    if provider_default:
        return normalize_model_for_provider(provider_default, provider)
    return fallback_model


def _is_success_reward(reward):
    if reward == 1 or reward == 1.0 or reward is True:
        return True
    if isinstance(reward, dict):
        return bool(reward.get("em"))
    return False


def _redacted_args(args):
    redacted = vars(args).copy()
    for key in ("judge_api_key", "user_api_key"):
        if redacted.get(key):
            redacted[key] = "<redacted>"
    return argparse.Namespace(**redacted)


def _sum_optional_numbers(values):
    total = 0.0
    found = False
    for value in values or []:
        if isinstance(value, (int, float)):
            total += value
            found = True
    return total if found else None


def _result_metrics(agent_info, task_wall_time_seconds):
    if not isinstance(agent_info, dict):
        return {"task_wall_time_seconds": task_wall_time_seconds}
    usage = agent_info.get("usage") or {}
    total_cost = agent_info.get("total_cost")
    if isinstance(usage, dict) and "cost" in usage:
        total_cost = _sum_optional_numbers(usage.get("cost"))
    metrics = {
        "time_to_resolution_seconds": agent_info.get("time_to_resolution_seconds"),
        "task_wall_time_seconds": task_wall_time_seconds,
        "model_calls": agent_info.get("model_calls"),
        "env_steps": agent_info.get("env_steps"),
        "usage": usage,
        "total_cost": total_cost,
    }
    if isinstance(usage, dict):
        metrics["total_prompt_tokens"] = _sum_optional_numbers(usage.get("prompt_tokens"))
        metrics["total_completion_tokens"] = _sum_optional_numbers(usage.get("completion_tokens"))
        metrics["total_tokens"] = _sum_optional_numbers(usage.get("total_tokens"))
    return metrics


def _safe_agent_messages(agent):
    try:
        return agent.get_messages()
    except Exception as exc:
        return [
            {
                "role": "system",
                "content": "Trajectory unavailable because the task failed before agent messages were initialized: "
                + str(exc),
            }
        ]


def run():
    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir)
    judge_provider = args.judge_provider or args.llm_provider
    user_provider = args.user_provider or judge_provider
    agent_model = normalize_model_for_provider(args.model, args.llm_provider)
    judge_model = _resolve_model_for_provider(args.judge_model, agent_model, judge_provider)
    user_model = _resolve_model_for_provider(args.user_model, judge_model, user_provider)
    ckpt_path = f"{args.log_dir}/results_{agent_model}_{args.agent_strategy}_{args.task_category}.json"
    os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
    print(f"Judge model/provider: {judge_model} / {judge_provider}")
    if args.judge_base_url:
        print(f"Judge base URL: {args.judge_base_url}")
    print(f"Agent max output tokens: {args.agent_max_tokens}")
    print(f"Syntactic verifier: {args.use_syntactic_verifier} (max retries={args.max_verifier_retries})")
    print(f"Working memory: {args.use_working_memory} (max chars={args.working_memory_max_chars})")
    print(f"Quote clipboard v2: {args.use_quote_clipboard} (max chars={args.quote_clipboard_max_chars})")
    print(f"Lead clipboard: {args.use_lead_clipboard} (max chars={args.lead_clipboard_max_chars})")
    print(f"Routing mode: {args.routing_mode} (min confidence={args.routing_min_confidence})")
    print(f"Scaffold mode: {args.scaffold_mode}")
    if args.interactive:
        print(f"User simulator model/provider: {user_model} / {user_provider}")
        if args.user_base_url:
            print(f"User simulator base URL: {args.user_base_url}")
    if args.org_type == "b2b":
        TASKS_NATURAL = TASKS_B2B_INTERACTIVE if args.interactive else TASKS_B2B
        SCHEMA = B2B_SCHEMA
    elif args.org_type == "b2c":
        TASKS_NATURAL = TASKS_B2C_INTERACTIVE if args.interactive else TASKS_B2C
        SCHEMA = B2C_SCHEMA
    else:
        # the original CRMArena
        TASKS_NATURAL = TASKS_ORIGINAL
        SCHEMA = SCHEMA_ORIGINAL
    
    if args.task_category == "default_focus":
        requested_tasks = DEFAULT_FOCUS_TASKS
        selected_tasks = [task for task in TASKS_NATURAL if task["task"] in requested_tasks]
    elif args.task_category == "all":
        selected_tasks = TASKS_NATURAL
    elif "," in args.task_category:
        requested_tasks = [task.strip() for task in args.task_category.split(",") if task.strip()]
        invalid_tasks = sorted(set(requested_tasks) - set(TASK_CATEGORY_CHOICES))
        if invalid_tasks:
            raise ValueError(f"Unsupported task categories: {', '.join(invalid_tasks)}")
        selected_tasks = [task for task in TASKS_NATURAL if task["task"] in requested_tasks]
    else:
        if args.task_category not in TASK_CATEGORY_CHOICES:
            raise ValueError(f"Unsupported task category: {args.task_category}")
        selected_tasks = [task for task in TASKS_NATURAL if task["task"] == args.task_category]

    requested_task_ids = None
    if args.task_ids:
        requested_task_ids = {
            int(task_id.strip())
            for task_id in args.task_ids.split(",")
            if task_id.strip()
        }
        selected_ids = {task["idx"] for task in selected_tasks}
        missing_requested = sorted(requested_task_ids - selected_ids)
        if missing_requested:
            print(f"Warning: requested task_ids not selected by org/category filters: {missing_requested}")
        selected_tasks = [task for task in selected_tasks if task["idx"] in requested_task_ids]

    if args.max_tasks_per_category > 0:
        capped_tasks = []
        category_counts = {}
        for task in selected_tasks:
            task_name = task["task"]
            count = category_counts.get(task_name, 0)
            if count >= args.max_tasks_per_category:
                continue
            capped_tasks.append(task)
            category_counts[task_name] = count + 1
        selected_tasks = capped_tasks
        
    # Load checkpoint if it exists
    completed_tasks = {}
    
    if os.path.exists(ckpt_path):
        if args.reuse_results:
            with open(ckpt_path, 'r') as f:
                data_res = json.load(f)
            if args.rerun_task_ids and requested_task_ids:
                before_count = len(data_res)
                data_res = [
                    task for task in data_res
                    if task.get("task_id") not in requested_task_ids
                ]
                removed_count = before_count - len(data_res)
                if removed_count:
                    with open(ckpt_path, "w") as f:
                        json.dump(data_res, f, indent=2)
                    print(f"Removed {removed_count} existing checkpoint rows for requested rerun task_ids")
            completed_tasks = {task['task_id']: task for task in data_res}
        else:
            os.remove(ckpt_path)
            
    print(f"Loaded {len(selected_tasks)} tasks")
    if args.max_tasks_per_category > 0:
        print(f"Max tasks per category: {args.max_tasks_per_category}")
    start_time = datetime.now()
    print(f"Starting evaluation at {start_time}")
    selected_tasks = {t['idx']: t for t in selected_tasks}
    
    if args.agent_strategy in ["act", "react", "lead_dsl", "general_dsl", "ewm"]:
        if args.interactive:
            if args.agent_strategy == "act":
                raise ValueError(
                    "Interactive mode is only supported for the 'react' strategy. "
                    "'act' strategy cannot be used with --interactive."
                )
            # This implies agent_strategy is "react" if interactive is True
            
            env = InteractiveChatEnv(
                tasks=selected_tasks,
                max_user_turns=args.max_user_turns,
                org_type=args.org_type,
                user_model=user_model,
                user_provider=user_provider,
                evaluator_model=judge_model,
                evaluator_provider=judge_provider,
                user_base_url=args.user_base_url,
                user_api_key=args.user_api_key,
                evaluator_base_url=args.judge_base_url,
                evaluator_api_key=args.judge_api_key,
            )
        else: # Not interactive, both 'act' and 'react' are fine
            env = ChatEnv(
                tasks=selected_tasks,
                org_type=args.org_type,
                evaluator_model=judge_model,
                evaluator_provider=judge_provider,
                evaluator_base_url=args.judge_base_url,
                evaluator_api_key=args.judge_api_key,
            )
    elif args.agent_strategy == "tool_call":
        if args.interactive:
            raise NotImplementedError(
                f"Interactive mode is not supported for the '{args.agent_strategy}' strategy."
            )
        if args.org_type != "original":
            raise NotImplementedError(
                f"The '{args.agent_strategy}' strategy is only supported for the 'original' org_type (CRMArena), "
                f"not '{args.org_type}'."
            )
        env = ToolEnv(tools=TOOLS, tasks=selected_tasks, org_type=args.org_type)
    elif args.agent_strategy == "tool_call_flex":
        if args.interactive:
            raise NotImplementedError(
                f"Interactive mode is not supported for the '{args.agent_strategy}' strategy."
            )
        if args.org_type != "original":
            raise NotImplementedError(
                f"The '{args.agent_strategy}' strategy is only supported for the 'original' org_type (CRMArena), "
                f"not '{args.org_type}'."
            )
        env = ToolEnv(tools=TOOLS_FULL, tasks=selected_tasks, org_type=args.org_type)
    else:
        # Fallback for unknown strategies, though argparse choices should prevent this.
        raise ValueError(f"Unsupported agent_strategy: {args.agent_strategy}")
    for idx, task in selected_tasks.items():
        # Skip tasks that have already been completed
        if idx in completed_tasks:
            print(f"Skipping task {idx} (already completed)")
            continue
        if task["task"] in EXTERNAL_FACING_TASKS:
            agent_type = "external"
        else:
            agent_type = "internal"
        task_metadata = task.get("metadata", {})
        routing_metadata = task_metadata
        if isinstance(task_metadata, dict) and args.agent_eval_mode != "aided":
            routing_metadata = {"required": task_metadata.get("required", "")}
        routing_result = route_task(
            query=task.get("query", ""),
            metadata=routing_metadata,
            oracle_task_label=task.get("task"),
            mode=args.routing_mode,
            min_confidence=args.routing_min_confidence,
        )
        scaffold_text = ""
        scaffold_source = "none"
        if args.scaffold_mode == "task":
            scaffold_text = scaffold_for_task(task.get("task", ""))
            scaffold_source = task.get("task", "unknown")
        elif args.scaffold_mode == "routed":
            scaffold_text = scaffold_for_family(routing_result.task_family)
            scaffold_source = routing_result.task_family
        if args.routing_mode != "none" or args.scaffold_mode != "none":
            print(
                "Routing:",
                f"predicted={routing_result.task_family}",
                f"confidence={routing_result.confidence:.2f}",
                f"oracle={task.get('task')}",
                f"scaffold={routing_result.scaffold_used}",
                f"scaffold_mode={args.scaffold_mode}",
                f"scaffold_source={scaffold_source}",
                f"evidence={routing_result.evidence}",
            )
        if args.agent_strategy in ["react", "lead_dsl", "general_dsl", "ewm"]:
            agent_cls = ChatAgent
            if args.agent_strategy == "lead_dsl":
                agent_cls = ChatAgentDSL
            elif args.agent_strategy == "general_dsl":
                agent_cls = ChatAgentGeneralRuntimeDSL
            elif args.agent_strategy == "ewm":
                agent_cls = ChatAgentEWM
            agent = agent_cls(
                model=agent_model,
                schema_obj=SCHEMA,
                eval_mode=args.agent_eval_mode,
                max_turns=args.max_turns,
                strategy="react" if args.agent_strategy in ["lead_dsl", "general_dsl", "ewm"] else args.agent_strategy,
                provider=args.llm_provider,
                interactive=args.interactive,
                agent_type=agent_type,
                privacy_aware_prompt=args.privacy_aware_prompt,
                use_syntactic_verifier=args.use_syntactic_verifier,
                max_verifier_retries=args.max_verifier_retries,
                agent_max_tokens=args.agent_max_tokens,
                scaffold_text=scaffold_text,
                routing_result=routing_result.as_dict(),
                use_working_memory=args.use_working_memory,
                working_memory_max_chars=args.working_memory_max_chars,
                use_quote_clipboard=args.use_quote_clipboard,
                quote_clipboard_active=task["task"] == "quote_approval",
                quote_clipboard_max_chars=args.quote_clipboard_max_chars,
                use_lead_clipboard=args.use_lead_clipboard,
                lead_clipboard_active=task["task"] == "lead_qualification",
                lead_clipboard_max_chars=args.lead_clipboard_max_chars,
            )
            agent.info["scaffold_mode"] = args.scaffold_mode
            agent.info["scaffold_source"] = scaffold_source
        else:
            
            agent = ToolCallAgent(
                model=agent_model,
                tools=env.tools_info,
                schema_obj=SCHEMA,
                eval_mode=args.agent_eval_mode,
                max_turns=args.max_turns,
                strategy=args.agent_strategy,
                provider=args.llm_provider
            )
        print(f"Running task {idx}")
        task_wall_start = time.perf_counter()
        try:
            reward = agent.act(
                env,
                idx
            )
            agent_info = agent.info
            result = {
                "task_id": idx,
                "task_type": task["task"],
                "gt_answer": task["answer"],
                "reward": reward,
                "routing": routing_result.as_dict(),
                "scaffold_mode": args.scaffold_mode,
                "scaffold_source": scaffold_source,
                "quote_clipboard_enabled": args.use_quote_clipboard,
                "lead_clipboard_enabled": args.use_lead_clipboard,
                "agent_info": agent_info,
                "traj": _safe_agent_messages(agent),
            }
        except Exception as e:
            traceback.print_exc()
            agent_info = {
                "source": "api",
                "content": "Error: " + str(e)
            }
            result = {
                "task_id": idx,
                "task_type": task["task"],
                "gt_answer": task["answer"],
                "reward": 0,
                "routing": routing_result.as_dict(),
                "scaffold_mode": args.scaffold_mode,
                "scaffold_source": scaffold_source,
                "quote_clipboard_enabled": args.use_quote_clipboard,
                "lead_clipboard_enabled": args.use_lead_clipboard,
                "agent_info": agent_info,
                "traj": _safe_agent_messages(agent),
            }
        result.update(_result_metrics(agent_info, time.perf_counter() - task_wall_start))
        print(
            "✅" if _is_success_reward(result["reward"]) else "❌",
            f"task_id={idx}"
        )
        print("-----")
        data_res = []
        if os.path.exists(ckpt_path):
            with open(ckpt_path, "r") as f:
                data_res = json.load(f)
        with open(ckpt_path, "w") as f:
            json.dump(data_res + [result], f, indent=2)
        time.sleep(1)
    end_time = datetime.now()
    print(f"Finished evaluation at {end_time}")
    
if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=str,
        help="The model to use for the agent",
        default="o1-mini",
        choices = ["o1-mini", "gpt-4o", "gpt-4-turbo"].extend(BEDROCK_MODELS_MAP.keys()),
    )
    parser.add_argument(
        "--agent_strategy",
        type=str,
        default="react",
        choices=["tool_call", "act", "react", "lead_dsl", "general_dsl", "ewm", "tool_call_flex"],
    )
    parser.add_argument(
        "--agent_eval_mode",
        type=str,
        default="default",
        choices=["default", "aided"],
    )
    parser.add_argument(
        "--llm_provider",
        type=str,
        default="bedrock",
        choices=PROVIDER_CHOICES
    )
    parser.add_argument(
        "--judge_model",
        type=str,
        default=None,
        help="Model used by evaluator/judge calls. Defaults to --model.",
    )
    parser.add_argument(
        "--judge_provider",
        type=str,
        default=None,
        choices=PROVIDER_CHOICES,
        help="LiteLLM provider for evaluator/judge calls. Defaults to --llm_provider.",
    )
    parser.add_argument(
        "--judge_base_url",
        type=str,
        default=None,
        help="Optional OpenAI-compatible base URL for evaluator/judge calls.",
    )
    parser.add_argument(
        "--judge_api_key",
        type=str,
        default=None,
        help="Optional API key for evaluator/judge calls.",
    )
    parser.add_argument(
        "--user_model",
        type=str,
        default=None,
        help="Model used for interactive CRMArena-Pro user simulation. Defaults to --judge_model or --model.",
    )
    parser.add_argument(
        "--user_provider",
        type=str,
        default=None,
        choices=PROVIDER_CHOICES,
        help="LiteLLM provider for interactive user simulation. Defaults to --judge_provider or --llm_provider.",
    )
    parser.add_argument(
        "--user_base_url",
        type=str,
        default=None,
        help="Optional OpenAI-compatible base URL for interactive user simulation calls.",
    )
    parser.add_argument(
        "--user_api_key",
        type=str,
        default=None,
        help="Optional API key for interactive user simulation calls.",
    )
    parser.add_argument(
        "--task_category",
        type=str,
        default="all",
        help=f"The category of tasks to evaluate. Use 'all', 'default_focus', or a comma-separated subset from: {', '.join(TASK_CATEGORY_CHOICES)}",
    )
    parser.add_argument(
        "--max_tasks_per_category",
        type=int,
        default=0,
        help="Optional cap for smoke tests. 0 means run all selected examples.",
    )
    parser.add_argument(
        "--task_ids",
        type=str,
        default="",
        help="Optional comma-separated task idx values to run after org/category filtering.",
    )
    parser.add_argument(
        "--rerun_task_ids",
        action="store_true",
        help="With --reuse_results and --task_ids, remove matching checkpoint rows before rerunning them.",
    )
    parser.add_argument(
        "--max_turns",
        type=int,
        default=20
    )
    parser.add_argument(
        "--max_user_turns",
        type=int,
        default=10
    )
    parser.add_argument(
        "--agent_max_tokens",
        type=int,
        default=1024,
        help="Maximum output tokens requested from the agent model per ReAct step.",
    )
    parser.add_argument(
        "--use_syntactic_verifier",
        action="store_true",
        help="Gate parsed ReAct actions with a deterministic SOQL/SOSL verifier before env.step.",
    )
    parser.add_argument(
        "--max_verifier_retries",
        type=int,
        default=3,
        help="Internal verifier repair calls allowed before ending the task.",
    )
    parser.add_argument(
        "--use_working_memory",
        action="store_true",
        help="Inject a compact deterministic working-memory state block once per ReAct model prompt.",
    )
    parser.add_argument(
        "--working_memory_max_chars",
        type=int,
        default=1200,
        help="Maximum characters in the injected working-memory state block.",
    )
    parser.add_argument(
        "--use_quote_clipboard",
        action="store_true",
        help="Enable quote-approval-only procedural clipboard v2 and response gate.",
    )
    parser.add_argument(
        "--quote_clipboard_max_chars",
        type=int,
        default=1000,
        help="Maximum characters in the injected quote approval clipboard block.",
    )
    parser.add_argument(
        "--use_lead_clipboard",
        action="store_true",
        help="Enable lead-qualification-only procedural BANT evidence clipboard.",
    )
    parser.add_argument(
        "--lead_clipboard_max_chars",
        type=int,
        default=1000,
        help="Maximum characters in the injected lead qualification clipboard block.",
    )
    parser.add_argument(
        "--routing_mode",
        type=str,
        default="deterministic",
        choices=["none", "deterministic"],
        help=(
            "Optional orchestration router. 'deterministic' uses visible query/metadata only; "
            "'none' preserves the base CRMArena harness."
        ),
    )
    parser.add_argument(
        "--routing_min_confidence",
        type=float,
        default=0.55,
        help="Minimum deterministic routing confidence before falling back to the confidentiality scaffold.",
    )
    parser.add_argument(
        "--scaffold_mode",
        type=str,
        default="routed",
        choices=["none", "task", "routed"],
        help=(
            "Optional prompt scaffold injection. 'task' uses the selected benchmark task category; "
            "'routed' uses the visible-input router prediction; 'none' preserves the base prompt."
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive mode"
    )
    parser.add_argument(
        "--org_type",
        type=str,
        default="b2b",
        choices=["b2b", "b2c", "original"] # original is the original CRMArena
    )
    parser.add_argument(
        "--reuse_results",
        action="store_true",
        help="Reuse results from previous runs"
    )
    parser.add_argument(
        "--privacy_aware_prompt",
        type=lambda x: {'true': True, 'false': False}[x.lower()],
        default=True,
        help="Whether to use a privacy-aware prompt. Accepts 'true' or 'false'. (default: %(default)s)"
    )
    parser.add_argument("--log_dir", type=str, default="logs")
    args = parser.parse_args()
    print(_redacted_args(args))

    run()
    
