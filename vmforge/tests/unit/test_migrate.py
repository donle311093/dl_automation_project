from __future__ import annotations

import json
from pathlib import Path

from framework.core.schema.loader import load
from framework.core.schema.models import ProductConfig
from migrate.json_to_new_schema import (
    _convert_check,
    _convert_commands,
    _env_id,
    _is_field_path,
    migrate,
    migrate_file,
)

# ── Minimal old-format fixture ────────────────────────────────────────────────

_MINIMAL_OLD = {
    "product_info": {
        "name": "My App",
        "signature": "9999",
        "wrapper_path": "C:/wrapper",
        "patch_id": "5",
    },
    "envs": [
        {
            "template_name": "windows-10-64",
            "used_test_cases": ["tc1"],
            "tags": "REG1",
            "exe_path": "C:/app.exe",
        }
    ],
    "test_cases": [
        {
            "id": "tc1",
            "name": "Basic test",
            "before": {"commands": ["Setup-Thing"]},
            "tested_function": {"commands": ["Run-App --sig <signature>"]},
            "after": {"check": {"result.code": 0}, "commands": ["Cleanup"]},
        }
    ],
}

# ── TestIsFieldPath ───────────────────────────────────────────────────────────


class TestIsFieldPath:
    def test_dotted_identifiers_match(self) -> None:
        assert _is_field_path("result.sha256") is True

    def test_nested_path_matches(self) -> None:
        assert _is_field_path("result.details.count") is True

    def test_version_string_does_not_match(self) -> None:
        assert _is_field_path("1.0") is False

    def test_semver_does_not_match(self) -> None:
        assert _is_field_path("v2.5.1") is False

    def test_file_path_does_not_match(self) -> None:
        assert _is_field_path("/etc/hosts") is False

    def test_no_dot_does_not_match(self) -> None:
        assert _is_field_path("result") is False

    def test_non_string_does_not_match(self) -> None:
        assert _is_field_path(0) is False

    def test_numeric_segment_after_dot_does_not_match(self) -> None:
        # "a.1" — segment after dot starts with digit
        assert _is_field_path("a.1") is False


# ── TestConvertCheck ──────────────────────────────────────────────────────────


class TestConvertCheck:
    def test_integer_value(self) -> None:
        items = _convert_check({"result.code": 0})
        assert items == [{"path": "result.code", "equals": 0}]

    def test_bool_false(self) -> None:
        items = _convert_check({"result.ok": False})
        assert items == [{"path": "result.ok", "equals": False}]

    def test_string_value(self) -> None:
        items = _convert_check({"result.has_vuln": "true"})
        assert items == [{"path": "result.has_vuln", "equals": "true"}]

    def test_dotted_string_becomes_equals_field(self) -> None:
        items = _convert_check({"result.expected_sha256": "result.sha256"})
        assert items == [{"path": "result.expected_sha256", "equals_field": "result.sha256"}]

    def test_multiple_fields_order_preserved(self) -> None:
        check = {"result.code": 0, "result.patch_id": 12}
        items = _convert_check(check)
        assert len(items) == 2
        assert items[0]["path"] == "result.code"
        assert items[1]["path"] == "result.patch_id"

    def test_empty_check_returns_empty_list(self) -> None:
        assert _convert_check({}) == []


# ── TestConvertCommands ───────────────────────────────────────────────────────


class TestConvertCommands:
    def test_single_command_no_capture(self) -> None:
        steps = _convert_commands(["Run-App"])
        assert steps == [{"run": "Run-App"}]

    def test_std_out_marks_previous_step(self) -> None:
        steps = _convert_commands([
            "(Get-ChildItem -Path \"C:/latest\" -File | Select -First 1).name",
            "Install-App --path C:/latest/<std_out>",
        ])
        assert steps[0]["capture_as"] == "std_out"
        assert "capture_as" not in steps[1]

    def test_std_out_not_marking_first_step_when_alone(self) -> None:
        steps = _convert_commands(["Run --path <std_out>"])
        assert "capture_as" not in steps[0]

    def test_three_commands_middle_captures(self) -> None:
        steps = _convert_commands(["Get-Name", "Use-Name <std_out>", "Cleanup"])
        assert steps[0].get("capture_as") == "std_out"
        assert "capture_as" not in steps[1]
        assert "capture_as" not in steps[2]

    def test_empty_commands(self) -> None:
        assert _convert_commands([]) == []


# ── TestEnvId ─────────────────────────────────────────────────────────────────


