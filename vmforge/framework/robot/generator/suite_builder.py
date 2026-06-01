from __future__ import annotations

from dataclasses import dataclass

from ...core.schema.models import AssertItem, Environment, ProductConfig, TestCaseSpec
from ...core.schema.resolver import resolve

__all__ = ["RobotSuite", "RobotTestCase", "build_suite", "build_test_case"]


@dataclass
class RobotTestCase:
    name: str
    tags: list[str]
    setup_cmds: list[str]                       # resolved setup commands
    step_lines: list[tuple[str | None, str]]    # (capture_var | None, resolved_cmd)
    assert_items: list[AssertItem]
    teardown_cmds: list[str]                    # resolved teardown commands


@dataclass
class RobotSuite:
    """One .robot file — one product x one environment."""
    product_id: str
    env_id: str
    platform: str
    executor: str
    template: str
    snapshot: str
    test_cases: list[RobotTestCase]


def build_test_case(config: ProductConfig, env: Environment, test: TestCaseSpec) -> RobotTestCase:
    ctx = config.build_var_context(env)
    captured: dict[str, str] = {}
    step_lines: list[tuple[str | None, str]] = []

    for step in test.steps:
        cmd = resolve(step.run, {**ctx, **captured})
        step_lines.append((step.capture_as, cmd))
        if step.capture_as:
            # Make the captured variable available as a RF variable for subsequent steps
            captured[step.capture_as] = f"${{{step.capture_as}}}"

    return RobotTestCase(
        name=f"{config.product.id} :: {env.id} :: {test.id}",
        tags=env.tags + [config.product.id],
        setup_cmds=[resolve(cmd, ctx) for cmd in test.setup],
        step_lines=step_lines,
        assert_items=list(test.assert_),
        teardown_cmds=[resolve(cmd, ctx) for cmd in test.teardown],
    )


def build_suite(config: ProductConfig, env: Environment) -> RobotSuite:
    return RobotSuite(
        product_id=config.product.id,
        env_id=env.id,
        platform=env.platform,
        executor=env.executor,
        template=env.template,
        snapshot=env.snapshot,
        test_cases=[
            build_test_case(config, env, config.get_test(t)) for t in env.run_tests
        ],
    )
