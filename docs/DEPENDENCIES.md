# Dependency and reuse inventory

Updated October 16, 2026. This inventory separates the initial foundation from planned integrations. It is not a complete software bill of materials or a compatibility/security certification. The committed [pyproject.toml](../pyproject.toml) declares dependency ranges; [uv.lock](../uv.lock) records exact resolved package pins. Dependency additions require matching inventory updates.

## Foundation

The initial environment uses Python **3.12.6** and uv **0.6.5**. Package support is Python `>=3.12,<3.13`. Exact pins below were read from the initial lockfile; the lockfile also records transitive packages and artifacts.

| Item | Role | Initial version / status |
|---|---|---|
| Pydantic | Public typed contracts and configuration | 2.14.1; runtime dependency. `pydantic-core` is pinned to 2.50.1. |
| tzdata | Portable IANA time-zone definitions, including Windows | 2026.5; runtime dependency. |
| sqlglot | DuckDB SQL parsing and bounded AST capability policy | 30.23.0; runtime dependency. Policy checks do not execute SQL or establish worker isolation. |
| DuckDB | Trusted regression tests and container-only analytical worker | 1.5.6; development dependency on host and separately hash-pinned in the worker image. No host analyst SQL executor. |
| Hypothesis | Property-based development checks | 6.170.0; development dependency. |
| mypy | Strict static checking | 1.20.2; development dependency. |
| pytest | Deterministic development checks | 8.4.2; development dependency. |
| Ruff | Formatting/lint | 0.17.1; development dependency. |
| Hatchling | Wheel build backend | 1.32.4; exact build-system requirement and locked development dependency. |

uv is environment tooling, not a Python runtime dependency. Docker client/server 29.8.2 use the local `desktop-linux` context; the Phase 2 validation used 28.0.4, and the latest run reproduced the same worker image ID on 29.8.2. The earlier unavailable-engine blocker is resolved: diagnostics, pinned worker builds, worker smoke, and all 28 real Docker boundary cases pass. Windows local state and public input path mapping have been exercised. [Saved validation evidence](validation/docker-validation.json) records the image, lockfile, and source hashes; [implementation status](IMPLEMENTATION_STATUS.md) states the tested scope and remaining work. In remote GitHub Actions CI, the foundation job resolves and installs the locked environment, including both optional extras, on Windows and Linux; after a snapshot-permission fix, the hosted Linux Docker job passes all 28 cases at `92dec74` ([remote CI](IMPLEMENTATION_STATUS.md#remote-ci)).

This milestone contains original lab work. No TraceFrame or AMOS implementation code has been copied or vendored. The lab's own distribution license is undecided; no upstream license is adopted by implication.

## Execution source and planned components

The worker/gateway and SQLite evidence storage are implemented with offline checks and genuine local container queries whose receipts and complete results round-trip through the evidence store. SQLite comes from the Python standard library. The Linux/amd64 worker base is `python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe`; the Docker registry manifest identified Python 3.12.15-slim-trixie at this pin. Its DuckDB/SQLGlot wheel hashes are in [worker requirements](../sandbox/requirements.txt). Actual image provisioning, path mapping, resource enforcement, and boundary tests pass on this host for the initial sales-schema worker. The pure [SQL policy](SQL_POLICY.md) is tested separately from execution.

TraceFrame is an optional `traceframe` extra resolved in `uv.lock` to the exact recorded commit; it runs only in the one-export subprocess, never in the runtime wheel's import path. Inspect (`inspect-ai` 0.3.281 in `uv.lock`, MIT license) is an optional `inspect` extra used only by `assay.agents.inspect_client` to call model providers; it brings a large transitive set (HTTP clients, a TUI, tokenizers) and is imported lazily, so the runtime wheel and default install do not need it. Offline tests use its `mockllm/model` provider; no paid provider is configured. Arrow/Parquet remains a planned integration. ControlArena, AMOS, FastAPI and React are deferred or conditional. Presence of source or a tool on a developer machine does not make it a tested container integration. See [execution decisions](ADR-0002-execution.md) and [current implementation status](IMPLEMENTATION_STATUS.md).

## Upstream planning baselines

These entries reproduce the locally inspected planning baselines in [REUSE_NOTES.md](../REUSE_NOTES.md); they have not been freshly fetched or revalidated for this documentation milestone.

| Upstream | Recorded commit / version | License and integration status |
|---|---|---|
| [TraceFrame](https://github.com/EltonChang1/traceframe) | `422befdcbadb95024b75b2e4ac381cb6716b97c3`; package 0.1.0 | Optional dependency for researcher-audit export (P3.7). The installed distribution's version, VCS commit, and MIT notice hash (`e45758a6…5098`) are verified by the exporter before use, and the notice is copied into every export. No upstream code is copied. |
| [AMOS](https://github.com/EltonChang1/AMOS) | `ab98863e643a0dd377084c7365fb283f3a3a5fcf`; package 0.2.0 | Cargo metadata declares MIT; planning inspection found no tracked LICENSE. Resolve notice provenance before copying/distributing implementation code. Payment-workflow constraints require a later capability gate. |

Before integrating, verify the chosen source/pin and its notice, record artifact hashes and direct/transitive dependencies, test supported behavior, and preserve attribution. A changed upstream HEAD does not change the recorded baseline automatically. Existing upstream metrics are not Assay results.

## Data, models, and distribution

Initial data are generated synthetic development fixtures. No external dataset or benchmark rights are implied. Inventory each future dataset's source, version/hash, license, redistribution restrictions, and split/exposure status separately from code.

No analyst/reviewer model or dated price is selected by the foundation. The pilot must record exact provider/model identifiers, configuration, prompts, prices, and terms relevant to stored/released traces. Confirmatory configuration also records code commit, lockfile hash, worker image digest, and check/scorer/policy versions.

Before public distribution, select the lab's license, enumerate resolved package notices, resolve AMOS provenance if relevant, and audit the allowlisted source/data/demo bundle. This file does not assert that those release requirements have passed.
