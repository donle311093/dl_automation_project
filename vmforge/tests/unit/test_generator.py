
from pathlib import Path

import pytest

from framework.core.schema.loader import load
from framework.core.schema.models import (
    AssertItem,
    Environment,
    Product,
    ProductConfig,
    Step,
    TestCaseSpec,
)
from framework.robot.generator.renderer import render_suite, suite_filename
from framework.robot.generator.suite_builder import (
    RobotTestCase,
    build_suite,
    build_test_case,
)

_CONFIG_DIR = Path(__file__).parents[2] / "configs" / "windows"


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_env(**kwargs: object) -> Environment:
    defaults: dict[str, object] = dict(
        id="win10", template="win10-tpl", snapshot="automation",
        platform="vsphere", executor="powershell", tags=["REG1"],
        run_tests=["t1"],
    )
    defaults.update(kwargs)
    return Environment(**defaults)  # type: ignore[arg-type]


def _make_config(
    steps: list[Step] | None = None,
    assert_: list[AssertItem] | None = None,
    setup: list[str] | None = None,
    teardown: list[str] | None = None,
    vars: dict[str, str] | None = None,
    env: Environment | None = None,
) -> tuple[ProductConfig, Environment]:
    if env is None:
        env = _make_env()
    test = TestCaseSpec(
        id="t1",
        steps=[Step(run="Get-Item <path>", capture_as="output")] if steps is None else steps,
        assert_=[AssertItem(path="result.code", equals=0)] if assert_ is None else assert_,
        setup=setup or [],
        teardown=teardown or [],
    )
    config = ProductConfig(
        product=Product(id="my-app", name="My App"),
        vars={"path": "C:/foo", **(vars or {})},
        environments=[env],
        tests=[test],
    )
    return config, env


# ── TestBuildTestCase ─────────────────────────────────────────────────────────

class TestBuildTestCase:
    def test_vars_resolved_in_step(self) -> None:
        config, env = _make_config()
        tc = build_test_case(config, env, config.get_test("t1"))
        _, cmd = tc.step_lines[0]
        assert cmd == "Get-Item C:/foo"

    def test_capture_as_chains_into_next_step(self) -> None:
        steps = [
            Step(run="Get-Name <path>", capture_as="filename"),
            Step(run="Get-Item <path>/<filename>", capture_as="output"),
        ]
        config, env = _make_config(steps=steps)
        tc = build_test_case(config, env, config.get_test("t1"))
        _, cmd2 = tc.step_lines[1]
        assert cmd2 == "Get-Item C:/foo/${filename}"

    def test_setup_cmds_resolved(self) -> None:
        config, env = _make_config(setup=["New-Item <path>"])
        tc = build_test_case(config, env, config.get_test("t1"))
        assert tc.setup_cmds == ["New-Item C:/foo"]

    def test_teardown_cmds_resolved(self) -> None:
        config, env = _make_config(teardown=["Remove-Item <path>"])
        tc = build_test_case(config, env, config.get_test("t1"))
        assert tc.teardown_cmds == ["Remove-Item C:/foo"]

    def test_tags_are_env_tags_plus_product_id(self) -> None:
        config, env = _make_config()
        tc = build_test_case(config, env, config.get_test("t1"))
        assert tc.tags == ["REG1", "my-app"]

    def test_name_format(self) -> None:
        config, env = _make_config()
        tc = build_test_case(config, env, config.get_test("t1"))
        assert tc.name == "my-app :: win10 :: t1"

    def test_assert_items_preserved(self) -> None:
        items = [AssertItem(path="result.code", equals=0), AssertItem(path="result.ok", equals=True)]
        config, env = _make_config(assert_=items)
        tc = build_test_case(config, env, config.get_test("t1"))
        assert len(tc.assert_items) == 2
        assert tc.assert_items[0].path == "result.code"

    def test_step_without_capture_gives_none(self) -> None:
        config, env = _make_config(steps=[Step(run="Do-Thing")])
        tc = build_test_case(config, env, config.get_test("t1"))
        capture_var, _ = tc.step_lines[0]
        assert capture_var is None


