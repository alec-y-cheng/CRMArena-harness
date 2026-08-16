"""Environment affordance graph for reachable enterprise information."""

from typing import Any, Dict, List, Optional

from .base import Serializable


class ObjectSchema(Serializable):
    def __init__(
        self,
        name: str,
        fields: Optional[Dict[str, Dict[str, Any]]] = None,
        relationships: Optional[List["RelationshipInfo"]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.fields = fields or {}
        self.relationships = relationships or []
        self.metadata = metadata or {}


class RelationshipInfo(Serializable):
    def __init__(
        self,
        source_object: str,
        target_object: str,
        relationship_name: str,
        field: Optional[str] = None,
        direction: str = "child",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.source_object = source_object
        self.target_object = target_object
        self.relationship_name = relationship_name
        self.field = field
        self.direction = direction
        self.metadata = metadata or {}


class ReachableInfo(Serializable):
    def __init__(
        self,
        description: str,
        action: str,
        object_name: Optional[str] = None,
        fields: Optional[List[str]] = None,
        relationship_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.action = action
        self.object_name = object_name
        self.fields = fields or []
        self.relationship_path = relationship_path
        self.metadata = metadata or {}


class EnvironmentIR(Serializable):
    def __init__(
        self,
        objects: Optional[Dict[str, ObjectSchema]] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.objects = objects or {}
        self.tool_schemas = tool_schemas or []
        self.metadata = metadata or {}

    def get_object(self, object_name: str) -> Optional[ObjectSchema]:
        return self.objects.get(object_name)


def build_environment_ir_from_mcp_schema(client: Any) -> EnvironmentIR:
    raise NotImplementedError("EnvironmentIR schema discovery is implemented in a later phase.")


def reachable_information(state: Any, env_ir: EnvironmentIR, depth: int = 1) -> List[ReachableInfo]:
    raise NotImplementedError("Reachability expansion is implemented in a later phase.")

