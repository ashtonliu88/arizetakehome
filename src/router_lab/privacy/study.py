from __future__ import annotations

import importlib.metadata
import json
import os
import random
from pathlib import Path

from ..providers import response_text
from ..util import append_jsonl, digest, now, read_jsonl, write_json
from .baselines import check_evidence
from .contracts import ANSWER_PROMPT, JUDGE_PROMPT, REPETITIONS, REPRESENTATIONS, VERSION, Episode, Judgment
from .corpus import build_corpus, observed_answer_references
from .views import make_view, validate_views


def load_episodes(directory: Path) -> list[Episode]:
    path = directory / "episodes.jsonl"
    if not path.exists():
        raise ValueError("run privacy prepare first")
    episodes = [Episode.model_validate(row) for row in read_jsonl(path)]
    if len(episodes) != 72 or len({e.episode_id for e in episodes}) != 72:
        raise ValueError("expected 72 unique canonical episodes")
    return episodes


def save_episodes(directory: Path, episodes):
    path = directory / "episodes.jsonl"
    temporary = path.with_suffix(".jsonl.tmp")
    directory.mkdir(parents=True, exist_ok=True)
    temporary.write_text("".join(e.model_dump_json() + "\n" for e in episodes))
    temporary.replace(path)


def export_views(directory: Path, episodes):
    # Local lineage, gold and transformation names are separate from input.
    for representation in REPRESENTATIONS:
        rows = [
            {
                "episode_id": e.episode_id,
                "base_id": e.base_id,
                "split": e.split,
                "input": make_view(e, representation),
            }
            for e in episodes
        ]
        write_json(directory / "views" / f"{representation}.json", rows)
    # Generated scratch queue; real human records live only in reviews.jsonl.
    queue = directory / "review-queue.jsonl"
    temporary = queue.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(
            json.dumps(
                {
                    "episode_id": e.episode_id,
                    "episode_hash": digest(e.model_dump()),
                    "proposed_scope_pass": e.oracle.scope_pass,
                    "answerable": {r: r != "blanket" for r in REPRESENTATIONS},
                    "approved": False,
                    "reviewer": "",
                    "note": "",
                }
            )
            + "\n"
            for e in episodes
        )
    )
    temporary.replace(queue)


def prepare(directory: Path, seed: int):
    if (directory / "episodes.jsonl").exists():
        episodes = load_episodes(directory)
    else:
        episodes = build_corpus(seed)
        save_episodes(directory, episodes)
    checks = validate_views(episodes)
    export_views(directory, episodes)
    write_json(directory / "checks.json", checks)
    # Preserve a fixed synthetic information-limit witness outside measured rows.
    # Generated prose may later distinguish a pair even when its identity fields collapse.
    witness = directory / "information-limit-control.json"
    if not witness.exists():
        pair = build_corpus(seed)[:2]
        write_json(
            witness,
            {
                "measurement": "constructed template control; excluded from model metrics",
                "scope_truth": [e.oracle.scope_pass for e in pair],
                "raw": [make_view(e, "raw") for e in pair],
                "blanket": [make_view(e, "blanket") for e in pair],
            },
        )
    return {
        **checks,
        "directory": str(directory),
        "model_calls": 0,
        "status": "synthetic diagnostic corpus; human audit and measured model evidence pending",
    }


