from __future__ import annotations

from ..phoenix_io import phoenix_client
from ..util import digest, write_json
from .contracts import REPRESENTATIONS
from .study import (
    audited_reviews,
    context,
    existing_results,
    load_episodes,
    result_path,
    schedule,
    verify_frozen,
)
from .views import make_view


def publish(directory, settings, split, judge, *, client=None):
    """Publish saved replay evidence, never canonical bundles or hidden maps.

    Each representation gets its own dataset and experiment. Phoenix reference
    labels belong to evaluator-only output; the model already ran on input only.
    """
    if split == "test":
        verify_frozen(directory, settings)
    client = client or phoenix_client()
    episodes = load_episodes(directory)
    by_id = {e.episode_id: e for e in episodes}
    reviews = audited_reviews(directory, episodes)
    configuration = context(settings)
    tasks = schedule(episodes, split, configuration, judge, seed=settings.seed)
    results = existing_results(result_path(directory, split, judge))
    if any(t["key"] not in results for t in tasks):
        raise ValueError("complete the scheduled split before publishing")
    published = []
    for representation in REPRESENTATIONS:
        subset = [t for t in tasks if t["representation"] == representation]
        examples = []
        for task in subset:
            episode = by_id[task["episode_id"]]
            examples.append(
                {
                    "input": make_view(episode, representation),
                    "output": {
                        "scope_pass": episode.oracle.scope_pass,
                        "answerable": reviews.get(episode.episode_id, {})
                        .get("answerable", {})
                        .get(representation),
                    },
                    "metadata": {
                        "replay_key": task["key"],
                        "source_episode_id": episode.episode_id,
                        "base_id": episode.base_id,
                        "repetition": task["repetition"],
                        "human_audited": episode.episode_id in reviews,
                    },
                    "splits": [split],
                }
            )
        name = f"privacy-{split}-{judge}-{representation}-{digest(examples)[:16]}"
        try:
            dataset = client.datasets.get_dataset(dataset=name)
        except Exception as exc:
            if (
                not (isinstance(exc, ValueError) and str(exc).startswith("Dataset not found:"))
                and getattr(getattr(exc, "response", None), "status_code", None) != 404
            ):
                raise
            dataset = client.datasets.create_dataset(
                name=name, examples=examples, dataset_description="Controlled synthetic offline replay"
            )
        local = {e["metadata"]["replay_key"]: e for e in examples}
        if len(dataset.examples) != len(local) or any(
            row["metadata"].get("replay_key") not in local
            or any(
                row[field] != local[row["metadata"]["replay_key"]][field]
                for field in ("input", "output", "metadata")
            )
            for row in dataset.examples
        ):
            raise ValueError("persisted Phoenix privacy dataset differs")

        def task(input, metadata):
            saved = results[metadata["replay_key"]]
            episode = by_id[saved["episode_id"]]
            if digest(input) != saved["view_hash"]:
                raise ValueError("published input differs from actual replay input")
            if input != make_view(episode, saved["representation"]):
                raise ValueError("published representation differs")
            return {"status": saved["status"], "judgment": saved["judgment"]}

        def coverage(output):
            return output["status"] == "ok" and (output["judgment"] or {}).get("verdict") in ("PASS", "FAIL")

        def false_approval(output, expected):
            return not expected["scope_pass"] and (output["judgment"] or {}).get("verdict") == "PASS"

        evaluators = {"scope_judgment_coverage": coverage, "scope_false_approval_event": false_approval}
        # Both creation and resume replay local terminal records, so neither can
        # invoke a model or multiply the study's two planned judge repetitions.
        existing = [e for e in client.experiments.list(dataset_id=dataset.id) if e["name"] == name]
        if existing:
            experiment_id = existing[-1]["id"]
            client.experiments.resume_experiment(
                experiment_id=experiment_id,
                task=task,
                evaluators=evaluators,
                retries=0,
                timeout=None,
                print_summary=False,
            )
            client.experiments.resume_evaluation(
                experiment_id=experiment_id,
                evaluators=evaluators,
                retries=0,
                timeout=None,
                print_summary=False,
            )
        else:
            experiment = client.experiments.run_experiment(
                dataset=dataset,
                task=task,
                evaluators=evaluators,
                experiment_name=name,
                repetitions=1,
                retries=0,
                timeout=None,
                experiment_metadata={
                    "measurement": "saved_model_replay" if judge == "model" else "code_baseline",
                    "representation": representation,
                    "split": split,
                    "cohort": "controlled_diagnostic",
                    "paid_calls": 0,
                },
            )
            experiment_id = experiment["experiment_id"]
        published.append(
            {"representation": representation, "dataset_id": dataset.id, "experiment_id": experiment_id}
        )
    write_json(directory / f"{split}-{judge}-phoenix.json", published)
    return {"published": published, "new_model_calls": 0}
