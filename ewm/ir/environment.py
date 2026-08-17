"""Environment affordance graph for reachable enterprise information."""

from typing import Any, Dict, List, Optional

from .base import Serializable, ensure_dict, object_list, string_list


class ObjectSchema(Serializable):
    def __init__(
        self,
        name: str,
        fields: Optional[Dict[str, Dict[str, Any]]] = None,
        relationships: Optional[List["RelationshipInfo"]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.fields = {str(key): ensure_dict(value) for key, value in (fields or {}).items()}
        self.relationships = [
            item if isinstance(item, RelationshipInfo) else RelationshipInfo.from_dict(ensure_dict(item))
            for item in (relationships or [])
        ]
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObjectSchema":
        return cls(
            name=str(data.get("name") or data.get("object_name") or ""),
            fields=ensure_dict(data.get("fields")),
            relationships=[
                RelationshipInfo.from_dict(ensure_dict(item))
                for item in (data.get("relationships") or [])
            ],
            metadata=ensure_dict(data.get("metadata")),
        )

    def has_field(self, field_name: str) -> bool:
        return field_name in self.fields

    def field_names(self) -> List[str]:
        return sorted(self.fields.keys())


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
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipInfo":
        return cls(
            source_object=str(data.get("source_object") or data.get("source") or ""),
            target_object=str(data.get("target_object") or data.get("target") or ""),
            relationship_name=str(data.get("relationship_name") or data.get("name") or ""),
            field=data.get("field"),
            direction=str(data.get("direction") or "child"),
            metadata=ensure_dict(data.get("metadata")),
        )


class ReachableInfo(Serializable):
    def __init__(
        self,
        description: str,
        action: str,
        object_name: Optional[str] = None,
        fields: Optional[List[str]] = None,
        relationship_path: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.action = action
        self.object_name = object_name
        self.fields = string_list(fields)
        self.relationship_path = relationship_path
        self.source_entity_id = source_entity_id or ""
        self.confidence = confidence
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReachableInfo":
        confidence = data.get("confidence")
        try:
            confidence_value = None if confidence is None else float(confidence)
        except (TypeError, ValueError):
            confidence_value = None
        return cls(
            description=str(data.get("description") or ""),
            action=str(data.get("action") or ""),
            object_name=data.get("object_name"),
            fields=string_list(data.get("fields")),
            relationship_path=data.get("relationship_path"),
            source_entity_id=data.get("source_entity_id"),
            confidence=confidence_value,
            metadata=ensure_dict(data.get("metadata")),
        )


class EnvironmentIR(Serializable):
    def __init__(
        self,
        objects: Optional[Dict[str, ObjectSchema]] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.objects = {
            str(key): value if isinstance(value, ObjectSchema) else ObjectSchema.from_dict(ensure_dict(value))
            for key, value in (objects or {}).items()
        }
        self.tool_schemas = object_list(tool_schemas)
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentIR":
        objects = {}
        for key, value in ensure_dict(data.get("objects")).items():
            object_data = ensure_dict(value)
            object_data.setdefault("name", key)
            objects[str(key)] = ObjectSchema.from_dict(object_data)
        return cls(
            objects=objects,
            tool_schemas=object_list(data.get("tool_schemas")),
            metadata=ensure_dict(data.get("metadata")),
        )

    def get_object(self, object_name: str) -> Optional[ObjectSchema]:
        return self.objects.get(object_name)

    def add_object(self, schema: ObjectSchema) -> None:
        self.objects[schema.name] = schema

    def object_names(self) -> List[str]:
        return sorted(self.objects.keys())

    def relationships_from(self, object_name: str) -> List[RelationshipInfo]:
        schema = self.get_object(object_name)
        return list(schema.relationships) if schema else []

    def has_tool(self, tool_name: str) -> bool:
        return any(str(tool.get("name") or "") == tool_name for tool in self.tool_schemas)

    def tool_names(self) -> List[str]:
        return sorted(str(tool.get("name") or "") for tool in self.tool_schemas if tool.get("name"))


def build_environment_ir_from_mcp_schema(client: Any) -> EnvironmentIR:
    """Build EnvironmentIR from a Salesforce SObject Reads MCP client.

    The client is expected to expose `list_tools()` and `call(MCPCall)`. This
    works with the local SalesforceReadsClient and should also work with a
    hosted MCP client that returns the same logical payloads.
    """

    from ewm.mcp.client import MCPCall

    tools = client.list_tools()
    index_observation = client.call(MCPCall("getObjectSchema", {}))
    if not getattr(index_observation, "ok", False):
        return EnvironmentIR(
            tool_schemas=[tool.to_dict() if hasattr(tool, "to_dict") else tool for tool in tools],
            metadata={
                "schema_discovery_error": getattr(index_observation, "error", {}),
            },
        )

    objects: Dict[str, ObjectSchema] = {}
    for object_name in _object_names_from_schema_index(index_observation.payload):
        detail_observation = client.call(MCPCall("getObjectSchema", {"object-name": object_name}))
        if not getattr(detail_observation, "ok", False):
            objects[object_name] = ObjectSchema(
                name=object_name,
                metadata={
                    "schema_detail_error": getattr(detail_observation, "error", {}),
                },
            )
            continue
        objects[object_name] = _object_schema_from_mcp_detail(detail_observation.payload)

    return EnvironmentIR(
        objects=objects,
        tool_schemas=[tool.to_dict() if hasattr(tool, "to_dict") else tool for tool in tools],
        metadata={"source": "mcp_getObjectSchema"},
    )


def reachable_information(state: Any, env_ir: EnvironmentIR, depth: int = 1) -> List[ReachableInfo]:
    """Return a shallow generic affordance view from resolved entities.

    Phase 4 will make this graph-aware. For Phase 2, this gives the workflow
    loop a JSON-serializable, task-agnostic view: known objects can be queried,
    and relationships from resolved object types can be traversed.
    """

    reachable: List[ReachableInfo] = []
    for object_name, schema in sorted(env_ir.objects.items()):
        reachable.append(
            ReachableInfo(
                description="Direct records and fields are available for {}".format(object_name),
                action="query_object",
                object_name=object_name,
                fields=schema.field_names(),
                metadata={"source": "environment_schema"},
            )
        )

    if depth <= 0:
        return reachable

    resolved_entities = []
    if hasattr(state, "resolved"):
        resolved_entities = list(getattr(state, "resolved", {}).get("entities", []))
    for entity in resolved_entities:
        if not isinstance(entity, dict):
            continue
        object_name = str(entity.get("object") or entity.get("object_name") or "")
        entity_id = str(entity.get("id") or entity.get("record_id") or "")
        if not object_name:
            continue
        for relationship in env_ir.relationships_from(object_name):
            reachable.append(
                ReachableInfo(
                    description="Related {} records are reachable from {}".format(
                        relationship.target_object,
                        object_name,
                    ),
                    action="traverse_relationship",
                    object_name=relationship.target_object,
                    relationship_path=relationship.relationship_name,
                    source_entity_id=entity_id,
                    metadata={
                        "source_object": relationship.source_object,
                        "field": relationship.field,
                        "direction": relationship.direction,
                    },
                )
            )
    return reachable


def _object_names_from_schema_index(payload: Any) -> List[str]:
    if not isinstance(payload, dict):
        return []
    objects = payload.get("objects", [])
    out = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            out.append(name)
    return sorted(set(out))


def _object_schema_from_mcp_detail(payload: Any) -> ObjectSchema:
    if not isinstance(payload, dict):
        return ObjectSchema(name="")
    object_info = ensure_dict(payload.get("object"))
    object_name = str(object_info.get("name") or "")
    fields: Dict[str, Dict[str, Any]] = {}
    relationships: List[RelationshipInfo] = []

    for field in payload.get("fields", []) or []:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or "")
        if not field_name:
            continue
        reference_targets = string_list(field.get("referenceTo"))
        fields[field_name] = {
            "label": field.get("label"),
            "type": field.get("type"),
            "custom": field.get("custom"),
            "nillable": field.get("nillable"),
            "createable": field.get("createable"),
            "updateable": field.get("updateable"),
            "filterable": field.get("filterable"),
            "sortable": field.get("sortable"),
            "reference_targets": reference_targets,
            "relationship_name": field.get("relationshipName") or _relationship_name_for_field(field_name),
            "picklist_values": field.get("picklistValues") or [],
        }
        for target in reference_targets:
            relationships.append(
                RelationshipInfo(
                    source_object=object_name,
                    target_object=target,
                    relationship_name=str(field.get("relationshipName") or _relationship_name_for_field(field_name)),
                    field=field_name,
                    direction="parent",
                    metadata={"source": "mcp_reference_field"},
                )
            )

    for relationship in payload.get("childRelationships", []) or []:
        if not isinstance(relationship, dict):
            continue
        relationship_name = str(relationship.get("relationshipName") or "")
        child_object = str(relationship.get("childSObject") or "")
        if not relationship_name or not child_object:
            continue
        relationships.append(
            RelationshipInfo(
                source_object=object_name,
                target_object=child_object,
                relationship_name=relationship_name,
                field=relationship.get("field"),
                direction="child",
                metadata={
                    "source": "mcp_child_relationship",
                    "deprecatedAndHidden": relationship.get("deprecatedAndHidden"),
                },
            )
        )

    return ObjectSchema(
        name=object_name,
        fields=fields,
        relationships=relationships,
        metadata={
            "source": "mcp_getObjectSchema",
            "label": object_info.get("label"),
            "labelPlural": object_info.get("labelPlural"),
            "custom": object_info.get("custom"),
            "queryable": object_info.get("queryable"),
            "searchable": object_info.get("searchable"),
            "createable": object_info.get("createable"),
            "updateable": object_info.get("updateable"),
            "deletable": object_info.get("deletable"),
        },
    )


def _relationship_name_for_field(field_name: str) -> str:
    if field_name.endswith("__c"):
        return "{}__r".format(field_name[:-3])
    if field_name.endswith("Id") and len(field_name) > 2:
        return field_name[:-2]
    return field_name
