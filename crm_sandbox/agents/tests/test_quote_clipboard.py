import unittest

from crm_sandbox.agents.clipboards import QuoteApprovalClipboard
from crm_sandbox.agents.chat_agent import ChatAgent


class QuoteApprovalClipboardTest(unittest.TestCase):
    def test_successful_quote_query_updates_quote_state(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Name, Discount FROM Quote WHERE Id = 'Q1'"},
            [{"Id": "Q1", "Name": "Quote 1", "Discount": 15}],
            {},
        )

        state = clipboard.as_dict()
        self.assertTrue(state["quote_retrieved"])
        self.assertEqual(state["quote_id"], "Q1")
        self.assertEqual(state["stage"], "retrieve_line_items")

    def test_failed_query_does_not_update_quote_state(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Missing__c FROM Quote"},
            "INVALID_FIELD",
            {"end_reason": {"message": "SOQL/SOSL query error"}},
        )

        state = clipboard.as_dict()
        self.assertFalse(state["quote_retrieved"])
        self.assertEqual(state["failed_queries"], ["select missing__c from quote"])

    def test_empty_successful_query_does_not_mark_retrieval(self):
        clipboard = QuoteApprovalClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id FROM Quote WHERE Id = 'missing'"},
            [],
            {},
        )

        state = clipboard.as_dict()
        self.assertFalse(state["quote_retrieved"])
        self.assertEqual(state["stage"], "retrieve_quote")

    def test_line_item_query_updates_line_item_state(self):
        clipboard = QuoteApprovalClipboard()
        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id FROM Quote WHERE Id = 'Q1'"},
            [{"Id": "Q1"}],
            {},
        )

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, QuoteId, Quantity FROM QuoteLineItem WHERE QuoteId = 'Q1'"},
            [{"Id": "QL1", "QuoteId": "Q1"}, {"Id": "QL2", "QuoteId": "Q1"}],
            {},
        )

        state = clipboard.as_dict()
        self.assertTrue(state["line_items_retrieved"])
        self.assertEqual(state["line_item_count"], 2)
        self.assertEqual(state["stage"], "retrieve_candidate_policies")

    def test_policy_search_adds_candidates(self):
        clipboard = self._clipboard_with_quote_and_lines()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "FIND {quote approval} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title)",
            },
            [{"Id": "KA1", "Title": "Quote Approval Policy"}],
            {},
        )

        state = clipboard.as_dict()
        self.assertIn("KA1", state["candidate_policies"])
        self.assertEqual(state["stage"], "inspect_candidate_policies")

    def test_title_only_policy_retrieval_does_not_count_as_inspection(self):
        clipboard = self._clipboard_with_quote_and_lines()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title FROM Knowledge__kav WHERE Id = 'KA1'"},
            [{"Id": "KA1", "Title": "Quote Approval Policy"}],
            {},
        )

        state = clipboard.as_dict()
        self.assertIn("KA1", state["candidate_policies"])
        self.assertEqual(state["inspected_policy_ids"], [])
        self.assertEqual(state["stage"], "inspect_candidate_policies")

    def test_detailed_policy_retrieval_marks_inspection(self):
        clipboard = self._clipboard_with_quote_and_lines()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "SELECT Id, Title, FAQ_Answer__c FROM Knowledge__kav WHERE Id = 'KA1'",
            },
            [{"Id": "KA1", "Title": "Quote Approval Policy", "FAQ_Answer__c": "Approval rules..."}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["inspected_policy_ids"], ["KA1"])
        self.assertEqual(state["stage"], "evaluate_policy")

    def test_response_gate_blocks_each_missing_retrieval_step(self):
        action = {"name": "respond", "content": "None"}
        clipboard = QuoteApprovalClipboard()

        self.assertEqual(clipboard.response_gate(action).error_code, "QUOTE_CLIPBOARD_MISSING_QUOTE")

        clipboard.record_env_step({"name": "execute", "content": "SELECT Id FROM Quote"}, [{"Id": "Q1"}], {})
        self.assertEqual(clipboard.response_gate(action).error_code, "QUOTE_CLIPBOARD_MISSING_LINE_ITEMS")

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id FROM QuoteLineItem"},
            [{"Id": "QL1"}],
            {},
        )
        self.assertEqual(clipboard.response_gate(action).error_code, "QUOTE_CLIPBOARD_MISSING_POLICY_CANDIDATES")

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Title FROM Knowledge__kav"},
            [{"Id": "KA1", "Title": "Quote Approval Policy"}],
            {},
        )
        self.assertEqual(clipboard.response_gate(action).error_code, "QUOTE_CLIPBOARD_MISSING_POLICY_DETAIL")

    def test_response_gate_allows_after_retrieval_complete(self):
        clipboard = self._complete_clipboard()

        result = clipboard.response_gate({"name": "respond", "content": "None"})

        self.assertTrue(result.valid)
        self.assertEqual(result.status, "UNKNOWN")

    def test_render_includes_stage_goal_and_counts(self):
        clipboard = self._complete_clipboard()

        rendered = clipboard.render()

        self.assertIn("# Quote approval clipboard", rendered)
        self.assertIn("Stage: evaluate_policy", rendered)
        self.assertIn("Candidate policies: 1", rendered)
        self.assertIn("Policies inspected: 1", rendered)

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

    def _clipboard_with_quote_and_lines(self):
        clipboard = QuoteApprovalClipboard()
        clipboard.record_env_step({"name": "execute", "content": "SELECT Id FROM Quote"}, [{"Id": "Q1"}], {})
        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, QuoteId FROM QuoteLineItem"},
            [{"Id": "QL1", "QuoteId": "Q1"}],
            {},
        )
        return clipboard

    def _complete_clipboard(self):
        clipboard = self._clipboard_with_quote_and_lines()
        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "SELECT Id, Title, FAQ_Answer__c FROM Knowledge__kav WHERE Id = 'KA1'",
            },
            [{"Id": "KA1", "Title": "Quote Approval Policy", "FAQ_Answer__c": "Approval rules..."}],
            {},
        )
        return clipboard


if __name__ == "__main__":
    unittest.main()
