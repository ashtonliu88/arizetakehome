"""Read-only local HTTP tools. Authoritative bindings come from stored records."""

from __future__ import annotations

import copy
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..tools import CATALOG, execute
from ..util import digest
from .contracts import ApplicationContext, Step


def contracts() -> dict[str, str]:
    return {
        t.action_id: digest(
            {
                "http_contract": "reuse-read-only-v1",
                "description": t.description,
                "arguments": t.argument_schema.model_json_schema(),
                "envelope": ["tool", "arguments", "bindings", "tenant", "state_version", "result"],
            }
        )
        for t in CATALOG
        if t.argument_schema
    }


def resource_key(tool: str, arguments: dict) -> str:
    if tool == "lookup_issue":
        return arguments["issue_id"]
    if tool == "lookup_test_results":
        return arguments["test_run_id"]
    if tool == "lookup_deployment":
        return f"{arguments['service']}/{arguments['environment']}"
    return tool + ":" + digest(arguments)


class GuardError(ValueError):
    pass


def validate_arguments(step: Step, context: ApplicationContext) -> dict:
    if step.tool not in context.capabilities:
        raise GuardError("capability denied")
    definition = next(t for t in CATALOG if t.action_id == step.tool)
    args = definition.argument_schema.model_validate(step.arguments).model_dump()
    if context.grants and resource_key(step.tool, args) not in context.grants:
        raise GuardError("resource denied")
    return args


def dispatch(step: Step, context: ApplicationContext, state: dict) -> dict:
    arguments = validate_arguments(step, context)
    result = execute(step.tool, arguments, state[context.tenant])
    record = result.get("record") or {}
    if step.tool == "lookup_issue":
        binding = {"issue_id": record.get("issue_id")}
    elif step.tool == "lookup_test_results":
        binding = {"test_run_id": record.get("test_run_id")}
    elif step.tool == "lookup_deployment":
        binding = {k: record.get(k) for k in ("service", "environment")}
    else:
        binding = arguments
    return {
        "tool": step.tool,
        "arguments": arguments,
        "bindings": binding,
        "tenant": context.tenant,
        "state_version": digest(state),
        "result": result,
    }


@contextmanager
def tool_service(state: dict):
    frozen_state = copy.deepcopy(state)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                if self.path != "/execute":
                    raise ValueError("unknown endpoint")
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 65536:
                    raise ValueError("invalid body size")
                data = json.loads(self.rfile.read(size))
                result = dispatch(
                    Step.model_validate(data["step"]),
                    ApplicationContext.model_validate(data["context"]),
                    frozen_state,
                )
                status = 200
            except (ValueError, KeyError) as exc:
                result, status = {"error": str(exc)}, 400
            body = json.dumps(result, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield HTTPAdapter(f"http://127.0.0.1:{server.server_port}", digest(frozen_state))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class HTTPAdapter:
    def __init__(self, endpoint: str, state_version: str):
        self.endpoint, self.state_version = endpoint, state_version

    def execute(self, step: Step, context: ApplicationContext) -> dict:
        validate_arguments(step, context)
        body = json.dumps({"step": step.model_dump(), "context": context.model_dump()}).encode()
        request = urllib.request.Request(
            self.endpoint + "/execute", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise GuardError("tool service rejected arguments or authorization") from exc
        if result["tenant"] != context.tenant or result["state_version"] != self.state_version:
            raise GuardError("returned tenant/state mismatch")
        if result["tool"] != step.tool or result["arguments"] != step.arguments:
            raise GuardError("returned invocation mismatch")
        if result["result"].get("found"):
            for key, value in result["bindings"].items():
                if step.arguments.get(key) != value:
                    raise GuardError("wrong returned binding")
            expected = {
                "lookup_issue": {"issue_id"},
                "lookup_test_results": {"test_run_id"},
                "lookup_deployment": {"service", "environment"},
            }.get(step.tool, set(step.arguments))
            if set(result["bindings"]) != expected:
                raise GuardError("missing returned bindings")
        return result
