"""
Validate a partner dataset against the AFBSTEP specification.

A partner hands over one CSV per CDM table. This module reads that directory
and reports where it departs from what the specification asks for, in five
layers, each answering a different question:

conformance
    Are the tables and fields there, and does every field the CDM declares
    NOT NULL actually carry a value? A CSV can hold an empty cell where a
    database could not, so this is checked before the export is ever loaded.
referential
    Do the foreign keys resolve within the dataset?
terminology
    Are the concept columns carrying concepts the specification recognises?
plausibility
    Do the recorded values fall in the range, and carry the unit, that the
    specification expects for that concept?
minimal data set
    Do the concepts the minimal data set requires appear at all?

Findings are graded. 
An **error** is a departure from something the specification actually states
A **warning** is something worth a human  looking at that the specification does 
not forbid — most importantly a concept AFBSTEP has not pinned, or one  that is not standard. 
Neither is rejected: the pinned concepts are a default offered to partners rather 
than a whitelist, and a site that already codes its data one way is not asked to 
recode it in order to take part.

Validation is offline and deterministic by construction: every judgement is
made against the pinned spec files, never against a vocabulary service.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from afbstepomop.output_validator.resolver import (
    DomainExpectations,
    PinnedVocabulary,
    VocabularySource,
    domain_expectations,
)
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import Vocabulary

ERROR = "error"
WARNING = "warning"

CONFORMANCE = "conformance"
REFERENTIAL = "referential"
TERMINOLOGY = "terminology"
PLAUSIBILITY = "plausibility"
MINIMAL = "minimal data set"

UNMAPPED_CONCEPT_ID = 0
UNIT_COLUMN = "unit_concept_id"
SOURCE_CONCEPT_SUFFIX = "_source_concept_id"
MANDATORY_TIER = "mandatory"
OPTIONAL_TIER = "optional"

#: Fields where a row's existence is the whole assertion. A condition row means
#: the patient has the condition; no row means either that they do not, or that
#: nobody looked, and the two are indistinguishable. Absence of such a concept
#: therefore cannot be reported as an error.
PRESENCE_ONLY_FIELDS = frozenset({
    "condition_occurrence.condition_concept_id",
    "procedure_occurrence.procedure_concept_id",
    "drug_exposure.drug_concept_id",
    "device_exposure.device_concept_id",
})


@dataclass(frozen=True)
class Finding:
    """One departure from the specification.

    Attributes
    ----------
    layer : str
        Which validation layer raised it.
    severity : str
        ``"error"`` for a stated requirement that is unmet, ``"warning"`` for
        something the specification permits but a human should see.
    table : str
        Table the finding concerns; empty when it concerns the dataset.
    column : str
        Column the finding concerns; empty when it concerns a whole table.
    message : str
        What is wrong, in the terms a partner can act on.
    count : int
        How many rows are affected, ``0`` when the finding is not row-level.
    """

    layer: str
    severity: str
    table: str
    column: str
    message: str
    count: int = 0

    def __str__(self) -> str:
        """Render the finding as one readable line."""
        where = ".".join(part for part in (self.table, self.column) if part)
        rows = f" ({self.count} rows)" if self.count else ""
        return f"[{self.severity}] {self.layer}: {where or 'dataset'}: {self.message}{rows}"


@dataclass
class Report:
    """The outcome of validating one dataset.

    Attributes
    ----------
    findings : tuple of Finding
        Every departure found, in layer order.
    row_counts : dict of str to int
        Rows read per table.
    vocabulary_label : str
        Which vocabulary the concepts were checked against. Part of the
        verdict, not a footnote: passing against the pinned specification is a
        weaker claim than passing against a full vocabulary release, and a
        reader cannot tell the two apart otherwise.
    unchecked : tuple of str
        What this run could not check, in the reader's terms. A partner
        validating locally without a vocabulary should learn that the server
        will check more on upload, rather than discovering it when the upload
        fails.
    """

    findings: tuple[Finding, ...]
    row_counts: dict[str, int]
    vocabulary_label: str = ""
    unchecked: tuple[str, ...] = ()

    def of_severity(self, severity: str) -> tuple[Finding, ...]:
        """Return the findings of one severity.

        Parameters
        ----------
        severity : str
            ``"error"`` or ``"warning"``.

        Returns
        -------
        tuple of Finding
        """
        return tuple(f for f in self.findings if f.severity == severity)

    @property
    def passed(self) -> bool:
        """Whether the dataset met every stated requirement.

        Warnings do not fail a dataset: they mark things the specification
        permits but a reviewer should see.
        """
        return not self.of_severity(ERROR)

    def summary(self) -> str:
        """Render the report as readable text.

        Returns
        -------
        str
            A verdict line, the row counts, and every finding.
        """
        errors = self.of_severity(ERROR)
        warnings = self.of_severity(WARNING)

        verdict = "PASSED" if self.passed else "FAILED"
        mode = f" [concepts checked against: {self.vocabulary_label}]" if self.vocabulary_label else ""

        lines = [
            f"AFBSTEP validation: {verdict}"
            f" — {len(errors)} error(s), {len(warnings)} warning(s){mode}",
            "",
            "Tables read:",
        ]
        lines += [f"  {name}: {count} rows" for name, count in sorted(self.row_counts.items())]
        if self.findings:
            lines += ["", "Findings:"] + [f"  {finding}" for finding in self.findings]
        if self.unchecked:
            lines += ["", "Not checked by this run:"] + [f"  - {item}" for item in self.unchecked]
        return "\n".join(lines)


def read_dataset(directory: Path, spec: ProjectSpec) -> dict[str, list[dict[str, str]]]:
    """Read one CSV per in-scope table from a partner's export directory.

    Values are read exactly as authored: this is partner data, not
    specification, so nothing is normalised away before it is judged.

    Parameters
    ----------
    directory : Path
        Directory holding ``<table>.csv`` files.
    spec : ProjectSpec
        Parsed project layer, deciding which tables to look for.

    Returns
    -------
    dict of str to list of dict
        Rows keyed by table name. Tables with no file are absent from the
        result, which the conformance layer then reports.
    """
    dataset: dict[str, list[dict[str, str]]] = {}
    for table in spec.in_scope():
        path = directory / f"{table}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            dataset[table] = list(csv.DictReader(handle))
    return dataset


def _conformance_findings(
    dataset: dict[str, list[dict[str, str]]], schema: CdmSchema, spec: ProjectSpec
) -> list[Finding]:
    """Check that the expected tables and columns are present."""
    findings: list[Finding] = []

    for table in spec.in_scope():
        if table in dataset or spec.tier(table) == OPTIONAL_TIER:
            # An optional table is in scope but asked for nothing: reporting its
            # absence would be noise a partner cannot act on.
            continue
        tier = spec.tier(table)
        findings.append(
            Finding(
                layer=CONFORMANCE,
                severity=ERROR if tier == MANDATORY_TIER else WARNING,
                table=table,
                column="",
                message=f"no {table}.csv found, but the table is {tier}",
            )
        )

    for table, rows in sorted(dataset.items()):
        declared = set(schema.tables[table].columns)
        present = set(rows[0]) if rows else set()

        for column in sorted(present - declared):
            findings.append(
                Finding(CONFORMANCE, WARNING, table, column, "column is not part of the CDM table and will not load")
            )
        for column in sorted(c for c in declared - present if not schema.tables[table].columns[c].nullable):
            findings.append(
                Finding(CONFORMANCE, ERROR, table, column, "column is missing but the CDM declares it NOT NULL")
            )

        # A CSV can hold an empty cell where a database could not. Every field
        # the CDM declares NOT NULL must actually carry a value, or the export
        # will fail to load — and finding that out at load time costs the
        # partner another round trip.
        for column in sorted(present & declared):
            if schema.tables[table].columns[column].nullable:
                continue
            empty = sum(1 for row in rows if not (row.get(column) or "").strip())
            if empty:
                findings.append(
                    Finding(
                        CONFORMANCE, ERROR, table, column,
                        "the CDM declares this field NOT NULL, but it is empty",
                        count=empty,
                    )
                )

        if not rows:
            findings.append(Finding(CONFORMANCE, WARNING, table, "", "table is present but empty"))

    return findings


def _referential_findings(dataset: dict[str, list[dict[str, str]]], schema: CdmSchema) -> list[Finding]:
    """Check that foreign keys resolve against the tables in the dataset.

    Only keys whose parent table is present are checked, since a key into a
    table the partner was never asked to supply cannot be resolved and is not
    the partner's error.
    """
    findings: list[Finding] = []

    keys_by_table = {
        table: {row.get(schema.tables[table].primary_key[0], "").strip() for row in rows}
        for table, rows in dataset.items()
        if schema.tables[table].primary_key
    }

    for table, rows in sorted(dataset.items()):
        for fk in schema.tables[table].foreign_keys:
            parent_keys = keys_by_table.get(fk.parent_table)
            if parent_keys is None or fk.column not in schema.tables[table].columns:
                continue

            dangling = {
                value
                for row in rows
                if (value := (row.get(fk.column) or "").strip())
                and value not in parent_keys
            }
            if dangling:
                findings.append(
                    Finding(
                        REFERENTIAL, ERROR, table, fk.column,
                        f"{len(dangling)} value(s) do not exist in {fk.parent_table}.{fk.parent_column}",
                        count=len(dangling),
                    )
                )

    return findings


def _concept_findings(
    table: str,
    column: str,
    usage: dict[int, int],
    source: VocabularySource,
    expectations: DomainExpectations,
) -> list[Finding]:
    """Judge every concept used in one field against the vocabulary source.

    Concepts are judged uniformly, whether or not the specification pins them
    to this field. Whether the specification itself is coherent is a separate
    question, answered by the maintainers' own check, and deliberately not
    worked around here.

    How loudly a problem can be stated depends on what the source knows: an
    unresolvable concept is an error only when the source is exhaustive, since
    otherwise its silence about a concept is not evidence of anything.

    Parameters
    ----------
    table, column : str
        The field being judged.
    usage : dict of int to int
        Concept ids used in it, and how many rows used each.
    source : VocabularySource
        The vocabulary to resolve against.

    Returns
    -------
    list of Finding
    """
    findings: list[Finding] = []
    expected = expectations.for_field(table, column)
    is_source_field = column.endswith(SOURCE_CONCEPT_SUFFIX)
    unresolved: dict[int, int] = {}

    for concept_id, rows in sorted(usage.items()):
        record = source.lookup(concept_id)

        if record is None:
            if source.is_exhaustive:
                findings.append(
                    Finding(TERMINOLOGY, ERROR, table, column,
                            f"concept {concept_id} does not exist", count=rows)
                )
            else:
                unresolved[concept_id] = rows
            continue

        if not record.is_current:
            # Retired upstream, but not rejected: a site whose data predates the
            # retirement should not have to recode it, for the same reason a
            # non-standard concept is accepted.
            findings.append(
                Finding(TERMINOLOGY, WARNING, table, column,
                        f"concept {concept_id} ({record.concept_name}) was retired upstream "
                        f"({record.invalid_reason}); it may not resolve in current OHDSI tooling",
                        count=rows)
            )
        elif not is_source_field and not record.is_standard:
            # AFBSTEP accepts non-standard concepts: a site that already codes
            # its data one way should not have to recode it to take part. The
            # consequence is real but is the reader's to weigh, not a failure,
            # so it is reported rather than rejected.
            findings.append(
                Finding(TERMINOLOGY, WARNING, table, column,
                        f"concept {concept_id} ({record.concept_name}) is not a standard concept; "
                        "analyses that select only standard concepts will not see these rows", count=rows)
            )
        elif expected is not None and not any(record.in_domain(d) for d in expected):
            wanted = " or ".join(repr(d) for d in sorted(expected))
            findings.append(
                Finding(TERMINOLOGY, ERROR, table, column,
                        f"concept {concept_id} ({record.concept_name}) is in domain "
                        f"{record.domain_id!r}, but this field expects {wanted}", count=rows)
            )

    if unresolved:
        findings.append(
            Finding(
                TERMINOLOGY, WARNING, table, column,
                f"{len(unresolved)} concept(s) not in {source.label}, e.g. "
                f"{sorted(unresolved)[:3]}; existence and domain were not verified",
                count=sum(unresolved.values()),
            )
        )

    return findings


def _terminology_findings(
    dataset: dict[str, list[dict[str, str]]],
    schema: CdmSchema,
    source: VocabularySource,
    expectations: DomainExpectations,
) -> list[Finding]:
    """Check concept fields against whichever vocabulary this run can reach.

    With only the pinned specification available, a concept it does not hold
    can never be more than a warning: the pinned file is explicitly not a
    whitelist, so its silence is not evidence. Given an exhaustive vocabulary,
    the same concept is judged properly — whether it exists, is standard, is
    current, and belongs in the field it occupies.
    """
    findings: list[Finding] = []

    for table, rows in sorted(dataset.items()):
        for column in schema.tables[table].concept_columns():
            malformed, unmapped = 0, 0
            usage: dict[int, int] = {}

            for row in rows:
                value = (row.get(column) or "").strip()
                if not value:
                    continue
                try:
                    concept_id = int(value)
                except ValueError:
                    malformed += 1
                    continue
                if concept_id == UNMAPPED_CONCEPT_ID:
                    unmapped += 1
                else:
                    usage[concept_id] = usage.get(concept_id, 0) + 1

            if malformed:
                findings.append(
                    Finding(TERMINOLOGY, ERROR, table, column, "value is not a concept id", count=malformed)
                )
            if unmapped:
                findings.append(
                    Finding(TERMINOLOGY, WARNING, table, column, "concept id 0: source value did not map", count=unmapped)
                )
            findings.extend(_concept_findings(table, column, usage, source, expectations))

    return findings



def _bounds(rule) -> str:
    """Describe a rule's bounds, however many of them it gives."""
    if rule.min_value is not None and rule.max_value is not None:
        return f"{rule.min_value:g}-{rule.max_value:g}"
    if rule.min_value is not None:
        return f"minimum of {rule.min_value:g}"
    return f"maximum of {rule.max_value:g}"


