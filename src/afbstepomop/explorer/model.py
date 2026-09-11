"""Assemble what the explorer page shows, out of the three specification layers.

The explorer is a renderer of the specification, in the same sense as
:mod:`afbstepomop.source_validator.display` — a different output target for the
same content. This module is the half that decides *what* is shown; the
rendering half decides how.

The split is deliberate. Everything here is a fact read from ``source/``:
a tier, a bound, a permitted concept. Nothing here knows about HTML, colours,
links or layout, so a change to the page's appearance cannot quietly become a
change to what the specification is claimed to say.

Two properties matter more than convenience:

gaps are shown, not dropped
    A minimal-data-set item naming a concept no vocabulary file pins is carried
    through as an unresolved item rather than silently omitted. The page is
    then also a review tool: the same rendering that helps a partner shows a
    maintainer where the specification is still thin.
out-of-scope tables are kept
    All CDM tables are modelled, each carrying its tier. Showing which tables a
    partner does *not* populate is the thing a stock OMOP diagram cannot do,
    and it is only possible if the model keeps them.

Concept records are repeated wherever they are shown rather than referenced by
id. The whole vocabulary is a couple of hundred rows, so the duplication costs
nothing and keeps the rendering side free of lookups.
"""

from __future__ import annotations

from dataclasses import dataclass

from afbstepomop.source_validator.spec import OUT_OF_SCOPE, MinimalConcept, ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import CUSTOM_ORIGIN, Concept, Vocabulary

#: Shown for a minimal item whose concept has not been decided yet.
NO_CONCEPT_AGREED = "no concept agreed yet"

#: Shown for a minimal item naming a concept that no vocabulary file pins.
NOT_PINNED = "names a concept the vocabulary does not pin"


@dataclass(frozen=True)
class ConceptRef:
    """A concept named from another concept, without its full record.

    Attributes
    ----------
    concept_id : int
        The concept referred to.
    name : str
        Its name, or a placeholder when the reference does not resolve.
    resolved : bool
        Whether the referenced concept is pinned. An unresolved reference is a
        specification gap and is shown as one.
    """

    concept_id: int
    name: str
    resolved: bool


@dataclass(frozen=True)
class BoundsView:
    """One plausibility rule, as the page states it.

    Attributes
    ----------
    table, column : str
        Where the constrained values live.
    minimum, maximum : float or None
        Inclusive bounds, either of which may stand alone.
    unit_concept_id : int or None
        Required unit, when the rule names one.
    unit_name : str
        Name of that unit, empty when there is none or it is not pinned.
    rationale : str
        Clinical basis for the constraint.
    """

    table: str
    column: str
    minimum: float | None
    maximum: float | None
    unit_concept_id: int | None
    unit_name: str
    rationale: str


@dataclass(frozen=True)
class ConceptView:
    """One concept, with everything the specification says about it.

    Attributes
    ----------
    concept_id : int
        OMOP concept id. Values from ``2000000000`` up are AFBSTEP's own.
    name : str
        Concept name as pinned.
    domain_id, vocabulary_id, concept_class_id, concept_code : str
        Terminological identity, as exported.
    standard_concept : str
        ``"S"`` for a standard concept, empty otherwise.
    origin : str
        ``"standard"`` or ``"custom"``.
    is_custom : bool
        Whether AFBSTEP minted it. Custom concepts have no external page, which
        the renderer has to know so it does not emit a dead link.
    table, column : str
        The concept field this concept is permitted in.
    status, rationale : str
        Project bookkeeping, carried through verbatim.
    is_minimal : bool
        Whether this concept carries an item of the minimal data set. The page
        shows the minimal data set rather than the whole vocabulary, so this is
        what decides whether a concept is displayed at all.
    bounds : tuple of BoundsView
        Plausibility rules keyed to this concept, empty when unconstrained.
    question : ConceptRef or None
        For an answer concept, the question it answers.
    answers : tuple of ConceptRef
        For a question concept, the answers declared permissible for it.
    """

    concept_id: int
    name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    concept_code: str
    standard_concept: str
    origin: str
    is_custom: bool
    table: str
    column: str
    status: str
    rationale: str
    is_minimal: bool
    bounds: tuple[BoundsView, ...]
    question: ConceptRef | None
    answers: tuple[ConceptRef, ...]


