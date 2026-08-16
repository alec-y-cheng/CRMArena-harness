import unittest

from ewm.mcp.salesforce_read_adapter import SalesforceReadMCPAdapter


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


if __name__ == "__main__":
    unittest.main()
