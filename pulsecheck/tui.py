from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich import box

from pulsecheck.engine import Engine
from pulsecheck.models import Target, TargetState
from pulsecheck.status import Status, all_up, classify, status_style


class KeyListener:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._restore: Callable[[], None] | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pulsecheck-keys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._restore is not None:
            try:
                self._restore()
            except OSError:
                pass
            self._restore = None
        if self._thread is not None:
            self._thread.join(timeout=0.4)
            self._thread = None

    async def get(self, timeout: float) -> str | None:
        assert self._queue is not None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    def _put(self, key: str) -> None:
        if self._loop is None or self._queue is None:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, key)

    def _run(self) -> None:
        if sys.platform == "win32":
            self._run_windows()
        else:
            self._run_posix()

    def _run_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in {"\x00", "\xe0"}:
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                if char in {"\x03"}:
                    self._put("q")
                    continue
                if char:
                    self._put(char)
            else:
                time.sleep(0.04)

    def _run_posix(self) -> None:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        try:
            original = termios.tcgetattr(fd)
        except termios.error:
            return
        self._restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, original)
        try:
            tty.setcbreak(fd)
            while not self._stop.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not ready:
                    continue
                char = sys.stdin.read(1)
                if char == "\x03":
                    self._put("q")
                elif char:
                    self._put(char)
        finally:
            if self._restore is not None:
                self._restore()
                self._restore = None


def build_table(states: list[TargetState], now: float | None = None) -> Table:
    clock = time.monotonic() if now is None else now
    table = Table(
        box=box.SIMPLE_HEAVY,
        expand=True,
        pad_edge=True,
        header_style="bold cyan",
        border_style="grey37",
        show_lines=False,
    )
    table.add_column("NAME", style="bold white", no_wrap=True, min_width=12)
    table.add_column("KIND", width=6, no_wrap=True)
    table.add_column("STATUS", width=8, no_wrap=True)
    table.add_column("LATENCY_MS", justify="right", width=11, no_wrap=True)
    table.add_column("LAST_ERROR", overflow="ellipsis", no_wrap=True, min_width=22)
    table.add_column("STREAK", justify="right", width=8, no_wrap=True)
    for state in states:
        status = classify(state, clock)
        last = state.last
        latency = "—" if last is None else f"{last.latency_ms:.1f}"
        error = "—"
        if last is not None and last.error:
            error = last.error
        elif status is Status.STALE and last is not None and last.ok:
            age_s = (clock - last.at)
            error = f"last ok {age_s:.1f}s ago"
        table.add_row(
            state.target.name,
            state.target.kind.upper(),
            Text(status.value, style=status_style(status)),
            latency,
            error,
            state.streak_label(),
        )
    return table


def build_view(states: list[TargetState], now: float | None = None) -> Group:
    clock = time.monotonic() if now is None else now
    counts = {Status.UP: 0, Status.DOWN: 0, Status.STALE: 0}
    for state in states:
        counts[classify(state, clock)] += 1
    stamp = datetime.now().strftime("%H:%M:%S")
    title = Text()
    title.append("pulsecheck", style="bold white")
    title.append("  ·  ", style="grey50")
    title.append(stamp, style="grey70")
    title.append("  ·  ", style="grey50")
    title.append(f"{counts[Status.UP]} up", style="green")
    title.append("  ·  ", style="grey50")
    title.append(f"{counts[Status.DOWN]} down", style="red")
    title.append("  ·  ", style="grey50")
    title.append(f"{counts[Status.STALE]} stale", style="yellow")
    footer = Text("q quit   r refresh", style="grey50")
    return Group(title, Text(""), build_table(states, clock), Text(""), footer)


def print_once(states: list[TargetState], console: Console | None = None) -> None:
    out = console or Console()
    out.print(build_view(states))


def snapshot(states: list[TargetState], now: float | None = None) -> dict[str, Any]:
    clock = time.monotonic() if now is None else now
    rows: list[dict[str, Any]] = []
    for state in states:
        status = classify(state, clock)
        last = state.last
        rows.append(
            {
                "name": state.target.name,
                "kind": state.target.kind,
                "status": status.value,
                "latency_ms": None if last is None else last.latency_ms,
                "error": None if last is None else last.error,
                "streak": state.streak,
                "status_code": None if last is None else last.status_code,
                "endpoint": state.target.endpoint(),
            }
        )
    return {"ok": all_up(states, clock), "targets": rows}


def print_json(states: list[TargetState], stream: Any | None = None) -> None:
    out = sys.stdout if stream is None else stream
    json.dump(snapshot(states), out, separators=(",", ":"))
    out.write("\n")


async def run_once(
    targets: list[Target],
    console: Console | None = None,
    as_json: bool = False,
) -> int:
    engine = Engine(targets)
    states = await engine.run_once()
    if as_json:
        print_json(states)
    else:
        print_once(states, console)
    return 0 if all_up(states) else 1


async def run_live(targets: list[Target], console: Console | None = None) -> int:
    out = console or Console()
    engine = Engine(targets)
    keys = KeyListener()
    live = Live(build_view(engine.states), console=out, refresh_per_second=8, screen=True)
    keys.start()
    live.start()
    worker = asyncio.create_task(engine.run(), name="pulsecheck-engine")
    try:
        while True:
            key = await keys.get(0.12)
            if key in {"q", "Q"}:
                break
            if key in {"r", "R"}:
                engine.refresh()
            live.update(build_view(engine.states))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        engine.stop()
        try:
            await asyncio.wait_for(worker, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        live.stop()
        keys.stop()
    return 0
