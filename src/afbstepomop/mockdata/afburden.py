"""Generate the AF-burden architecture of a mock dataset.

AF burden is the study's primary quantity and the hardest thing the
specification has to describe, because it is not one row anywhere. It is an
aggregated monitoring window, the percentage of that window spent in atrial
fibrillation, the method by which the percentage was derived, the individual
arrhythmia episodes inside the window, and the device that detected them —
spread over ``episode``, ``measurement``, ``observation``, ``episode_event``
and the custom ``device_specs``.

Aggregated windows and individual episodes share the ``episode`` table and are
told apart by ``episode_type_concept_id``. That discriminator is what the whole
architecture rests on.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from afbstepomop.mockdata import config
from afbstepomop.mockdata.common import concept_pool, fill_probability, random_date, value_range
from afbstepomop.source_validator.spec import ProjectSpec
from afbstepomop.source_validator.vocabulary import Vocabulary


def is_aggregated(episode: dict[str, object]) -> bool:
    """Whether an episode row is an aggregated monitoring window.

    Read from ``episode_concept_id``, which is where OMOP records *what an
    episode is*. ``episode_type_concept_id`` carries provenance instead, and is
    not a discriminator between kinds of episode.
    """
    return episode.get("episode_concept_id") == config.AGGREGATED_WINDOW_CONCEPT_ID


def generate_episode(
    periods: list[dict[str, object]], vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate monitoring windows and the arrhythmia episodes inside them.

    Each person gets one aggregated window and zero or more disaggregated
    episodes nested inside it via ``episode_parent_id``.

    ``episode_concept_id`` carries the discriminator: an aggregated window and a
    disaggregated episode are different kinds of episode, not different
    provenances. Fields the specification pins no concepts for are emitted as
    concept ``0``, so the gap surfaces in the validation report rather than
    being hidden behind an invented value.

    Parameters
    ----------
    periods : list of dict
        Rows returned by :func:`~afbstepomop.mockdata.core.generate_observation_period`.
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Aggregated windows and their child episodes, keyed by column name.
    """
    kinds = {c.concept_id for c in vocabulary.bindings().get(("episode", "episode_concept_id"), ())}
    aggregated = (
        config.AGGREGATED_WINDOW_CONCEPT_ID
        if config.AGGREGATED_WINDOW_CONCEPT_ID in kinds
        else config.UNMAPPED_CONCEPT_ID
    )
    disaggregated = (
        config.DISAGGREGATED_EPISODE_CONCEPT_ID
        if config.DISAGGREGATED_EPISODE_CONCEPT_ID in kinds
        else config.UNMAPPED_CONCEPT_ID
    )
    provenance = concept_pool(vocabulary, "episode", "episode_type_concept_id")
    about = concept_pool(vocabulary, "episode", "episode_object_concept_id")

    rows: list[dict[str, object]] = []
    for period in periods:
        observed_start = date.fromisoformat(str(period["observation_period_start_date"]))
        observed_end = date.fromisoformat(str(period["observation_period_end_date"]))

        window_start = random_date(rng, observed_start, observed_end)
        window_span = rng.randint(config.MIN_WINDOW_DAYS, config.MAX_WINDOW_DAYS)
        window_end = min(window_start + timedelta(days=window_span), observed_end)

        window_id = len(rows) + 1
        rows.append(
            {
                "episode_id": window_id,
                "person_id": period["person_id"],
                "episode_concept_id": aggregated,
                "episode_start_date": window_start.isoformat(),
                "episode_end_date": window_end.isoformat(),
                "episode_number": 1,
                "episode_object_concept_id": rng.choice(about),
                "episode_type_concept_id": rng.choice(provenance),
            }
        )

        for number in range(1, rng.randint(0, config.MAX_EPISODES_PER_PERSON) + 1):
            start = random_date(rng, window_start, window_end)
            episode_span = rng.randint(0, config.MAX_EPISODE_DAYS)
            rows.append(
                {
                    "episode_id": len(rows) + 1,
                    "person_id": period["person_id"],
                    "episode_concept_id": disaggregated,
                    "episode_start_date": start.isoformat(),
                    "episode_end_date": min(start + timedelta(days=episode_span), window_end).isoformat(),
                    "episode_parent_id": window_id,
                    "episode_number": number,
                    "episode_object_concept_id": rng.choice(about),
                    "episode_type_concept_id": rng.choice(provenance),
                }
            )

    return rows


