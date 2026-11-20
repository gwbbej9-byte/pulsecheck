from __future__ import annotations

from aiohttp import web

from pulsecheck.models import Target

PREFERRED_HOST = "127.0.0.1"
PREFERRED_PORT = 18765


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ok", _handle_ok)
    app.router.add_get("/fail", _handle_fail)
    return app


async def _handle_ok(_request: web.Request) -> web.Response:
    return web.Response(text="ok\n", status=200, content_type="text/plain")


async def _handle_fail(_request: web.Request) -> web.Response:
    return web.Response(text="fail\n", status=500, content_type="text/plain")


def bound_port(runner: web.AppRunner) -> int:
    for site in runner.sites:
        server = getattr(site, "_server", None)
        sockets = getattr(server, "sockets", None) if server is not None else None
        if sockets:
            return int(sockets[0].getsockname()[1])
    raise RuntimeError("mock server has no bound socket")


async def start_mock(host: str = PREFERRED_HOST, port: int = PREFERRED_PORT) -> tuple[web.AppRunner, str, int]:
    runner = web.AppRunner(build_app(), access_log=None)
    await runner.setup()
    last_error: OSError | None = None
    for candidate in (port, 0):
        site = web.TCPSite(runner, host, candidate, reuse_address=True)
        try:
            await site.start()
            last_error = None
            break
        except OSError as exc:
            last_error = exc
    if last_error is not None:
        await runner.cleanup()
        raise last_error
    return runner, host, bound_port(runner)


def demo_targets(host: str, port: int) -> list[Target]:
    base = f"http://{host}:{port}"
    return [
        Target("api-gateway", "http", 1000, 800, url=f"{base}/ok", expect_status=200),
        Target("billing", "http", 1000, 800, url=f"{base}/fail", expect_status=200),
        Target("postgres", "tcp", 1500, 500, host=host, port=port),
        Target("redis", "tcp", 2000, 400, host=host, port=59999),
        Target("metrics", "http", 2000, 800, url=f"{base}/ok", expect_status=200),
        Target("dead-http", "http", 2000, 300, url=f"http://{host}:59999/", expect_status=200),
    ]


async def stop_mock(runner: web.AppRunner) -> None:
    await runner.cleanup()