@dataclass(frozen=True)
class FieldView:
    """One column of one table, with the project's requirement for it.

    Attributes
    ----------
    name, sql_type : str
        As declared in the DDL.
    nullable : bool
        The CDM's own requirement, which is a floor: AFBSTEP may ask for more
        than the DDL does, never less.
    requirement : str
        What AFBSTEP asks, from ``minimal_dataset.csv``; empty when the
        specification says nothing about this column.
    rationale : str
        Why, when a requirement was recorded.
    is_concept_field : bool
        Whether the column is a foreign key to ``concept``.
    references : str
        Table this column points at, empty when it points at nothing.
    concepts : tuple of ConceptView
        Concepts the specification permits here. Empty on a concept field means
        the field is unbound: the CDM decides what it accepts, not AFBSTEP.
    """

    name: str
    sql_type: str
    nullable: bool
    requirement: str
    rationale: str
    is_concept_field: bool
    references: str
    concepts: tuple[ConceptView, ...]


@dataclass(frozen=True)
class TableView:
    """One CDM table as the page presents it.

    Attributes
    ----------
    name : str
        Table name.
    origin : str
        ``"structural"`` for a stock OMOP table, ``"custom"`` for an AFBSTEP
        addition. Custom tables have no OHDSI documentation page.
    tier : str
        How firmly AFBSTEP asks for it, including ``"out_of_scope"``.
    in_scope : bool
        Whether a partner populates it at all.
    rationale : str
        Why the table carries that tier.
    primary_key : tuple of str
        Its primary key columns.
    fields : tuple of FieldView
        Every column, in DDL order.
    minimal_items : tuple of ChecklistItem
        The minimal-data-set items recorded in this table. This is what the
        table's panel shows: what a partner must put here, rather than
        everything the CDM would accept.
    """

    name: str
    origin: str
    tier: str
    in_scope: bool
    rationale: str
    primary_key: tuple[str, ...]
    fields: tuple[FieldView, ...]
    minimal_items: tuple[ChecklistItem, ...] = ()

    @property
    def concept_fields(self) -> tuple[FieldView, ...]:
        """The columns of this table that hold a concept."""
        return tuple(f for f in self.fields if f.is_concept_field)

    @property
    def required_fields(self) -> tuple[FieldView, ...]:
        """The columns AFBSTEP records a requirement for.

        A column the specification says nothing about is not part of the
        minimal data set, so the page does not list it.
        """
        return tuple(f for f in self.fields if f.requirement)


@dataclass(frozen=True)
class SchemaEdge:
    """One foreign key between two tables, for the schema diagram.

    Attributes
    ----------
    table, column : str
        The referring side.
    parent_table, parent_column : str
        The referenced side.
    within_scope : bool
        Whether both ends are tables a partner populates. Edges leaving scope
        are kept so the diagram can show them when out-of-scope tables are
        revealed.
    """

    table: str
    column: str
    parent_table: str
    parent_column: str
    within_scope: bool


@dataclass(frozen=True)
class ChecklistItem:
    """One item of the minimal data set, with wherever it is recorded.

    Attributes
    ----------
    domain, domain_label : str
        Part C domain code and its human-readable name.
    item : str
        The clinical name of the item, authoritative for display.
    rationale : str
        Why the domain is collected.
    concept : ConceptView or None
        The concept carrying the item, when one is pinned.
    unresolved : str
        Empty when ``concept`` is present; otherwise why it is not, in the
        terms a reader can act on.
    """

    domain: str
    domain_label: str
    item: str
    rationale: str
    concept: ConceptView | None
    unresolved: str


@dataclass(frozen=True)
class ChecklistGroup:
    """The items of one Part C domain, kept in file order.

    Attributes
    ----------
    domain, label : str
        Domain code and name.
    items : tuple of ChecklistItem
        Its items.
    """

    domain: str
    label: str
    items: tuple[ChecklistItem, ...]

    @property
    def unresolved_count(self) -> int:
        """How many items of this domain name no pinned concept."""
        return sum(1 for item in self.items if item.concept is None)


