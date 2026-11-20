from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pulsecheck.cli import main
from pulsecheck.config import load_config, write_sample_config
from pulsecheck.demo import demo_targets, start_mock, stop_mock
from pulsecheck.engine import Engine
from pulsecheck.status import Status, classify
from tests.conftest import ThreadedMock


@pytest.mark.asyncio
async def test_once_mixed_and_all_up_against_mock() -> None:
    runner, host, port = await start_mock()
    try:
        mixed = demo_targets(host, port)
        mixed_states = await Engine(mixed).run_once()
        ups = [state.target for state in mixed_states if classify(state) is Status.UP]
        downs = [state.target for state in mixed_states if classify(state) is Status.DOWN]
        assert ups
        assert downs
        up_states = await Engine(ups).run_once()
        assert all(classify(state) is Status.UP for state in up_states)
        down_states = await Engine(downs).run_once()
        assert all(classify(state) is not Status.UP for state in down_states)
    finally:
        await stop_mock(runner)


def test_cli_once_all_up_exits_zero(tmp_path: Path) -> None:
    with ThreadedMock() as mock:
        path = tmp_path / "up.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "targets": [
                        {
                            "name": "ok",
                            "url": f"http://{mock.host}:{mock.port}/ok",
                            "interval_ms": 1000,
                            "timeout_ms": 800,
                            "expect_status": 200,
                        },
                        {
                            "name": "tcp",
                            "host": mock.host,
                            "port": mock.port,
                            "interval_ms": 1000,
                            "timeout_ms": 800,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert main(["run", str(path), "--once"]) == 0


def test_cli_once_any_down_exits_one(tmp_path: Path) -> None:
    with ThreadedMock() as mock:
        path = tmp_path / "down.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "targets": [
                        {
                            "name": "fail",
                            "url": f"http://{mock.host}:{mock.port}/fail",
                            "interval_ms": 1000,
                            "timeout_ms": 800,
                            "expect_status": 200,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert main(["run", str(path), "--once"]) == 1


def test_cli_once_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ThreadedMock() as mock:
        path = tmp_path / "up.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "targets": [
                        {
                            "name": "ok",
                            "url": f"http://{mock.host}:{mock.port}/ok",
                            "interval_ms": 1000,
                            "timeout_ms": 800,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert main(["run", str(path), "--once", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["targets"][0]["name"] == "ok"
    assert payload["targets"][0]["status"] == "UP"
    assert payload["targets"][0]["kind"] == "http"


def test_cli_json_requires_once(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text("targets:\n  - name: web\n    url: http://127.0.0.1/\n", encoding="utf-8")
    assert main(["run", str(path), "--json"]) == 2


def test_cli_demo_once_exits_one() -> None:
    # demo mix includes /fail and closed ports, so --once is non-zero
    code = main(["demo", "--once"])
    assert code == 1


def test_cli_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "config.yaml").is_file()
    assert main(["init"]) == 2


def test_write_sample_roundtrip(tmp_path: Path) -> None:
    dest = write_sample_config(tmp_path / "config.yaml")
    targets = load_config(dest)
    assert {t.kind for t in targets} == {"http", "tcp"}
