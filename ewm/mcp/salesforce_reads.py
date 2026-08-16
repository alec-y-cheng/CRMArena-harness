"""Thin EWM client wrapper around Salesforce read MCP-compatible backends."""

from typing import List

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


def execute_mcp_call(client: MCPClient, call: MCPCall) -> MCPObservation:
    return client.call(call)

