"""Publication policy profiles and the experimental arms built on them."""

from collections.abc import Mapping
from typing import Literal

PolicyProfile = Literal["baseline", "checked", "reviewed", "checked_reviewed"]
Arm = Literal["A", "B", "C", "D", "E"]
ArmView = Literal["ordinary", "evidence"]

# D and E share a profile and differ only in the reviewer's representation.
ARMS: Mapping[Arm, tuple[PolicyProfile, ArmView | None]] = {
    "A": ("baseline", None),
    "B": ("checked", None),
    "C": ("reviewed", "ordinary"),
    "D": ("checked_reviewed", "ordinary"),
    "E": ("checked_reviewed", "evidence"),
}