def _plausibility_findings(
    dataset: dict[str, list[dict[str, str]]], schema: CdmSchema, spec: ProjectSpec
) -> list[Finding]:
    """Check recorded values against the range and unit their concept requires.

    Constraints are keyed by concept, so each rule first selects the rows
    carrying that concept in the table's own concept column — the column named
    after the table, which OMOP uses for what a row is *about*. A table
    without such a column cannot be checked this way and is reported rather
    than skipped silently.
    """
    findings: list[Finding] = []

    for rule in spec.value_rules:
        rows = dataset.get(rule.table)
        if not rows:
            continue

        table = schema.tables[rule.table]
        concept_column = f"{rule.table}_concept_id"
        if concept_column not in table.concept_columns():
            findings.append(
                Finding(
                    PLAUSIBILITY, WARNING, rule.table, rule.column,
                    f"cannot apply the range for concept {rule.concept_id}: "
                    f"{rule.table} has no {concept_column} to select rows by",
                )
            )
            continue

        out_of_range, wrong_unit, malformed = 0, 0, 0
        for row in rows:
            if (row.get(concept_column) or "").strip() != str(rule.concept_id):
                continue

            # Each bound stands alone: a rule may give only a lower limit, only
            # an upper one, or neither when it constrains just the unit.
            raw = (row.get(rule.column) or "").strip()
            if raw and rule.has_range:
                try:
                    value = float(raw)
                except ValueError:
                    malformed += 1
                else:
                    below = rule.min_value is not None and value < rule.min_value
                    above = rule.max_value is not None and value > rule.max_value
                    if below or above:
                        out_of_range += 1

            unit = (row.get(UNIT_COLUMN) or "").strip()
            if rule.unit_concept_id is not None and unit and unit != str(rule.unit_concept_id):
                wrong_unit += 1

        if malformed:
            findings.append(
                Finding(PLAUSIBILITY, ERROR, rule.table, rule.column,
                        f"concept {rule.concept_id}: value is not a number", count=malformed)
            )
        if out_of_range:
            findings.append(
                Finding(PLAUSIBILITY, ERROR, rule.table, rule.column,
                        f"concept {rule.concept_id}: value outside the expected "
                        f"{_bounds(rule)}", count=out_of_range)
            )
        if wrong_unit:
            findings.append(
                Finding(PLAUSIBILITY, ERROR, rule.table, UNIT_COLUMN,
                        f"concept {rule.concept_id}: unit is not the expected {rule.unit_concept_id}",
                        count=wrong_unit)
            )

    return findings


