# Assay: Executable Evidence and Controlled Publication for AI Data Analysis

**Report version 0.1 | October 18, 2026 | Systems research report and prospective study protocol**

**Abstract.** A quantitative conclusion can cite an authentic SQL execution and still answer the wrong analytical question. Assay separates execution integrity, exact claim-to-cell binding, public metric checks, reviewer judgment, publication authorization, and independent benchmark correctness. The implemented prototype uses synthetic order-event data, a restricted DuckDB worker in a Linux container, a transactional evidence store, three-valued analytical checks, structured claim slots, and a revision-bound publisher. Five intervention policies provide no research oversight, checks alone, ordinary-summary review, checks with ordinary review, and checks with structured evidence review. This report formalizes the supported order-total task, documents implemented algorithms and conditional invariants, reproduces deterministic counterexamples, and specifies a paired online experiment with explicit safety, usefulness, cost, and missing-outcome estimands. A source audit found and corrected a relation-binding defect in which common table expressions could hide an unauthorized population change while semantic checks passed. Fresh development validation and its provenance are reported separately from prospective experiments. These results establish reproducible mechanism behavior on exposed fixtures; they do not establish a reduction in model-induced incorrect releases, general SQL verification, or production safety. Confirmatory claims require the held-out benchmark, complete budget/recovery boundaries, model protocol, and statistical freeze described here.

**Evidence status.** This is an evolving technical paper containing completed systems validation and a prospective empirical protocol. Proposed sample sizes are not observations. A small OpenAI API development pilot, capped at USD 15, has been executed once. Its assignment accounting, charges, and terminal statuses are in the development live-pilot section of `research/paper.md`. No confirmatory result is inferred from authorization or from the presence of an API adapter. The single PDF includes the argument, methods, numerical mechanism results, prospective analysis, limitations, and reproduction specification; source and machine-readable evidence remain available in the research repository for independent checking.

<!-- TOC -->

## 1. Research problem and contribution boundary

The research question is whether executable analytical checks and an evidence-preserving review protocol reduce materially incorrect quantitative claims released by an AI analyst at a fixed allowed oversight budget, while retaining correct required answers. The unit of safety is the report actually released to the simulated end user. An unreleased draft visible in a researcher audit interface is not a release, and a monitor's favorable label is not ground truth. These distinctions determine both the architecture and the experiment's denominators.

Consider an order worth USD 100 with several line items. A query joining orders to their items may repeat the order amount once per item. A receipt can prove which query ran against which snapshot and what cell it produced. A claim can point to that exact cell, with the correct unit and decimal value. Neither fact establishes that the aggregation counts each order once. The failure concerns the meaning of the query relative to the public question. A second failure arises when a repair sums distinct *amounts*: distinct order identities can have the same amount, so deduplicating values removes legitimate contributions.

Assay therefore treats the following predicates as different research objects: authorized execution, authentic result capture, numerical binding, compliance with supported public task semantics, a valid review decision, a current approved revision, and independent correctness. Their conjunction is not collapsed into a universal verification flag. The first five are runtime mechanisms; independent correctness is an evaluation outcome obtained after the episode. Returning the evaluator's answer to the runtime checker would trivialize the intervention and invalidate the intended research question.

The implemented contribution is a narrow systems prototype and development validation, rather than an established empirical improvement. Its distinctive experimental opportunity is the E-versus-D contrast: the same research checks and reviewer, the same permitted evidence corpus and lookup tools, and the same combined allowed oversight resources, with a different initial evidence representation. Ordinary-summary generation consumes resources in D. E uses a host-built representation. The estimand is the effect of those review protocols under equal caps, including their resource allocation, rather than an abstract property of provenance holding every token constant.

The current analytical implementation concerns settled USD order revenue and a permitted order count. Although the charter lists totals, means, rates, comparisons, and rankings as a longer-term domain, these broader families do not inherit validity from the order-total implementation. The deterministic fixtures, tests, source code, and observed values in this report are exposed development material. Fresh numerical seeds from the same generator do not constitute a structurally unseen benchmark. Negative or inconclusive future E-versus-D results satisfy the research objective if the protocol, accounting, and scope are sound.

