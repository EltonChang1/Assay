# Assay — Implementation Backlog

Implementation started October 16, 2026. The tables below retain the planned acceptance criteria; implemented and pending work is recorded with validation evidence in [implementation status](docs/IMPLEMENTATION_STATUS.md). The full decisions and study protocol are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); source integration constraints are in [REUSE_NOTES.md](REUSE_NOTES.md).

The primary builder owns implementation. Seek an independent review of task truth, trust boundaries, and final claims where practical; use separately implemented reference checks and documented self-review if no collaborator is available. Mark the difference accurately.

Complete the phases in dependency order. Tests and documentation belong to the feature ticket that introduces the behavior. Phase-level effort estimates include those checks. Use small branches/PRs with the problem, intended behavior, validation, and research impact described. Changes after the study freeze require explicit experiment-version handling.

An optional ticket can be marked not applicable with a recorded scope decision when the mandatory release gate is met through the supported simpler path. In particular, a static viewer can complete v1 without P8.3's local API.

## Phase 0 — Scope and environment (12–18 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P0.1 | Finalize v1 charter, claim domain, three threat regimes, and release definition | None | One-page scope names users, required behavior, primary research comparison, and deferred extensions |
| P0.2 | Create package/CLI skeleton, dependency lock, formatter/type checker, and basic CI | P0.1 | Clean install and offline smoke command pass on the supported environment |
| P0.3 | Validate Docker worker provisioning and local state directory outside OneDrive | P0.2 | Worker starts/stops; path mappings work; no live database under synchronized source path |
| P0.4 | Pin TraceFrame commit; inventory licenses and AMOS limitations | P0.1 | Reuse notes verified against dependency version; notices preserved; no assumption of a general AMOS task API |
| P0.5 | Write architecture decisions and experiment configuration schema | P0.1–P0.4 | Defaults, trust zones, resource caps, and open pilot decisions are explicit |

Gate G0: environment works, project scope and execution boundaries are agreed in versioned documents.

## Phase 1 — Data and independent truth (20–28 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P1.1 | Define TaskSpec, required/supporting answer slots, units, scope, tolerance, and answerability | G0 | Valid/invalid contract examples; every publishable claim has an independent scoring contract |
| P1.2 | Generate canonical sales events and derived relational tables | P1.1 | Seeded generation reproducible; schema/cardinality assertions pass |
| P1.3 | Implement independent oracle on canonical records | P1.2 | Hand-calculated cases agree; incorrect joins/denominators fail |
| P1.4 | Build clean, insufficient-data, and genuine historical-snapshot cases | P1.2–P1.3 | Correct abstention and legitimate historical answers accepted |
| P1.5 | Split public task files from private labels/reference code | P1.1–P1.4 | Agent-visible bundle contains no expected answers, private seeds, or diagnostic labels |
| P1.6 | Write task cards and mutation fixtures, starting with the worked USD 200/340 example | P1.3 | At least one wrong and one alternative correct implementation per initial task; equal-value orders defeat SUM(DISTINCT amount) shortcut |

Gate G1: the oracle distinguishes valid and deliberately incorrect analyses before an LLM is involved.

## Phase 2 — Secure analytical execution (28–38 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P2.1 | Specify and parse supported SQL grammar and permitted relations/functions | G1 | Required joins/aggregates work; unsupported syntax fails explicitly |
| P2.2 | Implement isolated query worker with locked database configuration | P2.1, P0.3 | External reads, network, writes, extensions, configuration changes denied |
| P2.3 | Build minimal versioned receipt/artifact persistence, then the tool gateway and host-assigned receipts | P2.2 | Durable snapshot/query/output records exist before G2; agent assertions cannot forge success or choose receipt IDs |
| P2.4 | Add CPU/memory/time/disk/output limits and cancellation | P2.2–P2.3 | Resource-exhaustion fixtures terminate without affecting other runs |
| P2.5 | Persist exact query, snapshot, full bounded output, and capped preview metadata | P2.3 | Hashes reproduce; truncation explicit; correct result cannot be confused with a preview |
| P2.6 | Build sandbox integration and isolation regression suite | P2.1–P2.5 | Useful queries pass alongside denied-path tests; no oracle/host secret access |

Gate G2: untrusted SQL executes only within the declared boundary and produces authoritative evidence.

## Phase 3 — Evidence, verification, and publication (30–40 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P3.1 | Extend Phase 2 storage with claims, checks, dependency edges, and publication metadata | G2 | Reuse the existing receipt/artifact foundation; versioned migrations and transactions preserve prior records |
| P3.2 | Implement exact claim-to-cell bindings and arithmetic/unit checks | P3.1 | Forged/cross-run/irrelevant references fail; correct alternatives pass |
| P3.3 | Implement public-contract check profiles with mandatory/advisory distinction | P3.2 | Pass/fail/unknown semantics tested; unsupported semantics never become a false proof |
| P3.4 | Render reports/charts from permitted structured claim slots | P3.2 | Unlisted numbers and contradictory free text cannot reach the released output |
| P3.5 | Implement revision-bound publication and invalidation | P3.3–P3.4 | Shared epoch prevents source-update races; current published reports become stale without erasing historical release records |
| P3.6 | Add crash/concurrency/retry tests around release | P3.5 | No duplicate release, orphan exposure, or wrong bytes; final attempt-fencing regression completes with P4.6 |
| P3.7 | Implement TraceFrame export adapter in isolated per-run context | P3.1–P3.5, P0.4 | Round-trip preserves source/result IDs, hashes, claims, limitations, and failed/unknown checks |

