from typing import Optional, List, Dict, Any, Union
from litellm import completion
import inspect
from crm_sandbox.model_client import completion_with_provider, is_cli_provider


def _completion_accepts_kwargs() -> bool:
    return inspect.getfullargspec(completion).varkw is not None


def _completion_supports_provider() -> bool:
    return "custom_llm_provider" in inspect.getfullargspec(completion).args or _completion_accepts_kwargs()


def _completion_supports_api_kwargs() -> bool:
    argspec = inspect.getfullargspec(completion)
    return argspec.varkw is not None or "api_base" in argspec.args or "api_key" in argspec.args


class LLMUserSimulationEnv(object):
    def __init__(
        self,
        model: str,
        provider: str,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.messages: List[Dict[str, Any]] = []
        self.model = model
        self.provider = provider
        self.api_base = api_base
        self.api_key = api_key
        self.total_cost = 0.0
        self.reset()

    def generate_next_message(self, messages: List[Dict[str, Any]]) -> str:
        completion_kwargs = {}
        if self.api_base and _completion_supports_api_kwargs():
            completion_kwargs["api_base"] = self.api_base
        if self.api_key and _completion_supports_api_kwargs():
            completion_kwargs["api_key"] = self.api_key
        if _completion_supports_provider() and not is_cli_provider(self.provider):
            completion_kwargs["custom_llm_provider"] = self.provider
        res = completion_with_provider(
            provider=self.provider,
            model=self.model,
            messages=messages,
            **completion_kwargs,
        )
        message = res.choices[0].message
        self.messages.append(message.model_dump())
        self.total_cost = res._hidden_params["response_cost"]
        return message.content or ""

    def build_system_prompt(self, instruction: Optional[str], persona: Optional[str]) -> str:
        persona = persona if persona is not None else ""
        instruction = instruction if instruction is not None else ""
        instruction_display = "\n\nInstruction: " + persona + " " + instruction + "\n"
        
        return f"""You are a user interacting with an agent. {instruction_display}
Rules:
- Just generate one line at a time to simulate the user's message.
- You may reason internally, but your visible output must contain only the simulated user's message. Do not reveal a thinking process or analysis.
- Do not give away all the instruction at once. For example, if there are multiple criteria like number of cases and time range, only give away one piece of those information once. It's okay if the instruction is under-specified.
- Alternatively, if the task is about understanding the best transfer count of agent, you can start with an abstract term like "best performing agent" and then the agent should follow up what it means.
- Do not hallucinate information that is not provided in the instruction. For example, if the agent asks for the order id but it is not mentioned in the instruction, do not make up an order id, just say you do not remember or have it.
- Do not repeat the exact instruction in the conversation. Instead, use your own words to convey the same information.
- Try to make the conversation as natural as possible, and stick to the personalities in the instruction.
- The agent may respond with a no answer to your query. This may not be a mistake but they just cannot find any record.
- Below demonstrate two strategies to give away partial information. Feel free to combine them.
- If the instruction goal is satisified, generate '###STOP###' as a standalone message without anything else to end the conversation.
- If the instruction asks about the ID of a person/case/account etc, and the agent respond with the name instead, ask for the ID.
- Try to make the conversation as natural as possible, and stick to the personalities in the instruction.
- The agent may respond "None", which means the agent cannot find any record. In this case, you should reply "###STOP###" to end the conversation.
- When the agent's response successfully fulfills the original instruction's goal, your reply should consist *only* of "###STOP###". Do not add any other text or pleasantries (e.g., "Thank you.").
- If the instruction asks for a short classification, label, ID, name, or list, and the agent replies with a concise final answer such as "None", one label, or comma-separated labels, treat the goal as satisfied and reply only "###STOP###". Do not ask the agent to confirm, explain, or repeat the answer.
- For lead qualification tasks, valid final answers are "None" or one or more of "Budget", "Authority", "Need", and "Timeline". When the agent replies with only those labels, reply only "###STOP###".

# Example 1 (broad -> specific)
Instruction: Which agent has the shortest handle time in Q2 in 2025?
Your output: Hi! I'm trying to figure out which agent performed the best in Q2 in 2025. Could you assist me with that? 


# Example 2 (omitting criteria)
Instruction: Which agent has the shortest handle time in Q2 in 2025?
Your output: Can you tell me which agent has the shortest average handle time?


# Example 3 (completing the goal)
Instruction: Find the Account ID for Acme Corp.
Agent's response: The Account ID for Acme Corp is 001XX000003GXXX.
Your output: ###STOP###

"""

    def reset(self, instruction: Optional[str] = None, persona: Optional[str] = None) -> str:
        self.messages = [
            {
                "role": "system",
                "content": self.build_system_prompt(instruction=instruction, persona=persona),
            },
            {"role": "user", "content": "Hi! How can I help you today?"},
        ]
        # print("user system prompt", self.messages[0]["content"])
        return self.generate_next_message(self.messages)

    def step(self, content: str) -> str:
        self.messages.append({"role": "user", "content": content})
        return self.generate_next_message(self.messages)

    def get_total_cost(self) -> float:
        return self.total_cost
