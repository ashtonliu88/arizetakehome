from __future__ import annotations

import math
import re
from collections import Counter

from ..util import digest
from .contracts import PlanTemplate, RequestBindings, Step
from .service import contracts


def features(text: str) -> Counter:
    words = re.findall(r"<\w+>|[a-z_]+|[+*/-]", text.lower())
    return Counter(words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)])


def retrieve(bindings: RequestBindings, bank: list[PlanTemplate], exact=False):
    if not bank:
        return None, 0.0, 0.0
    # Duplicate successful history workflows should not create artificial ambiguity.
    unique = {}
    for plan in bank:
        key = digest([plan.skeleton, [s.model_dump() for s in plan.steps], plan.namespace, plan.contracts])
        unique.setdefault(key, plan)
    plans = list(unique.values())
    documents = [features(p.skeleton) for p in plans]
    query = features(bindings.skeleton)
    df = Counter(term for doc in documents for term in doc)
    idf = {term: math.log((1 + len(documents)) / (1 + df[term])) + 1 for term in set(df) | set(query)}

    def vector(doc):
        weighted = {term: count * idf[term] for term, count in doc.items()}
        norm = math.sqrt(sum(value**2 for value in weighted.values())) or 1
        return {term: value / norm for term, value in weighted.items()}

    qv = vector(query)
    scores = []
    for plan, doc in zip(plans, documents, strict=False):
        score = (
            1.0
            if plan.skeleton == bindings.skeleton
            else sum(qv.get(k, 0) * v for k, v in vector(doc).items())
        )
        if not exact or plan.skeleton == bindings.skeleton:
            scores.append((score, plan))
    scores.sort(key=lambda pair: (-pair[0], pair[1].template_id))
    if not scores:
        return None, 0.0, 0.0
    best = scores[0]
    # Alternate wording for the identical plan is not an ambiguous plan choice.
    alternate = next(
        (score for score, p in scores[1:] if p.steps != best[1].steps or p.namespace != best[1].namespace), 0
    )
    return best[1], best[0], best[0] - alternate


def compatible(plan: PlanTemplate, bindings: RequestBindings, *, semantic=True) -> str | None:
    if plan.namespace != bindings.namespace:
        return "namespace"
    if any(contracts().get(tool) != version for tool, version in plan.contracts.items()):
        return "contract_version"
    if bindings.unresolved:
        return "unresolved_binding"
    if plan.slot_types != bindings.slot_types:
        return "roles_or_multiplicity"
    if semantic:
        if any(s.startswith("unknown:") or s == "constraint" for s in bindings.semantics):
            return "unknown_semantics"
        if plan.semantics != bindings.semantics:
            return "semantic_signature"
    return None


def resolve(steps: list[Step], bindings: RequestBindings, outputs: list[dict], index: int) -> Step:
    arguments = {}
    for key, value in steps[index].arguments.items():
        if isinstance(value, str) and value.startswith("$slot."):
            value = bindings.slots[value[6:]]
        elif isinstance(value, str) and value.startswith("$step."):
            parts = value.split(".")
            previous = int(parts[1])
            if previous >= index:
                raise ValueError("dependency must precede consumer")
            value = outputs[previous]["result"]
            for part in parts[2:]:
                value = value[part]
        arguments[key] = value
    return Step(tool=steps[index].tool, arguments=arguments)


def parameterize(steps: list[Step], bindings: RequestBindings, provenance: dict[str, str]) -> PlanTemplate:
    parameterized = []
    for step in steps:
        args = {}
        for key, value in step.arguments.items():
            if isinstance(value, str) and value.startswith("$step."):
                if not re.fullmatch(r"\$step\.[0-2]\.record\.test_run_id", value):
                    raise ValueError("unsupported dependency")
                args[key] = value
            elif isinstance(value, str) and value.startswith("$slot."):
                if value[6:] not in bindings.slots:
                    raise ValueError("missing slot")
                args[key] = value
            elif key == "operation" and value in ("add", "subtract", "multiply", "divide"):
                args[key] = value
            else:
                matches = [name for name, bound in bindings.slots.items() if bound == value]
                if len(matches) != 1:
                    raise ValueError("literal cannot be parameterized unambiguously")
                args[key] = "$slot." + matches[0]
        parameterized.append(Step(tool=step.tool, arguments=args))
    return PlanTemplate(
        template_id=digest([bindings.skeleton, [s.model_dump() for s in parameterized]])[:20],
        skeleton=bindings.skeleton,
        namespace=bindings.namespace,
        slot_types=bindings.slot_types,
        semantics=bindings.semantics,
        steps=parameterized,
        contracts={s.tool: contracts()[s.tool] for s in steps},
        provenance=provenance,
    )


def admit_history(record, plan, provenance, *, history_success: bool):
    """Accept a history-only success certificate, never an oracle or labeled request.

    The offline seed orchestrator checks history outcomes. Runtime execution and
    this admission boundary receive no expected paths, facts, or held-out labels.
    """
    if not history_success or record.status != "completed" or plan.kind != "tools" or record.replans:
        raise ValueError("history execution not certified successful")
    if not record.executions or any(not e["result"].get("found") for e in record.executions):
        raise ValueError("history tools not successful")
    return parameterize(plan.steps, record.bindings, provenance)
