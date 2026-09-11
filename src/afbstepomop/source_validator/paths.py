"""Where the specification files live.

Defined once, because every loader needs it and a copy per module is a
standing hazard: moving the loaders is then a change that has to be made in
several places and silently resolves to a directory that does not exist if one
is missed.
"""

from pathlib import Path

DEFAULT_SOURCE_DIR = Path(__file__).parent.parent / "source"

STRUCTURAL_DIR = "structural"
CUSTOM_DIR = "custom"
SPEC_DIR = "spec"