# ── TestBuildSuite ────────────────────────────────────────────────────────────

class TestBuildSuite:
    def test_suite_fields(self) -> None:
        config, env = _make_config()
        suite = build_suite(config, env)
        assert suite.product_id == "my-app"
        assert suite.env_id == "win10"
        assert suite.platform == "vsphere"
        assert suite.executor == "powershell"
        assert suite.template == "win10-tpl"
        assert suite.snapshot == "automation"

    def test_suite_test_cases_count(self) -> None:
        config, env = _make_config()
        suite = build_suite(config, env)
        assert len(suite.test_cases) == 1

    def test_unknown_test_id_raises(self) -> None:
        env = _make_env(run_tests=["missing"])
        t = TestCaseSpec(id="t1", steps=[Step(run="cmd")])
        config = ProductConfig(
            product=Product(id="p", name="P"), vars={},
            environments=[env], tests=[t],
        )
        with pytest.raises(KeyError, match="missing"):
            build_suite(config, env)


# ── TestRenderSuite ───────────────────────────────────────────────────────────

class TestRenderSuite:
    def _suite(self, **kwargs: object) -> object:
        config, env = _make_config(**kwargs)  # type: ignore[arg-type]
        return build_suite(config, env)

    def test_settings_section_present(self) -> None:
        assert "*** Settings ***" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_library_line_has_platform_and_executor(self) -> None:
        text = render_suite(self._suite())  # type: ignore[arg-type]
        assert "platform=vsphere" in text
        assert "executor=powershell" in text
        assert "VmForgeKeywords" in text

    def test_suite_setup_has_template_and_snapshot(self) -> None:
        assert "Clone VM    win10-tpl    automation" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_suite_teardown_present(self) -> None:
        assert "Suite Teardown    Teardown VM" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_test_cases_section_present(self) -> None:
        assert "*** Test Cases ***" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_test_case_name(self) -> None:
        assert "my-app :: win10 :: t1" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_tags_line(self) -> None:
        assert "[Tags]    REG1    my-app" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_setup_line_with_snapshot(self) -> None:
        assert "[Setup]    Revert Snapshot    automation" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_step_with_capture(self) -> None:
        assert "${output}=    Execute PS    Get-Item C:/foo" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_step_without_capture(self) -> None:
        config, env = _make_config(steps=[Step(run="Do-Thing <path>")], assert_=[])
        text = render_suite(build_suite(config, env))
        assert "    Execute PS    Do-Thing C:/foo" in text

    def test_check_field_assertion(self) -> None:
        assert "Check Field    ${output}    result.code    0" in render_suite(self._suite())  # type: ignore[arg-type]

    def test_equals_field_assertion(self) -> None:
        items = [AssertItem(path="result.sha256", equals_field="result.expected_sha256")]
        config, env = _make_config(steps=[Step(run="cmd", capture_as="output")], assert_=items)
        text = render_suite(build_suite(config, env))
        assert "Check Field    ${output}    result.sha256    =result.expected_sha256" in text

    def test_setup_cmd_before_steps(self) -> None:
        config, env = _make_config(setup=["New-Item <path>"])
        text = render_suite(build_suite(config, env))
        assert text.index("Execute PS    New-Item C:/foo") < text.index("${output}=")

    def test_single_teardown_cmd(self) -> None:
        config, env = _make_config(teardown=["Remove-Item <path>"])
        text = render_suite(build_suite(config, env))
        assert "[Teardown]    Execute PS    Remove-Item C:/foo" in text

    def test_multiple_teardown_cmds_use_run_keywords(self) -> None:
        config, env = _make_config(teardown=["Remove-Item <path>", "Clear-Cache"])
        text = render_suite(build_suite(config, env))
        assert "Run Keywords" in text
        assert "AND" in text
        assert "Remove-Item C:/foo" in text
        assert "Clear-Cache" in text

    def test_ssh_executor_uses_execute_ssh(self) -> None:
        env = _make_env(executor="ssh")
        config, _ = _make_config(env=env)
        text = render_suite(build_suite(config, env))
        assert "Execute SSH" in text
        assert "Execute PS" not in text

    def test_ends_with_newline(self) -> None:
        assert render_suite(self._suite()).endswith("\n")  # type: ignore[arg-type]

    def test_multiple_tests_separated_by_blank_line(self) -> None:
        env = _make_env(run_tests=["t1", "t2"])
        t1 = TestCaseSpec(id="t1", steps=[Step(run="cmd1")])
        t2 = TestCaseSpec(id="t2", steps=[Step(run="cmd2")])
        config = ProductConfig(
            product=Product(id="p", name="P"), vars={},
            environments=[env], tests=[t1, t2],
        )
        tc_section = render_suite(build_suite(config, env)).split("*** Test Cases ***")[1]
        assert "\n\n" in tc_section

    def test_assert_without_capture_raises(self) -> None:
        config, env = _make_config(
            steps=[Step(run="Do-Thing")],
            assert_=[AssertItem(path="result.code", equals=0)],
        )
        with pytest.raises(ValueError, match="no step uses capture_as"):
            render_suite(build_suite(config, env))

    def test_equals_true_renders_as_True(self) -> None:
        items = [AssertItem(path="result.ok", equals=True)]
        config, env = _make_config(assert_=items)
        text = render_suite(build_suite(config, env))
        assert "Check Field    ${output}    result.ok    True" in text

    def test_equals_false_renders_as_False(self) -> None:
        items = [AssertItem(path="result.ok", equals=False)]
        config, env = _make_config(assert_=items)
        text = render_suite(build_suite(config, env))
        assert "Check Field    ${output}    result.ok    False" in text


