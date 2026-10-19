"""Durable cumulative admission for one continuation of the original pilot.

This module performs no HTTP requests. A lifetime lineage lock and a persistent
one-child claim prevent a fresh directory from resetting the original USD 15
authorization. Parent evidence is opened read-only and checked before dispatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from assay.contracts.episode import ModelUsage
from research.run_pilot import BudgetDenied, PilotStopped, UncertainCall

HARD_CAP = Decimal("15.00")
CLAIM_NAME = "development-comparison-lineage.claim.json"
LOCK_NAME = "development-comparison-lineage.lock"
PARENT_FILES = ("manifest.json", "manifest.sha256", "results.json", "budget.sqlite3")


def _encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class FrozenConfig:
    model: str = "gpt-5.4-mini-2026-03-17"
    endpoint: str = "https://api.openai.com/v1/responses"
    input_rate: Decimal = Decimal("0.75")
    output_rate: Decimal = Decimal("4.50")
    context: int = 400_000
    max_output: int = 2048
    actor_calls: int = 24
    oversight_calls: int = 6
    max_request: int = 120_000
    max_response: int = 2_097_152

    def __post_init__(self) -> None:
        for name in ("input_rate", "output_rate"):
            rate = getattr(self, name)
            if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
                raise ValueError("billing rates must be finite positive Decimals")
        for name in (
            "context",
            "max_output",
            "actor_calls",
            "oversight_calls",
            "max_request",
            "max_response",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError("resource limits must be positive integers")
        if self.context != 400_000:
            raise ValueError("admission reserves the entire 400000-token context")
        if not self.model or self.endpoint != "https://api.openai.com/v1/responses":
            raise ValueError("a model and the fixed HTTPS endpoint are required")

    def as_dict(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }

    def charge(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.input_rate + Decimal(output_tokens) * self.output_rate
        ) / 1_000_000


def _parent_digests(parent: Path) -> dict[str, str]:
    for suffix in ("-wal", "-journal"):
        pending = parent / ("budget.sqlite3" + suffix)
        if pending.exists() and pending.stat().st_size:
            raise PilotStopped("parent journal has uncheckpointed or active state")
    return {name: _sha((parent / name).read_bytes()) for name in PARENT_FILES}


def _read_parent(parent: Path) -> dict[str, Any]:
    """Reconcile immutable requests, responses, usage, and the saved parent summary."""

    before = _parent_digests(parent)
    manifest_raw = (parent / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    results = json.loads((parent / "results.json").read_bytes())
    manifest_sha = _sha(manifest_raw)
    if (
        (parent / "manifest.sha256").read_text(encoding="ascii").strip() != manifest_sha
        or results.get("manifest_sha256") != manifest_sha
        or results.get("complete") is not True
        or Decimal(manifest["cost_cap_usd"]) != HARD_CAP
    ):
        raise PilotStopped("parent manifest or completed-result binding is invalid")
    uri = "file:" + quote((parent / "budget.sqlite3").as_posix(), safe="/:") + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        cap = db.execute("SELECT value FROM config WHERE key='cap'").fetchone()
        if cap is None or Decimal(cap[0]) != HARD_CAP:
            raise PilotStopped("parent ledger must retain the original USD 15 cap")
        rows = db.execute(
            "SELECT model,request_sha256,request_json,status,actual_usd,input_tokens,"
            "output_tokens,response_json,max_input,max_output FROM calls"
        ).fetchall()
    cost = Decimal(0)
    input_total = output_total = 0
    input_rate = Decimal(manifest["input_price_per_million_usd"])
    output_rate = Decimal(manifest["output_price_per_million_usd"])
    for model, request_sha, request, status, actual, inputs, outputs, response, bound, out in rows:
        if status != "settled":
            raise UncertainCall("parent has unresolved calls; continuation is forbidden")
        if (
            type(inputs) is not int
            or type(outputs) is not int
            or not 0 < inputs <= bound
            or not 0 <= outputs <= out
            or bound != manifest["reservation_input_tokens"]
            or out != manifest["max_output_tokens"]
            or model != manifest["model"]
            or request_sha != _sha(request)
        ):
            raise PilotStopped("parent request or usage record is invalid")
        body = json.loads(response)
        if (
            body.get("model") != model
            or body.get("usage", {}).get("input_tokens") != inputs
            or body.get("usage", {}).get("output_tokens") != outputs
        ):
            raise PilotStopped("parent response differs from settled usage")
        expected = (Decimal(inputs) * input_rate + Decimal(outputs) * output_rate) / 1_000_000
        if not expected.is_finite() or Decimal(actual) != expected:
            raise PilotStopped("parent charge differs from conservative settlement")
        cost += expected
        input_total += inputs
        output_total += outputs
    summary = results["budget"]
    if (
        summary["call_count"] != len(rows)
        or Decimal(summary["settled_cost_upper_usd"]) != cost
        or Decimal(summary["committed_cost_upper_usd"]) != cost
        or Decimal(summary["unreconciled_reserved_usd"]) != 0
        or summary["halted_uncertain"] is not False
        or summary["input_tokens"] != input_total
        or summary["output_tokens"] != output_total
        or not 0 <= cost <= HARD_CAP
        or _parent_digests(parent) != before
    ):
        raise PilotStopped("parent ledger and saved result do not reconcile")
    return {
        "directory": str(parent),
        "digests": before,
        "call_count": len(rows),
        "cost_upper_usd": str(cost),
        "input_tokens": input_total,
        "output_tokens": output_total,
    }


class CumulativeJournal:
    """One child ledger, bound to one frozen manifest and immutable parent spend.

    Hold this object for the entire run. ``close`` releases its exclusive lineage
    lock but retains the claim. A stale lock requires explicit inspection; it is
    never silently removed. Reopening the exact claimed child remains possible.
    """

    def __init__(
        self,
        path: Path,
        parent_dir: Path,
        manifest_sha256: str,
        config: FrozenConfig,
    ):
        if re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None:
            raise ValueError("manifest_sha256 must be a SHA256 hex digest")
        self.path, self.parent_dir = path.resolve(), parent_dir.resolve()
        if self.path.is_relative_to(self.parent_dir):
            raise ValueError("child ledger must not modify the immutable parent directory")
        self.config, self.manifest_sha256 = config, manifest_sha256
        self.call_lock = threading.Lock()
        self._db_lock = threading.RLock()
        self._closed = False
        self._lock_path = self.parent_dir.parent / LOCK_NAME
        self._descriptor = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self.db: sqlite3.Connection | None = None
        try:
            os.write(
                self._descriptor,
                _encoded(
                    {
                        "pid": os.getpid(),
                        "journal": str(self.path),
                        "manifest_sha256": manifest_sha256,
                    }
                ),
            )
            os.fsync(self._descriptor)
            self.parent = _read_parent(self.parent_dir)
            claim_path = self.parent_dir.parent / CLAIM_NAME
            identity = {
                "journal": str(self.path),
                "manifest_sha256": manifest_sha256,
                "parent": self.parent,
                "config": config.as_dict(),
                "cap_usd": str(HARD_CAP),
            }
            existing = claim_path.exists()
            if existing:
                claim = json.loads(claim_path.read_bytes())
                if {key: claim.get(key) for key in identity} != identity:
                    raise PilotStopped(
                        "lineage already claimed by a different child or configuration"
                    )
                if not self.path.is_file():
                    raise PilotStopped("claimed child journal is missing; refusing spending reset")
            else:
                if self.path.exists():
                    raise PilotStopped("an unclaimed existing child ledger cannot be adopted")
                claim = identity | {"lineage_id": "lineage-" + uuid4().hex}
                with claim_path.open("xb") as stream:
                    stream.write(_encoded(claim))
                    stream.flush()
                    os.fsync(stream.fileno())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA journal_mode=DELETE")
            expected_config = {
                "identity": _encoded(identity).decode(),
                "lineage_id": claim["lineage_id"],
            }
            if existing:
                try:
                    stored = dict(self.db.execute("SELECT key,value FROM config").fetchall())
                except sqlite3.Error as exc:
                    raise PilotStopped("claimed child ledger has no intact identity") from exc
                if stored != expected_config:
                    raise PilotStopped(
                        "child ledger identity differs from its durable lineage claim"
                    )
            else:
                self.db.executescript(
                    "CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                    "CREATE TABLE calls ("
                    "call_id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, role TEXT NOT NULL,"
                    "model TEXT NOT NULL, request_sha256 TEXT NOT NULL, request_json BLOB NOT NULL,"
                    "reserved_usd TEXT NOT NULL, max_input INTEGER NOT NULL,"
                    "max_output INTEGER NOT NULL, status TEXT NOT NULL, actual_usd TEXT,"
                    "input_tokens INTEGER, output_tokens INTEGER,"
                    "response_json BLOB, error_category TEXT, created_at TEXT NOT NULL);"
                )
                with self.db:
                    self.db.executemany("INSERT INTO config VALUES (?,?)", expected_config.items())
            self._validate_child()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> CumulativeJournal:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            if self.db is not None:
                self.db.close()
            os.close(self._descriptor)
            self._lock_path.unlink()
            self._closed = True

    @property
    def halted(self) -> bool:
        with self._db_lock:
            assert self.db is not None
            return (
                self.db.execute(
                    "SELECT 1 FROM calls WHERE status IN ('reserved','uncertain') LIMIT 1"
                ).fetchone()
                is not None
            )

    def totals(self) -> dict[str, Any]:
        with self._db_lock:
            assert self.db is not None
            rows = self.db.execute(
                "SELECT status,reserved_usd,actual_usd,input_tokens,output_tokens FROM calls"
            ).fetchall()
            settled = sum((Decimal(row[2]) for row in rows if row[2] is not None), Decimal(0))
            pending = sum((Decimal(row[1]) for row in rows if row[0] != "settled"), Decimal(0))
            parent = Decimal(self.parent["cost_upper_usd"])
            committed = parent + settled + pending
            return {
                "call_count": len(rows),
                "cumulative_call_count": self.parent["call_count"] + len(rows),
                "parent_cost_upper_usd": str(parent),
                "child_settled_cost_upper_usd": str(settled),
                "child_unreconciled_reserved_usd": str(pending),
                "settled_cost_upper_usd": str(settled),
                "unreconciled_reserved_usd": str(pending),
                "committed_cost_upper_usd": str(committed),
                "cap_usd": str(HARD_CAP),
                "remaining_usd": str(HARD_CAP - committed),
                "input_tokens": sum(row[3] or 0 for row in rows),
                "output_tokens": sum(row[4] or 0 for row in rows),
                "halted_uncertain": self.halted,
            }

    def _validate_child(self) -> None:
        """Detect lost reservations or changed settlements before admitting new spend."""

        assert self.db is not None
        rows = self.db.execute(
            "SELECT episode_id,role,model,request_sha256,request_json,reserved_usd,"
            "max_input,max_output,status,actual_usd,input_tokens,output_tokens,response_json "
            "FROM calls"
        ).fetchall()
        role_counts: dict[tuple[str, str], int] = {}
        unresolved = 0
        expected_reservation = self.config.charge(self.config.context, self.config.max_output)
        for (
            episode,
            role,
            model,
            digest,
            request,
            reserve,
            bound,
            out,
            status,
            cost,
            ins,
            outs,
            body,
        ) in rows:
            request_body = json.loads(request)
            if (
                role not in ("analyst", "oversight")
                or not episode
                or model != self.config.model
                or digest != _sha(request)
                or request_body.get("model") != self.config.model
                or request_body.get("max_output_tokens") != self.config.max_output
                or bound != self.config.context
                or out != self.config.max_output
                or Decimal(reserve) != expected_reservation
            ):
                raise PilotStopped("child request or reservation integrity failure")
            key = (episode, role)
            role_counts[key] = role_counts.get(key, 0) + 1
            limit = self.config.actor_calls if role == "analyst" else self.config.oversight_calls
            if role_counts[key] > limit:
                raise PilotStopped("child calls exceed the frozen shared role allowance")
            if status == "settled":
                response = json.loads(body)
                if (
                    type(ins) is not int
                    or type(outs) is not int
                    or not 0 < ins <= bound
                    or not 0 <= outs <= out
                    or response.get("model") != model
                    or response.get("usage", {}).get("input_tokens") != ins
                    or response.get("usage", {}).get("output_tokens") != outs
                    or Decimal(cost) != self.config.charge(ins, outs)
                ):
                    raise PilotStopped("child response or settlement integrity failure")
            elif status in ("reserved", "uncertain"):
                unresolved += 1
                if any(value is not None for value in (cost, ins, outs)):
                    raise PilotStopped("an unresolved child call has a partial settlement")
            else:
                raise PilotStopped("child call has an unknown billing status")
        if unresolved > 1 or Decimal(self.totals()["committed_cost_upper_usd"]) > HARD_CAP:
            raise PilotStopped("child ledger violates sequential cumulative admission")

    def reserve(self, episode_id: str, role: str, payload: bytes) -> str:
        with self._db_lock:
            assert self.db is not None
            if role not in ("analyst", "oversight"):
                raise ValueError("unknown budget role")
            if _parent_digests(self.parent_dir) != self.parent["digests"]:
                raise PilotStopped("immutable parent evidence changed; no dispatch")
            self._validate_child()
            if len(payload) > self.config.max_request:
                raise BudgetDenied("serialized_request_byte_limit")
            request = json.loads(payload)
            if (
                request.get("model") != self.config.model
                or type(request.get("max_output_tokens")) is not int
                or request["max_output_tokens"] != self.config.max_output
            ):
                raise PilotStopped("request differs from frozen model or output bound")
            if self.halted:
                raise UncertainCall("unsettled_call_prevents_dispatch")
            limit = self.config.actor_calls if role == "analyst" else self.config.oversight_calls
            rows = self.db.execute(
                "SELECT status,max_input,max_output,input_tokens,output_tokens FROM calls "
                "WHERE episode_id=? AND role=?",
                (episode_id, role),
            ).fetchall()
            if len(rows) >= limit:
                raise BudgetDenied("shared_role_call_limit")
            inputs = sum(row[3] if row[0] == "settled" else row[1] for row in rows)
            outputs = sum(row[4] if row[0] == "settled" else row[2] for row in rows)
            if inputs + self.config.context > limit * self.config.context:
                raise BudgetDenied("shared_role_input_token_limit")
            if outputs + self.config.max_output > limit * self.config.max_output:
                raise BudgetDenied("shared_role_output_token_limit")
            reservation = self.config.charge(self.config.context, self.config.max_output)
            if Decimal(self.totals()["committed_cost_upper_usd"]) + reservation > HARD_CAP:
                raise BudgetDenied("cumulative_experiment_dollar_cap")
            call_id = "comparison-call-" + uuid4().hex
            with self.db:
                self.db.execute(
                    "INSERT INTO calls (call_id,episode_id,role,model,request_sha256,request_json,"
                    "reserved_usd,max_input,max_output,status,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        call_id,
                        episode_id,
                        role,
                        self.config.model,
                        _sha(payload),
                        payload,
                        str(reservation),
                        self.config.context,
                        self.config.max_output,
                        "reserved",
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return call_id

    def uncertain(self, call_id: str, category: str) -> None:
        with self._db_lock:
            assert self.db is not None
            with self.db:
                self.db.execute(
                    "UPDATE calls SET status='uncertain',error_category=? WHERE call_id=? "
                    "AND status='reserved'",
                    (category[:128], call_id),
                )

    def settle(self, call_id: str, response: dict[str, Any]) -> ModelUsage:
        try:
            usage = response["usage"]
            inputs, outputs = usage["input_tokens"], usage["output_tokens"]
            if (
                type(inputs) is not int
                or type(outputs) is not int
                or not 0 < inputs <= self.config.context
                or not 0 <= outputs <= self.config.max_output
                or response.get("model") != self.config.model
            ):
                raise ValueError("invalid usage or model")
        except (KeyError, TypeError, ValueError) as exc:
            with self._db_lock:
                assert self.db is not None
                with self.db:
                    self.db.execute(
                        "UPDATE calls SET status='uncertain',error_category=?,response_json=? "
                        "WHERE call_id=? AND status='reserved'",
                        ("invalid_or_missing_usage", _encoded(response), call_id),
                    )
            raise UncertainCall("invalid_or_missing_usage") from exc
        with self._db_lock:
            assert self.db is not None
            with self.db:
                changed = self.db.execute(
                    "UPDATE calls SET status='settled',actual_usd=?,input_tokens=?,output_tokens=?,"
                    "response_json=? WHERE call_id=? AND status='reserved'",
                    (
                        str(self.config.charge(inputs, outputs)),
                        inputs,
                        outputs,
                        _encoded(response),
                        call_id,
                    ),
                ).rowcount
                if changed != 1:
                    raise PilotStopped("call settlement must occur exactly once")
        return ModelUsage(input_tokens=inputs, output_tokens=outputs)
