"""Tests for the canonical spec-driven general runtime driver."""

import json
import unittest

from dsl.general_runtime.driver import CanonicalGeneralRuntimeDriver


class FakeKnowledgeEnv:
    def __init__(self):
        self.user = object()
        self.actions = []

    def step(self, action):
        self.actions.append(dict(action))
        if action["name"] == "execute":
            return (
                [
                    {
                        "Id": "ka0Return",
                        "Title": "Return Policy",
                        "Summary": "Returns must be within 30 days.",
                        "FAQ_Answer__c": "Items can be returned within 30 days of purchase.",
                    }
                ],
                0,
                False,
                {"end_reason": {}},
            )
        if action["name"] == "respond":
            return ("###STOP###", 1, True, {"end_reason": {"content": action["content"]}, "agent_actions": []})
        raise AssertionError("unexpected action: {}".format(action))


class FakeCustomerProductEnv:
    def __init__(self):
        self.user = object()
        self.actions = []

    def step(self, action):
        self.actions.append(dict(action))
        if action["name"] == "execute":
            query = action["content"]
            if "FROM Contact" in query:
                return ([{"Id": "003000000000001AAA", "AccountId": "001000000000001AAA"}], 0, False, {"end_reason": {}})
            if "FIND" in query and "RETURNING Product2" in query:
                return ([{"Id": "01t000000000001AAA", "Name": "High Tech Fitness Bra", "Description": "Connected fitness apparel"}], 0, False, {"end_reason": {}})
            if "FROM OrderItem" in query:
                return ([{"Id": "802000000000001AAA", "OrderId": "801000000000001AAA", "Product2Id": "01t000000000001AAA", "Quantity": 1, "UnitPrice": 79}], 0, False, {"end_reason": {}})
            if "FROM Product2 WHERE Id IN" in query:
                return ([{"Id": "01t000000000001AAA", "Name": "High Tech Fitness Bra", "Description": "Connected fitness apparel"}], 0, False, {"end_reason": {}})
            raise AssertionError("unexpected query: {}".format(query))
        if action["name"] == "respond":
            return ("###STOP###", 1, True, {"end_reason": {"content": action["content"]}, "agent_actions": []})
        raise AssertionError("unexpected action: {}".format(action))


class CannedCanonicalModel:
    def __init__(self):
        self.calls = []

    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_knowledge_qa",
                    "request_summary": "Can I return shoes after 30 days?",
                    "target_entities": [{"entity_type": "product_or_topic", "surface_text": "shoes"}],
                    "query_terms": ["return shoes 30 days"],
                    "product_terms": ["shoes"],
                    "constraints": [],
                    "required_evidence_instances": [
                        {
                            "requirement": "answer_public_customer_question",
                            "evidence_type": "public_warranty_or_returns",
                            "subject_scope": "public",
                            "reason": "return policy question",
                        }
                    ],
                    "missing_information": [],
                }
            )
        if "answer_candidate" in prompt and "Retrieved evidence items" in prompt:
            return json.dumps(
                {
                    "answer_candidate": {
                        "answer": "Items can be returned within 30 days of purchase.",
                        "confidence": "high",
                        "evidence": "The return policy article states a 30-day return window.",
                        "selected_evidence": [
                            {
                                "evidence_id": "ka0Return",
                                "evidence_type": "public_warranty_or_returns",
                                "subject_scope": "public",
                                "safe_to_use": True,
                                "reason": "public return policy",
                            }
                        ],
                        "missing_information": [],
                    }
                }
            )
        if "Disclosure policy:" in prompt:
            return json.dumps(
                {
                    "safe_to_disclose": True,
                    "recommended_action": "answer",
                    "blocked_evidence_ids": [],
                    "blocked_information": [],
                    "reason": "public return policy evidence is safe to disclose",
                }
            )
        raise AssertionError("unexpected prompt: {}".format(prompt[:200]))


