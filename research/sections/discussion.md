## Discussion, limitations, and research completion

The current evidence demonstrates a useful separation of questions. Authentic execution provenance can bind an incorrect number faithfully. A checker can reject a known multiplicity error without being a complete SQL theorem prover. A reviewer can recommend release without having publication authority. A publisher can enforce a revision transaction without establishing the truth of arbitrary prose. An independent evaluator can detect a wrong baseline release while remaining excluded from online authorization. Each distinction is necessary to interpret an eventual prevention result.

The audit's relation-binding defect is especially relevant to research validity. A surface match on a base-table name was insufficient when a common table expression or positional column alias changed the meaning of that relation. The observed wrong outputs were genuine DuckDB calculations, and their authentic receipts did not protect the checker from its own mistaken interpretation. The repair conservatively marks the unsupported relation-binding shapes unknown. Regression coverage establishes those repaired cases; it is not a proof that no other false-pass construction exists. Future task/check extensions need adversarial relation-resolution tests, equivalence tests, and explicit unknown outcomes before entering a frozen study.

The development pilot adds a concrete boundary around that future comparison. On the measured worker image, fetching a timezone-aware `occurred_at` value fails because DuckDB requires `pytz` and the image does not contain it. Every analyst preview of `orders` therefore returned `query_error`, and all 24 episodes exhausted six model calls without submitting a claim. The resulting zero release rate is an allowance-exhaustion outcome. It leaves the D-versus-E contrast unmeasured. A later image that can return timestamps would be a new worker identity and would require its own frozen run.

The single exposed sales family limits statistical and external validity. There are no measurements of naturally occurring analyst error frequencies in production businesses, no causal/business-advice verification, no broad rate/mean/ranking benchmark, and no evidence that a defense transfers across schemas or attack formulations. Scripted A/C incorrect release and B/D/E withholding are mechanism outcomes deliberately induced by developer-selected trajectories. They must not be reported as estimated safety rates or as evidence that evidence-preserving review beats ordinary review. D and E share the same deterministic checks, which can completely determine these particular withholding decisions.

The trusted host and builder remain assumptions. Snapshot permissions and container mounts restrict the worker but do not defend against an adversarial host administrator. Content hashes detect changes relative to stored expectations when artifacts are read; they do not make a signed, externally anchored audit ledger. Publication rechecks its authoritative stored inputs and exact rendering but does not rerun SQL or recursively read every dependency at the instant of release. Source identifiers require host-enforced immutability. These constraints belong in the threat model and cannot be inferred away from successful transaction tests.

Current transaction/fencing tests establish selected lifecycle behaviors. Complete lease expiration, delayed gateway-result admission, durable whole-experiment spending reservations, and recoverable distributed retries remain separate runtime work. A sequential pilot's dedicated budget journal can constrain that pilot without demonstrating those production capabilities. Likewise, keeping oracle code outside a wheel or worker mount reduces exposure but does not establish that every final-test actor/reviewer interaction is isolated from private evaluation information. Confirmation requires testing the actual end-to-end information boundary.

The prospective empirical contrast includes representation cost. D spends part of the common allowance constructing its ordinary summary; E starts with a host-built evidence view. A positive result would concern those protocols under equal allowed resources. It would not establish that adding more evidence always helps, that every monitor is reliable, or that observed episodes estimate a deployment hazard rate. Actual token utilization, lookup count, latency, deterministic checking time, and dollars must accompany both safety and coverage. All-withhold is the limiting example: avoiding every incorrect release is uninformative if the system never supplies a correct answer.

The proposed sample arithmetic remains a planning envelope. Twelve held-out structural templates produce only twelve primary clusters even when each has ten generated datasets and several regimes. Sparse errors and correlated failures can yield unstable or degenerate bootstrap intervals. A small pilot on the current family cannot estimate between-template variance for a future broad benchmark. It can establish feasibility, identify protocol failures, characterize cost, and motivate a larger benchmark; it cannot justify a precise power claim for an unbuilt task distribution. Any increase in sample size or change to the method must be frozen before confirmation outcomes are examined.

Completion of the research does not require a favorable result. It requires a validated and frozen task/attack distribution, enforced resource and information boundaries, a complete assignment/attempt/charge ledger, independent scoring of actual releases, uncertainty and missingness accounting, and reproduction of every reported table. The final paper should retain negative findings and the boundaries discovered during development. Until those gates pass, this document remains a technical systems report and prospective protocol with explicitly scoped development observations.

## Reproduction and artifact specification

