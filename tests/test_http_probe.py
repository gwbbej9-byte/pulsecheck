from __future__ import annotations

import httpx
import pytest

from pulsecheck.models import Target
from pulsecheck.probe import http_ok, probe, probe_http


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/ok":
        return httpx.Response(200, text="ok")
    if request.url.path == "/created":
        return httpx.Response(201, text="created")
    if request.url.path == "/fail":
        return httpx.Response(500, text="fail")
    if request.url.path == "/slow":
        raise httpx.TimeoutException("simulated")
    return httpx.Response(404, text="missing")


@pytest.fixture
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_handler), follow_redirects=True)


@pytest.mark.asyncio
async def test_http_ok_matches_expect_status(client: httpx.AsyncClient) -> None:
    async with client:
        target = Target("api", "http", 1000, 800, url="http://mock/ok", expect_status=200)
        result = await probe_http(target, client)
    assert result.ok is True
    assert result.status_code == 200
    assert result.error is None
    assert result.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_http_status_mismatch(client: httpx.AsyncClient) -> None:
    async with client:
        target = Target("billing", "http", 1000, 800, url="http://mock/fail", expect_status=200)
        result = await probe_http(target, client)
    assert result.ok is False
    assert result.status_code == 500
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_http_timeout(client: httpx.AsyncClient) -> None:
    async with client:
        target = Target("slow", "http", 1000, 50, url="http://mock/slow", expect_status=200)
        result = await probe_http(target, client)
    assert result.ok is False
    assert result.error == "timeout"


@pytest.mark.asyncio
async def test_http_any_2xx_when_expect_omitted(client: httpx.AsyncClient) -> None:
    async with client:
        target = Target("created", "http", 1000, 800, url="http://mock/created")
        result = await probe_http(target, client)
    assert result.ok is True
    assert result.status_code == 201
    assert http_ok(201, None) is True
    assert http_ok(404, None) is False
    assert http_ok(201, 200) is False


@pytest.mark.asyncio
async def test_http_non_2xx_is_down(client: httpx.AsyncClient) -> None:
    async with client:
        target = Target("missing", "http", 1000, 800, url="http://mock/nope")
        result = await probe_http(target, client)
    assert result.ok is False
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_retries_then_ok() -> None:
    hits = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] < 3:
            return httpx.Response(500, text="fail")
        return httpx.Response(200, text="ok")

    target = Target(
        "flaky",
        "http",
        1000,
        800,
        url="http://mock/ok",
        retries=2,
        backoff_ms=1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(flaky), follow_redirects=True) as client:
        result = await probe(target, client)
    assert result.ok is True
    assert hits["n"] == 3
