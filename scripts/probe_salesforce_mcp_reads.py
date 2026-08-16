#!/usr/bin/env python3
"""Non-mutating probe for Salesforce Hosted MCP SObject Reads.

The script records the MCP handshake, tools/list response, and optional
read-only tool calls. It intentionally does not assume exact Salesforce tool
names; it discovers them from tools/list and then uses simple name matching for
optional examples.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_PROTOCOL_VERSION = "2025-06-18"


class MCPProbeClient:
    def __init__(self, url: str, token: str, protocol_version: str) -> None:
        self.url = url
        self.token = token
        self.protocol_version = protocol_version
        self.next_id = 1

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.next_id,
            "method": method,
        }
        self.next_id += 1
        if params is not None:
            payload["params"] = params

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": self.protocol_version,
            },
        )

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "status": resp.status,
                    "elapsed_s": round(time.time() - started, 3),
                    "request": redact_request(payload),
                    "response_headers": dict(resp.headers.items()),
                    "raw": raw,
                    "json": parse_json_maybe(raw),
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return {
                "ok": False,
                "status": exc.code,
                "elapsed_s": round(time.time() - started, 3),
                "request": redact_request(payload),
                "response_headers": dict(exc.headers.items()) if exc.headers else {},
                "raw": raw,
                "json": parse_json_maybe(raw),
                "error": str(exc),
            }
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "status": None,
                "elapsed_s": round(time.time() - started, 3),
                "request": redact_request(payload),
                "raw": "",
                "json": None,
                "error": str(exc),
            }

    def initialize(self) -> Dict[str, Any]:
        return self.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "crmarena-ewm-phase0-probe",
                    "version": "0.1.0",
                },
            },
        )

    def tools_list(self) -> Dict[str, Any]:
        return self.request("tools/list")

    def tools_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )


def parse_json_maybe(raw: str) -> Optional[Any]:
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("data:"):
        lines = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                lines.append(line[len("data:") :].strip())
        raw = "\n".join(lines).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def redact_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def extract_tools(tools_list_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = tools_list_response.get("json")
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if not isinstance(result, dict):
        return []
    tools = result.get("tools")
    if not isinstance(tools, list):
        return []
    return [tool for tool in tools if isinstance(tool, dict)]


def find_tool(tools: Iterable[Dict[str, Any]], needles: Iterable[str]) -> Optional[str]:
    scored: List[Tuple[int, str]] = []
    needle_list = [needle.lower() for needle in needles]
    for tool in tools:
        name = str(tool.get("name") or "")
        desc = str(tool.get("description") or "")
        haystack = f"{name} {desc}".lower()
        score = sum(1 for needle in needle_list if needle in haystack)
        if score:
            scored.append((score, name))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def maybe_call(
    client: MCPProbeClient,
    label: str,
    tool_name: Optional[str],
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    if not tool_name:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"Could not infer tool name for {label} from tools/list.",
            "arguments": arguments,
        }
    return client.tools_call(tool_name, arguments)


def build_arg_candidates(primary_name: str, value: str) -> List[Dict[str, Any]]:
    """Return common argument spellings without assuming Salesforce's exact schema."""
    if primary_name == "object":
        return [
            {"object-name": value},
            {"objectName": value},
            {"sobject-name": value},
            {"sobjectName": value},
        ]
    if primary_name == "query":
        return [{"query": value}]
    if primary_name == "search":
        return [{"search": value}]
    return [{primary_name: value}]


def first_call_that_runs(
    client: MCPProbeClient,
    label: str,
    tool_name: Optional[str],
    arg_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    attempts = []
    for arguments in arg_candidates:
        result = maybe_call(client, label, tool_name, arguments)
        attempts.append(result)
        if result.get("ok"):
            return {"ok": True, "attempts": attempts}
    return {"ok": False, "attempts": attempts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("SF_MCP_URL"))
    parser.add_argument("--token", default=os.environ.get("SF_MCP_BEARER_TOKEN"))
    parser.add_argument("--protocol-version", default=os.environ.get("MCP_PROTOCOL_VERSION", DEFAULT_PROTOCOL_VERSION))
    parser.add_argument("--object", default="Account", help="Object to use for optional schema detail probe.")
    parser.add_argument("--query", default=None, help="Optional read-only SOQL query.")
    parser.add_argument("--search", default=None, help="Optional read-only SOSL search.")
    parser.add_argument("--out", default=None, help="Path to write JSON probe output.")
    parser.add_argument("--skip-initialize", action="store_true", help="Try tools/list without initialize.")
    args = parser.parse_args()

    if not args.url:
        print("Missing --url or SF_MCP_URL.", file=sys.stderr)
        return 2
    if not args.token:
        print("Missing --token or SF_MCP_BEARER_TOKEN.", file=sys.stderr)
        return 2

    client = MCPProbeClient(args.url, args.token, args.protocol_version)
    report: Dict[str, Any] = {
        "url": args.url,
        "protocol_version": args.protocol_version,
        "steps": {},
    }

    if not args.skip_initialize:
        report["steps"]["initialize"] = client.initialize()

    report["steps"]["tools_list"] = client.tools_list()
    tools = extract_tools(report["steps"]["tools_list"])
    report["tool_summary"] = [
        {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
        }
        for tool in tools
    ]

    schema_tool = find_tool(tools, ["schema", "object"])
    soql_tool = find_tool(tools, ["soql", "query"])
    sosl_tool = find_tool(tools, ["sosl", "search"])
    user_tool = find_tool(tools, ["user", "context"])

    report["inferred_tool_mapping"] = {
        "DiscoverSchemaIndex_or_DiscoverObjectSchema": schema_tool,
        "RunSoqlQuery": soql_tool,
        "RunSoslSearch": sosl_tool,
        "GetUserContext": user_tool,
    }

    if schema_tool:
        report["steps"]["schema_index"] = maybe_call(client, "schema_index", schema_tool, {})
        report["steps"]["schema_detail"] = first_call_that_runs(
            client,
            "schema_detail",
            schema_tool,
            build_arg_candidates("object", args.object),
        )

    if user_tool:
        report["steps"]["user_context"] = maybe_call(client, "user_context", user_tool, {})

    if args.query:
        report["steps"]["soql_query"] = first_call_that_runs(
            client,
            "soql_query",
            soql_tool,
            build_arg_candidates("query", args.query),
        )

    if args.search:
        report["steps"]["sosl_search"] = first_call_that_runs(
            client,
            "sosl_search",
            sosl_tool,
            build_arg_candidates("search", args.search),
        )

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
