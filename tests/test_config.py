from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulsecheck.config import ConfigError, load_config, parse_targets, write_sample_config


def test_parse_yaml_http_and_tcp(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
targets:
  - name: web
    url: http://127.0.0.1:8080/ok
    interval_ms: 1000
    timeout_ms: 800
    expect_status: 204
  - name: db
    host: 127.0.0.1
    port: 5432
    interval_ms: 1500
    timeout_ms: 400
""",
        encoding="utf-8",
    )
    targets = load_config(path)
    assert [t.name for t in targets] == ["web", "db"]
    assert targets[0].kind == "http"
    assert targets[0].url == "http://127.0.0.1:8080/ok"
    assert targets[0].expect_status == 204
    assert targets[0].interval_ms == 1000
    assert targets[1].kind == "tcp"
    assert targets[1].host == "127.0.0.1"
    assert targets[1].port == 5432


def test_parse_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "api",
                        "url": "https://example.com/health",
                        "interval_ms": 2000,
                        "timeout_ms": 1000,
                        "expect_status": 200,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    targets = load_config(path)
    assert len(targets) == 1
    assert targets[0].kind == "http"
    assert targets[0].url == "https://example.com/health"


def test_defaults_when_optional_fields_omitted() -> None:
    targets = parse_targets(
        {"targets": [{"name": "web", "url": "http://localhost/"}]}
    )
    assert targets[0].interval_ms == 5000
    assert targets[0].timeout_ms == 3000
    assert targets[0].expect_status is None
    assert targets[0].retries == 0
    assert targets[0].backoff_ms == 200
    assert targets[0].kind == "http"


def test_reject_unknown_kind() -> None:
    with pytest.raises(ConfigError, match="unknown kind"):
        parse_targets(
            {"targets": [{"name": "web", "kind": "icmp", "url": "http://127.0.0.1/"}]}
        )


def test_reject_interval_not_positive() -> None:
    with pytest.raises(ConfigError, match="interval_ms"):
        parse_targets(
            {"targets": [{"name": "web", "url": "http://127.0.0.1/", "interval_ms": 0}]}
        )


def test_explicit_kind_http_and_tcp() -> None:
    targets = parse_targets(
        {
            "targets": [
                {"name": "web", "kind": "HTTP", "url": "http://127.0.0.1/ok"},
                {"name": "db", "kind": "tcp", "host": "127.0.0.1", "port": 5432},
            ]
        }
    )
    assert targets[0].kind == "http"
    assert targets[1].kind == "tcp"


def test_reject_url_and_host() -> None:
    with pytest.raises(ConfigError, match="url OR host:port"):
        parse_targets(
            {
                "targets": [
                    {
                        "name": "mixed",
                        "url": "http://127.0.0.1/ok",
                        "host": "127.0.0.1",
                        "port": 80,
                    }
                ]
            }
        )


def test_reject_duplicate_names() -> None:
    with pytest.raises(ConfigError, match="duplicate"):
        parse_targets(
            {
                "targets": [
                    {"name": "web", "url": "http://a/"},
                    {"name": "web", "url": "http://b/"},
                ]
            }
        )


def test_reject_empty_targets() -> None:
    with pytest.raises(ConfigError, match="non-empty"):
        parse_targets({"targets": []})


def test_reject_tcp_expect_status() -> None:
    with pytest.raises(ConfigError, match="HTTP-only"):
        parse_targets(
            {"targets": [{"name": "db", "host": "127.0.0.1", "port": 5432, "expect_status": 200}]}
        )


def test_reject_bad_url_scheme() -> None:
    with pytest.raises(ConfigError, match="http://"):
        parse_targets({"targets": [{"name": "web", "url": "ftp://example.com"}]})


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_init_writes_sample(tmp_path: Path) -> None:
    dest = tmp_path / "config.yaml"
    written = write_sample_config(dest)
    assert written == dest
    targets = load_config(dest)
    assert len(targets) == 3
    with pytest.raises(ConfigError, match="already exists"):
        write_sample_config(dest)