class MissingInfoKQAModel(CannedCanonicalModel):
    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_knowledge_qa",
                    "request_summary": "Can I return shoes after 30 days?",
                    "target_entities": [{"entity_type": "product_or_topic", "surface_text": "shoes"}],
                    "query_terms": ["return shoes 30 days"],
                    "product_terms": ["shoes"],
                    "constraints": [],
                    "required_evidence_instances": [
                        {
                            "requirement": "answer_public_customer_question",
                            "evidence_type": "public_warranty_or_returns",
                            "subject_scope": "public",
                            "reason": "return policy question",
                        }
                    ],
                    "missing_information": ["order_id", "purchase_date"],
                }
            )
        return super().__call__(messages)


class CannedCanonicalNEDModel:
    def __init__(self):
        self.calls = []

    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_named_entity_disambiguation",
                    "request_summary": "Find the product ID for a high-tech fitness bra purchased last week.",
                    "target_entities": [{"entity_type": "product", "surface_text": "high-tech fitness bra"}],
                    "query_terms": ["high tech fitness bra"],
                    "product_terms": ["high tech fitness bra"],
                    "constraints": [
                        {
                            "type": "purchase_date_window",
                            "start_date": "2026-07-25",
                            "end_date": "2026-07-25",
                            "source_text": "last week",
                            "is_valid_for_retrieval": True,
                        }
                    ],
                    "required_evidence_instances": [
                        {
                            "requirement": "resolve_current_customer_product",
                            "evidence_type": "current_customer_purchase_history",
                            "subject_scope": "current_customer",
                            "reason": "need customer's matching purchase",
                        },
                        {
                            "requirement": "resolve_current_customer_product",
                            "evidence_type": "product_catalog",
                            "subject_scope": "public",
                            "reason": "need product name/description",
                        },
                    ],
                    "missing_information": [],
                }
            )
        if "answer_candidate" in prompt and "Retrieved evidence items" in prompt:
            return json.dumps(
                {
                    "answer_candidate": {
                        "answer": "01t000000000001AAA",
                        "confidence": "high",
                        "evidence": "The current-customer OrderItem has Product2Id 01t000000000001AAA and the Product2 name matches.",
                        "selected_evidence": [
                            {
                                "evidence_id": "802000000000001AAA",
                                "evidence_type": "current_customer_purchase_history",
                                "subject_scope": "current_customer",
                                "safe_to_use": True,
                                "reason": "current customer's purchase record",
                            },
                            {
                                "evidence_id": "01t000000000001AAA",
                                "evidence_type": "product_catalog",
                                "subject_scope": "public",
                                "safe_to_use": True,
                                "reason": "public product catalog match",
                            },
                        ],
                        "missing_information": [],
                    }
                }
            )
        if "Disclosure policy:" in prompt:
            return json.dumps(
                {
                    "safe_to_disclose": True,
                    "recommended_action": "answer",
                    "blocked_evidence_ids": [],
                    "blocked_information": [],
                    "reason": "current-customer scoped purchase evidence and public product evidence are safe to disclose",
                }
            )
        raise AssertionError("unexpected prompt: {}".format(prompt[:200]))


class AdvisoryMissingNEDModel(CannedCanonicalNEDModel):
    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_named_entity_disambiguation",
                    "request_summary": "Find the product ID for a high-tech fitness bra purchased last week.",
                    "target_entities": [{"entity_type": "product", "surface_text": "high-tech fitness bra"}],
                    "query_terms": ["high tech fitness bra"],
                    "product_terms": ["high tech fitness bra"],
                    "constraints": [
                        {
                            "type": "purchase_date_window",
                            "start_date": "2026-07-25",
                            "end_date": "2026-07-25",
                            "source_text": "last week",
                            "is_valid_for_retrieval": True,
                        }
                    ],
                    "required_evidence_instances": [
                        {
                            "requirement": "resolve_current_customer_product",
                            "evidence_type": "current_customer_purchase_history",
                            "subject_scope": "current_customer",
                            "reason": "need customer's matching purchase",
                        }
                    ],
                    "missing_information": ["specific SKU", "order number"],
                }
            )
        return super().__call__(messages)


