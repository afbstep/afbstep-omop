"""Generate the person-level backbone of a mock dataset.

Persons, the observation periods that make absence of a record interpretable,
and the conditions recorded inside those periods. Everything else in the
dataset hangs off these three.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from afbstepomop.mockdata import config
from afbstepomop.mockdata.common import concept_pool, fill_probability, random_date
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.vocabulary import Vocabulary


def generate_person(
    n_persons: int, spec: ProjectSpec, vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate rows for ``person``.

    Ethnicity is derived from race rather than drawn independently, following
    the AFBSTEP coding rule that treats the two as one source field.

    Parameters
    ----------
    n_persons : int
        Number of persons to generate.
    spec : ProjectSpec
        Parsed project layer, deciding how completely to fill each column.
    vocabulary : Vocabulary
        Parsed vocabulary layer, supplying the permitted concepts.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        One row per person, keyed by column name.
    """
    genders = concept_pool(vocabulary, "person", "gender_concept_id")
    races = concept_pool(vocabulary, "person", "race_concept_id")
    birth_datetime_probability = fill_probability(spec, "person", "birth_datetime", nullable=True)
    source_value_probability = fill_probability(spec, "person", "person_source_value", nullable=True)

    rows: list[dict[str, object]] = []
    for person_id in range(1, n_persons + 1):
        race = rng.choice(races)
        birth = date(
            rng.randint(config.EARLIEST_BIRTH_YEAR, config.LATEST_BIRTH_YEAR),
            rng.randint(1, 12),
            rng.randint(1, 28),
        )

        row: dict[str, object] = {
            "person_id": person_id,
            "gender_concept_id": rng.choice(genders),
            "year_of_birth": birth.year,
            "race_concept_id": race,
            "ethnicity_concept_id": (
                config.HISPANIC_ETHNICITY_CONCEPT_ID
                if race == config.HISPANIC_RACE_CONCEPT_ID
                else config.NON_HISPANIC_ETHNICITY_CONCEPT_ID
            ),
        }
        if rng.random() < birth_datetime_probability:
            row["birth_datetime"] = f"{birth.isoformat()} 00:00:00"
        if rng.random() < source_value_probability:
            row["person_source_value"] = f"MOCK-{person_id:05d}"

        rows.append(row)

    return rows


def generate_observation_period(
    persons: list[dict[str, object]], vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate one observation period per person, inside the study window.

    A period cannot open before the study does, so absence of a record inside
    it is interpretable. A fraction of persons are still in follow-up; their
    period ends at the study end rather than at a far-future placeholder date,
    because a sentinel date would encode missingness in a way OHDSI tooling
    reads as a real value.

    Parameters
    ----------
    persons : list of dict
        Rows returned by :func:`generate_person`.
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        One row per person, keyed by column name.
    """
    period_types = concept_pool(vocabulary, "observation_period", "period_type_concept_id")
    minimum_follow_up = timedelta(days=config.MINIMUM_FOLLOW_UP_DAYS)

    rows: list[dict[str, object]] = []
    for index, person in enumerate(persons, start=1):
        start = random_date(rng, config.STUDY_START, config.STUDY_END - minimum_follow_up)
        if rng.random() < config.STILL_IN_FOLLOW_UP_FRACTION:
            end = config.STUDY_END
        else:
            span = rng.randint(config.MINIMUM_FOLLOW_UP_DAYS, config.MAXIMUM_FOLLOW_UP_DAYS)
            end = min(start + timedelta(days=span), config.STUDY_END)

        rows.append(
            {
                "observation_period_id": index,
                "person_id": person["person_id"],
                "observation_period_start_date": start.isoformat(),
                "observation_period_end_date": end.isoformat(),
                "period_type_concept_id": rng.choice(period_types),
            }
        )

    return rows


def generate_condition_occurrence(
    periods: list[dict[str, object]], spec: ProjectSpec, vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate conditions for each person, inside their observation period.

    Parameters
    ----------
    periods : list of dict
        Rows returned by :func:`generate_observation_period`, which supply the
        window each person's conditions must fall inside.
    spec : ProjectSpec
        Parsed project layer.
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Rows keyed by column name, numbered across all persons.
    """
    conditions = concept_pool(vocabulary, "condition_occurrence", "condition_concept_id")
    types = concept_pool(vocabulary, "condition_occurrence", "condition_type_concept_id")
    end_date_probability = fill_probability(spec, "condition_occurrence", "condition_end_date", nullable=True)
    source_value_probability = fill_probability(spec, "condition_occurrence", "condition_source_value", nullable=True)

    rows: list[dict[str, object]] = []
    for period in periods:
        window_start = date.fromisoformat(str(period["observation_period_start_date"]))
        window_end = date.fromisoformat(str(period["observation_period_end_date"]))

        for _ in range(rng.randint(0, config.MAX_CONDITIONS_PER_PERSON)):
            concept_id = rng.choice(conditions)
            start = random_date(rng, window_start, window_end)

            row: dict[str, object] = {
                "condition_occurrence_id": len(rows) + 1,
                "person_id": period["person_id"],
                "condition_concept_id": concept_id,
                "condition_start_date": start.isoformat(),
                "condition_type_concept_id": rng.choice(types),
            }
            if rng.random() < end_date_probability:
                row["condition_end_date"] = random_date(rng, start, window_end).isoformat()
            if rng.random() < source_value_probability:
                row["condition_source_value"] = f"SRC-{concept_id}"

            rows.append(row)

    return rows
