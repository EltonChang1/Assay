# Data, provenance, SQL verification, and analytical-agent literature

**Purpose.** Identify the prior work that determines what Assay can claim about evidence-backed quantitative answers, SQL semantics, abstention, and evaluation. The useful research goal is to test whether a release protocol prevents incorrect quantitative publication while retaining required correct answers under a fixed combined oversight budget. Authentic execution and a plausible explanation do not settle that question.

**Search date:** October 19, 2026. **Scope:** targeted primary-source search and backward/forward citation following; not an exhaustive systematic review of every related paper. The fourteen core records below prioritize direct conceptual or methodological overlap over citation count. Conference/publication status is recorded separately from an earlier preprint. Performance figures from these studies are deliberately not transferred to Assay.

**Inspection discipline.** “Selective full-text inspection” means the paper was opened and the indicated definitions, methods, evaluation, or limitations were examined; it does not mean every appendix was read or the artifact reproduced. No external benchmark or paid model experiment was run. Search snippets and third-party summaries were discovery aids, not evidence for technical conclusions. The strongest close studies should receive full artifact-level comparison before a submission claims superiority.

## Main finding and contribution boundary

The present manuscript's related work is too narrow for a conference submission. Provenance has a substantial formal history; SQL equivalence and counterexample generation are established fields; current studies already verify SQL without a gold query at inference time and combine verification with abstention. A 2026 preprint also explicitly frames structured-data reliability in terms of valid evidence paths. Assay should not present any of those ideas by itself as a new contribution.

The more defensible candidate contribution is the **joint protocol**: explicit business metric contracts; distinct execution, numerical-binding, semantic-check, review, and release predicates; an external publisher bound to exact report revision and released bytes; and an equal-total-budget comparison of ordinary versus structured evidence review. This is a positioning inference from the reviewed work, not a proof of novelty. The current zero-submission development pilot does not demonstrate that this protocol improves model safety or usefulness.

## Fourteen core papers

### D01. Why and Where: A Characterization of Data Provenance

