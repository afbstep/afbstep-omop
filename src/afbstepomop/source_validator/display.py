"""Render what the specification files actually say, in readable form.

The loaders turn ``source/`` into typed objects, which is what code needs and
not what a person needs. This module goes the other way: given any loaded
layer, it renders the underlying DDL or CSV content as text, so that a data
scientist can see the specification without opening five files or knowing which
attribute holds what.

One entry point covers all three layers::

    from afbstepomop.source_validator import describe, load_structural

    print(describe(load_structural()))              # every table, at a glance
    print(describe(load_structural(), "person"))    # that table's DDL
    print(describe(load_vocabulary(), "measurement"))
    print(describe(load_vocabulary(), "all"))    # every concept, as a catalogue
    print(describe(load_spec(), "condition_occurrence"))

The optional second argument narrows to one table, or for the vocabulary to a
single ``"table.column"``. Passing ``"all"`` to the vocabulary lists every
pinned concept instead, which is the reference a mapping needs when looking for
the concept for a source variable. Output is plain text and is returned rather than
printed, so it can be paged, written to a file, or shown in a notebook cell.
"""

from __future__ import annotations

from functools import singledispatch
from itertools import groupby

from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import Vocabulary

NAME_WIDTH = 58

#: Passed as ``subject`` to list every concept rather than group them by field.
CATALOGUE_SUBJECT = "all"


def _truncate(text: str, width: int = NAME_WIDTH) -> str:
    """Shorten text to ``width`` characters, marking where it was cut."""
    return text if len(text) <= width else text[: width - 1] + "…"


