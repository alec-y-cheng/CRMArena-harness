#!/usr/bin/env python3
"""Run a local MCP-compatible Salesforce SObject Reads server over stdio.

This is a development shim for EWM Phase 0.5. It mirrors the generic Hosted
SObject Reads tool surface while using the CRMArena Salesforce API credentials
through Simple Salesforce.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


PROTOCOL_VERSION = "2025-06-18"


def make_response(request_id: Any, result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result or {}
    return response


def make_error(code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return error


def handle_request(adapter: Any, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = request.get("method")
    request_id = request.get("id")

    if request_id is None:
        # Notification; ignore for this simple stdio server.
        return None

    if method == "initialize":
        return make_response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "local-salesforce-sobject-reads",
                    "version": "0.1.0",
                },
            },
        )

    if method == "tools/list":
        return make_response(request_id, {"tools": adapter.list_tools()})

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return make_response(request_id, error=make_error(-32602, "Missing params.name"))
        result = adapter.call_tool(name, arguments)
        return make_response(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, sort_keys=True),
                    }
                ],
                "structuredContent": result,
                "isError": not bool(result.get("ok", False)),
            },
        )

    return make_response(request_id, error=make_error(-32601, "Method not found: {}".format(method)))


def run_stdio(adapter: Any) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps(make_response(None, error=make_error(-32700, str(exc)))), flush=True)
            continue
        response = handle_request(adapter, request)
        if response is not None:
            print(json.dumps(response, sort_keys=True), flush=True)
    return 0


def run_demo(adapter: Any, object_name: str) -> int:
    print(json.dumps({"tools": adapter.list_tools()}, indent=2, sort_keys=True))
    print(json.dumps(adapter.call_tool("getObjectSchema", {}), indent=2, sort_keys=True))
    print(json.dumps(adapter.call_tool("getObjectSchema", {"object-name": object_name}), indent=2, sort_keys=True))
    print(json.dumps(adapter.call_tool("getUserInfo", {}), indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-type", default="b2b", choices=["b2b", "b2c", "original"])
    parser.add_argument("--demo", action="store_true", help="Print tools/schema/user examples instead of serving stdio.")
    parser.add_argument("--demo-object", default="Account")
    args = parser.parse_args()

    from ewm.mcp import SalesforceReadMCPAdapter

    adapter = SalesforceReadMCPAdapter(org_type=args.org_type)
    if args.demo:
        return run_demo(adapter, args.demo_object)
    return run_stdio(adapter)


if __name__ == "__main__":
    raise SystemExit(main())