- **Authors/year/status:** Peter Buneman, Sanjeev Khanna, Wang-Chiew Tan; 2001; peer-reviewed ICDT 2001, LNCS 1973, pp. 316–330.
- **Primary sources:** [author-hosted paper](https://homepages.inf.ed.ac.uk/opb/papers/ICDT2001.pdf), [university copy with publication metadata](https://www.research.ed.ac.uk/files/16509989/Why_and_Where_A_Characterization_of_Data_Provenance.pdf), [DOI](https://doi.org/10.1007/3-540-44503-X_20).
- **Inspected:** abstract, relational representation, witness/derivation definitions, where-provenance rewriting limitations, conclusion; selective full-text inspection.
- **Method and result:** Distinguishes data contributing to an output's existence from source locations supplying output values, with formal treatment for a query language covering positive relational operations. It also identifies difficulties making where-provenance invariant under equivalent rewrites.
- **Assay overlap/gap:** This is foundational prior art for the distinction between “where did this value originate?” and richer derivation information. Assay's execution/artifact DAG and exact result-cell citations are substantially coarser than a complete database-provenance calculus. Neither system's provenance definition alone establishes that a chosen query implements the user's intended metric. Cite this work when defining provenance terminology, not as evidence that Assay implements its algorithms.

### D02. Provenance Semirings

- **Authors/year/status:** Todd J. Green, Grigoris Karvounarakis, Val Tannen; 2007; peer-reviewed PODS 2007.
- **Primary sources:** [author-hosted paper](https://web.cs.ucdavis.edu/~green/papers/pods07.pdf), [DOI](https://doi.org/10.1145/1265530.1265535).
- **Inspected:** Sections 2–4, especially K-relations, bag semantics, homomorphisms, and provenance polynomials; selective full-text inspection. Recursive Datalog proofs were not audited.
- **Method and result:** Annotates tuples with elements of a commutative semiring; projection/union add annotations and joins multiply them. Polynomial annotations retain how input tuples contribute, including multiplicity, rather than merely listing sources.
- **Assay overlap/gap:** This supplies a principled context for the order-grain/multiplicity argument. Assay's authenticated receipt is not a provenance polynomial, and its dependency index does not expose every contributing row or coefficient. The paper should explain that its linear coefficient proposition is a narrow task-specific argument grounded in established bag semantics. Provenance of an incorrect computation can still be faithfully recorded; checking the business contract is an additional obligation.

### D03. Cosette: An Automated Prover for SQL

- **Authors/year/status:** Shumo Chu, Chenglong Wang, Konstantin Weitz, Alvin Cheung; 2017; CIDR 2017 research paper. Distinguish this from the separate SIGMOD 2017 demonstration.
- **Primary sources:** [official CIDR paper](https://www.cidrdb.org/cidr2017/papers/p51-chu-cidr17.pdf), [author project](https://cosette.cs.washington.edu/).
- **Inspected:** architecture, constraint-based counterexample construction, supported-feature limitations, proof-assistant path; selective full-text inspection.
- **Method and result:** Combines symbolic finite relations and a constraint solver for inequivalence witnesses with a separate K-relation/proof-assistant route for validating equivalence. Failure to find a bounded counterexample does not establish equivalence; proof tactics and supported syntax impose limits.
- **Assay overlap/gap:** This is mandatory comparison for claims about SQL verification. Assay's syntax/structure recognizer is not an automated equivalence prover and has no comparable soundness proof. Cosette compares two formal programs; Assay additionally studies the contract-to-claim-to-publication chain and a model oversight protocol. A conference paper should state precisely which query families Assay establishes and which return `unknown`, rather than borrowing the stronger meaning of “verified SQL.”

### D04. VeriEQL: Bounded Equivalence Verification for Complex SQL Queries with Integrity Constraints

- **Authors/year/status:** Yang He, Pinhan Zhao, Xinyu Wang, Yuepeng Wang; 2024; *Proceedings of the ACM on Programming Languages* 8, OOPSLA1, article 132.
- **Primary sources:** [author-hosted published paper](https://pinhanzhao.com/papers/oopsla24.pdf), [arXiv record](https://arxiv.org/abs/2403.03193).
- **Inspected:** formal bounded-equivalence definition, algorithm, attribute-renaming discussion, evaluation outcomes, limitations; selective full-text inspection.
- **Method and result:** Encodes SQL on symbolic tuples in SMT, including integrity constraints and features such as sorting and `CASE`. Its bounded claim quantifies over databases satisfying a schema/constraint set with at most a specified number of tuples per relation. Large-only counterexamples can escape practical bounds.
- **Assay overlap/gap:** Provides a stronger baseline for semantic-equivalence coverage and explicit handling of keys, duplicate multiplicity, and constraints. Assay must separate finite-fixture agreement, a bounded equivalence result, and an unrestricted theorem. Assay does not currently integrate VeriEQL. Its independent canonical event oracle answers a particular business task; it cannot substitute for formal query equivalence on all admitted data.

### D05. Test Data Generation for Complex SQL Queries

- **Authors/year/status:** Sunanda Somwase, Parismita Das, S. Sudarshan; 2025; *Proceedings of the ACM on Management of Data* 3(6), article 367, pp. 1–26; author publication list identifies SIGMOD 2026 presentation. Earlier preprint title: *Data Generation for Testing Complex Queries* (2024).
- **Primary sources:** [author publication list](https://www.cse.iitb.ac.in/~sudarsha/pubs.html), [DOI](https://doi.org/10.1145/3769832), [inspected preprint](https://arxiv.org/pdf/2409.18821), [XData project](https://www.cse.iitb.ac.in/infolab/xdata/).
- **Inspected:** preprint abstract and architecture/method portions; author metadata. The ACM final PDF could not be opened; final-version algorithmic changes were not checked.
- **Method and result:** Extends mutation-directed test generation to more complex SQL, addressing limitations of earlier XData query coverage and comparing non-equivalence detection with existing approaches.
- **Assay overlap/gap:** Assay's small duplicate-join and distinct-value fixtures are useful regression witnesses, but query-directed discriminating database generation is established prior work. A stronger Assay benchmark should systematically kill declared semantic mutations and report uncovered classes. Neither a mutation suite nor a changed random seed alone establishes a structural holdout or universal correctness.

### D06. Semantic Evaluation for Text-to-SQL with Distilled Test Suites

- **Authors/year/status:** Ruiqi Zhong, Tao Yu, Dan Klein; 2020; peer-reviewed EMNLP 2020, pp. 396–411.
- **Primary sources:** [ACL publication record](https://aclanthology.org/2020.emnlp-main.29/), [paper](https://aclanthology.org/2020.emnlp-main.29.pdf).
- **Inspected:** problem definition, implication chain, neighbor mutations, database sampling/distillation, evaluation setup; selective full-text inspection.
- **Method and result:** Constructs compact database suites chosen to distinguish a reference SQL query from nearby mutations. It formalizes semantic correctness as agreement on all databases, while test-suite agreement is an approximation and is weaker. The authors create suites before obtaining model predictions for evaluation.
- **Assay overlap/gap:** Direct support for the distinction between accidental agreement on one fixture and structural correctness. It also suggests a disciplined freeze: construct discriminating tests before inspecting confirmation model outputs. The method relies on a reference program; Assay derives task truth from canonical events. That independence reduces shared implementation failure but still needs adversarial tests of generator, contract, and scorer. Do not characterize passing Assay regressions as semantic-equivalence proof.

### D07. Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark

- **Authors/year/status:** Niklas Wretblad, Fredrik Gordh Riseby, Rahul Biswas, Amin Ahmadi, Oskar Holmström; 2024; peer-reviewed ACL 2024, Volume 2: Short Papers, pp. 356–369.
- **Primary sources:** [ACL publication record](https://aclanthology.org/2024.acl-short.34/), [paper](https://aclanthology.org/2024.acl-short.34.pdf).
- **Inspected:** annotation approach, domain/noise tables, corrected-dataset comparison, join-error examples, resource limitations; selective full-text inspection.
- **Method and result:** Audits selected BIRD domains for question and gold-query noise, then compares models on original and corrected variants. Gold-label corrections can change model rankings, so a generated/reference disagreement is not automatically a model error.
- **Assay overlap/gap:** Strong motivation for independent truth, explicit ambiguity/unanswerability policy, versioned scorer repair, and preservation of evaluation errors. The audit is scoped to inspected domains and conditions; it does not certify all BIRD items or imply Assay's private oracle is error-free. A valid Assay evaluation needs independent review of public metric wording, canonical events, arithmetic, and reason codes, not just a separate module bearing an “oracle” name.

### D08. SpotIt: Evaluating Text-to-SQL Evaluation with Formal Verification

- **Authors/year/status:** Rocky Klopfenstein, Yang He, Andrew Tremante, Yuepeng Wang, Nina Narodytska, Haoze Wu; 2026; published ICLR 2026 conference paper. Distinguish the earlier 2025 preprint/workshop version.
- **Primary sources:** [official proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/70e692da44c19710386648694e2b899b-Abstract-Conference.html), [conference paper](https://proceedings.iclr.cc/paper_files/paper/2026/file/70e692da44c19710386648694e2b899b-Paper-Conference.pdf).
- **Inspected:** three-phase algorithm, bounded checks, counterexample validation/reuse, evaluation motivation; selective full-text inspection.
- **Method and result:** Extends bounded SQL equivalence checking for text-to-SQL evaluation, searches for differentiating databases, and re-executes witnesses to reject spurious results caused by approximations or nondeterminism. Its analysis also distinguishes flawed gold queries and ambiguous questions from faulty generated queries.
- **Assay overlap/gap:** This is a close and recent comparator for evaluation validity. Assay should similarly validate counterexamples in the actual dialect and track unsupported/time-out outcomes. SpotIt compares candidate and reference SQL; Assay's runtime checker uses a narrow public metric contract and its independent scorer is outside release authority. That difference must be explicit. Failure to obtain a witness is not unrestricted proof.

### D09. Developing and Benchmarking Verification Algorithms to Improve Text-to-SQL Generation

- **Authors/year/status:** Tarfah Alrashed, Madhup Sukoon, David R. Karger, Natasha Noy; 2026; *Proceedings of the VLDB Endowment* 19(11), pp. 3732–3744.
- **Primary source:** [official published paper](https://www.vldb.org/pvldb/vol19/p3732-alrashed.pdf), [DOI](https://doi.org/10.14778/3836663.3836721).
- **Inspected:** Sections 1–4, verifier definitions, round-trip/synthetic-execution algorithms, selective-generation discussion; selective full-text inspection. Artifact not reproduced.
- **Method and result:** Defines inference-time verification without gold SQL. Round-Trip Critique reverse-translates SQL independently before comparing intent. Synthetic Execution Consistency generates small schema-consistent data and expected answers, then compares query execution. The paper studies benchmark auditing and selective generation.
- **Assay overlap/gap:** The closest reviewed inference-time SQL-verification comparison: Assay cannot claim that a separate SQL verifier, independent review context, synthetic execution, or abstention is new. Its narrower contract can reduce natural-language ambiguity, while its release gate and exact revision/byte identity address additional obligations. A future study should include an appropriately budgeted direct-critique or synthetic-execution baseline, or clearly explain its exclusion. These methods are empirical judges, not general semantic proofs.

### D10. TrustSQL: Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring

- **Authors/year/status:** Gyubok Lee, Woosog Chay, Seonhee Cho, Edward Choi; 2024 arXiv preprint, with inspected v3 dated June 8, 2024. An ICLR 2025 submission was located; acceptance was not verified in official proceedings, so this review does not label it an accepted ICLR paper.
- **Primary sources:** [arXiv record](https://arxiv.org/abs/2403.15879), [inspected HTML](https://arxiv.org/html/2403.15879v3).
- **Inspected:** feasible/infeasible task construction, task and reliability-score definitions, pipeline/unified models, discussion of all-abstain; selective full-text inspection.
- **Method and result:** Evaluates answering feasible questions and abstaining on infeasible ones; a user-specified penalty weights wrong answers relative to helpful correct answers. It combines infeasible-question detection, SQL generation, and SQL-error detection in pipeline baselines.
- **Assay overlap/gap:** Prior art for treating helpfulness and harmful answers jointly and exposing abstention tradeoffs. Assay should retain separate release risk, required-answer coverage, and missing outcomes even if it adds a penalty-based utility. A scalar penalty encodes preferences; it cannot establish safety independently of coverage or justify interpreting zero releases as successful oversight.

### D11. Reliable Text-to-SQL with Adaptive Abstention

- **Authors/year/status:** Kaiwen Chen, Yueting Chen, Nick Koudas, Xiaohui Yu; 2025; *Proceedings of the ACM on Management of Data* 3(1), article 69, pp. 1–30.
- **Primary sources:** [publisher record](https://doi.org/10.1145/3709719), [inspected preprint](https://arxiv.org/html/2501.10858v1), [author project](https://www.cs.toronto.edu/~koudas/reliable.html).
- **Inspected:** schema-linking/branching architecture, conformal prediction construction and assumptions, human interaction rationale; selective full-text inspection.
- **Method and result:** Uses internal model representations and conformal prediction to identify branching points in schema linking, enabling abstention or targeted human help. Its guarantees are tied to specified prediction/calibration assumptions, including exchangeability in the presented construction.
- **Assay overlap/gap:** Important prior art for reliability through abstention and limited human oversight. Schema-linking coverage is not a guarantee of whole-query correctness or accurate released prose. Assay's current API-based protocol lacks this hidden-state mechanism and proposes a different oversight-resource accounting. If comparing human/model effort, count clarification and review costs explicitly and avoid transferring the paper's component-level guarantees to Assay's release mechanism.

### D12. Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows

- **Authors/year/status:** Fangyu Lei, Jixuan Chen, Yuxiao Ye, Ruisheng Cao, Dongchan Shin, Hongjin Su, Zhaoqing Suo, Hongcheng Gao, Wenjing Hu, Pengcheng Yin, Victor Zhong, Caiming Xiong, Ruoxi Sun, Qian Liu, Sida Wang, Tao Yu; 2025; ICLR 2025 conference paper.
- **Primary sources:** [official proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/46c10f6c8ea5aa6f267bcdabcb123f97-Abstract-Conference.html), [paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/46c10f6c8ea5aa6f267bcdabcb123f97-Paper-Conference.pdf).
- **Inspected:** annotation/quality-control process, focused execution evaluation, experimental setup, Appendix A output matching; selective full-text inspection.
- **Method and result:** Evaluates enterprise workflows involving large schemas, dialects, documentation, project code, and multiple queries. Task-specific evaluators can focus on essential columns and output forms.
- **Assay overlap/gap:** A strong external-validity target, rather than evidence that a tiny synthetic revenue task reflects enterprise analysis. Adopting it would require independently validating evaluators, specifying admissible answers, excluding private truth from runtime tools, and freezing task selection. Assay's exact required-slot and supporting-claim policy also differs from evaluators that ignore nonessential columns. Benchmark success and incorrect released-claim risk are distinct outcomes.

### D13. DA-Code: Agent Data Science Code Generation Benchmark for Large Language Models

- **Authors/year/status:** Yiming Huang, Jianwen Luo, Yan Yu, Yitong Zhang, Fangyu Lei, Yifan Wei, Shizhu He, Lifu Huang, Xiao Liu, Jun Zhao, Kang Liu; 2024; peer-reviewed EMNLP 2024, pp. 13487–13521.
- **Primary sources:** [ACL publication record](https://aclanthology.org/2024.emnlp-main.748/), [paper](https://aclanthology.org/2024.emnlp-main.748.pdf).
- **Inspected:** task construction, Sections 3.2–3.4 scoring, cross-validation/red-team testing, execution environment; selective full-text inspection.
- **Method and result:** Provides multi-file, executable Python/SQL data-science tasks and customized evaluators for tables, charts, and text. Annotators cross-check task setup and probe evaluator false positives/negatives.
- **Assay overlap/gap:** Useful model for an executable benchmark and scorer validation. Its task score is not a revision-bound authority to publish every quantitative assertion; partial artifact matching can differ from Assay's all-submitted-supporting-claims policy. Assay needs more structurally diverse tasks and natural-agent completions before claiming generality. Neither the use of Docker nor task-level evaluator success establishes resistance to adversarial code or prompt injection.

### D14. TrustDABench: Benchmarking Reliability and Robustness of LLMs for Structured Data Analysis

- **Authors/year/status:** Boshen Shi, Yize Liu, Chen Zhao, Ce Chi, Zhendong Wang, Xing Wang, Junlan Feng; 2026; arXiv preprint first posted August 25, 2026. Peer-reviewed acceptance not verified.
- **Primary sources:** [arXiv record](https://arxiv.org/abs/2608.24145), [inspected HTML](https://arxiv.org/html/2608.24145v1), [author repository](https://github.com/Skyorca/TrustDABench).
- **Inspected:** task formulation, operator design, construction/validation protocol, evaluation dimensions, appendix validation fields; selective full-text inspection. Data and model results not reproduced.
- **Method and result:** Separates evidence-breaking perturbations, where refusal/clarification is appropriate, from answer-preserving table transformations. It defines 19 perturbation operators and reports 2,340 human-verified perturbed cases, motivated by valid question-to-data evidence paths.
- **Assay overlap/gap:** Very close conceptual prior art: evidence-path framing and recognition of executable-but-unsupported analysis are not distinctive by themselves. Assay adds an enforced publication boundary and a proposed budget-matched oversight intervention; its present evidence cannot establish comparative advantage. This preprint supplies useful candidate structural holdouts, but benchmark validity, licenses, leakage, and independence must be checked before adoption.

## Supporting work located and screened

These are relevant extensions of the reading list. Their metadata/abstracts or selected passages were checked; they did not receive the same method-level examination as the fourteen core records, except where noted. Do not describe them as fully reviewed or reproduced.

| Work | Verified primary source and status | Why it matters |
| --- | --- | --- |
| *Data Generation for Testing and Grading SQL Queries*, Bikash Chandra, Bhupesh Chawda, Biplab Kar, K. V. Maheshwara Reddy, Shetal Shah, S. Sudarshan | [VLDB Journal 24(6):731–755 (2015)](https://link.springer.com/article/10.1007/s00778-015-0395-0); [author preprint](https://arxiv.org/pdf/1411.6704). Aggregation-on-joins, mutant-killing, and tuple-assignment limitations inspected. | Earlier XData foundations; duplicate/aggregate testing predates LLM agents. |
| *Testing Database Engines via Pivoted Query Synthesis*, Manuel Rigger, Zhendong Su | [OSDI 2020 official record](https://www.usenix.org/conference/osdi20/presentation/rigger); [paper](https://www.usenix.org/system/files/osdi20-rigger.pdf). Abstract and containment-oracle mechanism inspected. | DBMS implementation correctness is a separate layer from whether an analyst chose the right metric. |
| *Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs*, Jinyang Li et al. | [NeurIPS 2023 Datasets and Benchmarks paper](https://papers.nips.cc/paper/2023/file/83fc8fab1710363050bbd1d4b8cc0021-Paper-Datasets_and_Benchmarks.pdf). Primary search extraction inspected; later PDF open failed. | Original BIRD task context: data values, domain knowledge, and efficiency. Do not conflate it with later gold-label audits. |
| *InfiAgent-DABench: Evaluating Agents on Data Analysis Tasks*, Xueyu Hu et al. | [ICML 2024 / PMLR 235:19544–19572](https://proceedings.mlr.press/v235/hu24s.html). Publication record and abstract inspected; PDF retrieval failed. | Closed-form outputs for end-to-end CSV analysis; useful upstream task source for TrustDABench. |
| *DSBench: How Far Are Data Science Agents from Becoming Data Science Experts?*, Liqiang Jing et al. | [ICLR 2025 official proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/50e9ad960ae78b741a6b4fea533f2eaf-Abstract-Conference.html). Abstract and paper opening inspected. | Broader multi-table and modeling tasks; useful external-validity context. |
| *ScienceAgentBench: Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery*, Ziru Chen et al. | [ICLR 2025 official proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/f12b4df26344f3be803c06b555252efe-Abstract-Conference.html). Abstract, validation rationale, conclusion inspected. | Expert validation and task-level scientific workflow assessment; avoids equating a partial task with end-to-end scientific discovery. |
| *What Predicts Correctness in Text-to-SQL? A Selective-Prediction Study* | [arXiv:2607.06799](https://arxiv.org/abs/2607.06799), July 2026 preprint; abstract screened only. | Candidate follow-up for risk–coverage curves, model judges, calibration, and unseen-schema transfer. Authors/venue and full methods need further checking before citation in the manuscript. |
| *PremiseSQL: Evaluating Premise Critique and Abstention in Text-to-SQL Systems* | [arXiv:2610.22158](https://arxiv.org/abs/2610.22158), October 15, 2026 preprint; abstract screened only. | Very recent candidate for false-premise/unanswerable questions. Not treated as an established result or a fully inspected study. |

## How this changes the paper and study

1. **Rewrite related work around obligations.** Start with provenance and multiplicity; distinguish formal program equivalence from finite execution tests; then distinguish reference-query evaluation from runtime intent verification; finally discuss selective generation and analytical agents. Explain the exact additional publication/oversight obligation after each group.
2. **Keep the central question narrow.** The current system supports a settled-revenue contract. A claim about general trustworthy data analysis requires substantially broader methods and evidence. Strong conference writing sharpens a falsifiable question and its contribution boundary; it does not enlarge the claim to fit a venue.
3. **Separate specification correctness from implementation correctness.** A canonical-event scorer can avoid sharing the runtime verifier's SQL recognizer, yet both can inherit a bad population, grain, null policy, or natural-language interpretation. Include hand-worked cases, alternative correct programs, negative examples, and an independently reviewed scorer specification.
4. **Treat `unknown` as a measured outcome.** Report syntax coverage, soundness counterexamples, false rejects of supported correct alternatives, timeouts, and unresolved cases. A withheld correct answer has a usefulness cost; a failure before a claim submission supplies no comparative review evidence.
5. **Measure the end-to-end intervention.** Budget-match summary generation, reviewer calls, correction reviews, evidence lookups, and terminal failure handling. Compare incorrect released claims and required-answer coverage on assigned episodes; supplement them with conditional error among releases and a risk–coverage curve when enough outcomes exist.
6. **Build structural tests before confirmation.** Change join cardinality, equal-value entities, missingness, empty populations, time boundaries, currencies, source aliases, nesting, and schema/representation families. Mutation-directed testing should be declared in advance. Withhold whole semantic structures from development, not merely fresh random numbers.
7. **Add close baselines before claiming an improvement.** At minimum explain how direct SQL critique, round-trip review, synthetic-execution checking, and an appropriate formal/bounded checker differ from the tested protocol. Not every prior method is compatible with every threat model; compare compatible methods or explain the concrete incompatibility and cost.
8. **Do not inflate results in the literature.** A bound on a schema-linking component is not whole-query correctness. Candidate/reference inequivalence does not identify which query matches an ambiguous question. A preprint's numerical score is a scoped report, not an established cross-domain safety property. Reproduce any adopted baseline under the frozen protocol before comparative claims.

## Remaining research limitations

This review does not establish that no prior system combines lineage, query validation, approval, and publication; workflow provenance, proof-carrying data, reproducible research, report-generation systems, data contracts, and access-control literature need additional targeted novelty checks if the final contribution claims encompass them. It also does not establish that the newest preprints are peer-reviewed. The current file prioritizes the SQL/quantitative-analysis neighborhood; AI-control, prompt-injection, experimental design, and conference-format literature are complementary workstreams.

The final-version mismatch for D05 and retrieval failures for the supporting BIRD/InfiAgent PDFs are explicit limits. No paper here is described as reproduced. The related-work map is ready to support a careful manuscript revision, while a top-conference empirical claim still requires successful frozen model episodes and independently valid held-out evaluation.
