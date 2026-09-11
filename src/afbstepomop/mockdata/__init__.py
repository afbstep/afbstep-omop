"""Generate a mock AFBSTEP dataset that conforms to the specification.

The generator exists so that the specification can be exercised end to end
without touching real patient data: it produces a dataset a partner site
*could* have handed over, which the validator should then pass.

It is driven by the specification itself — the parsed schema decides which
columns exist, ``tables.csv`` decides which tables to emit, ``minimal_dataset``
decides how completely to fill them, the vocabulary decides which concepts may
appear in a concept column, and ``plausibility.csv`` decides what a numeric
value may be. That makes the generator a test of the spec as much as of the
validator: a spec too thin to describe a dataset cannot generate one either.

What the specification cannot yet express lives in :mod:`.config` — chiefly
which concept plays which role in the AF-burden architecture.

Output is one CSV per table, carrying every column the CDM declares in DDL
order, because that is what a partner export looks like. Values are drawn from
a seeded :class:`random.Random`, so a given seed always produces the same
dataset.

The clinical shape of the data follows the AFBSTEP mock generator in the TRUST
repository, which encodes decisions worth keeping: ethnicity follows from race
rather than being drawn independently, observation periods sit inside the study
window, and clinical events sit inside a person's observation period.
"""

from afbstepomop.mockdata.afburden import (
    generate_device_specs,
    generate_episode,
    generate_episode_event,
    generate_measurement,
    generate_observation,
)
from afbstepomop.mockdata.common import write_table
from afbstepomop.mockdata.core import (
    generate_condition_occurrence,
    generate_observation_period,
    generate_person,
)
from afbstepomop.mockdata.dataset import generate_dataset

__all__ = [
    "generate_condition_occurrence",
    "generate_dataset",
    "generate_device_specs",
    "generate_episode",
    "generate_episode_event",
    "generate_measurement",
    "generate_observation",
    "generate_observation_period",
    "generate_person",
    "write_table",
]
