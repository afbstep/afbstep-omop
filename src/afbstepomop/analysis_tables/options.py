import re
from dataclasses import dataclass

_ALLOWED_MISSINGNESS = {"reason_columns", "collapse_to_na"}
_ALLOWED_SENTINELS = {"flag", "na"}
_ALLOWED_CONFLICT_RESOLUTION = {"positive", "negative"}
_SCHEMA_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TableOptions:
    schema: str = "main"
    studies: list[int] | None = None
    variables: dict | None = None
    baseline_window: tuple[int, int] = (-365, 30)
    missingness: str = "reason_columns"
    sentinels: str = "flag"
    conflict_resolution: str = "positive"

    def __post_init__(self):
        if not _SCHEMA_PATTERN.match(self.schema):
            raise ValueError(f"invalid schema name: {self.schema!r}")
        if self.missingness not in _ALLOWED_MISSINGNESS:
            raise ValueError(
                f"missingness={self.missingness!r}; expected one of {sorted(_ALLOWED_MISSINGNESS)}"
            )
        if self.sentinels not in _ALLOWED_SENTINELS:
            raise ValueError(
                f"sentinels={self.sentinels!r}; expected one of {sorted(_ALLOWED_SENTINELS)}"
            )
        if self.conflict_resolution not in _ALLOWED_CONFLICT_RESOLUTION:
            raise ValueError(
                f"conflict_resolution={self.conflict_resolution!r}; expected one of {sorted(_ALLOWED_CONFLICT_RESOLUTION)}"
            )
        lo, hi = self.baseline_window
        if lo > hi:
            raise ValueError("baseline_window must be (lower, upper) with lower <= upper")