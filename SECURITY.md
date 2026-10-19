# Security scope and reporting

Assay is an early local research prototype. The execution/evidence/publication, episode/review and correction mechanisms are implemented for a narrow synthetic sales task. The [paper](research/paper.md) and [repository review](research/REPOSITORY_REVIEW.md) separate tested controls, source audits, paid pilot observations and unexecuted confirmation.

The October 19 review passed 436 offline tests with 29 skips; Docker was unavailable, so container results remain those of the saved October 18 run (441 passes, one POSIX-only skip). A single paid development pilot has run: all 24 assignments exhausted their analyst allowance before submission, with no review or release. Its worker image cannot fetch timestamp previews because `pytz` is missing. Neither zero releases nor regression test counts establish comparative safety or security certification.

Final-test information isolation, lease expiry, gateway admission fencing, distributed recovery and general runtime spending reservations remain unfinished. The dedicated sequential pilot has a separate conservative budget journal; that protection does not apply to arbitrary `InspectModelClient` usage. Historical implementation milestones remain in [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Intended boundaries

- Treat model output, dataset text, retrieved documentation, and analyst SQL as untrusted input. A reviewer recommendation is also untrusted until checked by publication policy.
- Never execute analyst SQL in the host process or fall back to host execution when an isolated worker is unavailable. TraceFrame's SQL helper is not an execution sandbox.
- The worker receives only approved immutable tables and bounded query input. Local container tests verified read-only root/input mounts, no external network, absence of host/private paths and the Docker socket, non-root identity, disabled privileges/capabilities, seccomp, and resource enforcement. These checks apply to the recorded development environment and initial sales schema.
- The trusted host must generate receipts, capture outputs, validate claim references, enforce budgets, and bind approval to exact report bytes and dependencies. A successful query and a valid evidence link do not prove the intended metric is correct.
- Keep final-test truth, seeds, private objectives/labels, and scorer diagnostics outside actor/reviewer mounts and prompts. The independent evaluator measures released output after the episode and cannot authorize publication.
- Only the trusted publisher may release reports. Replay/export surfaces may expose clearly labeled drafts to researchers, but cannot become an end-user release route.
- The trusted host runs the analyst tool loop. Analyst tools read table data only through gateway queries (row previews included) and read stored results only from their own run; tool errors returned to the model are fixed codes that never echo host paths or exception text. A reviewer decision is parsed strictly and never publishes by itself; under `checked_reviewed` it cannot override a failed or unknown mandatory check. Correction feedback to the analyst contains only the arm's own decision reasons and reviewer reason codes, never reviewer prose, private labels, or check outcomes the arm does not use.

Requirements become validated boundaries only when the corresponding tests pass and are recorded. The real Docker suite passed useful and denied queries, container identity/filesystem/network access, resource exhaustion, output overflow, and timeout/cancellation cleanup. Resource probes use fixed developer-authored diagnostics inside containers with production resource arguments; the analyst interface remains SQL-only. The saved October 18 enabled run passed 441 tests, with one POSIX-only skip and no failures or errors. The October 19 review did not rerun containers. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for remaining claim/publication work and [ADR 0001](docs/ADR-0001-foundation.md) for sequencing.

## Local handling

Keep mutable state outside this OneDrive checkout and other synchronized roots, using the configured local state directory. Do not commit credentials, active databases, private final-test data, raw private logs, or generated run artifacts. `.gitignore` prevents accidental tracking; it does not prevent process access. Release preparation must build an explicit allowlisted bundle, check it for secrets/private truth, and verify its referenced artifacts and notices.

Offline development must work without API keys. Any new paid experiment must freeze its priced configuration and validate spending reservations before dispatch, preserving cumulative prior spending. The dedicated pilot runner does this for its sequential run only. `InspectModelClient` uses whatever provider credentials Inspect finds in its host-side configuration, and spending reservations (P4.5) do not exist yet, so a paid provider configured there would be called without a cap. The Docker diagnostic must not launch model calls, print secrets, or interpret availability as proof that isolation works.

## Reporting a concern

No dedicated private security contact or response-time commitment has been established. For a non-sensitive bug, open an issue with the affected commit, minimal reproduction, expected versus observed behavior, and the relevant boundary. Do not post credentials, private datasets, hidden test answers, or exploit material that exposes a live secret in a public issue. For a sensitive concern, use an available private repository reporting channel or contact the repository owner privately through an established channel.

Do not include claims that a boundary is enforced solely because a configuration option exists. Reports and fixes should distinguish intended policy, implemented mechanism, test evidence, and remaining limitations.
