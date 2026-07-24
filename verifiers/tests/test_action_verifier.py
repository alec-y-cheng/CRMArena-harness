import unittest

from verifiers import ActionVerifier
from verifiers.soql_parser_client import parse_soql


SCHEMA = [
    {
        "object": "Contact",
        "fields": {
            "Id": "Contact id",
            "Name": "Full name",
            "FirstName": "First name",
            "LastName": "Last name",
            "Email": "Email",
            "AccountId": "References Account object",
        },
    },
    {
        "object": "Case",
        "fields": {
            "Id": "Case id",
            "AccountId": "References Account object",
            "Description": "Long text description",
            "Subject": "Subject",
            "Status": "Status",
            "CreatedDate": "Created date",
            "OwnerId": "Owner id",
        },
    },
    {
        "object": "Account",
        "fields": {
            "Id": "Account id",
            "Name": "Account name",
        },
    },
    {
        "object": "Opportunity",
        "fields": {
            "Id": "Opportunity id",
            "AccountId": "References Account object",
            "Name": "Opportunity name",
            "OwnerId": "Owner id",
            "CloseDate": "Close date",
        },
    },
    {
        "object": "OpportunityLineItem",
        "fields": {
            "Id": "Line item id",
            "OpportunityId": "Opportunity id",
            "Product2Id": "Product id",
        },
    },
    {
        "object": "Lead",
        "fields": {
            "Id": "Lead id",
            "CreatedDate": "Date when the lead was created in 'YYYY-MM-DDTHH:MM:SSZ' format",
            "ConvertedDate": "Date when the lead was converted in 'YYYY-MM-DD' format",
            "IsConverted": "Whether the lead converted",
            "OwnerId": "Owner id",
        },
    },
    {
        "object": "Product2",
        "fields": {
            "Id": "Product id",
            "Name": "Product name",
            "Description": "Product description",
        },
    },
    {
        "object": "User",
        "fields": {
            "Id": "User id",
            "ProfileId": "Profile id",
            "FirstName": "First name",
            "LastName": "Last name",
        },
    },
    {
        "object": "Task",
        "fields": {
            "Id": "Task id",
            "OwnerId": "References User object",
            "WhatId": "References Opportunity object",
        },
    },
]


