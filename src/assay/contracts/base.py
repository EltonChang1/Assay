"""Shared versioning, exact numbers, and canonical public serialization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class VersionedModel(BaseModel):
    """Records are immutable, including their tuple-valued collections."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)
    schema_version: Literal["1.0"] = "1.0"


def exact_decimal(value: Any) -> Any:
    if isinstance(value, (float, bool)):
        raise ValueError("use a decimal string, Decimal, or integer, never a float")
    if isinstance(value, str) and len(value) > 128:
        raise ValueError("decimal text is too long")
    if isinstance(value, int) and value.bit_length() > 100:
        raise ValueError("decimal magnitude exceeds the supported range")
    if not isinstance(value, (Decimal, str, int)):
        raise ValueError("decimal values require Decimal, string, or integer input")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc
    if not number.is_finite():
        raise ValueError("decimal values must be finite")
    exponent = number.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -6 or exponent > 24:
        raise ValueError("decimal scale exceeds the supported range")
    if number.adjusted() > 23 or len(number.as_tuple().digits) > 30:
        raise ValueError("decimal precision or magnitude exceeds the supported range")
    return number


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must have an explicit UTC offset")
    return value.astimezone(UTC)


def canonical_json_bytes(model: BaseModel) -> bytes:
    """UTF-8, sorted keys, compact JSON, exact Decimal strings, one final LF."""

    return (
        json.dumps(
            model.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
