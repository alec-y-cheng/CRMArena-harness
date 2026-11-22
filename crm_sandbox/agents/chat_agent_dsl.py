import os
import litellm
litellm.set_verbose = False
from typing import Any, Dict, List, Optional
import time, traceback
from crm_sandbox.agents.prompts import SCHEMA_STRING, REACT_RULE_STRING, ACT_RULE_STRING, SYSTEM_METADATA, REACT_EXTERNAL_INTERACTIVE_PROMPT, REACT_INTERNAL_INTERACTIVE_PROMPT, REACT_INTERNAL_PROMPT, REACT_EXTERNAL_PROMPT, REACT_PRIVACY_AWARE_EXTERNAL_PROMPT, REACT_PRIVACY_AWARE_EXTERNAL_INTERACTIVE_PROMPT, ACT_PROMPT
from crm_sandbox.model_client import completion_with_provider, is_cli_provider
from crm_sandbox.agents.utils import parse_wrapped_response, BEDROCK_MODELS_MAP, TOGETHER_MODELS_MAP, VERTEX_MODELS_MAP
from dsl.case_routing.harness import CaseRoutingDSLDriver
from dsl.case_routing.schemas import CASE_ROUTING_SELECTION_SCHEMA, CASE_ROUTING_SLOT_SCHEMA
from dsl.external_facing.actions import (
    render_unavailable_response,
    should_fallback_to_ned_from_clarify,
)
from dsl.external_facing.harness import ExternalFacingRouter
from dsl.external_facing.schemas import EXTERNAL_REQUEST_ROUTE_SCHEMA
from dsl.general_runtime.schemas import DISCLOSURE_GATE_SCHEMA
from dsl.knowledge_qa.harness import KnowledgeQADSLDriver
from dsl.knowledge_qa.schemas import (
    KNOWLEDGE_QA_ANSWER_SCHEMA,
    KNOWLEDGE_QA_ARTICLE_EVIDENCE_SCHEMA,
    KNOWLEDGE_QA_SEARCH_PLAN_SCHEMA,
)
from dsl.lead_qualification.harness import LeadQualificationDSLDriver
from dsl.lead_qualification.schemas import BANT_EXTRACTION_SCHEMA, TIMELINE_POLICY_SCHEMA
from dsl.named_entity_disambiguation.harness import NamedEntityDisambiguationDSLDriver
from dsl.named_entity_disambiguation.schemas import (
    NED_CANDIDATE_SELECTION_SCHEMA,
    NED_CLARIFICATION_SCHEMA,
    NED_EXTRACTION_SCHEMA,
)
from dsl.quote_approval.harness import QuoteApprovalDSLDriver
from dsl.quote_approval.schemas import (
    QUOTE_ARTICLE_EVIDENCE_SCHEMA,
    QUOTE_DISCOUNT_POLICY_STRUCTURE_SCHEMA,
    QUOTE_POLICY_SEARCH_PLAN_SCHEMA,
)
import together

