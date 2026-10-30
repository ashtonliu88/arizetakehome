"""Conservative local extraction. A binding guard does not prove semantic intent."""

from __future__ import annotations

import re

from ..util import digest
from .contracts import RequestBindings, RequestInput

# Unknown semantics are intentionally misses, not a guess about what a user means.
KNOWN = set(
    """get show fetch retrieve check inspect tell me the a an of for on in and its this that
please current latest status details issue ticket bug test run results stored outcome deployment
deployed version service environment production staging development prod stage dev compare versus vs
with to against first second source target baseline candidate documentation docs documented code
implementation actual find search look up about query calculate compute add plus subtract minus from
multiply times divide by then associated linked related result runs both between difference sum
what is are how does explain mean concept recursion missing identifier need information id test_run_id
return read report give can you information lookup help i want would like could we see regarding
""".split()
)


def namespace(inp: RequestInput) -> str:
    return digest(
        {
            "tenant": inp.context.tenant,
            "capabilities": sorted(inp.context.capabilities),
            "grants": sorted(inp.context.grants),
        }
    )


def bind(inp: RequestInput) -> RequestBindings:
    text = inp.request
    spans: list[tuple[int, int, str, str | float]] = []
    unresolved = []
    for typ, pattern in [
        ("issue", r"\bENG-\d+\b"),
        ("test", r"\bTR-\d+\b"),
        ("environment", r"\b(?:production|staging|development|prod|stage|dev)\b"),
        ("query", r'["`]([^"`]+)["`]'),
    ]:
        for match in re.finditer(pattern, text, re.I):
            value = match.group(1) if typ == "query" else match.group()
            if typ in ("issue", "test"):
                value = value.upper()
            if typ == "environment":
                value = {"prod": "production", "stage": "staging", "dev": "development"}.get(
                    value.lower(), value.lower()
                )
            spans.append((match.start(), match.end(), typ, value))
    for match in re.finditer(r"\bservice\s+([a-z][\w-]*)", text, re.I):
        if match.group(1).lower() not in {"in", "on", "environment", "status", "version"}:
            spans.append((match.start(1), match.end(1), "service", match.group(1).lower()))
    for alias, targets in inp.context.aliases.items():
        for match in re.finditer(r"\b" + re.escape(alias) + r"\b", text, re.I):
            if len(targets) != 1:
                unresolved.append(f"ambiguous alias: {alias}")
            elif re.fullmatch(r"ENG-\d+|TR-\d+", targets[0]):
                spans.append(
                    (
                        match.start(),
                        match.end(),
                        "issue" if targets[0].startswith("ENG") else "test",
                        targets[0],
                    )
                )
            else:
                unresolved.append(f"unsupported alias: {alias}")
    # Numbers inside identifiers/queries are not arithmetic operands.
    for match in re.finditer(r"(?<![\w-])-?\d+(?:\.\d+)?(?![\w-])", text):
        if not any(start <= match.start() < end for start, end, _, _ in spans):
            spans.append((match.start(), match.end(), "number", float(match.group())))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    slots, types, replacements, counts = {}, {}, [], {}
    last_end = -1
    for start, end, typ, value in spans:
        if start < last_end:
            unresolved.append("overlapping references")
            continue
        key = f"{typ}{counts.get(typ, 0)}"
        counts[typ] = counts.get(typ, 0) + 1
        slots[key], types[key] = value, typ
        replacements.append((start, end, f"<{key}>"))
        last_end = end
    for typ in ("service", "environment"):
        value = getattr(inp.context, typ)
        if value and typ not in counts:
            key = f"{typ}0"
            slots[key], types[key] = value, typ
    skeleton = text
    for start, end, replacement in reversed(replacements):
        skeleton = skeleton[:start] + replacement + skeleton[end:]
    skeleton = " ".join(skeleton.lower().split())
    residual = re.sub(r"<\w+>", " ", skeleton)
    words = set(re.findall(r"[a-z_]+", residual))
    unknown = words - KNOWN
    flags = set()
    if re.search(r"\b(explain|concept|mean|recursion)\b", residual):
        flags.add("requires_planning")
    flags.update(
        f"role:{role}:{slot}"
        for role, slot in re.findall(
            r"\b(source|target|baseline|candidate|first|second)\s+(?:issue\s+)?<(\w+)>", skeleton
        )
    )
    if unknown:
        flags.add("unknown:" + ",".join(sorted(unknown)))
    if re.search(r"\b(not|except|exclude|only|before|after|instead|without|unless)\b", residual):
        flags.add("constraint")
    for name, pattern in {
        "docs": r"\b(docs|documentation|documented)\b",
        "code": r"\b(code|source|implementation)\b",
        "compare": r"\b(compare|versus|vs|against|both|between)\b",
        "linked": r"\b(associated|linked|related)\b",
        "subtract_from": r"\bsubtract\b.+\bfrom\b",
        "subtract": r"\b(subtract|minus|difference)\b| - ",
        "add": r"\b(add|plus|sum)\b|\+",
        "multiply": r"\b(multiply|times)\b|\*",
        "divide": r"\b(divide|by)\b|/",
    }.items():
        if re.search(pattern, residual):
            flags.add(name)
    # Resource categories and multiplicity are structural, independent of values.
    flags.update(f"count:{typ}:{count}" for typ, count in counts.items())
    if re.search(r"\b(deployment|deployed)\b", text, re.I):
        unresolved.extend(f"missing {typ}" for typ in ("service", "environment") if f"{typ}0" not in slots)
    if re.search(r"\b(issue|ticket)\b", text, re.I) and "issue0" not in slots:
        unresolved.append("missing issue identifier")
    if re.search(r"\b(test results|stored results)\b", text, re.I) and not (
        {"test0", "issue0"} & slots.keys()
    ):
        unresolved.append("missing test run identifier")
    if re.search(r"\brun tests\b", text, re.I):
        unresolved.append("test execution unavailable")
    if (
        re.search(r"\b(calculate|compute|add|subtract|multiply|divide)\b", text, re.I)
        and counts.get("number", 0) < 2
    ):
        unresolved.append("missing arithmetic operand")
    return RequestBindings(
        slots=slots,
        slot_types=types,
        skeleton=skeleton,
        namespace=namespace(inp),
        unresolved=unresolved,
        semantics=sorted(flags),
    )
