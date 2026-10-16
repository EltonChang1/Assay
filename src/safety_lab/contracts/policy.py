"""Publication policy profiles shared by reports, episodes, and arms."""

from typing import Literal

# A: baseline; B: checked; C: reviewed; D/E: checked_reviewed (views differ).
PolicyProfile = Literal["baseline", "checked", "reviewed", "checked_reviewed"]
