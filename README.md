# Assay

**Research goal:** determine what evidence is sufficient to authorize an AI analyst's quantitative answer, from the mathematical metric contract to the exact released bytes.

Read the self-contained [technical research paper](research/paper.md) or its [PDF](output/pdf/assay-technical-report.pdf). The paper develops the analytical contract from first principles, presents the implemented system and observed results, and places the prospective comparison in a separate technical appendix.

The current prototype supports settled-order revenue and order count on synthetic data, restricted container SQL, authentic execution receipts, exact claim-to-cell binding, public semantic checks, ordinary/evidence review, bounded correction and revision-bound publication. The independent scorer distinguishes a correct **USD 200.00** total from an authentic duplicated-join **USD 340.00** result. Equal-value orders expose why `SUM(DISTINCT amount)` cannot repair entity multiplicity.

**Current evidence:** fresh October 19 offline validation passed **436 tests**, with 29 skips (28 Docker tests and one POSIX-only case), no failures/errors and four dependency warnings. Docker is unavailable in the current session; the saved October 18 enabled run passed 441 tests with one skip. All 80 source/configuration/test digests from that validation still match. The ten numerical regressions reproduce exactly. See the [repository review](research/REPOSITORY_REVIEW.md) and [machine-readable reconciliation](research/validation/repository-review.json).

The one executed paid development pilot had 24 assignments and 144 analyst calls, with USD 0.160803 in conservative recorded charges. Every assignment exhausted its model allowance before submitting a claim; reviewers were never called and nothing released. The recorded image cannot fetch timestamp previews because it omits a timezone dependency. These observations establish an engineering failure, with zero required-answer coverage, and no D/E safety effect. The general budget/recovery boundaries, private confirmation isolation, structural holdouts and confirmatory experiment remain unfinished. Ordinary setup, testing, paper builds and evidence audits make no paid calls; the dedicated pilot runner requires an explicit live invocation. No further paid run was made for this review.

The [literature review](research/literature/README.md) annotates 40 core papers. The [academic writing guide](research/ACADEMIC_WRITING.md), [submission outline](research/SUBMISSION_OUTLINE.md), and [official conference comparison](research/literature/conference-requirements.md) preserve the publication research and distinguish a technical report from a venue-formatted submission.

## Run the foundation

Install Python 3.12 and uv, then run from this checkout:

```text
uv sync --locked
uv run --locked assay doctor
uv run --locked assay milestone
uv run --locked pytest
```

`milestone` runs the repository-only private evaluator in a separate process. It reports independent numerical scoring of ten fixed SQL regressions; it does not test untrusted execution or release reports. The evaluator is excluded from the runtime wheel. The local developer checkout and builder functions are trusted and are not a private-evaluator isolation boundary.

Generate an allowlisted public bundle containing the task contract, CSV tables, and hashed manifest:

```text
uv run --locked assay dataset build
uv run --locked assay dataset validate --manifest <public_bundle>/manifest.json
uv run --locked assay spec validate --manifest experiment_specs/development.json
```

The build command prints its actual output path. Its default is under `%LOCALAPPDATA%/Assay/datasets` on Windows and `$XDG_STATE_HOME/Assay/datasets` (or `~/.local/state/Assay/datasets`) on Linux. Use `--output <new-directory>`, `--seed <nonnegative-integer>`, or `--variant equal_amount|insufficient|historical` for another development fixture. Existing bundle directories are never overwritten. The public bundle contains no oracle answers, canonical private events, seeds, or diagnostic labels. Private development truth can be saved separately through the builder API, outside a public bundle.