def context(settings) -> dict:
    from ..manifest import PACKAGES

    return {
        "version": VERSION,
        "settings": settings.model_dump(mode="json"),
        "repetitions": REPETITIONS,
        "judge_prompt": digest(JUDGE_PROMPT),
        "answer_prompt": digest(ANSWER_PROMPT),
        "source": digest({str(p): digest(p) for p in sorted(Path("src/router_lab").rglob("*.py"))}),
        "lock": digest(Path("uv.lock")),
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "endpoint": digest(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")),
    }


def selected(episodes, split: str, max_bases: int | None = None):
    candidates = [e for e in episodes if e.split == split]
    bases = list(dict.fromkeys(e.base_id for e in candidates))
    # Round-robin families/domains for representative small pilots.
    bases.sort(key=lambda b: (int(b.rsplit(".", 1)[1]), b))
    if max_bases is not None:
        if max_bases < 1:
            raise ValueError("max-bases must be positive")
        bases = bases[:max_bases]
    return [e for e in candidates if e.base_id in bases]


def schedule(episodes, split, configuration, judge, *, seed=1729, max_bases=None):
    tasks = []
    # Shuffle within each base block; interleave all four representations/repeats.
    for base in dict.fromkeys(e.base_id for e in selected(episodes, split, max_bases)):
        block = []
        for episode in (e for e in episodes if e.base_id == base):
            for representation in REPRESENTATIONS:
                view = make_view(episode, representation)
                for repetition in range(1, REPETITIONS + 1):
                    key = digest(
                        [
                            digest(episode.evidence.model_dump()),
                            digest(view),
                            configuration,
                            judge,
                            repetition,
                            episode.episode_id,
                        ]
                    )
                    block.append(
                        {
                            "key": key,
                            "episode_id": episode.episode_id,
                            "base_id": base,
                            "representation": representation,
                            "repetition": repetition,
                            "view_hash": digest(view),
                        }
                    )
        random.Random(digest([seed, base])).shuffle(block)
        tasks.extend(block)
    return [dict(task, order=i) for i, task in enumerate(tasks)]


def result_path(directory, split, judge):
    return directory / f"{split}-{judge}.jsonl"


def existing_results(path):
    result = {}
    for row in read_jsonl(path):
        if row["key"] in result:
            raise ValueError("duplicate scheduled judgment in checkpoint")
        result[row["key"]] = row
    return result


def generation_key(configuration, episode):
    return digest(
        [
            configuration,
            episode.evidence.model_dump(exclude={"final_answer", "final_references"}),
            ANSWER_PROMPT,
        ]
    )


def check_inflight(directory):
    path = directory / "inflight.json"
    if not path.exists():
        return
    pending = json.loads(path.read_text())
    if pending["operation"] == "judge":
        row = pending["row"]
        completed = row["key"] in existing_results(result_path(directory, row["split"], "model"))
    else:
        completed = any(
            e.episode_id == pending["episode_id"] and e.generation_key == pending["key"]
            for e in load_episodes(directory)
        )
    if completed:
        path.unlink()
        return
    raise ValueError(
        "unfinished paid call found; inspect calls and global budget, then use "
        "privacy resolve-interruption --reviewer NAME --note NOTE before continuing"
    )


def resolve_interruption(directory, reviewer, note):
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and interruption note are required")
    path = directory / "inflight.json"
    if not path.exists():
        raise ValueError("no interrupted call to resolve")
    pending = json.loads(path.read_text())
    if pending["operation"] == "judge":
        row = pending["row"]
        target = result_path(directory, row["split"], "model")
        if row["key"] not in existing_results(target):
            append_jsonl(
                target,
                {
                    **row,
                    "status": "interrupted",
                    "completed_at": now(),
                    "interruption_review": {"reviewer": reviewer, "note": note},
                },
            )
    else:
        episodes = load_episodes(directory)
        for episode in episodes:
            if episode.episode_id == pending["episode_id"] and episode.generation_key != pending["key"]:
                episode.generation_failure = {"key": pending["key"], "reviewer": reviewer, "note": note}
        save_episodes(directory, episodes)
    append_jsonl(
        directory / "interruption-reviews.jsonl",
        {**pending, "reviewer": reviewer, "note": note, "resolved_at": now()},
    )
    path.unlink()
    return {"resolved": pending["operation"], "retained_budget_charges": True}


def review(directory, episode_id, reviewer, note, answerable, approve):
    if (directory / "frozen.json").exists():
        raise ValueError("review is frozen; use a new study directory for changed labels")
    episode = next((e for e in load_episodes(directory) if e.episode_id == episode_id), None)
    if episode is None:
        raise ValueError("unknown episode ID")
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and substantive audit note are required")
    names = set(answerable.split(",")) if answerable else set()
    if not names <= set(REPRESENTATIONS):
        raise ValueError("answerable must list representation names separated by commas")
    record = {
        "episode_id": episode_id,
        "episode_hash": digest(episode.model_dump()),
        "approved": approve,
        "reviewer": reviewer,
        "note": note,
        "answerable": {r: r in names for r in REPRESENTATIONS},
        "timestamp": now(),
    }
    append_jsonl(directory / "reviews.jsonl", record)
    return record


def audited_reviews(directory, episodes, *, required=False):
    reviews = {r["episode_id"]: r for r in read_jsonl(directory / "reviews.jsonl")}
    valid = {}
    for episode in episodes:
        row = reviews.get(episode.episode_id, {})
        if (
            row.get("approved") is True
            and row.get("reviewer", "").strip()
            and row.get("note", "").strip()
            and row.get("episode_hash") == digest(episode.model_dump())
            and set(row.get("answerable", {})) == set(REPRESENTATIONS)
            and all(type(v) is bool for v in row["answerable"].values())
        ):
            valid[episode.episode_id] = row
    if required and len(valid) != len(episodes):
        raise ValueError(
            f"{len(episodes) - len(valid)} canonical labels/views need current human review; "
            "use privacy review, or manually audit and append records to reviews.jsonl"
        )
    return valid


def freeze(directory, settings):
    check_inflight(directory)
    if any(read_jsonl(result_path(directory, "test", judge)) for judge in ("model", "evidence", "exact")):
        raise ValueError("held-out judgments already exist; cannot retune/refreeze this study")
    episodes = load_episodes(directory)
    validate_views(episodes)
    configuration = context(settings)
    if any(
        e.answer_origin != "model" or e.generation_key != generation_key(configuration, e) for e in episodes
    ):
        raise ValueError(
            "freeze requires all 72 captured model answers; run privacy generate for both splits"
        )
    audited_reviews(directory, episodes, required=True)
    results = existing_results(result_path(directory, "dev", "model"))
    expected = schedule(episodes, "dev", configuration, "model", seed=settings.seed)
    if any(task["key"] not in results for task in expected):
        raise ValueError("complete all 192 current development model judgments before freezing")
    manifest = {
        "context": configuration,
        "episodes_hash": digest(directory / "episodes.jsonl"),
        "reviews_hash": digest(directory / "reviews.jsonl"),
        "development_hash": digest(result_path(directory, "dev", "model")),
        "timestamp": now(),
        "held_out_base_clusters": 24,
        "design": "controlled diagnostic; nine whole families; 4 views x 2 repeats",
    }
    write_json(directory / "frozen.json", manifest)
    return manifest


def verify_frozen(directory, settings):
    path = directory / "frozen.json"
    if not path.exists():
        raise ValueError("held-out work requires privacy freeze and --frozen")
    frozen = json.loads(path.read_text())
    current = {
        "context": context(settings),
        "episodes_hash": digest(directory / "episodes.jsonl"),
        "reviews_hash": digest(directory / "reviews.jsonl"),
        "development_hash": digest(result_path(directory, "dev", "model")),
    }
    for key, value in current.items():
        if frozen[key] != value:
            raise ValueError(
                f"privacy freeze changed: {key}; preserve held-out evidence and start a new study"
            )
    return frozen


def generate(directory, settings, split, provider, *, max_bases=None, retry_failed=False):
    check_inflight(directory)
    if (directory / "frozen.json").exists():
        raise ValueError("answers are frozen; do not change canonical executions")
    episodes = load_episodes(directory)
    configuration = context(settings)
    pending = []
    for episode in selected(episodes, split, max_bases):
        source = episode.evidence.model_dump(exclude={"final_answer", "final_references"})
        key = generation_key(configuration, episode)
        if episode.generation_failure and episode.generation_failure["key"] == key and not retry_failed:
            raise ValueError("interrupted answer requires explicit --retry-failed to authorize another call")
        if episode.answer_origin != "model" or episode.generation_key != key:
            pending.append((episode, source, key))
    projection = sum(
        provider.estimate_call(
            "answer", json.dumps(source) + ANSWER_PROMPT, [], settings.answer_max_output_tokens
        )
        for _, source, _ in pending
    )
    provider.budget.check(projection)
    for episode, source, key in pending:
        write_json(
            directory / "inflight.json",
            {"operation": "answer", "episode_id": episode.episode_id, "key": key, "started_at": now()},
        )
        calls = provider.generate("answer", json.dumps(source), instructions=ANSWER_PROMPT)
        if not calls or calls[-1].error:
            raise RuntimeError(
                "answer generation failed; inspect calls/answers.jsonl and shared budget ledger"
            )
        episode.evidence.final_answer = response_text(calls[-1].raw)
        episode.evidence.final_references = observed_answer_references(
            episode.evidence.final_answer, episode.entities
        )
        episode.answer_origin = "model"
        episode.generation_key = key
        episode.answer_calls = [c.model_dump(mode="json") for c in calls]
        episode.generation_failure = None
        save_episodes(directory, episodes)  # Persist every completed answer before the next call.
        (directory / "inflight.json").unlink()
    export_views(directory, episodes)
    return {
        "generated": len(pending),
        "model_answers": sum(e.answer_origin == "model" for e in episodes),
        "projected_remaining_usd": projection,
        "shared_spent_usd": provider.budget.spent,
    }


def validate_judgment(value: str, view: dict) -> Judgment:
    judgment = Judgment.model_validate_json(value)
    for reference in judgment.evidence_refs:
        # References must resolve in the admitted evidence, rather than point to gold.
        import re

        if not re.fullmatch(r"[a-z_]+(?:\[\d+\])?(?:\.[a-z_]+(?:\[\d+\])?)*", reference):
            raise ValueError("invalid evidence reference syntax")
        current = view
        for part in reference.split("."):
            match = re.fullmatch(r"([a-z_]+)(?:\[(\d+)\])?", part)
            current = current[match[1]]
            if match[2] is not None:
                current = current[int(match[2])]
    return judgment


def replay(directory, settings, split, judge, *, provider=None, max_bases=None, frozen=False):
    check_inflight(directory)
    if split == "test":
        if not frozen:
            raise ValueError("held-out work requires --frozen")
        verify_frozen(directory, settings)
    elif (directory / "frozen.json").exists() and judge == "model":
        raise ValueError("development model results are frozen")
    episodes = load_episodes(directory)
    validate_views(episodes)
    by_id = {e.episode_id: e for e in episodes}
    configuration = context(settings)
    tasks = schedule(episodes, split, configuration, judge, seed=settings.seed, max_bases=max_bases)
    path = result_path(directory, split, judge)
    completed = existing_results(path)
    pending = [task for task in tasks if task["key"] not in completed]
    projection = 0
    if judge == "model":
        projection = sum(
            provider.estimate_call(
                "judge",
                json.dumps(make_view(by_id[t["episode_id"]], t["representation"])) + JUDGE_PROMPT,
                [],
                settings.answer_max_output_tokens,
            )
            for t in pending
        )
        provider.budget.check(projection)
    write_json(directory / f"{split}-{judge}-schedule.json", tasks)
    for task in pending:
        episode = by_id[task["episode_id"]]
        view = make_view(episode, task["representation"])
        row = {
            **task,
            "timestamp": now(),
            "split": split,
            "judge": judge,
            "context_hash": digest(configuration),
            "status": "ok",
            "judgment": None,
            "calls": [],
            "measurement": "model_replay" if judge == "model" else "code_baseline",
        }
        if judge == "model":
            # Each request is a fresh Responses call. No canonical IDs or oracle enter it.
            provider.call_log = directory / "calls" / f"{task['representation']}.jsonl"
            write_json(directory / "inflight.json", {"operation": "judge", "row": row})
            calls = provider.generate(
                "judge",
                json.dumps(view, ensure_ascii=False),
                instructions=JUDGE_PROMPT,
                schema=Judgment.model_json_schema(),
            )
            row["calls"] = [c.model_dump(mode="json") for c in calls]
            if not calls or calls[-1].error:
                row["status"] = "provider_error"
            else:
                try:
                    row["judgment"] = validate_judgment(response_text(calls[-1].raw), view).model_dump()
                except (ValueError, KeyError, TypeError, IndexError):
                    row["status"] = "invalid_output"
        else:
            row["judgment"] = check_evidence(view, exact=judge == "exact").model_dump()
        row["completed_at"] = now()
        # Preserve first terminal result, including operational failures. Planned repeats
        # have separate keys; they must never hit each other's cache.
        append_jsonl(path, row)
        if judge == "model":
            (directory / "inflight.json").unlink()
    return {
        "scheduled": len(tasks),
        "new_judgments": len(pending),
        "resumed": len(tasks) - len(pending),
        "projected_remaining_usd": projection,
        "measurement": "model_replay" if judge == "model" else "code_baseline",
    }
