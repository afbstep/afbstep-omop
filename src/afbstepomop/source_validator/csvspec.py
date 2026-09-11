"""Read a ``source/spec/`` CSV under the conventions the README documents.

Every spec file is authored by hand, and most of them start life in a
spreadsheet. That round trip is lossy in predictable ways: it introduces
surrounding whitespace and it leaves working columns behind. Both are repaired
here, once, so that the meaning of the specification cannot depend on how a
file was last saved.

The split between the two ways a file can be wrong is deliberate:

*malformed*
    A documented column is missing from the header. The file cannot be
    interpreted at all, so reading it raises.
*defective*
    Whitespace to strip, or a column outside the documented set. The file is
    interpretable; the defect is repaired and reported so it can be cleaned
    upstream instead of accumulating.
"""

from __future__ import annotations

import csv
from pathlib import Path


def read_spec_csv(path: Path, columns: tuple[str, ...]) -> tuple[list[dict[str, str]], list[str]]:
    """Read a spec CSV, normalising it to exactly the documented columns.

    Parameters
    ----------
    path : Path
        The CSV to read.
    columns : tuple of str
        The columns this file is documented to carry. Columns outside the set
        are dropped; a missing one raises, because the file no longer matches
        the format the loaders read.

    Returns
    -------
    list of dict
        Rows holding exactly ``columns``, with every value stripped.
    list of str
        One message per kind of defect repaired, empty when the file is clean.

    Raises
    ------
    ValueError
        If the header is missing a documented column.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in columns if column not in fieldnames]
        if missing:
            raise ValueError(f"{path.name}: missing documented column(s) {', '.join(missing)}")
        rows = list(reader)

    defects: list[str] = []
    stripped: set[str] = set()
    unknown = sorted(name for name in fieldnames if name not in columns)

    clean: list[dict[str, str]] = []
    for row in rows:
        for key, value in row.items():
            if isinstance(value, str) and value != value.strip():
                stripped.add(key)
        clean.append({column: (row.get(column) or "").strip() for column in columns})

    if stripped:
        defects.append(f"{path.name}: stripped surrounding whitespace in {', '.join(sorted(stripped))}")
    if unknown:
        defects.append(f"{path.name}: ignored undocumented column(s) {', '.join(unknown)}")

    return clean, defects
