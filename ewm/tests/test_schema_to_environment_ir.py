import json
import unittest

from ewm.ir.environment import EnvironmentIR, reachable_information
from ewm.ir.state import ExecutionState
from ewm.mining import environment_ir_from_crmarena_schema


class SchemaToEnvironmentIRTests(unittest.TestCase):
    def test_compact_schema_builds_object_field_and_relationship_graph(self):
        schema = [
            {
                "object": "Opportunity",
                "fields": {
                    "StageName": "Current stage",
                    "AccountId": "ID of the account. References Account object",
                    "OwnerId": "ID of the owner. References User object",
                },
            },
            {
                "object": "Account",
                "fields": {
                    "Name": "Account name",
                },
            },
            {
                "object": "User",
                "fields": {
                    "Name": "User name",
                },
            },
        ]

        env_ir = environment_ir_from_crmarena_schema(schema, metadata={"org_type": "b2b"})

        self.assertIsInstance(env_ir, EnvironmentIR)
        self.assertTrue(env_ir.get_object("Opportunity").has_field("Id"))
        self.assertTrue(env_ir.get_object("Opportunity").has_field("StageName"))
        self.assertIn("soqlQuery", env_ir.tool_names())

        relationships = env_ir.relationships_from("Opportunity")
        relationship_edges = {
            (item.source_object, item.field, item.target_object, item.relationship_name)
            for item in relationships
        }
        self.assertIn(("Opportunity", "AccountId", "Account", "Account"), relationship_edges)
        self.assertIn(("Opportunity", "OwnerId", "User", "Owner"), relationship_edges)

        encoded = json.dumps(env_ir.to_dict(), sort_keys=True)
        self.assertIn("schema_reference_field", encoded)
        self.assertNotIn("lead_qualification", encoded)

    def test_reachability_includes_relationships_from_resolved_records(self):
        env_ir = environment_ir_from_crmarena_schema(
            [
                {
                    "object": "Opportunity",
                    "fields": {
                        "AccountId": "References Account object",
                    },
                },
                {
                    "object": "Account",
                    "fields": {
                        "Name": "Account name",
                    },
                },
            ]
        )
        state = ExecutionState()
        state.resolved["entities"].append({"object": "Opportunity", "id": "006xx"})

        reachable = reachable_information(state, env_ir)
        relationship_affordances = [
            item for item in reachable if item.action == "traverse_relationship"
        ]

        relationship_targets = {
            (item.object_name, item.relationship_path, item.source_entity_id)
            for item in relationship_affordances
        }
        self.assertIn(("Account", "Account", "006xx"), relationship_targets)


if __name__ == "__main__":
    unittest.main()
