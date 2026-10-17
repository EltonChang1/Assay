# Assay — Existing Code and Integration Notes

Reviewed October 15, 2026. Read-only inspection of local cached bare repositories. No fetch, implementation changes, or test runs were performed in these repositories for this plan. The recorded commits are reproducible planning baselines, not assertions about current remote HEAD.

## 1. TraceFrame

Repository: [EltonChang1/traceframe](https://github.com/EltonChang1/traceframe).

Inspected commit: **422befdcbadb95024b75b2e4ac381cb6716b97c3**, dated August 26, 2026. Package version 0.1.0, Python requirement >=3.10, MIT license with a tracked notice.

Useful interfaces at this snapshot:

| Interface | Reuse in the lab |
|---|---|
| EvidenceRecord in src/traceframe/evidence.py | Export target for IDs, artifact type, run/source IDs, hashes, row counts, SQL/formula, warnings and metadata |
| tf.start(project_name, notebook_name=None) | Initialize an isolated export context |
| tf.track and transformation helpers | Record trusted input/result tables and explicitly known transformation relationships |
| tf.metric, tf.chart, tf.claim | Project already captured values, chart specifications, and claims into an audit report |
| expect_unique, expect_not_null, expect_no_duplicates, expect_schema, expect_column_between | Reuse or adapt quality-check logic under trusted execution, with exact version/behavior tests |
| lineage_graph, export_source_rows, drilldown, dataset_statuses | Optional inspection views and limited source samples |
| tf.export_report | First HTML evidence demonstration before a custom UI |

Exact type reference: [EvidenceRecord](https://github.com/EltonChang1/traceframe/blob/422befdcbadb95024b75b2e4ac381cb6716b97c3/src/traceframe/evidence.py#L21).

Important boundaries:

- tf.claim accepts free-form text and supporting references; it does not establish analytical correctness.
- src/traceframe/sql.py discovers FROM/JOIN sources with a regular expression. This is not the lab's authorization/dependency parser.
- tf.sql executes SQL directly and is not an isolation boundary. Do not route untrusted analyst queries through it in the host process.
- Local evidence JSON is mutable. Atomic file replacement does not create adversarial tamper protection or multi-writer transaction safety.
- Run, object, and database context includes process-global state. Use a new process and directory per adapter run until an explicitly tested context API exists.
- Source-row exports are samples, defaulting to the first 50 rows, not exhaustive row-level lineage.
- tf.expect(name, passed) accepts a boolean supplied by its caller. The lab only records such results after a trusted checker actually ran.
- Documentation headings refer to versions beyond the package's 0.1.0 declaration. Depend on the inspected code and a lockfile, not an inferred release from those headings.

Adapter design:

1. Receive an immutable lab run export with snapshot IDs, actual query/result records, typed claim bindings, checks, and decisions.
2. Verify its schema and referenced content hashes before exporting.
3. Create a dedicated TraceFrame process/context for that run.
4. Map lab IDs to TraceFrame IDs; preserve the lab IDs, schema version, source commit, and full content hashes in metadata.
5. Export known lineage edges and source samples with their coverage limitations.
6. Record unsupported fields in a companion versioned JSON manifest rather than dropping or inventing them.
7. Compare round-trip records with the lab authority; export/report failure must not change publication state.

Do not re-execute an untrusted query through tf.sql solely to obtain a lineage display. Record the result already executed by the lab's restricted worker. If the public API cannot represent a receipt cleanly, use a narrow adapter/export extension with conformance tests.

## 2. AMOS

Repository: [EltonChang1/AMOS](https://github.com/EltonChang1/AMOS).

Inspected commit: **ab98863e643a0dd377084c7365fb283f3a3a5fcf**, dated August 13, 2026. Package version 0.2.0. Cargo metadata declares MIT, but this snapshot has no tracked LICENSE file. Resolve the distribution notice before copying or redistributing AMOS implementation code. A separate lab design and adapter investigation can proceed.

The [domain types](https://github.com/EltonChang1/AMOS/blob/ab98863e643a0dd377084c7365fb283f3a3a5fcf/src/domain.rs) provide precedents for TaskDefinition, PlanStep, TypedPlan, ExecutionRecord, Claim, DependencyEdge, ReplayPackage, VerificationRecord, and Outcome. Useful concepts include resource limits, typed payloads, execution/output hashes, independent validity and review state, replay, fencing, idempotency, and transitive invalidation.

Existing API surfaces include /v1/tasks, /v1/artifacts/{id}, /v1/claims/{id}, replay/review routes, /v1/verify/sql, and /v1/audit. Their presence does not establish support for arbitrary lab tasks.

Concrete constraints in the inspected snapshot:

- src/runtime.rs:384 contains AmosRuntime::run_task; the runtime selects payment_health_review around line 425.
- The private build_plan around line 1961 emits fixed payment-workflow queries.
- preflight_sql around line 1452 also loads the payment task and fixed window.
- RuntimeConfig provides database/object paths and a capability key, not a general injected task pack, model provider, or worker implementation.
- src/verification.rs rejects joins, CTEs, subqueries, set operations, and functions outside its supported subset.
- Fixture-specific metric comparisons recompute some quantities; generic metric_value validation only checks that a numeric payload is finite.
- ModelProvider and isolated-worker architecture records are proposed extensions. The inspected implementation does not supply the full external-model analyst and OS-level worker isolation needed by this lab.
- Archived Python evaluation commands and saved historical result JSON are not a reproduction path or result evidence for the new study.

The [product-readiness document](https://github.com/EltonChang1/AMOS/blob/ab98863e643a0dd377084c7365fb283f3a3a5fcf/docs/PRODUCT_READINESS.md) explicitly scopes the project as a control-layer reference slice.

## 3. Conditional AMOS integration milestone

The standalone Python lab and first research release must work without AMOS integration. Then choose one bounded integration path:

1. Demonstrate the lab's evaluation/reporting interfaces against AMOS's existing payment fixture, retaining its current scope; or
2. Add a documented general task-definition/typed-plan/verifier port in a focused upstream change, preserving existing behavior and tests.

Use versioned JSON/HTTP contracts or a small Rust bridge. Negotiate query grammar, claim types, budget semantics, publication states, error types, and snapshot identities. Unsupported behavior must return a capability error; it must never skip verification silently.

Conformance gate:

- Identical supported tasks, inputs, queries, and claim bindings produce equivalent recorded semantics.
- Stale dependencies and changed report revisions cannot publish.
- Idempotent retries and crashes do not create duplicate releases.
- Actor/monitor code cannot reach private scorer data or publication credentials.
- Generic task support and worker isolation are demonstrated by executable tests, not inferred from architecture proposals.

## 4. Contribution and licensing workflow

Keep the lab's new contracts and gateway implementation separate from upstream projects. Pin exact dependency commits/releases and preserve the TraceFrame MIT notice. Resolve AMOS notice provenance before redistribution. Record licenses and source restrictions for all external datasets and benchmarks separately from the lab's own code license.

Potential upstream work after v1: a stable evidence-import/export contract, explicit non-global run contexts, stronger source parsing, receipt links, and generalized AMOS task/worker ports. Each should be a separate justified change with its own tests and review.

No existing project metric should appear as an Assay result. Reuse implementation knowledge and verified interfaces; generate the new study's evidence through its own frozen protocol.