def _unchecked_notes(source: VocabularySource) -> tuple[str, ...]:
    """List what this run could not verify, in terms a partner can act on.

    A local run without a full vocabulary is a weaker check than the one the
    server performs on upload. Saying so in the report turns a later upload
    failure into something the partner was told to expect.
    """
    notes: list[str] = []
    if not source.is_exhaustive:
        notes.append(
            f"Concept existence, standard status and domain, for concepts not in {source.label}. "
            "A mistyped concept id cannot be told apart from a valid one that is simply not pinned. "
            "Attach a full vocabulary release to check these."
        )
    notes.append(
        "Dataset-level coverage: whether an absent record means the finding was absent "
        "or was never assessed. The specification does not yet define this."
    )
    return tuple(notes)



def _minimal_concept_findings(
    dataset: dict[str, list[dict[str, str]]],
    schema: CdmSchema,
    spec: ProjectSpec,
    vocabulary: Vocabulary,
) -> list[Finding]:
    """Check that the minimal data set's concepts actually appear.

    A dataset can populate every required field and still omit a required
    *item*: all condition rows complete, and not one of them heart failure.
    This layer answers the second question.

    How loudly an absence can be reported depends on how the concept is
    carried. A measurement concept that never appears was not collected, and
    that is an error. A condition concept that never appears may simply mean no
    patient had it — indistinguishable from not collecting it — so it can only
    be a warning until a coverage declaration says which.
    """
    findings: list[Finding] = []
    if not spec.minimal_concepts:
        return findings

    present: set[int] = set()
    for table, rows in dataset.items():
        for column in schema.tables[table].concept_columns():
            for row in rows:
                value = (row.get(column) or "").strip()
                if value.isdigit() and int(value) != UNMAPPED_CONCEPT_ID:
                    present.add(int(value))

    pinned = vocabulary.by_id()
    for entry in spec.minimal_concepts:
        if entry.concept_id is None or entry.concept_id in present:
            continue
        concept = pinned.get(entry.concept_id)
        if concept is None:
            continue                      # unpinned: the spec check reports it
        target = f"{concept.cdm_table}.{concept.cdm_variable}"
        presence_only = target in PRESENCE_ONLY_FIELDS
        findings.append(
            Finding(
                MINIMAL,
                WARNING if presence_only else ERROR,
                concept.cdm_table,
                concept.cdm_variable,
                f"{entry.domain}/{entry.item!r} (concept {entry.concept_id}) appears nowhere in the dataset"
                + ("; no row may mean absent or may mean not collected" if presence_only
                   else "; this item is part of the minimal data set"),
            )
        )
    return findings


