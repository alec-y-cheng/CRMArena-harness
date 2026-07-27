import unittest

from crm_sandbox.agents.chat_agent import ChatAgent
from crm_sandbox.agents.clipboards import LeadQualificationClipboard


class LeadQualificationClipboardTest(unittest.TestCase):
    def test_reset_extracts_lead_id_from_query(self):
        clipboard = LeadQualificationClipboard()

        clipboard.reset("Assess lead 00QWt0000012345AAA for BANT.")

        self.assertEqual(clipboard.as_dict()["lead_id"], "00QWt0000012345AAA")

    def test_successful_lead_query_updates_lead_facts(self):
        clipboard = LeadQualificationClipboard()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "SELECT Id, Name, Company, Status, Rating FROM Lead WHERE Id = '00QWt0000012345AAA'",
            },
            [{"Id": "00QWt0000012345AAA", "Name": "Jane Buyer", "Company": "Acme", "Status": "Open", "Rating": "Hot"}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["lead_id"], "00QWt0000012345AAA")
        self.assertEqual(state["lead_facts"]["Company"], "Acme")
        self.assertEqual(state["stage"], "evidence_ready")
        self.assertIn("Lead facts:", clipboard.render())

    def test_qualification_guide_query_records_policy_evidence(self):
        clipboard = LeadQualificationClipboard()

        clipboard.record_env_step(
            {
                "name": "execute",
                "content": "FIND {BANT qualification guide} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title, FAQ_Answer__c)",
            },
            [{"Id": "KA1", "Title": "Lead Qualification Guide", "FAQ_Answer__c": "Budget, Authority, Need, and Timeline must be assessed."}],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["qualification_guides"][0]["Id"], "KA1")
        self.assertIn("Budget", state["qualification_guides"][0]["FAQ_Answer__c"])

    def test_transcript_query_assigns_bant_evidence_by_keywords(self):
        clipboard = LeadQualificationClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id, Subject, Description FROM Task WHERE WhoId = '00QWt0000012345AAA'"},
            [
                {
                    "Id": "T1",
                    "Subject": "Discovery call",
                    "Description": "The CFO must approve. They have allocated budget and need deployment before Q4.",
                }
            ],
            {},
        )

        evidence = clipboard.as_dict()["bant_evidence"]
        self.assertTrue(evidence["Budget"])
        self.assertTrue(evidence["Authority"])
        self.assertTrue(evidence["Need"])
        self.assertTrue(evidence["Timeline"])

    def test_failed_query_records_warning(self):
        clipboard = LeadQualificationClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Missing__c FROM Lead"},
            "INVALID_FIELD",
            {"end_reason": {"message": "SOQL/SOSL query error"}},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["failed_queries"], ["select missing__c from lead"])
        self.assertTrue(any(item.startswith("Last query failed") for item in state["unresolved"]))

    def test_empty_query_records_no_result_query(self):
        clipboard = LeadQualificationClipboard()

        clipboard.record_env_step(
            {"name": "execute", "content": "SELECT Id FROM Task WHERE Subject LIKE '%missing%'"},
            [],
            {},
        )

        state = clipboard.as_dict()
        self.assertEqual(state["no_result_queries"], ["select id from task where subject like '%missing%'"])
        self.assertTrue(any("returned no records" in item for item in state["unresolved"]))

    def test_response_gate_is_advisory_and_nonblocking(self):
        clipboard = LeadQualificationClipboard()

        result = clipboard.response_gate({"name": "respond", "content": "Budget, Authority"})

        self.assertTrue(result.valid)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.error_code, "LEAD_CLIPBOARD_WARNINGS_ONLY")

    def test_chat_agent_injects_lead_clipboard_only_into_temporary_context(self):
        agent = ChatAgent(
            schema_obj=[{"object": "Lead", "fields": {"Id": "Lead id"}}],
            model="openai/test",
            provider="openai",
            use_lead_clipboard=True,
            lead_clipboard_active=True,
        )
        agent.reset({"query": "Which BANT factors are missing?", "metadata": {"required": ""}})
        persistent_count = len(agent.messages)

        local_messages = agent._messages_with_working_memory(agent.messages)

        self.assertEqual(len(agent.messages), persistent_count)
        self.assertEqual(len(local_messages), persistent_count + 1)
        self.assertIn("Lead qualification clipboard", local_messages[-1]["content"])

    def test_chat_agent_does_not_activate_lead_clipboard_for_non_lead_task(self):
        agent = ChatAgent(
            schema_obj=[{"object": "Quote", "fields": {"Id": "Quote id"}}],
            model="openai/test",
            provider="openai",
            use_lead_clipboard=True,
            lead_clipboard_active=False,
        )
        agent.reset({"query": "Does this quote comply?", "metadata": {"required": ""}})

        local_messages = agent._messages_with_working_memory(agent.messages)

        self.assertEqual(local_messages, agent.messages)
        self.assertIsNone(agent.lead_clipboard)


if __name__ == "__main__":
    unittest.main()
