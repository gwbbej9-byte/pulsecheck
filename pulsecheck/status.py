from __future__ import annotations

import time
from enum import StrEnum

from pulsecheck.models import TargetState


class Status(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    STALE = "STALE"


def stale_after_ms(interval_ms: int) -> int:
    return max(interval_ms * 2, 1000)


def classify(state: TargetState, now: float | None = None) -> Status:
    """UP if last probe succeeded and is fresh; DOWN if it failed and is fresh; STALE otherwise."""
    clock = time.monotonic() if now is None else now
    if state.last is None:
        return Status.STALE
    age_ms = (clock - state.last.at) * 1000.0
    if age_ms > stale_after_ms(state.target.interval_ms):
        return Status.STALE
    return Status.UP if state.last.ok else Status.DOWN


def all_up(states: list[TargetState], now: float | None = None) -> bool:
    return all(classify(state, now) is Status.UP for state in states)


def status_style(status: Status) -> str:
    if status is Status.UP:
        return "bold green"
    if status is Status.DOWN:
        return "bold red"
    return "bold yellow"
