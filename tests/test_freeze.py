import pytest

from router_lab.manifest import current_manifest, save_manifest, verify_frozen
from router_lab.util import digest


def test_frozen_evidence_and_all_configuration_hashes(tmp_path, monkeypatch, settings):
    current = current_manifest(settings)
    frozen = current.model_copy(deep=True)
    frozen.threshold = 0.7
    review = tmp_path / "data/review.jsonl"
    review.parent.mkdir()
    review.write_text('{"test_only":true}\n')
    frozen.review_hash = digest(review)
    dev = tmp_path / "dev.jsonl"
    dev.write_text('{"test_only":"development evidence"}\n')
    frozen.development_results_hash = digest(dev)
    path = tmp_path / "frozen.json"
    save_manifest(path, frozen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("router_lab.manifest.current_manifest", lambda settings: current)
    assert verify_frozen(settings, path).threshold == 0.7
    for field in [
        "dataset_hash",
        "catalog_hash",
        "prompt_hash",
        "evaluator_hash",
        "source_hash",
        "lock_hash",
        "endpoint_hash",
    ]:
        old = getattr(current, field)
        setattr(current, field, "changed")
        with pytest.raises(ValueError, match=field):
            verify_frozen(settings, path)
        setattr(current, field, old)
    current.configuration = {"changed": True}
    with pytest.raises(ValueError, match="configuration"):
        verify_frozen(settings, path)
    current.configuration = frozen.configuration
    current.package_versions = {"changed": "version"}
    with pytest.raises(ValueError, match="package_versions"):
        verify_frozen(settings, path)
    current.package_versions = frozen.package_versions
    review.write_text("changed review")
    with pytest.raises(ValueError, match="human label review"):
        verify_frozen(settings, path)
    review.write_text('{"test_only":true}\n')
    dev.write_text("changed evidence")
    with pytest.raises(ValueError, match="development evidence"):
        verify_frozen(settings, path)