class ChatAgentDSL:
    def __init__(
        self,
        schema_obj,
        model: str = "gpt-4o",
        max_turns: int = 20,
        eval_mode="default",
        strategy="react",
        provider="bedrock",
        interactive=False,
        agent_type="internal",
        privacy_aware_prompt=False,
        max_dsl_retries=3,
        agent_max_tokens=2000,
        scaffold_text: Optional[str] = None,
        routing_result: Optional[Dict] = None,
    ):
        schema = self._build_schema(schema_obj)
        assert strategy in ["react", "act"], "Only react and act strategies supported for now"
        assert agent_type in ["internal", "external"], "Invalid agent type"
        
        if strategy == "react":
            # react strategy
            if not interactive:
                if agent_type == "internal":
                    self.sys_prompt = REACT_INTERNAL_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
                else:
                    if privacy_aware_prompt:
                        self.sys_prompt = REACT_PRIVACY_AWARE_EXTERNAL_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
                    else:
                        self.sys_prompt = REACT_EXTERNAL_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
            else:
                if agent_type == "internal":
                    self.sys_prompt = REACT_INTERNAL_INTERACTIVE_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
                else:
                    if privacy_aware_prompt:
                        self.sys_prompt = REACT_PRIVACY_AWARE_EXTERNAL_INTERACTIVE_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
                    else:
                        self.sys_prompt = REACT_EXTERNAL_INTERACTIVE_PROMPT.format(system_description=schema, system="Salesforce instance") # add strategy template and schema description
        else:
            # act strategy
            self.sys_prompt = ACT_PROMPT.format(system_description=schema, system="Salesforce instance")
        
        self.agent_type = agent_type
        self.original_model_name = model
        self.model = model
        self.eval_mode = eval_mode
        self.max_turns = max_turns
        self.strategy = strategy
        self.info = {}
        self.messages = []
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.provider = provider
        self.max_dsl_retries = max_dsl_retries
        self.agent_max_tokens = agent_max_tokens
        try:
            self.lead_dsl_extractor_max_tokens = int(os.environ.get("LEAD_DSL_EXTRACTOR_MAX_TOKENS", "1800"))
        except ValueError:
            self.lead_dsl_extractor_max_tokens = 1800
        try:
            self.quote_dsl_extractor_max_tokens = int(os.environ.get("QUOTE_DSL_EXTRACTOR_MAX_TOKENS", "2200"))
        except ValueError:
            self.quote_dsl_extractor_max_tokens = 2200
        try:
            self.case_dsl_extractor_max_tokens = int(os.environ.get("CASE_DSL_EXTRACTOR_MAX_TOKENS", "1400"))
        except ValueError:
            self.case_dsl_extractor_max_tokens = 1400
        try:
            self.knowledge_qa_dsl_extractor_max_tokens = int(os.environ.get("KNOWLEDGE_QA_DSL_EXTRACTOR_MAX_TOKENS", "1800"))
        except ValueError:
            self.knowledge_qa_dsl_extractor_max_tokens = 1800
        try:
            self.ned_dsl_extractor_max_tokens = int(os.environ.get("NED_DSL_EXTRACTOR_MAX_TOKENS", "1400"))
        except ValueError:
            self.ned_dsl_extractor_max_tokens = 1400
        try:
            self.external_router_max_tokens = int(os.environ.get("EXTERNAL_ROUTER_MAX_TOKENS", "900"))
        except ValueError:
            self.external_router_max_tokens = 900
        self.scaffold_text = (scaffold_text or "").strip()
        self.routing_result = routing_result or None
       
        if provider == "bedrock" and self.model in BEDROCK_MODELS_MAP:
            os.environ["AWS_REGION_NAME"] = BEDROCK_MODELS_MAP[self.model]["region"]
            self.model = BEDROCK_MODELS_MAP[self.model]["name"]
        elif provider == "together_ai" and self.model in TOGETHER_MODELS_MAP:
            self.model = TOGETHER_MODELS_MAP[self.model]["name"]
        elif "vertex" in provider and self.model in VERTEX_MODELS_MAP:
            self.model = VERTEX_MODELS_MAP[self.model]["name"]
            
        else:
            pass
        if self.model in ["o1-mini", "o1-preview", "o1-2024-12-17", "o3-mini-2025-01-31"]:
            import litellm
            
            litellm.drop_params=True
            print("dropping parameters")
            
            # assert self.model in ["o1-mini", "o1-preview", "gpt-4o-2024-08-06", "gpt-3.5-turbo-0125"], "Invalid model name"
    
    def _build_schema(self, schema_obj):
        object_description = dict()
        for item in schema_obj:
            object_description[item["object"]] = "\n".join([f"  - {k}: {v}" for k,v in item["fields"].items()])
            
        template = SCHEMA_STRING.format(
            object_names=", ".join(object_description.keys()),
            object_fields="\n".join(
                [f"{obj}\n{fields}" for obj, fields in object_description.items()]
            )
        )
        return template
    
    def reset(self, args):
        if self.scaffold_text:
            self.sys_prompt += "\n\n# Orchestration Scaffold\n" + self.scaffold_text
        if args["metadata"]["required"]:
            self.sys_prompt += SYSTEM_METADATA.format(system_metadata=args["metadata"]["required"], system="Salesforce instance") # add task/query-specific metadata here
        if self.eval_mode == "aided" and "optional" in args["metadata"]:
            self.sys_prompt += "\n" + args["metadata"]["optional"]
        if self.original_model_name not in ["o1-mini", "o1-preview", "o1-2024-12-17", "deepseek-r1", "o3-mini-2025-01-31", "gemini-2.5-flash-preview-04-17"]:
            self.messages = [{"role": "system", "content": self.sys_prompt.strip()}]
            self.messages.append({"role": "user", "content": args["query"].strip()})
        
        else:
            # No system role for o1-mini and o1-preview
            self.messages = [{"role": "user", "content": self.sys_prompt + "\n\n" + args["query"]}]
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        
    def act(self, env, index=None, temperature=0.0):
        if self._should_use_external_router_dsl(env, index):
            return self._act_external_router_dsl(env, index)
        if self._should_use_ned_dsl(env, index):
            return self._act_ned_dsl(env, index)
        if self._should_use_knowledge_qa_dsl(env, index):
            return self._act_knowledge_qa_dsl(env, index)
        if self._should_use_case_routing_dsl(env, index):
            return self._act_case_routing_dsl(env, index)
        if self._should_use_quote_approval_dsl(env, index):
            return self._act_quote_approval_dsl(env, index)
        if self._should_use_lead_qualification_dsl(env, index):
            return self._act_lead_qualification_dsl(env, index)

        query, metadata = env.reset(task_index=index)
        self.reset({"query": query, "metadata": metadata})
        # print("----")
        # print(self.sys_prompt)
        # print("----")
        total_cost = 0.0
        self.info["observation_sizes"] = []
        self.info["routing"] = self.routing_result
        self.info["scaffold_injected"] = bool(self.scaffold_text)
        self.info["model_calls"] = 0
        self.info["env_steps"] = 0
        done = False
        reward = 0
        message = {"content": ""}
        info = {}
        
        current_agent_turn = 0
        # for turn_id in range(self.max_turns):
        while current_agent_turn < self.max_turns:
            info = {}
            current_agent_turn += 1

            message = self._call_model(list(self.messages))
            action = self.message_action_parser(message, self.model)
            content = (message.get("content") or "").strip()
            print(
                "User Turn:", env.current_user_turn,
                "Agent Turn:", current_agent_turn,
                "Agent:", content,
            )
            self.messages.append({"role": "assistant", "content": content})
            if action is None:
                self.info["end_reason"] = {
                    "source": "agent",
                    "message": "Invalid action",
                    "content": content
                }
                info["end_reason"] = self.info["end_reason"]
                if self.strategy == "react":
                    self.messages.append({"role": "user", "content": REACT_RULE_STRING})
                elif self.strategy == "act":
                    self.messages.append({"role": "user", "content": ACT_RULE_STRING})
                continue

            obs, reward, done, info = env.step(action)
            self.info["env_steps"] += 1
            for timing_key in (
                "time_to_resolution_seconds",
                "interaction_start_time",
                "interaction_end_time",
            ):
                if timing_key in info:
                    self.info[timing_key] = info[timing_key]
            
            if "observation_size" in info:
                self.info["observation_sizes"].append(info["observation_size"])
            if "end_reason" in info: # implies error in query
                self.info["end_reason"] = info["end_reason"]
            # reset counter if previous action is respond
            if action["name"] == "respond":
                current_agent_turn = 0
            if done:
                break
            elif action["name"] == "execute": # execution results from
                self.messages.append({"role": "user", "content": f"Salesforce instance output: {obs}"})
            elif action["name"] == "respond": # respond to simulated user
                self.messages.append({"role": "user", "content": obs})
        
        # Here when either max_turns is reached or submitted
        if not done: 
            if "end_reason" not in info: # no error in last query
                self.info["end_reason"] = {
                    "source": "agent",
                    "message": "Max turns reached",
                    "content":  (message.get("content") or "").strip()
                }
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, current_agent_turn + 1)
        return reward

    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages

    def _call_model(
        self,
        messages,
        max_tokens=None,
        response_format=None,
        extra_body=None,
        structured_output_attempts=None,
    ):
        # sleep for non-openai models
        if self.provider != "openai" and not is_cli_provider(self.provider):
            time.sleep(5)
        # turn off thinking for gemini 2.5 flash
        if self.original_model_name == "gemini-2.5-flash-preview-04-17":
            thinking = {"type": "disabled", "budget_tokens": 0}
        elif self.original_model_name == "gemini-2.5-flash-preview-04-17-thinking-4096":
            thinking = {"type": "enabled", "budget_tokens": 4096}
        else:
            thinking = None

        default_max_tokens = self.agent_max_tokens if self.original_model_name not in ["o1-mini", "o1-preview", "o1-2024-12-17", "deepseek-r1", "o3-mini-2025-01-31", "gemini-2.5-flash-preview-04-17", "gemini-2.5-flash-preview-04-17-thinking-4096", "gemini-2.5-pro-preview-03-25"] else 50000

        completion_kwargs = {
            "messages": messages,
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": max_tokens if max_tokens is not None else default_max_tokens,
            "top_p": 1.0 if self.model not in ["o3-mini-2025-01-31"] else None,
            "thinking": thinking,
            # custom_llm_provider=self.provider,
            "additional_drop_params": ["temperature"] if self.original_model_name in ["o1-mini", "o1-preview", "o1-2024-12-17", "deepseek-r1", "o3-mini-2025-01-31"] else [],
        }
        attempts = structured_output_attempts
        if attempts is None:
            attempts = [
                {
                    "label": "requested",
                    "response_format": response_format,
                    "extra_body": extra_body,
                }
            ]

        res = None
        message = None
        last_error = None
        for attempt in attempts:
            attempt_kwargs = dict(completion_kwargs)
            attempt_response_format = attempt.get("response_format")
            attempt_extra_body = attempt.get("extra_body")
            if attempt_response_format is not None:
                attempt_kwargs["response_format"] = attempt_response_format
            if attempt_extra_body is not None:
                attempt_kwargs["extra_body"] = attempt_extra_body
            try:
                candidate_res = completion_with_provider(provider=self.provider, **attempt_kwargs)
                candidate_message = candidate_res.choices[0].message.model_dump()
                if attempt.get("require_content") and not self._model_message_content(candidate_message):
                    self.info.setdefault("structured_output_empty_content", []).append(
                        {
                            "label": attempt.get("label", "structured"),
                            "message": candidate_message,
                        }
                    )
                    self._record_completion_usage(candidate_res)
                    self.info["model_calls"] += 1
                    continue
                res = candidate_res
                message = candidate_message
                if attempt_response_format is not None or attempt_extra_body is not None:
                    self.info.setdefault("structured_output_modes", []).append(attempt.get("label", "structured"))
                break
            except Exception:
                last_error = traceback.format_exc()
                if attempt_response_format is None and attempt_extra_body is None and len(attempts) == 1:
                    raise
                self.info.setdefault("structured_output_fallbacks", []).append(
                    {
                        "label": attempt.get("label", "structured"),
                        "error": last_error,
                    }
                )

        if res is None:
            try:
                res = completion_with_provider(provider=self.provider, **completion_kwargs)
                message = res.choices[0].message.model_dump()
                self.info.setdefault("structured_output_modes", []).append("unstructured_fallback")
            except Exception:
                if last_error:
                    self.info.setdefault("structured_output_fallbacks", []).append(
                        {
                            "label": "unstructured_fallback",
                            "error": traceback.format_exc(),
                        }
                    )
                raise

        if message is None:
            message = res.choices[0].message.model_dump()
        self._record_completion_usage(res)
        self.info["model_calls"] += 1
        return message

    def _record_completion_usage(self, res):
        usage = res.usage
        for key in self.usage.keys():
            if key != "cost":
                self.usage[key].append(usage.get(key, 0))
        self.usage["cost"].append(res._hidden_params["response_cost"])

    def _should_use_external_router_dsl(self, env, index) -> bool:
        enabled = os.environ.get("USE_EXTERNAL_ROUTER_DSL", "false").lower() in ["1", "true", "yes"]
        if not enabled:
            return False
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") in [
            "knowledge_qa",
            "named_entity_disambiguation",
            "private_customer_information",
            "internal_operation_data",
            "confidential_company_knowledge",
        ]

    def _act_external_router_dsl(self, env, index=None) -> float:
        from dsl.external_facing.harness import ExternalFacingDSLRunResult

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
        for router_turn in range(max(1, self.max_turns)):
            conversation_text = self._external_router_conversation(messages)
            route = router.route(query.strip(), conversation_text)
            gate = router.gate_intended_retrieval(route)
            route_info = dict(router.last_info)
            route_info["router_turn"] = router_turn + 1
            route_info["pre_retrieval_gate"] = gate.as_dict()
            route_history.append(route_info)

            if route.route == "clarify" and should_fallback_to_ned_from_clarify(route):
                route_info["clarify_fallback"] = "named_entity_disambiguation"
                driver = NamedEntityDisambiguationDSLDriver(
                    model_extractor=self._call_ned_extractor,
                    external_router=router,
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
                if router_turn > 0:
                    route_info["clarification_exhausted"] = True
                    result = self._respond_external_router(
                        env,
                        messages,
                        route_info,
                        render_unavailable_response(),
                    )
                    reward = result.reward
                    break
                result = self._respond_external_router(
                    env,
                    messages,
                    route_info,
                    router.build_clarification(route),
                )
            elif route.route in ("refuse", "unsupported") or not gate.allowed:
                result = self._respond_external_router(
                    env,
                    messages,
                    route_info,
                    router.build_refusal(route),
                )
            elif route.route == "knowledge_qa":
                driver = KnowledgeQADSLDriver(
                    model_extractor=self._call_knowledge_qa_extractor,
                    external_router=router,
                    max_extraction_retries=self.max_dsl_retries,
                )
                result = driver.run(
                    env,
                    task_index=index,
                    initial_query=query,
                    initial_metadata=metadata,
                    initial_messages=messages,
                )
            elif route.route == "named_entity_disambiguation":
                driver = NamedEntityDisambiguationDSLDriver(
                    model_extractor=self._call_ned_extractor,
                    external_router=router,
                    max_extraction_retries=self.max_dsl_retries,
                )
                result = driver.run(
                    env,
                    task_index=index,
                    initial_query=query,
                    initial_metadata=metadata,
                    initial_messages=messages,
                )
            else:
                result = ExternalFacingDSLRunResult(
                    reward=0,
                    done=False,
                    messages=messages,
                    info={
                        "dsl_enabled": True,
                        "dsl_task_family": "external_router",
                        "external_router": route_info,
                        "env_steps": 0,
                        "end_reason": {
                            "source": "external_router",
                            "message": "Unsupported route",
                            "content": route.route,
                        },
                    },
                )

            reward = result.reward
            delegated_route = route.route in ("knowledge_qa", "named_entity_disambiguation")
            delegated_route = delegated_route or route_info.get("clarify_fallback") in (
                "knowledge_qa",
                "named_entity_disambiguation",
            )
            if result.done or delegated_route:
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
                    "dsl_task_family": "external_router",
                    "env_steps": 0,
                    "end_reason": {
                        "source": "external_router",
                        "message": "No router action",
                        "content": "",
                    },
                },
            )
        route_history_for_info = [dict(item) for item in route_history]
        final_route_info = dict(route_history[-1]) if route_history else {}
        final_route_info["route_history"] = route_history_for_info
        self._finalize_external_router_info(result, final_route_info)
        return result.reward

    def _respond_external_router(
        self,
        env,
        messages: List[Dict[str, str]],
        route_info: Dict[str, Any],
        answer: str,
    ):
        from dsl.external_facing.harness import ExternalFacingDSLRunResult

        action = {"name": "respond", "content": answer}
        messages.append({"role": "assistant", "content": "<respond>{}</respond>".format(answer)})
        observation, reward, done, step_info = env.step(action)
        messages.append({"role": "user", "content": observation})
        info = {
            "dsl_enabled": True,
            "dsl_task_family": "external_router",
            "external_router": route_info,
            "env_steps": 1,
            "end_reason": step_info.get("end_reason", {}),
            "agent_actions": step_info.get("agent_actions", []),
        }
        for key in (
            "time_to_resolution_seconds",
            "interaction_start_time",
            "interaction_end_time",
        ):
            if key in step_info:
                info[key] = step_info[key]
        return ExternalFacingDSLRunResult(reward=reward, done=done, messages=messages, info=info)

    def _finalize_external_router_info(self, result, route_info: Dict[str, Any]) -> None:
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        self.messages = result.messages
        self.info = result.info
        self.info["external_router"] = route_info
        self.info["external_router_model_calls"] = route_info.get("model_calls", 0)
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = self.info.get("num_turns", (0, self.info.get("env_steps", 0)))

    @staticmethod
    def _external_router_conversation(messages: List[Dict[str, str]]) -> str:
        chunks = []
        for message in messages:
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                chunks.append("Customer: {}".format(content))
            elif role == "assistant":
                chunks.append("Assistant: {}".format(content))
        return "\n".join(chunks)

    def _should_use_ned_dsl(self, env, index) -> bool:
        enabled = os.environ.get("USE_NED_DSL", "false").lower() in ["1", "true", "yes"]
        if not enabled:
            return False
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") == "named_entity_disambiguation"

    def _act_ned_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = NamedEntityDisambiguationDSLDriver(
            model_extractor=self._call_ned_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, self.info.get("env_steps", 0))
        return result.reward

    def _call_ned_extractor(self, messages: List[Dict[str, str]]) -> str:
        schema = self._ned_dsl_schema_for_messages(messages)
        disable_thinking = os.environ.get("NED_DSL_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        if schema is not None:
            schema_name = self._ned_dsl_schema_name_for_messages(messages)
            structured_output_attempts = [
                {
                    "label": "vllm_structured_outputs_json",
                    "response_format": None,
                    "extra_body": self._merge_extra_body(
                        thinking_extra_body,
                        {"structured_outputs": {"json": schema}},
                    ),
                    "require_content": True,
                },
                {
                    "label": "openai_json_schema",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema,
                        },
                    },
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "prompt_only_nonthinking",
                    "response_format": None,
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
            ]
        else:
            structured_output_attempts = [
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                }
            ]
        message = self._call_model(
            messages,
            max_tokens=self.ned_dsl_extractor_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("ned_dsl_extractor_model_messages", []).append(message)
        return self._model_message_content(message)

    @staticmethod
    def _ned_dsl_schema_for_messages(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "final selected-evidence disclosure gate" in system_text:
            return DISCLOSURE_GATE_SCHEMA
        if "extract product/entity" in system_text or "purchase-time slots" in system_text:
            return NED_EXTRACTION_SCHEMA
        if "clarification question" in system_text:
            return NED_CLARIFICATION_SCHEMA
        if "select the product/entity candidate" in system_text or "candidate" in system_text:
            return NED_CANDIDATE_SELECTION_SCHEMA
        return None

    @staticmethod
    def _ned_dsl_schema_name_for_messages(messages: List[Dict[str, str]]) -> str:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "final selected-evidence disclosure gate" in system_text:
            return "selected_evidence_disclosure_gate"
        if "extract product/entity" in system_text or "purchase-time slots" in system_text:
            return "ned_extraction"
        if "clarification question" in system_text:
            return "ned_clarification"
        return "ned_candidate_selection"

    def _should_use_knowledge_qa_dsl(self, env, index) -> bool:
        enabled = os.environ.get("USE_KNOWLEDGE_QA_DSL", "false").lower() in ["1", "true", "yes"]
        if not enabled:
            return False
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") == "knowledge_qa"

    def _act_knowledge_qa_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = KnowledgeQADSLDriver(
            model_extractor=self._call_knowledge_qa_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, self.info.get("env_steps", 0))
        return result.reward

    def _call_knowledge_qa_extractor(self, messages: List[Dict[str, str]]) -> str:
        schema = self._knowledge_qa_dsl_schema_for_messages(messages)
        disable_thinking = os.environ.get("KNOWLEDGE_QA_DSL_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        if schema is not None:
            schema_name = self._knowledge_qa_dsl_schema_name_for_messages(messages)
            structured_output_attempts = [
                {
                    "label": "vllm_structured_outputs_json",
                    "response_format": None,
                    "extra_body": self._merge_extra_body(
                        thinking_extra_body,
                        {"structured_outputs": {"json": schema}},
                    ),
                    "require_content": True,
                },
                {
                    "label": "openai_json_schema",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema,
                        },
                    },
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "prompt_only_nonthinking",
                    "response_format": None,
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
            ]
        else:
            structured_output_attempts = [
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                }
            ]
        message = self._call_model(
            messages,
            max_tokens=self.knowledge_qa_dsl_extractor_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("knowledge_qa_dsl_extractor_model_messages", []).append(message)
        return self._model_message_content(message)

    @staticmethod
    def _knowledge_qa_dsl_schema_for_messages(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "final selected-evidence disclosure gate" in system_text:
            return DISCLOSURE_GATE_SCHEMA
        if "search terms" in system_text:
            return KNOWLEDGE_QA_SEARCH_PLAN_SCHEMA
        if "classify selected knowledge" in system_text or "selected knowledge" in system_text or "article evidence" in system_text:
            return KNOWLEDGE_QA_ARTICLE_EVIDENCE_SCHEMA
        if "retrieved public knowledge" in system_text or "public knowledge" in system_text:
            return KNOWLEDGE_QA_ANSWER_SCHEMA
        return None

    @staticmethod
    def _knowledge_qa_dsl_schema_name_for_messages(messages: List[Dict[str, str]]) -> str:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "final selected-evidence disclosure gate" in system_text:
            return "selected_evidence_disclosure_gate"
        if "search terms" in system_text:
            return "knowledge_qa_search_plan"
        if "classify selected knowledge" in system_text or "selected knowledge" in system_text or "article evidence" in system_text:
            return "knowledge_qa_article_evidence"
        return "knowledge_qa_answer"

    def _call_external_router_extractor(self, messages: List[Dict[str, str]]) -> str:
        disable_thinking = os.environ.get("EXTERNAL_ROUTER_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        structured_output_attempts = [
            {
                "label": "vllm_structured_outputs_json",
                "response_format": None,
                "extra_body": self._merge_extra_body(
                    thinking_extra_body,
                    {"structured_outputs": {"json": EXTERNAL_REQUEST_ROUTE_SCHEMA}},
                ),
                "require_content": True,
            },
            {
                "label": "openai_json_schema",
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "external_request_route",
                        "schema": EXTERNAL_REQUEST_ROUTE_SCHEMA,
                    },
                },
                "extra_body": thinking_extra_body or None,
                "require_content": True,
            },
            {
                "label": "json_object_only",
                "response_format": {"type": "json_object"},
                "extra_body": thinking_extra_body or None,
                "require_content": True,
            },
            {
                "label": "prompt_only_nonthinking",
                "response_format": None,
                "extra_body": thinking_extra_body or None,
                "require_content": True,
            },
        ]
        message = self._call_model(
            messages,
            max_tokens=self.external_router_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("external_router_model_messages", []).append(message)
        return self._model_message_content(message)

    def _should_use_case_routing_dsl(self, env, index) -> bool:
        enabled = os.environ.get("USE_CASE_ROUTING_DSL", "false").lower() in ["1", "true", "yes"]
        if not enabled:
            return False
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") == "case_routing"

    def _act_case_routing_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = CaseRoutingDSLDriver(
            model_extractor=self._call_case_routing_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, self.info.get("env_steps", 0))
        return result.reward

    def _call_case_routing_extractor(self, messages: List[Dict[str, str]]) -> str:
        schema = self._case_dsl_schema_for_messages(messages)
        disable_thinking = os.environ.get("CASE_DSL_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        if schema is not None:
            schema_name = self._case_dsl_schema_name_for_messages(messages)
            structured_output_attempts = [
                {
                    "label": "vllm_structured_outputs_json",
                    "response_format": None,
                    "extra_body": self._merge_extra_body(
                        thinking_extra_body,
                        {"structured_outputs": {"json": schema}},
                    ),
                    "require_content": True,
                },
                {
                    "label": "openai_json_schema",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema,
                        },
                    },
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "prompt_only_nonthinking",
                    "response_format": None,
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
            ]
        else:
            structured_output_attempts = [
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                }
            ]
        message = self._call_model(
            messages,
            max_tokens=self.case_dsl_extractor_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("case_dsl_extractor_model_messages", []).append(message)
        return self._model_message_content(message)

    @staticmethod
    def _case_dsl_schema_for_messages(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "case-routing slots" in system_text:
            return CASE_ROUTING_SLOT_SCHEMA
        if "Issue__c record" in system_text or "Product2 record" in system_text:
            return CASE_ROUTING_SELECTION_SCHEMA
        return None

    @staticmethod
    def _case_dsl_schema_name_for_messages(messages: List[Dict[str, str]]) -> str:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "case-routing slots" in system_text:
            return "case_routing_slots"
        if "Issue__c record" in system_text:
            return "case_routing_issue_selection"
        return "case_routing_product_selection"

    def _should_use_quote_approval_dsl(self, env, index) -> bool:
        enabled = os.environ.get("USE_QUOTE_APPROVAL_DSL", "false").lower() in ["1", "true", "yes"]
        if not enabled:
            return False
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") == "quote_approval"

    def _act_quote_approval_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = QuoteApprovalDSLDriver(
            model_extractor=self._call_quote_approval_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, self.info.get("env_steps", 0))
        return result.reward

    def _call_quote_approval_extractor(self, messages: List[Dict[str, str]]) -> str:
        schema = self._quote_dsl_schema_for_messages(messages)
        disable_thinking = os.environ.get("QUOTE_DSL_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        if schema is not None:
            schema_name = self._quote_dsl_schema_name_for_messages(messages)
            structured_output_attempts = [
                {
                    "label": "vllm_structured_outputs_json",
                    "response_format": None,
                    "extra_body": self._merge_extra_body(
                        thinking_extra_body,
                        {"structured_outputs": {"json": schema}},
                    ),
                    "require_content": True,
                },
                {
                    "label": "openai_json_schema",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema,
                        },
                    },
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "prompt_only_nonthinking",
                    "response_format": None,
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
            ]
        else:
            structured_output_attempts = [
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                }
            ]
        message = self._call_model(
            messages,
            max_tokens=self.quote_dsl_extractor_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("quote_dsl_extractor_model_messages", []).append(message)
        return self._model_message_content(message)

    @staticmethod
    def _quote_dsl_schema_for_messages(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "Knowledge article searches" in system_text:
            return QUOTE_POLICY_SEARCH_PLAN_SCHEMA
        if "structured discount policy rules" in system_text:
            return QUOTE_DISCOUNT_POLICY_STRUCTURE_SCHEMA
        if "quote approval policy evidence" in system_text:
            return QUOTE_ARTICLE_EVIDENCE_SCHEMA
        return None

    @staticmethod
    def _quote_dsl_schema_name_for_messages(messages: List[Dict[str, str]]) -> str:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "Knowledge article searches" in system_text:
            return "quote_policy_search_plan"
        if "structured discount policy rules" in system_text:
            return "quote_discount_policy_structure"
        return "quote_article_evidence"

    def _should_use_lead_qualification_dsl(self, env, index) -> bool:
        task = None
        if index is not None and hasattr(env, "tasks"):
            task = env.tasks.get(index) if isinstance(env.tasks, dict) else env.tasks[index]
        elif hasattr(env, "task"):
            task = env.task
        return isinstance(task, dict) and task.get("task") == "lead_qualification"

    def _act_lead_qualification_dsl(self, env, index=None) -> float:
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.info = {"model_calls": 0}
        driver = LeadQualificationDSLDriver(
            model_extractor=self._call_lead_qualification_extractor,
            max_extraction_retries=self.max_dsl_retries,
        )
        result = driver.run(env, task_index=index)
        model_debug_info = {
            key: value for key, value in self.info.items() if key != "model_calls"
        }
        extractor_model_calls = self.info.get("model_calls", 0)
        self.messages = result.messages
        self.info = result.info
        self.info["extractor_model_calls"] = extractor_model_calls
        for key, value in model_debug_info.items():
            self.info.setdefault(key, value)
        self.info["usage"] = self.usage
        self.info["total_cost"] = sum(cost for cost in self.usage["cost"] if cost is not None)
        self.info["num_turns"] = (env.current_user_turn, self.info.get("env_steps", 0))
        return result.reward

    def _call_lead_qualification_extractor(self, messages: List[Dict[str, str]]) -> str:
        schema = self._lead_dsl_schema_for_messages(messages)
        disable_thinking = os.environ.get("LEAD_DSL_DISABLE_THINKING", "true").lower() not in ["0", "false", "no"]
        thinking_extra_body = (
            {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else {}
        )
        structured_output_attempts = None
        if schema is not None:
            schema_name = self._lead_dsl_schema_name_for_messages(messages)
            structured_output_attempts = [
                {
                    "label": "vllm_structured_outputs_json",
                    "response_format": None,
                    "extra_body": self._merge_extra_body(
                        thinking_extra_body,
                        {"structured_outputs": {"json": schema}},
                    ),
                    "require_content": True,
                },
                {
                    "label": "openai_json_schema",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema,
                        },
                    },
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
                {
                    "label": "prompt_only_nonthinking",
                    "response_format": None,
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                },
            ]
        else:
            structured_output_attempts = [
                {
                    "label": "json_object_only",
                    "response_format": {"type": "json_object"},
                    "extra_body": thinking_extra_body or None,
                    "require_content": True,
                }
            ]
        message = self._call_model(
            messages,
            max_tokens=self.lead_dsl_extractor_max_tokens,
            structured_output_attempts=structured_output_attempts,
        )
        self.info.setdefault("lead_dsl_extractor_model_messages", []).append(message)
        return self._model_message_content(message)

    @staticmethod
    def _lead_dsl_schema_for_messages(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "installation policy evidence" in system_text or "Timeline factor" in system_text:
            return TIMELINE_POLICY_SCHEMA
        if "BANT evidence" in system_text:
            return BANT_EXTRACTION_SCHEMA
        return None

    @staticmethod
    def _lead_dsl_schema_name_for_messages(messages: List[Dict[str, str]]) -> str:
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        if "installation policy evidence" in system_text or "Timeline factor" in system_text:
            return "timeline_policy_judgment"
        return "bant_extraction"

    @staticmethod
    def _merge_extra_body(*parts):
        merged = {}
        for part in parts:
            if part:
                merged.update(part)
        return merged or None

    def _call_lead_qualification_clarifier(self, messages: List[Dict[str, str]]) -> str:
        message = self._call_model(messages)
        self.info.setdefault("lead_dsl_clarifier_model_messages", []).append(message)
        return self._model_message_text(message)

    @staticmethod
    def _model_message_text(message: Dict[str, str]) -> str:
        for key in ("content", "reasoning_content"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        additional = message.get("additional_kwargs")
        if isinstance(additional, dict):
            value = additional.get("reasoning_content")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _model_message_content(message: Dict[str, str]) -> str:
        value = message.get("content")
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def message_action_parser(message: str, model_name: str) -> Dict[str, str]:
        action = None
        content = (message.get("content") or "").strip()
        # if model_name "deepseek-r1":
        #     content = content.split("</think>")[1]
        resp = parse_wrapped_response(r'<execute>(.*?)</execute>', content).strip()
        if resp:
            action = {"name": "execute", "content": resp}
            return action
        
        resp = parse_wrapped_response(r'<respond>(.*?)</respond>', content).strip()
        if resp:
            action = {"name": "respond", "content": resp}
            return action
        return action
