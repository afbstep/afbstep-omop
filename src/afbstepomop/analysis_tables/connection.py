import duckdb
from importlib.resources import files

class VocabularyMissingError(Exception):
    """Raised when the concept table exists but has no rows."""


def open_connection(con: str | duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Open (or reuse) a DuckDB connection and confirm the vocabulary is loaded."""
    if isinstance(con, str):
        con = duckdb.connect(con)
    elif not isinstance(con, duckdb.DuckDBPyConnection):
        raise TypeError(
            f"con must be a file path (str) or an open DuckDB connection, got {type(con).__name__}"
        )

    (count,) = con.execute("SELECT COUNT(*) FROM concept").fetchone()
    if count == 0:
        raise VocabularyMissingError(
            "The 'concept' table has no rows. Load the AF-B-STEP OMOP CDM vocabulary first."
        )
    return con

def load_sql(name: str) -> str:
    return (files("afbstepomop.analysis_tables") / "sql" / name).read_text()