from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from router_lab.budget import Budget, BudgetExceeded
from router_lab.models import CallRecord
from router_lab.privacy import study
from router_lab.privacy.analysis import analyze, metrics, paired_intervals
from router_lab.privacy.baselines import check_evidence
from router_lab.privacy.contracts import REPRESENTATIONS
from router_lab.privacy.corpus import build_corpus
from router_lab.privacy.views import make_view, replace_mentions, validate_views


class MockProvider:
    """No network; retain the real durable budget behavior."""

    def __init__(self, directory):
        self.budget = Budget(directory / "ledger.jsonl")
        self.requests = []
        self.invalid = False
        self.call_log = directory / "calls.jsonl"

    def estimate_call(self, *args):
        return 0.001

    def generate(self, kind, request, *, instructions, schema=None):
        reservation = self.budget.reserve_call(0.001, kind)
        self.requests.append((kind, json.loads(request), instructions, schema))
        if kind == "answer":
            text = "Observed " + json.loads(request)["events"][-1]["target"]["key"]
        elif self.invalid:
            text = json.dumps({"verdict": "APPROVED"})
        else:
            text = check_evidence(json.loads(request)).model_dump_json()
        self.budget.settle(reservation, 0.001)
        return [
            CallRecord(
                kind=kind,
                cost_usd=0.001,
                raw={"status": "completed", "output": [{"content": [{"type": "output_text", "text": text}]}]},
            )
        ]


@pytest.fixture
def corpus():
    return build_corpus()


def test_corpus_design_and_independent_oracle(corpus):
    from router_lab.privacy.corpus import arguments

    assert len(corpus) == 72
    assert Counter(e.split for e in corpus) == {"dev": 24, "test": 48}
    assert Counter(e.oracle.scope_pass for e in corpus) == {True: 36, False: 36}
    assert len({e.family for e in corpus}) == 9
    assert not {e.family for e in corpus if e.split == "dev"} & {
        e.family for e in corpus if e.split == "test"
    }
    for episode in corpus:
        assert all(event.arguments == arguments(event.target) for event in episode.evidence.events)
        for representation in ("raw", "pseudonym", "relation"):
            observed = check_evidence(make_view(episode, representation))
            assert (observed.verdict == "PASS") == episode.oracle.scope_pass
        assert check_evidence(make_view(episode, "blanket")).verdict == "INSUFFICIENT_EVIDENCE"
    assert any(not e.evidence.events[0].result["found"] and e.oracle.scope_pass for e in corpus)


def test_transform_is_blind_recursive_consistent_and_trace_local(corpus):
    checks = validate_views(corpus)
    assert checks["blanket_identical_pairs"] == 29
    episode = corpus[0].model_copy(deep=True)
    original = episode.model_dump()
    for representation in REPRESENTATIONS:
        first = make_view(episode, representation)
        episode.oracle.scope_pass = not episode.oracle.scope_pass
        episode.oracle.allowed = []
        assert make_view(episode, representation) == first
        assert (
            not {"oracle", "entities", "token_salt", "intervention", "representation", "family"}
            & first.keys()
        )
    assert corpus[0].model_dump() == original
    for representation in ("pseudonym", "relation"):
        first = make_view(corpus[0], representation)
        second = make_view(corpus[1], representation)
        assert first["requested"][0]["key"] != second["requested"][0]["key"]
        assert first["requested"][0]["key"] == first["events"][0]["binding"]["key"]


def test_overlapping_mentions_boundaries_and_escaped_json():
    value = {
        "ENG-10": ["ENG-100 and ENG-10 again ENG-10", "prefixENG-10 ENG-1000 ENG-10-suffix"],
        "nested": '{"resource": "service-x\\/production", "ok": true}',
        "unicode": '{"id":"ENG\\u002d10"}',
    }
    result = replace_mentions(value, {"ENG-10": "REF_A", "ENG-100": "REF_B", "service-x/production": "REF_C"})
    assert result["REF_A"][0] == "REF_B and REF_A again REF_A"
    assert result["REF_A"][1] == "prefixENG-10 ENG-1000 ENG-10-suffix"
    assert json.loads(result["nested"])["resource"] == "REF_C"
    assert json.loads(result["unicode"])["id"] == "REF_A"


