"""Schema-to-EnvironmentIR conversion helpers.

These helpers are intentionally environment-level, not task-level. They convert
the object/field/reference metadata that CRMArena or Salesforce describe APIs
provide into the generic EWM EnvironmentIR graph.
"""

from typing import Any, Dict, Iterable, Mapping, Optional

from ewm.ir.environment import EnvironmentIR, ObjectSchema
from ewm.mcp.client import MCPToolSchema
from verifiers.schema_utils import build_schema_index

from .relationship_miner import relationships_from_schema_index


DEFAULT_SOBJECT_READ_TOOL_SCHEMAS = [
    MCPToolSchema(
        "getObjectSchema",
        "Discover object fields, values, and relationships visible in the connected org.",
        {"type": "object"},
    ),
    MCPToolSchema(
        "soqlQuery",
        "Run a read-only SOQL query against objects visible in the connected org.",
        {"type": "object"},
    ),
    MCPToolSchema(
        "find",
        "Run a SOSL text search across objects visible in the connected org.",
        {"type": "object"},
    ),
    MCPToolSchema(
        "getUserInfo",
        "Return authenticated user context for the connected org.",
        {"type": "object"},
    ),
    MCPToolSchema(
        "listRecentSobjectRecords",
        "List recently viewed records for a requested object type.",
        {"type": "object"},
    ),
    MCPToolSchema(
        "getRelatedRecords",
        "Traverse a relationship from a resolved parent record.",
        {"type": "object"},
    ),
]


def environment_ir_from_crmarena_schema(
    schema_records: Iterable[Mapping[str, Any]],
    tool_schemas=None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> EnvironmentIR:
    """Build EnvironmentIR from CRMArena compact schema records.

    `schema_records` is the materialized value of B2B_SCHEMA, B2C_SCHEMA, or
    SCHEMA_ORIGINAL. The relationship graph is inferred through the same schema
    index used by the SOQL/SOSL verifier.
    """

    records = [dict(item) for item in schema_records]
    schema_index = build_schema_index(records)
    relationships_by_object = relationships_from_schema_index(schema_index)

    objects: Dict[str, ObjectSchema] = {}
    for object_name in sorted(schema_index.object_fields):
        fields = {}
        for field_name in sorted(schema_index.object_fields[object_name]):
            fields[field_name] = {
                "description": schema_index.field_description(object_name, field_name),
                "reference_targets": sorted(schema_index.referenced_objects(object_name, field_name)),
            }
        objects[object_name] = ObjectSchema(
            name=object_name,
            fields=fields,
            relationships=relationships_by_object.get(object_name, []),
            metadata={"source": "crmarena_schema"},
        )

    return EnvironmentIR(
        objects=objects,
        tool_schemas=[tool.to_dict() for tool in (tool_schemas or DEFAULT_SOBJECT_READ_TOOL_SCHEMAS)],
        metadata=dict(metadata or {}),
    )


def mine_schema_priors(schema_records: Iterable[Mapping[str, Any]], **kwargs) -> EnvironmentIR:
    """Return the initial schema-derived EnvironmentIR prior.

    Future phases can add usage-frequency and workflow priors, but the first
    schema prior is the object/field/relationship graph itself.
    """

    return environment_ir_from_crmarena_schema(schema_records, **kwargs)