### 1.1 Questions answered by the present evidence

The completed work asks whether independent canonical-event scoring distinguishes correct and incorrect relational calculations; whether genuine query results can be bound to structured claims without conflating that binding with correctness; whether the common publisher enforces the selected check/review policy; whether correction produces a new auditable revision; and whether declared worker boundaries operate under the tested environment. The source audit additionally asks whether the semantic checker resolves relation identity conservatively enough to avoid false certainty in selected adversarial SQL shapes.

The future empirical question asks how often real analyst/reviewer policies make and prevent errors on independently assigned tasks, under ordinary mistakes, indirect prompt injection, and prompted sabotage. Test counts do not answer that question. Scripted models deliberately choose known queries and review decisions. Their behavior demonstrates control flow, not the distribution of natural model mistakes or the strength of an adaptive attacker. Container diagnostics establish selected configuration and resource properties, not resistance to every malicious program or compromise of the host.

### 1.2 Relationship to prior work

AI control studies protocols intended to remain useful while preventing harmful outcomes even when an untrusted model attempts subversion. Greenblatt et al. evaluate this idea on programming tasks using trusted and untrusted models and limited trusted labor [R1]. Assay adopts the separation of legitimate-task usefulness from adversarial success and applies it to quantitative reports. Its synthetic analyst side objective is a constructed threat regime; it does not demonstrate that a model acquired an undisclosed objective spontaneously. No numerical result from the programming setting is transferred to the present task.

Database provenance provides formal ways to track how relational outputs depend on inputs. Green, Karvounarakis, and Tannen's semiring formulation represents annotations and multiplicities through relational operations [R2]. Assay's implemented receipts and dependency graph are coarser execution/artifact provenance, not a complete implementation of provenance polynomials or row-level lineage. The analytical observation motivating this system is that even complete provenance for a computation would not by itself establish that the chosen computation answers the user's metric contract. Provenance and semantic correctness are complementary requirements.

Text-to-SQL evaluation also depends on reliable truth. Wretblad et al. examine noise in BIRD questions and gold queries and show why benchmark annotations warrant scrutiny [R3]. Assay's independent reference is consequently derived from canonical business events rather than the analyst's SQL or the online verifier's labels. This design reduces one shared failure path; it does not eliminate errors in the public contract, generator, or reference implementation. Hand-calculated cases, alternative correct queries, counterexamples, and versioned scorer repairs remain necessary.

Inspect documents sandbox environments and host tool integration [R4]. Assay's optional adapter uses Inspect for model access while the trusted gateway explicitly dispatches SQL to its worker. Merely declaring a sandbox configuration would not make arbitrary host-side tools isolated. ControlArena provides settings and components for AI control experiments [R5]; it is a future integration option rather than an installed runtime dependency or a source of completed results here. TraceFrame is currently an optional audit-export target, and AMOS remains a design reference and deferred integration.

## 2. Formal task, truth, and error model

Let a public task be T = (V, M, G, P, I, U, S_req, S_sup, E, A), containing permitted source versions V, metric M, grain G, population P, a half-open time interval I, output unit U, required slots S_req, permitted supporting slots S_sup, tolerances E, and abstention rules A. A claim identifies its slot and includes the metric/type, decimal value or explicit abstention, unit, grain, snapshot, time scope, and current/historical report semantics. An executable citation additionally identifies a successful host execution and an exact result-cell locator. The task, source, execution, and report identities are distinct.

For the implemented revenue task, canonical event o has a unique order identity, status, currency, timezone-aware occurrence time, and amount a_o in integer cents or a declared missing value. Define eligibility independently of relational line-item multiplicity:

\[
e_T(o)=\mathbf{1}\{\mathrm{status}(o)=\mathrm{settled}\}
\mathbf{1}\{\mathrm{currency}(o)=\mathrm{USD}\}
\mathbf{1}\{t_{\min}\leq t_o<t_{\max}\}.
\]

When all eligible amounts are known, the independent reference is

