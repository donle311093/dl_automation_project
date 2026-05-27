from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class StepResult:
    command: str
    stdout: str
    exit_code: int
    capture_as: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class AssertResult:
    path: str
    expected: object
    actual: object
    passed: bool


@dataclass
class TestResult:
    test_id: str
    test_name: str
    status: Status
    step_results: list[StepResult] = field(default_factory=list)
    assert_results: list[AssertResult] = field(default_factory=list)
    error_message: str = ""


@dataclass
class SuiteResult:
    product_id: str
    env_id: str
    test_results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.test_results if t.status == Status.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.test_results if t.status == Status.FAIL)
