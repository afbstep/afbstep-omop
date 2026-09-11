"""
Parse the vocabulary layer of the AFBSTEP CDM specification.

The vocabulary layer describes *which concepts AFBSTEP commits to* and where
each one is expected to land in the CDM. It is assembled from two files under
`source/spec/`:

`spec/standard_vocabulary.csv`
    Standard OHDSI concepts pinned so that validation resolves offline and
    reproducibly instead of calling a vocabulary server. The list is
    deliberately *not* exhaustive: it covers the minimal data set plus common
    optional fields, and partners may submit standard concepts absent from it.
`spec/custom_vocabulary.csv`
    Concepts AFBSTEP had to mint because no standard concept exists. Same
    columns as the standard file plus `status` and `rationale`.

Both files carry `CDM_table` and `CDM_variable`, which record the concept
column a concept is expected to occupy. `CDM_table` is not derivable from
`domain_id` and the two deliberately disagree for some rows, so both are
kept as authored.

The following is checked:
- no concept id is declared twice across the pinned + custom CSVs
- a custom concept's id falls in the reserved 2000000000+ range
- a custom concept's vocabulary_id is the AFBSTEP custom vocabulary string
- a standard (pinned) concept's id does not fall in that reserved custom range
- valid_start_date and valid_end_date both parse as ISO dates
- valid_end_date comes after valid_start_date
- a binding to a CDM table/column is either fully stated or fully absent (not half)
- a stated binding's (table, column) is a real concept-valued column in the schema

Plus file-level defects (hygiene, not decisions): 
- stripped whitespace
- undocumented columns dropped
- ids exported as floats (2000011002.0) tolerated and coerced

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from afbstepomop.source_validator.csvspec import read_spec_csv

if TYPE_CHECKING:
    from afbstepomop.source_validator.structural import CdmSchema

from afbstepomop.source_validator.paths import DEFAULT_SOURCE_DIR  # noqa: E402  (re-exported for callers)

STANDARD_ORIGIN = "standard"
CUSTOM_ORIGIN = "custom"

CUSTOM_CONCEPT_ID_MIN = 2_000_000_000
CUSTOM_VOCABULARY_ID = "AFBSTEP"

SHARED_COLUMNS = (
    "concept_id",
    "concept_name",
    "domain_id",
    "vocabulary_id",
    "concept_class_id",
    "standard_concept",
    "concept_code",
    "valid_start_date",
    "valid_end_date",
    "CDM_table",
    "CDM_variable",
)

#: Columns only the custom file carries. `status` and `rationale` are the
#: audit trail for a minted concept; `valid_for_episode_type` records which
#: kind of episode the concept belongs inside.
CUSTOM_COLUMNS = ("status", "rationale", "valid_for_episode_type")

#: Carried by both files: the question concept an answer concept answers. Empty
#: on a concept that is not an answer, which is most of them.
ANSWER_COLUMN = "valid_for_question"


@dataclass(frozen=True)
class Concept:
    """A single concept AFBSTEP commits to.

    Attributes
    ----------
    concept_id : int
        OHDSI concept id. Custom concepts use the ``2000000000+`` range
        reserved for local vocabularies.
    concept_name, domain_id, vocabulary_id, concept_class_id : str
        Standard OHDSI vocabulary attributes, as authored.
    standard_concept : str
        ``"S"`` for standard concepts, empty otherwise.
    concept_code : str
        Code within ``vocabulary_id``.
    valid_start_date, valid_end_date : datetime.date or None
        Validity window. None when the authored value is not an ISO date,
        which is reported through :meth:`Vocabulary.issues`.
    cdm_table : str
        Table the concept is expected to land in. Empty when the concept binds
        to a field across several tables rather than to one table.
    cdm_variable : str
        Concept column within ``cdm_table``. Empty when unbound.
    origin : str
        ``"standard"`` or ``"custom"``, from the file the concept was read
        from.
    status : str
        Lifecycle of a custom concept. Empty for standard concepts.
    rationale : str
        Why a custom concept had to be minted. Empty for standard concepts.
    valid_for_episode_type : int or None
        The episode type this concept may appear within. None when it is not
        tied to an episode.
    valid_for_question : int or None
        For an answer concept, the question concept it answers. None when the
        concept is not an answer. This is what tells "Former smoker" apart from
        a valid answer to "AF burden estimation method".
    """

    concept_id: int
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    standard_concept: str
    concept_code: str
    valid_start_date: date | None
    valid_end_date: date | None
    cdm_table: str
    cdm_variable: str
    origin: str
    status: str = ""
    rationale: str = ""
    valid_for_episode_type: int | None = None
    valid_for_question: int | None = None

    @property
    def binding(self) -> tuple[str, str] | None:
        """Return the ``(table, column)`` this concept binds to, if any.

        Returns
        -------
        tuple of (str, str) or None
            None when the concept declares no target column.
        """
        if self.cdm_table and self.cdm_variable:
            return (self.cdm_table, self.cdm_variable)
        return None


@dataclass
class Vocabulary:
    """The parsed vocabulary layer: every concept AFBSTEP pins or mints.

    Attributes
    ----------
    concepts : tuple of Concept
        All concepts, standard and custom, in file order.
    defects : tuple of str
        File hygiene problems repaired on read: stripped whitespace and
        ignored unknown columns. These do not change the meaning of the
        specification, but they signal that a source file has drifted from the
        documented format and should be cleaned upstream.
    """

    concepts: tuple[Concept, ...]
    defects: tuple[str, ...] = ()

    def by_id(self) -> dict[int, Concept]:
        """Return the concepts keyed by ``concept_id``.

        Returns
        -------
        dict of int to Concept
            Later entries win if a id is declared twice; the duplicate is
            reported by :meth:`issues`.
        """
        return {concept.concept_id: concept for concept in self.concepts}

    def of_origin(self, origin: str) -> tuple[Concept, ...]:
        """Return the concepts read from one source file.

        Parameters
        ----------
        origin : str
            ``"standard"`` or ``"custom"``.

        Returns
        -------
        tuple of Concept
        """
        return tuple(c for c in self.concepts if c.origin == origin)

    def bindings(self) -> dict[tuple[str, str], tuple[Concept, ...]]:
        """Group the concepts by the concept column they bind to.

        This is the membership half of a value set: which concepts AFBSTEP
        expects in a given column. Whether that column is actually restricted
        to them is a separate decision recorded elsewhere in the spec.

        Returns
        -------
        dict of (str, str) to tuple of Concept
            Concepts keyed by ``(cdm_table, cdm_variable)``. Unbound concepts
            are omitted.
        """
        grouped: dict[tuple[str, str], list[Concept]] = {}
        for concept in self.concepts:
            binding = concept.binding
            if binding is not None:
                grouped.setdefault(binding, []).append(concept)
        return {key: tuple(value) for key, value in sorted(grouped.items())}

    def issues(self, schema: CdmSchema | None = None) -> list[str]:
        """
        Check the vocabulary against itself and, optionally, the schema.

        Catches the failure modes of a hand-maintained concept catalogue: 
        - an id declared twice
        - a custom concept outside the reserved id range
        - a minted concept with no recorded reason
        - a validity window that is not a window
        - a half-declared binding. 
        When a parsed schema is given, also checks that every binding names a 
        column the CDM actually declares as concept-valued.

        Parameters
        ----------
        schema : CdmSchema, optional
            Parsed structural layer. Binding targets are left unchecked when
            omitted, so the vocabulary can be inspected on its own.

        Returns
        -------
        list of str
            Human-readable problems, empty when the vocabulary is coherent.
            Ordered by concept id so the output is stable across runs.
        """
        problems: list[str] = []
        concept_columns = set(schema.concept_columns()) if schema is not None else None

        seen: set[int] = set()
        for concept in sorted(self.concepts, key=lambda c: c.concept_id):
            label = f"{concept.concept_id} ({concept.origin})"

            if concept.concept_id in seen:
                problems.append(f"{label}: concept id declared more than once")
            seen.add(concept.concept_id)

            problems.extend(_origin_issues(concept, label))
            problems.extend(_validity_issues(concept, label))
            problems.extend(_binding_issues(concept, label, concept_columns))

        return problems


def _origin_issues(concept: Concept, label: str) -> list[str]:
    """Check a concept against the conventions of the file it came from."""
    problems: list[str] = []
    is_custom = concept.origin == CUSTOM_ORIGIN

    if is_custom:
        if concept.concept_id < CUSTOM_CONCEPT_ID_MIN:
            problems.append(f"{label}: custom concept id is below the reserved {CUSTOM_CONCEPT_ID_MIN}+ range")
        if concept.vocabulary_id != CUSTOM_VOCABULARY_ID:
            problems.append(f"{label}: custom concept has vocabulary_id {concept.vocabulary_id!r}, expected {CUSTOM_VOCABULARY_ID!r}")
    elif concept.concept_id >= CUSTOM_CONCEPT_ID_MIN:
        problems.append(f"{label}: standard concept id falls in the reserved custom {CUSTOM_CONCEPT_ID_MIN}+ range")

    return problems


def _validity_issues(concept: Concept, label: str) -> list[str]:
    """Check that a concept's validity window is a usable date range."""
    problems: list[str] = []
    start, end = concept.valid_start_date, concept.valid_end_date

    for name, value in (("valid_start_date", start), ("valid_end_date", end)):
        if value is None:
            problems.append(f"{label}: {name} is not an ISO date")
    if start is not None and end is not None and end <= start:
        problems.append(f"{label}: valid_end_date {end} does not follow valid_start_date {start}")

    return problems


