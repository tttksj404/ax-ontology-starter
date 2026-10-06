from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Contract, Identifier, Sensitivity


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceStatus(StrEnum):
    OBSERVED = "observed"
    DOCUMENTED = "documented"
    REPORTED = "reported"
    UNKNOWN = "unknown"


class DecisionImpact(StrEnum):
    ADMINISTRATIVE = "administrative"
    FINANCIAL = "financial"
    PERSONAL_RIGHTS = "personal_rights"
    SAFETY = "safety"
    UNKNOWN = "unknown"


class Step(Contract):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    inputs: tuple[str, ...] = Field(default=(), max_length=20)
    outputs: tuple[str, ...] = Field(default=(), max_length=20)
    systems: tuple[str, ...] = Field(default=(), max_length=20)
    rules: tuple[str, ...] = Field(default=(), max_length=30)
    exceptions: tuple[str, ...] = Field(default=(), max_length=30)
    evidence_sources: tuple[str, ...] = Field(default=(), max_length=20)
    depends_on: tuple[Identifier, ...] = Field(default=(), max_length=20)
    monthly_cases: int | None = Field(default=None, ge=0, le=10_000_000)
    minutes_per_case: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False)
    repetitive: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    digital_readiness: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    rule_clarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    exception_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    risk: Risk = Risk.CRITICAL
    sensitivity: Sensitivity = Sensitivity.RESTRICTED
    authorized: bool = False
    reversible: bool = False
    kpi: str | None = Field(default=None, min_length=1, max_length=200)
    evidence_status: SourceStatus = SourceStatus.UNKNOWN
    value_status: SourceStatus = SourceStatus.UNKNOWN
    control_point: bool = True
    decision_impact: DecisionImpact = DecisionImpact.UNKNOWN


class BusinessIntake(Contract):
    business: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=500)
    process_owner: str | None = Field(default=None, min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=120)
    constraints: tuple[str, ...] = Field(max_length=30)
    steps: tuple[Step, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_workflow(self) -> "BusinessIntake":
        by_id = {step.id: step for step in self.steps}
        if len(by_id) != len(self.steps):
            raise PydanticCustomError("duplicate_step", "단계 ID 중복")
        resolved: set[str] = set()
        while len(resolved) < len(by_id):
            ready = {key for key, step in by_id.items() if set(step.depends_on) <= resolved}
            pending = ready - resolved
            if not pending:
                raise PydanticCustomError("invalid_dependency", "업무 의존성 순환 또는 누락")
            resolved.update(pending)
        return self


class AutomationMode(StrEnum):
    DEFER = "defer"
    ASSIST = "assist"
    APPROVAL = "approval_required"
    AUTOMATE = "automate_candidate"


class StepAssessment(Contract):
    step_id: str
    mode: AutomationMode
    priority_score: float | None
    baseline_hours_monthly: float | None
    reasons: tuple[str, ...]
    next_steps: tuple[str, ...]


class Assessment(Contract):
    business: str
    heuristic_version: str = "ax-triage-v1"
    measured_roi: bool = False
    steps: tuple[StepAssessment, ...]
    control_points: tuple[str, ...] = ()
    process_warnings: tuple[str, ...] = ()
