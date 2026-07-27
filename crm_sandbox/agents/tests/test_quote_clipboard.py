import unittest

from crm_sandbox.agents.chat_agent import ChatAgent
from crm_sandbox.agents.clipboards import QuoteApprovalClipboard


class QuoteApprovalClipboardTest(unittest.TestCase):
    def test_successful_quote_query_updates_decision_facts(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "SELECT Id, Name, Status, TotalPrice, Discount FROM Quote WHERE Id = 'Q1'",
            },
            [{"Id": "Q1", "Name": "Quote 1", "Status": "Needs Review", "TotalPrice": 1000, "Discount": 10}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["quote_facts"]["Id"], "Q1")
        self.assertEqual(state["quote_facts"]["TotalPrice"], 1000)
        self.assertEqual(state["stage"], "evidence_ready")
        self.assertIn("line-item", clipboard.render())

    def test_failed_query_records_warning_without_evidence_update(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Missing__c FROM Quote"},
            "INVALID_FIELD",
            {"end_reason": {"message": "SOQL/SOSL query error"}},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["quote_facts"], {})
        self.assertEqual(state["failed_queries"], ["select missing__c from quote"])
        self.assertTrue(any(item.startswith("Last query failed") for item in state["unresolved"]))

    def test_empty_successful_query_adds_nonblocking_warning(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id FROM Quote WHERE Id = 'missing'"},
            [],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["quote_facts"], {})
        self.assertIn("Last query returned no records; confirm whether this evidence is unnecessary before answering.", state["unresolved"])

    def test_line_item_query_updates_line_item_facts(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, QuoteId, Quantity, UnitPrice, Discount FROM QuoteLineItem WHERE QuoteId = 'Q1'"},
            [
                {"Id": "QL1", "QuoteId": "Q1", "Quantity": 2, "UnitPrice": 100, "Discount": 5},
                {"Id": "QL2", "QuoteId": "Q1", "Quantity": 3, "UnitPrice": 200, "Discount": 0},
            ],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(len(state["line_items"]), 2)
        self.assertEqual(state["line_items"][0]["Quantity"], 2)
        self.assertEqual(state["line_items"][1]["UnitPrice"], 200)

    def test_policy_search_stores_compact_evidence(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "FIND {quote approval} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title, FAQ_Answer__c)",
            },
            [{"Id": "KA1", "Title": "Quote Approval Policy", "FAQ_Answer__c": "Discounts over 20 percent require approval."}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["policy_evidence"][0]["Id"], "KA1")
        self.assertIn("Discounts over 20", state["policy_evidence"][0]["FAQ_Answer__c"])

    def test_bundle_policy_does_not_satisfy_discount_request(self):
        clipboard = QuoteApprovalClipboard()
        clipboard.reset("Does this quote's price and configuration comply with company policy?")

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title, FAQ_Answer__c FROM Knowledge__kav"},
            [
                {
                    "Id": "KBUNDLE",
                    "Title": "Mandatory Bundles for Quotes",
                    "FAQ_Answer__c": "CloudLink Designer must also include DesignEdge Pro and AI DesignShift.",
                }
            ],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["requested_policy_dimensions"], ["discount"])
        self.assertEqual(state["policy_evidence"], [])
        self.assertEqual(state["policy_evidence_by_type"]["bundle"][0]["Id"], "KBUNDLE")
        self.assertTrue(any("different policy dimension" in item for item in state["unresolved"]))
        self.assertIn("not the requested policy dimension", clipboard.render())

    def test_discount_policy_satisfies_discount_request(self):
        clipboard = QuoteApprovalClipboard()
        clipboard.reset("Does this quote's price comply with company policy?")

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title, FAQ_Answer__c FROM Knowledge__kav"},
            [
                {
                    "Id": "KDISCOUNT",
                    "Title": "Volume-Based Discounts",
                    "FAQ_Answer__c": "10% discount applies for purchases over $10 and 15% for purchases over $20.",
                }
            ],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["requested_policy_dimensions"], ["discount"])
        self.assertEqual(state["policy_evidence"][0]["Id"], "KDISCOUNT")
        self.assertFalse(any("No relevant policy" in item for item in state["unresolved"]))

    def test_title_only_policy_retrieval_still_records_candidate_evidence(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title FROM Knowledge__kav WHERE Id = 'KA1'"},
            [{"Id": "KA1", "Title": "Quote Approval Policy"}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["policy_evidence"][0]["Id"], "KA1")
        self.assertEqual(state["policy_evidence"][0]["Title"], "Quote Approval Policy")

    def test_response_gate_is_advisory_and_nonblocking(self):
        clipboard = QuoteApprovalClipboard()

        result = clipboard.response_gate({"name": "respond", "content": "None"})

        self.assertTrue(result.valid)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.error_code, "QUOTE_CLIPBOARD_WARNINGS_ONLY")

    def test_render_includes_decision_evidence_sections(self):
        clipboard = self._complete_clipboard()

        rendered = clipboard.render()

        self.assertIn("# Quote approval clipboard", rendered)
        self.assertIn("Quote facts:", rendered)
        self.assertIn("Line-item facts:", rendered)
        self.assertIn("Policy evidence:", rendered)
        self.assertIn("article Id or None", rendered)

    def test_missing_evidence_warnings_are_recomputed(self):
        clipboard = self._complete_clipboard()

        unresolved = clipboard.as_dict()["unresolved"]

        self.assertFalse(any("No quote facts" in item for item in unresolved))
        self.assertFalse(any("No line-item" in item for item in unresolved))
        self.assertFalse(any("No policy/article" in item for item in unresolved))

    def test_chat_agent_injects_clipboard_only_into_temporary_context(self):
        agent = ChatAgent(
            schema_obj=[{"object": "Quote", "fields": {"Id": "Quote id"}}],
            model="openai/test",
            provider="openai",
            use_quote_clipboard=True,
            quote_clipboard_active=True,
        )
        agent.reset({"query": "Does this quote comply?", "metadata": {"required": ""}})
        persistent_count = len(agent.messages)

        local_messages = agent._messages_with_working_memory(agent.messages)

        self.assertEqual(len(agent.messages), persistent_count)
        self.assertEqual(len(local_messages), persistent_count + 1)
        self.assertIn("Quote approval clipboard", local_messages[-1]["content"])

    def test_chat_agent_does_not_activate_clipboard_for_non_quote_task(self):
        agent = ChatAgent(
            schema_obj=[{"object": "Lead", "fields": {"Id": "Lead id"}}],
            model="openai/test",
            provider="openai",
            use_quote_clipboard=True,
            quote_clipboard_active=False,
        )
        agent.reset({"query": "Does this lead qualify?", "metadata": {"required": ""}})

        local_messages = agent._messages_with_working_memory(agent.messages)

        self.assertEqual(local_messages, agent.messages)
        self.assertIsNone(agent.quote_clipboard)

    def _complete_clipboard(self):
        clipboard = QuoteApprovalClipboard()
        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Name, TotalPrice FROM Quote WHERE Id = 'Q1'"},
            [{"Id": "Q1", "Name": "Quote 1", "TotalPrice": 1000}],
            {},
        )
        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, QuoteId, Quantity, UnitPrice, Discount FROM QuoteLineItem"},
            [{"Id": "QL1", "QuoteId": "Q1", "Quantity": 2, "UnitPrice": 100, "Discount": 5}],
            {},
        )
        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title, FAQ_Answer__c FROM Knowledge__kav WHERE Id = 'KA1'"},
            [{"Id": "KA1", "Title": "Quote Approval Policy", "FAQ_Answer__c": "Discounts over 20 percent require approval."}],
            {},
        )
        return clipboard


if __name__ == "__main__":
    unittest.main()
