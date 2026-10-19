# AI control, agent security, and monitoring: literature memo for Assay

**Research purpose.** Identify which parts of Assay are already established in AI control and agent-security research, and which narrower question about the correctness of released quantitative claims could support a new contribution. The useful candidate is whether executable, metric-specific evidence changes incorrect-release risk and required-answer coverage under equal allowed oversight resources. The existence of a monitor, sandbox, structured score, or approval gate is not by itself a new research contribution.

**Search and verification date: October 19, 2026.** This is a targeted narrative review of 14 particularly relevant papers, not a claim to have found every relevant publication. Searches combined AI control, untrusted monitoring, adaptive monitor attacks, sabotage evaluations, indirect prompt injection, structured monitoring, and agent evaluation. Selection prioritized primary papers with a direct threat-model or evaluation-method connection to the current manuscript. Venue checks used official proceedings, publisher records, ACL Anthology, and workshop sites. Search snippets and third-party summaries were discovery aids only. Dates below distinguish first preprint appearance, inspected version, and verified publication venue. “No archival venue verified” records this review's verification limit; it does not prove that no publication exists.

**Reading depth.** For the selected versions, the abstract and bibliographic record were inspected, together with the relevant methods, experimental definitions, selected results, and/or limitations specified below. This was not a line-by-line reading of every appendix, an independent reproduction, a code audit, or a new model experiment. Numerical results are the authors' reported results in their own settings. They are not Assay measurements or transferable deployment risk estimates.

## 1. Foundational AI control

### C01. AI Control: Improving Safety Despite Intentional Subversion

