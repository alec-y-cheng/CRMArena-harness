import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Set


BENCHMARK_REFERENCE_TARGETS: Mapping[str, Mapping[str, Set[str]]] = {
    "User": {"ProfileId": {"Profile"}},
    "Contact": {"AccountId": {"Account"}},
    "Case": {
        "AccountId": {"Account"},
        "ContactId": {"Contact"},
        "IssueId__c": {"Issue__c"},
        "OrderItemId__c": {"OrderItem"},
        "OwnerId": {"User"},
    },
    "ProductCategoryProduct": {
        "ProductCategoryId": {"ProductCategory"},
        "ProductId": {"Product2"},
    },
    "PricebookEntry": {
        "Pricebook2Id": {"Pricebook2"},
        "Product2Id": {"Product2"},
    },
    "Order": {
        "AccountId": {"Account"},
        "OwnerId": {"User"},
        "Pricebook2Id": {"Pricebook2"},
    },
    "OrderItem": {
        "OrderId": {"Order"},
        "PriceBookEntryId": {"PricebookEntry"},
        "PricebookEntryId": {"PricebookEntry"},
        "Product2Id": {"Product2"},
    },
    "EmailMessage": {
        "ParentId": {"Case"},
        "RelatedToId": {"Case", "Opportunity"},
    },
    "LiveChatTranscript": {
        "AccountId": {"Account"},
        "CaseId": {"Case"},
        "ContactId": {"Contact"},
        "OwnerId": {"User"},
    },
    "CaseHistory__c": {
        "CaseId__c": {"Case"},
        "NewValue__c": {"User"},
        "OldValue__c": {"User"},
    },
    "Opportunity": {
        "AccountId": {"Account"},
        "ContactId": {"Contact"},
        "ContractID__c": {"Contract"},
        "OwnerId": {"User"},
    },
    "OpportunityLineItem": {
        "OpportunityId": {"Opportunity"},
        "PricebookEntryId": {"PricebookEntry"},
        "Product2Id": {"Product2"},
    },
    "Quote": {
        "AccountId": {"Account"},
        "ContactId": {"Contact"},
        "OpportunityId": {"Opportunity"},
        "Pricebook2Id": {"Pricebook2"},
    },
    "QuoteLineItem": {
        "OpportunityLineItemId": {"OpportunityLineItem"},
        "PricebookEntryId": {"PricebookEntry"},
        "Product2Id": {"Product2"},
        "QuoteId": {"Quote"},
    },
    "Contract": {"AccountId": {"Account"}},
    "VoiceCallTranscript__c": {
        "LeadId__c": {"Lead"},
        "OpportunityId__c": {"Opportunity"},
    },
    "Task": {"OwnerId": {"User"}, "WhatId": {"Opportunity"}},
    "Event": {"OwnerId": {"User"}, "WhatId": {"Opportunity"}},
    "UserTerritory2Association": {
        "Territory2Id": {"Territory2"},
        "UserId": {"User"},
    },
    "Lead": {
        "ConvertedAccountId": {"Account"},
        "ConvertedContactId": {"Contact"},
        "OwnerId": {"User"},
    },
}


