import unittest

from dsl.lead_qualification.actions import (
    TimelinePolicyJudgment,
    apply_timeline_policy_judgment,
    compute_budget_total,
    extract_target_lead_id,
    query_installation_policy,
    query_lead,
    query_pricebook_entries,
    query_products_by_name,
    query_voice_call_transcripts,
    render_failed_bant_response,
    respond_to_user,
)
from dsl.lead_qualification.harness import LeadQualificationDSLDriver
from dsl.lead_qualification.parser import (
    BANTParseError,
    parse_bant_json,
    parse_timeline_policy_judgment_json,
)


STRICT_EXTRACTION = """
{
  "Budget": {"status": "supported", "evidence": "Budget is approved."},
  "Authority": {"status": "failed", "evidence": "The CFO must approve."},
  "Need": {"status": "supported", "evidence": "They need compliance reporting."},
  "Timeline": {"status": "supported", "evidence": "They can deploy next quarter."}
}
"""


class FakeEnv:
    def __init__(self, task_query, model_answer="Authority", stop_observation="DONE"):
        self.tasks = {
            14: {
                "task": "lead_qualification",
                "query": task_query,
                "metadata": {"required": ""},
                "answer": model_answer,
            }
        }
        self.current_user_turn = 0
        self.actions = []
        self.stop_observation = stop_observation

    def reset(self, task_index=14):
        self.task = self.tasks[task_index]
        self.actions = []
        return self.task["query"], self.task["metadata"]

    def step(self, action):
        self.actions.append(action)
        if action["name"] == "respond":
            reward = 1 if action["content"] == self.task["answer"] else 0
            info = {
                "end_reason": {
                    "source": "agent",
                    "message": "Submit action",
                    "content": action["content"],
                    "parsed_answer": action["content"],
                },
                "agent_actions": self.actions,
            }
            done = self.stop_observation == "DONE"
            return self.stop_observation, reward, done, info

        query = action["content"]
        if "FROM Lead" in query:
            records = [{"Id": "00QWt0000012345AAA", "Company": "Acme"}]
        elif "FROM VoiceCallTranscript__c" in query:
            records = [
                {
                    "Id": "V1",
                    "LeadId__c": "00QWt0000012345AAA",
                    "Body__c": "The CFO must approve. We need compliance reporting.",
                }
            ]
        else:
            records = []
        return str(records), 0, False, {"observation_size": len(records), "agent_actions": self.actions}

    def calculate_reward(self):
        answer = self.actions[-1]["content"]
        return {"reward": 1 if answer == self.task["answer"] else 0, "parsed_answer": answer}


class InteractiveFakeEnv(FakeEnv):
    def __init__(self, task_query, model_answer="Authority"):
        super().__init__(task_query=task_query, model_answer=model_answer)
        self.user = object()
        self._clarified = False

    def step(self, action):
        self.actions.append(action)
        if action["name"] == "respond" and not self._clarified:
            self._clarified = True
            observation = "The Lead ID is 00QWt0000012345AAA."
            return (
                observation,
                0,
                False,
                {
                    "end_reason": {"source": "user", "message": "Respond action", "content": observation},
                    "agent_actions": self.actions,
                },
            )

        if action["name"] == "respond":
            reward = 1 if action["content"] == self.task["answer"] else 0
            return (
                "DONE",
                reward,
                True,
                {
                    "end_reason": {
                        "source": "agent",
                        "message": "Submit action",
                        "content": action["content"],
                        "parsed_answer": action["content"],
                    },
                    "agent_actions": self.actions,
                },
            )

        self.actions.pop()
        return super().step(action)


