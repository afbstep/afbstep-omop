"""Parse the project layer of the AFBSTEP CDM specification.

The project layer describes *what AFBSTEP asks partners to produce*, as
distinct from what the CDM permits. It is assembled from two files under
``source/spec/``:

``spec/tables.csv``
    Which tables a partner has to populate at all, and how mandatory each one
    is. A table that is not listed is out of scope, so the file holds only
    decisions someone actually made.
``spec/minimal_dataset.csv``
    Which columns must be populated, and how completely. This is the layer
    that may be stricter than the DDL: the CDM's ``NOT NULL`` is a floor, and
    AFBSTEP may require a nullable column to be filled, or accept an
    uninformative value in a required one.
``plausibility.csv``
    Which concepts must be bounded, and what those bounds are.
``minimal_concepts.csv``
    Which concepts must be present in a dataset, and what clinical item they represent.

The  following are checked:

Table scope (tables.csv)

- tier is one of the documented values
-every scope decision has a recorded rationale
- an in-scope table actually exists in the CDM
- a table used elsewhere in the spec (a field rule, a value rule, or a vocabulary binding) isn't silently left out of tables.csv

Field requirements (minimal_dataset.csv)

- no (table, column) requirement declared twice
- requirement is one of the documented values
- has a rationale
- not declared for an out-of-scope table
- table/column named actually exist in the CDM
- a field marked not_used isn't NOT NULL in the DDL — a project requirement may only be stricter than the CDM, never looser

Value/plausibility rules (plausibility.csv)

-  min_value < max_value when both given
- the rule states at least a bound or a unit (not neither)
- has a rationale
- not declared for an out-of-scope table
- table/column named exist in the CDM
- the constrained concept is pinned in the vocabulary
- the unit concept, if any, is pinned in the vocabulary

Minimal concepts (minimal_concepts.csv)

- every concept it names is actually pinned in the vocabulary — this is the check producing most of the current 15 failures


Requirements are graded rather than boolean. A hard "required" is the wrong
instrument for clinical data, where real extracts are never complete on
anything and a rule every site fails on day one becomes a rule every site
learns to ignore. ``expected`` carries a completeness threshold instead, which
separates a forgotten field from a cohort with gaps.

This module reads requirements only. Which concepts are permitted in a column
is a different question, answered by the vocabulary and binding layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from afbstepomop.source_validator.csvspec import read_spec_csv

if TYPE_CHECKING:
    from afbstepomop.source_validator.structural import CdmSchema
    from afbstepomop.source_validator.vocabulary import Vocabulary

from afbstepomop.source_validator.paths import DEFAULT_SOURCE_DIR  # noqa: E402  (re-exported for callers)

OUT_OF_SCOPE = "out_of_scope"

#: How firmly AFBSTEP asks for a table, from strongest to weakest. ``optional``
#: sits below ``expected``: the table is in scope and may be populated, but a
#: partner who omits it is not told anything.
TIERS = ("mandatory", "expected", "optional", OUT_OF_SCOPE)
REQUIREMENTS = ("required", "expected", "optional", "not_used")
THRESHOLD_REQUIREMENT = "expected"

TABLE_COLUMNS = ("table", "tier", "rationale")
FIELD_COLUMNS = ("table", "column", "requirement", "rationale")
MINIMAL_COLUMNS = ("part_c_domain", "part_c_domain_label", "part_c_item", "concept_id", "rationale")
VALUE_COLUMNS = (
    "concept_id", "CDM_table", "CDM_variable", "unit_concept_id",
    "min_value", "max_value", "rationale",
)


@dataclass(frozen=True)
class TableRule:
    """Whether AFBSTEP asks partners to populate one table.

    Attributes
    ----------
    table : str
        Lower-cased table name.
    tier : str
        ``"mandatory"``, ``"expected"`` or ``"out_of_scope"``.
    rationale : str
        Why the table sits in that tier.
    """

    table: str
    tier: str
    rationale: str


@dataclass(frozen=True)
class FieldRule:
    """How completely AFBSTEP asks partners to populate one column.

    Attributes
    ----------
    table, column : str
        Lower-cased target, which must resolve against the parsed schema.
    requirement : str
        ``"required"``, ``"expected"``, ``"optional"`` or ``"not_used"``.
    rationale : str
        Why the column carries that requirement.
    """

    table: str
    column: str
    requirement: str
    rationale: str

    @property
    def target(self) -> tuple[str, str]:
        """Return the ``(table, column)`` this rule constrains."""
        return (self.table, self.column)


@dataclass(frozen=True)
class ValueRule:
    """The range and unit AFBSTEP expects for one concept's values.

    Keyed by concept rather than by column: ``measurement.value_as_number``
    holds AF burden, ejection fraction and heart rate at once, so a range
    attached to the column alone would be meaningless.

    Attributes
    ----------
    concept_id : int
        The concept whose values are constrained.
    table, column : str
        Where those values live.
    unit_concept_id : int or None
        Required unit; None when the quantity is unitless, such as a score.
    min_value, max_value : float or None
        Inclusive bounds, either of which may stand alone: a count bounded
        below by zero needs no upper limit. Deliberately generous where given —
        these catch unit and transcription errors, they do not define clinical
        normality. Both are None when the rule constrains only the unit.
    rationale : str
        Clinical basis for the constraint.
    """

    concept_id: int
    table: str
    column: str
    unit_concept_id: int | None
    min_value: float | None
    max_value: float | None
    rationale: str

    @property
    def has_range(self) -> bool:
        """Whether this rule bounds the value at all.

        One bound is a complete constraint on its own: a count cannot be
        negative, and saying so does not require inventing an upper limit.
        """
        return self.min_value is not None or self.max_value is not None

    @property
    def constrains_something(self) -> bool:
        """Whether the rule states anything a dataset could violate."""
        return self.has_range or self.unit_concept_id is not None



@dataclass(frozen=True)
class MinimalConcept:
    """One item of the AF-B-STEP minimal data set.

    The minimal data set is stated twice over, and the halves answer different
    questions: ``minimal_dataset.csv`` says which CDM *fields* must be
    populated, this says which *concepts* must be present. A dataset can
    satisfy one and fail the other — every field filled, but no heart failure
    recorded anywhere.

    Item names come from the consortium's Part C questionnaire and are
    deliberately clinical rather than terminological: submitters read "Prior
    stroke or transient ischemic attack", not "Cerebrovascular accident".

    Attributes
    ----------
    domain : str
        Part C domain code, such as ``"MH"`` or ``"CE/AE"``.
    domain_label : str
        Human-readable domain name, repeated on every item of the domain.
    item : str
        The clinical name of the item, authoritative for display.
    concept_id : int or None
        The concept carrying this item. None when none has been agreed yet,
        which is a real state rather than an omission.
    rationale : str
        Why the domain is collected.
    """

    domain: str
    domain_label: str
    item: str
    concept_id: int | None
    rationale: str


@dataclass
class ProjectSpec:
    """The parsed project layer: what AFBSTEP asks partners to produce.

    Attributes
    ----------
    table_rules : dict of str to TableRule
        Scope decisions keyed by table name.
    field_rules : tuple of FieldRule
        Field requirements, in file order.
    minimal_concepts : tuple of MinimalConcept
        The minimal data set stated as concepts, in Part C display order.
    value_rules : tuple of ValueRule
        Range and unit constraints, in file order.
    defects : tuple of str
        File hygiene repaired on read, as for the other spec layers.
    """

    table_rules: dict[str, TableRule]
    field_rules: tuple[FieldRule, ...] = ()
    value_rules: tuple[ValueRule, ...] = ()
    minimal_concepts: tuple[MinimalConcept, ...] = ()
    defects: tuple[str, ...] = ()

    def tier(self, table: str) -> str:
        """Return the tier of one table.

        Parameters
        ----------
        table : str
            Table name.

        Returns
        -------
        str
            The declared tier, or ``"out_of_scope"`` when the table is not
            listed. Silence means out of scope by design, so the file holds
            only decisions someone made.
        """
        rule = self.table_rules.get(table.lower())
        return rule.tier if rule is not None else OUT_OF_SCOPE

    def in_scope(self) -> tuple[str, ...]:
        """Return the tables a partner is asked to populate.

        Returns
        -------
        tuple of str
            Table names whose tier is not ``"out_of_scope"``, sorted.
        """
        return tuple(sorted(name for name, rule in self.table_rules.items() if rule.tier != OUT_OF_SCOPE))

    def rules_for(self, table: str) -> tuple[FieldRule, ...]:
        """Return the field requirements declared for one table.

        Parameters
        ----------
        table : str
            Table name.

        Returns
        -------
        tuple of FieldRule
            In file order; empty when the table has no declared requirements.
        """
        return tuple(rule for rule in self.field_rules if rule.table == table.lower())

    def issues(self, schema: CdmSchema | None = None, vocabulary: Vocabulary | None = None) -> list[str]:
        """Check the project layer against itself and, optionally, the schema.

        Catches a tier or requirement outside the documented vocabulary, a
        threshold on a requirement that takes none, a decision recorded twice,
        a requirement for a table nobody put in scope, and — when a schema is
        given — a target that does not exist or a requirement looser than the
        DDL.

        Parameters
        ----------
        schema : CdmSchema, optional
            Parsed structural layer. Targets are left unchecked when omitted.
        vocabulary : Vocabulary, optional
            Parsed vocabulary layer. When given, every concept and unit named
            by a value rule must be pinned in it.

        Returns
        -------
        list of str
            Human-readable problems, empty when the layer is coherent. Sorted
            so the output is stable across runs.
        """
        problems: list[str] = []

        for name in sorted(self.table_rules):
            rule = self.table_rules[name]
            if rule.tier not in TIERS:
                problems.append(f"{name}: tier {rule.tier!r} is not one of {', '.join(TIERS)}")
            if not rule.rationale:
                problems.append(f"{name}: no rationale recorded for tier {rule.tier!r}")
            if schema is not None and name not in schema.tables:
                problems.append(f"{name}: in scope but no such table in the CDM")

        seen: set[tuple[str, str]] = set()
        for rule in sorted(self.field_rules, key=lambda r: r.target):
            problems.extend(self._field_issues(rule, seen, schema))
            seen.add(rule.target)

        for rule in sorted(self.value_rules, key=lambda r: (r.concept_id, r.table, r.column)):
            problems.extend(self._value_issues(rule, schema, vocabulary))

        problems.extend(self._undeclared_table_issues(vocabulary))
        problems.extend(self._minimal_concept_issues(vocabulary))

        return problems

    def _minimal_concept_issues(self, vocabulary: Vocabulary | None) -> list[str]:
        """
        Check that every concept the minimal data set names is askable.

        Two things have to hold:

        1. The concept must be pinned, since an item naming a concept the registry 
           does not hold cannot be asked of a partner: nothing tells them which code to use. 
        
        2. It must name the column it belongs in. Because the binding decides how
           loudly an absence is reported in the output validator. 
           An item bound to a presence-only field is a warning when missing, 
           since no row may simply mean no patient had it; anything else is an error. 
           An unbound item defaults to an error and its finding cannot say where the item belongs.

        Parameters
        ----------
        vocabulary : Vocabulary or None
            Parsed vocabulary layer. Neither rule can be applied without it.

        Returns
        -------
        list of str
            One message per minimal item that cannot be asked of a partner.
        """
        if vocabulary is None:
            return []

        pinned = vocabulary.by_id()
        problems: list[str] = []

        for entry in self.minimal_concepts:
            if entry.concept_id is None:
                continue

            label = f"minimal item {entry.domain}/{entry.item!r} names concept {entry.concept_id}"
            concept = pinned.get(entry.concept_id)

            if concept is None:
                problems.append(f"{label}, which the vocabulary does not pin")
            elif not concept.cdm_table or not concept.cdm_variable:
                problems.append(f"{label}, which the vocabulary binds to no CDM column")

        return problems

    def _undeclared_table_issues(self, vocabulary: Vocabulary | None) -> list[str]:
        """Report tables the rest of the specification uses but scope omits.

        Pinning a concept to a table, or stating a requirement about it, is a
        statement that AFBSTEP wants data there. Leaving that table out of
        ``tables.csv`` silently puts it out of scope, so the two halves of the
        specification would disagree about whether a partner should populate
        it. Silence means out of scope only for tables nothing else mentions.

        Parameters
        ----------
        vocabulary : Vocabulary, optional
            Parsed vocabulary layer. Concept bindings are left unchecked when
            omitted; requirements and ranges are checked either way.

        Returns
        -------
        list of str
        """
        used: dict[str, set[str]] = {}
        for rule in self.field_rules:
            used.setdefault(rule.table, set()).add("minimal_dataset.csv")
        for rule in self.value_rules:
            used.setdefault(rule.table, set()).add("plausibility.csv")
        if vocabulary is not None:
            for concept in vocabulary.concepts:
                if concept.cdm_table:
                    used.setdefault(concept.cdm_table, set()).add("the vocabulary")

        return [
            f"{table}: used by {', '.join(sorted(sources))} but tables.csv does not declare it, "
            f"so it is out of scope"
            for table, sources in sorted(used.items())
            if self.tier(table) == OUT_OF_SCOPE
        ]

    def _value_issues(
        self, rule: ValueRule, schema: CdmSchema | None, vocabulary: Vocabulary | None
    ) -> list[str]:
        """Check one range constraint. See :meth:`issues`."""
        problems: list[str] = []
        label = f"concept {rule.concept_id} in {rule.table}.{rule.column}"

        if rule.min_value is not None and rule.max_value is not None and rule.min_value >= rule.max_value:
            problems.append(f"{label}: min_value {rule.min_value} is not below max_value {rule.max_value}")
        if not rule.constrains_something:
            problems.append(f"{label}: states neither a bound nor a unit, so it constrains nothing")
        if not rule.rationale:
            problems.append(f"{label}: no rationale recorded for the range")
        if self.tier(rule.table) == OUT_OF_SCOPE:
            problems.append(f"{label}: range declared for a table that is out of scope")

        if schema is not None:
            table = schema.tables.get(rule.table)
            if table is None:
                problems.append(f"{label}: no such table in the CDM")
            elif rule.column not in table.columns:
                problems.append(f"{label}: no such column in the CDM")

        if vocabulary is not None:
            pinned = vocabulary.by_id()
            if rule.concept_id not in pinned:
                problems.append(f"{label}: concept is not pinned in the vocabulary")
            if rule.unit_concept_id is not None and rule.unit_concept_id not in pinned:
                problems.append(f"{label}: unit concept {rule.unit_concept_id} is not pinned in the vocabulary")

        return problems

    def _field_issues(
        self, rule: FieldRule, seen: set[tuple[str, str]], schema: CdmSchema | None
    ) -> list[str]:
        """Check one field requirement. See :meth:`issues`."""
        problems: list[str] = []
        label = f"{rule.table}.{rule.column}"

        if rule.target in seen:
            problems.append(f"{label}: requirement declared more than once")
        if rule.requirement not in REQUIREMENTS:
            problems.append(f"{label}: requirement {rule.requirement!r} is not one of {', '.join(REQUIREMENTS)}")
        if not rule.rationale:
            problems.append(f"{label}: no rationale recorded for requirement {rule.requirement!r}")

        if self.tier(rule.table) == OUT_OF_SCOPE:
            problems.append(f"{label}: requirement declared for a table that is out of scope")

        problems.extend(self._schema_issues(rule, label, schema))
        return problems

    @staticmethod
    def _schema_issues(rule: FieldRule, label: str, schema: CdmSchema | None) -> list[str]:
        """Check one field requirement against the CDM. See :meth:`issues`."""
        if schema is None:
            return []

        table = schema.tables.get(rule.table)
        if table is None:
            return [f"{label}: no such table in the CDM"]

        column = table.columns.get(rule.column)
        if column is None:
            return [f"{label}: no such column in the CDM"]

        if rule.requirement == "not_used" and not column.nullable:
            return [f"{label}: marked not_used but the CDM declares it NOT NULL; a project requirement may be stricter than the DDL, never looser"]

        return []


def parse_tables_csv(path: Path) -> tuple[dict[str, TableRule], list[str]]:
    """Parse ``tables.csv`` into scope decisions.

    Parameters
    ----------
    path : Path
        The scope CSV.

    Returns
    -------
    dict of str to TableRule
        Rules keyed by lower-cased table name. A table declared twice keeps
        its last row; the duplicate is reported by :meth:`ProjectSpec.issues`.
    list of str
        Defects repaired while reading.
    """
    rows, defects = read_spec_csv(path, TABLE_COLUMNS)
    rules = {
        row["table"].lower(): TableRule(
            table=row["table"].lower(),
            tier=row["tier"].lower(),
            rationale=row["rationale"],
        )
        for row in rows
    }
    if len(rules) != len(rows):
        defects.append(f"{path.name}: a table is declared more than once")
    return rules, defects


def parse_minimal_dataset_csv(path: Path) -> tuple[list[FieldRule], list[str]]:
    """Parse ``minimal_dataset.csv`` into field requirements.

    Parameters
    ----------
    path : Path
        The field requirement CSV.

    Returns
    -------
    list of FieldRule
        One entry per row, in file order.
    list of str
        Defects repaired while reading.

    """
    rows, defects = read_spec_csv(path, FIELD_COLUMNS)

    rules: list[FieldRule] = []
    for number, row in enumerate(rows, start=2):
        label = f"{path.name} line {number}"
        rules.append(
            FieldRule(
                table=row["table"].lower(),
                column=row["column"].lower(),
                requirement=row["requirement"].lower(),
                rationale=row["rationale"],
            )
        )
    return rules, defects


def _parse_optional_int(value: str, label: str, field: str) -> int | None:
    """Parse an optional integer field, treating a blank as unset."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{label}: {field} {value!r} is not an integer") from error