@dataclass(frozen=True)
class ExplorerModel:
    """Everything the explorer page shows.

    Attributes
    ----------
    cdm_version : str
        The vendored CDM release the schema came from.
    checklist : tuple of ChecklistGroup
        The minimal data set, grouped by Part C domain. The page's front door.
    tables : tuple of TableView
        Every CDM table, in scope or not, alphabetically.
    edges : tuple of SchemaEdge
        Every foreign key between two known tables.
    """

    cdm_version: str
    checklist: tuple[ChecklistGroup, ...]
    tables: tuple[TableView, ...]
    edges: tuple[SchemaEdge, ...]

    @property
    def in_scope_tables(self) -> tuple[TableView, ...]:
        """The tables a partner populates."""
        return tuple(t for t in self.tables if t.in_scope)


def _bounds_by_concept(spec: ProjectSpec, vocabulary: Vocabulary) -> dict[int, tuple[BoundsView, ...]]:
    """Index the plausibility rules by the concept they constrain.

    Unit concept ids are resolved to names here rather than at render time,
    because resolving them needs the vocabulary and the renderer does not get
    it.

    Parameters
    ----------
    spec : ProjectSpec
        The project layer, holding the value rules.
    vocabulary : Vocabulary
        Used to name the unit concepts.

    Returns
    -------
    dict of int to tuple of BoundsView
        Rules per concept id. A concept may be constrained in more than one
        place, so the value is a tuple.
    """
    by_id = vocabulary.by_id()
    index: dict[int, list[BoundsView]] = {}
    for rule in spec.value_rules:
        unit = by_id.get(rule.unit_concept_id) if rule.unit_concept_id is not None else None
        index.setdefault(rule.concept_id, []).append(
            BoundsView(
                table=rule.table,
                column=rule.column,
                minimum=rule.min_value,
                maximum=rule.max_value,
                unit_concept_id=rule.unit_concept_id,
                unit_name=unit.concept_name if unit is not None else "",
                rationale=rule.rationale,
            )
        )
    return {concept_id: tuple(rules) for concept_id, rules in index.items()}


def _answers_by_question(vocabulary: Vocabulary) -> dict[int, tuple[ConceptRef, ...]]:
    """Invert ``valid_for_question`` into question id to permitted answers.

    The specification records the relation on the answer, which is the right
    place for it — an answer belongs to one question — but the page asks the
    question's side of it.

    Parameters
    ----------
    vocabulary : Vocabulary
        The pinned concepts.

    Returns
    -------
    dict of int to tuple of ConceptRef
        Answers per question concept id.
    """
    index: dict[int, list[ConceptRef]] = {}
    for concept in vocabulary.concepts:
        if concept.valid_for_question is None:
            continue
        index.setdefault(concept.valid_for_question, []).append(
            ConceptRef(concept_id=concept.concept_id, name=concept.concept_name, resolved=True)
        )
    return {question: tuple(answers) for question, answers in index.items()}


def _question_ref(concept: Concept, by_id: dict[int, Concept]) -> ConceptRef | None:
    """Resolve the question an answer concept belongs to.

    An unresolved reference is returned rather than dropped: a ``valid_for_question``
    naming a concept nothing pins is a specification gap, and the page is one of
    the places it should be visible.

    Parameters
    ----------
    concept : Concept
        The candidate answer concept.
    by_id : dict of int to Concept
        Every pinned concept.

    Returns
    -------
    ConceptRef or None
        None when the concept is not an answer to anything.
    """
    question_id = concept.valid_for_question
    if question_id is None:
        return None
    question = by_id.get(question_id)
    if question is None:
        return ConceptRef(concept_id=question_id, name=NOT_PINNED, resolved=False)
    return ConceptRef(concept_id=question_id, name=question.concept_name, resolved=True)


