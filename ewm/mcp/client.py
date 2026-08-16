"""Generic MCP client-side value objects and interfaces."""

from typing import Any, Dict, List, Optional

from ewm.ir.base import Serializable


class MCPToolSchema(Serializable):
    def __init__(self, name: str, description: str = "", input_schema: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}


class MCPCall(Serializable):
    def __init__(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        call_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.arguments = arguments or {}
        self.call_id = call_id
        self.metadata = metadata or {}


class MCPObservation(Serializable):
    def __init__(
        self,
        call: MCPCall,
        ok: bool,
        payload: Any = None,
        error: Optional[Dict[str, Any]] = None,
        raw: Any = None,
    ) -> None:
        self.call = call
        self.ok = ok
        self.payload = payload
        self.error = error or {}
        self.raw = raw


class ValidationResult(Serializable):
    def __init__(self, valid: bool, reason: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        self.valid = valid
        self.reason = reason
        self.metadata = metadata or {}


class MCPClient:
    """Minimal interface implemented by local and hosted MCP clients."""

    def list_tools(self) -> List[MCPToolSchema]:
        raise NotImplementedError

    def call(self, call: MCPCall) -> MCPObservation:
        raise NotImplementedError