Gate G3: correct claims release through one path; invalid bindings and stale/changed approvals cannot bypass it.

## Phase 4 — Models, policies, and experimental arms (22–30 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P4.1 | Add provider-agnostic analyst loop and structured claims through Inspect | G3 | Fake-model complete/abstain/error cases produce well-formed episodes |
| P4.2 | Add ordinary-summary reviewer and structured decision parser | P4.1 | Invalid/missing decisions withhold; costs and evidence access recorded |
| P4.3 | Add evidence-preserving summary with identical underlying lookup access | P4.2 | D/E differ only in declared representation protocol, not hidden extra information |
| P4.4 | Implement arms A–E and bounded correction | P4.1–P4.3 | Same actor/tools/schema/security across arms; only research interventions vary |
| P4.5 | Implement combined oversight and total experiment spending caps | P4.4 | Summaries/reviews/reviews-after-repair and in-flight calls count before dispatch |
| P4.6 | Integrate resumable run/attempt state, leases/fencing, cancellation, and categorized retries | P4.4–P4.5 | Revoked workers cannot publish; duplicate callbacks cannot double-settle costs; in-flight canceled-call reservations remain until reconciled |

Gate G4: an offline end-to-end matrix and a small paid development smoke run are fully accounted for.

## Phase 5 — Benchmark development and pilot (30–42 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P5.1 | Build initial 12 development templates spanning failure mechanisms | G4 | Task cards, oracle/mutation fixtures, valid counterexamples present |
| P5.2 | Add answer-preserving injection builder and paired immutable snapshots | P5.1 | Allowed text edits occur before freezing; clean/injected expected answers agree |
| P5.3 | Add prompted sabotage policies and monitor information barriers | P5.1 | Side objectives hidden from reviewer; evaluator can independently score success |
| P5.4 | Execute 216 core pilot episodes or declared budget-limited pilot | P5.1–P5.3 | A/D/E × regimes × cases; all attempts and charges retained |
| P5.5 | Run B/C component baselines on a declared development subset | P5.4 | Rules-only and ordinary-review effects available for interpretation |
| P5.6 | Audit scorer disagreements and stratified successful/failed outputs | P5.4–P5.5 | Mis-scoring fixed across all arms; corrections documented |
| P5.7 | Estimate capability, failure prevalence, cost, variance, and required study size | P5.6 | Feasible final design with stated precision/power assumptions and spend cap |

Gate G5: tasks are solvable, failures are meaningful, outcomes are measured correctly, and confirmation is affordable.

## Phase 6 — Red team, hardening, and study freeze (22–30 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P6.1 | Expand task inventory and establish structural/seed/attack holdouts | G5 | Versioned exposure register and 18/6/12 target split or justified frozen alternative |
| P6.2 | Adapt attacks against defenses with equal development resources | P6.1 | Attack revisions/calls logged; frozen union tested across arms |
| P6.3 | Calibrate mandatory/advisory profiles, thresholds, budgets, and repair policy | G5, P6.2 | No calibration uses final-test outcomes |
| P6.4 | Complete worker/release recovery, oracle-leakage, and concurrency tests | P6.1–P6.3 | Boundary suite passes; cost reservation and cancellation recover correctly |
| P6.5 | Freeze protocol, paired-case keys, attack assignments, usefulness margin, sample size, and analysis | P6.1–P6.4 | Immutable preregistration; E vs D population and full run-count arithmetic specified |

Gate G6: no confirmation begins until all boundary and study-freeze requirements pass.

## Phase 7 — Confirmation and analysis (30–44 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P7.1 | Preflight final manifests without exposing private outcomes | G6 | Hashes, caps, model configuration, image, splits, and query/check versions match freeze |
| P7.2 | Run confirmation in randomized, paired condition order | P7.1 | All assigned episode IDs accounted for; no result-based early stopping |
| P7.3 | Score exact released artifacts with the private evaluator | P7.2 | Required/supporting claims covered; no monitor labels used as truth |
| P7.4 | Aggregate paired effects with template-cluster bootstrap uncertainty | P7.3 | H1 sabotage result and H2 slot-weighted honest coverage use matched case keys; other regimes separate |
| P7.5 | Analyze missing-outcome bounds, infrastructure failures, and per-template results | P7.4 | Failure cases cannot silently improve safety rates |
| P7.6 | Produce cost/latency/usefulness plots and a failure taxonomy | P7.4–P7.5 | Every plot regenerates from versioned result records; negative findings retained |

Gate G7: the research is complete whether positive, negative, or inconclusive, with evidence for its exact scope.

