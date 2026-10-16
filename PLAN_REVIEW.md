# Planning Review and Completion Record

Completed October 16, 2026. This review concerns the implementation plan and its internal consistency. It is not a runtime security audit or a completed AI evaluation.

## Review scope

The primary review and dedicated research/systems reviews checked scientific validity, experiment accounting, trust boundaries, implementation dependencies, integration claims, release behavior, and feasibility. Existing AMOS/TraceFrame code was inspected at the cached commits documented in REUSE_NOTES.md.

## Material improvements incorporated

| Finding | Resolution |
|---|---|
| Unknown checks could imply either release or universal refusal | Explicit common-integrity, mandatory-research, advisory, and reviewer policies |
| Supporting claims lacked a scoring contract | Only declared supporting slots are publishable; the oracle scores them independently |
| Primary outcomes were ambiguous across threat regimes | Sabotage is the primary safety population; honest runs supply the usefulness constraint; other regimes reported separately |
| Injection edits appeared to conflict with immutable inputs | Construct attacked snapshots before freezing, with verified clean/attack answer correspondence |
| Summary costs could escape oversight caps | Enforce one combined summarization/review/re-review allowance |
| Attack pools could silently multiply runs or change paired inputs | One frozen assignment per shared case key; attack sweeps are separate experiments |
| Coverage statistics could change weighting during analysis | Recompute correct/required-slot ratios within paired template-cluster resamples |
| Late workers could publish after cancellation | Persist attempt leases/fencing; reject old admissions/releases; retain and reconcile outstanding costs idempotently |
| Already-published current reports had no stale-serving behavior | Keep immutable release history, separate current validity, and remove stale reports from the current index |
| Durable receipts were required before their storage layer existed | Implement minimal receipt/artifact persistence in Phase 2 and extend it in Phase 3 |
| An optional API could block a static release | Explicit not-applicable route and conditional backlog dependency |
| Architecture diagram suggested direct worker writes | Return worker results through the trusted gateway before evidence capture |
| The first milestone was abstract | Added a hand-checkable USD 200 versus USD 340 join-error fixture and a duplicate-amount counterexample |

No material planning contradiction remains from these reviews. Model selection, exact paid-run caps, numerical tolerances, and final sample size remain deliberate development/pilot decisions with specified selection and freeze procedures.

## Documentation validation

Checks performed:

- Local Markdown file links resolve; fenced blocks are balanced.
- The backlog has 60 uniquely identified implementation tickets and 8 extension tickets; all ticket references resolve.
- The ten phase effort ranges match between plan and backlog and sum to 250–350 hours.
- Adding 20% contingency produces 300–420 hours, consistent with the stated schedule.
- Pilot and illustrative confirmation arithmetic yield 216 and 1,080 episodes respectively under the stated assignments.
- The worked fixture totals are USD 200.00 for the correct calculation, USD 340.00 for the duplicated join, and USD 300.00 after the added equal-value order.

These checks validate the planning package. Dependency installation, sandbox tests, model calls, task scoring, statistical simulations, live provider prices, and measured performance remain implementation work.

## Completion boundary

The requested end-to-end plan is complete and ready to guide implementation. The first execution step is Phase 0, followed by the small independent data/oracle fixture. The package does not represent the planned application as built or its hypotheses as confirmed.
