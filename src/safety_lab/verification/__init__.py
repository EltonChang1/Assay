"""Public-contract checks; no evaluator truth or publication authority."""

from .service import CHECKER_VERSION, required_check_keys, verify_report

__all__ = ["CHECKER_VERSION", "required_check_keys", "verify_report"]
