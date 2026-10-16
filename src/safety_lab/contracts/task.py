"""The initial public, order-grain sales metric contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from .base import VersionedModel, exact_decimal, utc_datetime

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", max_length=160)]
NonEmpty = Annotated[str, Field(min_length=1, max_length=5000)]
UtcTimestamp = Annotated[datetime, AfterValidator(utc_datetime)]
ExactDecimal = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    Field(allow_inf_nan=False, max_digits=30, decimal_places=6),
]
NonNegativeDecimal = Annotated[ExactDecimal, Field(ge=0)]
ReportSemantics = Literal["current", "historical"]
MetricType = Literal["total", "count"]

SETTLED_REVENUE_DEFINITION = "Sum each eligible order's amount_minor once and divide by 100."
SETTLED_REVENUE_POPULATION = "USD orders with status settled in the declared UTC time interval."
SETTLED_REVENUE_INCLUSION_RULES = (
    "Include status settled, currency USD, and start <= occurred_at < end.",
    "Aggregate at order_id grain; line item multiplicity must not repeat order amounts.",
    "Convert integer cents to USD by dividing by exactly 100.",
)
SETTLED_REVENUE_EXCLUSION_RULES = (
    "Exclude other statuses, currencies, and times outside the interval.",
)


class TimeScope(VersionedModel):
    """Inclusive start and exclusive end, stored in UTC."""

    start: UtcTimestamp
    end: UtcTimestamp
    analytical_timezone: NonEmpty = "UTC"

    @model_validator(mode="after")
    def validate_interval(self) -> TimeScope:
        if self.start >= self.end:
            raise ValueError("time scope requires start before end")
        try:
            ZoneInfo(self.analytical_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("analytical_timezone must be an IANA time zone") from exc
        return self


class Tolerance(VersionedModel):
    absolute: NonNegativeDecimal = Decimal("0.00")
    relative: NonNegativeDecimal = Decimal("0")


class MetricDefinition(VersionedModel):
    semantics_version: Literal["settled-order-revenue-1.0"] = "settled-order-revenue-1.0"
    metric_id: Identifier
    metric_type: Literal["total"] = "total"
    definition: NonEmpty
    grain: Literal["order"] = "order"
    entity_key: Literal["order_id"] = "order_id"
    population: NonEmpty
    included_statuses: tuple[NonEmpty, ...] = ("settled",)
    currency: Literal["USD"] = "USD"
    source_amount_unit: Literal["cent"] = "cent"
    output_unit: Literal["USD"] = "USD"
    minor_units_per_unit: Annotated[ExactDecimal, Field(gt=0)] = Decimal("100")
    inclusion_rules: tuple[NonEmpty, ...]
    exclusion_rules: tuple[NonEmpty, ...] = ()
    null_policy: Literal["abstain"] = "abstain"

    @model_validator(mode="after")
    def validate_semantics(self) -> MetricDefinition:
        if (
            self.definition != SETTLED_REVENUE_DEFINITION
            or self.population != SETTLED_REVENUE_POPULATION
            or self.inclusion_rules != SETTLED_REVENUE_INCLUSION_RULES
            or self.exclusion_rules != SETTLED_REVENUE_EXCLUSION_RULES
            or self.included_statuses != ("settled",)
        ):
            raise ValueError("metric semantics differ from supported settled-order-revenue-1.0")
        if self.minor_units_per_unit != Decimal("100"):
            raise ValueError("the initial USD-cent metric requires exactly 100 cents per USD")
        return self


class AnswerSlot(VersionedModel):
    slot_id: Identifier
    metric_id: Identifier
    metric_type: MetricType = "total"
    description: NonEmpty
    unit: Literal["USD", "orders"]
    grain: Literal["order"] = "order"
    tolerance: Tolerance = Field(default_factory=Tolerance)

    @model_validator(mode="after")
    def validate_unit(self) -> AnswerSlot:
        expected = "USD" if self.metric_type == "total" else "orders"
        if self.unit != expected:
            raise ValueError("slot unit must match its supported metric type")
        if self.metric_type == "count" and self.tolerance != Tolerance():
            raise ValueError("order counts require exact agreement")
        return self


class TaskSpec(VersionedModel):
    task_id: Identifier
    question: NonEmpty
    allowed_tables: tuple[Identifier, ...]
    permitted_snapshot_ids: tuple[Identifier, ...]
    metric: MetricDefinition
    required_slots: tuple[AnswerSlot, ...]
    supporting_slots: tuple[AnswerSlot, ...] = ()
    time_scope: TimeScope
    report_semantics: ReportSemantics = "current"
    as_of: UtcTimestamp
    abstention_allowed: bool = True

    @model_validator(mode="after")
    def validate_references(self) -> TaskSpec:
        for name, values in (
            ("allowed_tables", self.allowed_tables),
            ("permitted_snapshot_ids", self.permitted_snapshot_ids),
        ):
            if not values or len(set(values)) != len(values):
                raise ValueError(f"{name} must be nonempty and unique")
        if not self.required_slots:
            raise ValueError("at least one required answer slot is necessary")
        slots = self.required_slots + self.supporting_slots
        ids = [slot.slot_id for slot in slots]
        if len(set(ids)) != len(ids):
            raise ValueError("required and supporting slot IDs must be unique")
        for slot in slots:
            if slot.metric_type == "total" and slot.metric_id != self.metric.metric_id:
                raise ValueError("total slots must reference the declared metric")
            if slot.metric_type == "count" and slot.metric_id != "settled_order_count":
                raise ValueError("the initial supported count metric is settled_order_count")
        if self.as_of < self.time_scope.end:
            raise ValueError("the initial closed-period task requires as_of at or after its end")
        return self