def _concept_views(spec: ProjectSpec, vocabulary: Vocabulary) -> dict[int, ConceptView]:
    """Build the view of every pinned concept, once, keyed by id.

    Parameters
    ----------
    spec : ProjectSpec
        Supplies the plausibility rules and which concepts are minimal.
    vocabulary : Vocabulary
        The pinned concepts.

    Returns
    -------
    dict of int to ConceptView
    """
    by_id = vocabulary.by_id()
    bounds = _bounds_by_concept(spec, vocabulary)
    answers = _answers_by_question(vocabulary)
    minimal = {m.concept_id for m in spec.minimal_concepts if m.concept_id is not None}

    return {
        concept.concept_id: ConceptView(
            concept_id=concept.concept_id,
            name=concept.concept_name,
            domain_id=concept.domain_id,
            vocabulary_id=concept.vocabulary_id,
            concept_class_id=concept.concept_class_id,
            concept_code=concept.concept_code,
            standard_concept=concept.standard_concept,
            origin=concept.origin,
            is_custom=concept.origin == CUSTOM_ORIGIN,
            table=concept.cdm_table,
            column=concept.cdm_variable,
            status=concept.status,
            rationale=concept.rationale,
            is_minimal=concept.concept_id in minimal,
            bounds=bounds.get(concept.concept_id, ()),
            question=_question_ref(concept, by_id),
            answers=answers.get(concept.concept_id, ()),
        )
        for concept in vocabulary.concepts
    }


def _fields_for(
    table_name: str,
    schema: CdmSchema,
    spec: ProjectSpec,
    permitted: dict[tuple[str, str], tuple[ConceptView, ...]],
) -> tuple[FieldView, ...]:
    """Build the column views of one table, in DDL order.

    Parameters
    ----------
    table_name : str
        Table to describe.
    schema : CdmSchema
        Supplies the columns, keys and foreign keys.
    spec : ProjectSpec
        Supplies the project's requirement per column.
    permitted : dict
        Concepts permitted per ``(table, column)``.

    Returns
    -------
    tuple of FieldView
    """
    table = schema.tables[table_name]
    concept_fields = set(table.concept_columns())
    requirements = {rule.column: rule for rule in spec.rules_for(table_name)}
    targets = {key.column: key.parent_table for key in table.foreign_keys}

    return tuple(
        FieldView(
            name=column.name,
            sql_type=column.sql_type,
            nullable=column.nullable,
            requirement=requirements[column.name].requirement if column.name in requirements else "",
            rationale=requirements[column.name].rationale if column.name in requirements else "",
            is_concept_field=column.name in concept_fields,
            references=targets.get(column.name, ""),
            concepts=permitted.get((table_name, column.name), ()),
        )
        for column in table.columns.values()
    )


def _items_by_table(checklist: tuple[ChecklistGroup, ...]) -> dict[str, tuple[ChecklistItem, ...]]:
    """Group the minimal-data-set items by the table that records them.

    An item that does not resolve to a pinned concept has no table to belong
    to, so it appears on the checklist and on no table. That is the honest
    reading: the specification has not yet said where it goes.

    Parameters
    ----------
    checklist : tuple of ChecklistGroup
        The grouped minimal data set.

    Returns
    -------
    dict of str to tuple of ChecklistItem
    """
    grouped: dict[str, list[ChecklistItem]] = {}
    for group in checklist:
        for item in group.items:
            if item.concept is None or not item.concept.table:
                continue
            grouped.setdefault(item.concept.table, []).append(item)
    return {table: tuple(items) for table, items in grouped.items()}


def _table_views(
    schema: CdmSchema,
    spec: ProjectSpec,
    permitted: dict[tuple[str, str], tuple[ConceptView, ...]],
    items_by_table: dict[str, tuple[ChecklistItem, ...]],
) -> tuple[TableView, ...]:
    """Build a view of every CDM table, in scope or not, alphabetically.

    Out-of-scope tables are kept in the model although the page does not draw
    them: the model is a reading of the specification, and which tables are
    excluded is part of what it says.

    Parameters
    ----------
    schema : CdmSchema
        The parsed DDL.
    spec : ProjectSpec
        Supplies tier and rationale.
    permitted : dict
        Concepts permitted per ``(table, column)``.
    items_by_table : dict
        Minimal-data-set items per table.

    Returns
    -------
    tuple of TableView
    """
    return tuple(
        TableView(
            name=name,
            origin=schema.tables[name].origin,
            tier=spec.tier(name),
            in_scope=spec.tier(name) != OUT_OF_SCOPE,
            rationale=spec.table_rules[name].rationale if name in spec.table_rules else "",
            primary_key=schema.tables[name].primary_key,
            fields=_fields_for(name, schema, spec, permitted),
            minimal_items=items_by_table.get(name, ()),
        )
        for name in sorted(schema.tables)
    )


