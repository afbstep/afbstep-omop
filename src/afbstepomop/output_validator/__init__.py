"""Validate a partner's mapped dataset against the AFBSTEP specification.

Where :mod:`afbstepomop.source_validator` checks that the *specification* is
coherent, this sub-package checks that a *dataset* follows it. The two are
separate flows with separate audiences: a maintainer fixes the spec, a partner
fixes their export, and neither should be shown the other's problems.

A dataset arrives as one CSV per CDM table and is checked in five layers, each
answering a different question:

conformance
    Are the tables and fields there at all?
completeness
    Are the fields populated as ``minimal_dataset.csv`` requires?
referential
    Do the foreign keys resolve within the dataset?
terminology
    Are the concept fields carrying concepts the vocabulary recognises?
plausibility
    Do the values fall in the range, and carry the unit, their concept expects?

How much the terminology layer can say depends on which vocabulary the run can
reach, which differs by deployment rather than by code path::

    validate(dataset, schema, spec, vocabulary)                  # pinned concepts only
    validate(dataset, schema, spec, vocabulary, source)          # full release attached

Both go through the same checks, so a dataset cannot pass locally by taking a
different route than the server takes. What differs is recorded in the report:
the verdict names the vocabulary it was reached with, and lists what the run
could not check.
"""

from afbstepomop.output_validator.athena import AthenaVocabulary, build_index, read_release
from afbstepomop.output_validator.resolver import (
    ChainedVocabulary,
    ConceptRecord,
    PinnedVocabulary,
    VocabularySource,
    DomainExpectations,
    domain_expectations,
)
from afbstepomop.output_validator.validate import Finding, Report, read_dataset, validate

__all__ = [
    "AthenaVocabulary",
    "ChainedVocabulary",
    "ConceptRecord",
    "Finding",
    "PinnedVocabulary",
    "Report",
    "VocabularySource",
    "build_index",
    "DomainExpectations",
    "domain_expectations",
    "read_dataset",
    "read_release",
    "validate",
]