BENCHMARK_CHILD_RELATIONSHIPS: Mapping[str, Mapping[str, str]] = {
    "Account": {
        "Contacts": "Contact",
        "Cases": "Case",
        "Opportunities": "Opportunity",
        "Orders": "Order",
        "Contracts": "Contract",
        "Quotes": "Quote",
    },
    "Case": {
        "EmailMessages": "EmailMessage",
        "LiveChatTranscripts": "LiveChatTranscript",
        "CaseHistories__r": "CaseHistory__c",
    },
    "Contact": {
        "Cases": "Case",
        "Opportunities": "Opportunity",
        "Quotes": "Quote",
    },
    "Contract": {"Opportunities": "Opportunity"},
    "Lead": {"VoiceCallTranscripts__r": "VoiceCallTranscript__c"},
    "Opportunity": {
        "OpportunityLineItems": "OpportunityLineItem",
        "Quotes": "Quote",
        "Tasks": "Task",
        "Events": "Event",
        "EmailMessages": "EmailMessage",
        "VoiceCallTranscripts__r": "VoiceCallTranscript__c",
    },
    "Order": {"OrderItems": "OrderItem"},
    "Pricebook2": {"PricebookEntries": "PricebookEntry", "Orders": "Order"},
    "PricebookEntry": {
        "OrderItems": "OrderItem",
        "OpportunityLineItems": "OpportunityLineItem",
        "QuoteLineItems": "QuoteLineItem",
    },
    "Product2": {
        "ProductCategoryProducts": "ProductCategoryProduct",
        "PricebookEntries": "PricebookEntry",
        "OrderItems": "OrderItem",
        "OpportunityLineItems": "OpportunityLineItem",
        "QuoteLineItems": "QuoteLineItem",
    },
    "ProductCategory": {"ProductCategoryProducts": "ProductCategoryProduct"},
    "Quote": {"QuoteLineItems": "QuoteLineItem"},
    "Territory2": {"UserTerritory2Associations": "UserTerritory2Association"},
    "User": {
        "Cases": "Case",
        "Orders": "Order",
        "LiveChatTranscripts": "LiveChatTranscript",
        "Opportunities": "Opportunity",
        "Tasks": "Task",
        "Events": "Event",
        "UserTerritory2Associations": "UserTerritory2Association",
        "Leads": "Lead",
    },
}


@dataclass(frozen=True)
class SchemaIndex:
    object_fields: Mapping[str, Set[str]]
    field_descriptions: Mapping[str, Mapping[str, str]]
    reference_targets: Mapping[str, Mapping[str, Set[str]]]
    parent_relationship_targets: Mapping[str, Mapping[str, Set[str]]]
    child_relationships: Mapping[str, Mapping[str, str]]

    @property
    def objects(self) -> Set[str]:
        return set(self.object_fields.keys())

    def has_object(self, object_name: str) -> bool:
        return object_name in self.object_fields

    def has_field(self, object_name: str, field_name: str) -> bool:
        if object_name not in self.object_fields:
            return False
        return field_name in self.object_fields[object_name]

    def field_description(self, object_name: str, field_name: str) -> str:
        if object_name not in self.field_descriptions:
            return ""
        return self.field_descriptions[object_name].get(field_name, "")

    def referenced_objects(self, object_name: str, field_name: str) -> Set[str]:
        return set(self.reference_targets.get(object_name, {}).get(field_name, set()))

    def parent_relationship_objects(self, object_name: str, relationship_name: str) -> Set[str]:
        return set(self.parent_relationship_targets.get(object_name, {}).get(relationship_name, set()))

    def child_relationship_object(self, object_name: str, relationship_name: str) -> Optional[str]:
        return self.child_relationships.get(object_name, {}).get(relationship_name)


def build_schema_index(schema_obj: Iterable[Mapping]) -> SchemaIndex:
    object_fields: Dict[str, Set[str]] = {}
    field_descriptions: Dict[str, Dict[str, str]] = {}
    reference_targets: Dict[str, Dict[str, Set[str]]] = {}
    schema_items = list(schema_obj)

    for item in schema_items:
        object_name = item.get("object")
        fields = item.get("fields", {})
        if not object_name or not isinstance(fields, Mapping):
            continue
        field_names = {str(field) for field in fields if field}
        # Id is present on Salesforce records even when omitted from compact schemas.
        field_names.add("Id")
        object_fields[str(object_name)] = field_names
        field_descriptions[str(object_name)] = {
            str(field): str(description or "") for field, description in fields.items() if field
        }
        field_descriptions[str(object_name)].setdefault("Id", "Salesforce record ID")

    for item in schema_items:
        object_name = item.get("object")
        fields = item.get("fields", {})
        if not object_name or not isinstance(fields, Mapping):
            continue
        reference_targets[str(object_name)] = {}
        for field, description in fields.items():
            parsed_targets = _reference_targets_from_description(str(description or ""), object_fields.keys())
            if parsed_targets:
                reference_targets[str(object_name)][str(field)] = parsed_targets

    for object_name, fields in BENCHMARK_REFERENCE_TARGETS.items():
        object_refs = reference_targets.setdefault(object_name, {})
        for field_name, targets in fields.items():
            object_refs.setdefault(field_name, set()).update(targets)

    parent_relationship_targets = _build_parent_relationship_targets(reference_targets)
    child_relationships = {
        object_name: dict(relationships)
        for object_name, relationships in BENCHMARK_CHILD_RELATIONSHIPS.items()
    }

    return SchemaIndex(
        object_fields=object_fields,
        field_descriptions=field_descriptions,
        reference_targets=reference_targets,
        parent_relationship_targets=parent_relationship_targets,
        child_relationships=child_relationships,
    )


