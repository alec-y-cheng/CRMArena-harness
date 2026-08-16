"""Local Salesforce read adapter with a Hosted SObject Reads-like tool surface.

This module intentionally mirrors Salesforce's generic SObject Reads MCP tools
without encoding CRMArena task families or benchmark workflows. The backend is
Simple Salesforce so we can develop the EWM runtime while Hosted MCP OAuth
access is still pending.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

READ_TOOL_NAMES = [
    "getObjectSchema",
    "soqlQuery",
    "find",
    "getUserInfo",
    "listRecentSobjectRecords",
    "getRelatedRecords",
]

MUTATING_SOQL_RE = re.compile(
    r"\b(insert|update|upsert|delete|undelete|merge|create|drop|alter|truncate)\b",
    re.IGNORECASE,
)


class SalesforceReadMCPAdapter:
    """Read-only MCP-shaped adapter backed by a Salesforce org.

    The public methods return JSON-serializable dictionaries. Raw Salesforce
    results are preserved under `raw` where possible so later EWM normalization
    can create observations/evidence without losing provenance.
    """

    def __init__(self, org_type: str = "b2b", connector: Optional[Any] = None) -> None:
        load_dotenv()
        self.org_type = org_type
        if connector is None:
            from crm_sandbox.env.connect_sandbox import SalesforceConnector

            connector = SalesforceConnector(org_type=org_type)
        self.connector = connector
        self.sf = self.connector.sf
        self._global_describe_cache = None
        self._object_describe_cache: Dict[str, Dict[str, Any]] = {}

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "getObjectSchema",
                "description": (
                    "Return Salesforce schema information. Call with no object-name "
                    "for a compact index, or with object-name for detailed fields, "
                    "picklists, and relationships."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object-name": {
                            "type": "string",
                            "description": "Optional API name of the object to describe.",
                        }
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "soqlQuery",
                "description": "Execute a read-only SOQL SELECT query against Salesforce.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A valid read-only SOQL SELECT query.",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find",
                "description": "Execute a SOSL FIND search across Salesforce objects.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "A valid SOSL FIND search string.",
                        }
                    },
                    "required": ["search"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "getUserInfo",
                "description": "Return context for the currently authenticated Salesforce user.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "listRecentSobjectRecords",
                "description": "Return recently viewed records for one Salesforce object type.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sobject-name": {"type": "string", "description": "Salesforce object API name."},
                        "limit": {"type": "integer", "description": "Maximum records to return."},
                    },
                    "required": ["sobject-name"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "getRelatedRecords",
                "description": "Return child records for a parent record relationship.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sobject-name": {"type": "string", "description": "Parent object API name."},
                        "id": {"type": "string", "description": "Parent Salesforce record Id."},
                        "relationship-path": {
                            "type": "string",
                            "description": "Child relationship name, such as Contacts.",
                        },
                        "limit": {"type": "integer", "description": "Maximum records to return."},
                    },
                    "required": ["sobject-name", "id", "relationship-path"],
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        arguments = arguments or {}
        try:
            if name == "getObjectSchema":
                return self.get_object_schema(arguments.get("object-name") or arguments.get("objectName"))
            if name == "soqlQuery":
                return self.soql_query(require_string(arguments, "query"))
            if name == "find":
                return self.sosl_find(require_string(arguments, "search"))
            if name == "getUserInfo":
                return self.get_user_info()
            if name == "listRecentSobjectRecords":
                object_name = arguments.get("sobject-name") or arguments.get("sobjectName")
                return self.list_recent_sobject_records(require_value(object_name, "sobject-name"), arguments.get("limit"))
            if name == "getRelatedRecords":
                object_name = arguments.get("sobject-name") or arguments.get("sobjectName")
                relationship = arguments.get("relationship-path") or arguments.get("relationshipPath")
                return self.get_related_records(
                    require_value(object_name, "sobject-name"),
                    require_string(arguments, "id"),
                    require_value(relationship, "relationship-path"),
                    arguments.get("limit"),
                )
            return error_result("UNKNOWN_TOOL", "Unknown tool: {}".format(name), {"tool": name})
        except Exception as exc:
            return exception_result(exc)

    def get_object_schema(self, object_name: Optional[str] = None) -> Dict[str, Any]:
        if not object_name:
            raw = self._global_describe()
            objects = []
            for sobj in raw.get("sobjects", []):
                if not sobj.get("queryable"):
                    continue
                objects.append(
                    {
                        "name": sobj.get("name"),
                        "label": sobj.get("label"),
                        "labelPlural": sobj.get("labelPlural"),
                        "custom": sobj.get("custom"),
                        "queryable": sobj.get("queryable"),
                        "searchable": sobj.get("searchable"),
                        "retrieveable": sobj.get("retrieveable"),
                    }
                )
            return ok_result(
                "getObjectSchema",
                {
                    "mode": "index",
                    "objects": objects,
                    "count": len(objects),
                },
                raw=raw,
            )

        desc = self._describe_object(object_name)
        fields = []
        for field in desc.get("fields", []):
            fields.append(
                {
                    "name": field.get("name"),
                    "label": field.get("label"),
                    "type": field.get("type"),
                    "custom": field.get("custom"),
                    "nillable": field.get("nillable"),
                    "createable": field.get("createable"),
                    "updateable": field.get("updateable"),
                    "filterable": field.get("filterable"),
                    "sortable": field.get("sortable"),
                    "referenceTo": field.get("referenceTo"),
                    "relationshipName": field.get("relationshipName"),
                    "picklistValues": normalize_picklists(field.get("picklistValues") or []),
                }
            )
        relationships = []
        for rel in desc.get("childRelationships", []):
            if not rel.get("relationshipName"):
                continue
            relationships.append(
                {
                    "relationshipName": rel.get("relationshipName"),
                    "childSObject": rel.get("childSObject"),
                    "field": rel.get("field"),
                    "deprecatedAndHidden": rel.get("deprecatedAndHidden"),
                }
            )
        return ok_result(
            "getObjectSchema",
            {
                "mode": "detail",
                "object": {
                    "name": desc.get("name"),
                    "label": desc.get("label"),
                    "labelPlural": desc.get("labelPlural"),
                    "custom": desc.get("custom"),
                    "queryable": desc.get("queryable"),
                    "searchable": desc.get("searchable"),
                    "createable": desc.get("createable"),
                    "updateable": desc.get("updateable"),
                    "deletable": desc.get("deletable"),
                },
                "fields": fields,
                "childRelationships": relationships,
            },
            raw=desc,
        )

    def soql_query(self, query: str) -> Dict[str, Any]:
        query = clean_query(query)
        validation = validate_read_only_soql(query)
        if validation:
            return validation
        raw = self.sf.query_all(query)
        records = strip_attributes(raw.get("records", []))
        return ok_result(
            "soqlQuery",
            {
                "records": records,
                "totalSize": raw.get("totalSize", len(records)),
                "done": raw.get("done"),
            },
            raw=raw,
        )

    def sosl_find(self, search: str) -> Dict[str, Any]:
        search = clean_query(search)
        if not search.lower().startswith("find"):
            return error_result("INVALID_SOSL", "SOSL search must start with FIND.", {"search": search})
        raw = self.sf.search(search)
        records = strip_attributes(raw.get("searchRecords", []))
        return ok_result(
            "find",
            {
                "searchRecords": records,
                "totalSize": len(records),
            },
            raw=raw,
        )

    def get_user_info(self) -> Dict[str, Any]:
        username = username_for_org(self.org_type)
        if username:
            safe_username = soql_quote(username)
            query = (
                "SELECT Id, Name, Email, Username, TimeZoneSidKey, LocaleSidKey, "
                "Profile.Name, UserRole.Name, Manager.Name "
                "FROM User WHERE Username = '{}' LIMIT 1"
            ).format(safe_username)
            try:
                raw = self.sf.query_all(query)
                records = strip_attributes(raw.get("records", []))
                if records:
                    return ok_result("getUserInfo", {"user": records[0]}, raw=raw)
            except Exception:
                pass
        return ok_result(
            "getUserInfo",
            {
                "user": {
                    "username": username,
                    "org_type": self.org_type,
                    "instance": getattr(self.sf, "sf_instance", None),
                }
            },
        )

    def list_recent_sobject_records(self, object_name: str, limit: Any = None) -> Dict[str, Any]:
        limit_int = bounded_limit(limit, default=10, maximum=200)
        fields = self._default_select_fields(object_name)
        if "LastViewedDate" not in fields:
            fields.append("LastViewedDate")
        query = (
            "SELECT {} FROM {} WHERE LastViewedDate != null "
            "ORDER BY LastViewedDate DESC LIMIT {}"
        ).format(", ".join(fields), object_name, limit_int)
        return self.soql_query(query)

    def get_related_records(
        self,
        object_name: str,
        record_id: str,
        relationship_path: str,
        limit: Any = None,
    ) -> Dict[str, Any]:
        desc = self._describe_object(object_name)
        rel = self._find_child_relationship(desc, relationship_path)
        if not rel:
            return error_result(
                "UNKNOWN_RELATIONSHIP",
                "Relationship '{}' was not found on {}.".format(relationship_path, object_name),
                {"sobject-name": object_name, "relationship-path": relationship_path},
            )
        child = rel.get("childSObject")
        field = rel.get("field")
        if not child or not field:
            return error_result("INVALID_RELATIONSHIP", "Relationship metadata is incomplete.", rel)
        limit_int = bounded_limit(limit, default=25, maximum=200)
        fields = self._default_select_fields(child)
        query = "SELECT {} FROM {} WHERE {} = '{}' LIMIT {}".format(
            ", ".join(fields),
            child,
            field,
            soql_quote(record_id),
            limit_int,
        )
        result = self.soql_query(query)
        result["relationship"] = {
            "parentObject": object_name,
            "parentId": record_id,
            "relationshipName": relationship_path,
            "childSObject": child,
            "field": field,
        }
        return result

    def _global_describe(self) -> Dict[str, Any]:
        if self._global_describe_cache is None:
            self._global_describe_cache = self.sf.describe()
        return self._global_describe_cache

    def _describe_object(self, object_name: str) -> Dict[str, Any]:
        if object_name not in self._object_describe_cache:
            self._object_describe_cache[object_name] = getattr(self.sf, object_name).describe()
        return self._object_describe_cache[object_name]

    def _default_select_fields(self, object_name: str) -> List[str]:
        desc = self._describe_object(object_name)
        available = set(field.get("name") for field in desc.get("fields", []))
        preferred = ["Id", "Name", "Subject", "CaseNumber", "StageName", "Status", "CreatedDate", "LastModifiedDate"]
        fields = [field for field in preferred if field in available]
        if "Id" not in fields and "Id" in available:
            fields.insert(0, "Id")
        return fields or ["Id"]

    def _find_child_relationship(self, desc: Dict[str, Any], relationship_path: str) -> Optional[Dict[str, Any]]:
        target = relationship_path.lower()
        for rel in desc.get("childRelationships", []):
            name = str(rel.get("relationshipName") or "").lower()
            if name == target:
                return rel
        return None


def ok_result(tool: str, content: Dict[str, Any], raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = {
        "ok": True,
        "tool": tool,
        "content": content,
    }
    if raw is not None:
        result["raw"] = raw
    return result


def error_result(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def exception_result(exc: Exception) -> Dict[str, Any]:
    return error_result(exc.__class__.__name__, str(exc), {})


def require_string(arguments: Dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    return require_value(value, key)


def require_value(value: Any, key: str) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError("Missing required argument: {}".format(key))
    return str(value).strip()


def clean_query(query: str) -> str:
    return " ".join(str(query or "").strip().split())


def validate_read_only_soql(query: str) -> Optional[Dict[str, Any]]:
    lowered = query.lower()
    if not lowered.startswith("select"):
        return error_result("INVALID_SOQL", "SOQL query must start with SELECT.", {"query": query})
    if MUTATING_SOQL_RE.search(query):
        return error_result("MUTATING_QUERY_REJECTED", "Only read-only SOQL SELECT queries are allowed.", {"query": query})
    return None


def strip_attributes(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean = []
    for record in records:
        item = {}
        for key, value in record.items():
            if key == "attributes":
                continue
            if isinstance(value, dict) and "attributes" in value:
                nested = dict(value)
                nested.pop("attributes", None)
                item[key] = nested
            else:
                item[key] = value
        clean.append(item)
    return clean


def normalize_picklists(values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for value in values:
        if not value.get("active", True):
            continue
        normalized.append(
            {
                "label": value.get("label"),
                "value": value.get("value"),
                "defaultValue": value.get("defaultValue"),
            }
        )
    return normalized


def bounded_limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def soql_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def username_for_org(org_type: str) -> Optional[str]:
    env_name = {
        "b2b": "SALESFORCE_B2B_USERNAME",
        "b2c": "SALESFORCE_B2C_USERNAME",
        "original": "SALESFORCE_USERNAME",
    }.get(org_type)
    if not env_name:
        return None
    return os.environ.get(env_name)
