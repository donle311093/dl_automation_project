from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner, Result

from framework.cli import app

runner = CliRunner()

# ── shared fixtures / helpers ─────────────────────────────────────────────────

_VALID_CONFIG = {
    "product": {"id": "my-app", "name": "My App"},
    "vars": {"path": "C:/foo"},
    "environments": [
        {
            "id": "win10",
            "template": "win10-tpl",
            "snapshot": "automation",
            "platform": "vsphere",
            "executor": "powershell",
            "tags": ["REG1"],
            "run_tests": ["t1"],
        }
    ],
    "tests": [
        {
            "id": "t1",
            "steps": [{"run": "Get-Item <path>", "capture_as": "output"}],
            "assert": [{"path": "result.code", "equals": 0}],
        }
    ],
}

_OLD_FORMAT = {
    "product_info": {"name": "My App", "signature": "1", "wrapper_path": "C:/w"},
    "envs": [{"template_name": "win10", "used_test_cases": ["tc1"], "tags": "REG1"}],
    "test_cases": [
        {
            "id": "tc1",
            "tested_function": {"commands": ["Run-App"]},
            "after": {"check": {"result.code": 0}, "commands": []},
        }
    ],
}


def _write_config(tmp_path: Path, data: dict | None = None) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data if data is not None else _VALID_CONFIG))
    return p


# ── TestValidate ──────────────────────────────────────────────────────────────


