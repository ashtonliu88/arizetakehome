from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .models import ACTIONS, BenchmarkExample
from .util import read_jsonl

DATA_PATH = Path("data/benchmark.jsonl")


def load_data(path: Path = DATA_PATH, split: str | None = None) -> list[BenchmarkExample]:
    examples = [BenchmarkExample.model_validate(row) for row in read_jsonl(path)]
    return [e for e in examples if split is None or e.split == split]


def validate_data(examples: list[BenchmarkExample]) -> dict:
    if len(examples) != 120:
        raise ValueError("benchmark must contain exactly 120 examples")
    ids = [e.example_id for e in examples]
    requests = [re.sub(r"\W+", " ", e.request.lower()).strip() for e in examples]
    if len(set(ids)) != 120 or len(set(requests)) != 120:
        raise ValueError("duplicate example ID or normalized request")
    counts = Counter((e.split, e.expected_action) for e in examples)
    for action in ACTIONS:
        if counts["dev", action] != 5 or counts["test", action] != 10:
            raise ValueError(f"incorrect split count for {action}")
    groups = defaultdict(set)
    for e in examples:
        groups[e.paraphrase_group].add(e.split)
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("paraphrase leakage across splits")
    return {
        "examples": 120,
        "dev": 40,
        "test": 80,
        "actions": dict(Counter(e.expected_action for e in examples)),
        "label_review": "pending human review; see data/review.jsonl",
    }