def generate_measurement(
    episodes: list[dict[str, object]], spec: ProjectSpec, vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate the numeric quantity each episode carries.

    An aggregated window carries the AF burden as a percentage of monitored
    time; a disaggregated episode carries the maximum rate reached during it.
    Both values and their units come from ``plausibility.csv``, so a generated
    dataset cannot contradict the ranges the specification states.

    Parameters
    ----------
    episodes : list of dict
        Rows returned by :func:`generate_episode`.
    spec : ProjectSpec
        Parsed project layer, supplying the ranges.
    vocabulary : Vocabulary
        Parsed vocabulary layer, supplying the type concept.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Measurement rows keyed by column name.
    """
    types = concept_pool(vocabulary, "measurement", "measurement_type_concept_id")

    rows: list[dict[str, object]] = []
    for episode in episodes:
        concept_id = (
            config.AF_BURDEN_CONCEPT_ID if is_aggregated(episode) else config.MAXIMUM_RATE_CONCEPT_ID
        )
        low, high, unit = value_range(spec, concept_id)

        rows.append(
            {
                "measurement_id": len(rows) + 1,
                "person_id": episode["person_id"],
                "measurement_concept_id": concept_id,
                "measurement_date": episode["episode_end_date"],
                "measurement_type_concept_id": rng.choice(types),
                "value_as_number": round(rng.uniform(low, high), 1),
                "unit_concept_id": unit if unit is not None else "",
                "measurement_event_id": episode["episode_id"],
            }
        )

    return rows


def generate_observation(
    episodes: list[dict[str, object]], spec: ProjectSpec, vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate the qualitative context each episode needs to be interpretable.

    An aggregated window records how the burden was estimated and how much
    signal it rests on; a disaggregated episode records its duration and
    whether it was symptomatic. Burden figures are not comparable across
    estimation methods, so the method is not optional context.

    Parameters
    ----------
    episodes : list of dict
        Rows returned by :func:`generate_episode`.
    spec : ProjectSpec
        Parsed project layer, supplying the ranges the counts must fall in.
    vocabulary : Vocabulary
        Parsed vocabulary layer.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Observation rows keyed by column name.
    """
    types = concept_pool(vocabulary, "observation", "observation_type_concept_id")
    permitted = {c.concept_id for c in vocabulary.bindings().get(("observation", "value_as_concept_id"), ())}
    methods = [c for c in config.AF_BURDEN_METHOD_CONCEPT_IDS if c in permitted] or [
        config.UNMAPPED_CONCEPT_ID
    ]

    rows: list[dict[str, object]] = []

    def emit(episode: dict[str, object], concept_id: int, **values: object) -> None:
        """Append one observation row bound to an episode."""
        rows.append(
            {
                "observation_id": len(rows) + 1,
                "person_id": episode["person_id"],
                "observation_concept_id": concept_id,
                "observation_date": episode["episode_end_date"],
                "observation_type_concept_id": rng.choice(types),
                "observation_event_id": episode["episode_id"],
                **values,
            }
        )

    for episode in episodes:
        if is_aggregated(episode):
            emit(episode, config.BURDEN_METHOD_CONCEPT_ID, value_as_concept_id=rng.choice(methods))

            # Counts come from plausibility.csv rather than from constants here,
            # so widening a range in the spec widens the generated data with it
            # and the two cannot drift apart. The spec currently bounds neither
            # count, so the example supplies its own range for the ones it does
            # not state; a bound added to the spec overrides it.
            low, high, _ = value_range(
                spec,
                config.ANALYSABLE_ECG_COUNT_CONCEPT_ID,
                default_low=config.MIN_ANALYSABLE_ECGS,
                default_high=config.MAX_ANALYSABLE_ECGS,
            )
            analysable = rng.randint(int(low), int(high))
            emit(episode, config.ANALYSABLE_ECG_COUNT_CONCEPT_ID, value_as_number=analysable)

            af_low, _, _ = value_range(spec, config.AF_ECG_COUNT_CONCEPT_ID)
            emit(episode, config.AF_ECG_COUNT_CONCEPT_ID, value_as_number=rng.randint(int(af_low), analysable))
        else:
            emit(
                episode,
                config.EPISODE_DURATION_CONCEPT_ID,
                value_as_number=rng.randint(1, config.MAX_EPISODE_DURATION_MINUTES),
            )
            emit(episode, config.SYMPTOMATIC_STATUS_CONCEPT_ID, value_as_number=rng.randint(0, 1))

    return rows


def generate_device_exposure(
    episodes: list[dict[str, object]], vocabulary: Vocabulary, rng: random.Random
) -> list[dict[str, object]]:
    """Generate the device exposure behind each aggregated monitoring window.

    ``device_specs`` names its device through ``device_exposure_id``, which the
    CDM declares NOT NULL, so a window described by a ``device_specs`` row needs
    an exposure row to point at. One exposure per aggregated window, spanning
    the window, keeps that a one-to-one relationship.

    Parameters
    ----------
    episodes : list of dict
        Rows returned by :func:`generate_episode`.
    vocabulary : Vocabulary
        Parsed vocabulary layer, supplying the permitted device concepts.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Device exposure rows keyed by column name, one per aggregated window.
    """
    devices = concept_pool(vocabulary, "device_exposure", "device_concept_id")
    types = concept_pool(vocabulary, "device_exposure", "device_type_concept_id")

    rows: list[dict[str, object]] = []
    for episode in episodes:
        if not is_aggregated(episode):
            continue

        rows.append(
            {
                "device_exposure_id": len(rows) + 1,
                "person_id": episode["person_id"],
                "device_concept_id": rng.choice(devices),
                "device_exposure_start_date": episode["episode_start_date"],
                "device_exposure_end_date": episode["episode_end_date"],
                "device_type_concept_id": rng.choice(types),
            }
        )

    return rows


def generate_device_specs(
    episodes: list[dict[str, object]],
    exposures: list[dict[str, object]],
    spec: ProjectSpec,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Generate the detection algorithm behind each aggregated monitoring window.

    Only aggregated windows get a device row, because ``device_specs`` is keyed
    on ``episode_id`` and it is the monitoring window, not an individual
    arrhythmia episode, that a device produced. The device itself is described by
    the matching ``device_exposure`` row; this table adds what the CDM has no
    field for, the detection algorithm and its version.

    Parameters
    ----------
    episodes : list of dict
        Rows returned by :func:`generate_episode`.
    exposures : list of dict
        Rows returned by :func:`generate_device_exposure`, one per aggregated
        window and in the same order. Paired strictly, so a change to either
        filter fails here rather than silently mismatching the two tables.
    spec : ProjectSpec
        Parsed project layer, deciding how completely to fill each column.
    rng : random.Random
        Seeded generator.

    Returns
    -------
    list of dict
        Device rows keyed by column name, one per aggregated window.
    """
    algorithm_probability = fill_probability(spec, "device_specs", "device_algorithm", nullable=True)
    aggregated = [episode for episode in episodes if is_aggregated(episode)]

    rows: list[dict[str, object]] = []
    for episode, exposure in zip(aggregated, exposures, strict=True):
        row: dict[str, object] = {
            "episode_id": episode["episode_id"],
            "person_id": episode["person_id"],
            "device_exposure_id": exposure["device_exposure_id"],
        }
        if rng.random() < algorithm_probability:
            row["device_algorithm"] = rng.choice(config.DEVICE_ALGORITHM_NAMES)
            row["device_algorithm_v"] = f"{rng.randint(1, 4)}.{rng.randint(0, 9)}"
        rows.append(row)

    return rows


def generate_episode_event(
    episodes: list[dict[str, object]],
    measurements: list[dict[str, object]],
    observations: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Link each episode to the measurement and observation rows derived from it.

    ``episode_event_field_concept_id`` is emitted as concept ``0`` because the
    specification pins no field concepts yet. Without them the link cannot be
    resolved to a table, so this is a gap the validator should report rather
    than one the generator should paper over.

    Parameters
    ----------
    episodes : list of dict
        Rows returned by :func:`generate_episode`.
    measurements, observations : list of dict
        Rows carrying an ``*_event_id`` back-reference to an episode.

    Returns
    -------
    list of dict
        One row per linked event.
    """
    known = {episode["episode_id"] for episode in episodes}

    links: list[dict[str, object]] = []
    for rows, key in ((measurements, "measurement_event_id"), (observations, "observation_event_id")):
        for row in rows:
            episode_id = row.get(key)
            if episode_id in known:
                links.append(
                    {
                        "episode_id": episode_id,
                        "event_id": row.get("measurement_id") or row.get("observation_id"),
                        "episode_event_field_concept_id": config.UNMAPPED_CONCEPT_ID,
                    }
                )

    return links
