from __future__ import annotations

import json
import os
from contextlib import contextmanager
from threading import Lock

from opentelemetry.sdk.trace import SpanProcessor


class CaptureProcessor(SpanProcessor):
    """Remember automatic SDK spans so grades attach to the actual provider call."""

    def __init__(self):
        self.children = {}
        self.lock = Lock()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        if span.parent and span.attributes.get("openinference.span.kind") in ("LLM", "DECISION"):
            with self.lock:
                self.children[span.parent.span_id] = span.context.span_id

    def pop(self, parent_id):
        with self.lock:
            child = self.children.pop(parent_id, None)
        return f"{child:016x}" if child else None

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


class Tracing:
    def __init__(self, provider=None):
        phoenix_provider = provider is None
        if provider is None:
            from phoenix.otel import register

            endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006").rstrip("/")
            if not endpoint.endswith("/v1/traces"):
                endpoint += "/v1/traces"
            provider = register(
                project_name=os.getenv("PHOENIX_PROJECT_NAME", "decision-router-lab"),
                endpoint=endpoint,
                protocol="http/protobuf",
                auto_instrument=True,
                batch=True,
            )
        self.provider = provider
        self.capture = CaptureProcessor()
        if phoenix_provider:
            provider.add_span_processor(self.capture, replace_default_processor=False)
        else:
            provider.add_span_processor(self.capture)
        self.tracer = provider.get_tracer("router_lab")

    @contextmanager
    def span(self, name, kind="CHAIN", **attributes):
        with self.tracer.start_as_current_span(name) as span:
            span.set_attribute("openinference.span.kind", kind)
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(
                        key, value if isinstance(value, (str, int, float, bool)) else json.dumps(value)
                    )
            yield span

    def close(self):
        self.provider.force_flush()
        self.provider.shutdown()


def span_id(span):
    return f"{span.get_span_context().span_id:016x}"


def trace_id(span):
    return f"{span.get_span_context().trace_id:032x}"