def _parse_optional_float(value: str, label: str, field: str) -> float | None:
    """Parse an optional numeric field, treating a blank as unset.

    A blank bound is meaningful rather than missing: a categorical concept has
    no range to state, and the row exists to carry its episode-type context.

    Raises
    ------
    ValueError
        If the value is present but not a number.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{label}: {field} {value!r} is not a number") from error


def parse_plausibility_csv(path: Path) -> tuple[list[ValueRule], list[str]]:
    """Parse ``plausibility.csv`` into range and unit constraints.

    Parameters
    ----------
    path : Path
        The plausibility CSV.

    Returns
    -------
    list of ValueRule
        One entry per row, in file order.
    list of str
        Defects repaired while reading.

    Raises
    ------
    ValueError
        If a row carries a non-numeric concept id, unit or bound.
    """
    rows, defects = read_spec_csv(path, VALUE_COLUMNS)

    rules: list[ValueRule] = []
    for number, row in enumerate(rows, start=2):
        label = f"{path.name} line {number}"
        try:
            rules.append(
                ValueRule(
                    concept_id=int(row["concept_id"]),
                    table=row["CDM_table"].lower(),
                    column=row["CDM_variable"].lower(),
                    unit_concept_id=_parse_optional_int(row["unit_concept_id"], label, "unit_concept_id"),
                    min_value=_parse_optional_float(row["min_value"], label, "min_value"),
                    max_value=_parse_optional_float(row["max_value"], label, "max_value"),
                    rationale=row["rationale"],
                )
            )
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error

    return rules, defects



def parse_minimal_concepts_csv(path: Path) -> tuple[list[MinimalConcept], list[str]]:
    """Parse ``minimal_concepts.csv`` into minimal data set items.

    Parameters
    ----------
    path : Path
        The minimal concepts CSV.

    Returns
    -------
    list of MinimalConcept
        One entry per item, in file order, which is Part C display order.
    list of str
        Defects repaired while reading.

    Raises
    ------
    ValueError
        If a row carries a non-integer ``concept_id``.
    """
    rows, defects = read_spec_csv(path, MINIMAL_COLUMNS)

    entries = [
        MinimalConcept(
            domain=row["part_c_domain"],
            domain_label=row["part_c_domain_label"],
            item=row["part_c_item"],
            concept_id=_parse_optional_int(row["concept_id"], f"{path.name} line {number}", "concept_id"),
            rationale=row["rationale"],
        )
        for number, row in enumerate(rows, start=2)
    ]
    return entries, defects


def load_spec(source_dir: Path | None = None) -> ProjectSpec:
    """Load the complete project layer from a ``source/`` directory.

    Both files are optional so that a partial specification can still be
    inspected; a missing ``tables.csv`` simply puts every table out of scope.

    Parameters
    ----------
    source_dir : Path, optional
        Directory holding ``spec/``. Defaults to the ``source/`` directory
        shipped inside the package.

    Returns
    -------
    ProjectSpec
        Scope and field requirements, with the defects repaired on read.
    """
    root = DEFAULT_SOURCE_DIR if source_dir is None else Path(source_dir)

    table_rules: dict[str, TableRule] = {}
    field_rules: list[FieldRule] = []
    value_rules: list[ValueRule] = []
    minimal_concepts: list[MinimalConcept] = []
    defects: list[str] = []

    tables_path = root / "spec" / "tables.csv"
    if tables_path.exists():
        table_rules, table_defects = parse_tables_csv(tables_path)
        defects.extend(table_defects)

    fields_path = root / "spec" / "minimal_dataset.csv"
    if fields_path.exists():
        field_rules, field_defects = parse_minimal_dataset_csv(fields_path)
        defects.extend(field_defects)

    values_path = root / "spec" / "plausibility.csv"
    if values_path.exists():
        value_rules, value_defects = parse_plausibility_csv(values_path)
        defects.extend(value_defects)

    minimal_path = root / "spec" / "minimal_concepts.csv"
    if minimal_path.exists():
        minimal_concepts, minimal_defects = parse_minimal_concepts_csv(minimal_path)
        defects.extend(minimal_defects)

    return ProjectSpec(
        table_rules=table_rules,
        field_rules=tuple(field_rules),
        value_rules=tuple(value_rules),
        minimal_concepts=tuple(minimal_concepts),
        defects=tuple(defects),
    )
