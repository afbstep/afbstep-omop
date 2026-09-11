"""
Entry points for the AFBSTEP specification package.

(uv run )
python main.py --validate ./export                     # against the spec only
python main.py --validate-full ./export                # + every concept against the stored catalogue
python main.py --validate                              # either, with no dir, runs the mock demo
python main.py --build-index /path/to/athena_download  # build the sqlite index file
python main.py --check-spec                            # check the source files (maintainers)

./export is the directory hodling the mapped csv files.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from afbstepomop.mockdata import generate_dataset
from afbstepomop.output_validator.athena import AthenaVocabulary, build_index
from afbstepomop.output_validator.resolver import ChainedVocabulary, PinnedVocabulary
from afbstepomop.source_validator.spec import load_spec
from afbstepomop.source_validator.structural import load_structural
from afbstepomop.output_validator.validate import read_dataset, validate
from afbstepomop.source_validator.vocabulary import load_vocabulary

BASELINE_PATH = Path(__file__).parent / "spec_baseline.txt"

# default path for the sqlite index file
DEFAULT_INDEX_PATH = Path("vocabulary.sqlite")

#: Sentinel for "--validate given without a directory": run against a generated
#: mock dataset rather than a partner export.
DEMO = Path("-")


def _dataset_argument(value: Path | None) -> Path | None:
    """Turn the parsed --validate value into a directory, or None for the demo."""
    return None if value is None or value == DEMO else value


def read_baseline(path: Path) -> set[str]:
    """Read the list of specification issues that are accepted for now.

    Parameters
    ----------
    path : Path
        Baseline file. Blank lines and ``#`` comments are ignored. A missing
        file means nothing is accepted, which is strict mode.

    Returns
    -------
    set of str
        Issue messages that should not fail the check.
    """
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def check_specification(baseline_path: Path = BASELINE_PATH) -> int:
    """Report incoherence in the specification itself, for maintainers.

    Issues listed in the baseline are reported as accepted rather than as
    failures, so a known open decision does not keep the pipeline red while a
    newly introduced problem does. A baseline entry that is no longer reported
    also fails, so the file cannot drift out of date silently.

    File defects always fail regardless of the baseline: whitespace and
    undocumented columns are format violations with a known fix, and letting
    them through is what this check exists to prevent.

    Parameters
    ----------
    baseline_path : Path, optional
        File listing accepted issues.

    Returns
    -------
    int
        Process exit code: ``0`` when nothing new is wrong.
    """
    schema = load_structural()
    vocabulary = load_vocabulary()
    spec = load_spec()

    print(f"CDM {schema.cdm_version}: {len(schema.tables)} tables, {len(schema.concept_columns())} concept columns")
    print(f"Vocabulary: {len(vocabulary.concepts)} concepts over {len(vocabulary.bindings())} concept columns")
    print(f"In scope: {', '.join(spec.in_scope())}")

    accepted = read_baseline(baseline_path)
    reported: set[str] = set()
    unexpected: list[str] = []

    for layer, problems in (
        ("structural", schema.issues()),
        ("vocabulary", vocabulary.issues(schema)),
        ("project", spec.issues(schema, vocabulary)),
    ):
        reported.update(problems)
        fresh = [problem for problem in problems if problem not in accepted]
        unexpected += fresh
        print(f"\n{layer}: {len(problems)} issue(s), {len(fresh)} not accepted")
        for problem in problems:
            print(f"  {'FAIL' if problem in fresh else 'ok  '}  {problem}")

    defects = list(vocabulary.defects) + list(spec.defects)
    print(f"\nfile defects: {len(defects)}")
    for defect in defects:
        print(f"  FAIL  {defect}")

    stale = sorted(accepted - reported)
    if stale:
        print(f"\nstale baseline entries: {len(stale)}")
        for entry in stale:
            print(f"  FAIL  no longer reported, remove from {baseline_path.name}: {entry}")

    failures = len(unexpected) + len(defects) + len(stale)
    print(f"\n{'PASSED' if failures == 0 else 'FAILED'} — {failures} blocking problem(s), {len(accepted)} accepted")
    return 0 if failures == 0 else 1


def validate_dataset(directory: Path | None, index_path: Path | None = None) -> int:
    """Validate a partner export, or a generated mock dataset when none is given.

    Parameters
    ----------
    directory : Path or None
        Directory holding one CSV per table. When None, a mock dataset is
        generated and validated instead, as a demonstration.
    index_path : Path, optional
        A vocabulary index built by ``--build-index``. Without it, concepts are
        resolved against the pinned specification only, and the report says so.

    Returns
    -------
    int
        Process exit code: ``0`` when the dataset meets every requirement.
    """
    schema = load_structural()
    vocabulary = load_vocabulary()
    spec = load_spec()
    source = None
    if index_path is not None:
        # AFBSTEP's own concepts live in the 2000000000+ local range and are
        # absent from any release, so the release is chained behind them.
        source = ChainedVocabulary(PinnedVocabulary(vocabulary, origins=("custom",)), AthenaVocabulary(index_path))

    if directory is not None:
        report = validate(read_dataset(directory, spec), schema, spec, vocabulary, source)
    else:
        print("No dataset given; generating a mock one to validate.\n")
        with TemporaryDirectory() as temporary:
            generated = Path(temporary)
            generate_dataset(50, generated, seed=0, schema=schema, spec=spec, vocabulary=vocabulary)
            report = validate(read_dataset(generated, spec), schema, spec, vocabulary, source)

    print(report.summary())
    return 0 if report.passed else 1


def build_vocabulary_index(vocabulary_dir: Path, index_path: Path) -> int:
    """Build the vocabulary index a full concept check needs.

    Parameters
    ----------
    vocabulary_dir : Path
        Directory holding an extracted OHDSI vocabulary download.
    index_path : Path
        Where to write the index.

    Returns
    -------
    int
        Process exit code.
    """
    print(f"Indexing {vocabulary_dir} — this reads a large file once and takes a few minutes.")
    indexed = build_index(vocabulary_dir, index_path)
    print(f"Indexed {indexed:,} concepts into {index_path}")
    print("Use it with: --validate-full ./export")
    return 0


def main() -> int:
    """Parse arguments and dispatch to the requested command."""
    parser = argparse.ArgumentParser(
        description="Validate a dataset against the AFBSTEP CDM specification.",
        epilog=(
            "Both validate commands take an export directory, or none at all to run "
            "against a freshly generated mock dataset."
        ),
    )
    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--validate",
        type=Path,
        nargs="?",
        const=DEMO,
        metavar="DIR",
        help="validate an export against the specification",
    )
    mode.add_argument(
        "--validate-full",
        type=Path,
        nargs="?",
        const=DEMO,
        metavar="DIR",
        help="as --validate, and additionally check every concept against the vocabulary index",
    )
    mode.add_argument(
        "--build-index",
        type=Path,
        metavar="DIR",
        help="build the vocabulary index from an extracted OHDSI download",
    )
    mode.add_argument(
        "--check-spec",
        action="store_true",
        help="check the specification against itself (maintainers, not partners)",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        metavar="PATH",
        help=f"where the vocabulary index is built and read (default: {DEFAULT_INDEX_PATH})",
    )
    arguments = parser.parse_args()

    if arguments.build_index is not None:
        return build_vocabulary_index(arguments.build_index, arguments.index_path)
    if arguments.check_spec:
        return check_specification()

    if arguments.validate_full is not None:
        if not arguments.index_path.exists():
            parser.error(
                f"no vocabulary index at {arguments.index_path}. Build one with:\n"
                f"    uv run python main.py --build-index /path/to/athena_download\n"
                f"or point --index-path at an existing index."
            )
        return validate_dataset(_dataset_argument(arguments.validate_full), arguments.index_path)

    return validate_dataset(_dataset_argument(arguments.validate))


if __name__ == "__main__":
    raise SystemExit(main())
