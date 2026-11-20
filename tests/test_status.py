from __future__ import annotations

from pulsecheck.models import ProbeResult, Target, TargetState
from pulsecheck.status import Status, all_up, classify, stale_after_ms


def _http(name: str = "web", interval_ms: int = 1000) -> Target:
    return Target(name, "http", interval_ms, 800, url="http://127.0.0.1/ok")


def test_never_probed_is_stale() -> None:
    state = TargetState(_http())
    assert classify(state, now=10.0) is Status.STALE


def test_recent_success_is_up() -> None:
    state = TargetState(_http(interval_ms=1000))
    state.apply(ProbeResult(True, 12.0, None, at=10.0, status_code=200))
    assert classify(state, now=10.5) is Status.UP


def test_recent_failure_is_down() -> None:
    state = TargetState(_http(interval_ms=1000))
    state.apply(ProbeResult(False, 801.0, "timeout", at=10.0))
    assert classify(state, now=10.2) is Status.DOWN


def test_old_result_is_stale_even_if_ok() -> None:
    state = TargetState(_http(interval_ms=1000))
    state.apply(ProbeResult(True, 9.0, None, at=1.0, status_code=200))
    assert stale_after_ms(1000) == 2000
    assert classify(state, now=4.0) is Status.STALE


def test_old_failure_is_stale() -> None:
    state = TargetState(_http(interval_ms=1000))
    state.apply(ProbeResult(False, 4.0, "connection refused", at=1.0))
    assert classify(state, now=5.0) is Status.STALE


def test_streak_flips_on_status_change() -> None:
    state = TargetState(_http())
    state.apply(ProbeResult(True, 1.0, None, at=1.0))
    state.apply(ProbeResult(True, 1.0, None, at=2.0))
    assert state.streak == 2
    state.apply(ProbeResult(False, 1.0, "timeout", at=3.0))
    assert state.streak == -1
    state.apply(ProbeResult(False, 1.0, "timeout", at=4.0))
    assert state.streak == -2
    assert state.streak_label() == "-2"


def test_all_up_requires_every_target() -> None:
    ok = TargetState(_http("a"))
    ok.apply(ProbeResult(True, 1.0, None, at=10.0))
    bad = TargetState(_http("b"))
    bad.apply(ProbeResult(False, 1.0, "status 500", at=10.0))
    assert all_up([ok], now=10.1) is True
    assert all_up([ok, bad], now=10.1) is False