# ── TestSuiteFilename ─────────────────────────────────────────────────────────

class TestSuiteFilename:
    def test_filename_format(self) -> None:
        config, env = _make_config()
        assert suite_filename(build_suite(config, env)) == "my-app__win10.robot"


# ── TestGoldenOutput ─────────────────────────────────────────────────────────

_GOLDEN_7ZIP = (
    "*** Settings ***\n"
    "Library    vmforge.framework.robot.keywords.VmForgeKeywords"
    "    platform=vsphere    executor=powershell\n"
    "Suite Setup       Clone VM    windows-10-86    automation\n"
    "Suite Teardown    Teardown VM\n"
    "\n"
    "*** Test Cases ***\n"
    "7zip-x86 :: win10-x86 :: download-latest\n"
    '    [Tags]    REG1    7zip-x86\n'
    "    [Setup]    Revert Snapshot    automation\n"
    '    Execute PS    New-Item -ItemType Directory -Force -Path "C:/Users/Admin/Desktop/wrapper/latest"\n'
    '    ${output}=    Execute PS    & "C:/Users/Admin/Desktop/wrapper/test_auto_patching.exe"'
    " --sig 3112 --download 2 --architecture 32-bit\n"
    "    Check Field    ${output}    result.code    0\n"
    "    Check Field    ${output}    result.patch_id    12\n"
    "\n"
    "7zip-x86 :: win10-x86 :: install-patch\n"
    "    [Tags]    REG1    7zip-x86\n"
    "    [Setup]    Revert Snapshot    automation\n"
    '    ${filename}=    Execute PS    (Get-ChildItem -Path "C:/Users/Admin/Desktop/wrapper/latest"'
    " -Force -File | Select-Object -First 1).name\n"
    '    ${output}=    Execute PS    & "C:/Users/Admin/Desktop/wrapper/test_auto_patching.exe"'
    ' --install --path "C:/Users/Admin/Desktop/wrapper/latest/${filename}" --patch_id 12\n'
    "    Check Field    ${output}    result.code    1005\n"
    "    Check Field    ${output}    result.patch_id    12\n"
)


class TestGoldenOutput:
    def test_7zip_x86_golden(self) -> None:
        cfg = load(_CONFIG_DIR / "7zip_x86.json")
        suite = build_suite(cfg, cfg.environments[0])
        result = render_suite(suite)
        assert result == _GOLDEN_7ZIP, (
            "Generated .robot does not match golden.\n"
            f"--- got ---\n{result}\n--- expected ---\n{_GOLDEN_7ZIP}"
        )
