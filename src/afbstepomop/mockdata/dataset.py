"""Assemble a complete mock dataset from the generators.

Dependency order is the point of this module: persons, then the observation
periods that bound them, then the clinical events that must sit inside those
periods, then the AF-burden architecture and everything hanging off it.
"""

from __future__ import annotations

import random
from pathlib import Path

from afbstepomop.mockdata.afburden import (
    generate_device_exposure,
    generate_device_specs,
    generate_episode,
    generate_episode_event,
    generate_measurement,
    generate_observation,
)
from afbstepomop.mockdata.common import write_table
from afbstepomop.mockdata.minimal import generate_minimal_items
from afbstepomop.mockdata.core import (
    generate_condition_occurrence,
    generate_observation_period,
    generate_person,
)
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.structural import CdmSchema
from afbstepomop.source_validator.vocabulary import Vocabulary


def generate_dataset(
    n_persons: int = 50,
    output_dir: Path | None = None,
    *,
    seed: int = 0,
    schema: CdmSchema,
    spec: ProjectSpec,
    vocabulary: Vocabulary,
) -> dict[str, list[dict[str, object]]]:
    """Generate a complete mock dataset for the tables currently in scope.

    A table that is in scope but has no generator here is skipped rather than
    faked, so the gap stays visible.

    Parameters
    ----------
    n_persons : int, optional
        Number of persons to generate.
    output_dir : Path, optional
        Directory to write one CSV per table into, created if absent. Nothing
        is written when omitted.
    seed : int, optional
        Seed for the random generator, so a dataset is reproducible.
    schema : CdmSchema
        Parsed structural layer.
    spec : ProjectSpec
        Parsed project layer, deciding which tables are in scope.
    vocabulary : Vocabulary
        Parsed vocabulary layer.

    Returns
    -------
    dict of str to list of dict
        Generated rows keyed by table name, for inspection without re-reading
        the written files.
    """
    rng = random.Random(seed)

    persons = generate_person(n_persons, spec, vocabulary, rng)
    periods = generate_observation_period(persons, vocabulary, rng)
    conditions = generate_condition_occurrence(periods, spec, vocabulary, rng)

    episodes = generate_episode(periods, vocabulary, rng)
    measurements = generate_measurement(episodes, spec, vocabulary, rng)
    observations = generate_observation(episodes, spec, vocabulary, rng)
    exposures = generate_device_exposure(episodes, vocabulary, rng)
    devices = generate_device_specs(episodes, exposures, spec, rng)
    links = generate_episode_event(episodes, measurements, observations)

    generated = {
        "person": persons,
        "observation_period": periods,
        "condition_occurrence": conditions,
        "episode": episodes,
        "episode_event": links,
        "measurement": measurements,
        "observation": observations,
        "device_exposure": exposures,
        "device_specs": devices,
    }
    # Last, because it continues the primary key sequences the others started.
    for name, extra in generate_minimal_items(periods, generated, spec, vocabulary, schema, rng).items():
        generated.setdefault(name, []).extend(extra)

    dataset = {name: rows for name, rows in generated.items() if name in spec.in_scope()}

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in dataset.items():
            write_table(rows, name, schema, output_dir / f"{name}.csv")

    return dataset
