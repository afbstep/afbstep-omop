# Analysis Table Generation (`afbstepomop.analysis_tables`)

This document explains how `cdm_to_table()` turns a populated AFBSTEP OMOP
CDM database into ready-to-use analysis tables (baseline characteristics,
data availability, discharge medications). It is meant as a reference for
anyone extending the package with a new table type.

## Design principles

- **SQL-only, no side information.** Every table is derived purely from
  what is in the CDM database plus the arguments passed to `cdm_to_table()`.
  Variable names and labels come from `concept.concept_name` (auto-discovery),
  never from a hardcoded list.
- **One shared anchor.** Baseline-oriented tables use the same anchor date
  per person: the visit marked by concept `2000013017` ("Baseline visit")
  if one exists, otherwise `person_study.enrollment_date`. This is computed
  once in `sql/index.sql` and reused everywhere.
- **Registry pattern.** Each table type is a builder function registered
  under a name in `registry.py`. Adding a table type never requires
  touching `api.py`, `options.py`, or `connection.py`.
- **Shared building blocks live in `builders/_helpers.py`.** Anything used
  by more than one table type (index SQL, variable filtering, conflict
  resolution, generic pivoting) is defined once there.

## Overview: how a call flows through the package

```mermaid
flowchart TD
    A["cdm_to_table(con, table_type, ...)"] --> B["TableOptions: validate arguments"]
    B --> C["open_connection: check vocabulary is loaded"]
    C --> D["get_builder(table_type): look up in registry"]
    D --> E1["build_baseline"]
    D --> E2["build_availability"]
    D --> E3["build_discharge"]

    E1 --> F["result DataFrame"]
    E2 --> F
    E3 --> F
    F -->|path given| G[to_parquet]
    F --> H[return to caller]

    classDef entry fill:#1565c0,stroke:#0d3d75,color:#fff
    classDef builder fill:#2e7d32,stroke:#1b4d1f,color:#fff
    class A entry
    class E1,E2,E3 builder
```

## `baseline`: six domains, one anchor

```mermaid
flowchart TD
    IDX["index.sql: anchor per person<br/>(baseline visit ⟶ else enrolment date)"]

    IDX --> COND["baseline_conditions.sql<br/>Case 1/2/3 + explicit negatives"]
    IDX --> MEAS["baseline_measurements.sql<br/>window + closest-value rule"]
    IDX --> OBS["baseline_observations.sql<br/>categorical value_as_concept_id"]
    IDX --> MED["baseline_medications.sql<br/>active at anchor + most-recent-start rule"]
    IDX --> DEV["baseline_devices.sql<br/>active at anchor + most-recent-start rule"]
    IDX --> PROC["baseline_procedures.sql<br/>Case 1/2/3 (no negatives)"]

    COND --> CONF["resolve_conflicts<br/>(positive vs. negative)"]
    CONF --> PIVC["pivot_timed_events"]
    PROC --> PIVP["pivot_timed_events"]
    MEAS --> PIVM["_pivot_measurements<br/>(number or concept name)"]
    OBS --> PIVO["_pivot_observations"]
    MED --> PIVMED["pivot_presence"]
    DEV --> PIVDEV["pivot_presence"]

    PIVC & PIVM & PIVO & PIVMED & PIVDEV & PIVP --> JOIN["left-join onto index, one row per person"]

    JOIN --> AVAIL["build_availability:<br/>does the study collect this variable at all?"]
    AVAIL --> FILL["_fill_missing_reasons:<br/>not_assessed vs. not_collected_by_study"]
    FILL --> RESULT["baseline table"]

    classDef sql fill:#37474f,stroke:#1c313a,color:#fff
    classDef py fill:#4527a0,stroke:#2c1a63,color:#fff
    class IDX,COND,MEAS,OBS,MED,DEV,PROC sql
    class CONF,PIVC,PIVP,PIVM,PIVO,PIVMED,PIVDEV,JOIN,AVAIL,FILL py
```

## `availability`: studies × variables, always unfiltered by `studies`