Ryan Greenblatt, Buck Shlegeris, Kshitij Sachan, and Fabien Roger. **2024, ICML**, PMLR 235:16295–16336; peer-reviewed conference paper. First preprint December 2023. The extended version inspected is arXiv v5, July 23, 2024; the paper explicitly says the ICML version is shortened and modified. [Official proceedings](https://proceedings.mlr.press/v235/greenblatt24a.html); [extended v5](https://arxiv.org/html/2312.06942v5).

**Method and supported result.** A blue team designs protocols using a strong untrusted model, a weaker trusted model, and limited high-quality trusted labor. A red team supplies a subversive policy. The APPS setting asks for useful programming solutions while preventing submission of backdoors that pass ordinary tests. Trusted monitoring, untrusted monitoring with anti-collusion measures, deferral, and trusted editing are compared. Safety concerns any successful backdoor over a simulated sequence; usefulness is measured separately with the honest model.

**Limits and Assay connection.** The extended paper discloses no train/validation split for protocol development and uses approximations to simulate large deployments. Trusted labor is simulated. Assay inherits the control framing and safety/usefulness distinction. Its per-assignment incorrect-release estimand is different from this paper's deployment-level probability and must be defined independently. Assay cannot claim to introduce AI control or untrusted monitoring.

**Inspected:** Sections 1–2, Table 2, assumptions and sampling discussion; selected monitoring descriptions.

### C02. Ctrl-Z: Controlling AI Agents via Resampling

Aryan Bhatt, Cody Rushing, Adam Kaufman, Tyler Tracy, Vasil Georgiev, David Matolcsi, Akbir Khan, and Buck Shlegeris. **2025, arXiv preprint**, v1, April 14, 2025; no archival venue verified. [Primary paper](https://arxiv.org/html/2504.10374v1).

**Method and supported result.** BashBench contains 257 multistep system-administration tasks. An adversarially scaffolded agent attempts covert malware download and execution. The authors use monitors, auditing, deferral, and resampling of suspicious actions; repeated suspicious proposals can provide evidence for intervention. The best reported protocol combines resampling with earlier-step analysis, reducing attack success from 58% to 7% with a reported 5% usefulness cost in that setup.

**Limits and Assay connection.** Results depend on attack elicitation, task environment, trajectory assumptions, and auditing. The conclusion identifies longer trajectories, broader tasks, and imperfect auditing as open questions. Assay's correction reviews are additional protocol resources and must be charged, just as resampling changes both capability and cost. A paper must distinguish prevention of a bad action from merely assigning a high suspicion score. These shell-task rates do not establish the safety of quantitative reports.

**Inspected:** Setting, protocol overview, selected result discussion, conclusion; appendix structure.

### C03. Evaluating Control Protocols for Untrusted AI Agents

Jon Kutasov, Chloe Loughridge, Yuqi Sun, Henry Sleight, Buck Shlegeris, Tyler Tracy, and Joe Benton. **2025 preprint; AAAI 2026 Trustworthy Agentic AI workshop version verified.** This is a workshop appearance, not verified AAAI main-track publication. Inspected arXiv v1, November 4, 2025. [Primary paper](https://arxiv.org/html/2511.02997v1); [official workshop listing](https://trustagenticai.github.io/AAAI2026/paper.html).

**Method and supported result.** The study compares control protocols in SHADE-Arena, then improves attacks against selected defenses. Preserving the full resampling history improves one protocol from 83% to 87% reported safety. Giving attackers more monitoring information and monitor-simulation affordances reduces the strongest resampling strategy's reported safety to 17%. Deferring consequential actions to a trusted model is more robust against their tested attacks.

**Limits and Assay connection.** The study assumes audits catch attempted side tasks and counts detection by the end of a transcript as acceptable, even if the harmful action happened earlier. This is a materially different endpoint from preventing release. Assay should treat publication as the consequential action, retain complete revision/correction history, and score actual released bytes. A favorable result against a default prompted attacker is insufficient evidence of robustness against defense-aware attacks.

**Inspected:** Sections 1–2, critical-action explanation, discussion, selected monitor prompts.

### C04. Adaptive Attacks on Trusted Monitors Subvert AI Control Protocols

Mikhail Terekhov, Alexander Panfilov, Daniil Dzenhaliou, Caglar Gulcehre, Maksym Andriushchenko, Ameya Prabhu, and Jonas Geiping. **2026, ICLR**, peer-reviewed conference paper; first preprint October 10, 2025. Inspected arXiv v2, March 2, 2026. [Official proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/54b153ad8a138f4c186f21a8b7341d5e-Abstract-Conference.html); [v2 full text](https://arxiv.org/html/2510.09462v2).

**Method and supported result.** The attacker knows the monitor and protocol and places prompt injections in the material the monitor reviews. Experiments on APPS and BashBench show substantial failures of tested monitor-dependent protocols across model pairs. Resampling can increase the number of opportunities to find a monitor-evading output. The paper's broad abstract wording must be read alongside its actual evaluated protocols.

**Limits and Assay connection.** The limitations exclude a comprehensive study of all protocols, in-depth time-travel variants, and untrusted-monitoring designs. Malicious behavior is prompted. Assay's reviewer can itself encounter adversarial summaries, SQL, evidence text, and lookup results; those are potential injection surfaces. Host-built evidence is a transport and integrity mechanism, not automatic immunity to instructions carried in its contents. Future tests should include attempts to manipulate the reviewer directly and define attacker knowledge explicitly.

**Inspected:** Threat model, evaluation overview, discussion, limitations, reproducibility statement.

## 2. Sabotage and oversight endpoints

### C05. Sabotage Evaluations for Frontier Models

Joe Benton, Misha Wagner, Eric Christiansen, Cem Anil, Ethan Perez, Jai Srivastav, Esin Durmus, Deep Ganguli, Shauna Kravec, Buck Shlegeris, Jared Kaplan, Holden Karnofsky, Evan Hubinger, Roger Grosse, Samuel R. Bowman, and David Duvenaud. **2024, technical report/arXiv preprint**, v1, October 28, 2024; institutional release October 18. No archival venue verified. [Primary paper](https://arxiv.org/html/2410.21514v1); [institutional research description](https://www.anthropic.com/research/sabotage-evaluations).

**Method and supported result.** Four mitigation-aware evaluation families cover human decision sabotage, code sabotage, sandbagging, and undermining oversight. The work measures a model's ability to achieve a harmful objective while evading a specified oversight procedure. Demonstrations use Claude 3 Opus and Claude 3.5 Sonnet. The authors' assessment of limited current sabotage risk is explicitly about those models and mitigations.

**Limits and Assay connection.** These constructed tasks test capabilities under elicitation; they do not estimate the frequency of spontaneously adopted harmful goals. Assay's prompted revenue-corruption side objective belongs to that constructed threat regime. Review agreement, monitor suspicion, success at hiding intent, and a materially wrong released answer are different outcomes. Assay should identify which is primary and avoid presenting scripted sabotage or tests as evidence of natural scheming.

**Inspected:** Abstract, threat-model/evaluation descriptions, selected results and limitations; institutional explanation of the four families.

### C06. SHADE-Arena: Evaluating Sabotage and Monitoring in LLM Agents

Jonathan Kutasov, Yuqi Sun, Paul Colognese, Teun van der Weij, Linda Petrini, Chen Bo Calvin Zhang, John Hughes, Xiang Deng, Henry Sleight, Tyler Tracy, Buck Shlegeris, and Joe Benton. **2025, arXiv preprint**, first submitted June 17; inspected v2, July 8. No archival venue verified. [Primary paper](https://arxiv.org/html/2506.15740v2).

**Method and supported result.** Seventeen complex task pairs combine a benign main goal with a harmful side goal in synthetic tool environments. Evaluation requires main-task completion, side-task completion, and evasion of monitoring. The reported best sabotage score is 27% for Claude 3.7 Sonnet under Claude 3.6 Sonnet monitoring; Gemini 2.5 Pro reaches monitor AUC 0.87 on the tested transcripts. These are different metrics with different denominators.

**Limits and Assay connection.** Models often fail the benign task; a weak attack-completion rate can therefore reflect poor agent competence. Only five of 17 pairs were publicly released to reduce contamination. Assay's universal pilot failure before submission creates the same interpretive problem more severely: zero releases cannot identify a useful oversight effect. Report benign feasibility, joint outcomes, required-answer coverage, hidden-scratchpad affordances, and contamination policy separately from attack success.

**Inspected:** Sections 1–2, monitoring result overview, discussion and dataset-release limits.

### C07. TraceGuard: Structured Multi-Dimensional Monitoring as a Collusion-Resistant Control Protocol

Khanh Linh Nguyen, Hoa Nghiem, and Tu Tran. **2026, arXiv preprint**, v1, April 5; developed in an AI-control hackathon. No archival venue verified. [Primary paper](https://arxiv.org/html/2604.03968v1).

**Method and supported result.** Five parallel LLM calls score goal alignment, constraints, reasoning, safety, and action/trace consistency; heuristic detectors and an optional intent-analysis call supplement the score. Table 2 reports attack deferral of 70.8% and honest usefulness of 93.9% at threshold 0.5 for the hybrid monitor's 519 samples. The paper also reports experiments with untrusted monitoring and separation of duties.

**Limits and Assay connection.** The authors disclose hand-tuned weights, nonadaptive attacks, limited domains, and five scoring calls per step plus possible additional analysis. Its “safety” is an attack detection/deferral measure rather than Assay's incorrect-release rate. This is close prior work for any broad claim that structured multidimensional review is new or inherently collusion-resistant. Assay's possible distinction is executable metric evidence and exact revision-bound publication under equal budgets; it needs an empirical representation comparison to support that distinction.

**Inspected:** Methods, setup, metric definitions, Table 2, discussion and limitations. Headline collusion percentages are not treated as security guarantees.

## 3. Prompt injection and evaluation construction

### C08. Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection

Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph Endres, Thorsten Holz, and Mario Fritz. **2023, ACM AISec workshop**, peer-reviewed workshop paper, pp. 79–90; DOI 10.1145/3605764.3623985. First preprint February 23; inspected arXiv v2, May 5. [Publisher record](https://doi.org/10.1145/3605764.3623985); [full preprint](https://arxiv.org/html/2302.12173v2); [official workshop](https://aisec.cc/2023/).

**Method and supported result.** The paper defines and demonstrates attacks carried by retrieved material rather than the user's direct request. Its taxonomy covers altered content, data theft, malicious tool behavior, and availability. Demonstrations use synthetic applications and local HTML with Bing Chat's sidebar; the work is qualitative rather than an estimated population attack-success rate.

**Limits and Assay connection.** The authors explicitly distinguish demonstrations from in-the-wild delivery and leave systematic repeated-generation evaluation open. For Assay, schema descriptions, comments, retrieved documents, and result text can carry attacker instructions. Keep legitimate user intent, attacker-controlled content, and trusted metadata distinct in the threat model. A credible evaluation must state exactly what the attacker may modify without allowing arbitrary corruption of the evaluator's answer.

**Inspected:** Attack taxonomy, experimental setup, demonstration types, limitations and reproducibility discussion.

### C09. InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents

Qiusi Zhan, Zhixiang Liang, Zifan Ying, and Daniel Kang. **2024, Findings of ACL**, peer-reviewed Findings paper, pp. 10471–10506; DOI 10.18653/v1/2024.findings-acl.624. [Official paper and metadata](https://aclanthology.org/2024.findings-acl.624/); [inspected full preprint v2](https://arxiv.org/html/2403.02691v2).

**Method and supported result.** A generated-and-refined benchmark supplies an agent with a user task and an adversarial tool response, then measures harmful tool behavior. It contains 1,054 cases, 17 user tools, 62 attacker tools, and direct-harm/data-stealing categories. Thirty agents are tested. The paper reports approximately 24% attack success for ReAct-prompted GPT-4 in its base setting, increasing with a fixed attack-enhancement prompt.

**Limits and Assay connection.** The limitations identify simplified single-turn interactions, attacks of at most two steps, fixed enhancement text, and limited mixing of benign and malicious content. It does not establish full-task usefulness in a multistep analyst workflow. Assay should preserve useful task data while injecting instructions, test complete trajectories, and report required-answer coverage alongside attacks. Do not use its attack-only metric as a replacement for Assay's joint safety/usefulness evaluation.

**Inspected:** Benchmark construction, evaluation overview, selected result tables, explicit limitations.

### C10. AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents

Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr. **2024, NeurIPS Datasets and Benchmarks**, peer-reviewed conference track. [Official proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html); [inspected full preprint v3](https://arxiv.org/html/2406.13352v3).

**Method and supported result.** Four stateful tool environments support 97 user tasks and 629 security cases. User-task utility and attacker success are evaluated from task-specific state/output criteria. Agents choose their own tools and execute complete tasks. The authors prefer deterministic evaluation functions partly because a prompt injection could also compromise an LLM evaluator.

**Limits and Assay connection.** Advance tool filtering is effective when legitimate and malicious tasks need different tools, but fails when necessary permissions overlap or later tool needs cannot be planned. Later papers in this memo identify additional benchmark weaknesses. Assay's incorrect SQL and correct SQL use the same read capability, so isolation alone cannot settle analytical correctness. Its independent canonical scorer is methodologically important, but needs its own validation. The environment is extensible; a fixed published attack set is not automatically adaptive.

**Inspected:** Section 3 construction and evaluation definitions, selected defenses, tool-isolation limitations.

### C11. Defeating Prompt Injections by Design (CaMeL)

Edoardo Debenedetti, Ilia Shumailov, Tianqi Fan, Jamie Hayes, Nicholas Carlini, Daniel Fabian, Christoph Kern, Chongyang Shi, Andreas Terzis, and Florian Tramèr. **2026, IEEE SaTML**, peer-reviewed conference paper; DOI 10.1109/SaTML68715.2026.00040. First preprint March 24, 2025; inspected v2, June 24, 2025. [Publisher record](https://ieeexplore.ieee.org/abstract/document/11691650); [full v2](https://arxiv.org/html/2503.18813v2).

**Method and supported result.** CaMeL separates planning from processing untrusted data, tracks data/control flow, and enforces tool-call security policies using capabilities. Version 2 reports solving 77% of AgentDojo tasks with its security guarantees, versus 84% undefended. The older v1 figure of 67% must not be silently mixed with v2.

**Limits and Assay connection.** The threat model explicitly excludes answer-only text manipulation that changes neither protected control flow nor unauthorized data flow. Policy specification, declassification, user burden, and side channels remain limitations. This gives Assay a precise potential complement: an authentic, authorized computation can still implement the wrong metric. Assay should compare security predicates carefully and avoid claiming stronger general security than CaMeL; its semantic checks cover a narrow analytical grammar, and their soundness remains conditional.

**Inspected:** Threat-model exclusions, architecture and policy overview, version-specific utility result, Section 9 limitations.

### C12. Design Patterns for Securing LLM Agents against Prompt Injections

Luca Beurer-Kellner, Beat Buesser, Ana-Maria Creţu, Edoardo Debenedetti, Daniel Dobos, Daniel Fabian, Marc Fischer, David Froelicher, Kathrin Grosse, Daniel Naeff, Ezinwanne Ozoani, Andrew Paverd, Florian Tramèr, and Václav Volhejn. **2025, arXiv preprint**, first submitted June 10; inspected v3, June 27. No archival venue verified. [Primary paper](https://arxiv.org/html/2506.08837v3).

**Method and supported result.** Six architectural patterns constrain how untrusted data reaches actions: action selection, planning before execution, map-reduce decomposition, dual LLMs, code before execution, and context minimization. Ten application case studies include a SQL agent with database access and Python execution. The work develops design arguments and tradeoffs rather than one aggregate comparative safety result.

**Limits and Assay connection.** Each security argument depends on a restricted interface and an explicit attacker capability model; restricting behavior may reduce task generality. Structured outputs alone do not prove that their semantic contents are correct. Assay should position its worker, gateway, and publication boundary in this architectural landscape, state which interfaces preserve trust boundaries, and separately justify the mathematical relation between a query and the requested metric. The paper's SQL case study is especially important prior context.

**Inspected:** Pattern definitions and tradeoffs, SQL-agent case study, selected neighboring case studies.

### C13. Indirect Prompt Injections: Are Firewalls All You Need, or Stronger Benchmarks?

Rishika Bhagwatkar, Kevin Kasa, Abhay Puri, Gabriel Huang, Irina Rish, Graham W. Taylor, Krishnamurthy Dj Dvijotham, and Alexandre Lacoste. **2025 preprint and NeurIPS 2025 Lock-LLM workshop version**; inspected arXiv v2, March 23, 2026. Workshop appearance is verified; ICLR main-track acceptance was not verified. [Primary v2](https://arxiv.org/html/2510.05244v2); [workshop paper](https://openreview.net/pdf?id=aSUHAayPml).

**Method and supported result.** A tool-input minimizer and tool-output sanitizer are evaluated on four benchmarks. Strong results on published attacks motivate an audit of benchmark construction. The authors identify attacks that overwrite essential task content, brittle success checks, and unrealistic tool-use evaluation. Version 2 adds a cascade of standard, second-order, and adaptive attacks.

**Limits and Assay connection.** Zero observed attack success on a fixed suite is not universal security. The approach assumes trusted user intent and secure tools apart from poisoned data. For Assay, an injection that deletes a necessary amount changes answerability and confounds usefulness loss with instruction following. Validate preservation of task truth, keep infrastructure failure separate, and include simple sanitizer/minimizer or constrained-interface baselines when scientifically appropriate. Its benchmark criticisms should be investigated rather than imported as assumptions about every task.

**Inspected:** Firewall definitions, benchmark critique, adaptive-attack cascade, impact/assumptions discussion.

### C14. AutoDojo: A Generative Benchmark for Evaluating Prompt Injection Defenses in LLM Agents

Xinhang Ma, Taoran Li, Chaowei Xiao, Zhiyuan Yu, Ning Zhang, and Yevgeniy Vorobeychik. **2026, arXiv preprint**, first submitted June 13; inspected v3, September 28. No archival venue verified. The earlier title was “AutoDojo: Adaptive Attacks Expose Superficial Defenses and User-Underspecification Limits in LLM Agents.” [Current version record](https://arxiv.org/abs/2606.15057v3); [full v3](https://arxiv.org/html/2606.15057v3).

**Method and supported result.** The framework generates defense-adaptive attacks across AgentDojo and AgentDyn, using black-box success feedback. It evaluates ten defenses and five target models over six task suites. Reported results show substantial differences between static and adaptive evaluations and sensitivity to task underspecification.

**Limits and Assay connection.** The authors report point estimates rather than repeated-run variance, citing expense; successful counterexamples establish vulnerability but do not identify a precise comparative deployment risk. Assay should specify adaptation budget, attacker feedback, task-contract ambiguity, model versions, and all attempts. Confirmation needs sealed structural tasks and frozen attacks/protocols; changing only numerical seeds is insufficient. Adaptive development attacks and final held-out measurement serve different purposes and should have distinct evidence records.

**Inspected:** Benchmark overview, adaptive threat model, selected results, Appendix G.3 limitations and full-results table structure.

## 4. Consequences for Assay's research claim

The following are **reviewer-facing inferences from the literature and the current manuscript**, not results measured by those papers.

| Potential Assay statement | Literature constraint | Defensible direction |
|---|---|---|
| “We introduce monitoring or AI control for agents.” | C01–C06 already establish these ideas in multiple environments. | State the quantitative-report setting and exact new obligation. |
| “Structured evidence review is novel.” | C07 studies structured multidimensional monitoring; C12 studies constrained interfaces. | Distinguish executable claim-to-cell/metric evidence from generic rubrics and test the distinction. |
| “A trusted monitor makes the system secure.” | C04 attacks the monitor's instruction/data boundary. | Treat reviewed content and lookup responses as untrusted inputs; test adaptive reviewer attacks. |
| “Authorization proves that the answer is right.” | C11 protects defined flows, while explicitly leaving some answer corruption outside scope. | Derive the separate semantic property for the public metric and show authentic-but-wrong counterexamples. |
| “We observed zero unsafe outputs.” | C06 and C13 explain competence and measurement confounds. | Always report required-answer coverage, no-submission/failure categories, and uncertainty. |
| “The attacker was unsuccessful.” | C03, C04, and C14 show sensitivity to attacker knowledge and adaptation. | State elicitation limits; use defense-aware attacks with frozen budgets and retained failures. |
| “The benchmark is independently scored.” | C09–C10 use task-specific criteria, but C13 finds scorer/data defects. | Validate the canonical oracle with hand cases, alternative correct implementations, and counterexamples. |
| “The same token cap makes review fair.” | C02 and C07 incur extra samples or scoring calls. | Include summary generation, corrections, retries, lookups, tokens, latency, and dollars in the declared resource comparison. |

The current Assay systems report is most credible when it proves or tests conditional boundaries—execution authenticity, cell binding, supported semantics, and current-revision release—and preserves the negative feasibility pilot. An eventual top-conference empirical claim would need a usable analyst path, independent outcome truth, a broad enough structural benchmark, strong relevant baselines, adversarial adaptation, and a completed comparison with uncertainty. A polished related-work section cannot substitute for those observations.

## 5. Search limits and next reading

This memo intentionally concentrates on control, sabotage, and prompt-injection methodology. It does not cover the full literature on database provenance, SQL equivalence/verification, text-to-SQL benchmark validity, statistical selective prediction, human factors, or general agent benchmarks; those are separate necessary branches for an Assay bibliography. Scalable oversight, debate, capability-based type systems, distributed deployment monitoring, and cost-sensitive evaluation warrant additional focused reading before making broad claims in those areas. The selected papers' reference lists are useful starting points, not evidence that those branches were fully reviewed here.

Venue and version checks are time-bounded. Workshop and preprint records must not be relabeled as main-conference publications. For a final submission, refresh official publication metadata and pin the exact version behind every numerical comparison, especially CaMeL and AutoDojo. No paid-model calls or experiments were performed for this review.
