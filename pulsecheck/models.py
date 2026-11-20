from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["http", "tcp"]


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    kind: Kind
    interval_ms: int
    timeout_ms: int
    url: str | None = None
    host: str | None = None
    port: int | None = None
    expect_status: int | None = None
    retries: int = 0
    backoff_ms: int = 200

    def endpoint(self) -> str:
        if self.kind == "http":
            return self.url or ""
        return f"{self.host}:{self.port}"


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    latency_ms: float
    error: str | None
    at: float
    status_code: int | None = None


@dataclass(slots=True)
class TargetState:
    target: Target
    last: ProbeResult | None = None
    streak: int = 0

    def apply(self, result: ProbeResult) -> None:
        if result.ok:
            self.streak = self.streak + 1 if self.streak > 0 else 1
        else:
            self.streak = self.streak - 1 if self.streak < 0 else -1
        self.last = result

    def streak_label(self) -> str:
        if self.streak == 0:
            return "0"
        return f"+{self.streak}" if self.streak > 0 else str(self.streak)
