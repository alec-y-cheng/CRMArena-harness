"""Benchmark-facing agent wrapper for the generic EWM runtime."""

import os
from typing import Any, Dict, List, Optional

from crm_sandbox.agents.chat_agent_dsl import ChatAgentDSL
from crm_sandbox.agents.prompts import SYSTEM_METADATA
from ewm.ir.environment import EnvironmentIR
from ewm.ir.frame import InstanceFrame, OutcomeContract, ResponseContract
from ewm.mcp.salesforce_read_adapter import SalesforceReadMCPAdapter
from ewm.mcp.salesforce_reads import SalesforceReadsClient
from ewm.mining.schema_miner import environment_ir_from_crmarena_schema
from ewm.runtime.llm_components import LLMRuntimeComponents
from ewm.runtime.frame_sanitizer import drop_protocol_constraints
from ewm.runtime.verifier import CompletionVerifierSuite, LLMCompletionVerifier
from ewm.runtime.workflow_driver import WorkflowDriver


class ChatAgentEWM(ChatAgentDSL):
    """Run CRMArena tasks through the generic EWM driver.

    This is intentionally not a task-family DSL. The LLM infers the
    InstanceFrame, selects from MCP-shaped backend/frontend/complete decisions,
    extracts claims, and proposes completion. The runtime validates calls,
    records observations/evidence, and runs completion verifiers.
    """

    def __init__(self, schema_obj, *args, **kwargs) -> None:
        self.schema_obj = schema_obj
        self.ewm_privacy_aware_prompt = bool(kwargs.get("privacy_aware_prompt", False))
        super().__init__(schema_obj=schema_obj, *args, **kwargs)
        self.env_ir = environment_ir_from_crmarena_schema(
            schema_obj,
            metadata={"source": "crmarena_schema", "runtime": "ewm"},
        )

    def act(self, env, index=None, temperature=0.0):
        query, metadata = env.reset(task_index=index)
        metadata = metadata if isinstance(metadata, dict) else {"required": str(metadata or "")}
        self.messages = [{"role": "user", "content": query.strip()}]
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {
            "model_calls": 0,
            "env_steps": 0,
            "ewm_enabled": True,
            "ewm_runtime": "generic",
            "ewm_states": [],
            "ewm_component_debug": {},
            "agent_type": self.agent_type,
        }

        components = LLMRuntimeComponents(
            model_call=self._ewm_model_call,
            max_retries=self.max_verifier_retries,
            frame_max_tokens=_env_int("EWM_FRAME_MAX_TOKENS", 1200),
            decision_max_tokens=_env_int("EWM_DECISION_MAX_TOKENS", 1400),
            claim_max_tokens=_env_int("EWM_CLAIM_MAX_TOKENS", 1200),
            verifier_max_tokens=_env_int("EWM_COMPLETION_VERIFIER_MAX_TOKENS", 900),
        )
        mcp_client = SalesforceReadsClient(
            SalesforceReadMCPAdapter(
                org_type=os.environ.get("EWM_ORG_TYPE", "b2b"),
                connector=getattr(env, "sf_connector", None),
            )
        )
        driver = WorkflowDriver(
            mcp_client=mcp_client,
            env_ir=self.env_ir,
            frame_inferer=lambda messages, env_summary: self._compile_frame(
                components,
                messages,
                env_summary,
            ),
            decision_selector=components.select_decision,
            claim_extractor=None,
            completion_verifier_suite=CompletionVerifierSuite(
                semantic_verifiers=[LLMCompletionVerifier(components.verify_completion_payload)]
            ),
            max_steps=_env_int("EWM_MAX_STEPS", 8),
        )

        done = False
        reward = 0
        info: Dict[str, Any] = {}
        state = None
        max_user_turns = getattr(env, "max_user_turns", 1)
        for interaction_turn in range(max(1, self.max_turns)):
            state = driver.run(
                messages=list(self.messages),
                env_summary=self._env_summary(metadata),
                initial_state=state,
            )
            self.info["ewm_states"].append(state.to_dict())
            response = driver.render(state).strip()
            if not response:
                response = self._fallback_response(state)

            action = {"name": "respond", "content": response}
            self.messages.append({"role": "assistant", "content": response})
            observation, reward, done, info = env.step(action)
            self.info["env_steps"] += 1
            self._copy_env_timing(info)
            if done:
                break
            self.messages.append({"role": "user", "content": str(observation)})
            if getattr(env, "current_user_turn", 0) >= max_user_turns:
                break

        if not done and "end_reason" not in info:
            self.info["end_reason"] = {
                "source": "ewm",
                "message": "Max turns reached",
                "content": self.messages[-1]["content"] if self.messages else "",
            }
        elif "end_reason" in info:
            self.info["end_reason"] = info["end_reason"]

        self.info["ewm_component_debug"] = components.debug
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (getattr(env, "current_user_turn", 0), self.info.get("env_steps", 0))
        return reward

    def _ewm_model_call(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
        message = self._call_model(messages, max_tokens=max_tokens)
        return str(message.get("content") or "")

    def _compile_frame(
        self,
        components: LLMRuntimeComponents,
        messages: List[Dict[str, Any]],
        env_summary: Dict[str, Any],
    ) -> InstanceFrame:
        """Compile benchmark-visible instructions into the initial frame.

        The EWM runtime should not receive a stronger task/privacy prompt than
        the ReAct baseline. We therefore give the frame compiler the same
        benchmark system prompt surface and ask it to extract the goal,
        constraints, evidence requirements, and answer contract into structured
        state. The deterministic bootstrap remains only as a malformed-output
        fallback so the driver never starts from an empty frame.
        """

        frame_env_summary = self._frame_env_summary(env_summary)
        frame = components.infer_frame(messages, frame_env_summary)
        if frame.goal or frame.request_summary:
            self._sanitize_compiled_frame(frame)
            frame.metadata.setdefault("frame_source", "llm_compiled_benchmark_prompt")
            return frame
        fallback = self._bootstrap_frame(messages, env_summary)
        self._sanitize_compiled_frame(fallback)
        fallback.metadata["frame_source"] = "deterministic_fallback"
        return fallback

    def _sanitize_compiled_frame(self, frame: InstanceFrame) -> None:
        frame.constraints = drop_protocol_constraints(frame.constraints)
        frame.response_contract.constraints = drop_protocol_constraints(frame.response_contract.constraints)

    def _bootstrap_frame(self, messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> InstanceFrame:
        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_text = str(message.get("content") or "").strip()
                break
        constraints = []
        if env_summary.get("required_metadata"):
            constraints.append(str(env_summary.get("required_metadata")))
        if env_summary.get("privacy_aware_prompt"):
            constraints.append("Respect privacy, authorization, and disclosure constraints implied by the request context.")
        return InstanceFrame(
            goal=user_text,
            request_summary=user_text,
            actor={"kind": env_summary.get("agent_type") or "unknown"},
            constraints=constraints,
            outcome_contract=OutcomeContract("complete the user's CRM request using supported evidence"),
            response_contract=ResponseContract("answer the current user request"),
            metadata={"bootstrap": True},
        )

    def _frame_env_summary(self, env_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent_type": env_summary.get("agent_type"),
            "benchmark_system_prompt": self._benchmark_system_prompt(env_summary),
            "required_metadata": env_summary.get("required_metadata", ""),
            "optional_metadata_available": env_summary.get("optional_metadata_available", False),
            "optional_metadata": env_summary.get("optional_metadata", ""),
            "compilation_guidance": (
                "Use benchmark_system_prompt and metadata as the authority for "
                "stated constraints. Compile those instructions into InstanceFrame "
                "fields. Keep a constraint only if it would still govern task "
                "execution or the user-visible outcome under a different runtime. "
                "Exclude protocol instructions about JSON, action tags, ReAct "
                "formatting, system observations, or this compilation step itself."
            ),
        }

    def _benchmark_system_prompt(self, env_summary: Dict[str, Any]) -> str:
        prompt = self.sys_prompt.strip()
        if self.scaffold_text:
            prompt += "\n\n# Orchestration Scaffold\n" + self.scaffold_text
        required = str(env_summary.get("required_metadata") or "").strip()
        if required:
            prompt += "\n" + SYSTEM_METADATA.format(
                system_metadata=required,
                system="Salesforce instance",
            )
        optional = str(env_summary.get("optional_metadata") or "").strip()
        if env_summary.get("optional_metadata_available") and optional:
            prompt += "\n" + optional
        return prompt

    def _env_summary(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "privacy_aware_prompt": self.ewm_privacy_aware_prompt,
            "required_metadata": metadata.get("required", ""),
            "optional_metadata_available": self.eval_mode == "aided" and bool(metadata.get("optional")),
            "optional_metadata": metadata.get("optional", "") if self.eval_mode == "aided" else "",
            "objects": self._schema_summary(max_fields_per_object=_env_int("EWM_SCHEMA_FIELDS_PER_OBJECT", 80)),
            "tools": self.env_ir.tool_schemas,
        }

    def _schema_summary(self, max_fields_per_object: int = 80) -> List[Dict[str, Any]]:
        out = []
        for object_name in self.env_ir.object_names():
            schema = self.env_ir.get_object(object_name)
            if schema is None:
                continue
            fields = []
            for field_name in schema.field_names()[:max_fields_per_object]:
                field_info = schema.fields.get(field_name, {})
                fields.append(
                    {
                        "name": field_name,
                        "description": field_info.get("description", ""),
                        "reference_targets": field_info.get("reference_targets", []),
                    }
                )
            out.append({"object": object_name, "fields": fields})
        return out

    def _copy_env_timing(self, info: Dict[str, Any]) -> None:
        for key in ("time_to_resolution_seconds", "interaction_start_time", "interaction_end_time"):
            if key in info:
                self.info[key] = info[key]

    @staticmethod
    def _fallback_response(state) -> str:
        if state.completion_state.status == "needs_action" and state.completion_state.needed:
            needed = state.completion_state.needed[0]
            if isinstance(needed, dict) and needed.get("source") == "user":
                return str(needed.get("description") or "").strip()
        if state.completion_state.status == "needs_verification":
            return "I do not have enough verified information to answer that."
        return "I do not have enough information to answer that."


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default
