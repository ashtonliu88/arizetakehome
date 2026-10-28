from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .util import append_jsonl, now, read_jsonl


class BudgetExceeded(RuntimeError):
    pass


@contextmanager
def run_lock(path: Path = Path("results/.run.lock")):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another paid command is running") from exc
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class Budget:
    """Durable reservations include interrupted and usage-unknown requests."""

    def __init__(self, path: Path, limit: float = 50, reserve: float = 5):
        self.path, self.limit, self.reserve = path, limit, reserve

    @property
    def spent(self) -> float:
        charges = {}
        for row in read_jsonl(self.path):
            charges[row["id"]] = row["amount"]
        return sum(charges.values())

    def check(self, estimate: float, *, headroom=True):
        ceiling = self.limit - (self.reserve if headroom else 0)
        if self.spent + estimate > ceiling:
            raise BudgetExceeded(
                f"budget: ${self.spent:.4f} committed; ${estimate:.4f} projected; ceiling ${ceiling:.2f}"
            )

    def reserve_call(self, estimate: float, kind: str, *, headroom=True) -> str:
        self.check(estimate, headroom=headroom)
        reservation = uuid4().hex
        append_jsonl(
            self.path,
            {"id": reservation, "amount": estimate, "state": "reserved", "kind": kind, "timestamp": now()},
        )
        return reservation

    def settle(self, reservation: str, amount: float, estimated=False):
        append_jsonl(
            self.path,
            {
                "id": reservation,
                "amount": amount,
                "state": "estimated" if estimated else "measured",
                "timestamp": now(),
            },
        )