def test_metadata_errors_final_answer_and_composite_arguments_are_sanitized(corpus):
    episode = next(e for e in corpus if e.domain == "deployment")
    key = episode.evidence.requested[0].key
    episode.evidence.metadata["error"] = f"lookup failed for {key}"
    episode.evidence.final_answer = f"I observed {key}."
    for representation in REPRESENTATIONS[1:]:
        view = make_view(episode, representation)
        assert key not in json.dumps(view)
        assert key.split("/")[0] not in json.dumps(view)
        assert "service" not in view["events"][0]["arguments"]


def test_schedule_repeats_and_clustered_holdout(corpus, settings):
    configuration = study.context(settings)
    tasks = study.schedule(corpus, "dev", configuration, "model")
    assert len(tasks) == len({t["key"] for t in tasks}) == 192
    assert len(study.schedule(corpus, "test", configuration, "model")) == 384
    assert len(study.schedule(corpus, "dev", configuration, "model", max_bases=3)) == 48
    assert tasks == study.schedule(corpus, "dev", configuration, "model")
    for offset in range(0, len(tasks), 16):
        assert len({t["base_id"] for t in tasks[offset : offset + 16]}) == 1
        assert {t["representation"] for t in tasks[offset : offset + 16]} == set(REPRESENTATIONS)


def test_replay_blinding_resume_and_planned_repeats(tmp_path, settings):
    study.prepare(tmp_path, settings.seed)
    provider = MockProvider(tmp_path)
    first = study.replay(tmp_path, settings, "dev", "model", provider=provider, max_bases=1)
    assert first["new_judgments"] == 16
    assert len(provider.requests) == 16
    assert provider.budget.spent == pytest.approx(0.016)
    for kind, view, instructions, schema in provider.requests:
        assert kind == "judge" and schema
        assert "oracle" not in view and "representation" not in view and "episode_id" not in view
        assert "INSUFFICIENT_EVIDENCE" in instructions
    resumed = study.replay(tmp_path, settings, "dev", "model", provider=provider, max_bases=1)
    assert resumed["new_judgments"] == 0
    assert len(provider.requests) == 16
    assert provider.budget.spent == pytest.approx(0.016)


def test_operational_errors_are_terminal_and_missing_work_stays_in_denominator(tmp_path, settings):
    study.prepare(tmp_path, settings.seed)
    provider = MockProvider(tmp_path)
    provider.invalid = True
    study.replay(tmp_path, settings, "dev", "model", provider=provider, max_bases=1)
    rows = list(study.existing_results(study.result_path(tmp_path, "dev", "model")).values())
    assert all(r["status"] == "invalid_output" and r["judgment"] is None for r in rows)
    report = analyze(tmp_path, settings, "dev", "model")
    assert report["scheduled_judgments"] == 192 and report["current_completed"] == 16
    assert report["by_representation"]["raw"]["operational_failure"]["numerator"] == 48
    assert report["by_representation"]["raw"]["coverage"]["rate"] == 0
    assert report["by_representation"]["raw"]["unsupported_approval"]["denominator"] == 0


def test_metric_denominators_and_zero_event_uncertainty():
    rows = []
    for base in range(4):
        for representation in ("blanket", "pseudonym"):
            for good in (False, True):
                for _ in range(2):
                    rows.append(
                        {
                            "base_id": str(base),
                            "representation": representation,
                            "scope_pass": good,
                            "answerable": representation == "pseudonym",
                            "verdict": ("PASS" if good else "FAIL")
                            if representation == "pseudonym"
                            else "INSUFFICIENT_EVIDENCE",
                            "status": "ok",
                        }
                    )
    values = metrics(rows)
    assert values["false_approval"] == {"numerator": 0, "denominator": 16, "rate": 0}
    assert values["coverage"]["rate"] == 0.5
    assert values["decided_accuracy"]["rate"] == 1
    paired = paired_intervals(rows, 1729, draws=100)
    interval = paired["contrasts"]["false_approval"]["interval_95"]
    assert interval[0] < 0 < interval[1]
    assert paired["base_clusters"] == 4


def test_evidence_reference_validation(corpus):
    view = make_view(corpus[0], "raw")
    output = check_evidence(view).model_dump()
    study.validate_judgment(json.dumps(output), view)
    output["evidence_refs"] = ["oracle.scope_pass"]
    with pytest.raises(KeyError):
        study.validate_judgment(json.dumps(output), view)


