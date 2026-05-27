from typing import Any
from pydantic import BaseModel, Field, model_validator


class Step(BaseModel):
    run: str
    capture_as: str | None = None


class AssertItem(BaseModel):
    path: str
    equals: Any | None = None
    equals_field: str | None = None

    @model_validator(mode="after")
    def _require_check(self) -> "AssertItem":
        if self.equals is None and self.equals_field is None:
            raise ValueError("AssertItem must set either 'equals' or 'equals_field'")
        return self


class TestCaseSpec(BaseModel):
    id: str
    name: str = ""
    setup: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    assert_: list[AssertItem] = Field(default_factory=list, alias="assert")
    teardown: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# Public alias — callers use TestCase; TestCaseSpec avoids pytest collection warning
TestCase = TestCaseSpec


class Environment(BaseModel):
    id: str
    template: str
    snapshot: str = "automation"
    platform: str
    executor: str
    tags: list[str] = Field(default_factory=list)
    vars: dict[str, Any] = Field(default_factory=dict)
    run_tests: list[str]


class Product(BaseModel):
    id: str
    name: str
    signature: int | None = None


class ProductConfig(BaseModel):
    product: Product
    vars: dict[str, Any] = Field(default_factory=dict)
    environments: list[Environment]
    tests: list[TestCaseSpec]

    def get_test(self, test_id: str) -> TestCaseSpec:
        result = next((t for t in self.tests if t.id == test_id), None)
        if result is None:
            raise KeyError(f"No test with id {test_id!r}")
        return result

    def build_var_context(self, env: "Environment") -> dict[str, str]:
        # None values are excluded — a var explicitly set to null in JSON is ignored
        ctx: dict[str, Any] = {}
        ctx.update(self.product.model_dump())
        ctx.update(self.vars)
        ctx.update(env.vars)
        return {k: str(v) for k, v in ctx.items() if v is not None}
