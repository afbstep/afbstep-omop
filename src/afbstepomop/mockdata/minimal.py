"""Generate a row for every concept the minimal data set requires.

The other generators build one table each and know what belongs in it. This one
knows nothing about any particular table: it reads ``minimal_concepts.csv``, and
for each item emits a row wherever the vocabulary says that concept lives. So a
concept removed from the minimal set stops being generated, and one added starts,
without a code change — which is the coupling the per-table generators lack.

What it deliberately does not do is invent values. Where the specification states
a range or pins answer concepts, the value comes from there; where it says
nothing, the row carries the concept and no value. That is legal in the CDM and
leaves the gap visible, rather than hiding a thin specification behind numbers
the generator made up.
"""

from __future__ import annotations

import random

from afbstepomop.mockdata import config
from afbstepomop.mockdata.common import concept_pool, random_date, value_range
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import Concept, Vocabulary

from datetime import date


def _answers_by_question(vocabulary: Vocabulary) -> dict[int, list[int]]:
    """Group answer concepts by the question they answer.

    Parameters
    ----------
    vocabulary : Vocabulary
        Parsed vocabulary layer.

    Returns
    -------
    dict of int to list of int
        Question concept id mapped to the concept ids permitted as its answers.
    """
    answers: dict[int, list[int]] = {}
    for concept in vocabulary.concepts:
        if concept.valid_for_question is not None:
            answers.setdefault(concept.valid_for_question, []).append(concept.concept_id)
    return answers


def _value_for(
    concept: Concept,
    spec: ProjectSpec,
    answers: dict[int, list[int]],
    rng: random.Random,
) -> dict[str, object]:
    """Give the row a value, but only where the specification supplies one.

    Three cases, in order. A concept with a plausibility rule gets a number drawn
    inside it, with the unit the rule names. A question with pinned answers gets
    one of them. Anything else gets nothing: an empty value column is a truthful
    statement that the specification does not yet say what may go there.

    Parameters
    ----------
    concept : Concept
        The concept the row is built around.
    spec : ProjectSpec
        Parsed project layer, holding the plausibility rules.
    answers : dict of int to list of int
        Output of :func:`_answers_by_question`.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    dict of str to object
        Columns to merge into the row; empty when the spec states no value.
    """
    if any(rule.concept_id == concept.concept_id for rule in spec.value_rules):
        low, high, unit = value_range(spec, concept.concept_id)
        value: dict[str, object] = {"value_as_number": round(rng.uniform(low, high), 1)}
        if unit is not None:
            value["unit_concept_id"] = unit
        return value

    permitted = answers.get(concept.concept_id)
    if permitted:
        return {"value_as_concept_id": rng.choice(permitted)}

    return {}


