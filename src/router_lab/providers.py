from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Protocol

import openai

from .budget import Budget
from .models import (
    CallRecord,
    RouteChoice,
    Settings,
    Usage,
    validate_probabilities,
)
from .prompts import ARGUMENT_PROMPT, ROUTING_PROMPT
from .tracing import span_id
from .util import append_jsonl, now


class Provider(Protocol):
    def call(self, kind: str, request: str, catalog: list[dict]) -> list[CallRecord]: ...


def response_text(raw: dict) -> str:
    if raw.get("status") != "completed":
        raise ValueError("incomplete response")
    pieces = []
    for output in raw.get("output", []):
        for item in output.get("content", []):
            if item.get("type") == "refusal":
                raise ValueError("refusal")
            if item.get("type") == "output_text":
                pieces.append(item["text"])
    if not pieces:
        raise ValueError("missing output text")
    return "".join(pieces)


def parse_decision(raw: dict, record: CallRecord) -> None:
    answers = raw.get("answers", [])
    if len(answers) != 1:
        raise ValueError("expected one decision answer")
    answer = answers[0]
    if answer.get("type") != "choice" or answer.get("name") != "next_action":
        raise ValueError("refusal or unexpected decision answer")
    record.action = RouteChoice(action=answer.get("choice")).action
    confidence = answer.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("unusable decision confidence")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("unusable decision confidence")
    record.confidence = confidence
    items = answer.get("probabilities", [])
    probabilities = {item["value"]: item["probability"] for item in items}
    if len(items) != len(probabilities):
        raise ValueError("duplicate probability option")
    validate_probabilities(probabilities)
    record.probabilities = probabilities


class OpenAIProvider:
    def __init__(
        self,
        settings: Settings,
        tracing,
        budget: Budget,
        call_log: Path = Path("results/calls.jsonl"),
        *,
        headroom=True,
        client=None,
    ):
        if client is None and (not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your-key"):
            raise RuntimeError("add OPENAI_API_KEY to .env and run with uv run --env-file .env")
        self.settings, self.tracing, self.budget = settings, tracing, budget
        self.headroom, self.call_log = headroom, call_log
        self.client = client or openai.OpenAI(timeout=settings.timeout_seconds, max_retries=0)

    def estimate_call(self, kind: str, request: str, catalog: list[dict], output_tokens=None) -> float:
        # UTF-8 bytes bound ordinary text token counts conservatively. Schema overhead
        # and a 2x margin protect the scheduler; this is not a provider billing limit.
        n = len((request + json.dumps(catalog) + ROUTING_PROMPT + ARGUMENT_PROMPT).encode()) + 5000
        rates = self.settings.pricing["decisions" if kind == "decisions" else "llm"]
        return (
            (
                n * max(rates.input, rates.cache_write)
                + (output_tokens or self.settings.max_output_tokens) * rates.output
            )
            * 2
            / 1e6
        )

    def call(self, kind: str, request: str, catalog: list[dict]) -> list[CallRecord]:
        records = []
        for attempt in range(self.settings.max_retries + 1):
            record, transient = self._attempt(kind, request, catalog, attempt)
            records.append(record)
            if not transient:
                break
            if attempt < self.settings.max_retries:
                time.sleep(min(2**attempt, 4))
        return records

    def _attempt(
        self, kind, request, catalog, attempt, *, schema=None, instructions=None, output_tokens=None
    ):
        estimate = self.estimate_call(kind, request, catalog, output_tokens)
        reservation = self.budget.reserve_call(estimate, kind, headroom=self.headroom)
        record = CallRecord(kind=kind, attempt=attempt, timestamp=now())
        usage_known = False
        transient = False
        start = time.perf_counter()
        with self.tracing.span(f"{kind} call", "CHAIN", **{"input.value": request}) as span:
            try:
                if kind == "decisions":
                    response = self.client.decisions.create(
                        model=self.settings.decision_model,
                        input=request,
                        questions=[
                            {
                                "type": "choice",
                                "name": "next_action",
                                "instructions": ROUTING_PROMPT,
                                "choices": catalog,
                            }
                        ],
                    )
                else:
                    response = self.client.responses.create(
                        model=self.settings.llm_model,
                        reasoning={"effort": self.settings.reasoning_effort},
                        max_output_tokens=output_tokens or self.settings.max_output_tokens,
                        instructions=instructions or (ROUTING_PROMPT + "\nCatalog:\n" + json.dumps(catalog)),
                        input=request,
                        store=False,
                        **(
                            {
                                "text": {
                                    "format": {
                                        "type": "json_schema",
                                        "name": "route" if schema is None else "arguments",
                                        "strict": True,
                                        "schema": schema or RouteChoice.model_json_schema(),
                                    }
                                }
                            }
                            if kind != "answer"
                            else {}
                        ),
                    )
                record.raw = response.model_dump(mode="json", exclude_unset=True)
                record.usage = Usage.from_provider(record.raw.get("usage") or {})
                if not record.raw.get("usage"):
                    record.cost_usd, record.cost_estimated = estimate, True
                else:
                    rates = self.settings.pricing["decisions" if kind == "decisions" else "llm"]
                    record.cost_usd = rates.cost(record.usage)
                    usage_known = True
                if kind == "decisions":
                    parse_decision(record.raw, record)
                elif kind == "llm":
                    record.action = RouteChoice.model_validate_json(response_text(record.raw)).action
                else:
                    response_text(record.raw)
            except Exception as exc:
                # Provider exception messages can contain credentials or proxy URLs.
                # Save type/status and response body, never request headers.
                status = getattr(exc, "status_code", None)
                if not usage_known:
                    record.cost_usd, record.cost_estimated = estimate, True
                record.error = (
                    str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__} status={status}"
                )
                if isinstance(exc, openai.APIError) and isinstance(getattr(exc, "body", None), dict):
                    record.raw = {"provider_error": exc.body}
                transient = isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)) or (
                    isinstance(exc, openai.APIStatusError) and (status in (408, 409, 429) or status >= 500)
                )
                span.set_attribute("router.error", record.error)
            finally:
                record.latency_ms = (time.perf_counter() - start) * 1000
                record.span_id = self.tracing.capture.pop(span.get_span_context().span_id) or span_id(span)
                span.set_attribute("router.cost_usd", record.cost_usd)
                self.budget.settle(reservation, record.cost_usd, record.cost_estimated)
                append_jsonl(self.call_log, record.model_dump(mode="json"))
        return record, transient

    def generate(self, kind, request, *, instructions, schema=None) -> list[CallRecord]:
        records = []
        for attempt in range(self.settings.max_retries + 1):
            record, transient = self._attempt(
                kind,
                request,
                [],
                attempt,
                schema=schema,
                instructions=instructions,
                output_tokens=self.settings.answer_max_output_tokens,
            )
            records.append(record)
            if not transient:
                break
            if attempt < self.settings.max_retries:
                time.sleep(min(2**attempt, 4))
        return records
