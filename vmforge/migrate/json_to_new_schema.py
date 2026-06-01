"""Migrate old vuln_automation JSON configs to the VMForge schema."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = ["migrate", "migrate_file", "_is_field_path"]

_STRUCTURAL_PRODUCT_FIELDS = {"name", "signature"}

_STRUCTURAL_ENV_FIELDS = {
    "template_name",
    "used_test_cases",
    "tags",
    "online",
    "platform",
    "executor",
    "snapshot_name",
}

_STD_OUT_PATTERN = re.compile(r"<std_out>")

# Matches a dotted identifier path like "result.code" or "a.b.c".
# Plain strings such as "1.0", "v2.5", "/etc/hosts" do NOT match, preventing
# false-positive equals_field promotion.
_FIELD_PATH_RE = re.compile(r"^[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)+$")


def _to_int_maybe(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_field_path(value: Any) -> bool:
    """Return True only when value looks like a dotted identifier path (e.g. result.sha256)."""
    return isinstance(value, str) and bool(_FIELD_PATH_RE.match(value))


def _convert_check(check: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path, expected in check.items():
        if _is_field_path(expected):
            items.append({"path": path, "equals_field": expected})
        else:
            items.append({"path": path, "equals": expected})
    return items


def _convert_commands(commands: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for cmd in commands:
        uses_prev_output = _STD_OUT_PATTERN.search(cmd) is not None
        step: dict[str, Any] = {"run": cmd}
        if uses_prev_output and steps:
            steps[-1]["capture_as"] = "std_out"
        steps.append(step)
    return steps


def _env_id(template_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", template_name).strip("-").lower()


def migrate(old: dict[str, Any], product_id: str) -> dict[str, Any]:
    """Convert a parsed old-format config dict to a new VMForge schema dict."""
    product_info: dict[str, Any] = old.get("product_info", {})

    product: dict[str, Any] = {
        "id": product_id,
        "name": product_info.get("name", product_id),
    }
    sig = _to_int_maybe(product_info.get("signature"))
    if sig is not None:
        product["signature"] = sig

    top_vars: dict[str, Any] = {
        k: v
        for k, v in product_info.items()
        if k not in _STRUCTURAL_PRODUCT_FIELDS
    }

    environments: list[dict[str, Any]] = []
    for env_raw in old.get("envs", []):
        template = env_raw.get("template_name", "")
        env_id = _env_id(template)

        tags_raw = env_raw.get("tags", "")
        tags: list[str] = (
            [t.strip() for t in tags_raw.split(",") if t.strip()]
            if tags_raw
            else []
        )
        if env_raw.get("online"):
            tags.append("online")

        env_vars: dict[str, Any] = {
            k: v
            for k, v in env_raw.items()
            if k not in _STRUCTURAL_ENV_FIELDS
        }

        env: dict[str, Any] = {
            "id": env_id,
            "template": template,
            "snapshot": env_raw.get("snapshot_name", "automation"),
            "platform": env_raw.get("platform", "vsphere"),
            "executor": env_raw.get("executor", "powershell"),
            "run_tests": list(env_raw.get("used_test_cases", [])),
        }
        if tags:
            env["tags"] = tags
        if env_vars:
            env["vars"] = env_vars

        environments.append(env)

    tests: list[dict[str, Any]] = []
    for i, tc_raw in enumerate(old.get("test_cases", [])):
        before_cmds: list[str] = tc_raw.get("before", {}).get("commands", [])
        tested_cmds: list[str] = tc_raw.get("tested_function", {}).get("commands", [])
        after_check: dict[str, Any] = tc_raw.get("after", {}).get("check", {})
        after_cmds: list[str] = tc_raw.get("after", {}).get("commands", [])

        tc_id = tc_raw.get("id")
        if tc_id is None:
            raise ValueError(
                f"test_case entry at index {i} is missing required 'id' field"
            )
        tc: dict[str, Any] = {"id": tc_id}
        if tc_raw.get("name"):
            tc["name"] = tc_raw["name"].strip()

        if before_cmds:
            tc["setup"] = before_cmds

        steps = _convert_commands(tested_cmds)
        if steps:
            tc["steps"] = steps

        assert_items = _convert_check(after_check)
        if assert_items:
            tc["assert"] = assert_items

        if after_cmds:
            tc["teardown"] = after_cmds

        tests.append(tc)

    return {
        "product": product,
        "vars": top_vars,
        "environments": environments,
        "tests": tests,
    }


def migrate_file(src: Path, dst: Path, product_id: str | None = None) -> None:
    """Read an old-format JSON file and write the migrated schema to dst."""
    pid = product_id or src.stem
    try:
        old = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to migrate {src}: invalid JSON — {exc}") from exc
    new = migrate(old, pid)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
