from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from pulsecheck.models import Target

DEFAULT_INTERVAL_MS = 5000
DEFAULT_TIMEOUT_MS = 3000
DEFAULT_RETRIES = 0
DEFAULT_BACKOFF_MS = 200
KNOWN_KINDS = frozenset({"http", "tcp"})


class ConfigError(ValueError):
    pass


def load_config(path: str | Path) -> list[Target]:
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"config not found: {file_path}")
    raw_text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        payload = _parse_json(raw_text, file_path)
    elif suffix in {".yaml", ".yml"}:
        payload = _parse_yaml(raw_text, file_path)
    else:
        payload = _parse_unknown(raw_text, file_path)
    return parse_targets(payload)


def parse_targets(payload: Any) -> list[Target]:
    if not isinstance(payload, dict):
        raise ConfigError("config root must be a mapping with a 'targets' list")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ConfigError("config must contain a non-empty 'targets' list")
    targets: list[Target] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_targets):
        target = _parse_target(item, index)
        if target.name in seen:
            raise ConfigError(f"duplicate target name: {target.name}")
        seen.add(target.name)
        targets.append(target)
    return targets


def sample_config_yaml() -> str:
    return (
        "# pulsecheck — HTTP + TCP health targets\n"
        "targets:\n"
        "  - name: example-http\n"
        "    kind: http\n"
        "    url: https://example.com\n"
        "    interval_ms: 5000\n"
        "    timeout_ms: 3000\n"
        "    retries: 0\n"
        "    backoff_ms: 200\n"
        "  - name: local-mock\n"
        "    kind: http\n"
        "    url: http://127.0.0.1:18765/ok\n"
        "    interval_ms: 1000\n"
        "    timeout_ms: 800\n"
        "    expect_status: 200\n"
        "  - name: local-tcp\n"
        "    kind: tcp\n"
        "    host: 127.0.0.1\n"
        "    port: 18765\n"
        "    interval_ms: 1500\n"
        "    timeout_ms: 500\n"
        "    retries: 1\n"
        "    backoff_ms: 200\n"
    )


def write_sample_config(path: str | Path) -> Path:
    dest = Path(path)
    if dest.exists():
        raise ConfigError(f"{dest} already exists")
    dest.write_text(sample_config_yaml(), encoding="utf-8")
    return dest


def _parse_unknown(raw_text: str, file_path: Path) -> Any:
    try:
        return _parse_yaml(raw_text, file_path)
    except ConfigError:
        return _parse_json(raw_text, file_path)


def _parse_yaml(raw_text: str, file_path: Path) -> Any:
    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
    return payload


def _parse_json(raw_text: str, file_path: Path) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {file_path}: {exc}") from exc


def _parse_target(item: Any, index: int) -> Target:
    loc = f"targets[{index}]"
    if not isinstance(item, dict):
        raise ConfigError(f"{loc} must be a mapping")
    name = _require_str(item, "name", loc)
    kind = _parse_kind(item, loc, name)
    has_url = "url" in item and item["url"] is not None
    has_host = "host" in item and item["host"] is not None
    has_port = "port" in item and item["port"] is not None
    if has_url and (has_host or has_port):
        raise ConfigError(f"{loc} ({name}): use url OR host:port, not both")
    if kind == "http" and not has_url:
        raise ConfigError(f"{loc} ({name}): kind http needs url")
    if kind == "tcp" and not (has_host and has_port):
        raise ConfigError(f"{loc} ({name}): kind tcp needs host+port")
    if kind is None:
        if has_url:
            kind = "http"
        elif has_host and has_port:
            kind = "tcp"
        else:
            raise ConfigError(f"{loc} ({name}): need url or host+port")
    interval_ms = _optional_int(item, "interval_ms", loc, DEFAULT_INTERVAL_MS, minimum=1)
    timeout_ms = _optional_int(item, "timeout_ms", loc, DEFAULT_TIMEOUT_MS, minimum=1)
    retries = _optional_int(item, "retries", loc, DEFAULT_RETRIES, minimum=0)
    backoff_ms = _optional_int(item, "backoff_ms", loc, DEFAULT_BACKOFF_MS, minimum=0)
    if kind == "http":
        url = _require_str(item, "url", loc)
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"{loc} ({name}): url must start with http:// or https://")
        expect_status: int | None
        if "expect_status" not in item or item["expect_status"] is None:
            expect_status = None
        else:
            expect_status = _optional_int(
                item, "expect_status", loc, 200, minimum=100, maximum=599
            )
        return Target(
            name=name,
            kind="http",
            interval_ms=interval_ms,
            timeout_ms=timeout_ms,
            url=url,
            expect_status=expect_status,
            retries=retries,
            backoff_ms=backoff_ms,
        )
    host = _require_str(item, "host", loc)
    port = _optional_int(item, "port", loc, 0, minimum=1, maximum=65535)
    if "expect_status" in item and item["expect_status"] is not None:
        raise ConfigError(f"{loc} ({name}): expect_status is HTTP-only")
    return Target(
        name=name,
        kind="tcp",
        interval_ms=interval_ms,
        timeout_ms=timeout_ms,
        host=host,
        port=port,
        retries=retries,
        backoff_ms=backoff_ms,
    )


def _parse_kind(item: dict[str, Any], loc: str, name: str) -> str | None:
    if "kind" not in item or item["kind"] is None:
        return None
    kind = item["kind"]
    if not isinstance(kind, str) or not kind.strip():
        raise ConfigError(f"{loc} ({name}): unknown kind: {kind!r}")
    normalized = kind.strip().lower()
    if normalized not in KNOWN_KINDS:
        raise ConfigError(f"{loc} ({name}): unknown kind: {kind}")
    return normalized


def _require_str(item: dict[str, Any], key: str, loc: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{loc}: '{key}' must be a non-empty string")
    return value.strip()


def _optional_int(
    item: dict[str, Any],
    key: str,
    loc: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if key not in item or item[key] is None:
        return default
    value = item[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{loc}: '{key}' must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{loc}: '{key}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{loc}: '{key}' must be <= {maximum}")
    return value