def _died_periods(periods: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the periods of persons whose follow-up ended before the study did.

    Death is the one minimal item that cannot be sprinkled over an arbitrary
    sample: a death row asserts the person died, so it may only be written for
    someone whose observation period closed early. Everyone else is still in
    follow-up.

    Parameters
    ----------
    periods : list of dict
        Rows returned by ``generate_observation_period``.

    Returns
    -------
    list of dict
        The subset whose period ends before the end of the study window.
    """
    end_of_study = config.STUDY_END.isoformat()
    return [period for period in periods if period["observation_period_end_date"] < end_of_study]


def _main_concept_column(table) -> str:
    """Return the column naming what a row of this table is about.

    Every clinical table has one: ``condition_concept_id`` for a condition,
    ``observation_concept_id`` for an observation. It is the required concept
    column that is not a ``_type_concept_id``, which records provenance instead.

    Parameters
    ----------
    table : Table
        Parsed structural definition.

    Returns
    -------
    str
        The column name, or ``""`` when the table has no such column.
    """
    for name, column in table.columns.items():
        if column.nullable or not name.endswith("_concept_id") or name.endswith("_type_concept_id"):
            continue
        return name
    return ""


def _fill_required(
    row: dict[str, object],
    table,
    period: dict[str, object],
    vocabulary: Vocabulary,
    table_name: str,
    rng: random.Random,
) -> None:
    """Fill every required column the row has not already set, by kind.

    Column names cannot be predicted from the table name — ``condition_occurrence``
    carries ``condition_start_date``, ``procedure_occurrence`` carries
    ``procedure_date`` — so each remaining required column is filled from what its
    name ends in rather than from a per-table rule. Dates land inside the person's
    observation period, and an end date never precedes its start.

    Parameters
    ----------
    row : dict
        Row being built; modified in place.
    table : Table
        Parsed structural definition, supplying which columns are required.
    period : dict
        The person's observation period, bounding any date.
    vocabulary : Vocabulary
        Parsed vocabulary layer, supplying concepts for concept columns.
    table_name : str
        Name of the table, needed to look up concept bindings.
    rng : random.Random
        Seeded generator.
    """
    opened = _date_in(period, rng)

    for name, column in table.columns.items():
        if column.nullable or name in row:
            continue
        if name.endswith("_end_date"):
            row[name] = max(opened, _date_in(period, rng))
        elif name.endswith("_date"):
            row[name] = opened
        elif name.endswith("_concept_id"):
            row[name] = rng.choice(concept_pool(vocabulary, table_name, name))


def generate_minimal_items(
    periods: list[dict[str, object]],
    generated: dict[str, list[dict[str, object]]],
    spec: ProjectSpec,
    vocabulary: Vocabulary,
    schema: CdmSchema,
    rng: random.Random,
) -> dict[str, list[dict[str, object]]]:
    """Emit rows carrying every concept the minimal data set requires.

    Each row is placed by the vocabulary: the concept's ``cdm_table`` decides the
    table and its ``cdm_variable`` the column. An *answer* concept, which sits in
    a value column, additionally needs the question it answers written into the
    table's own concept column, or the row would say a value without saying what
    it is a value of. Every other required column is filled by
    :func:`_fill_required`.

    Parameters
    ----------
    periods : list of dict
        Observation periods, supplying both the person and the window a date may
        fall in. A row outside its person's period would be uninterpretable.
    generated : dict of str to list of dict
        Tables built by the other generators. Read only, to continue their
        primary key sequences rather than colliding with them.
    spec : ProjectSpec
        Parsed project layer, holding the minimal items and value ranges.
    vocabulary : Vocabulary
        Parsed vocabulary layer, deciding where each concept lives.
    schema : CdmSchema
        Parsed structural layer, supplying each table's columns and key.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    dict of str to list of dict
        New rows keyed by table name, for merging into the dataset.
    """
    pinned = vocabulary.by_id()
    answers = _answers_by_question(vocabulary)
    died = _died_periods(periods)

    rows: dict[str, list[dict[str, object]]] = {}
    next_id = {name: len(existing) + 1 for name, existing in generated.items()}

    for entry in spec.minimal_concepts:
        concept = pinned.get(entry.concept_id) if entry.concept_id is not None else None
        if concept is None or not concept.cdm_table or not concept.cdm_variable:
            # --check-spec rejects these; skip rather than fail a demo dataset.
            continue

        name = concept.cdm_table
        table = schema.tables.get(name)
        if table is None or name not in spec.in_scope():
            continue

        # Death asserts an event, so it is drawn only from persons whose
        # follow-up actually ended; every other concept may sit on anyone.
        candidates = died if name == "death" else periods
        if not candidates:
            continue

        for period in rng.sample(candidates, min(config.MINIMAL_ITEM_PERSONS, len(candidates))):
            row: dict[str, object] = {"person_id": period["person_id"]}

            key = table.primary_key[0] if table.primary_key else ""
            if key and key != "person_id":
                row[key] = next_id.get(name, 1)
                next_id[name] = row[key] + 1

            row[concept.cdm_variable] = concept.concept_id

            # An answer concept needs something in the question column, which the
            # CDM requires. Where the vocabulary names the question, use it. Where
            # it does not, record 0 rather than drawing a question from the pinned
            # pool: valid_for_question exists to let this generator build coherent
            # rows, not to restrict where a partner may use an answer concept, so
            # its absence is silence rather than a defect. Picking a question at
            # random would assert a link the specification never made; 0 is OMOP's
            # way of saying the link is not recorded.
            question_column = _main_concept_column(table)
            if question_column and question_column not in row:
                row[question_column] = (
                    config.UNMAPPED_CONCEPT_ID
                    if concept.valid_for_question is None
                    else concept.valid_for_question
                )

            _fill_required(row, table, period, vocabulary, name, rng)
            row.update(
                {
                    column: value
                    for column, value in _value_for(concept, spec, answers, rng).items()
                    if column in table.columns
                }
            )
            rows.setdefault(name, []).append(row)

    return _deduplicate_death(rows)


def _date_in(period: dict[str, object], rng: random.Random) -> str:
    """Draw an ISO date inside one observation period."""
    start = date.fromisoformat(str(period["observation_period_start_date"]))
    end = date.fromisoformat(str(period["observation_period_end_date"]))
    return random_date(rng, start, end).isoformat()


def _deduplicate_death(rows: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    """Keep one death row per person, merging what the separate items wrote.

    ``death`` is keyed by person in practice: a person dies once. Two minimal
    items land there — the death itself and its cause — so without merging, a
    person selected for both would be given two deaths.

    Parameters
    ----------
    rows : dict of str to list of dict
        Rows built by :func:`generate_minimal_items`.

    Returns
    -------
    dict of str to list of dict
        The same rows with ``death`` collapsed to one row per person.
    """
    deaths = rows.get("death")
    if not deaths:
        return rows

    merged: dict[object, dict[str, object]] = {}
    for row in deaths:
        merged.setdefault(row["person_id"], {}).update(row)
    rows["death"] = list(merged.values())
    return rows
