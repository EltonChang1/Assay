# TraceFrame Safety Lab

**Development foundation — implementation started October 16, 2026.**

The package/CLI, public task and claim contracts, deterministic synthetic sales data, independent development scorer, SQL policy, and transactional execution evidence store are implemented. The first regression harness distinguishes the correct **USD 200.00** total from the duplicated-join **USD 340.00** result, and rejects the `SUM(DISTINCT amount)` shortcut when two orders have the same value.

TraceFrame Safety Lab is an AI safety research and systems engineering project investigating whether executable checks and data provenance reduce unsupported conclusions released by an AI data analyst.

The Docker worker and gateway are implemented. The Phase 2 enabled run passed **311 tests**, including **28 real Docker boundary cases**; [saved validation evidence](docs/validation/docker-validation.json) records the image, source hashes, and checked boundaries. Phase 3 adds claim-to-cell verification, public-contract checks, a typed-slot renderer, the single fenced publisher with source-epoch invalidation, and an isolated TraceFrame researcher-audit export ([ADR 0003](docs/ADR-0003-publication.md)). **365 offline tests** pass; the Docker suite awaits a re-run on the current tree. Model integrations and research experiments remain planned work. No model calls or charges are incurred by the implemented commands.

## Run the foundation

Install Python 3.12 and uv, then run from this checkout:

```text
uv sync --locked
uv run --locked safety-lab doctor
uv run --locked safety-lab milestone
uv run --locked pytest
```

`milestone` runs the repository-only private evaluator in a separate process. It reports independent numerical scoring of ten fixed SQL regressions; it does not test untrusted execution or release reports. The evaluator is excluded from the runtime wheel. The local developer checkout and builder functions are trusted and are not a private-evaluator isolation boundary.

Generate an allowlisted public bundle containing the task contract, CSV tables, and hashed manifest:

```text
uv run --locked safety-lab dataset build
uv run --locked safety-lab dataset validate --manifest <public_bundle>/manifest.json
uv run --locked safety-lab spec validate --manifest experiment_specs/development.json
```

The build command prints its actual output path. Its default is under `%LOCALAPPDATA%/TraceFrameSafetyLab/datasets` on Windows and `$XDG_STATE_HOME/TraceFrameSafetyLab/datasets` (or `~/.local/state/TraceFrameSafetyLab/datasets`) on Linux. Use `--output <new-directory>`, `--seed <nonnegative-integer>`, or `--variant equal_amount|insufficient|historical` for another development fixture. Existing bundle directories are never overwritten. The public bundle contains no oracle answers, canonical private events, seeds, or diagnostic labels. Private development truth can be saved separately through the builder API, outside a public bundle.

`SAFETY_LAB_STATE_DIR` overrides the live-state root with an absolute local path; paths inside the source workspace or OneDrive are rejected. The diagnostic command checks setup without creating a database, printing credentials, or calling a model. `doctor --require-docker` additionally requires a running Linux engine. With the pinned image available, `doctor` reports Docker and worker readiness; it explicitly leaves isolation validation unassessed. Local provisioning, Windows-to-Linux input mounting, and separate container boundary tests have passed; see [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Container execution development

With a working local Linux Docker engine, build the pinned worker from this **source checkout**, then exercise provisioning:

```text
uv run --locked safety-lab worker build
uv run --locked safety-lab worker smoke
uv run --locked safety-lab query --manifest <public_bundle>/manifest.json --sql "SELECT SUM(amount_minor * 0.01) AS revenue_usd FROM orders"
uv run --locked safety-lab receipt --id <execution_id>
```

These commands fail when the worker is unavailable and never execute analyst SQL on the host. The image build uses an allowlisted staging directory containing only the worker, shared SQL policy, Dockerfile, and hash-pinned dependencies. Runtime dispatch uses its immutable local image ID, a read-only frozen public input mount, disabled network, a non-root user, resource limits, and bounded output capture. Private evaluator code, the checkout, state database, and Docker socket are not mounted. The opt-in [Docker boundary suite](tests/test_sandbox_integration.py) has passed useful and denied queries, resource exhaustion, isolation, output overflow, and timeout/cancellation cleanup on this local engine.

Receipts preserve the exact query/hash, normalized query, snapshot manifest hash, worker image ID, timing, outcome, full canonical result hash, and explicit preview truncation. Complete bounded typed JSON results and receipt metadata commit atomically to local SQLite; public CSV snapshots are retained separately under the evidence directory. The first format is JSON, with Arrow/Parquet deferred until needed. Reports cannot be published by these development commands. See [the SQL subset](docs/SQL_POLICY.md) and [execution decisions](docs/ADR-0002-execution.md).

## Development checks

```text
uv sync --locked --extra traceframe
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv build --no-sources
```

The optional `traceframe` extra installs the exact pinned upstream commit for the researcher-audit export tests. Without it, those tests skip; set `SAFETY_LAB_TRACEFRAME_TESTS=1` (as CI does) to make a missing extra fail instead.

The CI workflow runs the foundation checks on Windows and Linux. CI has been configured; a remote CI run is not claimed by local validation. Exact Python dependencies and artifact hashes are recorded in `uv.lock`. See the [dependency inventory](docs/DEPENDENCIES.md), [charter](docs/CHARTER.md), [architecture decision](docs/ADR-0001-foundation.md), and [security boundaries](SECURITY.md).

## Plan and research scope

Start with [the end-to-end implementation plan](IMPLEMENTATION_PLAN.md). Use [the implementation backlog](IMPLEMENTATION_BACKLOG.md) to execute it and [the reuse notes](REUSE_NOTES.md) to integrate existing TraceFrame and AMOS work accurately.

The plan covers research hypotheses, architecture, threat boundaries, schemas, data generation, independent scoring, five comparison methods, cost controls, tests, UI, operations, release, and a worked first milestone. The backlog contains 60 implementation tickets and 8 later extensions, with dependencies and acceptance evidence. Current implementation progress is tracked separately from the historical planning review.

See [the planning review](PLAN_REVIEW.md) for resolved findings and validation checks.

The first release targets synthetic tabular data, isolated SQL execution, structured quantitative claims, evidence-aware oversight, a controlled publication path, and an independent evaluator. It compares ordinary mistakes, prompt injection, and prompted sabotage while reporting useful completion and cost alongside incorrect releases.

Planning envelope: 300–420 hours including contingency, approximately 12–17 weeks at 25 hours per week. Exact model choices, spending limits, and final sample size are resolved through the development pilot before confirmation.

The existing TraceFrame and AMOS repositories have not been modified. TraceFrame is used only as a pinned optional dependency for researcher-audit export; AMOS is not integrated. These deterministic development checks are not model performance or safety study results.
