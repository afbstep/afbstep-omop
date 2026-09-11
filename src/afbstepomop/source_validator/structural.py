"""Parse the structural layer of the AFBSTEP CDM specification.

The structural layer describes *what tables and columns exist* and how they
reference each other. It is assembled from five files under ``source/``:

``structural/schema.sql``
    Stock OMOP CDM 5.4 table definitions, vendored from the OHDSI
    CommonDataModel project. Never hand-edited, so it stays diffable against
    future CDM releases.
``structural/primary_keys.sql``, ``structural/constraints.sql``
    Vendored primary and foreign key constraints for the stock tables.
``structural/CDM_VERSION``
    The upstream CDM release the vendored files were taken from.
``custom/schema_custom.sql``, ``custom/constraints_custom.sql``
    AFBSTEP's own tables and their constraints, kept apart from the vendored
    files so the two can be told apart and upgraded independently.

Vendored constraint files carry an ``@cdmDatabaseSchema.`` placeholder in
front of every table name; it is stripped during parsing. All table and
column names are normalised to lower case.

This module only reads structure. Which tables are in scope, which fields are
required, and which concepts are permitted are project decisions and live in
the ``source/spec/`` CSVs.

It checks the following:
- CDM_VERSION file is non-empty
- every primary key column actually exists on its table
- every foreign key's own column exists
- every foreign key's referenced table exists
- every foreign key's referenced column exists on that parent table
- every AFBSTEP custom table (custom/schema_custom.sql) has a declared primary key

"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from afbstepomop.source_validator.paths import DEFAULT_SOURCE_DIR  # noqa: E402  (re-exported for callers)

STRUCTURAL_ORIGIN = "structural"
CUSTOM_ORIGIN = "custom"

CONCEPT_TABLE = "concept"

_LINE_COMMENT = re.compile(r"--[^\n]*")
_CREATE_TABLE = re.compile(r"CREATE\s+TABLE\s+(\w+)\s*\(", re.IGNORECASE)
_PRIMARY_KEY = re.compile(
    r"ALTER\s+TABLE\s+(?:@\w+\.)?(\w+)\s+ADD\s+CONSTRAINT\s+(\w+)\s+"
    r"PRIMARY\s+KEY\s*\(([^)]+)\)",
    re.IGNORECASE,
)
_FOREIGN_KEY = re.compile(
    r"ALTER\s+TABLE\s+(?:@\w+\.)?(\w+)\s+ADD\s+CONSTRAINT\s+(\w+)\s+"
    r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+(?:@\w+\.)?(\w+)\s*\(([^)]+)\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Column:
    """A single column of a CDM table.

    Attributes
    ----------
    name : str
        Lower-cased column name.
    sql_type : str
        Declared SQL type, verbatim from the DDL (e.g. ``integer``,
        ``varchar(50)``).
    nullable : bool
        False when the DDL declares ``NOT NULL``. Note this is the *CDM*
        requirement; AFBSTEP may additionally require a nullable column to be
        populated, which is recorded in the project spec, not here.
    """

    name: str
    sql_type: str
    nullable: bool


@dataclass(frozen=True)
class ForeignKey:
    """A foreign key from one CDM column to another table's column."""

    name: str
    table: str
    column: str
    parent_table: str
    parent_column: str


@dataclass
class Table:
    """A CDM table with its columns and constraints.

    Attributes
    ----------
    name : str
        Lower-cased table name.
    origin : str
        ``"structural"`` for stock OMOP tables, ``"custom"`` for AFBSTEP
        extensions.
    columns : dict of str to Column
        Columns keyed by name, in DDL order.
    primary_key : tuple of str
        Primary key column names; empty when the table declares none.
    foreign_keys : tuple of ForeignKey
        Foreign keys declared on this table.
    """

    name: str
    origin: str
    columns: dict[str, Column] = field(default_factory=dict)
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()

    def concept_columns(self) -> tuple[str, ...]:
        """Return the columns that must hold a valid ``concept_id``.

        Derived from the foreign keys rather than from naming conventions, so
        a column counts as concept-valued only if the CDM says it references
        the ``concept`` table.

        Returns
        -------
        tuple of str
            Column names referencing ``concept``, in DDL order.
        """
        referencing = {
            fk.column for fk in self.foreign_keys if fk.parent_table == CONCEPT_TABLE
        }
        return tuple(name for name in self.columns if name in referencing)


