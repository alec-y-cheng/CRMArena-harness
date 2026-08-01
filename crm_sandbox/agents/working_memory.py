import ast
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Optional


DEFAULT_NEXT_GOAL = {
    "lead_qualification": "Resolve the remaining qualification criteria with the latest available evidence.",
    "quote_approval": "Find policy evidence and quote line details needed for the approval decision.",
    "case_routing": "Find evidence about similar cases, agent ownership, and routing constraints.",
    "conversion_rate_comprehension": "Collect the records needed to compute the requested conversion rate.",
    "confidentiality": "Answer only if the request is authorized and does not disclose protected information.",
}


@dataclass
class WorkingMemoryState:
    task_family: str = "unknown"
    goal: str = ""
    known: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    failed_queries: List[str] = field(default_factory=list)
    next_goal: str = ""

    def as_dict(self) -> dict:
        return {
            "task_family": self.task_family,
            "goal": self.goal,
            "known": list(self.known),
            "unknown": list(self.unknown),
            "failed_queries": list(self.failed_queries),
            "next_goal": self.next_goal,
        }


class WorkingMemory:
    """Compact procedural memory derived from visible task state and prior actions."""

    def __init__(self, max_chars: int = 1200, max_items: int = 5) -> None:
        self.max_chars = max(300, max_chars)
        self.max_items = max(2, max_items)
        self.state = WorkingMemoryState()

    def reset(self, query: str, routing_result: Optional[Mapping[str, Any]] = None) -> None:
        task_family = "unknown"
        if isinstance(routing_result, Mapping):
            task_family = str(routing_result.get("task_family") or "unknown")
        self.state = WorkingMemoryState(
            task_family=task_family,
            goal=self._compact(query, 220),
            known=[],
            unknown=self._initial_unknowns(query, task_family),
            failed_queries=[],
            next_goal=DEFAULT_NEXT_GOAL.get(task_family, "Find the next piece of evidence needed to answer correctly."),
        )

    def record_verifier_failure(self, action: Optional[Mapping[str, str]], error_code: Optional[str]) -> None:
        if action and action.get("name") == "execute":
            self.add_failed_query(str(action.get("content", "")))
        if error_code:
            self._append_unique(self.state.known, f"Verifier rejected last action: {error_code}")
        self.state.next_goal = "Revise the action using the verifier feedback before querying again."
        self._trim()

    def record_env_step(self, action: Mapping[str, str], observation: Any, info: Optional[Mapping[str, Any]] = None) -> None:
        info = info or {}
        action_name = str(action.get("name", ""))
        content = str(action.get("content", "")).strip()
        end_reason = info.get("end_reason") if isinstance(info, Mapping) else None

        if action_name == "execute" and isinstance(end_reason, Mapping):
            message = str(end_reason.get("message", "query failed"))
            self.add_failed_query(content)
            self._append_unique(self.state.known, f"Last query failed: {message}")
            self.state.next_goal = "Change the query; do not repeat the failed query exactly."
        elif action_name == "execute":
            self._append_unique(self.state.known, self._observation_summary(observation))
            self.state.next_goal = "Use the returned evidence to answer, or query only the missing evidence."
        elif action_name == "respond":
            self._append_unique(self.state.known, "Final response submitted to the user.")
            self.state.unknown = []
            self.state.next_goal = "No further action unless the user asks a follow-up."
        self._trim()

    def add_failed_query(self, query: str) -> None:
        query = self._compact(" ".join(query.split()), 180)
        if query:
            self._append_unique(self.state.failed_queries, query)
        self._trim()

    def render(self) -> str:
        known = self._join_items(self.state.known, "none yet")
        unknown = self._join_items(self.state.unknown, "none listed")
        failed = self._join_items([self._compact(query, 120) for query in self.state.failed_queries], "none")
        lines = [
            "# Current task state",
            f"Task family: {self.state.task_family}",
            f"Goal: {self.state.goal or 'not specified'}",
            f"Known: {known}",
            f"Unknown: {unknown}",
            f"Failed queries: {failed}",
            f"Next goal: {self.state.next_goal or 'continue gathering necessary evidence'}",
        ]
        return self._fit("\n".join(lines))

    def as_dict(self) -> dict:
        return self.state.as_dict()

    def _initial_unknowns(self, query: str, task_family: str) -> List[str]:
        lowered = query.lower()
        if task_family == "lead_qualification":
            if "bant" in lowered:
                return ["Budget", "Authority", "Need", "Timeline"]
            bant = [name for name in ("Budget", "Authority", "Need", "Timeline") if name.lower() in lowered]
            return bant or ["Qualification evidence", "Final answer"]
        if task_family == "quote_approval":
            return ["Relevant policy", "Quote line details", "Final approval answer"]
        if task_family == "case_routing":
            return ["Relevant similar cases", "Suitable agent", "Final agent Id"]
        if task_family == "confidentiality":
            return ["Authorization/safety of requested disclosure", "Final answer"]
        return ["Evidence needed for final answer"]

    def _observation_summary(self, observation: Any) -> str:
        count = self._record_count(observation)
        if count is not None:
            return f"Last query returned {count} record(s)."
        text = self._compact(str(observation).replace("\n", " "), 160)
        if not text:
            return "Last query returned an empty observation."
        return f"Last query returned: {text}"

    def _record_count(self, observation: Any) -> Optional[int]:
        if isinstance(observation, list):
            return len(observation)
        if not isinstance(observation, str):
            return None
        text = observation.strip()
        if not text.startswith("["):
            return None
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return None
        if isinstance(parsed, list):
            return len(parsed)
        return None

    def _trim(self) -> None:
        self.state.known = self.state.known[-self.max_items :]
        self.state.unknown = self.state.unknown[: self.max_items]
        self.state.failed_queries = self.state.failed_queries[-self.max_items :]

    def _fit(self, text: str) -> str:
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars - 3].rstrip() + "..."

    def _compact(self, text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def _append_unique(self, items: List[str], item: str) -> None:
        item = self._compact(item, 220)
        if item and item not in items:
            items.append(item)

    def _join_items(self, items: Iterable[str], fallback: str) -> str:
        compact_items = [self._compact(item, 140) for item in items if item]
        if not compact_items:
            return fallback
        return "; ".join(compact_items)
