# TraceFrame Safety Lab

**Planning package — runtime implementation has not started.**

Completed and reviewed October 16, 2026.

A proposed AI safety research and systems engineering project that evaluates whether executable checks and data provenance reduce unsupported conclusions released by an AI data analyst.

Start with [the end-to-end implementation plan](IMPLEMENTATION_PLAN.md). Use [the implementation backlog](IMPLEMENTATION_BACKLOG.md) to execute it and [the reuse notes](REUSE_NOTES.md) to integrate existing TraceFrame and AMOS work accurately.

The package covers research hypotheses, architecture, threat boundaries, schemas, data generation, independent scoring, five comparison methods, cost controls, tests, UI, operations, release, and a worked first milestone. The backlog contains 60 implementation tickets and 8 later extensions, with dependencies and acceptance evidence.

See [the planning review](PLAN_REVIEW.md) for resolved findings and validation checks.

The first release targets synthetic tabular data, isolated SQL execution, structured quantitative claims, evidence-aware oversight, a controlled publication path, and an independent evaluator. It compares ordinary mistakes, prompt injection, and prompted sabotage while reporting useful completion and cost alongside incorrect releases.

Planning envelope: 300–420 hours including contingency, approximately 12–17 weeks at 25 hours per week. Exact model choices, spending limits, and final sample size are resolved through the development pilot before confirmation.

The existing TraceFrame and AMOS repositories were not modified, no paid model evaluation was launched, and no project performance results are claimed by this planning package.