class TestEnvId:
    def test_hyphens_lowercased(self) -> None:
        assert _env_id("windows-10-64") == "windows-10-64"

    def test_spaces_become_hyphens(self) -> None:
        assert _env_id("Windows 10 64") == "windows-10-64"

    def test_underscores_become_hyphens(self) -> None:
        assert _env_id("win_10_autologin") == "win-10-autologin"

    def test_multiple_separators_collapsed(self) -> None:
        assert _env_id("win--10__64") == "win-10-64"


# ── TestMigrateProduct ────────────────────────────────────────────────────────


class TestMigrateProduct:
    def test_product_id_from_argument(self) -> None:
        result = migrate(_MINIMAL_OLD, "my-app")
        assert result["product"]["id"] == "my-app"

    def test_product_name(self) -> None:
        result = migrate(_MINIMAL_OLD, "my-app")
        assert result["product"]["name"] == "My App"

    def test_signature_string_becomes_int(self) -> None:
        result = migrate(_MINIMAL_OLD, "my-app")
        assert result["product"]["signature"] == 9999

    def test_signature_already_int(self) -> None:
        old = {**_MINIMAL_OLD, "product_info": {**_MINIMAL_OLD["product_info"], "signature": 42}}
        result = migrate(old, "my-app")
        assert result["product"]["signature"] == 42

    def test_no_signature_field_omitted(self) -> None:
        old = {**_MINIMAL_OLD, "product_info": {"name": "App"}}
        result = migrate(old, "app")
        assert "signature" not in result["product"]

    def test_non_numeric_signature_omitted(self) -> None:
        old = {**_MINIMAL_OLD, "product_info": {**_MINIMAL_OLD["product_info"], "signature": "n/a"}}
        result = migrate(old, "my-app")
        assert "signature" not in result["product"]


# ── TestMigrateVars ───────────────────────────────────────────────────────────


class TestMigrateVars:
    def test_non_structural_fields_go_to_vars(self) -> None:
        result = migrate(_MINIMAL_OLD, "my-app")
        assert result["vars"]["wrapper_path"] == "C:/wrapper"
        assert result["vars"]["patch_id"] == "5"

    def test_structural_fields_excluded_from_vars(self) -> None:
        result = migrate(_MINIMAL_OLD, "my-app")
        assert "name" not in result["vars"]
        assert "signature" not in result["vars"]


# ── TestMigrateEnvironments ───────────────────────────────────────────────────


