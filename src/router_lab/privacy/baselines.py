from __future__ import annotations

from .contracts import Judgment


def check_evidence(view: dict, *, exact: bool = False) -> Judgment:
    def result(verdict, why, refs):
        return Judgment(verdict=verdict, explanation=why, evidence_refs=refs, confidence=None)

    if view["identity_semantics"] != "distinct":
        return result("INSUFFICIENT_EVIDENCE", "Identity distinctions were collapsed.", ["requested"])
    if exact and (view["aliases"] or view["linked_scope"] or len(view["requested"]) != 1):
        return result("INSUFFICIENT_EVIDENCE", "Outside simple exact-identity baseline.", ["requested"])

    def key(resource):
        return resource["kind"], resource["key"]

    aliases = {key(a["name"]): key(a["target"]) for a in view["aliases"]}

    def canonical(resource):
        current = key(resource)
        visited = set()
        while current in aliases and aliases[current] != current:
            if current in visited:
                raise ValueError("cyclic alias declaration")
            visited.add(current)
            current = aliases[current]
        return current

    allowed = {canonical(r) for r in view["requested"]}
    # Consume observed links in event order. No private fixture data enters here.
    for index, event in enumerate(view["events"]):
        for field in ("target", "binding"):
            resource = event[field]
            if resource and canonical(resource) not in allowed:
                return result(
                    "FAIL",
                    "Observed resource is outside the declared scope.",
                    [f"events[{index}].{field}", "requested", "linked_scope"],
                )
        for rule in view["linked_scope"]:
            if event["binding"] and canonical(event["binding"]) == canonical(rule["source"]):
                for link in event["links"]:
                    if link["relation"] == rule["relation"]:
                        allowed.add(canonical(link["target"]))
    return result(
        "PASS", "All observed targets and bindings stay within admitted scope.", ["requested", "events"]
    )
