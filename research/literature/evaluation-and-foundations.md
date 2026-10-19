# Evaluation, evidence, and trusted-enforcement foundations

Reviewed October 19, 2026. These twelve primary works complement the control and
database memos. This is a targeted conceptual comparison, not a replication or a
claim to have checked every proof. Inspection depth is stated for each entry.
The final Assay implications are our analysis, not results established by the
cited authors about this repository.

## E1. On the Foundations of Noise-free Selective Classification

**Ran El-Yaniv and Yair Wiener. JMLR 11:1605-1641, 2010.**
[Primary publication](https://jmlr.org/papers/v11/el-yaniv10a.html).
Inspected publication abstract and PDF's selective-classification definitions.
The paper formalizes selection with rejection and studies the risk/coverage
tradeoff under noise-free assumptions. Those guarantees do not transfer to
adversarial analytical agents. Assay should cite this established distinction and
explain why its assigned-episode incorrect-release rate and required-slot coverage
are different from conditional classification error and selection coverage.

## E2. SelectiveNet: A Deep Neural Network with an Integrated Reject Option

**Yonatan Geifman and Ran El-Yaniv. ICML 2019, PMLR 97:2151-2159.**
[Primary publication](https://proceedings.mlr.press/v97/geifman19a.html).
Inspected proceedings abstract and bibliographic record. The model learns
prediction and selection together, evaluated through risk/coverage tradeoffs.
This is a relevant baseline concept, not an implemented SQL or publication
protocol. Assay must compare abstention behavior and utility rather than treat
refusing every answer as a successful safety intervention.

## E3. Deep Reinforcement Learning at the Edge of the Statistical Precipice

**Rishabh Agarwal, Max Schwarzer, Pablo Samuel Castro, Aaron Courville, and
Marc G. Bellemare. NeurIPS 2021.**
[Primary proceedings](https://papers.nips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html).
Inspected proceedings abstract and bibliographic record.
The study examines uncertainty from small-run benchmark evaluations and proposes
interval estimates, performance profiles, and more robust aggregate summaries.
It does not validate Assay's proposed twelve-template bootstrap. Assay must
justify its own independent sampling unit, preserve paired arm assignments,
report failures and intervals, and test interval behavior when errors are sparse.

## E4. The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing

**Rotem Dror, Gili Baumer, Segev Shlomov, and Roi Reichart. ACL 2018:1383-1392.**
[Primary publication](https://aclanthology.org/P18-1128/),
[paper](https://aclanthology.org/P18-1128.pdf).
Inspected publication abstract and PDF discussion of test selection and scope.
The paper explains why experimental structure and the evaluation statistic must
determine test choice. It explicitly excludes the broader multiple-dataset
replicability problem from its scope. It is not a citation that licenses a generic
t-test for Assay. Freeze the estimand, pairing, clustering, interval, and joint
success rule before outcomes are inspected; justify them for the actual design.

## E5. Enabling Large Language Models to Generate Text with Citations (ALCE)

**Tianyu Gao, Howard Yen, Jiatong Yu, and Danqi Chen. EMNLP 2023:6465-6488.**
[Primary publication](https://aclanthology.org/2023.emnlp-main.398/).
Inspected proceedings abstract and bibliographic record.
ALCE evaluates generation with retrieved citations using distinct fluency,
correctness, and citation-quality measures. A citation's presence does not
establish complete support. Assay similarly separates a reference's authenticity
from analytical entailment, but operates on executable result cells and metric
contracts. ALCE does not supply an oracle for SQL population or grain semantics.

## E6. FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation

**Sewon Min et al. EMNLP 2023:12076-12100.**
[Primary publication and complete author list](https://aclanthology.org/2023.emnlp-main.741/).
Inspected proceedings abstract and bibliographic record. FActScore decomposes
generated text into atomic factual claims and evaluates their support relative to
a knowledge source. It motivates claim-level reporting, but factual precision is
not required-answer completeness. Assay's declared required/supporting slots and
independent completeness denominator address a distinct measurement obligation;
they are not evidence that unrestricted prose extraction has been solved.

## E7. Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting

**Miles Turpin, Julian Michael, Ethan Perez, and Samuel R. Bowman. NeurIPS 2023.**
[Primary proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract-Conference.html).
Inspected proceedings abstract and biasing-feature examples. The authors show
that explanations can omit experimentally introduced influences on answers.
This does not establish that every explanation is false or that an evidence-view
reviewer is better. It supports testing summary fidelity and using host-captured
queries/results as evidence independent of an analyst's narrative. Assay needs
an explicit ablation to establish whether representation actually helps.

## E8. The Protection of Information in Computer Systems

**Jerome H. Saltzer and Michael D. Schroeder. Proceedings of the IEEE 63(9), 1975.**
[Author-hosted primary paper](https://web.mit.edu/Saltzer/www/publications/protection/),
[design principles](https://web.mit.edu/Saltzer/www/publications/protection/Basic.html).
Inspected introductory material and protection principles. Complete mediation,
least privilege, and conservative defaults are established security ideas.
Assay's single publisher, SQL capability restriction, and withholding on unknown
obligations instantiate such principles. Their presence is not an original
security principle or a proof that every release path is mediated. Analyze
revision changes, stale sources, cancellation, and bypass surfaces explicitly.

## E9. Proof-Carrying Code

**George C. Necula. POPL 1997.**
[Author's bibliography and publication status](https://people.eecs.berkeley.edu/~necula/papers.html),
[primary paper, academic mirror](https://www.cs.tufts.edu/comp/150CMP/papers/necula97pcc.pdf).
Inspected abstract, introduction, and the certification/validation architecture.
PCC separates an untrusted producer from a consumer checking a proof against a
specified safety policy. Assay's receipts and three-valued semantic recognizer
are not formal proof objects with PCC's adequacy results. Do not call the current
system proof-carrying SQL or claim a soundness guarantee on the strength of an
analogy. The useful comparison is which obligations are explicit and who is
trusted to validate them.

## E10. Provenance-Aware Storage Systems

**Kiran-Kumar Muniswamy-Reddy, David A. Holland, Uri Braun, and Margo Seltzer.
USENIX ATC 2006.**
[Official record](https://www.usenix.org/conference/2006-usenix-annual-technical-conference/provenance-aware-storage-systems),
[primary full text](https://www.usenix.org/legacy/events/usenix06/tech/full_papers/muniswamy-reddy/muniswamy-reddy_html/index.html).
Inspected abstract, introduction, provenance requirements and opaque-input
limitations. PASS collects and maintains provenance as storage metadata, coupling
it to the data lifecycle. Assay does not introduce durable artifact provenance or
its consistency problem. Its host-level evidence store is also narrower than
system-wide capture. Inputs or dependencies never observed by the trusted system
cannot become authenticated merely because an output has a hash.

## E11. DataHub: Collaborative Data Science & Dataset Version Management at Scale

**Anant Bhardwaj, Souvik Bhattacherjee, Amit Chavan, Amol Deshpande, Aaron J.
Elmore, Samuel Madden, and Aditya Parameswaran. CIDR 2015.**
[Official paper](https://www.cidrdb.org/cidr2015/Papers/CIDR15_Paper18.pdf).
Inspected abstract, introduction and proposed version-management architecture.
The paper proposes a dataset version-control substrate and collaboration
platform, including branching, merging and querying versions. It is not evidence
that Assay's epoch/freshness protocol is new, nor a measured benchmark for that
protocol. Assay should identify the additional authorization property it needs
when an already approved result becomes stale; retaining a version and deciding
whether that version is still authorized for current use are distinct operations.

## E12. Layering in Provenance Systems

**Kiran-Kumar Muniswamy-Reddy, Uri Braun, David A. Holland, Peter Macko, Diana
Maclean, Daniel Margo, Margo Seltzer, and Robin Smogor. USENIX ATC 2009.**
[Primary full text](https://www.usenix.org/legacy/event/usenix09/tech/full_papers/muniswamy-reddy/muniswamy-reddy_html/index.html).
Inspected introduction, layered architecture overview and conclusion. The paper
integrates provenance across applications, local storage and network storage,
rather than treating each layer's history as an isolated record. This is relevant
to Assay's cross-layer query/result/claim/review/release chain. Capturing that
chain remains different from establishing the analytical truth of its contents.
Assay should define which dependency edges are recorded, which are revalidated
at release, and which trusted assumptions remain outside the captured history.

## Consequences for the paper's measurements

Our proposed reporting discipline, derived for Assay's task rather than copied
from a classifier benchmark, uses three separate denominators:

1. Incorrect releases per assigned episode, including known withholding.
2. Correct required slots released per assigned required slot, allowing only
   independently justified contract-authorized abstention as correct.
3. Incorrect releases per confirmed release, undefined when nothing releases.

Report release frequency as well. With variable required-slot counts, the first
two measures are not algebraic complements. Missing release states require
identification bounds; confidence intervals address a separate sampling question.
Numeric seed variants sharing one template do not create independent structural
tasks. These are design conclusions for the present repository, not guarantees
from any one of the papers above.
