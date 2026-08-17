"""Relationship graph construction helpers."""

from typing import Dict, List

from ewm.ir.environment import RelationshipInfo
from verifiers.schema_utils import SchemaIndex


def relationships_from_schema_index(schema_index: SchemaIndex) -> Dict[str, List[RelationshipInfo]]:
    """Convert verifier reference metadata into EnvironmentIR graph edges."""

    relationships: Dict[str, List[RelationshipInfo]] = {}

    for source_object in sorted(schema_index.reference_targets):
        for field_name, targets in sorted(schema_index.reference_targets[source_object].items()):
            for target_object in sorted(targets):
                relationships.setdefault(source_object, []).append(
                    RelationshipInfo(
                        source_object=source_object,
                        target_object=target_object,
                        relationship_name=_relationship_name_for_field(field_name),
                        field=field_name,
                        direction="parent",
                        metadata={"source": "schema_reference_field"},
                    )
                )

    for parent_object, child_relationships in sorted(schema_index.child_relationships.items()):
        for relationship_name, child_object in sorted(child_relationships.items()):
            relationships.setdefault(parent_object, []).append(
                RelationshipInfo(
                    source_object=parent_object,
                    target_object=child_object,
                    relationship_name=relationship_name,
                    direction="child",
                    metadata={"source": "schema_child_relationship"},
                )
            )

    return relationships


def mine_relationship_priors(schema_index: SchemaIndex, **kwargs) -> Dict[str, List[RelationshipInfo]]:
    """Return the schema-derived relationship graph prior."""

    return relationships_from_schema_index(schema_index)


def _relationship_name_for_field(field_name: str) -> str:
    if field_name.endswith("__c"):
        return "{}__r".format(field_name[:-3])
    if field_name.endswith("Id") and len(field_name) > 2:
        return field_name[:-2]
    if field_name == "OwnerId":
        return "Owner"
    if field_name == "CreatedById":
        return "CreatedBy"
    if field_name == "LastModifiedById":
        return "LastModifiedBy"
    if field_name == "ParentId":
        return "Parent"
    if field_name == "RelatedToId":
        return "RelatedTo"
    if field_name == "WhatId":
        return "What"
    return field_name