def _grid(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    """Lay out rows as an aligned text table.

    Parameters
    ----------
    headers : tuple of str
        Column headings.
    rows : list of tuple of str
        Cell values, one tuple per row.

    Returns
    -------
    list of str
        Header line, a rule, then one line per row. Empty when there are no
        rows, so callers can say "none" in their own words.
    """
    if not rows:
        return []

    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
    lines = ["  ".join(head.ljust(width) for head, width in zip(headers, widths)).rstrip()]
    lines.append("  ".join("─" * width for width in widths))
    lines += ["  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]
    return lines


def _heading(title: str, subtitle: str = "") -> list[str]:
    """Render a section title with an underline, and an optional subtitle."""
    lines = [title, "=" * len(title)]
    if subtitle:
        lines.append(subtitle)
    lines.append("")
    return lines


@singledispatch
def describe(source: object, subject: str | None = None) -> str:
    """Render one loaded specification layer as readable text.

    Parameters
    ----------
    source : CdmSchema, Vocabulary or ProjectSpec
        A layer returned by one of the loaders.
    subject : str, optional
        Narrow the output to one table. For a vocabulary, also accepts
        ``"table.column"`` to show a single concept column.

    Returns
    -------
    str
        Plain text, ready to print.

    Raises
    ------
    TypeError
        If ``source`` is not one of the three loaded layers.
    """
    raise TypeError(f"describe() does not handle {type(source).__name__}; pass a loaded specification layer")


@describe.register
def _(source: CdmSchema, subject: str | None = None) -> str:
    """Render the structural layer: the tables and columns the CDM declares."""
    if subject is not None:
        return _describe_table(source, subject)

    rows = [
        (
            table.name,
            table.origin,
            str(len(table.columns)),
            ", ".join(table.primary_key) or "—",
            str(len(table.foreign_keys)),
            str(len(table.concept_columns())),
        )
        for table in sorted(source.tables.values(), key=lambda t: (t.origin != "custom", t.name))
    ]
    lines = _heading(
        f"OMOP CDM {source.cdm_version} — structural layer",
        f"{len(source.tables)} tables, {len(source.concept_columns())} concept columns. "
        "Custom AFBSTEP tables listed first.",
    )
    lines += _grid(("table", "origin", "cols", "primary key", "fks", "concepts"), rows)
    return "\n".join(lines)


def _describe_table(source: CdmSchema, name: str) -> str:
    """Render one table the way its DDL declares it."""
    table = source.tables.get(name.lower())
    if table is None:
        known = ", ".join(sorted(source.tables)[:6])
        return f"No table named {name!r}. Known tables include: {known}, …"

    references = {fk.column: f"{fk.parent_table}.{fk.parent_column}" for fk in table.foreign_keys}
    concept_columns = set(table.concept_columns())

    rows = []
    for column in table.columns.values():
        marks = []
        if column.name in table.primary_key:
            marks.append("PK")
        if column.name in concept_columns:
            marks.append("concept")
        rows.append(
            (
                column.name,
                column.sql_type,
                "NOT NULL" if not column.nullable else "",
                " ".join(marks),
                references.get(column.name, ""),
            )
        )

    lines = _heading(
        f"{table.name}",
        f"{table.origin} table · {len(table.columns)} columns · "
        f"primary key {', '.join(table.primary_key) or 'none declared'}",
    )
    lines += _grid(("column", "type", "null", "role", "references"), rows)
    return "\n".join(lines)


@describe.register
def _(source: Vocabulary, subject: str | None = None) -> str:
    """Render the vocabulary layer: the concepts AFBSTEP pins or mints."""
    bindings = source.bindings()

    if subject is not None:
        if subject.lower() == CATALOGUE_SUBJECT:
            return _describe_catalogue(source)
        return _describe_concepts(source, subject)

    rows = [
        (table, column, str(len(concepts)), _truncate(concepts[0].concept_name, 44))
        for (table, column), concepts in bindings.items()
    ]
    unbound = [c for c in source.concepts if not c.cdm_table]
    lines = _heading(
        "AFBSTEP vocabulary layer",
        f"{len(source.concepts)} concepts "
        f"({len(source.of_origin('standard'))} pinned standard, {len(source.of_origin('custom'))} AFBSTEP-minted) "
        f"over {len(bindings)} concept columns.",
    )
    lines += _grid(("table", "column", "n", "example"), rows)
    if unbound:
        lines += ["", f"{len(unbound)} unbound (vocabulary infrastructure, not data):"]
        lines += [f"  {c.concept_id}  {c.concept_class_id}  {c.concept_name}" for c in unbound]
    return "\n".join(lines)


def _describe_catalogue(source: Vocabulary) -> str:
    """List every pinned concept, sorted for lookup rather than by field.

    Grouped views omit concepts bound to no field; this one includes them, so
    it is the only complete listing of what the specification holds.

    Parameters
    ----------
    source : Vocabulary
        Parsed vocabulary layer.

    Returns
    -------
    str
    """
    rows = [
        (
            str(c.concept_id),
            c.origin,
            c.domain_id,
            f"{c.cdm_table}.{c.cdm_variable}" if c.cdm_table else "—",
            _truncate(c.concept_name),
        )
        for c in sorted(source.concepts, key=lambda c: (c.domain_id, c.concept_name))
    ]
    lines = _heading(
        "AFBSTEP concept catalogue",
        f"{len(rows)} concepts, sorted by domain then name. "
        "'target' is the field the specification suggests for the concept.",
    )
    lines += _grid(("concept_id", "origin", "domain", "target", "concept_name"), rows)
    return "\n".join(lines)


def _describe_concepts(source: Vocabulary, subject: str) -> str:
    """Render the concepts bound to one table, or to one concept column."""
    bindings = source.bindings()
    wanted = subject.lower()
    selected = {
        key: concepts
        for key, concepts in bindings.items()
        if key[0] == wanted or f"{key[0]}.{key[1]}" == wanted
    }

    if not selected:
        known = ", ".join(sorted({table for table, _ in bindings}))
        return f"No concepts bound to {subject!r}. Bound tables: {known}"

    lines: list[str] = []
    for (table, column), concepts in selected.items():
        lines += _heading(f"{table}.{column}", f"{len(concepts)} concepts offered here by the specification")
        lines += _grid(
            ("concept_id", "origin", "domain", "concept_name"),
            [
                (str(c.concept_id), c.origin, c.domain_id, _truncate(c.concept_name))
                for c in sorted(concepts, key=lambda c: c.concept_name)
            ],
        )
        lines.append("")
    return "\n".join(lines).rstrip()


@describe.register
def _(source: ProjectSpec, subject: str | None = None) -> str:
    """Render the project layer: what AFBSTEP asks partners to produce."""
    if subject is not None:
        return _describe_requirements(source, subject)

    rows = [
        (
            rule.table,
            rule.tier,
            str(len(source.rules_for(rule.table))),
            str(sum(1 for v in source.value_rules if v.table == rule.table)),
            _truncate(rule.rationale, 52),
        )
        for rule in sorted(source.table_rules.values(), key=lambda r: (r.tier, r.table))
    ]
    lines = _heading(
        "AFBSTEP project layer",
        f"{len(source.in_scope())} tables in scope, {len(source.field_rules)} field requirements, "
        f"{len(source.value_rules)} value ranges. A table not listed is out of scope.",
    )
    lines += _grid(("table", "tier", "fields", "ranges", "rationale"), rows)
    return "\n".join(lines)


def _bound(value: float | None) -> str:
    """Render one end of a value range.

    An open end is blank rather than ``0``: a rule may legitimately state one
    bound or neither, and printing a missing bound as a number would state a
    constraint the specification does not make.

    Parameters
    ----------
    value : float or None
        One end of the range, or None when the specification leaves it open.

    Returns
    -------
    str
    """
    return "" if value is None else f"{value:g}"


def _describe_requirements(source: ProjectSpec, subject: str) -> str:
    """Render the field requirements and value ranges for one table."""
    table = subject.lower()
    rules = source.rules_for(table)
    ranges = [rule for rule in source.value_rules if rule.table == table]

    if not rules and not ranges:
        known = ", ".join(sorted(source.in_scope()))
        return (
            f"No requirements declared for {subject!r} (tier: {source.tier(table)}). "
            f"The subject is a table name; in scope: {known}"
        )

    lines = _heading(f"{table}", f"tier: {source.tier(table)}")
    lines += _grid(
        ("column", "requirement", "rationale"),
        [
            (
                rule.column,
                rule.requirement,
                _truncate(rule.rationale, 60),
            )
            for rule in rules
        ],
    )
    if ranges:
        lines += ["", "value ranges (keyed by concept, not by column):"]
        lines += _grid(
            ("concept_id", "column", "unit", "min", "max"),
            [
                (
                    str(rule.concept_id),
                    rule.column,
                    "" if rule.unit_concept_id is None else str(rule.unit_concept_id),
                    _bound(rule.min_value),
                    _bound(rule.max_value),
                )
                for rule in ranges
            ],
        )
    return "\n".join(lines)


def _minimal_rows(
    spec: ProjectSpec, vocabulary: Vocabulary, wanted: str | None
) -> list[tuple[str, str, str, str]]:
    """Collect the minimal items, each resolved to the field it belongs in.

    Parameters
    ----------
    spec : ProjectSpec
        Parsed project layer, holding the minimal data set.
    vocabulary : Vocabulary
        Parsed vocabulary layer, supplying each concept's binding.
    wanted : str or None
        Lower-cased Part C domain or table name to keep, or None to keep all.

    Returns
    -------
    list of tuple
        ``(domain, item, concept_id, target)``, sorted so that grouping by
        domain needs no second pass. ``target`` is an em dash for an item the
        vocabulary does not bind: ``--check-spec`` reports those, and this view
        shows them rather than quietly dropping them.
    """
    pinned = vocabulary.by_id()
    rows: list[tuple[str, str, str, str]] = []

    for entry in spec.minimal_concepts:
        concept = pinned.get(entry.concept_id) if entry.concept_id is not None else None
        table = concept.cdm_table if concept else ""
        target = f"{table}.{concept.cdm_variable}" if concept and table else "—"

        if wanted is not None and wanted not in (entry.domain.lower(), table.lower()):
            continue

        rows.append((entry.domain, entry.item, str(entry.concept_id), target))

    return sorted(rows)


def describe_minimal(
    spec: ProjectSpec, vocabulary: Vocabulary, subject: str | None = None
) -> str:
    """List the concepts an export must contain, and the field each belongs in.

    The other views answer "what may I put in this field?", which is the
    question of someone already at the right column. This one answers the
    question a partner starts with: "what must I produce, and where does each
    piece go?". Assembling that from the per-field views would mean touring
    every bound column and collecting the required concepts by hand.

    It is a sibling of :func:`describe` rather than one of its subjects because
    it joins two layers: the item and its Part C grouping come from the project
    layer, the field it belongs in from the vocabulary.

    Parameters
    ----------
    spec : ProjectSpec
        Parsed project layer, holding the minimal data set.
    vocabulary : Vocabulary
        Parsed vocabulary layer, deciding where each concept lives.
    subject : str, optional
        Narrow to one Part C domain (``"MH"``) or one table
        (``"observation"``). Case-insensitive. Without it, every item is listed.

    Returns
    -------
    str
        Plain text, grouped by Part C domain.
    """
    rows = _minimal_rows(spec, vocabulary, None if subject is None else subject.lower())

    if not rows:
        domains = sorted({entry.domain for entry in spec.minimal_concepts})
        tables = sorted({row[3].split(".")[0] for row in _minimal_rows(spec, vocabulary, None)})
        return (
            f"No minimal items for {subject!r}. "
            f"Part C domains: {', '.join(domains)}. Tables: {', '.join(tables)}"
        )

    labels = {entry.domain: entry.domain_label for entry in spec.minimal_concepts}
    # Items, not concepts: several Part C items may name the same concept, so
    # counting rows as concepts would overstate what a partner has to produce.
    distinct = len({row[2] for row in rows})
    lines = _heading(
        "AFBSTEP minimal data set",
        f"{len(rows)} items over {distinct} distinct concepts that a conforming "
        "export must contain, and the field each belongs in.",
    )

    for domain, group in groupby(rows, key=lambda row: row[0]):
        entries = list(group)
        lines.append(f"{domain} — {labels.get(domain, domain)}  ({len(entries)} items)")
        lines += _grid(
            ("item", "concept_id", "belongs in"),
            [(_truncate(item, 46), concept_id, target) for _, item, concept_id, target in entries],
        )
        lines.append("")

    return "\n".join(lines).rstrip()
