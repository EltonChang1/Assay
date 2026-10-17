"""Crash, concurrency, and retry behavior around the single release transaction."""

import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from phase3_support import CORRECT_SQL, make_lab
from test_publication import SOURCE, setup, submit, through_decision

from assay.evidence import EvidenceStore
from assay.publication import (
    FencingError,
    InvalidTransitionError,
    Publisher,
    StaleSourceError,
)

ROOT = Path(__file__).resolve().parents[1]


def race(*calls):
    """Start calls together on separate store connections; return outcomes."""

    barrier = threading.Barrier(len(calls))
    outcomes: list[object] = [None] * len(calls)

    def run(index, call):
        barrier.wait()
        try:
            outcomes[index] = call()
        except Exception as exc:
            outcomes[index] = exc

    threads = [threading.Thread(target=run, args=item) for item in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    return outcomes


def fresh(lab):
    return Publisher(EvidenceStore(lab.state / "evidence"))


def release_rows(lab):
    with sqlite3.connect(lab.evidence.database_path) as connection:
        return connection.execute(
            "SELECT release_id, validity, source_epoch FROM releases ORDER BY release_id"
        ).fetchall()


def test_concurrent_publishers_create_exactly_one_release(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    outcomes = race(*(lambda: fresh(lab).publish(lease, report.revision_id) for _ in range(4)))
    assert all(not isinstance(item, Exception) for item in outcomes), outcomes
    assert len({item.release_id for item in outcomes}) == 1
    assert len(release_rows(lab)) == 1
    events = [event.event_type for event in lab.evidence.get_events()]
    assert events.count("report.published") == 1


def test_concurrent_checks_and_decisions_bind_once(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report = submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    checks = race(*(lambda: fresh(lab).check_report(lease, report.revision_id) for _ in range(3)))
    assert sum(not isinstance(item, Exception) for item in checks) == 1
    assert all(
        isinstance(item, InvalidTransitionError) for item in checks if isinstance(item, Exception)
    )
    decisions = race(
        lambda: fresh(lab).decide(lease, report.revision_id, "checked"),
        lambda: fresh(lab).decide(lease, report.revision_id, "baseline"),
    )
    assert sum(not isinstance(item, Exception) for item in decisions) == 1
    with sqlite3.connect(lab.evidence.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1


@pytest.mark.parametrize("attempt", range(6))
def test_publication_and_source_update_race_never_leaves_old_epoch_current(
    tmp_path, monkeypatch, attempt
):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    update = make_lab(tmp_path / "update", monkeypatch, seed=attempt + 1)
    publish, register = race(
        lambda: fresh(lab).publish(lease, report.revision_id),
        lambda: fresh(lab).register_source(SOURCE, update.snapshot),
    )
    assert register == 2
    rows = release_rows(lab)
    if isinstance(publish, Exception):
        assert isinstance(publish, (InvalidTransitionError, StaleSourceError))
        assert rows == []
    else:
        assert rows == [(publish.release_id, "stale", 1)]
    assert publisher.read_current("report-q1") is None


@pytest.mark.parametrize("attempt", range(4))
def test_cancellation_and_publication_race_is_ordered(tmp_path, monkeypatch, attempt):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    publish, cancel = race(
        lambda: fresh(lab).publish(lease, report.revision_id),
        lambda: fresh(lab).cancel_attempt(lease),
    )
    assert cancel is None
    events = [event.event_type for event in lab.evidence.get_events()]
    if isinstance(publish, Exception):
        assert isinstance(publish, FencingError)
        assert release_rows(lab) == [] and "report.published" not in events
    else:
        assert events.index("report.published") < events.index("attempt.canceled")
    with pytest.raises(FencingError):
        publisher.publish(lease, report.revision_id)


def test_failure_inside_release_transaction_exposes_nothing_and_retry_succeeds(
    tmp_path, monkeypatch
):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    with sqlite3.connect(lab.evidence.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER interrupt_release BEFORE INSERT ON evidence_events "
            "WHEN NEW.event_type = 'report.published' "
            "BEGIN SELECT RAISE(ABORT, 'simulated crash before commit'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated crash"):
        publisher.publish(lease, report.revision_id)
    assert release_rows(lab) == []
    assert publisher.revision_status(report.revision_id) == "approved"
    assert publisher.read_current("report-q1") is None
    assert lab.evidence.get_blob(report.rendered_sha256)
    with sqlite3.connect(lab.evidence.database_path) as connection:
        connection.execute("DROP TRIGGER interrupt_release")
    release = publisher.publish(lease, report.revision_id)
    assert publisher.read_current("report-q1").record == release
    assert len(release_rows(lab)) == 1


KILL_DURING_PUBLISH = """
import os, sys
from assay.evidence import EvidenceStore
from assay.publication import AttemptLease, Publisher

store = EvidenceStore(sys.argv[1])
original = store._record_event

def record_then_die(connection, event_type, *args, **kwargs):
    if event_type == "report.published":
        os._exit(9)
    return original(connection, event_type, *args, **kwargs)

store._record_event = record_then_die
lease = AttemptLease(sys.argv[2], sys.argv[3], int(sys.argv[4]))
Publisher(store).publish(lease, sys.argv[5])
"""


def test_process_killed_mid_publication_recovers_without_partial_release(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    killed = subprocess.run(
        [
            sys.executable,
            "-c",
            KILL_DURING_PUBLISH,
            str(lab.state / "evidence"),
            lease.run_id,
            lease.attempt_id,
            str(lease.fencing_token),
            report.revision_id,
        ],
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert killed.returncode == 9, killed.stderr.decode(errors="replace")
    recovered = fresh(lab)
    assert release_rows(lab) == []
    assert recovered.read_current("report-q1") is None
    assert recovered.revision_status(report.revision_id) == "approved"
    release = recovered.publish(lease, report.revision_id)
    assert recovered.publish(lease, report.revision_id) == release
    assert len(release_rows(lab)) == 1
