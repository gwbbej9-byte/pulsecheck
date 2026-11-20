from __future__ import annotations

import asyncio
import time

import httpx

from pulsecheck.models import ProbeResult, Target

ERROR_LIMIT = 48


def clip_error(message: str, limit: int = ERROR_LIMIT) -> str:
    text = " ".join(message.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _now_pair() -> tuple[float, float]:
    return time.perf_counter(), time.monotonic()


def _latency_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)


def http_ok(status_code: int, expect_status: int | None) -> bool:
    if expect_status is not None:
        return status_code == expect_status
    return 200 <= status_code < 300


async def probe(target: Target, client: httpx.AsyncClient | None = None) -> ProbeResult:
    last: ProbeResult | None = None
    attempts = target.retries + 1
    for attempt in range(attempts):
        try:
            last = await _probe_once(target, client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            started, at = _now_pair()
            last = ProbeResult(False, _latency_ms(started), clip_error(str(exc) or type(exc).__name__), at, None)
        if last.ok:
            return last
        if attempt + 1 < attempts:
            delay_s = (target.backoff_ms / 1000.0) * (2**attempt)
            if delay_s > 0:
                await asyncio.sleep(delay_s)
    assert last is not None
    return last


async def _probe_once(target: Target, client: httpx.AsyncClient | None) -> ProbeResult:
    if target.kind == "http":
        if client is None:
            timeout = httpx.Timeout(target.timeout_ms / 1000.0)
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as owned:
                return await probe_http(target, owned)
        return await probe_http(target, client)
    return await probe_tcp(target)


async def probe_http(target: Target, client: httpx.AsyncClient) -> ProbeResult:
    if not target.url:
        raise ValueError(f"{target.name}: HTTP target missing url")
    started, at = _now_pair()
    timeout_s = target.timeout_ms / 1000.0
    try:
        async with asyncio.timeout(timeout_s):
            response = await client.get(target.url, timeout=timeout_s)
        latency = _latency_ms(started)
        if http_ok(response.status_code, target.expect_status):
            return ProbeResult(True, latency, None, at, response.status_code)
        return ProbeResult(
            False,
            latency,
            clip_error(f"status {response.status_code}"),
            at,
            response.status_code,
        )
    except asyncio.CancelledError:
        raise
    except (TimeoutError, httpx.TimeoutException):
        return ProbeResult(False, _latency_ms(started), "timeout", at, None)
    except httpx.ConnectError as exc:
        return ProbeResult(False, _latency_ms(started), clip_error(_connect_error(exc)), at, None)
    except httpx.HTTPError as exc:
        return ProbeResult(False, _latency_ms(started), clip_error(str(exc) or exc.__class__.__name__), at, None)


async def probe_tcp(target: Target) -> ProbeResult:
    if not target.host or target.port is None:
        raise ValueError(f"{target.name}: TCP target missing host/port")
    started, at = _now_pair()
    timeout_s = target.timeout_ms / 1000.0
    writer = None
    try:
        async with asyncio.timeout(timeout_s):
            _reader, writer = await asyncio.open_connection(target.host, target.port)
        return ProbeResult(True, _latency_ms(started), None, at, None)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        return ProbeResult(False, _latency_ms(started), "timeout", at, None)
    except ConnectionRefusedError:
        return ProbeResult(False, _latency_ms(started), "connection refused", at, None)
    except OSError as exc:
        return ProbeResult(False, _latency_ms(started), clip_error(_os_error(exc)), at, None)
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def _connect_error(exc: httpx.ConnectError) -> str:
    cause = exc.__cause__ or exc
    if isinstance(cause, ConnectionRefusedError):
        return "connection refused"
    text = str(cause)
    if "Connect call failed" in text or "All connection attempts failed" in text:
        return "connection refused"
    return text or "connect error"


def _os_error(exc: OSError) -> str:
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    winerr = getattr(exc, "winerror", None)
    if winerr == 1225:
        return "connection refused"
    if exc.errno in {111, 10061}:
        return "connection refused"
    return str(exc) or "os error"
