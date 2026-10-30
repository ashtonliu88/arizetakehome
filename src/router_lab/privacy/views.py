from __future__ import annotations

import json
import random
import re
from copy import deepcopy

from ..util import digest
from .contracts import REPRESENTATIONS, Episode


def replace_mentions(value, replacements: dict[str, str]):
    """Transform every admitted field, including JSON-encoded string fields.

    Longest-first, one-pass replacement avoids overlapping IDs and replacement
    cascades. JSON string normalization is a declared serialization omission.
    """
    alternatives = sorted(replacements, key=lambda s: (-len(s), s))
    pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(s) for s in alternatives) + r")(?![\w-])")

    def visit(item):
        if isinstance(item, dict):
            return {visit(k): visit(v) for k, v in item.items()}
        if isinstance(item, list):
            return [visit(v) for v in item]
        if not isinstance(item, str):
            return item
        try:
            decoded = json.loads(item)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, (dict, list)):
            changed = visit(decoded)
            if changed != decoded:
                return json.dumps(changed, ensure_ascii=False, sort_keys=True)
        return pattern.sub(lambda m: replacements[m.group()], item)

    return visit(value)


def admitted(e: Episode) -> dict:
    result = e.evidence.model_dump(mode="json")
    # Normalize typed argument objects to whole resource references in ALL views.
    # Deployment identities are composite keys; no component-token ablation here.
    for event in result["events"]:
        event["arguments"] = {"resource": event["target"]["key"]}
    return {"identity_semantics": "distinct", **result}


def make_view(episode: Episode, representation: str) -> dict:
    if representation not in REPRESENTATIONS:
        raise ValueError("unknown representation")
    bundle = admitted(episode)
    if representation == "raw":
        return bundle
    rng = random.Random(int(digest([episode.token_salt, representation]), 16))
    tokens, replacements = {}, {}
    admitted_aliases = {
        (a.name.kind, a.name.key): (a.target.kind, a.target.key) for a in episode.evidence.aliases
    }
    for entity in episode.entities:
        for mention in entity.mentions:
            # Private registry membership alone must not grant an alias equality.
            identity = (entity.resource.kind, mention)
            identity = admitted_aliases.get(identity, identity)
            if identity not in tokens:
                tokens[identity] = (
                    f"[{entity.resource.kind.upper()}]"
                    if representation == "blanket"
                    else f"REF_{rng.getrandbits(96):024x}"
                )
            if mention in replacements and replacements[mention] != tokens[identity]:
                raise ValueError("ambiguous typed entity mention")
            replacements[mention] = tokens[identity]
    # Unbound prose components cannot safely identify a composite deployment.
    # Collapse these components instead of inventing a service/environment-token
    # ablation. Complete composite mentions still match first and retain equality.
    for entity in episode.entities:
        if entity.resource.kind == "deployment":
            service, environment = entity.resource.key.split("/")
            replacements.setdefault(service, "[SERVICE_COMPONENT]")
            replacements.setdefault(environment, "[ENVIRONMENT_COMPONENT]")
    bundle = replace_mentions(bundle, replacements)
    if representation == "blanket":
        bundle["identity_semantics"] = "collapsed"
    if representation == "relation":
        # References come solely from admitted observations, not oracle.allowed.
        # Token equality is a trusted derived verification signal, not free inference.
        bundle = deepcopy(bundle)
        for field in ("request", "final_answer", "metadata"):
            bundle.pop(field)
        for event in bundle["events"]:
            event["result"] = {"found": event["result"]["found"], "error": event["result"]["error"]}
    return bundle


def validate_views(episodes: list[Episode]) -> dict:
    seen_tokens = set()
    collisions = 0
    by_base = {}
    for episode in episodes:
        original = episode.model_dump(mode="json")
        views = {r: make_view(episode, r) for r in REPRESENTATIONS}
        for representation in REPRESENTATIONS[1:]:
            serialized = json.dumps(views[representation])
            # Seeded composite identifiers and declared aliases are all known locally.
            for entity in episode.entities:
                for mention in entity.mentions:
                    if mention in serialized:
                        raise ValueError(f"identifier survived {representation}: {episode.episode_id}")
                if entity.resource.kind == "deployment":
                    if entity.resource.key.split("/")[0] in serialized:
                        raise ValueError("standalone deployment service survived")
        # Check injectivity/consistency on every structured admitted reference.
        raw = views["raw"]
        for representation in ("pseudonym", "relation"):
            view = views[representation]

            def references(bundle):
                return (
                    bundle["requested"]
                    + bundle["final_references"]
                    + [r for event in bundle["events"] for r in (event["target"], event["binding"]) if r]
                    + [link["target"] for event in bundle["events"] for link in event["links"]]
                    + [a[field] for a in bundle["aliases"] for field in ("name", "target")]
                    + [rule["source"] for rule in bundle["linked_scope"]]
                )

            original_refs, transformed = references(raw), references(view)
            admitted_aliases = {
                (a["name"]["kind"], a["name"]["key"]): (a["target"]["kind"], a["target"]["key"])
                for a in raw["aliases"]
            }
            assignments = {}
            for original_ref, transformed_ref in zip(original_refs, transformed, strict=True):
                identity = original_ref["kind"], original_ref["key"]
                identity = admitted_aliases.get(identity, identity)
                token = transformed_ref["key"]
                if identity in assignments and assignments[identity] != token:
                    raise ValueError("inconsistent within-trace pseudonym")
                assignments[identity] = token
            if len(set(assignments.values())) != len(assignments):
                raise ValueError("non-injective within-trace pseudonyms")
            # Every exported token is trace-local; alias equality is admitted explicitly.
            local_tokens = {r["key"] for r in transformed}
            if seen_tokens & local_tokens:
                raise ValueError("cross-trace token reuse")
            seen_tokens.update(local_tokens)
        if episode.model_dump(mode="json") != original:
            raise ValueError("transformation mutated canonical episode")
        by_base.setdefault(episode.base_id, []).append(views["blanket"])
    for pair in by_base.values():
        collisions += len(pair) == 2 and pair[0] == pair[1]
    if not collisions and all(e.answer_origin == "deterministic_template" for e in episodes):
        raise ValueError("corpus needs opposite-label byte-identical blanket views")
    return {
        "episodes": len(episodes),
        "views": len(episodes) * 4,
        "blanket_identical_pairs": collisions,
        "guarantee": "seeded-entity offline contract only; no general PII or live-export guarantee",
    }
