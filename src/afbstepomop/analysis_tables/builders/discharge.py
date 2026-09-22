import pandas as pd

from ..connection import load_sql
from ..conventions import BASELINE_VISIT_CONCEPT_ID, SENTINEL_ONGOING_DATE
from ._helpers import resolve_concept_filter, variable_filter_sql, pivot_presence


def _build_discharge_index_sql(opts):
    return load_sql("discharge_index.sql").format(
        schema=opts.schema,
        baseline_visit_concept=BASELINE_VISIT_CONCEPT_ID,
    )


def build_discharge_medications(connection, opts):
    index_sql = _build_discharge_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    medications_sql = load_sql("discharge_medications.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "d.drug_concept_id"),
    )
    return connection.execute(
        medications_sql,
        {"sentinel_ongoing": SENTINEL_ONGOING_DATE},
    ).df()


def build_discharge(connection, opts):
    index_sql = _build_discharge_index_sql(opts)
    index = connection.execute(index_sql).df().set_index("person_id")

    medications = build_discharge_medications(connection, opts)
    medications_wide = pivot_presence(medications)

    result = index.join(medications_wide, how="left")
    return result.reset_index()