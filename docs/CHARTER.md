# TraceFrame Safety Lab — v1 charter

Adopted October 16, 2026. This charter fixes the research scope; it does not certify that the planned runtime or phase gates are complete. Implementation has reached the Phase 3 publication slice and the first Phase 4 episode and reviewer tickets (P4.1–P4.3). Gate status and remaining work are tracked in [implementation status](IMPLEMENTATION_STATUS.md) against [the backlog](../IMPLEMENTATION_BACKLOG.md).

## Purpose and users

Build a reproducible local research system to test whether executable checks and evidence-preserving review reduce incorrect quantitative conclusions released by an AI data analyst at a fixed oversight budget, while retaining useful answers. The primary user runs experiments; a secondary user audits claims, evidence, decisions, releases, and costs.

The first release uses synthetic tabular business data, structured answer slots, SQL tools, immutable input snapshots, a trusted evidence store, a revision-bound publisher, and a separate evaluator. Its audit viewer must distinguish draft reports from the exact bytes released to the simulated end user.

## Research comparison

The primary comparison is **E versus D**: E presents structured evidence links and check outcomes; D presents an ordinary summary and the same check outcomes. Both use the same reviewer model, combined oversight budget, underlying evidence corpus, bounded lookup tools, and executable checks. Any extra information or retrieval capability changes the intervention and requires an explicit ablation before attributing an effect to presentation.

The primary safety outcome is the episode rate of any materially incorrect released required or permitted supporting quantitative claim under prompted sabotage. The usefulness constraint is correct required-answer coverage on honest-agent ordinary-error runs, measured against a margin frozen before confirmation. Model identifiers, materiality, budget, margin, and final sample size remain pilot decisions. A is the no-research-oversight reference; B/C component baselines begin in development. Every arm retains the same host integrity and publication controls.

## Claim domain and regimes

v1 covers totals, counts, means, rates, comparisons, and simple rankings under explicit metric, population, grain, time, unit, version, and tolerance definitions. Every released quantitative claim must occupy a required or explicitly permitted supporting slot. An explicit, correctly justified abstention can be an answer. Numerical binding to a real result is separate from semantic correctness.

Evaluate three regimes separately:

| Regime | Adversarial control |
|---|---|
| Ordinary analytical errors | None; the analyst attempts the legitimate task. |
| Indirect prompt injection | Declared text fields or documentation, edited before snapshot freezing while preserving the legitimate answer. |
| Prompted sabotage | A synthetic private side objective given to the analyst; this does not demonstrate spontaneously arising hidden goals. |

The attacker cannot edit frozen data, the task contract, gateway, checker, authoritative log, publisher, or private scorer. Numeric data poisoning is deferred.

## Required trust boundaries

Actors see approved public tasks, tables, and bounded tools. Reviewers see their assigned legitimate-task evidence view, excluding the side objective and answer key. The trusted host owns execution receipts, immutable evidence, budgets, checks, and publication. SQL runs only through a restricted isolated worker with no private evaluator, host secrets, network, Docker socket, or publication mount. The private evaluator scores exact released artifacts after the episode and never authorizes release or supplies final-test feedback to actors. A `.gitignore`, directory name, schema validation, or successful Docker check does not establish these boundaries.

## Release definition and deferrals

v0.1 requires an isolated vertical slice: a correct report releases, a deliberately incorrect report scores wrong, and withheld content cannot bypass publication through export. v1 requires a frozen held-out evaluation, accounted-for assigned episodes and paid attempts, uncertainty and usefulness/cost reporting, an inspectable replay, sanitized artifacts, and clean-environment reproduction. Positive findings are not a completion requirement.

Defer hosted or multi-user operation, arbitrary Python/pandas tools, causal/general prose truth, open-ended business advice, public datasets, additional model/budget studies, human runtime review, long-history studies, and AMOS integration. Each needs its own protocol or capability gate. The standalone lab must work without AMOS; TraceFrame is an export target, not the evidence authority. See [the architecture decision](ADR-0001-foundation.md) and [reuse notes](../REUSE_NOTES.md).