class ActionVerifierTest(unittest.TestCase):
    def setUp(self):
        self.verifier = ActionVerifier.from_schema(SCHEMA)

    def verify(self, action, failed_queries=None):
        return self.verifier.verify_action(action, failed_queries=failed_queries)

    def test_valid_soql(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name FROM Contact WHERE LastName = 'Smith' LIMIT 10"})
        self.assertTrue(result.valid)

    def test_official_soql_parser_accepts_valid_query(self):
        result = parse_soql("SELECT Id, Name FROM Contact WHERE LastName = 'Smith' LIMIT 10")
        self.assertFalse(result.unavailable)
        self.assertTrue(result.success)
        self.assertEqual(result.errors, ())

    def test_official_soql_parser_rejects_malformed_query(self):
        result = parse_soql("SELECT Id, FROM Contact")
        self.assertFalse(result.unavailable)
        self.assertFalse(result.success)
        self.assertTrue(result.errors)

    def test_malformed_soql_rejected_by_official_parser(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, FROM Contact"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")
        self.assertIn("official SOQL parser", result.feedback)

    def test_valid_sosl(self):
        result = self.verify({"name": "execute", "content": "FIND {Smith} IN ALL FIELDS RETURNING Contact(Id, Name), Account(Id, Name)"})
        self.assertTrue(result.valid)

    def test_valid_sosl_with_write_word_in_search_terms(self):
        result = self.verify({"name": "execute", "content": "FIND {customer update request} IN ALL FIELDS RETURNING Case(Id, Subject, OwnerId)"})
        self.assertTrue(result.valid)

    def test_relationship_path_is_not_schema_checked(self):
        result = self.verify({"name": "execute", "content": "SELECT Opportunity.OwnerId, COUNT(Id) FROM OpportunityLineItem GROUP BY Opportunity.OwnerId"})
        self.assertTrue(result.valid)

    def test_child_relationship_subquery_is_not_schema_checked(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name, (SELECT Id FROM OpportunityLineItems) FROM Opportunity"})
        self.assertTrue(result.valid)

    def test_child_relationship_subquery_validates_in_child_context(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name, (SELECT Id, Product2.Name FROM OpportunityLineItems) FROM Opportunity"})
        self.assertTrue(result.valid)

    def test_same_object_prefix_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT Lead.Id, Lead.OwnerId, Owner.FirstName FROM Lead WHERE Lead.CreatedDate >= 2024-01-01T00:00:00Z"})
        self.assertTrue(result.valid)

    def test_invalid_child_relationship_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name, (SELECT Id FROM LeadLineItems) FROM Opportunity"})
        self.assertTrue(result.valid)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.error_code, "UNKNOWN_RELATIONSHIP")

    def test_unknown_parent_relationship_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Bogus.Name FROM OpportunityLineItem"})
        self.assertTrue(result.valid)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.error_code, "UNKNOWN_RELATIONSHIP")

    def test_unknown_parent_relationship_field_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Opportunity.NotAField__c FROM OpportunityLineItem"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNKNOWN_FIELD")

    def test_valid_semijoin_relationship(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Account WHERE Id IN (SELECT AccountId FROM Opportunity)"})
        self.assertTrue(result.valid)

    def test_invalid_semijoin_relationship_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Task WHERE WhatId IN (SELECT Id FROM Lead)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_RELATIONSHIP")

    def test_unknown_object(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Bogus__c"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNKNOWN_OBJECT")

    def test_unknown_field(self):
        result = self.verify({"name": "execute", "content": "SELECT Missing__c FROM Contact"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNKNOWN_FIELD")
        self.assertIn("Available fields from the benchmark schema", result.feedback)
        self.assertIn("Contact.", result.feedback)
        self.assertIn("There may be other valid schema fields not shown here.", result.feedback)

    def test_unknown_related_field_feedback_uses_related_object(self):
        result = self.verify({"name": "execute", "content": "SELECT Opportunity.Missing__c FROM OpportunityLineItem"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNKNOWN_FIELD")
        self.assertIn("relationship 'Opportunity'", result.feedback)
        self.assertIn("Opportunity.", result.feedback)

    def test_empty_action(self):
        result = self.verify({"name": "execute", "content": "   "})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "EMPTY_ACTION")

    def test_unsupported_action(self):
        result = self.verify({"name": "submit", "content": "answer"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNKNOWN_ACTION")

    def test_write_like_query(self):
        result = self.verify({"name": "execute", "content": "DELETE FROM Contact WHERE LastName = 'Smith'"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_QUERY_TYPE")

    def test_count_empty_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT OwnerId, COUNT() FROM Case GROUP BY OwnerId"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_simple_count_empty_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT COUNT() FROM Case WHERE OwnerId = '005xx0000012345AAA'"})
        self.assertTrue(result.valid)

    def test_known_standard_field_omitted_from_compact_schema_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name, Phone, Title FROM Contact"})
        self.assertTrue(result.valid)

    def test_known_omitted_standard_object_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT Id, Name FROM Profile"})
        self.assertTrue(result.valid)

    def test_sql_date_function_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT DATEDIFF(CreatedDate, CloseDate) FROM Opportunity"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_quoted_date_literal_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Opportunity WHERE CloseDate >= '2024-01-01'"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_DATE_LITERAL")

    def test_datetime_field_requires_datetime_literal(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead WHERE CreatedDate >= 2024-01-01"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_DATE_LITERAL")

    def test_datetime_field_accepts_datetime_literal(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead WHERE CreatedDate >= 2024-01-01T00:00:00Z"})
        self.assertTrue(result.valid)

    def test_date_field_rejects_datetime_literal(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead WHERE ConvertedDate >= 2024-01-01T00:00:00Z"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_DATE_LITERAL")

    def test_non_filterable_text_field_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Case WHERE Description LIKE '%outage%'"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "NON_FILTERABLE_FIELD")

    def test_object_specific_description_filter_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Product2 WHERE Description LIKE '%EcoPower%'"})
        self.assertTrue(result.valid)

    def test_datevalue_function_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Opportunity WHERE CloseDate >= DATEVALUE('2023-08-01')"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_group_by_rejects_ungrouped_selected_field(self):
        result = self.verify({"name": "execute", "content": "SELECT OwnerId, Status FROM Case GROUP BY OwnerId"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNGROUPED_SELECTED_FIELD")

    def test_group_by_allows_grouped_fields_and_aggregates(self):
        result = self.verify({"name": "execute", "content": "SELECT OwnerId, COUNT(Id) TotalCases FROM Case GROUP BY OwnerId"})
        self.assertTrue(result.valid)

    def test_join_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Lead.Id FROM Lead JOIN User ON Lead.OwnerId = User.Id"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_union_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead UNION SELECT Id FROM Contact"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_scalar_subquery_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Account WHERE Id = (SELECT ConvertedAccountId FROM Lead WHERE Id = '00Qxx0000000001AAA')"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_as_alias_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT COUNT(Id) AS TotalLeads FROM Lead"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_bare_aggregate_alias_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT OwnerId, COUNT(Id) TotalLeads FROM Lead GROUP BY OwnerId"})
        self.assertTrue(result.valid)

    def test_sql_date_literal_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead WHERE CreatedDate >= DATE '2024-01-01'"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_GRAMMAR")

    def test_year_function_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Lead WHERE YEAR(CreatedDate) = 2024"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_SYNTAX")

    def test_select_distinct_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT DISTINCT OwnerId FROM Opportunity"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_SYNTAX")

    def test_invalid_id_literal_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM User WHERE ProfileId != 'System Administrator'"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_ID_LITERAL")

    def test_deep_relationship_path_rejected(self):
        result = self.verify({"name": "execute", "content": "SELECT Opportunity.OwnerId.FirstName FROM OpportunityLineItem"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOQL_SYNTAX")

    def test_or_inside_semijoin_subquery_allowed(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM User WHERE ProfileId IN (SELECT Id FROM Profile WHERE Name LIKE '%Support%' OR Name LIKE '%Agent%')"})
        self.assertTrue(result.valid)

    def test_sosl_unsearchable_object_rejected(self):
        result = self.verify({"name": "execute", "content": "FIND {VerifySim Elite} IN ALL FIELDS RETURNING Issue__c(Id, Name)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNSEARCHABLE_SOSL_OBJECT")

    def test_sosl_embedded_hyphen_rejected(self):
        result = self.verify({"name": "execute", "content": "FIND {Cirku-Tech} IN ALL FIELDS RETURNING Case(Id, Subject)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_SOSL_SEARCH_TERM")

    def test_sosl_unsupported_field_group_rejected(self):
        result = self.verify({"name": "execute", "content": "FIND {quote approval} IN TITLE FIELDS RETURNING Case(Id, Subject)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNSUPPORTED_SOSL_FIELD_GROUP")

    def test_sosl_empty_search_term_rejected(self):
        result = self.verify({"name": "execute", "content": "FIND {} IN ALL FIELDS RETURNING Case(Id, Subject)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "EMPTY_SOSL_SEARCH_TERM")

    def test_sosl_unbalanced_search_braces_rejected(self):
        result = self.verify({"name": "execute", "content": "FIND {Smith IN ALL FIELDS RETURNING Case(Id, Subject)"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNBALANCED_SEARCH_BRACES")

    def test_unbalanced_quotes(self):
        result = self.verify({"name": "execute", "content": "SELECT Id FROM Contact WHERE LastName = 'Smith"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNBALANCED_QUOTES")

    def test_unbalanced_parentheses(self):
        result = self.verify({"name": "execute", "content": "SELECT COUNT(Id FROM Contact"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "UNBALANCED_PARENTHESES")

    def test_repeated_failed_query(self):
        query = "SELECT Id FROM Contact WHERE LastName = 'Smith'"
        result = self.verify({"name": "execute", "content": query}, failed_queries=[query])
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "REPEATED_FAILED_QUERY")

    def test_repeated_failed_query_ignores_harmless_formatting(self):
        failed_query = "SELECT Id FROM Contact WHERE LastName = 'Smith';"
        query = " select   Id from Contact where LastName='Smith' "
        result = self.verify({"name": "execute", "content": query}, failed_queries=[failed_query])
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "REPEATED_FAILED_QUERY")

    def test_repeated_failed_query_preserves_literal_content(self):
        failed_query = "SELECT Id FROM Contact WHERE LastName = 'Smith'"
        query = "SELECT Id FROM Contact WHERE LastName = 'SMITH'"
        result = self.verify({"name": "execute", "content": query}, failed_queries=[failed_query])
        self.assertTrue(result.valid)

    def test_valid_response(self):
        result = self.verify({"name": "respond", "content": "003xx000004TmiQAAS"})
        self.assertTrue(result.valid)

    def test_empty_response(self):
        result = self.verify({"name": "respond", "content": ""})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "EMPTY_ACTION")

    def test_response_that_looks_like_query(self):
        result = self.verify({"name": "respond", "content": "SELECT Id FROM Contact"})
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "INVALID_RESPONSE_FORMAT")


if __name__ == "__main__":
    unittest.main()
