import pandas as pd
import csv
from importlib.resources import files

from ..connection import load_sql
from ..conventions import BASELINE_VISIT_CONCEPT_ID


def build_index_sql(opts, apply_study_filter: bool = True):
    """The standard anchor: baseline visit if marked, else enrolment date."""
    if apply_study_filter and opts.studies is not None:
        study_ids = ", ".join(str(int(s)) for s in opts.studies)
        study_filter = f"WHERE ps.study_id IN ({study_ids})"
    else:
        study_filter = ""

    return load_sql("index.sql").format(
        schema=opts.schema,
        baseline_visit_concept=BASELINE_VISIT_CONCEPT_ID,
        study_filter=study_filter,
    )


def load_core_concept_ids() -> list[int]:
    path = files("afbstepomop.source") / "spec" / "minimal_concepts.csv"
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return [int(row["concept_id"]) for row in reader]


def resolve_concept_filter(variables) -> list[int] | None:
    if variables is None:
        return None
    if variables == "core":
        return load_core_concept_ids()
    return [int(v) for v in variables]


def variable_filter_sql(concept_ids: list[int] | None, column: str) -> str:
    if concept_ids is None:
        return ""
    ids = ", ".join(str(int(c)) for c in concept_ids)
    return f"AND {column} IN ({ids})"


def resolve_conflicts(events: pd.DataFrame, conflict_resolution: str) -> tuple[pd.DataFrame, list[str]]:
    is_negative = events["timing"] == "negative"

    keys_positive = set(map(tuple, events.loc[~is_negative, ["person_id", "variable"]].values))
    keys_negative = set(map(tuple, events.loc[is_negative, ["person_id", "variable"]].values))
    conflicting_keys = keys_positive & keys_negative

    warnings = [
        f"person_id={person_id}, variable={variable!r}: both a positive and a negative "
        f"finding exist; keeping the {conflict_resolution} one"
        for person_id, variable in conflicting_keys
    ]

    row_keys = list(zip(events["person_id"], events["variable"]))
    is_conflicting_row = pd.Series([key in conflicting_keys for key in row_keys], index=events.index)

    if conflict_resolution == "positive":
        drop = is_conflicting_row & is_negative
    else:
        drop = is_conflicting_row & ~is_negative

    return events[~drop].reset_index(drop=True), warnings


def timed_events_value_and_reason(events: pd.DataFrame) -> pd.DataFrame:
    """Shared by conditions and procedures: presence (1/0) + reason from `timing`."""
    events = events.copy()
    events["value"] = (events["timing"] != "negative").astype("Int64")
    events.loc[events["timing"] == "negative", "value"] = 0
    events["reason"] = "observed"
    events.loc[events["timing"] == "negative", "reason"] = "negative"
    return events


def pivot_timed_events(events: pd.DataFrame) -> pd.DataFrame:
    events = timed_events_value_and_reason(events)
    value_wide = events.pivot(index="person_id", columns="variable", values="value")
    reason_wide = events.pivot(index="person_id", columns="variable", values="reason")
    reason_wide.columns = [f"{col}_reason" for col in reason_wide.columns]
    return pd.concat([value_wide, reason_wide], axis=1)


def pivot_presence(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    value_wide = data.pivot(index="person_id", columns="variable", values="value")
    ongoing_wide = data.pivot(index="person_id", columns="variable", values="ongoing")
    start_day_wide = data.pivot(index="person_id", columns="variable", values="start_day")
    ongoing_wide.columns = [f"{col}_ongoing" for col in ongoing_wide.columns]
    start_day_wide.columns = [f"{col}_start_day" for col in start_day_wide.columns]
    return pd.concat([value_wide, ongoing_wide, start_day_wide], axis=1)