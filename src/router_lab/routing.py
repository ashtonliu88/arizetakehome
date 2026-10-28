from __future__ import annotations

import json
import math
import time

from .models import RouteResult, Usage
from .tools import CATALOG, catalog_payload
from .tracing import span_id, trace_id


class Router:
    def __init__(self, policy, provider, tracing, threshold=0.0, always_fallback=False):
        if policy not in ("llm", "decisions", "hybrid"):
            raise ValueError("unknown policy")
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be in [0,1]")
        self.policy, self.provider, self.tracing = policy, provider, tracing
        self.threshold, self.always_fallback = threshold, always_fallback

    def route(self, request: str, catalog=CATALOG) -> RouteResult:
        start = time.perf_counter()
        result = RouteResult()
        with self.tracing.span(f"routing {self.policy}", "CHAIN", **{"input.value": request}) as span:
            result.trace_id, result.policy_span_id = trace_id(span), span_id(span)
            kind = "llm" if self.policy == "llm" else "decisions"
            calls = self.provider.call(kind, request, catalog_payload(catalog))
            initial = calls[-1]
            result.calls.extend(calls)
            result.initial_action = initial.action
            result.initial_span_id = initial.span_id
            result.decision_confidence = initial.confidence if kind == "decisions" else None
            result.option_probabilities = initial.probabilities if kind == "decisions" else {}
            final = initial
            if self.policy == "hybrid":
                if initial.error or initial.action is None or initial.confidence is None:
                    result.fallback_reason = "operational"
                elif self.always_fallback:
                    result.fallback_reason = "always"
                elif initial.confidence < self.threshold:
                    result.fallback_reason = "confidence"
                if result.fallback_reason:
                    result.fallback = True
                    fallback_calls = self.provider.call("llm", request, catalog_payload(catalog))
                    result.calls.extend(fallback_calls)
                    final = fallback_calls[-1]
            result.final_action = final.action if final.error is None else None
            result.final_span_id = final.span_id
            result.errors = [call.error for call in result.calls if call.error]
            result.cost_usd = sum(call.cost_usd for call in result.calls)
            result.usage = Usage(
                **{key: sum(getattr(c.usage, key) for c in result.calls) for key in Usage.model_fields}
            )
            # Ends before evaluation, export, persistence and Phoenix annotations.
            result.latency_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("router.cost_usd", result.cost_usd)
            span.set_attribute("router.fallback_reason", result.fallback_reason or "none")
            span.set_attribute("output.value", json.dumps({"final_action": result.final_action}))
        return result
