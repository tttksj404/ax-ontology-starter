import math
from collections import Counter
from itertools import pairwise

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Contract, Identifier


class ProcessEvent(Contract):
    case_id: Identifier
    step_id: Identifier
    owner: Identifier
    received_at: AwareDatetime
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def ordered_times(self) -> "ProcessEvent":
        if not self.received_at <= self.started_at <= self.completed_at:
            raise PydanticCustomError("event_time_order", "접수·착수·완료 시각의 순서 오류")
        return self


class ProcessLog(Contract):
    source: str
    synthetic: bool
    events: tuple[ProcessEvent, ...] = Field(min_length=1, max_length=10_000)


class StageMetrics(Contract):
    step_id: str
    observations: int
    median_work_minutes: float
    p90_work_minutes: float
    median_wait_minutes: float
    wait_share: float
    repeated_visits: int


class ProcessMetrics(Contract):
    source: str
    synthetic: bool
    case_count: int
    event_count: int
    median_lead_minutes: float
    p90_lead_minutes: float
    handoff_count: int
    stages: tuple[StageMetrics, ...]
    bottleneck_step: str


def percentile(values: tuple[float, ...], proportion: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    low, high = math.floor(position), math.ceil(position)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 3)


def process_metrics(log: ProcessLog) -> ProcessMetrics:
    stages: list[StageMetrics] = []
    for key in sorted({event.step_id for event in log.events}):
        events = tuple(event for event in log.events if event.step_id == key)
        work = tuple(
            (event.completed_at - event.started_at).total_seconds() / 60 for event in events
        )
        waiting = tuple(
            (event.started_at - event.received_at).total_seconds() / 60 for event in events
        )
        denominator = sum(work) + sum(waiting)
        counts = Counter(event.case_id for event in events)
        stages.append(
            StageMetrics(
                step_id=key,
                observations=len(events),
                median_work_minutes=percentile(work, 0.5),
                p90_work_minutes=percentile(work, 0.9),
                median_wait_minutes=percentile(waiting, 0.5),
                wait_share=round(sum(waiting) / denominator, 4) if denominator else 0,
                repeated_visits=sum(count - 1 for count in counts.values()),
            )
        )
    leads: list[float] = []
    handoffs = 0
    for case in sorted({event.case_id for event in log.events}):
        events = sorted(
            (event for event in log.events if event.case_id == case),
            key=lambda event: event.started_at,
        )
        leads.append(
            (
                max(event.completed_at for event in events)
                - min(event.received_at for event in events)
            ).total_seconds()
            / 60
        )
        handoffs += sum(before.owner != after.owner for before, after in pairwise(events))
    bottleneck = max(
        stages,
        key=lambda stage: (stage.median_wait_minutes, stage.median_work_minutes, stage.step_id),
    ).step_id
    return ProcessMetrics(
        source=log.source,
        synthetic=log.synthetic,
        case_count=len(leads),
        event_count=len(log.events),
        median_lead_minutes=percentile(tuple(leads), 0.5),
        p90_lead_minutes=percentile(tuple(leads), 0.9),
        handoff_count=handoffs,
        stages=tuple(stages),
        bottleneck_step=bottleneck,
    )
