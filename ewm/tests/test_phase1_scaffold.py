import json
import unittest

from ewm.ir import (
    Claim,
    EvidenceItem,
    EvidenceRequirement,
    ExecutionState,
    InstanceFrame,
    Observation,
    OutcomeContract,
    ResponseContract,
)
from ewm.mcp.client import MCPCall, MCPObservation, MCPToolSchema, ValidationResult
from ewm.runtime.verifier import validate_mcp_call


class Phase1ScaffoldTests(unittest.TestCase):
    def test_execution_state_serializes_to_json(self):
        frame = InstanceFrame(
            goal="answer user request",
            evidence_requirements=[EvidenceRequirement("retrieve relevant Salesforce data")],
            outcome_contract=OutcomeContract("outcome is supported"),
            response_contract=ResponseContract("respond concisely"),
        )
        state = ExecutionState(frame=frame)
        state.add_observation(Observation("obs_1", "soqlQuery", {"records": []}))
        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Id": "001"}))
        state.add_claim(Claim("cl_1", "Account Id is 001", status="supported", supporting_evidence_ids=["ev_1"]))

        encoded = json.dumps(state.to_dict(), sort_keys=True)
        self.assertIn("answer user request", encoded)
        self.assertIn("Account Id is 001", encoded)

    def test_basic_mcp_validation(self):
        call = MCPCall("soqlQuery", {"query": "SELECT Id FROM Account LIMIT 1"})
        tool = MCPToolSchema("soqlQuery", input_schema={"type": "object"})
        state = ExecutionState()
        result = validate_mcp_call(call, state, env_ir=None, tool_schema=tool)
        self.assertTrue(result.valid)

        mismatch = validate_mcp_call(MCPCall("find"), state, env_ir=None, tool_schema=tool)
        self.assertFalse(mismatch.valid)

    def test_mcp_value_objects_serialize(self):
        call = MCPCall("find", {"search": "FIND {Acme}"}, call_id="call_1")
        observation = MCPObservation(call=call, ok=True, payload={"searchRecords": []})
        result = ValidationResult(True, "ok")

        self.assertEqual(observation.to_dict()["call"]["name"], "find")
        self.assertEqual(result.to_dict()["valid"], True)


if __name__ == "__main__":
    unittest.main()
