"""Tunable constants for the mock data generator.

Everything the generator cannot read from ``source/`` lives here, in one file,
so that what is *specified* stays visibly separate from what is merely *chosen*
for the purpose of producing example data.

Two kinds of constant sit here, and the distinction matters:

shape
    How much data to produce and over what period — study window, cohort birth
    years, how many episodes a person may have. These are properties of the
    example, not of the specification, and changing them is harmless.
roles
    Which concept plays which part in the AF-burden architecture. The
    specification records that a concept *may* appear in a column; it does not
    record that AF burden is the quantity hanging off an aggregated monitoring
    window while maximum rate hangs off an individual episode. Until the spec
    can express that, the generator has to be told, and being told here is
    better than being told in the middle of a function.

The role constants are therefore a standing reminder of a gap in the
specification, not a convenience.
"""

from datetime import date

# --- Shape of the generated example -------------------------------------

STUDY_START = date(2020, 1, 1)
STUDY_END = date(2026, 12, 31)

EARLIEST_BIRTH_YEAR = 1930
LATEST_BIRTH_YEAR = 2000

STILL_IN_FOLLOW_UP_FRACTION = 0.2
MINIMUM_FOLLOW_UP_DAYS = 180
MAXIMUM_FOLLOW_UP_DAYS = 1800

MAX_CONDITIONS_PER_PERSON = 5
MAX_EPISODES_PER_PERSON = 3
MAX_WINDOW_DAYS = 365
MIN_WINDOW_DAYS = 30
MAX_EPISODE_DAYS = 7

MIN_ANALYSABLE_ECGS = 20
MAX_ANALYSABLE_ECGS = 500
MAX_EPISODE_DURATION_MINUTES = 10080

# How many persons carry each minimal-data-set concept. The minimal layer checks
# presence, not prevalence: its question is whether a concept can be found where
# the specification says it lives, not how common it is. A handful of rows answers
# that; one row per person per concept would multiply the dataset for no gain, and
# would claim a prevalence the specification never states.
MINIMAL_ITEM_PERSONS = 5

DEVICE_ALGORITHM_NAMES = ("AF-Detect", "SmartRhythm", "CardioScan")

# How often an ``expected`` column is filled. Not 1.0 on purpose: generated data
# should exercise the partly-filled case, which is what a real export looks like.
EXPECTED_FILL_PROBABILITY = 0.85
OPTIONAL_FILL_PROBABILITY = 0.5

# --- OMOP conventions ---------------------------------------------------

UNMAPPED_CONCEPT_ID = 0

# --- Roles the specification does not yet record ------------------------

# Ethnicity follows from race rather than being drawn independently, because
# the two are one field in the source codebook.
HISPANIC_RACE_CONCEPT_ID = 1546523
HISPANIC_ETHNICITY_CONCEPT_ID = 38003563
NON_HISPANIC_ETHNICITY_CONCEPT_ID = 38003564

# The two kinds of row the episode table carries, held in
# episode_concept_id. Not episode_type_concept_id, which is provenance.
AGGREGATED_WINDOW_CONCEPT_ID = 2000011002
DISAGGREGATED_EPISODE_CONCEPT_ID = 2000011003

# Quantities measured for each kind of episode.
AF_BURDEN_CONCEPT_ID = 2000008002
MAXIMUM_RATE_CONCEPT_ID = 2000009004

# Context recorded for an aggregated monitoring window.
BURDEN_METHOD_CONCEPT_ID = 2000008003
ANALYSABLE_ECG_COUNT_CONCEPT_ID = 2000008008
AF_ECG_COUNT_CONCEPT_ID = 2000008009

# Context recorded for an individual arrhythmia episode.
EPISODE_DURATION_CONCEPT_ID = 2000009003
SYMPTOMATIC_STATUS_CONCEPT_ID = 2000009005

# The permitted values of BURDEN_METHOD_CONCEPT_ID, listed explicitly. These
# were previously selected by numeric id range, which coupled the generator to
# how the custom vocabulary happens to be numbered.
AF_BURDEN_METHOD_CONCEPT_IDS = (2000008004, 2000008005, 2000008006)
