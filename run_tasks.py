from dotenv import load_dotenv
import json, os
from crm_sandbox.agents import ChatAgent, ChatAgentDSL, ChatAgentGeneralRuntimeDSL, ToolCallAgent
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
    if args.agent_strategy in ("lead_dsl", "general_dsl"):
        print(f"DSL model-output retries: {args.max_dsl_retries}")
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
    
    if args.agent_strategy in ["act", "react", "lead_dsl", "general_dsl"]:
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
        if args.agent_strategy in ["react", "lead_dsl", "general_dsl"]:
            agent_cls = ChatAgent
            if args.agent_strategy == "lead_dsl":
                agent_cls = ChatAgentDSL
            elif args.agent_strategy == "general_dsl":
                agent_cls = ChatAgentGeneralRuntimeDSL
            dsl_options = {"max_dsl_retries": args.max_dsl_retries} if agent_cls is not ChatAgent else {}
            agent = agent_cls(
                model=agent_model,
                schema_obj=SCHEMA,
                eval_mode=args.agent_eval_mode,
                max_turns=args.max_turns,
                strategy="react" if args.agent_strategy in ["lead_dsl", "general_dsl"] else args.agent_strategy,
                provider=args.llm_provider,
                interactive=args.interactive,
                agent_type=agent_type,
                privacy_aware_prompt=args.privacy_aware_prompt,
                agent_max_tokens=args.agent_max_tokens,
                scaffold_text=scaffold_text,
                routing_result=routing_result.as_dict(),
                **dsl_options,
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


def build_parser(show_all=False):
    parser = argparse.ArgumentParser(description="Run CRMArena or CRMArena-Pro evaluations.")
    parser.add_argument(
        "--help-all",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Show advanced options for ablations, providers, and checkpoints.",
    )
    parser.add_argument("--model", default="o1-mini", help="Agent model name.")
    parser.add_argument(
        "--llm_provider",
        default="bedrock",
        choices=PROVIDER_CHOICES,
        metavar=None if show_all else "PROVIDER",
        help="Agent provider, such as openai or claude_cli.",
    )
    parser.add_argument(
        "--agent_strategy",
        default="react",
        choices=["tool_call", "act", "react", "lead_dsl", "general_dsl", "tool_call_flex"],
        metavar=None if show_all else "STRATEGY",
        help="Use general_dsl for the workflow harness. Defaults to react.",
    )
    parser.add_argument(
        "--org_type",
        default="b2b",
        choices=["b2b", "b2c", "original"],
        help="Salesforce benchmark org (default: b2b).",
    )
    task_help = "Task category or comma-separated list. Defaults to all categories."
    if show_all:
        task_help += " Options include default_focus and " + ", ".join(TASK_CATEGORY_CHOICES) + "."
    else:
        task_help += " For example, knowledge_qa. See --help-all for the full list."
    parser.add_argument("--task_category", default="all", help=task_help)
    parser.add_argument("--interactive", action="store_true", help="Enable multi-turn user simulation.")
    parser.add_argument(
        "--max_tasks_per_category",
        type=int,
        default=0,
        help="Cap examples per category for smoke tests. Zero runs all selected examples.",
    )
    parser.add_argument("--log_dir", default="logs", help="Directory for result JSON files (default: logs).")
    parser.add_argument("--reuse_results", action="store_true", help="Resume from an existing results file.")
    parser.add_argument(
        "--judge_provider",
        choices=PROVIDER_CHOICES,
        metavar=None if show_all else "PROVIDER",
        help="Judge provider. Defaults to the agent provider.",
    )
    parser.add_argument(
        "--judge_model",
        help="Judge model override. Uses the provider default or the agent model when omitted.",
    )

    advanced = parser.add_argument_group("advanced options")

    def add_advanced(*flags, **kwargs):
        if not show_all:
            kwargs["help"] = argparse.SUPPRESS
        advanced.add_argument(*flags, **kwargs)

    add_advanced(
        "--agent_eval_mode",
        default="default",
        choices=["default", "aided"],
        help="Select the benchmark prompt mode.",
    )
    add_advanced("--judge_base_url", help="OpenAI-compatible base URL for the judge.")
    add_advanced("--judge_api_key", help="API key for the judge.")
    add_advanced(
        "--user_provider",
        choices=PROVIDER_CHOICES,
        help="Interactive user provider. Defaults to the judge provider.",
    )
    add_advanced(
        "--user_model",
        help="Interactive user model override. Uses the provider default or the judge model when omitted.",
    )
    add_advanced("--user_base_url", help="OpenAI-compatible base URL for the interactive user.")
    add_advanced("--user_api_key", help="API key for the interactive user.")
    add_advanced(
        "--task_ids",
        default="",
        help="Comma-separated task IDs to run within the selected org and categories.",
    )
    add_advanced(
        "--rerun_task_ids",
        action="store_true",
        help="With --reuse_results and --task_ids, replace matching checkpoint rows.",
    )
    add_advanced("--max_turns", type=int, default=20, help="Maximum agent turns.")
    add_advanced("--max_user_turns", type=int, default=10, help="Maximum simulated user turns.")
    add_advanced("--agent_max_tokens", type=int, default=1024, help="Maximum requested output tokens per ReAct step.")
    add_advanced("--max_dsl_retries", type=int, default=3, help="Retry cap for DSL routing and extraction responses.")
    add_advanced(
        "--routing_mode",
        default="deterministic",
        choices=["none", "deterministic"],
        help="Select the optional prompt-scaffold router.",
    )
    add_advanced(
        "--routing_min_confidence",
        type=float,
        default=0.55,
        help="Minimum confidence for the prompt-scaffold router.",
    )
    add_advanced(
        "--scaffold_mode",
        default="routed",
        choices=["none", "task", "routed"],
        help="Select a prompt scaffold by benchmark category (task) or router prediction (routed).",
    )
    add_advanced(
        "--privacy_aware_prompt",
        type=lambda value: {"true": True, "false": False}[value.lower()],
        default=True,
        help="Use the privacy-aware ReAct prompt. Accepts true or false.",
    )
    return parser


if __name__ == "__main__":
    load_dotenv()
    args = build_parser().parse_args()
    if getattr(args, "help_all", False):
        build_parser(show_all=True).print_help()
    else:
        print(_redacted_args(args))
        run()