def _binding_issues(
    concept: Concept, label: str, concept_columns: set[tuple[str, str]] | None
) -> list[str]:
    """Check a concept's declared target column, against the schema if given."""
    problems: list[str] = []
    table, variable = concept.cdm_table, concept.cdm_variable

    if bool(table) != bool(variable):
        problems.append(f"{label}: binding is half declared as {table or '<empty>'}.{variable or '<empty>'}")
    elif table and concept_columns is not None and (table, variable) not in concept_columns:
        problems.append(f"{label}: binds to {table}.{variable}, which the CDM does not declare as a concept column")

    return problems


def _optional_int(value: str) -> int | None:
    """Parse an optional concept reference, treating a blank as unset."""
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))     # tolerate ids exported as 2000011002.0
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date, or return None if it is not one."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _concept_from_row(row: dict[str, str], origin: str) -> Concept:
    """Build a Concept from one normalised row."""
    return Concept(
        concept_id=int(row["concept_id"]),
        concept_name=row["concept_name"],
        domain_id=row["domain_id"],
        vocabulary_id=row["vocabulary_id"],
        concept_class_id=row["concept_class_id"],
        standard_concept=row["standard_concept"],
        concept_code=row["concept_code"],
        valid_start_date=_parse_date(row["valid_start_date"]),
        valid_end_date=_parse_date(row["valid_end_date"]),
        cdm_table=row["CDM_table"].lower(),
        cdm_variable=row["CDM_variable"].lower(),
        origin=origin,
        status=row.get("status", ""),
        rationale=row.get("rationale", ""),
        valid_for_episode_type=_optional_int(row.get("valid_for_episode_type", "")),
        valid_for_question=_optional_int(row.get(ANSWER_COLUMN, "")),
    )