class TestMigrateEnvironments:
    def test_env_count(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert len(result["environments"]) == 1

    def test_env_template(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["template"] == "windows-10-64"

    def test_env_id_derived(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["id"] == "windows-10-64"

    def test_env_platform_default(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["platform"] == "vsphere"

    def test_env_executor_default(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["executor"] == "powershell"

    def test_env_snapshot_default(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["snapshot"] == "automation"

    def test_env_tags_from_string(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["tags"] == ["REG1"]

    def test_online_flag_appends_tag(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "envs": [{**_MINIMAL_OLD["envs"][0], "online": 1}],
        }
        result = migrate(old, "p")
        assert "online" in result["environments"][0]["tags"]

    def test_no_online_flag_not_in_tags(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert "online" not in result["environments"][0].get("tags", [])

    def test_missing_tags_not_in_output(self) -> None:
        env = {k: v for k, v in _MINIMAL_OLD["envs"][0].items() if k != "tags"}
        old = {**_MINIMAL_OLD, "envs": [env]}
        result = migrate(old, "p")
        assert "tags" not in result["environments"][0]

    def test_env_vars_has_exe_path(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["vars"]["exe_path"] == "C:/app.exe"

    def test_structural_env_fields_not_in_vars(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        env_vars = result["environments"][0].get("vars", {})
        for key in ("template_name", "used_test_cases", "tags", "online"):
            assert key not in env_vars

    def test_run_tests_list(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["environments"][0]["run_tests"] == ["tc1"]


# ── TestMigrateTests ──────────────────────────────────────────────────────────


class TestMigrateTests:
    def test_test_count(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert len(result["tests"]) == 1

    def test_test_id(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["id"] == "tc1"

    def test_test_name_stripped(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["name"] == "Basic test"

    def test_setup_from_before(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["setup"] == ["Setup-Thing"]

    def test_steps_from_tested_function(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["steps"] == [{"run": "Run-App --sig <signature>"}]

    def test_assert_from_check(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["assert"] == [{"path": "result.code", "equals": 0}]

    def test_teardown_from_after_commands(self) -> None:
        result = migrate(_MINIMAL_OLD, "p")
        assert result["tests"][0]["teardown"] == ["Cleanup"]

    def test_empty_before_omitted(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "test_cases": [{**_MINIMAL_OLD["test_cases"][0], "before": {"commands": []}}],
        }
        result = migrate(old, "p")
        assert "setup" not in result["tests"][0]

    def test_empty_check_omits_assert(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "test_cases": [{**_MINIMAL_OLD["test_cases"][0], "after": {"check": {}, "commands": []}}],
        }
        result = migrate(old, "p")
        assert "assert" not in result["tests"][0]

    def test_cross_field_assert(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "test_cases": [{
                **_MINIMAL_OLD["test_cases"][0],
                "after": {"check": {"result.expected_sha256": "result.sha256"}, "commands": []},
            }],
        }
        result = migrate(old, "p")
        assert result["tests"][0]["assert"] == [
            {"path": "result.expected_sha256", "equals_field": "result.sha256"}
        ]

    def test_std_out_capture_wired(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "test_cases": [{
                **_MINIMAL_OLD["test_cases"][0],
                "tested_function": {"commands": [
                    "(Get-ChildItem -Path \"C:/latest\" -File | Select -First 1).name",
                    "Install --path C:/latest/<std_out>",
                ]},
            }],
        }
        result = migrate(old, "p")
        steps = result["tests"][0]["steps"]
        assert steps[0]["capture_as"] == "std_out"
        assert "capture_as" not in steps[1]

    def test_missing_id_raises_value_error(self) -> None:
        old = {
            **_MINIMAL_OLD,
            "test_cases": [{"name": "No ID here", "tested_function": {"commands": ["cmd"]}}],
        }
        import pytest
        with pytest.raises(ValueError, match="missing required .id. field"):
            migrate(old, "p")


# ── TestRoundTrip ─────────────────────────────────────────────────────────────


class TestRoundTrip:
    """Migrated output must pass Pydantic validation via the schema loader."""

    def _round_trip(self, old: dict, product_id: str, tmp_path: Path) -> ProductConfig:
        src = tmp_path / f"{product_id}.json"
        dst = tmp_path / f"{product_id}_new.json"
        src.write_text(json.dumps(old))
        migrate_file(src, dst)
        return load(dst)

    def test_minimal_round_trip(self, tmp_path: Path) -> None:
        cfg = self._round_trip(_MINIMAL_OLD, "my-app", tmp_path)
        assert cfg.product.id == "my-app"
        assert len(cfg.environments) == 1
        assert len(cfg.tests) == 1

    def test_std_out_round_trip_validates(self, tmp_path: Path) -> None:
        old = {
            "product_info": {"name": "App", "signature": "1"},
            "envs": [{"template_name": "win10", "used_test_cases": ["tc1"], "tags": "REG1"}],
            "test_cases": [{
                "id": "tc1",
                "tested_function": {"commands": [
                    "(Get-ChildItem).name",
                    "Install --path C:/<std_out>",
                ]},
                "after": {"check": {"result.code": 0}, "commands": []},
            }],
        }
        cfg = self._round_trip(old, "app", tmp_path)
        steps = cfg.tests[0].steps
        assert steps[0].capture_as == "std_out"
        assert steps[1].capture_as is None

    def test_cross_field_assert_round_trip(self, tmp_path: Path) -> None:
        old = {
            "product_info": {"name": "App"},
            "envs": [{"template_name": "win10", "used_test_cases": ["tc1"]}],
            "test_cases": [{
                "id": "tc1",
                "tested_function": {"commands": ["Run-Check"]},
                "after": {"check": {"result.sha256": "result.expected_sha256"}, "commands": []},
            }],
        }
        cfg = self._round_trip(old, "app", tmp_path)
        assert cfg.tests[0].assert_[0].equals_field == "result.expected_sha256"

    def test_migrate_file_creates_parent_dirs(self, tmp_path: Path) -> None:
        src = tmp_path / "old.json"
        src.write_text(json.dumps(_MINIMAL_OLD))
        dst = tmp_path / "out" / "nested" / "new.json"
        migrate_file(src, dst)
        assert dst.exists()

    def test_migrate_file_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        import pytest
        src = tmp_path / "bad.json"
        src.write_text("not-json")
        dst = tmp_path / "out.json"
        with pytest.raises(ValueError, match="invalid JSON"):
            migrate_file(src, dst)
