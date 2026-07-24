import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crm_sandbox.data.assets import (
    TASKS_B2B,
    TASKS_B2B_INTERACTIVE,
    TASKS_B2C,
    TASKS_B2C_INTERACTIVE,
    TASKS_ORIGINAL,
)
from crm_sandbox.orchestration import expected_family_from_task_label, route_task


DEFAULT_FOCUS_TASKS = [
    "quote_approval",
    "lead_qualification",
    "case_routing",
    "private_customer_information",
    "internal_operation_data",
    "confidential_company_knowledge",
]


def task_source(org_type: str, interactive: bool) -> list[dict]:
    if org_type == "b2b":
        return TASKS_B2B_INTERACTIVE if interactive else TASKS_B2B
    if org_type == "b2c":
        return TASKS_B2C_INTERACTIVE if interactive else TASKS_B2C
    return TASKS_ORIGINAL


def selected_tasks(tasks: Iterable[dict], task_category: str) -> list[dict]:
    if task_category == "default_focus":
        wanted = set(DEFAULT_FOCUS_TASKS)
    elif task_category == "all":
        wanted = None
    else:
        wanted = {item.strip() for item in task_category.split(",") if item.strip()}
    return [task for task in tasks if wanted is None or task.get("task") in wanted]


def visible_metadata(task: dict, eval_mode: str) -> dict:
    metadata = task.get("metadata", {})
    if not isinstance(metadata, dict):
        return {}
    if eval_mode == "aided":
        return metadata
    return {"required": metadata.get("required", "")}


def markdown_table(title: str, rows: list[dict], fields: list[str]) -> str:
    if not rows:
        return f"## {title}\n\nNo rows.\n"
    lines = [f"## {title}", "", "| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze deterministic CRMArena orchestration routing alignment.")
    parser.add_argument("--org_type", choices=["b2b", "b2c", "original"], default="b2b")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--agent_eval_mode", choices=["default", "aided"], default="default")
    parser.add_argument(
        "--task_category",
        default="default_focus",
        help="Use all, default_focus, or a comma-separated task subset.",
    )
    parser.add_argument("--routing_min_confidence", type=float, default=0.55)
    parser.add_argument("--md", type=Path, default=None, help="Optional Markdown report path.")
    args = parser.parse_args()

    tasks = selected_tasks(task_source(args.org_type, args.interactive), args.task_category)
    matrix = Counter()
    by_task = defaultdict(Counter)
    misses = []
    total = 0
    correct = 0

    for task in tasks:
        gold_task = task.get("task", "")
        expected = expected_family_from_task_label(gold_task)
        result = route_task(
            query=task.get("query", ""),
            metadata=visible_metadata(task, args.agent_eval_mode),
            oracle_task_label=gold_task,
            mode="deterministic",
            min_confidence=args.routing_min_confidence,
        )
        total += 1
        is_correct = result.task_family == expected
        correct += int(is_correct)
        matrix[(gold_task, result.task_family)] += 1
        by_task[gold_task]["total"] += 1
        by_task[gold_task]["correct"] += int(is_correct)
        by_task[gold_task]["general_fallback"] += int(result.task_family == "general")
        if not is_correct and len(misses) < 25:
            misses.append(
                {
                    "idx": task.get("idx", ""),
                    "task": gold_task,
                    "expected_family": expected,
                    "predicted_family": result.task_family,
                    "confidence": f"{result.confidence:.2f}",
                    "evidence": ", ".join(result.evidence),
                    "query": str(task.get("query", ""))[:160].replace("\n", " "),
                }
            )

    accuracy = correct / total if total else 0.0
    print(f"tasks={total} correct={correct} accuracy={accuracy:.4f}")

    task_rows = []
    for task_name, counts in sorted(by_task.items()):
        task_total = counts["total"]
        task_rows.append(
            {
                "task": task_name,
                "total": task_total,
                "correct": counts["correct"],
                "accuracy": f"{counts['correct'] / task_total:.4f}" if task_total else "0.0000",
                "general_fallback": counts["general_fallback"],
            }
        )
    for row in task_rows:
        print(row)

    matrix_rows = [
        {"task": task, "predicted_family": family, "count": count}
        for (task, family), count in sorted(matrix.items())
    ]

    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        report = [
            "# Routing Analysis",
            "",
            f"- org_type: `{args.org_type}`",
            f"- interactive: `{args.interactive}`",
            f"- agent_eval_mode: `{args.agent_eval_mode}`",
            f"- task_category: `{args.task_category}`",
            f"- routing_min_confidence: `{args.routing_min_confidence}`",
            f"- tasks: `{total}`",
            f"- correct: `{correct}`",
            f"- accuracy: `{accuracy:.4f}`",
            "",
            markdown_table("By Task", task_rows, ["task", "total", "correct", "accuracy", "general_fallback"]),
            markdown_table("Confusion Counts", matrix_rows, ["task", "predicted_family", "count"]),
            markdown_table("Example Misses", misses, ["idx", "task", "expected_family", "predicted_family", "confidence", "evidence", "query"]),
        ]
        args.md.write_text("\n".join(report))
        print(f"Wrote Markdown report: {args.md}")


if __name__ == "__main__":
    main()
