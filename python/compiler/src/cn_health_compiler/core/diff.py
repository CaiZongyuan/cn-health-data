"""Version-diff value objects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiffSummary:
    """Record-level counts between two immutable releases."""

    added: int
    removed: int
    modified: int
    unchanged: int
