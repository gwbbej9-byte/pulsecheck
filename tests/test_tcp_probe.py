from __future__ import annotations

import asyncio

import pytest

from pulsecheck.models import Target
from pulsecheck.probe import probe_tcp


async def _accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


@pytest.mark.asyncio
async def test_tcp_connect_to_local_socket() -> None:
    server = await asyncio.start_server(_accept, "127.0.0.1", 0)
    sockets = server.sockets
    assert sockets
    port = int(sockets[0].getsockname()[1])
    try:
        target = Target("db", "tcp", 1000, 800, host="127.0.0.1", port=port)
        result = await probe_tcp(target)
        assert result.ok is True
        assert result.error is None
        assert result.latency_ms >= 0.0
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tcp_refused() -> None:
    target = Target("redis", "tcp", 1000, 400, host="127.0.0.1", port=1)
    result = await probe_tcp(target)
    assert result.ok is False
    assert result.error is not None