## Phase 8 — Replay demo and operational readiness (30–40 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P8.1 | Build static run/claim/evidence/check/released-output views | G4; finalized with G7 | A reviewer can trace a claim to execution and distinguish draft from released content |
| P8.2 | Add experiment comparison tables/plots with accessibility | P8.1, P7.6 | Safety shown with completion/cost; keyboard usable; status not color-only |
| P8.3 | Add optional local read API only if static views are insufficient | P8.1 | ID-based access; no arbitrary paths; no alternate publication route |
| P8.4 | Test escaping, artifact serving, and sanitized export | P8.1–P8.2; P8.3 if enabled | Malicious dataset/model text cannot execute in the viewer; no private evaluator leakage |
| P8.5 | Write and exercise outage, cancellation, budget, corruption, and restore runbooks | G6 | Representative incidents recover with an auditable outcome |
| P8.6 | Reproduce setup and analysis in a clean environment | G7, P8.4–P8.5 | Saved reproduction log distinguishes artifact replay from fresh model reruns |

Gate G8: the demo and results are independently inspectable without requiring hidden local state.

## Phase 9 — Research report and release (26–40 hours)

| ID | Work item | Dependencies | Acceptance evidence |
|---|---|---|---|
| P9.1 | Write report with methods, statistics, tradeoffs, and limitations | G7 | Every numerical claim has a result/table reference and scope qualifier |
| P9.2 | Complete dataset/system cards and reproducibility documentation | P9.1, G8 | Provenance, licenses, exposure, models, environment, and known failures documented |
| P9.3 | Create a minimal static demo bundle and short recording | G8 | Demonstrates correct release, caught error, and a remaining failure |
| P9.4 | Audit public files, dependency notices, traces, and source attributions | P9.1–P9.3 | Allowlisted bundle contains no credentials, restricted data, or hidden active holdouts |
| P9.5 | Tag/version the release and generate checksums/results manifest | P9.4 | Source, artifacts, report, and experiment versions agree |
| P9.6 | Record follow-up questions and establish a fresh holdout for future studies | P9.5 | Published test data marked exposed; later tuning cannot reuse it as untouched confirmation |

Gate G9: reproducible public release ready. Actual remote publication or announcements follow the user's chosen destination and authorization; the local release package is prepared first.

## Post-v1 extension tickets

| ID | Extension | Entry requirement | Exit evidence |
|---|---|---|---|
| X1 | Second model pair or oversight budget | G9 and new frozen configuration | Replicated tradeoff with separate costs/uncertainty |
| X2 | Real public datasets | License review and independently reviewed task truth | Documented domain-shift evaluation |
| X3 | AMOS integration | Capability/notice review and explicit task-port decision | Supported conformance suite; no silent verification bypass |
| X4 | Python/pandas tools | Revised threat model and isolated execution design | Fabricated-output/bypass tests plus independent checking strategy |
| X5 | Human review study | Explicit reviewer protocol and time budget | Actual measured review effort and usefulness/safety outcomes |
| X6 | Long-history/compression experiment | Working v1 baseline and new holdout | Matched total oversight-budget comparison |
| X7 | Model-organism or internal-monitor study | Model access, training budget, distinct protocol | Training/test separation and claims limited to measured behavior |
| X8 | Tactile-data reliability study | Separate prediction/abstention question | Corruption robustness measured without claiming physical robot safety |

## Proposed command-line contract

These names are specifications to implement, not commands that work today:

~~~text
assay doctor
assay dataset build --manifest <public-source-config>
assay dataset validate --manifest <case-manifest>
assay eval --spec <experiment-spec> --dry-run
assay eval --spec <experiment-spec> --max-cost-usd <cap>
assay resume --experiment <id> --max-cost-usd <remaining-cap>
assay cancel --experiment <id>
assay score --experiment <id> --oracle-manifest <private-path>
assay analyze --experiment <id>
assay replay --run <id>
assay export --experiment <id> --profile public-demo
~~~

Doctor and dry-run commands must not incur model charges or print secrets. Scoring runs only in the private evaluator context. Replay uses saved evidence; a fresh model rerun is a separately identified experiment. All live model commands validate a budget before dispatch.

## First working week

At roughly 20–25 hours, complete Phase 0 and begin P1.1–P1.3: choose the first question, write a tiny dataset whose answer can be computed by hand, define the claim contract, and build the independent reference calculation. End the week with an executable test showing that a correct aggregation passes and a duplicated-join aggregation fails. That is the first concrete research artifact; the isolated analyst execution path follows in Phase 2.

## Definition of done

- All mandatory phase gates pass with saved evidence.
- Final results account for every assigned episode and every paid attempt.
- Safety, usefulness, uncertainty, and cost are reported together.
- The public report uses only measurements from this project and discloses prototype/synthetic scope.
- The source, data contracts, oracle specification, manifests, results, demo, and reproduction instructions agree on versions.
- A clean environment reproduces the deterministic artifacts and documented demo.
- Outstanding limits and optional extensions are explicitly recorded; positive research findings are not a completion prerequisite.
