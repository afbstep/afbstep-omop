from .builders.baseline import build_baseline
from .builders.availability import build_availability
from .builders.discharge import build_discharge


TABLE_BUILDERS = {
    "baseline": build_baseline,
    "availability": build_availability,
    "discharge": build_discharge,
}


def get_builder(table_type: str):
    try:
        return TABLE_BUILDERS[table_type]
    except KeyError:
        raise ValueError(
            f"unknown table_type {table_type!r}; available: {sorted(TABLE_BUILDERS)}"
        ) from None