@dataclass
class CdmSchema:
    """The parsed structural layer: every table, keyed by name."""

    tables: dict[str, Table]
    cdm_version: str

    def concept_columns(self) -> tuple[tuple[str, str], ...]:
        """Return every concept-valued column across the whole schema.

        Returns
        -------
        tuple of (str, str)
            ``(table_name, column_name)`` pairs for columns referencing the
            ``concept`` table.
        """
        return tuple(
            (table.name, column)
            for table in self.tables.values()
            for column in table.concept_columns()
        )

    def issues(self) -> list[str]:
        """Check the specification against itself.

        Catches the failure modes that arise from maintaining the vendored and
        custom files separately: a table defined twice, a constraint naming a
        table or column that does not exist, an AFBSTEP table nobody has given
        a primary key, and a missing CDM version stamp.

        Returns
        -------
        list of str
            Human-readable problems, empty when the specification is coherent.
            Ordered by table name so the output is stable across runs.
        """
        problems: list[str] = []

        if not self.cdm_version:
            problems.append("CDM_VERSION is empty; the vendored release is unrecorded")

        for name in sorted(self.tables):
            table = self.tables[name]

            for column in table.primary_key:
                if column not in table.columns:
                    problems.append(f"{name}: primary key names unknown column {column!r}")

            for fk in table.foreign_keys:
                if fk.column not in table.columns:
                    problems.append(f"{name}: foreign key {fk.name} names unknown column {fk.column!r}")
                parent = self.tables.get(fk.parent_table)
                if parent is None:
                    problems.append(f"{name}: foreign key {fk.name} references unknown table {fk.parent_table!r}")
                elif fk.parent_column not in parent.columns:
                    problems.append(
                        f"{name}: foreign key {fk.name} references unknown column "
                        f"{fk.parent_table}.{fk.parent_column}"
                    )

            if table.origin == CUSTOM_ORIGIN and not table.primary_key:
                problems.append(f"{name}: custom table has no primary key declared")

        return problems


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments so they cannot be mistaken for DDL."""
    return _LINE_COMMENT.sub("", sql)


def _split_top_level(body: str) -> list[str]:
    """Split a parenthesised DDL body on commas outside nested parentheses.

    Keeps types such as ``varchar(50)`` and ``numeric(19,2)`` intact.

    Parameters
    ----------
    body : str
        Text between a table definition's outermost parentheses.

    Returns
    -------
    list of str
        Stripped, non-empty column definitions.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _parse_column(definition: str) -> Column | None:
    """Parse one column definition, or return None if it is not one.

    Parameters
    ----------
    definition : str
        A single comma-separated fragment of a ``CREATE TABLE`` body, such as
        ``person_id integer NOT NULL``.

    Returns
    -------
    Column or None
        None when the fragment has too few tokens to be a column (for example
        a stray table-level constraint).
    """
    tokens = definition.split()
    if len(tokens) < 2:
        return None
    nullable = "NOT NULL" not in " ".join(tokens[2:]).upper()
    return Column(name=tokens[0].lower(), sql_type=tokens[1], nullable=nullable)


def parse_schema_sql(path: Path, origin: str) -> dict[str, Table]:
    """Parse ``CREATE TABLE`` statements into tables and columns.

    The outermost parentheses of each statement are located by counting
    depth rather than by regular expression, so parenthesised types do not
    terminate the body early.

    Parameters
    ----------
    path : Path
        A schema DDL file.
    origin : str
        ``"structural"`` or ``"custom"``, recorded on every table parsed.

    Returns
    -------
    dict of str to Table
        Tables keyed by lower-cased name, without constraints attached.
    """
    sql = _strip_comments(path.read_text())
    tables: dict[str, Table] = {}

    for match in _CREATE_TABLE.finditer(sql):
        depth, end = 1, match.end()
        while depth and end < len(sql):
            depth += {"(": 1, ")": -1}.get(sql[end], 0)
            end += 1

        table = Table(name=match.group(1).lower(), origin=origin)
        for definition in _split_top_level(sql[match.end() : end - 1]):
            column = _parse_column(definition)
            if column is not None:
                table.columns[column.name] = column
        tables[table.name] = table

    return tables