`ASSAY_STATE_DIR` overrides the live-state root with an absolute local path; paths inside the source workspace or OneDrive are rejected. The diagnostic command checks setup without creating a database, printing credentials, or calling a model. `doctor --require-docker` additionally requires a running Linux engine. With the pinned image available, `doctor` reports Docker and worker readiness; it explicitly leaves isolation validation unassessed. Local provisioning, Windows-to-Linux input mounting, and separate container boundary tests have passed; see [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Container execution development

With a working local Linux Docker engine, build the pinned worker from this **source checkout**, then exercise provisioning:

```text
uv run --locked assay worker build
uv run --locked assay worker smoke
uv run --locked assay query --manifest <public_bundle>/manifest.json --sql "SELECT SUM(amount_minor * 0.01) AS revenue_usd FROM orders"
uv run --locked assay receipt --id <execution_id>
```

These commands fail when the worker is unavailable and never execute analyst SQL on the host. The image build uses an allowlisted staging directory containing only the worker, shared SQL policy, Dockerfile, and hash-pinned dependencies. Runtime dispatch uses its immutable local image ID, a read-only frozen public input mount, disabled network, a non-root user, resource limits, and bounded output capture. Private evaluator code, the checkout, state database, and Docker socket are not mounted. The opt-in [Docker boundary suite](tests/test_sandbox_integration.py) has passed useful and denied queries, resource exhaustion, isolation, output overflow, and timeout/cancellation cleanup on this local engine.

Receipts preserve the exact query/hash, normalized query, snapshot manifest hash, worker image ID, timing, outcome, full canonical result hash, and explicit preview truncation. Complete bounded typed JSON results and receipt metadata commit atomically to local SQLite; public CSV snapshots are retained separately under the evidence directory. The first format is JSON, with Arrow/Parquet deferred until needed. Reports cannot be published by these development commands. See [the SQL subset](docs/SQL_POLICY.md) and [execution decisions](docs/ADR-0002-execution.md).

## Development checks

```text
uv sync --locked --extra traceframe --extra inspect
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv build --no-sources
```

The optional `traceframe` extra installs the exact pinned upstream commit for the researcher-audit export tests. The optional `inspect` extra installs Inspect for `InspectModelClient`; its tests use Inspect's offline mock provider. Without an extra, its tests skip; set `ASSAY_TRACEFRAME_TESTS=1` or `ASSAY_INSPECT_TESTS=1` (as CI does) to make a missing extra fail instead.

GitHub Actions runs the foundation checks on Windows and Linux, plus a separate Linux Docker job. The historical implementation-status record reports that at `92dec74` every job passed: the foundation checks on both systems (the 28 Docker cases skip there) and all 28 cases in the hosted Docker job. Earlier runs failed 11 Docker cases because the frozen input snapshot was owner-only, which Linux bind mounts enforce and Docker Desktop on Windows does not; see [implementation status](docs/IMPLEMENTATION_STATUS.md#remote-ci). Exact Python dependencies and artifact hashes are recorded in `uv.lock`. See the [dependency inventory](docs/DEPENDENCIES.md), [charter](docs/CHARTER.md), [architecture decision](docs/ADR-0001-foundation.md), and [security boundaries](SECURITY.md).

## Plan and research scope

Start with [the end-to-end implementation plan](IMPLEMENTATION_PLAN.md). Use [the implementation backlog](IMPLEMENTATION_BACKLOG.md) to execute it and [the reuse notes](REUSE_NOTES.md) to integrate existing TraceFrame and AMOS work accurately.

The plan covers research hypotheses, architecture, threat boundaries, schemas, data generation, independent scoring, five comparison methods, cost controls, tests, UI, operations, release, and a worked first milestone. The backlog contains 60 implementation tickets and 8 later extensions, with dependencies and acceptance evidence. Current implementation progress is tracked separately from the historical planning review.

See [the planning review](PLAN_REVIEW.md) for resolved findings and validation checks.

The first release targets synthetic tabular data, isolated SQL execution, structured quantitative claims, evidence-aware oversight, a controlled publication path, and an independent evaluator. It compares ordinary mistakes, prompt injection, and prompted sabotage while reporting useful completion and cost alongside incorrect releases.

Planning envelope: 300–420 hours including contingency, approximately 12–17 weeks at 25 hours per week. Exact model choices, spending limits, and final sample size are resolved through the development pilot before confirmation.

The existing TraceFrame and AMOS repositories have not been modified. TraceFrame is used only as a pinned optional dependency for researcher-audit export; AMOS is not integrated. These deterministic development checks are not model performance or safety study results.
