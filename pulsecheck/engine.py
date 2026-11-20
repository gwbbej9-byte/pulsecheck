from __future__ import annotations

import asyncio
import time

import httpx

from pulsecheck.models import ProbeResult, Target, TargetState
from pulsecheck.probe import clip_error, probe


class Engine:
    def __init__(self, targets: list[Target]) -> None:
        self.targets = targets
        self.states = [TargetState(target) for target in targets]
        self._stop = asyncio.Event()
        self._kick = {target.name: asyncio.Event() for target in targets}
        self._client: httpx.AsyncClient | None = None

    def _client_timeout(self) -> httpx.Timeout:
        max_ms = max((target.timeout_ms for target in self.targets), default=3000)
        seconds = max_ms / 1000.0
        return httpx.Timeout(seconds, connect=seconds)

    async def run(self) -> None:
        async with httpx.AsyncClient(follow_redirects=True, timeout=self._client_timeout()) as client:
            self._client = client
            workers = [asyncio.create_task(self._watch(state), name=f"probe:{state.target.name}") for state in self.states]
            try:
                await self._stop.wait()
            finally:
                for worker in workers:
                    worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                self._client = None

    async def run_once(self) -> list[TargetState]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=self._client_timeout()) as client:
            raw = await asyncio.gather(
                *[probe(state.target, client) for state in self.states],
                return_exceptions=True,
            )
        for state, item in zip(self.states, raw, strict=True):
            if isinstance(item, asyncio.CancelledError):
                raise item
            if isinstance(item, BaseException):
                state.apply(
                    ProbeResult(
                        False,
                        0.0,
                        clip_error(str(item) or type(item).__name__),
                        time.monotonic(),
                        None,
                    )
                )
            else:
                state.apply(item)
        return self.states

    def refresh(self) -> None:
        for event in self._kick.values():
            event.set()

    def stop(self) -> None:
        self._stop.set()
        self.refresh()

    async def _watch(self, state: TargetState) -> None:
        kick = self._kick[state.target.name]
        while not self._stop.is_set():
            result = await probe(state.target, self._client)
            state.apply(result)
            if self._stop.is_set():
                return
            kick.clear()
            try:
                await asyncio.wait_for(kick.wait(), timeout=state.target.interval_ms / 1000.0)
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
