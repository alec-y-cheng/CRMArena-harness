"""General-runtime DSL chat agent.

This agent is the integration surface for the shared WorkflowSpec /
InstanceFrame / ExecutionState runtime. Supported workflows run through the
canonical spec-driven driver; unported workflows fall back to ChatAgentDSL.
"""

import os
from typing import Any, Dict, List

from crm_sandbox.agents.chat_agent_dsl import ChatAgentDSL
from dsl.external_facing.actions import render_unavailable_response, should_fallback_to_ned_from_clarify
from dsl.external_facing.harness import (
    ExternalFacingRouter,
    ExternalFacingDSLRunResult,
    best_supported_route,
    route_as_supported_workflow,
)
from dsl.general_runtime.driver import CanonicalGeneralRuntimeDriver
from dsl.general_runtime.internal_router import InternalWorkflowRouter
from dsl.general_runtime.io import init_runtime_info, respond_env


class ChatAgentGeneralRuntimeDSL(ChatAgentDSL):
    """ChatAgentDSL variant backed by the generic symbolic runtime where ported."""

    def act(self, env, index=None, temperature=0.0):
        if self._should_use_external_router_dsl(env, index):
            return self._act_external_router_general_runtime_dsl(env, index)
        if self._should_use_general_runtime_kqa(env, index):
            return self._act_knowledge_qa_general_runtime_dsl(env, index)
        if self._should_use_general_runtime_ned(env, index):
            return self._act_named_entity_disambiguation_general_runtime_dsl(env, index)
        if self._should_use_internal_router_general_runtime(env, index):
            return self._act_internal_router_general_runtime_dsl(env, index)
        internal_workflow_id = self._internal_general_runtime_workflow_id(env, index)
        if internal_workflow_id:
            return self._act_internal_general_runtime_dsl(env, index, internal_workflow_id)
        return super().act(env, index=index, temperature=temperature)

    def _should_use_general_runtime_kqa(self, env, index) -> bool:
        task = self._task_from_env(env, index)
        return isinstance(task, dict) and task.get("task") == "knowledge_qa"

    def _should_use_general_runtime_ned(self, env, index) -> bool:
        task = self._task_from_env(env, index)
        return isinstance(task, dict) and task.get("task") == "named_entity_disambiguation"

    def _should_use_internal_router_general_runtime(self, env, index) -> bool:
        enabled = os.environ.get("USE_INTERNAL_ROUTER_DSL", "true").lower() not in ["0", "false", "no"]
        if not enabled:
            return False
        task = self._task_from_env(env, index)
        return isinstance(task, dict) and task.get("task") in [
            "wrong_stage_rectification",
            "policy_violation_identification",
        ]

    def _internal_general_runtime_workflow_id(self, env, index) -> str:
        task = self._task_from_env(env, index)
        if not isinstance(task, dict):
            return ""
        return {
            "wrong_stage_rectification": "wrong_stage_rectification",
            "policy_violation_identification": "policy_violation_identification",
        }.get(task.get("task"), "")

    def _act_knowledge_qa_general_runtime_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = CanonicalGeneralRuntimeDriver(
            workflow_id="external_knowledge_qa",
            model_extractor=self._call_knowledge_qa_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        self._finalize_general_runtime_result(result, env)
        return result.reward

    def _act_named_entity_disambiguation_general_runtime_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = CanonicalGeneralRuntimeDriver(
            workflow_id="external_named_entity_disambiguation",
            model_extractor=self._call_ned_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        self._finalize_general_runtime_result(result, env)
        return result.reward

    def _act_internal_general_runtime_dsl(self, env, index=None, workflow_id: str = "") -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = CanonicalGeneralRuntimeDriver(
            workflow_id=workflow_id,
            model_extractor=self._call_case_routing_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        self._finalize_general_runtime_result(result, env)
        return result.reward

    def _act_internal_router_general_runtime_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        query, metadata = env.reset(task_index=index)
        messages = [{"role": "user", "content": query.strip()}]
        router = InternalWorkflowRouter(
            model_extractor=self._call_case_routing_extractor,
            max_retries=self.max_dsl_retries,
        )
        route = router.route(query.strip(), query.strip())
        route_info = dict(router.last_info)
        route_info["general_runtime_internal_router"] = True
        route_info["oracle_task_family"] = (self._task_from_env(env, index) or {}).get("task") if isinstance(self._task_from_env(env, index), dict) else None

        if route.route in ("wrong_stage_rectification", "policy_violation_identification"):
            driver = CanonicalGeneralRuntimeDriver(
                workflow_id=route.route,
                model_extractor=self._call_case_routing_extractor,
                max_extraction_retries=self.max_dsl_retries,
            )
            result = driver.run(
                env,
                task_index=index,
                initial_query=query,
                initial_metadata=metadata,
                initial_messages=messages,
            )
        elif route.route == "clarify":
            response = "Could you clarify {} so I can route this internal request?".format(
                ", ".join(route.missing_information or ["the target record and task"])
            )
            result = self._respond_internal_router(env, messages, route_info, response)
        else:
            result = self._respond_internal_router(env, messages, route_info, render_unavailable_response())

        self._finalize_general_runtime_result(result, env)
        self.info["internal_router"] = route_info
        self.info["workflow_id"] = route.route
        self.info["dsl_task_family"] = route.route
        return result.reward

    def _respond_internal_router(self, env, messages, route_info, response):
        info = init_runtime_info("internal_router", "internal_router", {})
        info["internal_router"] = route_info
        return respond_env(env, messages, info, response)

    def _act_external_router_general_runtime_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        query, metadata = env.reset(task_index=index)
        messages = [{"role": "user", "content": query.strip()}]
        router = ExternalFacingRouter(
            model_extractor=self._call_external_router_extractor,
            max_retries=self.max_dsl_retries,
        )
        route_history = []
        result = None
        reward = 0
        max_router_clarification_turns = 2
        for router_turn in range(max(1, self.max_turns)):
            conversation_text = self._external_router_conversation(messages)
            route_query = _latest_user_message(messages) or query.strip()
            route = router.route(route_query, conversation_text)
            gate = router.gate_intended_retrieval(route)
            route_info = dict(router.last_info)
            route_info["router_turn"] = router_turn + 1
            route_info["pre_retrieval_gate"] = gate.as_dict()
            route_info["general_runtime_router"] = True
            route_history.append(route_info)

            if route.route == "clarify" and should_fallback_to_ned_from_clarify(route):
                route = route_as_supported_workflow(route, "named_entity_disambiguation", "Clarification route normalized to candidate workflow")
                route_info["clarify_fallback"] = route.route
                result = self._run_external_candidate_route(route, router, env, index, route_query, metadata, messages)
            elif route.route == "clarify":
                if router_turn >= max_router_clarification_turns:
                    candidate_route = best_supported_route(route)
                    if candidate_route and getattr(route, "threat_confidence", "unknown") != "high":
                        route = route_as_supported_workflow(route, candidate_route, "Router clarification exhausted; delegating to candidate workflow")
                        route_info["clarification_exhausted"] = True
                        route_info["clarify_fallback"] = route.route
                        result = self._run_external_candidate_route(route, router, env, index, route_query, metadata, messages)
                    else:
                        route_info["clarification_exhausted"] = True
                        result = self._respond_external_router(env, messages, route_info, render_unavailable_response())
                        reward = result.reward
                        break
                else:
                    result = self._respond_external_router(env, messages, route_info, router.build_clarification(route))
            elif route.route == "unsupported" and gate.allowed:
                result = self._respond_external_router(env, messages, route_info, render_unavailable_response())
            elif route.route == "refuse" or not gate.allowed:
                result = self._respond_external_router(env, messages, route_info, router.build_refusal(route))
            elif route.route == "knowledge_qa":
                result = self._run_external_candidate_route(route, router, env, index, route_query, metadata, messages)
            elif route.route == "named_entity_disambiguation":
                result = self._run_external_candidate_route(route, router, env, index, route_query, metadata, messages)
            else:
                result = ExternalFacingDSLRunResult(
                    reward=0,
                    done=False,
                    messages=messages,
                    info={
                        "dsl_enabled": True,
                        "general_runtime_enabled": True,
                        "dsl_task_family": "external_router",
                        "external_router": route_info,
                        "env_steps": 0,
                        "end_reason": {"source": "external_router", "message": "Unsupported route", "content": route.route},
                    },
                )

            reward = result.reward
            delegated_route = route.route in ("knowledge_qa", "named_entity_disambiguation")
            delegated_route = delegated_route or route_info.get("clarify_fallback") in ("knowledge_qa", "named_entity_disambiguation")
            if delegated_route and not result.done:
                route_info["delegated_route_continued"] = True
            if result.done:
                break
            if env.current_user_turn >= getattr(env, "max_user_turns", env.current_user_turn + 1):
                break

        if result is None:
            result = ExternalFacingDSLRunResult(
                reward=reward,
                done=False,
                messages=messages,
                info={
                    "dsl_enabled": True,
                    "general_runtime_enabled": True,
                    "dsl_task_family": "external_router",
                    "env_steps": 0,
                    "end_reason": {"source": "external_router", "message": "No router action", "content": ""},
                },
            )
        route_history_for_info = [dict(item) for item in route_history]
        final_route_info = dict(route_history[-1]) if route_history else {}
        final_route_info["route_history"] = route_history_for_info
        self._finalize_external_router_info(result, final_route_info)
        self.info["general_runtime_enabled"] = True
        return result.reward

    def _run_external_candidate_route(self, route, router, env, index, query, metadata, messages):
        if route.route == "named_entity_disambiguation":
            workflow_id = "external_named_entity_disambiguation"
            extractor = self._call_ned_extractor
        else:
            workflow_id = "external_knowledge_qa"
            extractor = self._call_knowledge_qa_extractor
        driver = CanonicalGeneralRuntimeDriver(
            workflow_id=workflow_id,
            model_extractor=extractor,
            external_router=router,
            max_extraction_retries=self.max_dsl_retries,
        )
        return driver.run(
            env,
            task_index=index,
            initial_query=query,
            initial_metadata=metadata,
            initial_messages=messages,
        )

    def _finalize_general_runtime_result(self, result, env) -> None:
        model_debug_info = {key: value for key, value in self.info.items() if key != "model_calls"}
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["general_runtime_enabled"] = True
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (getattr(env, "current_user_turn", 0), self.info.get("env_steps", 0))

    @staticmethod
    def _task_from_env(env, index):
        if index is not None and hasattr(env, "tasks"):
            return env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        if hasattr(env, "task"):
            return env.task
        return None


def _latest_user_message(messages: List[Dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = (message.get("content") or "").strip()
            if content and not content.startswith("Salesforce instance output:"):
                return content
    return ""
