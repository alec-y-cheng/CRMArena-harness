import os
from litellm import completion
import litellm
litellm.set_verbose = False
from typing import Dict, List, Optional
import time, traceback
from crm_sandbox.agents.prompts import SCHEMA_STRING, REACT_RULE_STRING, ACT_RULE_STRING, SYSTEM_METADATA, REACT_EXTERNAL_INTERACTIVE_PROMPT, REACT_INTERNAL_INTERACTIVE_PROMPT, REACT_INTERNAL_PROMPT, REACT_EXTERNAL_PROMPT, REACT_PRIVACY_AWARE_EXTERNAL_PROMPT, REACT_PRIVACY_AWARE_EXTERNAL_INTERACTIVE_PROMPT, ACT_PROMPT
from crm_sandbox.agents.clipboards import QuoteApprovalClipboard
from crm_sandbox.agents.utils import parse_wrapped_response, BEDROCK_MODELS_MAP, TOGETHER_MODELS_MAP, VERTEX_MODELS_MAP
from crm_sandbox.agents.working_memory import WorkingMemory
from verifiers import ActionVerifier
import together





class ChatAgent:
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
        use_syntactic_verifier=False,
        max_verifier_retries=3,
        agent_max_tokens=2000,
        scaffold_text: Optional[str] = None,
        routing_result: Optional[Dict] = None,
        use_working_memory=False,
        working_memory_max_chars=1200,
        use_quote_clipboard=False,
        quote_clipboard_active=False,
        quote_clipboard_max_chars=1000,
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
        self.usage = {"cost": [], "completion_tokens": [], "prompt_tokens": [], "total_tokens": []}
        self.provider = provider
        self.use_syntactic_verifier = use_syntactic_verifier
        self.max_verifier_retries = max_verifier_retries
        self.action_verifier = ActionVerifier.from_schema(schema_obj) if use_syntactic_verifier else None
        self.agent_max_tokens = agent_max_tokens
        self.scaffold_text = (scaffold_text or "").strip()
        self.routing_result = routing_result or None
        self.use_working_memory = use_working_memory
        self.working_memory = WorkingMemory(max_chars=working_memory_max_chars) if use_working_memory else None
        self.use_quote_clipboard = use_quote_clipboard
        self.quote_clipboard_active = bool(use_quote_clipboard and quote_clipboard_active)
        self.quote_clipboard = (
            QuoteApprovalClipboard(max_chars=quote_clipboard_max_chars)
            if self.quote_clipboard_active
            else None
        )
       
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
        if self.working_memory is not None:
            self.working_memory.reset(args["query"], self.routing_result)
        if self.quote_clipboard is not None:
            self.quote_clipboard.reset(args["query"], self.routing_result)
        
    def act(self, env, index=None, temperature=0.0):
        query, metadata = env.reset(task_index=index)
        self.reset({"query": query, "metadata": metadata})
        # print("----")
        # print(self.sys_prompt)
        # print("----")
        total_cost = 0.0
        self.info["observation_sizes"] = []
        self.info["syntactic_verifier_enabled"] = self.use_syntactic_verifier
        self.info["routing"] = self.routing_result
        self.info["scaffold_injected"] = bool(self.scaffold_text)
        self.info["working_memory_enabled"] = self.use_working_memory
        self.info["working_memory_snapshots"] = []
        self.info["quote_clipboard_enabled"] = self.use_quote_clipboard
        self.info["quote_clipboard_active"] = self.quote_clipboard_active
        self.info["quote_clipboard_snapshots"] = []
        self.info["quote_clipboard_gate_failures"] = []
        if self.working_memory is not None:
            self.info["working_memory_snapshots"].append(
                {
                    "outer_turn": 0,
                    "event": "reset",
                    "state": self.working_memory.as_dict(),
                    "rendered": self.working_memory.render(),
                }
            )
        if self.quote_clipboard is not None:
            self._record_quote_clipboard_snapshot(0, "reset")
        self.info["model_calls"] = 0
        self.info["env_steps"] = 0
        self.info["verification_failures"] = []
        self.info["verification_unknowns"] = []
        done = False
        reward = 0
        failed_queries = []
        message = {"content": ""}
        info = {}
        
        current_agent_turn = 0
        # for turn_id in range(self.max_turns):
        while current_agent_turn < self.max_turns:
            info = {}
            current_agent_turn += 1

            local_messages = self._messages_with_working_memory(self.messages)
            accepted_message = None
            accepted_action = None
            exhausted_verifier_retries = False

            for verifier_attempt in range(self.max_verifier_retries + 1):
                message = self._call_model(local_messages)
                action = self.message_action_parser(message, self.model)
                content = message.get("content") or ""
                stripped_content = content.strip()
                print(
                    "User Turn:", env.current_user_turn,
                    "Agent Turn:", current_agent_turn,
                    "Verifier Attempt:", verifier_attempt,
                    "Agent:", stripped_content,
                )

                if action is None:
                    if verifier_attempt == 0 or verifier_attempt >= self.max_verifier_retries:
                        accepted_message = stripped_content
                        break
                    local_messages.append({"role": "assistant", "content": stripped_content})
                    local_messages.append({"role": "user", "content": REACT_RULE_STRING if self.strategy == "react" else ACT_RULE_STRING})
                    continue

                if self.action_verifier is None:
                    quote_gate = self._quote_clipboard_response_gate(action)
                    if quote_gate is not None and not quote_gate.valid:
                        if self._handle_quote_clipboard_gate_failure(
                            quote_gate,
                            current_agent_turn,
                            verifier_attempt,
                            stripped_content,
                            action,
                            local_messages,
                        ):
                            exhausted_verifier_retries = True
                            break
                        continue
                    accepted_message = stripped_content
                    accepted_action = action
                    break

                verification = self.action_verifier.verify_action(action, failed_queries=failed_queries)
                if verification.valid:
                    if getattr(verification, "status", "VALID") == "UNKNOWN":
                        self.info["verification_unknowns"].append(
                            {
                                "outer_turn": current_agent_turn,
                                "attempt": verifier_attempt + 1,
                                "error_code": verification.error_code,
                                "feedback": verification.feedback,
                                "rule": getattr(verification, "rule", None),
                                "raw_output": stripped_content,
                                "parsed_action": action,
                            }
                        )
                    quote_gate = self._quote_clipboard_response_gate(action)
                    if quote_gate is not None and not quote_gate.valid:
                        if self._handle_quote_clipboard_gate_failure(
                            quote_gate,
                            current_agent_turn,
                            verifier_attempt,
                            stripped_content,
                            action,
                            local_messages,
                        ):
                            exhausted_verifier_retries = True
                            break
                        continue
                    accepted_message = stripped_content
                    accepted_action = action
                    break

                failure = {
                    "outer_turn": current_agent_turn,
                    "attempt": verifier_attempt + 1,
                    "repair_call": verifier_attempt,
                    "error_code": verification.error_code,
                    "feedback": verification.feedback,
                    "raw_output": stripped_content,
                    "parsed_action": action,
                }
                self.info["verification_failures"].append(failure)
                if self.working_memory is not None:
                    self.working_memory.record_verifier_failure(action, verification.error_code)
                    self.info["working_memory_snapshots"].append(
                        {
                            "outer_turn": current_agent_turn,
                            "event": "verifier_failure",
                            "state": self.working_memory.as_dict(),
                            "rendered": self.working_memory.render(),
                        }
                    )
                if self.quote_clipboard is not None:
                    self.quote_clipboard.record_verifier_failure(action, verification.error_code)
                    self._record_quote_clipboard_snapshot(current_agent_turn, "verifier_failure")
                if verifier_attempt >= self.max_verifier_retries:
                    self.info["end_reason"] = {
                        "source": "verifier",
                        "message": verification.error_code,
                        "content": verification.feedback,
                    }
                    info["end_reason"] = self.info["end_reason"]
                    exhausted_verifier_retries = True
                    break
                local_messages.append({"role": "assistant", "content": stripped_content})
                local_messages.append({"role": "user", "content": self._verification_feedback(verification)})

            if exhausted_verifier_retries:
                info["end_reason"] = self.info.get("end_reason", {})
                break

            self.messages.append({"role": "assistant", "content": accepted_message or ""})
            action = accepted_action
            if action is None:
                self.info["end_reason"] = {
                    "source": "agent",
                    "message": "Invalid action",
                    "content":  accepted_message or ""
                }
                info["end_reason"] = self.info["end_reason"]
                if self.strategy == "react":
                    self.messages.append({"role": "user", "content": REACT_RULE_STRING})
                elif self.strategy == "act":
                    self.messages.append({"role": "user", "content": ACT_RULE_STRING})
                continue

            obs, reward, done, info = env.step(action)
            self.info["env_steps"] += 1
            if self.working_memory is not None:
                self.working_memory.record_env_step(action, obs, info)
                self.info["working_memory_snapshots"].append(
                    {
                        "outer_turn": current_agent_turn,
                        "event": f"accepted_{action['name']}",
                        "state": self.working_memory.as_dict(),
                        "rendered": self.working_memory.render(),
                        }
                    )
            if self.quote_clipboard is not None:
                self.quote_clipboard.record_env_step(action, obs, info)
                self._record_quote_clipboard_snapshot(current_agent_turn, f"accepted_{action['name']}")
            
            if "observation_size" in info:
                self.info["observation_sizes"].append(info["observation_size"])
            if "end_reason" in info: # implies error in query
                self.info["end_reason"] = info["end_reason"]
                if (
                    action["name"] == "execute"
                    and info["end_reason"].get("message") == "SOQL/SOSL query error"
                ):
                    failed_queries.append(action["content"])
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

    def _messages_with_working_memory(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if self.working_memory is None and self.quote_clipboard is None:
            return list(messages)
        extra_messages = []
        if self.working_memory is not None:
            extra_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use this compact working memory as a brief, non-authoritative state summary. "
                        "It may be incomplete; rely on the task prompt and Salesforce observations for facts. "
                        "Do not copy this block into the final answer.\n\n"
                        f"{self.working_memory.render()}"
                    ),
                }
            )
        if self.quote_clipboard is not None:
            extra_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use this quote approval clipboard as deterministic retrieval state. "
                        "It tracks what evidence has been retrieved, not whether the quote complies. "
                        "Do not copy this block into the final answer.\n\n"
                        f"{self.quote_clipboard.render()}"
                    ),
                }
            )
        return list(messages) + extra_messages

    def _call_model(self, messages):
        # sleep for non-openai models
        if self.provider != "openai":
            time.sleep(5)
        # turn off thinking for gemini 2.5 flash
        if self.original_model_name == "gemini-2.5-flash-preview-04-17":
            thinking = {"type": "disabled", "budget_tokens": 0}
        elif self.original_model_name == "gemini-2.5-flash-preview-04-17-thinking-4096":
            thinking = {"type": "enabled", "budget_tokens": 4096}
        else:
            thinking = None

        res = completion(
            messages=messages,
            model=self.model,
            temperature=0.0,
            max_tokens=self.agent_max_tokens if self.original_model_name not in ["o1-mini", "o1-preview", "o1-2024-12-17", "deepseek-r1", "o3-mini-2025-01-31", "gemini-2.5-flash-preview-04-17", "gemini-2.5-flash-preview-04-17-thinking-4096", "gemini-2.5-pro-preview-03-25"] else 50000,
            top_p=1.0 if self.model not in ["o3-mini-2025-01-31"] else None,
            thinking=thinking,
            # custom_llm_provider=self.provider,
            additional_drop_params=["temperature"] if self.original_model_name in ["o1-mini", "o1-preview", "o1-2024-12-17", "deepseek-r1", "o3-mini-2025-01-31"] else []
        )

        message = res.choices[0].message.model_dump()
        usage = res.usage
        for key in self.usage.keys():
            if key != "cost":
                self.usage[key].append(usage.get(key, 0))
        self.usage["cost"].append(res._hidden_params["response_cost"])
        self.info["model_calls"] += 1
        return message

    @staticmethod
    def _verification_feedback(verification) -> str:
        return (
            f"Action verification failed [{verification.error_code}]: {verification.feedback}\n"
            "Retry with exactly one Thought and one Action. Use "
            "<execute> one valid read-only SOQL/SOSL query </execute> or "
            "<respond> final answer only </respond>. Do not repeat the rejected action."
        )

    def _quote_clipboard_response_gate(self, action):
        if self.quote_clipboard is None:
            return None
        return self.quote_clipboard.response_gate(action)

    def _handle_quote_clipboard_gate_failure(
        self,
        verification,
        current_agent_turn,
        verifier_attempt,
        stripped_content,
        action,
        local_messages,
    ) -> bool:
        failure = {
            "outer_turn": current_agent_turn,
            "attempt": verifier_attempt + 1,
            "repair_call": verifier_attempt,
            "error_code": verification.error_code,
            "feedback": verification.feedback,
            "raw_output": stripped_content,
            "parsed_action": action,
        }
        self.info["quote_clipboard_gate_failures"].append(failure)
        self._record_quote_clipboard_snapshot(current_agent_turn, "respond_gate_failure")
        if verifier_attempt >= self.max_verifier_retries:
            self.info["end_reason"] = {
                "source": "quote_clipboard",
                "message": verification.error_code,
                "content": verification.feedback,
            }
            return True
        local_messages.append({"role": "assistant", "content": stripped_content})
        local_messages.append({"role": "user", "content": self._quote_clipboard_feedback(verification)})
        return False

    @staticmethod
    def _quote_clipboard_feedback(verification) -> str:
        return (
            f"Quote approval clipboard blocked the response [{verification.error_code}]: {verification.feedback}\n"
            "Retry with exactly one Thought and one Action. Retrieve the missing evidence with "
            "<execute> one valid read-only SOQL/SOSL query </execute>, or use <respond> only after the clipboard prerequisites are complete."
        )

    def _record_quote_clipboard_snapshot(self, turn, event):
        if self.quote_clipboard is None:
            return
        self.info["quote_clipboard_snapshots"].append(
            {
                "turn": turn,
                "event": event,
                "stage": self.quote_clipboard.state.stage,
                "state": self.quote_clipboard.as_dict(),
                "rendered": self.quote_clipboard.render(),
            }
        )

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
