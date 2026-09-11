"""
Resolve concepts against a downloaded OHDSI vocabulary release.
website: https://athena.ohdsi.org/vocabulary/list

A vocabulary release is a directory of very large tab-separated files;
`CONCEPT.csv` alone is close to a gigabyte and holds millions of rows. 
A validation run needs to ask about a few dozen concept ids, so neither obvious
approach works: re-scanning the file each run costs a full pass to answer a
handful of questions, and loading it into a dictionary costs several gigabytes
of memory.

This module converts the file once into a SQLite index holding only the columns
validation asks about, after which every lookup is a single indexed query. The
index is read-only afterwards, so it can be copied between machines or shipped
to the server rather than rebuilt.

Unlike the pinned specification, a release is **exhaustive**: a concept it does
not hold does not exist, which is what lets the validator report a mistyped
concept id as an error rather than a warning.

The release files have four properties worth knowing, all of which this module
handles and none of which are obvious from the `.csv`` extension: 
- they are tab-separated
- they are unquoted while concept names contain quote characters
- some fields exceed Python's default CSV field limit
- dates are written `YYYYMMDD` rather than as ISO dates.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import date
from pathlib import Path

from afbstepomop.output_validator.resolver import ConceptRecord

# Configs related to the OHDSI vocabulary release files
# --------------------------------------------------------------------------------

CONCEPT_FILE = "CONCEPT.csv"
VOCABULARY_FILE = "VOCABULARY.csv"

#: The row of ``VOCABULARY.csv`` carrying the release stamp for the whole bundle.
RELEASE_ROW_ID = "None"
UNKNOWN_RELEASE = "unknown release"

#: Columns kept from ``CONCEPT.csv``, by position in the release file. Everything
#: else is dropped: synonyms, relationships, ancestry and drug strength make up
#: most of the download and no check consults them.
_CONCEPT_ID = 0
_CONCEPT_NAME = 1
_DOMAIN_ID = 2
_VOCABULARY_ID = 3
_STANDARD_CONCEPT = 5
_VALID_START = 7
_VALID_END = 8
_INVALID_REASON = 9
_MINIMUM_FIELDS = 10

_BATCH = 50_000


# Schema for the SQLite index
# --------------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE concept (
    concept_id        INTEGER PRIMARY KEY,
    concept_name      TEXT NOT NULL,
    domain_id         TEXT NOT NULL,
    vocabulary_id     TEXT NOT NULL,
    standard_concept  TEXT NOT NULL,
    valid_start_date  TEXT NOT NULL,
    valid_end_date    TEXT NOT NULL,
    invalid_reason    TEXT NOT NULL
);
CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Actual code starts here
# --------------------------------------------------------------------------------


def _iso(stamp: str) -> str:
    """Convert an ``YYYYMMDD`` stamp to an ISO date string.

    Parameters
    ----------
    stamp : str
        Eight digits as written in the release files.

    Returns
    -------
    str
        ``YYYY-MM-DD``, or the empty string when the stamp is unusable, so one
        malformed row cannot abort a build of ten million.
    """
    if len(stamp) != 8 or not stamp.isdigit():
        return ""
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"


def read_release(vocabulary_dir: Path) -> str:
    """Read the release stamp of a downloaded vocabulary.

    The stamp identifies which vocabulary produced a verdict, and lets a
    mismatch between the server's copy and a partner's be seen rather than
    silently changing what validation means.

    Parameters
    ----------
    vocabulary_dir : Path
        Directory holding the extracted release files.

    Returns
    -------
    str
        For example ``"v5.0 27-FEB-26"``, or a placeholder when the file is
        absent or does not carry the stamp.
    """
    path = vocabulary_dir / VOCABULARY_FILE
    if not path.exists():
        return UNKNOWN_RELEASE

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        next(reader, None)
        for row in reader:
            if len(row) >= 4 and row[0] == RELEASE_ROW_ID and row[3]:
                return row[3]
    return UNKNOWN_RELEASE


def _concept_rows(path: Path):
    """Yield the kept columns of every usable row in ``CONCEPT.csv``.

    Rows too short to carry the columns validation needs are skipped rather
    than raising: a release is a third-party artefact and one damaged line
    should not prevent an index being built from the other ten million.

    Parameters
    ----------
    path : Path
        The ``CONCEPT.csv`` of a release.

    Yields
    ------
    tuple
        Values in the column order of the ``concept`` table.
    """
    csv.field_size_limit(sys.maxsize)

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        next(reader, None)
        for row in reader:
            if len(row) < _MINIMUM_FIELDS:
                continue
            try:
                concept_id = int(row[_CONCEPT_ID])
            except ValueError:
                continue
            yield (
                concept_id,
                row[_CONCEPT_NAME],
                row[_DOMAIN_ID],
                row[_VOCABULARY_ID],
                row[_STANDARD_CONCEPT],
                _iso(row[_VALID_START]),
                _iso(row[_VALID_END]),
                row[_INVALID_REASON],
            )


def build_index(vocabulary_dir: Path, index_path: Path) -> int:
    """Build a SQLite index from a downloaded vocabulary release.

    Reads ``CONCEPT.csv`` once and writes the columns validation needs into a
    database keyed on ``concept_id``. An existing index at ``index_path`` is
    replaced, because a half-written index is worse than none: it would answer
    lookups confidently and wrongly.

    Parameters
    ----------
    vocabulary_dir : Path
        Directory holding the extracted release files.
    index_path : Path
        Where to write the index. Its parent directory is created if needed.

    Returns
    -------
    int
        Number of concepts indexed.

    Raises
    ------
    FileNotFoundError
        If ``CONCEPT.csv`` is not in ``vocabulary_dir``.
    """
    concept_path = vocabulary_dir / CONCEPT_FILE
    if not concept_path.exists():
        raise FileNotFoundError(f"{CONCEPT_FILE} not found in {vocabulary_dir}")

    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.unlink(missing_ok=True)

    release = read_release(vocabulary_dir)
    connection = sqlite3.connect(index_path)
    try:
        # This database is written once and read many times, so durability
        # during the build buys nothing: a crash means rebuilding, not repair.
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.executescript(_SCHEMA)

        indexed = 0
        batch: list[tuple] = []
        for row in _concept_rows(concept_path):
            batch.append(row)
            if len(batch) >= _BATCH:
                connection.executemany("INSERT OR REPLACE INTO concept VALUES (?,?,?,?,?,?,?,?)", batch)
                indexed += len(batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT OR REPLACE INTO concept VALUES (?,?,?,?,?,?,?,?)", batch)
            indexed += len(batch)

        connection.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("release", release),
                ("source", str(concept_path)),
                ("concept_count", str(indexed)),
                ("built_at", date.today().isoformat()),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return indexed


class AthenaVocabulary:
    """A downloaded vocabulary release, as an exhaustive vocabulary source.

    Being exhaustive is the point: a concept this source does not hold does not
    exist, so the validator can report a mistyped concept id as an error rather
    than merely noting that it was not recognised.

    Parameters
    ----------
    index_path : Path
        A SQLite index produced by :func:`build_index`.

    Raises
    ------
    FileNotFoundError
        If the index does not exist. It is not built implicitly, because
        building takes minutes and a caller expecting a lookup should not
        silently get a long job instead.
    """

    def __init__(self, index_path: Path) -> None:
        index_path = Path(index_path)
        if not index_path.exists():
            raise FileNotFoundError(f"no vocabulary index at {index_path}; build it with build_index()")

        self._connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True, check_same_thread=False)
        metadata = dict(self._connection.execute("SELECT key, value FROM metadata"))
        self._release = metadata.get("release", UNKNOWN_RELEASE)
        self._count = int(metadata.get("concept_count", 0))

    @property
    def label(self) -> str:
        """Describe the release for the verdict line."""
        return f"OHDSI vocabulary {self._release} ({self._count:,} concepts)"

    @property
    def is_exhaustive(self) -> bool:
        """Always True: a full release defines what exists."""
        return True

    @property
    def release(self) -> str:
        """The release stamp, for comparing one deployment against another."""
        return self._release

    def lookup(self, concept_id: int) -> ConceptRecord | None:
        """Return what the release knows about a concept, or None if absent.

        Parameters
        ----------
        concept_id : int
            The concept to look up.

        Returns
        -------
        ConceptRecord or None
            None means the concept does not exist in this release.
        """
        row = self._connection.execute(
            "SELECT concept_id, concept_name, domain_id, standard_concept, "
            "valid_start_date, valid_end_date, invalid_reason FROM concept WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
        if row is None:
            return None

        return ConceptRecord(
            concept_id=row[0],
            concept_name=row[1],
            domain_id=row[2],
            standard_concept=row[3],
            valid_start_date=date.fromisoformat(row[4]) if row[4] else None,
            valid_end_date=date.fromisoformat(row[5]) if row[5] else None,
            invalid_reason=row[6],
        )

    def close(self) -> None:
        """Close the underlying database connection."""
        self._connection.close()
