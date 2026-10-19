# Repository and paper review

Reviewed October 19, 2026 (America/Los_Angeles). The deliverable is the self-contained
[paper](paper.md) and its [rendered PDF](../output/pdf/assay-technical-report.pdf).
The paper completes a bounded systems study and reports a negative feasibility
pilot. The proposed comparative safety study remains unexecuted.

## Coverage and evidence

| Repository area | Review focus and disposition |
|---|---|
| `src/assay/contracts`, `datasets`, benchmark task card | Exact decimals, required/permitted slots, public metric, canonical events and public/private separation. Current implementation supports revenue and order count; charter-level means/rates/rankings remain prospective. |
| `gateway`, `execution`, `sandbox` | AST admission, scoped source access, frozen inputs, worker isolation, serialization, resource limits and error paths. Earlier container validation is saved; Docker is unavailable for this review. |
| `evidence`, `verification` | Canonical bytes, immutable artifacts, SQLite dependency indices, exact cell binding, semantic coverage and unknown cases. All 80 previously tested source/config/test digests still match. |
| `publication`, `review`, `agents` | Policy membership, revision/source/attempt binding, ordinary/evidence views, correction rounds and usage accounting. Distinguish sequential pilot budget protection from unfinished general runtime reservations and recovery. |
| `evaluator` | Independent canonical-event reference, slot scoring and ten fixed numerical regressions. Fresh milestone JSON exactly matches saved evidence; it is neither an isolation test nor a random sample of model mistakes. |
| CLI/config, adapters, tests, CI, lock/build inputs | Fresh suite requires both optional integrations: 436 passed, 29 skipped, no failures/errors, four warnings. Static checks pass. Remote CI statements are historical records, not freshly verified remote results. |
| `research/run_pilot.py`, saved/local evidence | Read-only reconciliation of all 24 assigned run IDs and treatment fields, manifest/results hashes, 144 settled analyst calls, zero oversight calls and USD 0.160803 conservative settlement. No new paid call. |
| README, security/status docs, charter, ADRs, plans/backlog | Align current summaries with the executed pilot; retain historical milestones and prospective gates as such. The canonical paper is the complete current argument; `research/sections` contains historical drafting material. |

Machine-readable reconciliation: [repository-review.json](validation/repository-review.json).
Fresh tests: [repository-review-junit.xml](validation/repository-review-junit.xml).
Audit command: `uv run --locked python research/audit_evidence.py`, optionally with
`--pilot-dir <local-state>/Assay/research/dev-pilot-20261018` for the original local
ledger. Runtime databases and raw requests/responses remain outside OneDrive.

## Material findings

1. **The pilot cannot answer the comparative hypothesis.** Every episode ended
   `tool_limit` before submission. No review occurred. Zero releases accompanied
   zero required-answer coverage; there is no measured D/E safety effect.
2. **The recorded worker cannot preview the primary table.** Its pinned dependencies
   omit `pytz`; DuckDB's timestamp fetch fails. Aggregate-only preflights did not
   reveal this defect. A future repair needs representative timestamp/preview
   validation, a new image/run identity and a separately frozen experiment. This
   paper review does not change the historical image or rerun the paid pilot.
3. **General confirmation gates remain open.** Combined runtime budgets, lease
   expiry, gateway admission fencing/recovery, structural holdouts, attack builders,
   private evaluator isolation and a complete analysis freeze are not established
   by the exposed development tests. The dedicated sequential pilot journal does
   not establish these broader capabilities.
4. **Source identity needs the digest inventory.** The checkout contains preexisting
   uncommitted semantic repairs and tests. A parent commit alone does not identify
   the tested system. Those edits are preserved; the current review does not
   silently replace historical source/evidence records.
5. **Current documentation lagged the evidence.** Older summaries said no paid
   provider had run and used superseded test totals. Current entry points now
   distinguish historical enabled validation, fresh offline verification and the
   executed negative pilot. No source-level finding is converted into a model
   performance result.

## Manuscript changes

The opening research question precedes the abstract. The redesigned paper places
closest prior work before the first-principles contract and multiplicity
derivation, then develops the checking and publication methods, evaluation design,
results, discussion and conclusion. Methods retain actual contracts, algorithms,
trust assumptions, counterexamples and publication invariants. Results distinguish
all evidence levels and retain the failed pilot. The proposed comparison now
appears in a separate prospective appendix. The report has no issue date, cover
sheet or contents page; bibliographic years and exact model versions remain.
No claim of production security or empirical superiority is made.

This is a repository-wide source, evidence and document consistency review,
supported by the recorded checks. It is not an exhaustive adversarial security
audit, fresh remote CI verification, or a completed held-out experiment.
