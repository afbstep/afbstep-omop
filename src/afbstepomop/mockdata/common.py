"""Helpers shared by the mock data generators.

These are the points where the generator consults the specification rather
than its own configuration: how completely to fill a column, which concepts a
column permits, and what range a concept's values must fall in.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from afbstepomop.mockdata import config
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import Vocabulary


def fill_probability(spec: ProjectSpec, table: str, column: str, nullable: bool) -> float:
    """Decide how often to populate one column.

    A column the CDM declares ``NOT NULL`` is always populated regardless of
    what the project asks, since an absent value would not be loadable. Beyond
    that the project requirement decides, and an ``expected`` column is filled
    part way between its threshold and full.

    Parameters
    ----------
    spec : ProjectSpec
        Parsed project layer.
    table, column : str
        The column being filled.
    nullable : bool
        Whether the CDM permits the column to be empty.

    Returns
    -------
    float
        Probability in ``0.0``-``1.0`` that a given row carries a value.
    """
    if not nullable:
        return 1.0

    rules = [rule for rule in spec.rules_for(table) if rule.column == column]
    if not rules:
        return 0.0

    rule = rules[0]
    if rule.requirement == "required":
        return 1.0
    if rule.requirement == "expected":
        return config.EXPECTED_FILL_PROBABILITY
    if rule.requirement == "optional":
        return config.OPTIONAL_FILL_PROBABILITY
    return 0.0


def concept_pool(vocabulary: Vocabulary, table: str, column: str) -> tuple[int, ...]:
    """Return the concept ids the spec permits in one concept column.

    Parameters
    ----------
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    table, column : str
        The concept column.

    Returns
    -------
    tuple of int
        Pinned concept ids, or ``(0,)`` when the spec pins none, mirroring the
        OMOP convention that an unmapped concept is recorded as ``0``.
    """
    concepts = vocabulary.bindings().get((table, column), ())
    return tuple(c.concept_id for c in concepts) or (config.UNMAPPED_CONCEPT_ID,)


def value_range(
    spec: ProjectSpec,
    concept_id: int,
    *,
    default_low: float = 0.0,
    default_high: float = 1.0,
) -> tuple[float, float, int | None]:
    """Return the range and unit ``plausibility.csv`` records for a concept.

    Drawing mock values from the plausibility rules rather than from hard-coded
    numbers keeps the generator honest: a dataset it produces cannot violate a
    range the specification states.

    A rule may state one bound, or neither: an unbounded count is a legitimate
    thing for the specification to say. The generator still needs two numbers to
    draw between, so each bound the spec leaves blank falls back to the default
    given here. A bound added to the spec later takes precedence automatically.

    Parameters
    ----------
    spec : ProjectSpec
        Parsed project layer.
    concept_id : int
        The concept whose values are being generated.
    default_low, default_high : float, optional
        Used for a bound the specification does not state, and for a concept it
        states no rule for at all.

    Returns
    -------
    tuple of (float, float, int or None)
        Lower bound, upper bound, and required unit concept id.
    """
    for rule in spec.value_rules:
        if rule.concept_id == concept_id:
            return (
                default_low if rule.min_value is None else rule.min_value,
                default_high if rule.max_value is None else rule.max_value,
                rule.unit_concept_id,
            )
    return (default_low, default_high, None)


def random_date(rng: random.Random, earliest: date, latest: date) -> date:
    """Draw a uniform date in ``[earliest, latest]``."""
    span = max((latest - earliest).days, 0)
    return earliest + timedelta(days=rng.randint(0, span))


def write_table(rows: list[dict[str, object]], table_name: str, schema: CdmSchema, path: Path) -> None:
    """Write one table to CSV, carrying every column the CDM declares.

    Columns a row does not populate are written empty rather than omitted, so
    the file has the shape of a partner export rather than of whatever the
    generator happened to fill.

    Parameters
    ----------
    rows : list of dict
        Rows keyed by column name.
    table_name : str
        Table being written; must exist in the schema.
    schema : CdmSchema
        Parsed structural layer, supplying the column order.
    path : Path
        Destination file.
    """
    columns = list(schema.tables[table_name].columns)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)
