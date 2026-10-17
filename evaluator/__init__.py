"""Repository-only private scoring and trusted fixture validation.

This package is deliberately outside the installed ``assay`` package. It
must not be mounted in analyst/reviewer workers or imported by runtime checks.
The committed examples are exposed development fixtures, never held-out truth.
"""

from evaluator.oracle import OracleInputError, derive_truth, score_claims

__all__ = ["OracleInputError", "derive_truth", "run_milestone", "score_claims"]


def run_milestone() -> dict[str, object]:
    """Run the exposed, developer-authored first-milestone regressions."""
    from evaluator.milestone import run_milestone as run

    return run()
