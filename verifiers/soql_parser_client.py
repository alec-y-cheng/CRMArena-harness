import atexit
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class SOQLParserError:
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    token: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class SOQLParseResult:
    success: bool
    errors: Tuple[SOQLParserError, ...]
    tokens: Tuple[Mapping[str, Any], ...] = ()
    parse_tree: Optional[Mapping[str, Any]] = None
    unavailable: bool = False


class SOQLParserService:
    def __init__(self, node_path: Optional[str] = None, script_path: Optional[Path] = None) -> None:
        self.node_path = node_path or self._find_node()
        self.script_path = script_path or Path(__file__).resolve().parent / "soql_parser" / "parse_soql.js"
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 1

    def parse(self, query: str) -> SOQLParseResult:
        if not self.node_path:
            return SOQLParseResult(
                success=True,
                errors=(),
                unavailable=True,
            )
        with self._lock:
            try:
                process = self._ensure_process()
                request_id = self._next_id
                self._next_id += 1
                process.stdin.write(json.dumps({"id": request_id, "query": query}) + "\n")
                process.stdin.flush()
                line = process.stdout.readline()
                if not line:
                    self.close()
                    return SOQLParseResult(
                        success=True,
                        errors=(SOQLParserError("SOQL parser service exited without a response."),),
                        unavailable=True,
                    )
                return self._decode_result(line)
            except Exception as exc:
                self.close()
                return SOQLParseResult(
                    success=True,
                    errors=(SOQLParserError(str(exc)),),
                    unavailable=True,
                )

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _ensure_process(self) -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        env = dict(os.environ)
        env.pop("NODE_OPTIONS", None)
        self._process = subprocess.Popen(
            [self.node_path, str(self.script_path)],
            cwd=str(self.script_path.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        return self._process

    def _decode_result(self, line: str) -> SOQLParseResult:
        payload = json.loads(line)
        errors = tuple(
            SOQLParserError(
                message=str(error.get("message", "")),
                line=error.get("line"),
                column=error.get("column"),
                token=error.get("token"),
            )
            for error in payload.get("errors", [])
            if isinstance(error, Mapping)
        )
        return SOQLParseResult(
            success=bool(payload.get("success")),
            errors=errors,
            tokens=tuple(token for token in payload.get("tokens", []) if isinstance(token, Mapping)),
            parse_tree=payload.get("parseTree") if isinstance(payload.get("parseTree"), Mapping) else None,
        )

    def _find_node(self) -> Optional[str]:
        env_node = os.environ.get("SOQL_PARSER_NODE")
        if env_node:
            return env_node

        path_node = shutil.which("node")
        if path_node:
            return path_node

        repo_root = Path(__file__).resolve().parents[1]
        workspace_root = repo_root.parent
        local_node = workspace_root / "tools" / "node-v20.11.1-linux-arm64" / "bin" / "node"
        if local_node.exists():
            return str(local_node)

        code_server_node = Path("/opt/apps/code_server/4.22.1/lib/node")
        if code_server_node.exists():
            return str(code_server_node)

        return None


_SHARED_SERVICE: Optional[SOQLParserService] = None


def parse_soql(query: str) -> SOQLParseResult:
    global _SHARED_SERVICE
    if _SHARED_SERVICE is None:
        _SHARED_SERVICE = SOQLParserService()
        atexit.register(_SHARED_SERVICE.close)
    return _SHARED_SERVICE.parse(query)