class UngroundedDateWindowNEDModel(CannedCanonicalNEDModel):
    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_named_entity_disambiguation",
                    "request_summary": "Find a high support sports bra from past transactions.",
                    "target_entities": [{"entity_type": "product", "surface_text": "high support sports bra"}],
                    "query_terms": ["high support sports bra"],
                    "product_terms": ["high support sports bra"],
                    "constraints": [
                        {
                            "type": "purchase_date_window",
                            "start_date": "2021-02-26",
                            "end_date": "2021-02-26",
                            "source_text": "past transactions",
                            "is_valid_for_retrieval": False,
                        }
                    ],
                    "required_evidence_instances": [
                        {
                            "requirement": "resolve_current_customer_product",
                            "evidence_type": "current_customer_purchase_history",
                            "subject_scope": "current_customer",
                            "reason": "need customer's matching purchase",
                        }
                    ],
                    "missing_information": [],
                }
            )
        return super().__call__(messages)


class InconsistentNoneNEDModel(CannedCanonicalNEDModel):
    def __call__(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "Return an InstanceFrame JSON object" in prompt:
            return json.dumps(
                {
                    "workflow_id": "external_named_entity_disambiguation",
                    "request_summary": "Find the product ID for a high-tech fitness bra purchased last week.",
                    "target_entities": [{"entity_type": "product", "surface_text": "high-tech fitness bra"}],
                    "query_terms": ["high tech fitness bra"],
                    "product_terms": ["high tech fitness bra"],
                    "constraints": [
                        {
                            "type": "purchase_date_window",
                            "start_date": "2026-07-25",
                            "end_date": "2026-07-25",
                            "source_text": "last week",
                            "is_valid_for_retrieval": True,
                        }
                    ],
                    "required_evidence_instances": [],
                    "missing_information": [],
                }
            )
        if "answer_candidate" in prompt and "Retrieved evidence items" in prompt:
            return json.dumps(
                {
                    "answer_candidate": {
                        "answer": None,
                        "confidence": "low",
                        "evidence": "The purchased Product2Id 01t000000000001AAA is the only material match for the requested fitness bra.",
                        "selected_evidence": [
                            {
                                "evidence_id": "802000000000001AAA",
                                "evidence_type": "current_customer_purchase_history",
                                "subject_scope": "current_customer",
                                "safe_to_use": True,
                                "reason": "This purchase record links to Product2Id 01t000000000001AAA, the only product that matches the requested item.",
                            }
                        ],
                        "missing_information": [],
                    }
                }
            )
        if "Disclosure policy:" in prompt:
            return json.dumps(
                {
                    "safe_to_disclose": True,
                    "recommended_action": "answer",
                    "blocked_evidence_ids": [],
                    "blocked_information": [],
                    "reason": "current-customer scoped purchase evidence is safe to disclose",
                }
            )
        raise AssertionError("unexpected prompt: {}".format(prompt[:200]))


class CanonicalGeneralRuntimeDriverTests(unittest.TestCase):
    def test_canonical_kqa_driver_runs_from_spec(self):
        model = CannedCanonicalModel()
        driver = CanonicalGeneralRuntimeDriver("external_knowledge_qa", model, max_extraction_retries=0)
        result = driver.run(
            FakeKnowledgeEnv(),
            initial_query="Can I return shoes after 30 days?",
            initial_metadata={},
        )

        self.assertTrue(result.done)
        self.assertEqual(result.reward, 1)
        self.assertEqual(result.info["workflow_id"], "external_knowledge_qa")
        self.assertEqual(result.info["end_reason"]["content"], "Items can be returned within 30 days of purchase.")
        self.assertEqual(result.info["general_runtime_state"]["answer_candidate"]["confidence"], "high")
        self.assertEqual(len(model.calls), 3)

    def test_canonical_kqa_ignores_advisory_missing_information(self):
        model = MissingInfoKQAModel()
        env = FakeKnowledgeEnv()
        driver = CanonicalGeneralRuntimeDriver("external_knowledge_qa", model, max_extraction_retries=0)
        result = driver.run(
            env,
            initial_query="Can I return damaged running shoes after 30 days?",
            initial_metadata={},
        )

        self.assertTrue(result.done)
        self.assertEqual(result.info["end_reason"]["content"], "Items can be returned within 30 days of purchase.")
        self.assertFalse(any(action["name"] == "respond" and "Could you clarify" in action["content"] for action in env.actions))
        frame = result.info["general_runtime_state"]["instance_frame"]
        self.assertEqual(frame["missing_information"], [])

    def test_canonical_ned_driver_runs_from_spec(self):
        model = CannedCanonicalNEDModel()
        driver = CanonicalGeneralRuntimeDriver("external_named_entity_disambiguation", model, max_extraction_retries=0)
        result = driver.run(
            FakeCustomerProductEnv(),
            initial_query="Can you find the product ID for a high-tech fitness bra I purchased last week?",
            initial_metadata={"required": {"customer_id": "003000000000001AAA", "today": "2026-08-01"}},
        )

        self.assertTrue(result.done)
        self.assertEqual(result.reward, 1)
        self.assertEqual(result.info["workflow_id"], "external_named_entity_disambiguation")
        self.assertEqual(result.info["end_reason"]["content"], "01t000000000001AAA")
        self.assertIn("OrderItem", result.info["general_runtime_state"]["retrieved_records"])
        order_item = result.info["general_runtime_state"]["retrieved_records"]["OrderItem"][0]
        self.assertEqual(order_item["__symbolic_context"]["date_window"], ["2026-07-25", "2026-07-25"])
        self.assertIn("filtered", order_item["__symbolic_context"]["date_window_guarantee"])
        self.assertEqual(len(model.calls), 3)

    def test_canonical_ned_ignores_advisory_missing_information_when_required_fields_exist(self):
        model = AdvisoryMissingNEDModel()
        env = FakeCustomerProductEnv()
        driver = CanonicalGeneralRuntimeDriver("external_named_entity_disambiguation", model, max_extraction_retries=0)
        result = driver.run(
            env,
            initial_query="Can you find the product ID for a high-tech fitness bra I purchased last week?",
            initial_metadata={"required": {"customer_id": "003000000000001AAA", "today": "2026-08-01"}},
        )

        self.assertTrue(result.done)
        self.assertEqual(result.info["end_reason"]["content"], "01t000000000001AAA")
        self.assertFalse(any(action["name"] == "respond" and "Could you clarify" in action["content"] for action in env.actions))
        frame = result.info["general_runtime_state"]["instance_frame"]
        self.assertEqual(frame["missing_information"], [])

    def test_canonical_ned_rejects_ungrounded_date_window(self):
        model = UngroundedDateWindowNEDModel()
        env = FakeCustomerProductEnv()
        driver = CanonicalGeneralRuntimeDriver("external_named_entity_disambiguation", model, max_extraction_retries=0)
        result = driver.run(
            env,
            initial_query="Can you find a high support sports bra from my past transactions?",
            initial_metadata={"required": {"customer_id": "003000000000001AAA", "today": "2021-02-26"}},
        )

        self.assertTrue(result.done)
        self.assertTrue(any(action["name"] == "respond" and "purchase date or timeframe" in action["content"] for action in env.actions))
        self.assertFalse(any(action["name"] == "execute" and "FROM OrderItem" in action["content"] for action in env.actions))

    def test_canonical_ned_repairs_inconsistent_none_answer(self):
        model = InconsistentNoneNEDModel()
        driver = CanonicalGeneralRuntimeDriver("external_named_entity_disambiguation", model, max_extraction_retries=0)
        result = driver.run(
            FakeCustomerProductEnv(),
            initial_query="Can you find the product ID for a high-tech fitness bra I purchased last week?",
            initial_metadata={"required": {"customer_id": "003000000000001AAA", "today": "2026-08-01"}},
        )

        self.assertTrue(result.done)
        self.assertEqual(result.info["end_reason"]["content"], "01t000000000001AAA")
        self.assertEqual(result.info["general_runtime_state"]["answer_candidate"]["answer"], "01t000000000001AAA")
        self.assertEqual(result.info["answer_repairs"][0]["type"], "entity_id_none_consistency_repair")


if __name__ == "__main__":
    unittest.main()