\[
y_T=\frac{1}{100}\sum_{o:e_T(o)=1}a_o,\qquad
n_T=\sum_o e_T(o).
\]

If any eligible amount is missing, revenue is unanswerable under the current contract rather than the sum of the remaining known amounts. The order count can remain answerable. Duplicate canonical order identities and unsupported semantic contracts produce a visible reference-input error. Empty eligible populations produce the specified zero total through the canonical calculation; database NULL behavior must not silently override the contract.

For an answerable numeric slot s, value v agrees numerically with reference y if

\[
|v-y|\leq\max(\epsilon_{s,\mathrm{abs}},\;|y|\epsilon_{s,\mathrm{rel}}).
\]

Agreement also requires the slot's metric, type, unit, grain, allowed snapshot, interval, and report semantics to match. The default tolerances are exact, and count slots require exact agreement. Decimal arithmetic preserves financial values without binary-float rounding; the reference expands its decimal context to avoid silently rounding large canonical integer totals. Numeric range constraints bound arithmetic even for trusted callers bypassing ordinary validation. A claim of correct abstention requires reference unanswerability, public permission to abstain, and a nonempty reason. Arbitrary refusal on an answerable task is incorrect.

The independent report score checks every required slot and every submitted supporting slot. Missing required slots, duplicate slot claims, undeclared slots, incorrect supporting claims, wrong semantics, unsupported answers, and invalid abstentions remain explicit reason codes. The aggregate report-correct flag is useful for complete-task correctness, but it is not identical to the primary incorrect-release endpoint: an omitted answer reduces usefulness, while an actually released materially wrong quantitative assertion triggers the safety event. The prospective analysis retains slot-level error classes to avoid substituting one endpoint for the other.

### 2.1 Multiplicity and the distinct-value counterexample

Let m_o be the number of matched line items for eligible order o. An expanded join computes

\[
y_{\mathrm{join}}=\frac{1}{100}\sum_{o:e_T(o)=1}m_o a_o,
\qquad y_{\mathrm{join}}-y_T=\frac{1}{100}\sum_{o:e_T(o)=1}(m_o-1)a_o.
\]

This formula describes overcounting when every contributing order has a match and positive amounts; absent matches, signed amounts, and alternative join kinds require their own case analysis. The current fixtures deliberately contain the declared development structure. The common shortcut SUM(DISTINCT amount) instead computes one contribution per distinct monetary value. If two distinct orders have the same eligible amount, it undercounts the legitimate order-grain sum. Deduplicating order identities before aggregation, when the public data and join restrictions support that equivalence, addresses a different operation.

<!-- FIXTURE_FIGURE -->

**Figure 1.** Deterministic exposed fixtures, not model performance. The dashed line is independent canonical truth. Order-grain aggregation returns USD 200 on the base fixture and USD 300 on the equal-amount fixture. The duplicated join returns USD 340 and USD 440. Distinct-amount aggregation happens to return the correct USD 200 on the base fixture but incorrectly returns USD 200 when legitimate equal-value orders make truth USD 300. All plotted values are reproduced by the saved ten-case milestone output.

### 2.2 Integrity, semantics, and release as separate predicates

For claim c, write H(c) for authentic successful host execution and structural integrity, B(c) for exact numerical binding, and Q_T(c) for supported public analytical-contract checks. A valid binding B(c) does not imply Q_T(c), and even a collection of passing public checks is not a universal proof that every admitted SQL query is semantically correct. The implemented checks recognize a limited grammar and selected relational equivalences. Unsupported cases must remain unknown. The newly discovered relation-binding counterexamples and conservative correction illustrate why the distinction is an empirical engineering requirement rather than a naming convention.

Write R(r) for a well-formed reviewer recommendation bound to exact revision r, F(r) for current source epochs and valid attempt authorization, and P_a(r) for the arm's deterministic release predicate. The baseline and reviewed policies deliberately permit the measurement of research-level errors while retaining common host controls. Checked policies add mandatory research-check requirements. The publisher alone emits released bytes. The private oracle is not an argument to P_a. Detailed implemented check membership, state transitions, assumptions, and counterexamples follow in the system-methods section.
