"""
Answer questions about a concept, from whichever vocabulary is available.

Validation needs to ask four things about a `concept_id` a partner has used:
- does it exist
- is it standard
- is its domain right for the field it sits in
- was it valid on the record date. 
How much of that can be answered depends entirely on which vocabulary 
the run has access to, and that varies by deployment:

pinned
    The ~150 concepts in `source/spec/` (custom + standard). 
    Always present, needs no download, and is **not exhaustive**, 
    i.e a concept missing from it may be perfectly valid and simply not pinned.
Athena
    A downloaded OHDSI vocabulary release. Optional, large, offline, and
    **exhaustive**: a concept missing from it does not exist.

The distinction between those two is the whole point of this module. Absence
from a non-exhaustive source carries no information, so it can only ever be a
warning; absence from an exhaustive one is a typo, and can be an error. A
:class:`VocabularySource` therefore reports whether it is exhaustive, and the
validator decides how loudly to speak based on that rather than on which
implementation it happens to be holding.

Both deployments of this package — the server, which validates uploads in full,
and the partner's local copy, which may or may not have a vocabulary — run the
same checks through this one seam, so a partner cannot pass locally by taking a
different code path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from afbstepomop.source_validator.structural import CUSTOM_ORIGIN
from afbstepomop.source_validator.vocabulary import Vocabulary

STANDARD_CONCEPT_FLAG = "S"

#: Domain names the vocabulary abbreviates inside a compound domain. The
#: upstream vocabulary is not consistent about this — ``Measurement/Obs`` spells
#: one part out and abbreviates the other — so both forms must resolve.
DOMAIN_ABBREVIATIONS = {
    "Meas": "Measurement",
    "Obs": "Observation",
    "Spec": "Specimen",
}

#: The domain a concept field is expected to carry, by field name. Derived from
#: the OMOP CDM's own conventions rather than from an AFBSTEP decision, which is
#: why it lives in code and not in ``source/spec/``.
#:
#: Fields deliberately absent from this map are not domain-checked:
#: ``value_as_concept_id`` holds answer concepts from many domains (AFBSTEP's own
#: registry binds Condition concepts there), and ``*_source_concept_id`` fields
#: hold non-standard source codes by design.
EXPECTED_DOMAINS = {
    "condition_concept_id": "Condition",
    "condition_status_concept_id": "Condition Status",
    "device_concept_id": "Device",
    "drug_concept_id": "Drug",
    "episode_concept_id": "Episode",
    "ethnicity_concept_id": "Ethnicity",
    "gender_concept_id": "Gender",
    "measurement_concept_id": "Measurement",
    "observation_concept_id": "Observation",
    "procedure_concept_id": "Procedure",
    "race_concept_id": "Race",
    "route_concept_id": "Route",
    "specimen_concept_id": "Specimen",
    "unit_concept_id": "Unit",
    "visit_concept_id": "Visit",
}

#: Suffix marking a field that records how a row was obtained. Every such field
#: expects the same domain.
#:
#: This is an OMOP naming convention and holds only on OMOP's own tables. On an
#: AFBSTEP extension table the same suffix means something else entirely --
#: ``study.study_type_concept_id`` names the kind of study, not the provenance
#: of the row -- so the rule is applied by table origin, never by name alone.
#: See :func:`domain_expectations`.
TYPE_FIELD_SUFFIX = "_type_concept_id"
TYPE_CONCEPT_DOMAIN = "Type Concept"

#: Fields holding an answer concept rather than naming a thing. Answers are
#: drawn from whatever domain the question needs, so they are never
#: domain-checked: ``study_attribute.value_concept_id`` carries Methodological
#: Concept values for the provision level and standard Geography concepts for
#: the country, by design.
ANSWER_FIELDS = frozenset({"value_as_concept_id", "value_concept_id"})


@dataclass(frozen=True)
class ConceptRecord:
    """What a vocabulary knows about one concept.

    A deliberately narrow view: only the attributes validation needs, so that
    an Athena-backed source does not have to carry synonyms, relationships or
    ancestry it will never be asked for.

    Attributes
    ----------
    concept_id : int
        The concept's OHDSI identifier.
    concept_name : str
        Human-readable name, used to make findings legible rather than to
        decide anything.
    domain_id : str
        The concept's domain, possibly compound (``"Condition/Meas"``).
    standard_concept : str
        ``"S"`` for standard concepts, ``"C"`` for classification concepts,
        empty for non-standard ones.
    valid_start_date, valid_end_date : datetime.date or None
        Validity window; None when the source does not record it.
    invalid_reason : str
        ``"D"`` deprecated, ``"U"`` upgraded, empty when the concept is
        current. Not recorded by the pinned source, which has no field for it.
    """

    concept_id: int
    concept_name: str
    domain_id: str
    standard_concept: str
    valid_start_date: date | None = None
    valid_end_date: date | None = None
    invalid_reason: str = ""

    @property
    def is_standard(self) -> bool:
        """Whether the concept may be used in a ``*_concept_id`` field."""
        return self.standard_concept == STANDARD_CONCEPT_FLAG

    @property
    def is_current(self) -> bool:
        """Whether the concept has not been deprecated or upgraded upstream."""
        return not self.invalid_reason

    def covers(self, day: date) -> bool:
        """Whether the concept was valid on a given date.

        Parameters
        ----------
        day : datetime.date
            The date of the record using this concept.

        Returns
        -------
        bool
            True when the validity window includes ``day``, and also when the
            source records no window at all, since an unknown window is not
            evidence of a problem.
        """
        if self.valid_start_date is not None and day < self.valid_start_date:
            return False
        if self.valid_end_date is not None and day > self.valid_end_date:
            return False
        return True

    def in_domain(self, expected: str) -> bool:
        """Whether the concept's domain satisfies an expected domain.

        Compound domains such as ``Condition/Meas`` satisfy either part, so a
        concept the vocabulary considers both a condition and a measurement is
        accepted in a condition field. Abbreviated parts are expanded first,
        because the upstream vocabulary abbreviates inconsistently.

        Single domains containing a space, such as ``Meas Value``, are *not*
        compounds and are compared whole — a Meas Value concept is an answer
        concept and does not belong in ``measurement_concept_id``.

        Parameters
        ----------
        expected : str
            The domain the field expects, for example ``"Condition"``.

        Returns
        -------
        bool
        """
        parts = [DOMAIN_ABBREVIATIONS.get(part, part) for part in self.domain_id.split("/")]
        return expected in parts


@dataclass(frozen=True)
class DomainExpectations:
    """What each concept field accepts, per table origin.

    Attributes
    ----------
    extension_tables : frozenset of str
        AFBSTEP extension tables, where OMOP's naming conventions do not apply.
    pinned : dict of (str, str) to frozenset of str
        Domains the specification binds to a field on one of those tables.
    """

    extension_tables: frozenset[str]
    pinned: dict[tuple[str, str], frozenset[str]]

    def for_field(self, table: str, field: str) -> frozenset[str] | None:
        """Return the domains ``table.field`` accepts, or None if unconstrained."""
        if field in ANSWER_FIELDS:
            return None

        if table in self.extension_tables:
            # The specification answers for its own tables. Where it pins
            # nothing, a name with a genuine OMOP meaning still counts, but the
            # _type_concept_id suffix -- an OMOP convention that does not hold
            # here -- never does.
            pinned = self.pinned.get((table, field))
            if pinned is not None:
                return pinned
            named = EXPECTED_DOMAINS.get(field)
            return frozenset({named}) if named else None

        if field.endswith(TYPE_FIELD_SUFFIX):
            return frozenset({TYPE_CONCEPT_DOMAIN})
        named = EXPECTED_DOMAINS.get(field)
        return frozenset({named}) if named else None


def domain_expectations(schema, vocabulary) -> DomainExpectations:
    """The domains each AFBSTEP extension field accepts, taken from the spec.

    OMOP's naming conventions describe OMOP's tables and stop there. AFBSTEP's
    own tables reuse the ``_type_concept_id`` suffix for a different purpose, so
    inferring ``Type Concept`` from the name misreads every one of them. On
    those tables the specification is the authority instead: the domains it
    pins to a field are the domains that field accepts.

    This is a reading of the spec, not a second statement of it. Nothing new is
    recorded anywhere -- ``cdm_table``, ``cdm_variable`` and ``domain_id``
    already say, per concept, what belongs where.

    Parameters
    ----------
    schema : CdmSchema
        Parsed structural layer, used only to tell an AFBSTEP extension table
        (``origin == "custom"``) from a stock OMOP one.
    vocabulary : Vocabulary
        Parsed vocabulary layer, whose bindings supply the expectations.

    Returns
    -------
    DomainExpectations
        Which tables are extensions, and what the spec pins to their fields.
    """
    extension_tables = frozenset(
        name for name, table in schema.tables.items() if table.origin == CUSTOM_ORIGIN
    )
    pinned: dict[tuple[str, str], set[str]] = {}
    for concept in vocabulary.concepts:
        table, column = concept.cdm_table, concept.cdm_variable
        if not table or not column or table not in extension_tables:
            continue
        if column in ANSWER_FIELDS:
            continue
        pinned.setdefault((table, column), set()).add(concept.domain_id)
    return DomainExpectations(
        extension_tables=extension_tables,
        pinned={key: frozenset(domains) for key, domains in pinned.items()},
    )


@runtime_checkable
class VocabularySource(Protocol):
    """A vocabulary that can be asked about a concept.

    Implementations differ in how much they know, not in what they are asked.
    """

    @property
    def label(self) -> str:
        """Short description of this source, shown in the validation verdict.

        The verdict has to say which vocabulary produced it: ``PASSED`` against
        the pinned concepts is a weaker claim than ``PASSED`` against a full
        vocabulary release, and a reader cannot tell them apart otherwise.
        """
        ...

    @property
    def is_exhaustive(self) -> bool:
        """Whether absence from this source means the concept does not exist.

        False for the pinned specification, which holds only the concepts
        AFBSTEP committed to. True for a full vocabulary release.
        """
        ...

    def lookup(self, concept_id: int) -> ConceptRecord | None:
        """Return what is known about a concept, or None if it is not held.

        Parameters
        ----------
        concept_id : int
            The concept to look up.

        Returns
        -------
        ConceptRecord or None
            None means "not in this source", which is only evidence of an
            error when :attr:`is_exhaustive` is True.
        """
        ...


class PinnedVocabulary:
    """The concepts pinned in ``source/spec/``, as a vocabulary source.

    Always available, needs no download, and answers for the 156 concepts
    AFBSTEP has committed to. It is **not** exhaustive: a partner may
    legitimately use standard concepts that are not pinned, so absence from it
    says nothing about whether a concept is real.

    Parameters
    ----------
    vocabulary : Vocabulary
        The parsed vocabulary layer.
    origins : tuple of str, optional
        Restrict to concepts from one source file, ``"standard"`` or
        ``"custom"``. Used to hold only the AFBSTEP-minted concepts when
        chaining behind a full vocabulary release, so that the release remains
        the authority on everything it knows about.
    """

    def __init__(self, vocabulary: Vocabulary, origins: tuple[str, ...] | None = None) -> None:
        selected = [
            concept
            for concept in vocabulary.concepts
            if origins is None or concept.origin in origins
        ]
        self._origins = origins
        self._records = {
            concept.concept_id: ConceptRecord(
                concept_id=concept.concept_id,
                concept_name=concept.concept_name,
                domain_id=concept.domain_id,
                standard_concept=concept.standard_concept,
                valid_start_date=concept.valid_start_date,
                valid_end_date=concept.valid_end_date,
            )
            for concept in selected
        }

    @property
    def label(self) -> str:
        """Describe the source for the verdict line."""
        which = "pinned specification" if self._origins is None else f"AFBSTEP {'/'.join(self._origins)} concepts"
        return f"{which} ({len(self._records)} concepts)"

    @property
    def is_exhaustive(self) -> bool:
        """Always False: the pinned set is explicitly not a whitelist."""
        return False

    def lookup(self, concept_id: int) -> ConceptRecord | None:
        """Return the pinned record for a concept, or None if it is not pinned."""
        return self._records.get(concept_id)


class ChainedVocabulary:
    """Consult a local extension first, then a full vocabulary release.

    AFBSTEP mints its own concepts in the ``2000000000+`` range reserved for
    local vocabularies. Those concepts do not exist upstream and never will, so
    a downloaded release used on its own reports every one of them as
    nonexistent. Chaining is what makes an exhaustive source usable: the local
    extension answers for concepts AFBSTEP created, and the release answers for
    everything else.

    Order matters. The release is consulted *second* but is authoritative for
    everything it holds, so a pinned standard concept that was deprecated
    upstream is still reported as deprecated rather than being masked by the
    project's own copy of it. That is why the local part should hold only
    custom concepts.

    Parameters
    ----------
    local : VocabularySource
        Concepts that exist only within the project.
    release : VocabularySource
        A full vocabulary release.
    """

    def __init__(self, local: VocabularySource, release: VocabularySource) -> None:
        self._local = local
        self._release = release

    @property
    def label(self) -> str:
        """Describe both members, since both shaped the verdict."""
        return f"{self._release.label} + {self._local.label}"

    @property
    def is_exhaustive(self) -> bool:
        """Whether the pair together define what exists.

        True when the release is exhaustive: between a complete release and the
        project's own extension, a concept in neither exists nowhere.
        """
        return self._release.is_exhaustive

    def lookup(self, concept_id: int) -> ConceptRecord | None:
        """Return the local record if there is one, otherwise the release's."""
        return self._local.lookup(concept_id) or self._release.lookup(concept_id)
