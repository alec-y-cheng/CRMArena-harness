"""MCP-compatible adapters used by the EWM runtime."""

from .client import MCPCall, MCPClient, MCPObservation, MCPToolSchema, ValidationResult
from .salesforce_read_adapter import SalesforceReadMCPAdapter
from .salesforce_reads import SalesforceReadsClient

__all__ = [
    "MCPCall",
    "MCPClient",
    "MCPObservation",
    "MCPToolSchema",
    "SalesforceReadMCPAdapter",
    "SalesforceReadsClient",
    "ValidationResult",
]
