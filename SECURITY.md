# Security scope and reporting

TraceFrame Safety Lab is an early local research prototype. The container SQL worker, gateway, and durable execution evidence are implemented; all 28 real Docker boundary cases passed locally for the initial sales schema. The trusted publisher (revision-bound approvals, attempt fencing, source-epoch invalidation) is implemented and tested offline ([ADR 0003](docs/ADR-0003-publication.md)). The final-test information boundary, lease expiry, and gateway admission fencing remain unimplemented. Passing these tests is not a security certification. [Saved validation evidence](docs/validation/docker-validation.json) and [implementation status](docs/IMPLEMENTATION_STATUS.md) record the tested scope and open work, with planned work in [the backlog](IMPLEMENTATION_BACKLOG.md).

## Intended boundaries

- Treat model output, dataset text, retrieved documentation, and analyst SQL as untrusted input. A reviewer recommendation is also untrusted until checked by publication policy.
- Never execute analyst SQL in the host process or fall back to host execution when an isolated worker is unavailable. TraceFrame's SQL helper is not an execution sandbox.
- The worker receives only approved immutable tables and bounded query input. Local container tests verified read-only root/input mounts, no external network, absence of host/private paths and the Docker socket, non-root identity, disabled privileges/capabilities, seccomp, and resource enforcement. These checks apply to the recorded development environment and initial sales schema.
- The trusted host must generate receipts, capture outputs, validate claim references, enforce budgets, and bind approval to exact report bytes and dependencies. A successful query and a valid evidence link do not prove the intended metric is correct.
- Keep final-test truth, seeds, private objectives/labels, and scorer diagnostics outside actor/reviewer mounts and prompts. The independent evaluator measures released output after the episode and cannot authorize publication.
- Only the trusted publisher may release reports. Replay/export surfaces may expose clearly labeled drafts to researchers, but cannot become an end-user release route.

Requirements become validated boundaries only when the corresponding tests pass and are recorded. The real Docker suite passed useful and denied queries, container identity/filesystem/network access, resource exhaustion, output overflow, and timeout/cancellation cleanup. Resource probes use fixed developer-authored diagnostics inside containers with production resource arguments; the analyst interface remains SQL-only. The full enabled run passed 311 tests with no skips, failures, or errors and left no worker containers running. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for remaining claim/publication work and [ADR 0001](docs/ADR-0001-foundation.md) for sequencing.

## Local handling

Keep mutable state outside this OneDrive checkout and other synchronized roots, using the configured local state directory. Do not commit credentials, active databases, private final-test data, raw private logs, or generated run artifacts. `.gitignore` prevents accidental tracking; it does not prevent process access. Release preparation must build an explicit allowlisted bundle, check it for secrets/private truth, and verify its referenced artifacts and notices.

Offline development must work without API keys. Future paid model commands must validate priced configurations and spending reservations before dispatch. The Docker diagnostic must not launch model calls, print secrets, or interpret availability as proof that isolation works.

## Reporting a concern

No dedicated private security contact or response-time commitment has been established. For a non-sensitive bug, open an issue with the affected commit, minimal reproduction, expected versus observed behavior, and the relevant boundary. Do not post credentials, private datasets, hidden test answers, or exploit material that exposes a live secret in a public issue. For a sensitive concern, use an available private repository reporting channel or contact the repository owner privately through an established channel.

Do not include claims that a boundary is enforced solely because a configuration option exists. Reports and fixes should distinguish intended policy, implemented mechanism, test evidence, and remaining limitations.
