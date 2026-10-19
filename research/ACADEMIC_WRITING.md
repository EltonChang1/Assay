# Writing an academically competitive Assay paper

Research and guidance checked October 19, 2026. This document preserves the
literature and writing lessons for future revisions. It is a project-specific
editorial synthesis, not an acceptance prediction or a completed empirical study.

## 1. The central standard

A conference paper must leave a reader with new, defensible knowledge about an
important problem. Technical detail helps only when it makes that knowledge
precise, demonstrates why a mechanism works, or reveals where it fails. More
equations, implementation detail, citations, or pages do not independently make
a contribution stronger.

The checked NeurIPS reviewer instructions organize assessment around quality,
clarity, significance, and originality; different contribution types retain
substantive evidentiary standards. In particular, its negative-results guidance
requires understanding of an important negative finding, beyond an experiment
merely not working. [Official reviewer guidance](https://neurips.cc/Conferences/2026/ReviewerGuidelines).

For Assay, keep three questions separate:

1. **What is implemented?** A metric contract, restricted execution, evidence store,
   partial semantic checker, review interface, and controlled publication path.
2. **What has been learned?** Specific authentic-but-wrong calculations, a repaired
   relation-binding defect, tested conditional publication behavior, and a failed
   feasibility pilot.
3. **What remains to be learned?** Whether structured evidence review improves
   incorrect-release risk relative to ordinary-summary review at an equal total
   oversight allowance while retaining useful answers.

The third question is the motivating empirical hypothesis. It cannot appear as a
result until the relevant completed comparison exists. The present report is a
bounded systems report, with a prospective protocol, rather than a conference-ready
demonstration of that hypothesis.

## 2. What the literature changes

The [literature map](literature/README.md) links 40 core-paper annotations and the
official venue comparison. The strongest nearby work includes formal/bounded SQL
equivalence, discriminating query tests, inference-time SQL verification,
adaptive abstention, structured monitoring, and structured-data evidence paths.

Consequently, these statements are not defensible novelty claims by themselves:

- Adding provenance or citing a result cell.
- Verifying SQL without a runtime gold answer.
- Refusing an answer when confidence or a check is inadequate.
- Presenting a structured rubric to a monitor.
- Separating an untrusted producer from trusted enforcement.
- Finding that one query accidentally agrees with gold on one database.

The candidate research distinction is the **combination and interaction** of
explicit analytical obligations, exact-revision/byte publication authority, and
review protocols compared under equal combined resources. Calling the combination
novel remains a hypothesis about the literature, not a fact established by the
presence of several components. It needs comparison with the closest mechanisms
and an explanation of the additional behavior or insight it enables.

Build a comparison matrix using properties the papers actually discuss: public
metric contract; resolved SQL semantics; formal or bounded guarantees; claimed
cell binding; review representation; release authority; source/revision freshness;
required-answer coverage; adaptive attacks; and complete cost accounting. Use
“not established in the inspected source” when a paper does not report a feature.
Absence from an abstract is not proof that a system lacks it.

## 3. Choose the scientific story before the template

| Possible paper | Central evidence needed | Present status |
|---|---|---|
| Empirical AI-control study | Completed D/E comparison, independently scored released outputs, strong attacks/baselines, uncertainty, useful coverage and costs | Unanswered: pilot never reached review |
| Data-management systems study | Distinct semantic/release mechanism, supported language and boundaries, realistic workloads, coverage/overhead/scaling, careful comparison with SQL verification | Partial: one exposed analytical family |
| Formal-methods study | A substantively new specification or verification result, precise semantics, proof with scoped assumptions, meaningful mechanization/evaluation as appropriate | No general checker soundness theorem |
| Benchmark/evaluation study | A useful new task distribution, independent validated ground truth, leakage controls, evaluator audit, broad baselines and reproducible artifacts | Structural benchmark remains unbuilt |
| Significant negative result | A well-posed important question, capable baseline, controlled study and explanatory evidence ruling out key alternative causes | Dependency/allowance failure alone is insufficient |

This is our assessment of fit, not a statement that any venue requires all paper
types to have identical experiments. Pure theory, measurement, systems, and
benchmark papers justify different claims with different evidence.

Do not select a contribution type to conceal a missing experiment. A narrowed
systems question is legitimate when it produces a meaningful, completed insight
of its own; renaming incomplete empirical work does not create that insight.

## 4. Write a claim before writing sections

Use one sentence with five parts: **problem; new mechanism or insight; evaluated
scope; completed evidence; limit**. An internal sentence appropriate today is:

> Assay separates execution authenticity, numerical binding, supported metric
> semantics, and current-revision release authority for a synthetic revenue task;
> deterministic counterexamples and publication regressions establish selected
> mechanism behavior, while a zero-submission pilot leaves the oversight effect
> unmeasured.

This is an accurate project summary, not a claim that the result is sufficiently
significant for a particular conference. The final abstract must state the
scientific contribution, not just enumerate software modules.

Maintain a claim ledger before revising prose:

| Claim | Required support | Permitted wording now |
|---|---|---|
| Authenticity does not imply metric correctness | Constructive counterexample with independently derived truth | “An authentic duplicated-join result is incorrect under the declared metric.” |
| Selected publication transitions preserve bindings | Explicit assumptions, implementation analysis and recorded race/recovery tests | “The tested transitions enforce these conditional invariants.” |
| Structured review improves safety | Frozen paired model experiment and valid endpoint analysis | “We propose to test…” |
| Broad SQL verification or universal security | Defined semantic universe and a suitable proof/evaluation | Unsupported; omit |
| Evidence is independently correct | Independent derivation plus validation of generator/contract/scorer | Describe the independence path and remaining shared assumptions |

For every quantitative claim, record its denominator, unit, evidence version,
analysis command, uncertainty, missingness and qualification. A test count is
evidence of the tested mechanisms, not a sample from a deployment safety rate.

## 5. Opening, abstract, introduction, and contributions

**Title.** Name the problem and the specific mechanism or finding. Avoid “safe,”
“verified,” “guaranteed,” or “first” when the necessary scope or proof is missing.
An existing system name is optional; the reader should understand the topic
without knowing the project.

**Abstract.** As an editorial target, use roughly 150-220 words unless the chosen
venue specifies otherwise. State the problem, unresolved gap, approach, completed
evaluation scope, principal result, and main limitation. That word range is not a
universal conference rule. Do not put a proposed sample size in the position of
an observed result, and do not imply safety improvement from zero releases.

**Introduction.** Use a short worked failure to make the objective concrete,
then answer: why it matters, why existing mechanisms do not settle it, what the
paper adds, and what evidence supports the addition. A late paragraph should
identify the exact limits a reader needs to interpret the claim. Jennifer Widom's
author guidance provides a useful problem/importance/difficulty/gap/approach
framework. [Stanford notes](https://cs.stanford.edu/people/widom/paper-writing.html).

**Contribution list.** Each item needs an intellectual object and evidence:
a formalized obligation, mechanism with a new property, validated benchmark, or
empirical finding. “We wrote a package, many tests, and a paper” describes effort,
not the advance in knowledge. Separate established background from anything
claimed to be original. Three sharp contributions are an editorial option, not
a mandatory count.

The paper should explain the useful idea before exhaustive machinery. Simon
Peyton Jones's guidance treats writing as a way to clarify the idea, recommends
one central message, and uses concrete examples to introduce it. His slide page
allocations are teaching examples, not current venue limits.
[Primary resource](https://www.microsoft.com/en-us/research/academic-program/write-great-research-paper/).

## 6. Make first-principles reasoning do useful work

For each important property:

1. Define the task and mathematical objects before using them.
2. State the semantic and trust assumptions.
3. Derive the claim, including the direction of each implication.
4. Give a proof, witness, or appropriately scoped experiment.
5. Show a boundary case where an assumption matters.
6. Identify which part is established background and which part advances it.

For an order-grain sum, let e(o) be eligibility, a(o) integer cents, and w(o) the
effective multiplicity introduced by a query. With fixed eligibility and
coefficients independent of amounts, the error is

```text
estimated_total - requested_total
    = sum over eligible o of (w(o) - 1) * a(o) / 100.
```

Universal preservation over admissible amounts requires the correct entity
coefficients. A single passing fixture is weaker. This is a useful explanatory
derivation grounded in established bag semantics; adding the label “Proposition”
does not make it a new mathematical contribution.

For release authority, define the report revision, exact rendering, source epoch,
check version and active attempt before stating an invariant. Distinguish
“the implementation checks these fields” from “the state machine has this
property under stated assumptions” and from “the property has a machine-checked
proof.” Explain what remains trusted. A cryptographic hash establishes identity
relative to an expectation, not the truth of a computation.

## 7. Explain methods so a reviewer can evaluate them

Present the minimum architecture that explains the claim. A useful order is
public task and threats, objects and observations, checking algorithm, review
protocol, and publication transition. The full report can retain the detailed
source audit, but a conference paper should not spend its main argument listing
files, tickets, console commands, or implementation history.

For each algorithm, specify inputs, outputs, versioned state, preconditions,
failure/unknown behavior and the property it is intended to establish. Give
pseudocode where it clarifies control flow. Explain the supported query language
and handling of aliases, nulls, units, temporal bounds, duplicates and missing
evidence. Show both accepted alternative correct solutions and rejected wrong
ones. Unsupported correct queries must remain visible as a coverage limitation.

For an empirical review comparison, define the information each role receives,
which content is adversarial, what retrieval is permitted, and how correction
affects later exposure. Equal resources must include D's summary generation,
every review, correction review, lookup, retry and unresolved charge. Equal caps
define an allowed-resource comparison; actual use may still differ.

## 8. Design evaluation around questions and competing explanations

Our proposed question-to-experiment map is:

| Question | Appropriate measurement | Alternative explanation to address |
|---|---|---|
| Can the agent solve the legitimate task? | Useful baseline completion and correct required slots | Oversight appears safe because the agent never submits |
| Do checks detect the intended errors? | Independently scored semantic mutations and alternative correct solutions | Checker overfits hand-chosen query strings |
| Does representation help? | Matched D/E cases, same checker/reviewer/corpus and combined limits | Extra retrieval, information or budget causes the change |
| Does the publisher enforce current approval? | Revision/source/attempt races and fault injection | An alternate release path bypasses the mechanism |
| Does the result generalize? | Sealed structural/schema/attack partitions | New amounts repeat the development structure |
| Is the result useful at feasible cost? | Correct-answer coverage, actual role costs and latency, risk/coverage displays | An all-withhold or exorbitant protocol wins on error count |

Useful new baselines should be motivated by the closest work: deterministic
checks alone; ordinary review; structured review; direct SQL critique or other
appropriate ground-truth-free SQL verifier; and explicit all-withhold. Every
baseline is an implementation commitment. Do not state that these comparisons
were executed when they are only recommended.

Report counts and effect sizes, not only a p-value. Cluster at the genuinely
independent structural unit, preserve pairing, retain all assignments and failure
categories, and distinguish sampling intervals from unknown-outcome bounds.
The selective-prediction and evaluation references in
[evaluation-and-foundations.md](literature/evaluation-and-foundations.md) explain
the surrounding concepts; they do not automatically validate the repository's
proposed bootstrap or sample size.

Choose sample counts through a feasible, frozen precision plan. The old 1,080
episode arithmetic is a proposal, not a power calculation or a spending
authorization. A negative or inconclusive result is acceptable when the question
is meaningful and the study can discriminate important explanations.

## 9. Related work should change the reader's judgment

Organize by competing solutions or unresolved obligations, rather than give one
abstract-like paragraph per paper. For every close comparison, explain its task,
assumptions, method, guarantee or measured outcome, then the precise remaining
gap. Discuss the strongest overlap directly, including work outside ML.

Michael Ernst's author guidance emphasizes a coherent message, comparison rather
than a list of summaries, reader-oriented organization and substantive revision.
This guide adopts those practices without treating every stylistic preference as
a binding rule. [University-hosted guidance](https://homes.cs.washington.edu/~mernst/advice/write-technical-paper.html).

For Assay, organize the comparison around:

- Provenance and formal/bounded SQL reasoning.
- Inference-time verification, abstention and structured-data reliability.
- AI control, adversarial monitoring and constrained agent architectures.
- Evaluation validity, evidence support and selective risk/coverage.

Do not claim a prior method fails on an Assay example without applying it under
its own assumptions or deriving the incompatibility. Do not call a preprint a
conference paper because it appeared on OpenReview. Pin version-specific numbers,
especially when a title, evaluation or reported result changed.

## 10. Figures, results, limitations, and conclusion

Each figure should answer a named question. Captions need dataset/task scope,
units, denominators, relevant uncertainty and enough description to prevent an
incorrect inference. Show the all-withhold boundary where meaningful. Explain
why a difference matters in the text; readers should not have to infer the
scientific claim from bar colors.

Separate mechanism validation, source audit, capability pilot and held-out model
comparison in result headings. Keep limitations next to claims where their
absence would mislead, then discuss their implications together later. A
diagnosed preview defect explains that preview failure; it does not explain all
other query errors without evidence.

The conclusion should answer the opening question at the achieved scope,
identify the transferable insight, and state the remaining uncertainty. It
should not advertise an unfinished experiment as an expected positive result.

## 11. Actual conference format

The [official venue comparison](literature/conference-requirements.md) records
exact cycles, tracks, sources, submission/final differences, identity rules,
templates and ancillary requirements. Use it for planning, then recheck the live
selected call. The verified families are NeurIPS 2026, ICML 2026, ICLR 2027,
SIGMOD 2027 and PVLDB volume 20. Several deadlines have already passed; their
format rules are not an invitation to submit late or a prediction of future rules.

A conference manuscript normally begins directly with title, abstract and the
argument in the official style. Assay's report cover, evidence-status block,
contents page, custom running footer and 24-page single-column presentation are
technical-report conventions. A venue version must follow that venue's template;
it should not reproduce report furniture or compress the PDF through smaller
fonts. Keep essential definitions, method and evidence in the main allowance.
Appendices supply detail rather than hide an unsupported central claim.

Preserve the complete canonical report and evidence. A later submission version
must remain synchronized with it. The [submission outline](SUBMISSION_OUTLINE.md)
provides an editorial page allocation without manufacturing missing results.

## 12. Repeatable drafting and review workflow

1. Select the scientific question and plausible venue family; make scope explicit.
2. Refresh the closest-work matrix, exact versions, and claim/evidence ledger.
3. Write the one-sentence thesis, opening example and contribution list.
4. Outline each section with the claim it establishes and its supporting artifact.
5. Complete the evidence needed for those claims under a frozen protocol.
6. Draft methods and results; rewrite abstract and introduction to match them.
7. Run a technical audit of definitions, proofs, units, numerical reproduction,
   unsupported cases, baselines and denominators.
8. Read as a skeptical reviewer: identify the strongest alternative explanation,
   closest prior work, and missing information required to reproduce the result.
9. Check official formatting, citations, anonymity/identity, ethics, AI disclosures,
   artifacts and concurrent-publication rules for the exact track.
10. Render every page and inspect extracted text, equations, figure labels and
    bibliography. Human authors verify and accept responsibility for the final
    scientific content.

Writing and literature research can proceed now. Model experiments, publication,
submission, public artifact release and messaging remain distinct actions and
must follow existing project authorization and evidence rules. This guide does
not authorize new paid calls or erase previous cumulative spending.