def _reference_targets_from_description(description: str, known_objects: Iterable[str]) -> Set[str]:
    targets: Set[str] = set()
    known = set(known_objects) | {"Profile", "Issue__c", "OrderItem"}
    for match in re.finditer(r"\bReferences?\s+(.+?)\s+objects?\b", description, re.IGNORECASE):
        target_text = match.group(1)
        for object_name in known:
            if re.search(rf"\b{re.escape(object_name)}\b", target_text):
                targets.add(object_name)
    return targets


def _build_parent_relationship_targets(
    reference_targets: Mapping[str, Mapping[str, Set[str]]],
) -> Dict[str, Dict[str, Set[str]]]:
    relationships: Dict[str, Dict[str, Set[str]]] = {}
    for object_name, fields in reference_targets.items():
        object_relationships = relationships.setdefault(object_name, {})
        for field_name, targets in fields.items():
            for relationship_name in _relationship_names_for_field(field_name, targets):
                object_relationships.setdefault(relationship_name, set()).update(targets)
    return relationships


def _relationship_names_for_field(field_name: str, targets: Set[str]) -> Set[str]:
    names: Set[str] = set()
    if field_name.endswith("Id"):
        base = field_name[:-2]
        if base:
            names.add(base)
    if field_name.endswith("__c"):
        names.add(f"{field_name[:-3]}__r")

    if field_name == "OwnerId":
        names.add("Owner")
    if field_name == "CreatedById":
        names.add("CreatedBy")
    if field_name == "LastModifiedById":
        names.add("LastModifiedBy")
    if field_name == "ParentId":
        names.add("Parent")
    if field_name == "RelatedToId":
        names.add("RelatedTo")
    if field_name == "WhatId":
        names.add("What")

    if len(targets) == 1:
        names.update(targets)
    return {name for name in names if name}


def normalize_query(query: str) -> str:
    """Normalize harmless query formatting while preserving literal content."""
    parts = _literal_preserving_parts(query.strip())
    placeholders: List[str] = []
    normalized_parts: List[str] = []
    for is_literal, text in parts:
        if is_literal:
            placeholder = f"@@LITERAL_{len(placeholders)}@@"
            placeholders.append(text)
            normalized_parts.append(placeholder)
        else:
            normalized_parts.append(text.lower())

    normalized = "".join(normalized_parts).strip()
    normalized = re.sub(r";+\s*$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*(<=|>=|!=|=|<|>)\s*", r"\1", normalized)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*\)\s*", ")", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for index, literal in enumerate(placeholders):
        normalized = normalized.replace(f"@@literal_{index}@@", literal)
        normalized = normalized.replace(f"@@LITERAL_{index}@@", literal)
    return normalized


def _literal_preserving_parts(query: str) -> List[tuple[bool, str]]:
    parts: List[tuple[bool, str]] = []
    buffer: List[str] = []
    literal: List[str] = []
    in_quote: Optional[str] = None
    escaped = False

    def flush_buffer() -> None:
        if buffer:
            parts.append((False, "".join(buffer)))
            buffer.clear()

    for char in query:
        if escaped:
            escaped = False
            if in_quote:
                literal.append(char)
            else:
                buffer.append(char)
            continue
        if char == "\\":
            escaped = True
            if in_quote:
                literal.append(char)
            else:
                buffer.append(char)
            continue
        if in_quote:
            literal.append(char)
            if char == in_quote:
                parts.append((True, "".join(literal)))
                literal.clear()
                in_quote = None
            continue
        if char in {"'", '"'}:
            flush_buffer()
            in_quote = char
            literal.append(char)
            continue
        buffer.append(char)

    if literal:
        parts.append((True, "".join(literal)))
    flush_buffer()
    return parts
