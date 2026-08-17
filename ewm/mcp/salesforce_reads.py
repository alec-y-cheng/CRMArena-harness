"""Thin EWM client wrapper around Salesforce read MCP-compatible backends."""

from typing import Any, Dict, List, Optional

from .client import MCPCall, MCPClient, MCPObservation, MCPToolSchema


class SalesforceReadsClient(MCPClient):
    """Adapter from an in-process Salesforce read backend to MCPClient."""

    def __init__(self, backend) -> None:
        self.backend = backend

    def list_tools(self) -> List[MCPToolSchema]:
        tools = []
        for tool in self.backend.list_tools():
            tools.append(
                MCPToolSchema(
                    name=tool.get("name", ""),
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                )
            )
        return tools

    def call(self, call: MCPCall) -> MCPObservation:
        raw = self.backend.call_tool(call.name, call.arguments)
        return MCPObservation(
            call=call,
            ok=bool(raw.get("ok", False)),
            payload=raw.get("content"),
            error=raw.get("error", {}),
            raw=raw,
        )

    def get_object_schema(self, object_name: Optional[str] = None) -> MCPObservation:
        arguments: Dict[str, Any] = {}
        if object_name:
            arguments["object-name"] = object_name
        return self.call(MCPCall("getObjectSchema", arguments))

    def soql_query(self, query: str) -> MCPObservation:
        return self.call(MCPCall("soqlQuery", {"query": query}))

    def sosl_search(self, search: str) -> MCPObservation:
        return self.call(MCPCall("find", {"search": search}))

    def get_user_context(self) -> MCPObservation:
        return self.call(MCPCall("getUserInfo", {}))

    def list_recent_sobject_records(self, object_name: str, limit: Optional[int] = None) -> MCPObservation:
        arguments: Dict[str, Any] = {"sobject-name": object_name}
        if limit is not None:
            arguments["limit"] = limit
        return self.call(MCPCall("listRecentSobjectRecords", arguments))

    def get_related_records(
        self,
        object_name: str,
        record_id: str,
        relationship_path: str,
        limit: Optional[int] = None,
    ) -> MCPObservation:
        arguments: Dict[str, Any] = {
            "sobject-name": object_name,
            "id": record_id,
            "relationship-path": relationship_path,
        }
        if limit is not None:
            arguments["limit"] = limit
        return self.call(MCPCall("getRelatedRecords", arguments))


def execute_mcp_call(client: MCPClient, call: MCPCall) -> MCPObservation:
    return client.call(call)