class TestValidate:
    def test_valid_config_exits_zero(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        result = runner.invoke(app, ["validate", str(cfg)])
        assert result.exit_code == 0

    def test_valid_config_shows_summary(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        result = runner.invoke(app, ["validate", str(cfg)])
        assert "my-app" in result.output
        assert "win10" in result.output
        assert "OK" in result.output

    def test_missing_file_exits_nonzero(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", str(tmp_path / "nope.json")])
        assert result.exit_code != 0

    def test_invalid_json_exits_nonzero(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not-json")
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code != 0

    def test_schema_error_exits_nonzero(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"product": {"id": "x"}}))  # missing name
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code != 0


# ── TestGenerate ──────────────────────────────────────────────────────────────


class TestGenerate:
    def test_creates_robot_file(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        out = tmp_path / "out"
        result = runner.invoke(app, ["generate", str(cfg), "--out-dir", str(out)])
        assert result.exit_code == 0
        assert any(out.glob("*.robot"))

    def test_robot_file_name_format(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        out = tmp_path / "out"
        runner.invoke(app, ["generate", str(cfg), "--out-dir", str(out)])
        assert (out / "my-app__win10.robot").exists()

    def test_robot_file_contains_suite_setup(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        out = tmp_path / "out"
        runner.invoke(app, ["generate", str(cfg), "--out-dir", str(out)])
        text = (out / "my-app__win10.robot").read_text()
        assert "Clone VM" in text
        assert "win10-tpl" in text

    def test_output_dir_created(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        out = tmp_path / "new" / "nested"
        result = runner.invoke(app, ["generate", str(cfg), "--out-dir", str(out)])
        assert result.exit_code == 0
        assert out.is_dir()

    def test_invalid_config_exits_nonzero(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("bad")
        result = runner.invoke(app, ["generate", str(p)])
        assert result.exit_code != 0

    def test_directory_input_generates_all(self, tmp_path: Path) -> None:
        d = tmp_path / "configs"
        d.mkdir()
        for i in range(2):
            cfg = dict(_VALID_CONFIG)
            cfg["product"] = {"id": f"app{i}", "name": f"App {i}"}
            (d / f"app{i}.json").write_text(json.dumps(cfg))
        out = tmp_path / "out"
        result = runner.invoke(app, ["generate", str(d), "--out-dir", str(out)])
        assert result.exit_code == 0
        assert len(list(out.glob("*.robot"))) == 2

    def test_shows_generated_file_paths(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        out = tmp_path / "out"
        result = runner.invoke(app, ["generate", str(cfg), "--out-dir", str(out)])
        assert "my-app__win10.robot" in result.output


# ── TestRun ───────────────────────────────────────────────────────────────────


class TestRun:
    def _run_with_mock(self, tmp_path: Path, extra_args: list[str] | None = None, returncode: int = 0) -> tuple[Result, MagicMock]:
        cfg = _write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = returncode
        with (
            patch("framework.cli.shutil.which", return_value="/usr/bin/pabot"),
            patch("framework.cli.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = runner.invoke(app, ["run", str(cfg)] + (extra_args or []))
        return result, mock_run

    def test_calls_pabot_by_default(self, tmp_path: Path) -> None:
        _, mock_run = self._run_with_mock(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "/usr/bin/pabot" in cmd[0]

    def test_passes_processes_flag(self, tmp_path: Path) -> None:
        _, mock_run = self._run_with_mock(tmp_path, ["--processes", "8"])
        cmd = mock_run.call_args[0][0]
        assert "--processes" in cmd
        assert "8" in cmd

    def test_robot_flag_calls_robot(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("framework.cli.shutil.which", return_value="/usr/bin/robot"),
            patch("framework.cli.subprocess.run", return_value=mock_result) as mock_run,
        ):
            runner.invoke(app, ["run", str(cfg), "--robot"])
        cmd = mock_run.call_args[0][0]
        assert "--processes" not in cmd

    def test_runner_not_found_exits_nonzero(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        with patch("framework.cli.shutil.which", return_value=None):
            result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code != 0

    def test_propagates_runner_exit_code(self, tmp_path: Path) -> None:
        result, _ = self._run_with_mock(tmp_path, returncode=1)
        assert result.exit_code == 1

    def test_generates_suites_before_running(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        out = tmp_path / "results"
        with (
            patch("framework.cli.shutil.which", return_value="/usr/bin/pabot"),
            patch("framework.cli.subprocess.run", return_value=mock_result),
        ):
            runner.invoke(app, ["run", str(cfg), "--out-dir", str(out)])
        assert (out / "suites").is_dir()


# ── TestReport ────────────────────────────────────────────────────────────────

_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generated="20240101 10:00:00.000" rpa="false" schemaversion="4">
<suite name="Suite">
<test name="my-app :: win10 :: t1" id="s1-t1">
<status status="PASS" elapsed="1.5"/>
</test>
</suite>
<statistics/><errors/>
</robot>"""


class TestReport:
    def _xml(self, tmp_path: Path) -> Path:
        p = tmp_path / "output.xml"
        p.write_text(_SAMPLE_XML)
        return p

    def test_excel_format_creates_xlsx(self, tmp_path: Path) -> None:
        xml = self._xml(tmp_path)
        result = runner.invoke(app, ["report", str(xml), "--format", "excel"])
        assert result.exit_code == 0
        assert (tmp_path / "output.xlsx").exists()

    def test_custom_out_path(self, tmp_path: Path) -> None:
        xml = self._xml(tmp_path)
        dst = tmp_path / "custom.xlsx"
        result = runner.invoke(app, ["report", str(xml), "--format", "excel", "--out", str(dst)])
        assert result.exit_code == 0
        assert dst.exists()

    def test_missing_xml_exits_nonzero(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["report", str(tmp_path / "nope.xml")])
        assert result.exit_code != 0

    def test_junit_format_calls_rebot(self, tmp_path: Path) -> None:
        xml = self._xml(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["report", str(xml), "--format", "junit"])
        assert result.exit_code == 0

    def test_both_format_generates_two_files(self, tmp_path: Path) -> None:
        xml = self._xml(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["report", str(xml), "--format", "both"])
        assert result.exit_code == 0
        assert (tmp_path / "output.xlsx").exists()

    def test_rebot_failure_exits_nonzero(self, tmp_path: Path) -> None:
        xml = self._xml(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["report", str(xml), "--format", "junit"])
        assert result.exit_code != 0


# ── TestMigrate ───────────────────────────────────────────────────────────────


class TestMigrate:
    def _old(self, tmp_path: Path, name: str = "old.json") -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(_OLD_FORMAT))
        return p

    def test_single_file_creates_output(self, tmp_path: Path) -> None:
        src = self._old(tmp_path)
        dst = tmp_path / "new.json"
        result = runner.invoke(app, ["migrate", str(src), "--dst", str(dst)])
        assert result.exit_code == 0
        assert dst.exists()

    def test_output_validates_as_new_schema(self, tmp_path: Path) -> None:
        from framework.core.schema.loader import load
        src = self._old(tmp_path)
        dst = tmp_path / "new.json"
        runner.invoke(app, ["migrate", str(src), "--dst", str(dst)])
        cfg = load(dst)
        assert cfg.product.signature == 1

    def test_default_dst_appends_new_suffix(self, tmp_path: Path) -> None:
        src = self._old(tmp_path)
        result = runner.invoke(app, ["migrate", str(src)])
        assert result.exit_code == 0
        assert (tmp_path / "old.new.json").exists()

    def test_product_id_override(self, tmp_path: Path) -> None:
        from framework.core.schema.loader import load
        src = self._old(tmp_path)
        dst = tmp_path / "new.json"
        runner.invoke(app, ["migrate", str(src), "--dst", str(dst), "--product-id", "custom-id"])
        cfg = load(dst)
        assert cfg.product.id == "custom-id"

    def test_directory_mode_requires_out_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "configs"
        d.mkdir()
        self._old(d)
        result = runner.invoke(app, ["migrate", str(d)])
        assert result.exit_code != 0
        # CliRunner defaults to mix_stderr=True, so err=True messages land in output.
        assert "--out-dir" in result.output

    def test_directory_mode_migrates_all(self, tmp_path: Path) -> None:
        d = tmp_path / "configs"
        d.mkdir()
        for i in range(3):
            self._old(d, f"app{i}.json")
        out = tmp_path / "out"
        result = runner.invoke(app, ["migrate", str(d), "--out-dir", str(out)])
        assert result.exit_code == 0
        assert len(list(out.glob("*.json"))) == 3

    def test_directory_mode_empty_dir_exits_nonzero(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        result = runner.invoke(app, ["migrate", str(d), "--out-dir", str(tmp_path / "out")])
        assert result.exit_code != 0

    def test_missing_src_exits_nonzero(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["migrate", str(tmp_path / "nope.json")])
        assert result.exit_code != 0

    def test_invalid_json_exits_nonzero(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not-json")
        result = runner.invoke(app, ["migrate", str(p)])
        assert result.exit_code != 0

    def test_shows_migrated_path_in_output(self, tmp_path: Path) -> None:
        src = self._old(tmp_path)
        dst = tmp_path / "new.json"
        result = runner.invoke(app, ["migrate", str(src), "--dst", str(dst)])
        assert "new.json" in result.output
