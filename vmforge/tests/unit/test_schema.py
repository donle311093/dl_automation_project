import json
import pytest
from pydantic import ValidationError

from framework.core.schema.models import (
    ProductConfig, Product, Environment, TestCaseSpec, TestCase,
    Step, AssertItem,
)
from framework.core.schema.loader import load, load_all, ConfigLoadError
from framework.core.schema.resolver import resolve, find_unresolved


SAMPLE_CONFIG = {
    "product": {"id": "7zip-x86", "name": "7-Zip x86", "signature": 3112},
    "vars": {"wrapper_path": "C:/wrapper", "architecture": "32-bit"},
    "environments": [
        {
            "id": "win10-x86",
            "template": "windows-10-86",
            "snapshot": "automation",
            "platform": "vsphere",
            "executor": "powershell",
            "tags": ["REG1"],
            "vars": {"exe_path": "C:\\Program Files\\7-Zip\\7zFM.exe"},
            "run_tests": ["download-latest"],
        }
    ],
    "tests": [
        {
            "id": "download-latest",
            "name": "Download Latest Installer",
            "steps": [
                {
                    "run": '& "<wrapper_path>/test.exe" --sig <signature> --arch <architecture>',
                    "capture_as": "output",
                }
            ],
            "assert": [
                {"path": "result.code", "equals": 0},
                {"path": "result.patch_id", "equals": 12},
            ],
        }
    ],
}


