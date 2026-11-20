from __future__ import annotations

import asyncio
import threading
from types import TracebackType

from pulsecheck.demo import start_mock, stop_mock


class ThreadedMock:
    """Keep aiohttp on the loop that created it so CLI tests can use a second loop."""

    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._runner = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    def start(self) -> ThreadedMock:
        self._thread = threading.Thread(target=self._run, name="pulsecheck-mock", daemon=True)
        self._thread.start()
        if not self._ready.wait(8.0):
            raise RuntimeError("mock server did not start")
        if self._error is not None:
            raise self._error
        return self

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def __enter__(self) -> ThreadedMock:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._runner, self.host, self.port = loop.run_until_complete(start_mock())
            self._ready.set()
            loop.run_forever()
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            if self._runner is not None:
                try:
                    loop.run_until_complete(stop_mock(self._runner))
                except (AttributeError, RuntimeError):
                    pass
            loop.close()
