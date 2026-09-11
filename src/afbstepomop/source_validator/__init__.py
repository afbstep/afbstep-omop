"""Read and check the AFBSTEP specification files under ``source/``.

The specification is data; this sub-package is its interpreter. It reads the
three layers and checks each one against itself and against the others, so that
an inconsistency in the spec surfaces to a maintainer rather than to a partner
site trying to follow it.

======================  ===================================  =================
Layer                   Reads                                Loader
======================  ===================================  =================
structural              the five DDL files                   ``load_structural``
vocabulary              the two vocabulary CSVs              ``load_vocabulary``
project                 ``tables``, ``minimal_dataset``,     ``load_spec``
                        ``plausibility``
======================  ===================================  =================

Every loader has the same shape, so they can be used interchangeably::

    layer = load_structural()
    layer.issues()      # inconsistencies needing a human decision
    describe(layer)     # what the underlying source files actually say

``issues()`` and ``defects`` answer different questions and are deliberately
kept apart. A **defect** is file hygiene the loader repaired on read — stray
whitespace, an undocumented column — which changes nothing about what the spec
means but signals a file drifting from its documented format. An **issue** is an
inconsistency the loader cannot resolve, because resolving it is a project
decision rather than a parsing one.

Nothing here validates partner data; that is :mod:`afbstepomop.output_validator.validate`.
"""

from afbstepomop.source_validator.csvspec import read_spec_csv
from afbstepomop.source_validator.display import describe, describe_minimal
from afbstepomop.source_validator.paths import DEFAULT_SOURCE_DIR
from afbstepomop.source_validator.spec import FieldRule, ProjectSpec, TableRule, ValueRule, load_spec
from afbstepomop.source_validator.structural import CdmSchema, Column, ForeignKey, Table, load_structural
from afbstepomop.source_validator.vocabulary import Concept, Vocabulary, load_vocabulary

__all__ = [
    "CdmSchema",
    "Column",
    "Concept",
    "DEFAULT_SOURCE_DIR",
    "FieldRule",
    "ForeignKey",
    "ProjectSpec",
    "Table",
    "TableRule",
    "ValueRule",
    "Vocabulary",
    "describe",
    "describe_minimal",
    "load_spec",
    "load_structural",
    "load_vocabulary",
    "read_spec_csv",
]
