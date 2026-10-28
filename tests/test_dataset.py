import pytest
from pydantic import ValidationError

from router_lab.dataset import load_data, validate_data
from router_lab.models import BenchmarkExample


def test_dataset_contract_and_input_isolation():
    data = load_data()
    assert validate_data(data)["examples"] == 120
    assert len({e.request for e in data}) == 120
    assert len(load_data(split="dev")) == 40
    assert len(load_data(split="test")) == 80
    assert all(set(e.model_input()) == {"request"} for e in data)
    assert all(e.rationale not in str(e.model_input()) for e in data)


@pytest.mark.parametrize("defect", ["id", "request", "split", "paraphrase"])
def test_dataset_audit_rejects_defects(defect):
    data = load_data()
    if defect == "id":
        data[1] = data[1].model_copy(update={"example_id": data[0].example_id})
    elif defect == "request":
        data[1] = data[1].model_copy(update={"request": data[0].request.upper()})
    elif defect == "split":
        data[0] = data[0].model_copy(update={"split": "test"})
    else:
        data[5] = data[5].model_copy(update={"paraphrase_group": data[0].paraphrase_group})
    with pytest.raises(ValueError):
        validate_data(data)


def test_invalid_label():
    row = load_data()[0].model_dump()
    row["expected_action"] = "run_tests"
    with pytest.raises(ValidationError):
        BenchmarkExample.model_validate(row)