def validate(
    dataset: dict[str, list[dict[str, str]]],
    schema: CdmSchema,
    spec: ProjectSpec,
    vocabulary: Vocabulary,
    vocabulary_source: VocabularySource | None = None,
) -> Report:
    """Validate a partner dataset against the whole specification.

    Parameters
    ----------
    dataset : dict of str to list of dict
        Rows keyed by table name, as returned by :func:`read_dataset`.
    schema : CdmSchema
        Parsed structural layer.
    spec : ProjectSpec
        Parsed project layer.
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    vocabulary_source : VocabularySource, optional
        The vocabulary concepts are resolved against. Defaults to the pinned
        specification, which needs no download and is what a partner has
        without further setup. Pass an exhaustive source — a downloaded
        vocabulary release — to have concept existence, standard status and
        domain checked properly. The server passes one; a partner may.

    Returns
    -------
    Report
        Findings in layer order, the row count of every table read, which
        vocabulary was used, and what this run could not check.
    """
    source = PinnedVocabulary(vocabulary) if vocabulary_source is None else vocabulary_source

    findings = (
        _conformance_findings(dataset, schema, spec)
        + _referential_findings(dataset, schema)
        + _terminology_findings(dataset, schema, source, domain_expectations(schema, vocabulary))
        + _plausibility_findings(dataset, schema, spec)
        + _minimal_concept_findings(dataset, schema, spec, vocabulary)
    )
    return Report(
        findings=tuple(findings),
        row_counts={table: len(rows) for table, rows in dataset.items()},
        vocabulary_label=source.label,
        unchecked=_unchecked_notes(source),
    )
