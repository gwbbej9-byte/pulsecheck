from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pulsecheck import __version__
from pulsecheck.config import ConfigError, load_config, write_sample_config
from pulsecheck.demo import demo_targets, start_mock, stop_mock
from pulsecheck.models import Target
from pulsecheck.tui import run_live, run_once


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ConfigError as exc:
        print(f"pulsecheck: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulsecheck",
        description="Asyncio HTTP/TCP health dashboard.",
    )
    parser.add_argument("--version", action="version", version=f"pulsecheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="probe targets from a YAML or JSON config")
    run_cmd.add_argument("config", type=Path, help="path to config.yaml / config.json")
    run_cmd.add_argument("--once", action="store_true", help="one round, print table, exit 0 if all up")
    run_cmd.add_argument("--json", action="store_true", help="machine JSON on stdout (requires --once)")
    run_cmd.set_defaults(handler=_cmd_run)

    init_cmd = sub.add_parser("init", help="write sample config.yaml in the current directory")
    init_cmd.add_argument(
        "--path",
        type=Path,
        default=Path("config.yaml"),
        help="output path (default: config.yaml)",
    )
    init_cmd.set_defaults(handler=_cmd_init)

    demo_cmd = sub.add_parser("demo", help="start a local mock server and run the dashboard against it")
    demo_cmd.add_argument("--once", action="store_true", help="one round against the mock, then exit")
    demo_cmd.set_defaults(handler=_cmd_demo)

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    dest = write_sample_config(args.path)
    print(f"wrote {dest}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.json and not args.once:
        print("pulsecheck: --json requires --once", file=sys.stderr)
        return 2
    targets = load_config(args.config)
    return _execute(targets, once=args.once, as_json=args.json)


def _cmd_demo(args: argparse.Namespace) -> int:
    return _run_async(_demo_async(args.once))


def _execute(targets: list[Target], once: bool, as_json: bool = False) -> int:
    if once:
        return _run_async(run_once(targets, as_json=as_json))
    return _run_async(run_live(targets))


def _run_async(coro: object) -> int:
    try:
        return asyncio.run(coro)  # type: ignore[arg-type]
    except KeyboardInterrupt:
        return 130


async def _demo_async(once: bool) -> int:
    runner, host, port = await start_mock()
    try:
        targets = demo_targets(host, port)
        if once:
            return await run_once(targets)
        return await run_live(targets)
    finally:
        await stop_mock(runner)