The canonical manuscript is `research/paper.md`; the reading artifact is `output/pdf/assay-technical-report.pdf`. The PDF embeds all text, tables, figure pixels, and mathematical expressions. The source, validation records, JUnit outputs, and live-pilot manifests are supporting reproducibility artifacts, not additional papers. Rebuilding the PDF performs no model calls, executes no SQL, and does not rerun experiments. The build record binds the source and PDF by SHA-256 and reports page count and extracted-text length. Visual layout inspection is performed separately and is not inferred from extraction.

The current development checks use Python 3.12, the committed `uv.lock`, and the pinned optional Inspect/TraceFrame dependencies. The saved validation record contains exact commands, environment versions, source hashes, outcomes, skips, and timing. Invoke tools through `python -m` if a relocated virtual environment retains stale executable-launcher paths. No key value or raw credential belongs in command output, source control, paper text, model prompts, public evidence bundles, or a worker mount.

```text
uv sync --locked --extra traceframe --extra inspect
uv run --locked python -m ruff check .
uv run --locked python -m ruff format --check .
uv run --locked python -m mypy
# Enable all optional integration requirements in the calling shell:
# ASSAY_DOCKER_TESTS=1 ASSAY_TRACEFRAME_TESTS=1 ASSAY_INSPECT_TESTS=1
uv run --locked --extra traceframe --extra inspect python -m pytest
uv run --locked python -m evaluator
uv build --no-sources
uv run --script research/build_paper.py
```

The fixed milestone directly executes developer-authored SQL against in-memory DuckDB and scores canonical events; it is not an isolation or publication test. Episode/reviewer/publication tests using the phase-3 helper exercise real host services with an in-process DuckDB stand-in for container dispatch. The enabled Docker suite independently tests the real worker boundary. Fresh provider calls, a saved-trajectory replay, and a deterministic code regression are different experiments and require distinct labels and identifiers.

For each measured table, archive an immutable input manifest, source/environment identity, analysis command, analysis version, output checksum, assigned denominator, and relevant exclusions. Model reruns receive new experiment/attempt identities and may differ even with the same generation settings. A public release must audit credentials, notices, private truth, and active holdout material. Once a test set is published, it becomes exposed material for later work. The report is prepared locally; publication or announcements require the chosen release process.

## References

[R1] Ryan Greenblatt, Buck Shlegeris, Kshitij Sachan, and Fabien Roger. *AI Control: Improving Safety Despite Intentional Subversion*. ICML 2024; arXiv:2312.06942, version 5. [Primary paper](https://arxiv.org/abs/2312.06942v5).

[R2] Todd J. Green, Grigoris Karvounarakis, and Val Tannen. *Provenance Semirings*. PODS 2007. DOI: 10.1145/1265530.1265535. [Author-hosted paper](https://www.cs.ucdavis.edu/~green/papers/pods07.pdf).

[R3] Niklas Wretblad, Fredrik Gordh Riseby, Rahul Biswas, Amin Ahmadi, and Oskar Holmstrom. *Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark*. 2024. arXiv:2402.12243. [Primary paper](https://arxiv.org/abs/2402.12243).

[R4] UK AI Security Institute. *Inspect: Sandboxing*. Documentation consulted October 18, 2026. The local adapter's actual dependency version is bound by `uv.lock`. [Official documentation](https://inspect.aisi.org.uk/sandboxing.html).

[R5] UK AI Security Institute and Redwood Research. *ControlArena*. Documentation consulted October 18, 2026. No ControlArena integration is claimed in the measured implementation. [Official project documentation](https://control-arena.aisi.org.uk/).

[R6] OpenAI. *GPT-5.4 Mini model* and *Function calling*. Documentation consulted October 18, 2026. The authorized pilot configuration uses the dated model `gpt-5.4-mini-2026-03-17`, standard text input USD 0.75 and output USD 4.50 per million tokens, a 400,000-token context, no built-in paid tools, and an explicit reservation policy. Account availability and pilot execution are measured separately. [Model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini); [function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling).

[R7] Assay source repository, source revision and modifications identified in the validation section. Primary implementation references: `src/assay/contracts`, `datasets`, `gateway`, `execution`, `evidence`, `verification`, `review`, `agents`, `publication`; `sandbox/worker.py`; `evaluator/oracle.py`; `evaluator/milestone.py`; and the saved validation records. Planning references: `IMPLEMENTATION_PLAN.md`, `IMPLEMENTATION_BACKLOG.md`, `docs/CHARTER.md`, and architecture decisions 0001-0005. TraceFrame pin: `422befdcbadb95024b75b2e4ac381cb6716b97c3`; AMOS inspected planning reference: `ab98863e643a0dd377084c7365fb283f3a3a5fcf`.