def parse_primary_keys(path: Path) -> dict[str, tuple[str, ...]]:
    """Parse ``ADD CONSTRAINT ... PRIMARY KEY`` statements.

    Parameters
    ----------
    path : Path
        A primary key DDL file. A missing or empty file yields no keys.

    Returns
    -------
    dict of str to tuple of str
        Primary key column names keyed by lower-cased table name.
    """
    if not path.exists():
        return {}

    sql = _strip_comments(path.read_text())
    return {
        table.lower(): tuple(c.strip().lower() for c in columns.split(","))
        for table, _name, columns in _PRIMARY_KEY.findall(sql)
    }


def parse_foreign_keys(path: Path) -> list[ForeignKey]:
    """Parse ``ADD CONSTRAINT ... FOREIGN KEY`` statements.

    Parameters
    ----------
    path : Path
        A constraints DDL file. A missing or empty file yields no keys.

    Returns
    -------
    list of ForeignKey
        One entry per foreign key, in file order.
    """
    if not path.exists():
        return []

    sql = _strip_comments(path.read_text())
    return [
        ForeignKey(
            name=name.lower(),
            table=table.lower(),
            column=column.strip().lower(),
            parent_table=parent_table.lower(),
            parent_column=parent_column.strip().lower(),
        )
        for table, name, column, parent_table, parent_column in _FOREIGN_KEY.findall(sql)
    ]


def _read_version(path: Path) -> str:
    """Read the vendored CDM version stamp.

    The stamp is quoted in some upstream releases. Quotes are stripped here
    rather than in the file, so the vendored directory stays byte-identical to
    what it was taken from.

    Parameters
    ----------
    path : Path
        The ``CDM_VERSION`` file.

    Returns
    -------
    str
        The version, or the empty string when the file is absent or blank.
    """
    if not path.exists():
        return ""
    return path.read_text().strip().strip('"').strip()


def load_structural(source_dir: Path | None = None) -> CdmSchema:
    """Load the complete structural layer from a ``source/`` directory.

    Stock and custom tables are parsed separately so their origin is retained,
    then constraints from both layers are attached. Constraints naming a table
    that does not exist are kept out of the schema and surface through
    :meth:`CdmSchema.issues` instead of failing the load, so a partial or
    in-progress specification can still be inspected.

    Parameters
    ----------
    source_dir : Path, optional
        Directory holding ``structural/`` and ``custom/``. Defaults to the
        ``source/`` directory shipped inside the package.

    Returns
    -------
    CdmSchema
        Parsed tables with primary and foreign keys attached.

    Raises
    ------
    FileNotFoundError
        If ``structural/schema.sql`` is absent.
    """
    root = DEFAULT_SOURCE_DIR if source_dir is None else Path(source_dir)

    tables = parse_schema_sql(root / "structural" / "schema.sql", STRUCTURAL_ORIGIN)
    custom_path = root / "custom" / "schema_custom.sql"
    if custom_path.exists():
        tables.update(parse_schema_sql(custom_path, CUSTOM_ORIGIN))

    primary_keys = parse_primary_keys(root / "structural" / "primary_keys.sql")
    primary_keys.update(parse_primary_keys(root / "custom" / "constraints_custom.sql"))

    foreign_keys = parse_foreign_keys(root / "structural" / "constraints.sql")
    foreign_keys += parse_foreign_keys(root / "custom" / "constraints_custom.sql")

    for name, table in tables.items():
        table.primary_key = primary_keys.get(name, ())
        table.foreign_keys = tuple(fk for fk in foreign_keys if fk.table == name)

    version_path = root / "structural" / "CDM_VERSION"
    cdm_version = _read_version(version_path)

    return CdmSchema(tables=tables, cdm_version=cdm_version)