```mermaid
flowchart TD
    IDX2["build_index_sql(opts, apply_study_filter=False)<br/>— always all studies"]
    IDX2 --> AV["availability.sql<br/>UNION over conditions, observations,<br/>measurements, drugs, devices"]
    AV --> PIVAV["pivot to wide: one row per study_id"]
    PIVAV --> REINDEX["reindex onto ALL study_ids<br/>(studies with zero data → 0, not missing)"]
    REINDEX --> RESULT2["availability table"]
```

## `discharge`: a separate anchor

```mermaid
flowchart TD
    DIDX["discharge_index.sql<br/>anchor = visit_end_date of the baseline visit<br/>(only persons with a discharge date)"]
    DIDX --> DMED["discharge_medications.sql<br/>active at discharge + most-recent-start rule"]
    DMED --> DPIV["pivot_presence"]
    DPIV --> DRESULT["discharge table"]
```

**Why `discharge` is a separate table, not part of `baseline`:** a
"baseline" characteristic must exist before treatment can have caused it.
Discharge medications can themselves be a consequence of what happened
during the admission (e.g. a beta-blocker started because of a new HF
diagnosis) — including them in the baseline table would risk adjusting
for a mediator. See the design discussion in [chat/commit reference] for
the full reasoning.

## Module structure

```mermaid
flowchart LR
    subgraph API["public surface"]
        api[api.py<br/>cdm_to_table]
        opts[options.py<br/>TableOptions]
        reg[registry.py<br/>TABLE_BUILDERS]
        conn[connection.py<br/>open_connection, load_sql]
    end

    subgraph BUILDERS["builders/"]
        helpers[_helpers.py<br/>shared logic]
        baseline[baseline.py]
        availability[availability.py]
        discharge[discharge.py]
    end

    api --> opts
    api --> conn
    api --> reg
    reg --> baseline
    reg --> availability
    reg --> discharge
    baseline --> helpers
    availability --> helpers
    discharge --> helpers

    classDef pub fill:#1565c0,stroke:#0d3d75,color:#fff
    classDef bld fill:#2e7d32,stroke:#1b4d1f,color:#fff
    class api,opts,reg,conn pub
    class helpers,baseline,availability,discharge bld
```

## Conventions used throughout

| Convention | Value | Defined in |
|---|---|---|
| Unknown historical date (comorbidity Case 3) | `1900-01-01` | `conventions.SENTINEL_UNKNOWN_DATE` |
| Ongoing exposure | `2099-12-31` or empty end date | `conventions.SENTINEL_ONGOING_DATE` |
| Explicit negative finding | `4189457` | `conventions.NEGATIVE_CONCEPT_ID` |
| Baseline visit marker | `2000013017` | `conventions.BASELINE_VISIT_CONCEPT_ID` |
| Field concept for `visit_occurrence.visit_occurrence_id` | `1147869` | `sql/index.sql`, `sql/discharge_index.sql` |

## Adding a new table type

1. Write the SQL file(s) under `sql/`.
2. Write a `builders/<name>.py` with a `build_<name>(connection, opts)`
   function returning a `pandas.DataFrame`. Reuse `builders/_helpers.py`
   wherever the logic is generic (index anchor, variable filtering,
   conflict resolution, pivoting).
3. Register it in `registry.py`: `TABLE_BUILDERS["<name>"] = build_<name>`.
4. Add a fixture-based test suite under `tests/analysis_tables/`.

No change to `api.py`, `options.py`, or `connection.py` is required.

## Known limitations / deferred work

- `study_missingness_design.csv` is loaded but not yet consulted — it is
  meant to distinguish studies whose protocol cannot record explicit
  negative findings, once populated with real studies.
- Overlapping medication/device rows resolve via "most recent start
  wins"; no explicit handling of genuinely simultaneous, non-overlapping
  courses of the same drug.
- Conflict detection (positive vs. negative finding for the same
  person/variable) should eventually also be flagged by the output
  validator at data-loading time, not only resolved here at read time.