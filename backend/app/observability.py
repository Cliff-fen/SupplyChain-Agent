from contextlib import contextmanager
from functools import wraps
from inspect import isasyncgenfunction
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

from app.core.config import get_settings

HTTP_REQUESTS = Counter(
    "supplymind_http_requests_total",
    "Total HTTP requests handled by the API",
    ("method", "path", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "supplymind_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "path"),
)
AGENT_RUNS = Counter(
    "supplymind_agent_runs_total",
    "Agent runs by route and terminal status",
    ("route", "status"),
)
AGENT_SUBAGENT_DURATION = Histogram(
    "supplymind_agent_subagent_duration_seconds",
    "Subagent execution latency",
    ("agent", "status"),
)
AGENT_FALLBACKS = Counter(
    "supplymind_agent_fallbacks_total",
    "Agent degradation and fallback decisions",
    ("stage", "fallback"),
)
RAG_STAGE_DURATION = Histogram(
    "supplymind_rag_stage_duration_seconds",
    "Advanced RAG stage latency",
    ("stage",),
)
MCP_TOOL_CALLS = Counter(
    "supplymind_mcp_tool_calls_total",
    "MCP tool calls by tool and status",
    ("tool", "status"),
)
MODEL_TOKENS = Counter(
    "supplymind_model_tokens_total",
    "Estimated model tokens emitted or consumed",
    ("model", "direction"),
)

_configured = False


def configure_telemetry(service_name: str) -> None:
    global _configured
    if _configured:
        return
    endpoint = get_settings().otel_exporter_otlp_endpoint
    if not endpoint:
        _configured = True
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.version": "0.1.0",
                "deployment.environment": get_settings().env,
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _configured = True


@contextmanager
def genai_span(name: str, attributes: dict[str, Any] | None = None, *, context=None):
    with trace.get_tracer("supplymind.genai").start_as_current_span(name, context=context) as span:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
            raise


def model_operation(name: str):
    """Observe real requests without recording prompts, credentials or rows."""
    def decorate(function):
        if isasyncgenfunction(function):
            @wraps(function)
            async def streaming(*args, **kwargs):
                with genai_span(name, {"gen_ai.operation.name": function.__name__}):
                    async for value in function(*args, **kwargs):
                        yield value
            return streaming

        @wraps(function)
        async def request(*args, **kwargs):
            with genai_span(name, {"gen_ai.operation.name": function.__name__}):
                return await function(*args, **kwargs)
        return request
    return decorate
