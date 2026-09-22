import pandas as pd

from ..connection  import load_sql
from ..conventions import BASELINE_VISIT_CONCEPT_ID, SENTINEL_UNKNOWN_DATE, NEGATIVE_CONCEPT_ID, SENTINEL_ONGOING_DATE
from .availability import build_availability

from ._helpers import (
    build_index_sql,
    resolve_concept_filter,
    variable_filter_sql,
    resolve_conflicts,
    pivot_timed_events,
    pivot_presence,
)

def _load_study_missingness_design() -> pd.DataFrame:
    path = files("afbstepomop.analysis_tables") / "config" / "study_missingness_design.csv"
    return pd.read_csv(path)

def build_baseline_conditions(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    conditions_sql = load_sql("baseline_conditions.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "co.condition_concept_id"),
    )
    conditions = connection.execute(
        conditions_sql,
        {
            "unknown_date": SENTINEL_UNKNOWN_DATE,
            "negative_concept_id": NEGATIVE_CONCEPT_ID,
        },
    ).df()

    conditions, warnings = resolve_conflicts(conditions, opts.conflict_resolution)
    for warning in warnings:
        print(f"Warning: {warning}")

    return conditions


def build_baseline_measurements(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    measurements_sql = load_sql("baseline_measurements.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "m.measurement_concept_id"),
    )
    lo, hi = opts.baseline_window
    return connection.execute(
        measurements_sql,
        {"lo": lo, "hi": hi},
    ).df()


def _measurements_value_and_reason(measurements: pd.DataFrame) -> pd.DataFrame:
    measurements = measurements.copy()
    measurements["value"] = measurements["value_as_number"].where(
        measurements["value_as_number"].notna(),
        measurements["value_as_concept_name"],
    )
    measurements["reason"] = "observed"
    measurements.loc[measurements["value"].isna(), "reason"] = "not_assessed"
    return measurements


def _pivot_measurements(measurements: pd.DataFrame) -> pd.DataFrame:
    measurements = _measurements_value_and_reason(measurements)
    value_wide = measurements.pivot(index="person_id", columns="variable", values="value")
    reason_wide = measurements.pivot(index="person_id", columns="variable", values="reason")
    day_wide = measurements.pivot(index="person_id", columns="variable", values="day_offset")

    reason_wide.columns = [f"{col}_reason" for col in reason_wide.columns]
    day_wide.columns = [f"{col}_day" for col in day_wide.columns]

    return pd.concat([value_wide, reason_wide, day_wide], axis=1)


def build_baseline_medications(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    medications_sql = load_sql("baseline_medications.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "d.drug_concept_id"),
    )
    return connection.execute(
        medications_sql,
        {"sentinel_ongoing": SENTINEL_ONGOING_DATE},
    ).df()


def build_baseline_devices(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    devices_sql = load_sql("baseline_devices.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "de.device_concept_id"),
    )
    return connection.execute(
        devices_sql,
        {"sentinel_ongoing": SENTINEL_ONGOING_DATE},
    ).df()


def _fill_missing_reasons(result: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    reason_columns = [col for col in result.columns if col.endswith("_reason")]
    availability_by_study = availability.set_index("study_id")

    for col in reason_columns:
        variable = col.removesuffix("_reason")
        missing = result[col].isna()

        if variable not in availability_by_study.columns:
            result.loc[missing, col] = "not_assessed"
            continue

        collects = result["study_id"].map(availability_by_study[variable]).fillna(0).astype(bool)
        result.loc[missing & collects, col] = "not_assessed"
        result.loc[missing & ~collects, col] = "not_collected_by_study"

    return result

def build_baseline_observations(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    observations_sql = load_sql("baseline_observations.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "o.observation_concept_id"),
    )
    lo, hi = opts.baseline_window
    return connection.execute(
        observations_sql,
        {
            "baseline_visit_concept": BASELINE_VISIT_CONCEPT_ID,
            "negative_concept_id": NEGATIVE_CONCEPT_ID,
            "lo": lo,
            "hi": hi,
        },
    ).df()

def _observations_reason(observations: pd.DataFrame) -> pd.DataFrame:
    observations = observations.copy()
    observations["reason"] = "observed"
    return observations


def _pivot_observations(observations: pd.DataFrame) -> pd.DataFrame:
    observations = _observations_reason(observations)
    value_wide = observations.pivot(index="person_id", columns="variable", values="value_as_concept_name")
    reason_wide = observations.pivot(index="person_id", columns="variable", values="reason")
    day_wide = observations.pivot(index="person_id", columns="variable", values="day_offset")

    reason_wide.columns = [f"{col}_reason" for col in reason_wide.columns]
    day_wide.columns = [f"{col}_day" for col in day_wide.columns]

    return pd.concat([value_wide, reason_wide, day_wide], axis=1)


def build_baseline_procedures(connection, opts):
    index_sql = build_index_sql(opts)
    concept_ids = resolve_concept_filter(opts.variables)
    procedures_sql = load_sql("baseline_procedures.sql").format(
        schema=opts.schema,
        index_sql=index_sql,
        variable_filter=variable_filter_sql(concept_ids, "po.procedure_concept_id"),
    )
    procedures = connection.execute(
        procedures_sql,
        {"unknown_date": SENTINEL_UNKNOWN_DATE},
    ).df()

    procedures, warnings = resolve_conflicts(procedures, opts.conflict_resolution)
    for warning in warnings:
        print(f"Warning: {warning}")

    return procedures


def build_baseline(connection, opts):
    index_sql = build_index_sql(opts)
    index = connection.execute(index_sql).df().set_index("person_id")

    conditions = build_baseline_conditions(connection, opts)
    conditions_wide = pivot_timed_events(conditions) if not conditions.empty else pd.DataFrame(index=index.index)

    measurements = build_baseline_measurements(connection, opts)
    measurements_wide = _pivot_measurements(measurements) if not measurements.empty else pd.DataFrame(index=index.index)

    observations = build_baseline_observations(connection, opts)
    observations_wide = _pivot_observations(observations) if not observations.empty else pd.DataFrame(index=index.index)

    medications = build_baseline_medications(connection, opts)
    medications_wide = pivot_presence(medications)

    procedures = build_baseline_procedures(connection, opts)
    procedures_wide = pivot_timed_events(procedures) if not procedures.empty else pd.DataFrame(index=index.index)

    devices = build_baseline_devices(connection, opts)
    devices_wide = pivot_presence(devices)

    result = (
        index
        .join(conditions_wide, how="left")
        .join(measurements_wide, how="left")
        .join(observations_wide, how="left")
        .join(procedures_wide, how="left")
        .join(medications_wide, how="left")
        .join(devices_wide, how="left")
    )
    result = result.reset_index()

    availability = build_availability(connection, opts)
    result = _fill_missing_reasons(result, availability)

    return result