def _edges(schema: CdmSchema, spec: ProjectSpec) -> tuple[SchemaEdge, ...]:
    """Collect the foreign keys between tables the schema knows.

    Keys pointing at ``concept`` are left out: every concept field points there,
    so drawing them would connect the whole diagram to one node and say nothing.

    Parameters
    ----------
    schema : CdmSchema
        The parsed DDL.
    spec : ProjectSpec
        Decides which endpoints count as in scope.

    Returns
    -------
    tuple of SchemaEdge
    """
    edges: list[SchemaEdge] = []
    for table in schema.tables.values():
        for key in table.foreign_keys:
            if key.parent_table == "concept" or key.parent_table not in schema.tables:
                continue
            edges.append(
                SchemaEdge(
                    table=key.table,
                    column=key.column,
                    parent_table=key.parent_table,
                    parent_column=key.parent_column,
                    within_scope=spec.tier(key.table) != OUT_OF_SCOPE
                    and spec.tier(key.parent_table) != OUT_OF_SCOPE,
                )
            )
    return tuple(edges)


def _checklist(spec: ProjectSpec, concepts: dict[int, ConceptView]) -> tuple[ChecklistGroup, ...]:
    """Group the minimal data set by Part C domain, in file order.

    File order is kept rather than sorted: the questionnaire's own sequence is
    the one the consortium reads it in.

    Parameters
    ----------
    spec : ProjectSpec
        Supplies the minimal concepts.
    concepts : dict of int to ConceptView
        Every pinned concept, for resolving each item.

    Returns
    -------
    tuple of ChecklistGroup
    """
    order: list[str] = []
    labels: dict[str, str] = {}
    grouped: dict[str, list[ChecklistItem]] = {}

    for minimal in spec.minimal_concepts:
        if minimal.domain not in grouped:
            order.append(minimal.domain)
            labels[minimal.domain] = minimal.domain_label
            grouped[minimal.domain] = []
        grouped[minimal.domain].append(_checklist_item(minimal, concepts))

    return tuple(
        ChecklistGroup(domain=domain, label=labels[domain], items=tuple(grouped[domain]))
        for domain in order
    )


def _checklist_item(minimal: MinimalConcept, concepts: dict[int, ConceptView]) -> ChecklistItem:
    """Resolve one minimal-data-set item against the pinned concepts.

    An item that does not resolve keeps its place and says why. The two ways it
    can fail are different states, not one: no concept has been agreed yet, or
    one has been named and no vocabulary file pins it.

    Parameters
    ----------
    minimal : MinimalConcept
        The item as the specification records it.
    concepts : dict of int to ConceptView
        Every pinned concept.

    Returns
    -------
    ChecklistItem
    """
    if minimal.concept_id is None:
        concept, unresolved = None, NO_CONCEPT_AGREED
    else:
        concept = concepts.get(minimal.concept_id)
        unresolved = "" if concept is not None else f"{NOT_PINNED} ({minimal.concept_id})"

    return ChecklistItem(
        domain=minimal.domain,
        domain_label=minimal.domain_label,
        item=minimal.item,
        rationale=minimal.rationale,
        concept=concept,
        unresolved=unresolved,
    )


def build_model(schema: CdmSchema, spec: ProjectSpec, vocabulary: Vocabulary) -> ExplorerModel:
    """Assemble the explorer's view model from the three specification layers.

    Parameters
    ----------
    schema : CdmSchema
        The structural layer, from ``load_structural``.
    spec : ProjectSpec
        The project layer, from ``load_spec``.
    vocabulary : Vocabulary
        The vocabulary layer, from ``load_vocabulary``.

    Returns
    -------
    ExplorerModel
        Everything the page shows, and nothing about how it looks.
    """
    concepts = _concept_views(spec, vocabulary)
    permitted = {
        binding: tuple(concepts[c.concept_id] for c in bound)
        for binding, bound in vocabulary.bindings().items()
    }
    checklist = _checklist(spec, concepts)

    return ExplorerModel(
        cdm_version=schema.cdm_version,
        checklist=checklist,
        tables=_table_views(schema, spec, permitted, _items_by_table(checklist)),
        edges=_edges(schema, spec),
    )
