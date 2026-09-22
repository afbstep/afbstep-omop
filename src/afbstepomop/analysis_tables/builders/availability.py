import pandas as pd

from ..connection import load_sql
from ..conventions import BASELINE_VISIT_CONCEPT_ID, NEGATIVE_CONCEPT_ID
from importlib.resources import files
from ._helpers import build_index_sql

def _load_study_missingness_design() -> pd.DataFrame:
    path = files("afbstepomop.analysis_tables") / "config" / "study_missingness_design.csv"
    return pd.read_csv(path)

def _build_index_sql(opts):
    return build_index_sql(opts, apply_study_filter=False)

def build_availability(connection, opts):
    index_sql = _build_index_sql(opts)
    all_study_ids = connection.execute(index_sql).df()["study_id"].unique()

    availability_sql = load_sql("availability.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
    )
    observed = connection.execute(
        availability_sql,
        {"negative_concept_id": NEGATIVE_CONCEPT_ID},
    ).df()

    if observed.empty:
        return pd.DataFrame({"study_id": all_study_ids})

    wide = observed.pivot(index="study_id", columns="variable", values="collected")
    wide = wide.reindex(all_study_ids)
    wide = wide.fillna(0).astype("Int64")
    return wide.reset_index()