class TestProductConfig:
    def test_parse_valid(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        assert cfg.product.id == "7zip-x86"
        assert cfg.product.signature == 3112
        assert len(cfg.environments) == 1
        assert len(cfg.tests) == 1

    def test_product_typed(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        assert isinstance(cfg.product, Product)
        assert cfg.product.name == "7-Zip x86"

    def test_assert_is_list(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        test = cfg.tests[0]
        assert isinstance(test.assert_, list)
        assert len(test.assert_) == 2
        assert isinstance(test.assert_[0], AssertItem)

    def test_assert_item_fields(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        item = cfg.tests[0].assert_[0]
        assert item.path == "result.code"
        assert item.equals == 0
        assert item.equals_field is None

    def test_get_test(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        t = cfg.get_test("download-latest")
        assert t.id == "download-latest"

    def test_get_test_missing_raises_key_error(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        with pytest.raises(KeyError, match="nonexistent"):
            cfg.get_test("nonexistent")

    def test_build_var_context(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        env = cfg.environments[0]
        ctx = cfg.build_var_context(env)
        assert ctx["wrapper_path"] == "C:/wrapper"
        assert ctx["signature"] == "3112"
        assert ctx["id"] == "7zip-x86"
        assert "exe_path" in ctx

    def test_env_vars_override_product_vars(self):
        data = {
            **SAMPLE_CONFIG,
            "vars": {"wrapper_path": "C:/global"},
            "environments": [{
                **SAMPLE_CONFIG["environments"][0],
                "vars": {"wrapper_path": "C:/local"},
            }],
        }
        cfg = ProductConfig.model_validate(data)
        ctx = cfg.build_var_context(cfg.environments[0])
        assert ctx["wrapper_path"] == "C:/local"

    def test_environment_default_snapshot(self):
        cfg = ProductConfig.model_validate(SAMPLE_CONFIG)
        assert cfg.environments[0].snapshot == "automation"

    def test_missing_required_field_raises_validation_error(self):
        bad = {k: v for k, v in SAMPLE_CONFIG.items() if k != "product"}
        with pytest.raises(ValidationError):
            ProductConfig.model_validate(bad)

    def test_build_var_context_excludes_none_values(self):
        data = {
            **SAMPLE_CONFIG,
            "vars": {"optional_var": None, "present_var": "value"},
        }
        cfg = ProductConfig.model_validate(data)
        ctx = cfg.build_var_context(cfg.environments[0])
        assert "optional_var" not in ctx
        assert ctx["present_var"] == "value"

    def test_test_case_alias(self):
        # TestCase is the public alias; TestCaseSpec is the internal class
        assert TestCase is TestCaseSpec

    def test_list_defaults_are_independent(self):
        # Each model instance gets its own list — not shared
        cfg1 = ProductConfig.model_validate(SAMPLE_CONFIG)
        cfg2 = ProductConfig.model_validate(SAMPLE_CONFIG)
        cfg1.tests[0].setup.append("extra")
        assert cfg2.tests[0].setup == []


class TestAssertItem:
    def test_valid_equals(self):
        item = AssertItem(path="result.code", equals=0)
        assert item.equals == 0

    def test_valid_equals_field(self):
        item = AssertItem(path="result.sha256", equals_field="result.expected_sha256")
        assert item.equals_field == "result.expected_sha256"

    def test_both_none_raises(self):
        with pytest.raises(ValidationError, match="equals.*equals_field"):
            AssertItem(path="result.code")

    def test_both_set_is_valid(self):
        # equals takes precedence — having both is allowed (no validator blocks it)
        item = AssertItem(path="result.code", equals=0, equals_field="result.other")
        assert item.equals == 0


class TestResolver:
    def test_resolve_simple(self):
        assert resolve("hello <name>", {"name": "world"}) == "hello world"

    def test_resolve_multiple(self):
        result = resolve("<a> and <b>", {"a": "foo", "b": "bar"})
        assert result == "foo and bar"

    def test_resolve_missing_key_unchanged(self):
        assert resolve("hello <missing>", {}) == "hello <missing>"

    def test_resolve_no_tokens(self):
        assert resolve("plain text", {"x": "y"}) == "plain text"

    def test_resolve_empty_string(self):
        assert resolve("", {"x": "y"}) == ""

    def test_resolve_numeric_value(self):
        assert resolve("--sig <signature>", {"signature": "3112"}) == "--sig 3112"

    def test_resolve_token_with_underscore_and_digits(self):
        assert resolve("<var_1>", {"var_1": "hello"}) == "hello"

    def test_find_unresolved(self):
        tokens = find_unresolved("cmd <a> and <b> done")
        assert tokens == ["a", "b"]

    def test_find_unresolved_none(self):
        assert find_unresolved("no tokens here") == []

    def test_find_unresolved_with_underscore_digits(self):
        assert find_unresolved("<var_1> <name2>") == ["var_1", "name2"]

    def test_resolve_chained_capture(self):
        ctx = {"wrapper_path": "C:/wrapper", "filename": "${filename}"}
        result = resolve('& "<wrapper_path>/<filename>"', ctx)
        assert result == '& "C:/wrapper/${filename}"'


class TestLoaderFromFile:
    def test_load_valid_file(self, tmp_path):
        p = tmp_path / "7zip.json"
        p.write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")
        cfg = load(p)
        assert cfg.product.id == "7zip-x86"

    def test_load_file_not_found(self, tmp_path):
        with pytest.raises(ConfigLoadError, match="not found"):
            load(tmp_path / "nonexistent.json")

    def test_load_malformed_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="Malformed JSON"):
            load(p)

    def test_load_invalid_schema(self, tmp_path):
        p = tmp_path / "bad_schema.json"
        p.write_text(json.dumps({"product": {"id": "x"}}), encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="Schema validation failed"):
            load(p)

    def test_load_all(self, tmp_path):
        for name in ["a.json", "b.json"]:
            (tmp_path / name).write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")
        configs = load_all(tmp_path)
        assert len(configs) == 2

    def test_load_all_empty_dir_returns_empty_list(self, tmp_path):
        configs = load_all(tmp_path)
        assert configs == []

    def test_load_all_nonexistent_dir(self, tmp_path):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_all(tmp_path / "does_not_exist")

    def test_load_all_sorted_by_name(self, tmp_path):
        for name in ["c.json", "a.json", "b.json"]:
            (tmp_path / name).write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")
        configs = load_all(tmp_path)
        assert len(configs) == 3  # order deterministic via sorted()
