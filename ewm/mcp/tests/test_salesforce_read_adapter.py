import unittest

from ewm.ir.environment import build_environment_ir_from_mcp_schema, reachable_information
from ewm.ir.state import ExecutionState
from ewm.mcp.client import MCPCall
from ewm.mcp.normalizer import normalize_observation, to_observation
from ewm.mcp.salesforce_read_adapter import SalesforceReadMCPAdapter
from ewm.mcp.salesforce_reads import SalesforceReadsClient


class FakeSObject:
    def __init__(self, describe_payload):
        self.describe_payload = describe_payload

    def describe(self):
        return self.describe_payload


class FakeSalesforce:
    def __init__(self):
        self.sf_instance = "example.my.salesforce.com"
        self.queries = []

    def describe(self):
        return {
            "sobjects": [
                {"name": "Account", "label": "Account", "queryable": True, "searchable": True},
                {"name": "InternalOnly", "label": "Internal Only", "queryable": False, "searchable": False},
            ]
        }

    def query_all(self, query):
        self.queries.append(query)
        return {
            "totalSize": 1,
            "done": True,
            "records": [
                {
                    "attributes": {"type": "Contact"},
                    "Id": "003000000000001AAA",
                    "Name": "Ada Lovelace",
                }
            ],
        }

    def search(self, search):
        return {
            "searchRecords": [
                {
                    "attributes": {"type": "Account"},
                    "Id": "001000000000001AAA",
                    "Name": "Acme",
                }
            ]
        }

    @property
    def Account(self):
        return FakeSObject(
            {
                "name": "Account",
                "label": "Account",
                "labelPlural": "Accounts",
                "queryable": True,
                "searchable": True,
                "createable": True,
                "updateable": True,
                "deletable": True,
                "fields": [
                    {"name": "Id", "label": "Account ID", "type": "id"},
                    {"name": "Name", "label": "Account Name", "type": "string"},
                ],
                "childRelationships": [
                    {
                        "relationshipName": "Contacts",
                        "childSObject": "Contact",
                        "field": "AccountId",
                        "deprecatedAndHidden": False,
                    }
                ],
            }
        )

    @property
    def Contact(self):
        return FakeSObject(
            {
                "name": "Contact",
                "label": "Contact",
                "fields": [
                    {"name": "Id", "label": "Contact ID", "type": "id"},
                    {"name": "Name", "label": "Name", "type": "string"},
                    {"name": "AccountId", "label": "Account ID", "type": "reference"},
                ],
                "childRelationships": [],
            }
        )


class FakeConnector:
    def __init__(self):
        self.sf = FakeSalesforce()


class SalesforceReadMCPAdapterTests(unittest.TestCase):
    def setUp(self):
        self.connector = FakeConnector()
        self.adapter = SalesforceReadMCPAdapter(org_type="b2b", connector=self.connector)

    def test_list_tools_matches_hosted_read_surface(self):
        names = [tool["name"] for tool in self.adapter.list_tools()]
        self.assertEqual(
            names,
            [
                "getObjectSchema",
                "soqlQuery",
                "find",
                "getUserInfo",
                "listRecentSobjectRecords",
                "getRelatedRecords",
            ],
        )

    def test_schema_index_filters_nonqueryable_objects(self):
        result = self.adapter.call_tool("getObjectSchema", {})
        self.assertTrue(result["ok"])
        names = [obj["name"] for obj in result["content"]["objects"]]
        self.assertEqual(names, ["Account"])

    def test_schema_detail_includes_fields_and_relationships(self):
        result = self.adapter.call_tool("getObjectSchema", {"object-name": "Account"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"]["object"]["name"], "Account")
        self.assertEqual(result["content"]["fields"][0]["name"], "Id")
        self.assertEqual(result["content"]["childRelationships"][0]["relationshipName"], "Contacts")

    def test_soql_query_rejects_mutating_text(self):
        result = self.adapter.call_tool("soqlQuery", {"query": "UPDATE Account SET Name = 'x'"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_SOQL")

    def test_sosl_find_strips_attributes(self):
        result = self.adapter.call_tool("find", {"search": "FIND {Acme} IN NAME FIELDS RETURNING Account(Id, Name)"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"]["searchRecords"], [{"Id": "001000000000001AAA", "Name": "Acme"}])

    def test_get_related_records_uses_child_relationship_metadata(self):
        result = self.adapter.call_tool(
            "getRelatedRecords",
            {
                "sobject-name": "Account",
                "id": "001000000000001AAA",
                "relationship-path": "Contacts",
            },
        )
        self.assertTrue(result["ok"])
        self.assertIn("FROM Contact WHERE AccountId = '001000000000001AAA'", self.connector.sf.queries[-1])
        self.assertEqual(result["relationship"]["childSObject"], "Contact")

    def test_salesforce_reads_client_executes_and_normalizes_observations(self):
        client = SalesforceReadsClient(self.adapter)
        observation = client.soql_query("SELECT Id, Name FROM Contact LIMIT 1")
        self.assertTrue(observation.ok)
        self.assertEqual(observation.payload["records"][0]["Name"], "Ada Lovelace")

        stored_observation = to_observation(MCPCall("soqlQuery", {"query": "SELECT Id, Name FROM Contact LIMIT 1"}), observation)
        self.assertTrue(stored_observation.ok)

        evidence = normalize_observation(
            MCPCall("soqlQuery", {"query": "SELECT Id, Name FROM Contact LIMIT 1"}),
            observation,
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].source_tool, "soqlQuery")
        self.assertEqual(evidence[0].source_object, "Contact")
        self.assertEqual(evidence[0].record_id, "003000000000001AAA")

    def test_build_environment_ir_from_mcp_schema(self):
        client = SalesforceReadsClient(self.adapter)
        env_ir = build_environment_ir_from_mcp_schema(client)

        self.assertIn("Account", env_ir.object_names())
        self.assertTrue(env_ir.get_object("Account").has_field("Name"))
        self.assertIn("getRelatedRecords", env_ir.tool_names())

        state = ExecutionState()
        state.resolved["entities"].append({"object": "Account", "id": "001000000000001AAA"})
        reachable = reachable_information(state, env_ir)
        relationship_targets = {
            (item.object_name, item.relationship_path, item.source_entity_id)
            for item in reachable
            if item.action == "traverse_relationship"
        }
        self.assertIn(("Contact", "Contacts", "001000000000001AAA"), relationship_targets)


if __name__ == "__main__":
    unittest.main()
