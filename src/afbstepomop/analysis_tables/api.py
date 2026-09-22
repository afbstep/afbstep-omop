import pandas as pd

from .connection import open_connection
from .options import TableOptions
from .registry import get_builder


def cdm_to_table(
    con,
    table_type: str = "baseline",
    *,
    studies: list[int] | None = None,
    variables: dict | None = None,
    baseline_window: tuple[int, int] = (-365, 0),
    missingness: str = "reason_columns",
    sentinels: str = "flag",
    path: str | None = None,
) -> pd.DataFrame:
    """Build an analysis table from a populated AFBSTEP OMOP CDM."""
    opts = TableOptions(
        studies=studies,
        variables=variables,
        baseline_window=baseline_window,
        missingness=missingness,
        sentinels=sentinels,
    )
    connection = open_connection(con)
    builder = get_builder(table_type)
    table = builder(connection, opts)

    if path is not None:
        table.to_parquet(path, index=False)
    return table