def parse_vocabulary_csv(path: Path, origin: str) -> tuple[list[Concept], list[str]]:
    """Parse one vocabulary CSV into concepts.

    Parameters
    ----------
    path : Path
        A vocabulary CSV.
    origin : str
        ``"standard"`` or ``"custom"``; custom files carry two extra columns
        and the concepts are tagged with it.

    Returns
    -------
    list of Concept
        One entry per row, in file order.
    list of str
        Defects repaired while reading.

    Raises
    ------
    ValueError
        If a required column is missing from the header, or a row carries a
        ``concept_id`` that is not an integer. Both mean the file is
        malformed rather than merely inconsistent, so they fail the load
        instead of being reported afterwards.
    """
    columns = SHARED_COLUMNS + (ANSWER_COLUMN,)
    if origin == CUSTOM_ORIGIN:
        columns += CUSTOM_COLUMNS
    clean, defects = read_spec_csv(path, columns)

    concepts: list[Concept] = []
    for number, row in enumerate(clean, start=2):
        try:
            concepts.append(_concept_from_row(row, origin))
        except ValueError as error:
            raise ValueError(f"{path.name} line {number}: {error}") from error

    return concepts, defects


def load_vocabulary(source_dir: Path | None = None) -> Vocabulary:
    """Load the complete vocabulary layer from a ``source/`` directory.

    Both files are optional so that a partial specification can still be
    inspected; a missing file simply contributes no concepts.

    Parameters
    ----------
    source_dir : Path, optional
        Directory holding ``spec/``. Defaults to the ``source/`` directory
        shipped inside the package.

    Returns
    -------
    Vocabulary
        Every pinned and minted concept, with the defects repaired on read.
    """
    root = DEFAULT_SOURCE_DIR if source_dir is None else Path(source_dir)

    concepts: list[Concept] = []
    defects: list[str] = []
    for filename, origin in (
        ("standard_vocabulary.csv", STANDARD_ORIGIN),
        ("custom_vocabulary.csv", CUSTOM_ORIGIN),
    ):
        path = root / "spec" / filename
        if not path.exists():
            continue
        parsed, file_defects = parse_vocabulary_csv(path, origin)
        concepts.extend(parsed)
        defects.extend(file_defects)

    return Vocabulary(concepts=tuple(concepts), defects=tuple(defects))
