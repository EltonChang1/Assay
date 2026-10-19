# Assay literature review and conference-writing research

**Review date: October 19, 2026 (America/Los_Angeles).**

This is a targeted, primary-source narrative review with **40 annotated core
papers**, additional screened works, five verified conference/track cycles, and
author-written academic-writing guides. It is not an exhaustive systematic review
of every relevant publication. Inspection depth, version and publication status
are recorded in the individual notes; no paper or benchmark was independently
reproduced here.

## Read the outputs

| Document | Contents |
|---|---|
| [Academic writing guide](../ACADEMIC_WRITING.md) | Contribution selection, claim/evidence discipline, abstract/introduction, technical argument, methods, evaluation, figures, related work and submission workflow |
| [Submission outline](../SUBMISSION_OUTLINE.md) | A venue-adaptable main-paper outline, editorial page allocation, proposed figures and evidence still needed |
| [Control and agents](control-and-agents.md) | 14 core papers: AI control, adaptive monitor attacks, sabotage, structured monitoring, injection benchmarks and constrained architectures |
| [Data and verification](data-and-verification.md) | 14 core papers: provenance, SQL equivalence, discriminating tests, verification, abstention and analytical-agent evaluation; eight additional screened works |
| [Evaluation and foundations](evaluation-and-foundations.md) | 12 core works: selective prediction, uncertainty, citation support, explanation faithfulness, trusted enforcement, proof-carrying code and versioned provenance |
| [Conference requirements](conference-requirements.md) | Official NeurIPS 2026, ICML 2026, ICLR 2027, SIGMOD 2027 and PVLDB v20 limits, templates, anonymity, review criteria and ancillary requirements |

## Search and selection protocol

Searches combined the project's research question with six neighborhoods:
AI control/monitoring; prompt injection and sabotage; database provenance and
versioning; SQL equivalence, test generation and intent verification;
data-analysis reliability/abstention; and evaluation/statistical reporting.
Foundation papers were included when they constrain the claimed contribution.
Recent searches extended through papers available on the review date, including
selected 2026 work. We followed references and neighboring work from the closest
sources; this is not a complete forward-citation census.

Primary evidence came from official proceedings, ACL Anthology, PMLR, JMLR,
USENIX, CIDR, author-hosted papers, and versioned arXiv texts. Official author and
reviewer instructions determine format. Discovery snippets and third-party
summaries were not used to assign stronger technical results than the primary
source supports. Each annotation records what was actually inspected, including
inaccessible final versions, abstract-only records and limits of venue verification.

Core inclusion required a direct connection to Assay's semantics, threat model,
release authority, oversight comparison or evaluation design. Generic model
benchmarks, broad surveys and product marketing were not added simply to enlarge
the bibliography. A preprint and its conference version are one work, with their
differences recorded rather than counted as independent contributions.

## Closest comparisons and remaining candidate gap

| Literature neighborhood | Especially close sources | What Assay must not claim as new by itself |
|---|---|---|
| Runtime SQL verification | Alrashed et al., PVLDB 2026; adaptive-abstention work; TrustSQL | Ground-truth-free SQL review or abstention |
| SQL evaluation validity | Cosette; VeriEQL; distilled test suites; SpotIt; XData | Counterexample databases, bag-semantics checks or single-fixture limitations |
| Structured-data reliability | TrustDABench, 2026 preprint | Evidence-path framing or answerability-aware evaluation |
| Agent control and monitoring | AI Control; Ctrl-Z; adaptive monitor attacks; TraceGuard | Oversight, structured monitoring or an allowing/rejecting reviewer |
| Constrained agent architectures | CaMeL; prompt-injection design patterns | Capability separation or the general use of trusted enforcement |
| Provenance and authorization | Provenance Semirings; PASS; layered provenance; DataHub; Saltzer/Schroeder; PCC | Lineage, versioned artifacts, a small trusted validator or complete mediation |

The remaining **candidate**, not an established priority claim, is a task-specific
analytical protocol connecting these obligations to exact-revision released
claims, paired with a resource-matched comparison of review representations.
Novelty and usefulness must be demonstrated through direct comparisons and a
completed study. The broader workflow-provenance, semantic-layer, data-contract
and proof-carrying-data literatures still warrant a focused search if a future
paper expands its claims into those areas.

## Recommended reading sequence

1. AI Control; Adaptive Attacks on Trusted Monitors; AgentDojo; CaMeL: establish
   protocols, attacker knowledge and the difference between authorized flow and
   answer correctness.
2. Alrashed et al.; SpotIt; VeriEQL; TrustDABench: establish the closest 2026
   methods and what their guarantees/evaluators actually mean.
3. Provenance Semirings; distilled test suites; PASS/layered provenance: locate
   the established semantic and artifact foundations.
4. Selective-classification foundations; Agarwal et al.; Dror et al.: define
   coverage/risk, independent units and uncertainty before interpreting scores.
5. TraceGuard and defense-adaptive attack work: design representation ablations
   and failure analysis under meaningful total resource limits.
6. The exact chosen venue's reviewer/author instructions, then the writing guide:
   build an argument appropriate to its contribution type and current rules.

The memos contain authors' reported findings, not new Assay measurements. The
current pilot has no reviewer exposure and cannot test the intended D/E effect.
No model calls, external benchmark replications, publication, submission or
messages to outside parties were performed for this literature review. The
repository's existing deterministic numerical regression was rechecked as part
of the paper evidence audit.
