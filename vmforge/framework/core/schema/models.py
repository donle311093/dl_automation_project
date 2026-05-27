from typing import Any
from pydantic import BaseModel, Field


class Step(BaseModel):
    run: str
    capture_as: str | None = None


class AssertItem(BaseModel):
    path: str
    equals: Any | None = None
    equals_field: str | None = None


class TestCase(BaseModel):
    id: str
    name: str = ""
    setup: list[str] = []
    steps: list[Step] = []
    assert_: list[AssertItem] = Field(default_factory=list, alias="assert")
    teardown: list[str] = []

    model_config = {"populate_by_name": True}


class Environment(BaseModel):
    id: str
    template: str
    snapshot: str = "automation"
    platform: str
    executor: str
    tags: list[str] = []
    vars: dict[str, Any] = {}
    run_tests: list[str]


class Product(BaseModel):
    id: str
    name: str
    signature: int | None = None


class ProductConfig(BaseModel):
    product: Product
    vars: dict[str, Any] = {}
    environments: list[Environment]
    tests: list[TestCase]

    def get_test(self, test_id: str) -> TestCase:
        return next(t for t in self.tests if t.id == test_id)

    def build_var_context(self, env: Environment) -> dict[str, str]:
        ctx: dict = {}
        ctx.update(self.product.model_dump())
        ctx.update(self.vars)
        ctx.update(env.vars)
        return {k: str(v) for k, v in ctx.items() if v is not None}
