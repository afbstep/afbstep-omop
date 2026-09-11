"""Generate the explorer page from the specification files.

Run as a module so that nothing tracked in the repository has to import this
package while it is still gitignored::

    uv run python -m afbstepomop.explorer
    uv run python -m afbstepomop.explorer docs/index.html

Promoting it to a ``main.py --explore`` flag is a one-line change once the
package is shipped rather than ignored.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from afbstepomop.explorer.model import build_model
from afbstepomop.explorer.render import render_page
from afbstepomop.source_validator.spec import load_spec
from afbstepomop.source_validator.structural import load_structural
from afbstepomop.source_validator.vocabulary import load_vocabulary

#: Written next to wherever the command is run, unless a path is given.
DEFAULT_OUTPUT = Path("afbstep_explorer.html")


def write_explorer(output: Path) -> int:
    """Render the specification to one self-contained HTML file.

    Parameters
    ----------
    output : Path
        Where to write the page. Parent directories are created.

    Returns
    -------
    int
        Process exit code, ``0`` on success.
    """
    model = build_model(load_structural(), load_spec(), load_vocabulary())
    page = render_page(model)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")

    tables = model.in_scope_tables
    placed = sum(len(table.minimal_items) for table in tables)
    unplaced = sum(1 for group in model.checklist for item in group.items if item.concept is None)

    # Report the size on disk, not len(page): the page carries multi-byte
    # glyphs, so the character count is smaller and reads as a stale file.
    print(f"Wrote {output} ({output.stat().st_size:,} bytes)")
    print(f"  CDM {model.cdm_version}: {len(tables)} tables in scope, {len(model.edges)} foreign keys")
    print(f"  minimal data set: {placed} items placed, {unplaced} not yet placed")
    print(f"\nOpen it with:  xdg-open {output}")
    return 0


def main() -> int:
    """Parse arguments and write the page."""
    parser = argparse.ArgumentParser(
        prog="python -m afbstepomop.explorer",
        description="Render the AFBSTEP specification as one offline HTML page.",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT,
        help=f"where to write the page (default: {DEFAULT_OUTPUT})",
    )
    return write_explorer(parser.parse_args().output)


if __name__ == "__main__":
    raise SystemExit(main())