class LeadQualificationDSLTest(unittest.TestCase):
    def test_lead_id_extraction_from_task_prompt(self):
        self.assertEqual(
            extract_target_lead_id("Determine failed BANT factors for lead 00QWt0000012345AAA."),
            "00QWt0000012345AAA",
        )
        self.assertIsNone(extract_target_lead_id("Determine failed BANT factors for this account."))
        self.assertIn("Lead ID", respond_to_user("target_lead_id"))

    def test_soql_templates_are_known_good_shapes(self):
        lead_id = "00QWt0000012345AAA"
        self.assertEqual(
            query_lead(lead_id),
            "SELECT Id, FirstName, LastName, Company, Email, Phone, Status, Title, "
            "CreatedDate, ConvertedDate, IsConverted, OwnerId FROM Lead WHERE Id = '00QWt0000012345AAA'",
        )
        self.assertEqual(
            query_voice_call_transcripts(lead_id),
            "SELECT Id, LeadId__c, Body__c, CreatedDate, EndTime__c "
            "FROM VoiceCallTranscript__c WHERE LeadId__c = '00QWt0000012345AAA'",
        )
        self.assertIn("FROM Product2 WHERE Name LIKE '%CircuitMaster%'", query_products_by_name(["CircuitMaster"]))
        self.assertEqual(
            query_pricebook_entries(["01tWt000006hOd8IAE"]),
            "SELECT Id, Product2Id, Pricebook2Id, UnitPrice "
            "FROM PricebookEntry WHERE Product2Id IN ('01tWt000006hOd8IAE')",
        )
        policy_query = query_installation_policy()
        self.assertIn("RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)", policy_query)
        self.assertNotIn("WHERE FAQ_Answer__c", policy_query)

    def test_compute_budget_total_defaults_missing_quantities_to_one_each(self):
        products = [
            {"Id": "P1", "Name": "SecureData Nexus"},
            {"Id": "P2", "Name": "PulseSim Pro"},
        ]
        pricebook_entries = [
            {"Product2Id": "P1", "UnitPrice": 599.99},
            {"Product2Id": "P2", "UnitPrice": 499.99},
        ]

        self.assertEqual(
            str(compute_budget_total(products, pricebook_entries, {})),
            "1099.98",
        )

    def test_compute_budget_total_uses_explicit_quantities_when_present(self):
        products = [
            {"Id": "P1", "Name": "SecureData Nexus"},
            {"Id": "P2", "Name": "PulseSim Pro"},
        ]
        pricebook_entries = [
            {"Product2Id": "P1", "UnitPrice": 599.99},
            {"Product2Id": "P2", "UnitPrice": 499.99},
        ]

        self.assertEqual(
            str(
                compute_budget_total(
                    products,
                    pricebook_entries,
                    {"SecureData Nexus": 2, "PulseSim Pro": 3},
                )
            ),
            "2699.95",
        )

    def test_bant_json_parser_rejects_malformed_factors_and_statuses(self):
        state = parse_bant_json(STRICT_EXTRACTION)
        self.assertEqual(state.factors["Authority"].status, "failed")

        state_with_thinking = parse_bant_json(
            """
            <think>{"irrelevant": "reasoning with braces"}</think>
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "failed", "evidence": "The CFO must approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "They can deploy next quarter."}
            }
            """
        )
        self.assertEqual(state_with_thinking.factors["Authority"].status, "failed")

        state_with_reasoning = parse_bant_json(
            """
            {
              "reasoning": "Authority is the only failed factor.",
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "failed", "evidence": "The CFO must approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "They can deploy next quarter."}
            }
            """
        )
        self.assertEqual(state_with_reasoning.factors["Authority"].status, "failed")

        with self.assertRaises(BANTParseError):
            parse_bant_json('{"Budget": {"status": "maybe", "evidence": ""}}')

        state_with_timeline_fields = parse_bant_json(
            """
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "supported", "evidence": "Buyer can approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "Seller can accommodate the timeline."},
              "requested_timeline_days": 2,
              "client_timeline": "Customer asked for setup within two days.",
              "seller_timeline_feasibility": "Seller said they can prioritize the installation.",
              "seller_timeline_commitment_strength": "generic"
            }
            """
        )
        self.assertEqual(state_with_timeline_fields.requested_timeline_days, 2)
        self.assertIn("two days", state_with_timeline_fields.client_timeline)
        self.assertIn("prioritize", state_with_timeline_fields.seller_timeline_feasibility)
        self.assertEqual(state_with_timeline_fields.seller_timeline_commitment_strength, "generic")

        state_with_quantities = parse_bant_json(
            """
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "supported", "evidence": "Buyer can approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "Seller can accommodate the timeline."},
              "product_names": ["CloudLink Designer", "DesignWave Automation"],
              "quantities": {"CloudLink Designer": 2, "DesignWave Automation": 3}
            }
            """
        )
        self.assertEqual(state_with_quantities.total_requested_units, 5)

        state_with_product_bundle = parse_bant_json(
            """
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "supported", "evidence": "Buyer can approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "Seller can accommodate the timeline."},
              "product_names": ["CloudLink Designer", "DesignWave Automation", "Workflow Genius"]
            }
            """
        )
        self.assertEqual(state_with_product_bundle.total_requested_units, 3)

        with self.assertRaises(BANTParseError):
            parse_bant_json(
                """
                {
                  "Budget": {"status": "supported", "evidence": ""},
                  "Authority": {"status": "supported", "evidence": ""},
                  "Need": {"status": "supported", "evidence": ""},
                  "Timeline": {"status": "supported", "evidence": ""},
                  "client_timeline": ["urgent"]
                }
                """
            )

    def test_timeline_policy_judgment_parser_rejects_invalid_statuses(self):
        judgment = parse_timeline_policy_judgment_json(
            """
            {
              "reasoning": "The requested timeline is shorter than the policy duration.",
              "required_installation_days": 3,
              "policy_evidence": "The applicable policy requires three days.",
              "Timeline": {
                "status": "failed",
                "evidence": "Customer requested two days, but policy requires three."
              }
            }
            """
        )
        self.assertEqual(judgment.required_installation_days, 3)
        self.assertEqual(judgment.timeline_status, "failed")

        with self.assertRaises(BANTParseError):
            parse_timeline_policy_judgment_json(
                """
                {
                  "required_installation_days": 3,
                  "policy_evidence": "The applicable policy requires three days.",
                  "Timeline": {"status": "urgent", "evidence": ""}
                }
                """
            )

    def test_final_renderer_contract(self):
        self.assertEqual(render_failed_bant_response({"Budget": {"status": "failed"}}), "Budget")
        self.assertEqual(
            render_failed_bant_response(
                {
                    "Budget": {"status": "failed"},
                    "Authority": {"status": "failed"},
                    "Need": {"status": "supported"},
                    "Timeline": {"status": "unknown"},
                }
            ),
            "Budget, Authority",
        )
        self.assertEqual(render_failed_bant_response({}), "None")

    def test_replay_task_14_returns_only_authority_after_transcript(self):
        env = FakeEnv("Which BANT factors fail for lead 00QWt0000012345AAA?")
        driver = LeadQualificationDSLDriver(lambda _messages: STRICT_EXTRACTION)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[-1], {"name": "respond", "content": "Authority"})
        self.assertTrue(any("VoiceCallTranscript__c" in action["content"] for action in env.actions))

    def test_interactive_missing_lead_id_asks_user_then_continues(self):
        env = InteractiveFakeEnv("Can you check which BANT factors fail for this lead?")
        driver = LeadQualificationDSLDriver(lambda _messages: STRICT_EXTRACTION)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[0]["name"], "respond")
        self.assertIn("Lead ID", env.actions[0]["content"])
        self.assertTrue(any(action["name"] == "execute" and "FROM Lead" in action["content"] for action in env.actions))
        self.assertTrue(any("VoiceCallTranscript__c" in action["content"] for action in env.actions))
        self.assertEqual(env.actions[-1], {"name": "respond", "content": "Authority"})

    def test_noninteractive_missing_lead_id_does_not_clarify(self):
        env = FakeEnv("Can you check which BANT factors fail for this lead?", model_answer="None")
        driver = LeadQualificationDSLDriver(lambda _messages: STRICT_EXTRACTION)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions, [{"name": "respond", "content": "None"}])
        self.assertEqual(result.info["missing_requirements"], ["target_lead_id"])

    def test_replay_task_9_stops_at_need_after_transcript_evidence(self):
        extraction = """
        {
          "Budget": {"status": "supported", "evidence": "Budget is approved."},
          "Authority": {"status": "supported", "evidence": "Decision maker is on the call."},
          "Need": {"status": "failed", "evidence": "They said there is no current business need."},
          "Timeline": {"status": "supported", "evidence": "They can deploy this quarter."}
        }
        """
        env = FakeEnv(
            "Which BANT factors fail for lead 00QWt0000012345AAA?",
            model_answer="Need",
        )
        driver = LeadQualificationDSLDriver(lambda _messages: extraction)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[-1]["content"], "Need")

    def test_timeline_policy_judgment_updates_timeline(self):
        state = parse_bant_json(
            """
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "supported", "evidence": "Buyer can approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "unknown", "evidence": "They asked for two day deployment."},
              "quantities": {"CircuitMaster Analyzer": 5},
              "requested_timeline_days": 2,
              "client_timeline": "They asked for two day deployment.",
              "seller_timeline_feasibility": "Seller said they can try to prioritize it."
            }
            """
        )
        judgment = TimelinePolicyJudgment(
            required_installation_days=3,
            policy_evidence="Applicable policy requires three days.",
            timeline_status="failed",
            timeline_evidence="Customer requested two days, but policy requires three.",
        )

        apply_timeline_policy_judgment(state, judgment)

        self.assertEqual(state.policy_required_installation_days, 3)
        self.assertEqual(state.factors["Timeline"].status, "failed")

    def test_timeline_policy_prompt_uses_customer_timeline_and_total_units(self):
        state = parse_bant_json(
            """
            {
              "Budget": {"status": "supported", "evidence": "Budget is approved."},
              "Authority": {"status": "supported", "evidence": "Buyer can approve."},
              "Need": {"status": "supported", "evidence": "They need compliance reporting."},
              "Timeline": {"status": "supported", "evidence": "Seller can accommodate the timeline."},
              "product_names": ["CloudLink Designer", "DesignWave Automation", "Workflow Genius"],
              "requested_timeline_days": 2,
              "client_timeline": "Customer asked for setup within two days.",
              "seller_timeline_feasibility": "Seller said they can accommodate that timeline.",
              "seller_timeline_commitment_strength": "generic"
            }
            """
        )

        from dsl.lead_qualification.actions import extract_timeline_policy_judgment_prompt

        prompt = extract_timeline_policy_judgment_prompt(state, [])

        self.assertIn("'total_requested_units': 3", prompt)
        self.assertIn("total deployment", prompt)
        self.assertIn("customer's requested timeline", prompt)
        self.assertIn("independent disqualifying reason", prompt)
        self.assertIn("seller_timeline_commitment_strength", prompt)

    def test_driver_uses_llm_policy_judgment_for_explicit_timeline(self):
        extraction = """
        {
          "Budget": {"status": "supported", "evidence": "Budget is approved."},
          "Authority": {"status": "supported", "evidence": "Buyer can approve."},
          "Need": {"status": "supported", "evidence": "They need compliance reporting."},
          "Timeline": {"status": "supported", "evidence": "Seller can prioritize two day deployment."},
          "quantities": {"CircuitMaster Analyzer": 5},
          "requested_timeline_days": 2,
          "client_timeline": "Customer asked for two day deployment.",
          "seller_timeline_feasibility": "Seller can prioritize it.",
          "seller_timeline_commitment_strength": "generic"
        }
        """
        policy_judgment = """
        {
          "required_installation_days": 3,
          "policy_evidence": "The applicable installation policy requires three days.",
          "Timeline": {
            "status": "failed",
            "evidence": "Customer requested two days, but policy requires three days."
          }
        }
        """
        outputs = [extraction, policy_judgment]
        env = FakeEnv(
            "Which BANT factors fail for lead 00QWt0000012345AAA?",
            model_answer="Timeline",
        )
        driver = LeadQualificationDSLDriver(lambda _messages: outputs.pop(0))

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[-1]["content"], "Timeline")
        self.assertTrue(any("Knowledge__kav" in action["content"] for action in env.actions))

    def test_driver_skips_policy_for_strong_seller_timeline_commitment(self):
        extraction = """
        {
          "Budget": {"status": "supported", "evidence": "Budget is approved."},
          "Authority": {"status": "supported", "evidence": "Buyer can approve."},
          "Need": {"status": "supported", "evidence": "They need compliance reporting."},
          "Timeline": {"status": "supported", "evidence": "Seller committed to two day deployment."},
          "quantities": {"CircuitMaster Analyzer": 5},
          "requested_timeline_days": 2,
          "client_timeline": "Customer asked for two day deployment.",
          "seller_timeline_feasibility": "Seller committed to complete installation within two days for this order.",
          "seller_timeline_commitment_strength": "strong"
        }
        """
        env = FakeEnv(
            "Which BANT factors fail for lead 00QWt0000012345AAA?",
            model_answer="None",
        )
        driver = LeadQualificationDSLDriver(lambda _messages: extraction)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[-1]["content"], "None")
        self.assertFalse(any("Knowledge__kav" in action["content"] for action in env.actions))
        self.assertEqual(
            result.info["timeline_policy_skipped"]["reason"],
            "strong_seller_timeline_commitment",
        )

    def test_driver_skips_policy_for_vague_client_timeline_without_requested_days(self):
        extraction = """
        {
          "Budget": {"status": "supported", "evidence": "Budget is approved."},
          "Authority": {"status": "failed", "evidence": "The CFO must approve."},
          "Need": {"status": "supported", "evidence": "They need compliance reporting."},
          "Timeline": {"status": "supported", "evidence": "Seller said the team can work with a tight timeline."},
          "client_timeline": "The customer has a tight timeline for installation.",
          "seller_timeline_feasibility": "Seller said the team can work with the timeline."
        }
        """
        env = FakeEnv(
            "Which BANT factors fail for lead 00QWt0000012345AAA?",
            model_answer="Authority",
        )
        driver = LeadQualificationDSLDriver(lambda _messages: extraction)

        result = driver.run(env, task_index=14)

        self.assertEqual(result.reward, 1)
        self.assertEqual(env.actions[-1]["content"], "Authority")
        self.assertFalse(any("Knowledge__kav" in action["content"] for action in env.actions))
        self.assertNotIn("timeline_policy_extraction_error", result.info)


if __name__ == "__main__":
    unittest.main()
