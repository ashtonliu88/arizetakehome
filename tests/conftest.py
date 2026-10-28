import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from router_lab.manifest import load_settings
from router_lab.tracing import Tracing


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def telemetry():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(provider)
    yield tracing, exporter
    tracing.close()
