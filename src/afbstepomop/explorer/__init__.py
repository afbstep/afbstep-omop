"""Render the AFBSTEP specification as a browsable page.

The explorer is a *renderer* of the specification and reads nothing else: its
only inputs are the three loaders under
:mod:`afbstepomop.source_validator`. A fact the page needs that ``source/``
cannot supply is a signal to teach the specification, not to reach outside it.
"""

from afbstepomop.explorer.model import ExplorerModel, build_model
from afbstepomop.explorer.render import render_page

__all__ = ["ExplorerModel", "build_model", "render_page"]