def test_freeze_requires_real_answers_current_audits_and_development(tmp_path, settings):
    study.prepare(tmp_path, settings.seed)
    with pytest.raises(ValueError, match="72 captured model answers"):
        study.freeze(tmp_path, settings)
    provider = MockProvider(tmp_path)
    for split in ("dev", "test"):
        study.generate(tmp_path, settings, split, provider)
    assert study.generate(tmp_path, settings, "test", provider)["generated"] == 0
    with pytest.raises(ValueError, match="human review"):
        study.freeze(tmp_path, settings)
    for episode in study.load_episodes(tmp_path):
        # Test-only audit fixtures, never generated by the application.
        study.review(
            tmp_path,
            episode.episode_id,
            "test fixture reviewer",
            "test-only approved fixture",
            "raw,pseudonym,relation",
            True,
        )
    with pytest.raises(ValueError, match="192 current development"):
        study.freeze(tmp_path, settings)
    study.replay(tmp_path, settings, "dev", "model", provider=provider)
    manifest = study.freeze(tmp_path, settings)
    assert study.verify_frozen(tmp_path, settings) == manifest
    study.replay(tmp_path, settings, "test", "evidence", frozen=True)
    with pytest.raises(ValueError, match="held-out judgments already exist"):
        study.freeze(tmp_path, settings)
    with pytest.raises(ValueError, match="frozen"):
        study.review(tmp_path, study.load_episodes(tmp_path)[0].episode_id, "x", "x", "raw", True)
    with (tmp_path / "reviews.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="reviews_hash"):
        study.verify_frozen(tmp_path, settings)


def test_test_guard_and_budget_preflight_make_no_calls(tmp_path, settings):
    study.prepare(tmp_path, settings.seed)
    provider = MockProvider(tmp_path)
    with pytest.raises(ValueError, match="--frozen"):
        study.replay(tmp_path, settings, "test", "model", provider=provider)
    with pytest.raises(ValueError, match="privacy freeze"):
        study.replay(tmp_path, settings, "test", "model", provider=provider, frozen=True)
    provider.budget = Budget(tmp_path / "small-ledger.jsonl", limit=0.001, reserve=0)
    with pytest.raises(BudgetExceeded):
        study.replay(tmp_path, settings, "dev", "model", provider=provider)
    assert provider.requests == []
    assert not Path(study.result_path(tmp_path, "dev", "model")).exists()


def test_private_alias_registry_cannot_add_evidence(corpus):
    episode = next(e.model_copy(deep=True) for e in corpus if e.evidence.aliases)
    episode.evidence.aliases = []
    view = make_view(episode, "pseudonym")
    assert view["requested"][0]["key"] != view["events"][0]["binding"]["key"]


def test_generated_prose_may_remove_byte_collisions_without_breaking_transform(corpus):
    for index, episode in enumerate(corpus):
        episode.answer_origin = "model"
        episode.evidence.final_answer = f"Distinct generated wording {index}."
    assert validate_views(corpus)["blanket_identical_pairs"] == 0


def test_uncertain_paid_judgment_is_not_automatically_bought_again(tmp_path, settings):
    study.prepare(tmp_path, settings.seed)

    class Interrupted(MockProvider):
        def generate(self, *args, **kwargs):
            super().generate(*args, **kwargs)
            raise KeyboardInterrupt

    provider = Interrupted(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        study.replay(tmp_path, settings, "dev", "model", provider=provider, max_bases=1)
    assert provider.budget.spent == pytest.approx(0.001)
    with pytest.raises(ValueError, match="unfinished paid call"):
        study.replay(tmp_path, settings, "dev", "model", provider=provider, max_bases=1)
    study.resolve_interruption(tmp_path, "test reviewer", "test-only uncertain call fixture")
    rows = study.existing_results(study.result_path(tmp_path, "dev", "model"))
    assert len(rows) == 1 and next(iter(rows.values()))["status"] == "interrupted"
    resumed = MockProvider(tmp_path)
    result = study.replay(tmp_path, settings, "dev", "model", provider=resumed, max_bases=1)
    assert result["new_judgments"] == 15 and result["resumed"] == 1
    assert resumed.budget.spent == pytest.approx(0.016)
