"""Render the explorer model as one self-contained HTML page.

The page is a network of the tables a partner populates. Clicking a table
reveals what the specification asks for in it: the fields with a recorded
requirement, and the minimal-data-set items recorded there.

Three constraints shape everything here:

no external requests
    No CDN, no web font, no image. Partners open this from inside hospital
    networks that block outbound traffic, and a page whose layout depends on a
    script it cannot fetch is worse than no page. CSS and JavaScript are
    inlined, and the graph is plain SVG.
the layout is computed here, not in the browser
    Positions come from the foreign-key topology by a deterministic rule, so
    two runs on the same specification produce the same file and a diff means
    the specification changed. A physics simulation in the browser would settle
    somewhere slightly different every time.
the page shows the minimal data set
    Not every column and not the whole vocabulary. What a partner must produce
    is a much shorter document than what the CDM permits, and conflating the
    two is what makes OMOP hard to approach.

Only the model is read. Anything the page would like to show that
:mod:`afbstepomop.explorer.model` cannot supply is a gap in the specification,
to be fixed there rather than worked around here.
"""

from __future__ import annotations

import html
import math

from afbstepomop.explorer.model import ExplorerModel, TableView

#: Where the graph hangs from. Every clinical table points at it, so it is the
#: natural centre and the only sensible root for the radial layout.
HUB = "person"

#: SVG canvas. Scaled to the viewport by ``viewBox``, so these are proportions
#: rather than pixels.
CANVAS_WIDTH = 1720
CANVAS_HEIGHT = 1080

#: Radii of the first ring, as an ellipse: screens are wider than they are
#: tall, and the first ring carries thirteen tables.
RING_RX = 560
RING_RY = 380

#: How much further out each additional step from the hub sits.
RING_STEP = 175

NODE_HEIGHT = 38
NODE_MIN_WIDTH = 118
NODE_CHAR_WIDTH = 8.1
NODE_PADDING = 26


def _escape(value: object) -> str:
    """Escape a value for inclusion in HTML text or an attribute.

    Parameters
    ----------
    value : object
        Rendered with ``str`` first, so numbers and None are accepted.

    Returns
    -------
    str
    """
    return html.escape(str(value), quote=True)


def _node_width(name: str) -> float:
    """Width of a table's box, wide enough for its name.

    Parameters
    ----------
    name : str
        Table name.

    Returns
    -------
    float
    """
    return max(NODE_MIN_WIDTH, len(name) * NODE_CHAR_WIDTH + NODE_PADDING)


def _adjacency(model: ExplorerModel) -> dict[str, set[str]]:
    """Build the undirected neighbour map over in-scope tables.

    Direction is dropped because the layout asks "what is near what", which is
    a question about connection rather than about which side holds the key.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the edges.

    Returns
    -------
    dict of str to set of str
        Neighbours per table. Self-references are excluded: they say nothing
        about placement.
    """
    neighbours: dict[str, set[str]] = {}
    for edge in model.edges:
        if not edge.within_scope or edge.table == edge.parent_table:
            continue
        neighbours.setdefault(edge.table, set()).add(edge.parent_table)
        neighbours.setdefault(edge.parent_table, set()).add(edge.table)
    return neighbours


def _depths(names: list[str], neighbours: dict[str, set[str]]) -> dict[str, int]:
    """Breadth-first distance from the hub, for every in-scope table.

    Parameters
    ----------
    names : list of str
        In-scope table names.
    neighbours : dict of str to set of str
        Undirected adjacency.

    Returns
    -------
    dict of str to int
        Distance from :data:`HUB`. Tables with no path to it are absent, which
        is how the caller recognises them.
    """
    if HUB not in names:
        return {}

    depth = {HUB: 0}
    frontier = [HUB]
    while frontier:
        following: list[str] = []
        for name in frontier:
            for neighbour in sorted(neighbours.get(name, ())):
                if neighbour not in depth and neighbour in names:
                    depth[neighbour] = depth[name] + 1
                    following.append(neighbour)
        frontier = following
    return depth


def _ring_order(ring: list[str], neighbours: dict[str, set[str]], degrees: dict[str, int]) -> list[str]:
    """Order the first ring so that connected tables sit together.

    Tables on the first ring all attach to the hub, so the hub's own edges
    cannot cross. The edges that *can* cross are the ones between first-ring
    tables — ``measurement`` to ``visit_occurrence`` and its like. Grouping each
    table beside the busiest neighbour it shares the ring with keeps those
    chords short instead of letting them cut across the middle.

    Parameters
    ----------
    ring : list of str
        Tables at distance one from the hub.
    neighbours : dict of str to set of str
        Undirected adjacency.
    degrees : dict of str to int
        Edge count per table, used to pick the busier of two neighbours.

    Returns
    -------
    list of str
        The ring in drawing order.
    """
    members = set(ring)

    def anchor(name: str) -> str:
        """The ring neighbour this table clusters around, or itself."""
        siblings = [n for n in neighbours.get(name, ()) if n in members]
        if not siblings:
            return name
        busiest = max(siblings, key=lambda n: (degrees.get(n, 0), n))
        return busiest if degrees.get(busiest, 0) > degrees.get(name, 0) else name

    clusters: dict[str, list[str]] = {}
    for name in sorted(ring):
        clusters.setdefault(anchor(name), []).append(name)

    ordered: list[str] = []
    for lead in sorted(clusters, key=lambda n: (-degrees.get(n, 0), n)):
        group = clusters[lead]
        # The cluster's own hub first, so it sits at the group's edge rather
        # than being separated from the tables that point at it.
        ordered += sorted(group, key=lambda n: (n != lead, n))
    return ordered


def _positions(model: ExplorerModel) -> dict[str, tuple[float, float]]:
    """Place every in-scope table on the canvas.

    The hub sits at the centre, its neighbours on an ellipse around it, and
    anything further out at the angle of the table it hangs from, one step
    further from the centre. Tables with no foreign key to anything in scope
    cannot be placed by connection and are set out along the bottom, which
    states plainly that they stand apart.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the in-scope tables and their edges.

    Returns
    -------
    dict of str to tuple of float
        Centre point per table name.
    """
    names = [table.name for table in model.in_scope_tables]
    neighbours = _adjacency(model)
    degrees = {name: len(neighbours.get(name, ())) for name in names}
    depth = _depths(names, neighbours)

    centre_x, centre_y = CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2
    positions: dict[str, tuple[float, float]] = {HUB: (centre_x, centre_y)} if HUB in names else {}
    angles: dict[str, float] = {}

    # Tables with no in-scope foreign key take a place on the ring like any
    # other. Having no line drawn to them already says they stand alone, and
    # putting them in a row apart only left a hole in the layout.
    on_ring = [n for n in names if depth.get(n) == 1 or (n not in depth and n != HUB)]
    ring = _ring_order(on_ring, neighbours, degrees)
    for index, name in enumerate(ring):
        angle = 2 * math.pi * index / max(len(ring), 1) - math.pi / 2
        angles[name] = angle
        positions[name] = (centre_x + RING_RX * math.cos(angle), centre_y + RING_RY * math.sin(angle))

    # Everything beyond the first ring is placed outside the table it hangs
    # from, so a chain such as person_study -> study -> study_attribute reads
    # outward along one line rather than being scattered.
    for distance in range(2, max(depth.values(), default=0) + 1):
        for name in sorted(n for n in names if depth.get(n) == distance):
            parents = [n for n in neighbours.get(name, ()) if depth.get(n, 99) == distance - 1]
            angle = angles[sorted(parents)[0]] if parents else 0.0
            siblings = sorted(
                n for n in names
                if depth.get(n) == distance
                and [p for p in neighbours.get(n, ()) if depth.get(p, 99) == distance - 1] == parents
            )
            spread = (siblings.index(name) - (len(siblings) - 1) / 2) * 0.22
            angle += spread
            angles[name] = angle
            rx, ry = RING_RX + (distance - 1) * RING_STEP, RING_RY + (distance - 1) * RING_STEP
            positions[name] = (centre_x + rx * math.cos(angle), centre_y + ry * math.sin(angle))

    unplaced = sorted(n for n in names if n not in positions)
    for index, name in enumerate(unplaced):
        positions[name] = (150 + index * 230, CANVAS_HEIGHT - 40)
    return positions


def _edges_svg(model: ExplorerModel, positions: dict[str, tuple[float, float]]) -> str:
    """Draw the foreign keys as lines, and self-references as a loop.

    Lines run centre to centre and the table boxes are drawn over them, so no
    trimming at the box edge is needed.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the edges.
    positions : dict
        Centre point per table.

    Returns
    -------
    str
        SVG markup.
    """
    parts: list[str] = []
    for edge in model.edges:
        if not edge.within_scope or edge.table not in positions or edge.parent_table not in positions:
            continue
        title = _escape(f"{edge.table}.{edge.column} → {edge.parent_table}.{edge.parent_column}")
        if edge.table == edge.parent_table:
            x, y = positions[edge.table]
            top = y - NODE_HEIGHT / 2
            parts.append(
                f'<path class="edge self" data-a="{_escape(edge.table)}" data-b="{_escape(edge.table)}" '
                f'd="M {x - 26:.1f} {top:.1f} C {x - 46:.1f} {top - 66:.1f}, '
                f'{x + 46:.1f} {top - 66:.1f}, {x + 26:.1f} {top:.1f}"><title>{title}</title></path>'
            )
            continue
        x1, y1 = positions[edge.table]
        x2, y2 = positions[edge.parent_table]
        parts.append(
            f'<line class="edge" data-a="{_escape(edge.table)}" data-b="{_escape(edge.parent_table)}" '
            f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"><title>{title}</title></line>'
        )
    return "\n".join(parts)


def _nodes_svg(model: ExplorerModel, positions: dict[str, tuple[float, float]]) -> str:
    """Draw each table as a labelled box, coloured by tier.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the tables.
    positions : dict
        Centre point per table.

    Returns
    -------
    str
        SVG markup.
    """
    parts: list[str] = []
    for table in model.in_scope_tables:
        if table.name not in positions:
            continue
        x, y = positions[table.name]
        width = _node_width(table.name)
        custom = " custom" if table.origin != "structural" else ""
        count = len(table.minimal_items)
        badge_x, badge_y = x + width / 2 - 3, y - NODE_HEIGHT / 2 + 3
        badge = (
            f'<circle class="disc" cx="{badge_x:.1f}" cy="{badge_y:.1f}" r="10.5"/>'
            f'<text class="count" x="{badge_x:.1f}" y="{badge_y:.1f}">{count}</text>'
            if count
            else ""
        )
        parts.append(
            f'<g class="node {_escape(table.tier)}{custom}" data-table="{_escape(table.name)}" tabindex="0" '
            f'role="button" aria-label="{_escape(table.name)}, {_escape(table.tier)}">'
            f'<rect x="{x - width / 2:.1f}" y="{y - NODE_HEIGHT / 2:.1f}" '
            f'width="{width:.1f}" height="{NODE_HEIGHT}" rx="7"/>'
            f'<text x="{x:.1f}" y="{y:.1f}">{_escape(table.name)}</text>{badge}</g>'
        )
    return "\n".join(parts)


def _viewbox(model: ExplorerModel, positions: dict[str, tuple[float, float]]) -> str:
    """Fit the drawing area to what was actually placed.

    The layout frame is a starting point, not a boundary: a deep chain of
    tables pushes nodes past it, and a fixed ``viewBox`` would then clip them.
    Measuring the result instead means the page stays correct whatever the
    specification's shape turns out to be.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the tables.
    positions : dict
        Centre point per table.

    Returns
    -------
    str
        A ``viewBox`` value.
    """
    padding = 46
    xs: list[float] = []
    ys: list[float] = []
    for table in model.in_scope_tables:
        if table.name not in positions:
            continue
        x, y = positions[table.name]
        half = _node_width(table.name) / 2
        xs += [x - half, x + half]
        # Self-reference loops arc above the box and must not be clipped.
        ys += [y - NODE_HEIGHT / 2 - 70, y + NODE_HEIGHT / 2]

    if not xs:
        return f"0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}"
    left, top = min(xs) - padding, min(ys) - padding
    return f"{left:.0f} {top:.0f} {max(xs) - left + padding:.0f} {max(ys) - top + padding:.0f}"


def _bounds_text(concept) -> str:
    """State a concept's plausibility rules in one readable phrase.

    Parameters
    ----------
    concept : ConceptView
        The concept whose bounds are wanted.

    Returns
    -------
    str
        Empty when the concept is unconstrained.
    """
    phrases: list[str] = []
    for bound in concept.bounds:
        if bound.minimum is not None and bound.maximum is not None:
            span = f"{bound.minimum:g} to {bound.maximum:g}"
        elif bound.minimum is not None:
            span = f"at least {bound.minimum:g}"
        elif bound.maximum is not None:
            span = f"at most {bound.maximum:g}"
        else:
            span = ""
        phrases.append(" ".join(part for part in (span, bound.unit_name) if part))
    return "; ".join(phrase for phrase in phrases if phrase)


def _field_rows(table: TableView) -> str:
    """Render the columns AFBSTEP records a requirement for.

    Laid out as stacked rows rather than a table: the panel is a narrow column,
    and a rationale worth reading does not survive being squeezed into a third
    of it.

    Parameters
    ----------
    table : TableView
        The table being described.

    Returns
    -------
    str
        HTML markup, or a note when the specification names no column.
    """
    if not table.required_fields:
        return '<p class="empty">No field requirement recorded for this table.</p>'

    rows: list[str] = []
    for field in table.required_fields:
        marks = []
        if field.is_concept_field:
            marks.append('<span class="mark">concept</span>')
        if field.references and not field.is_concept_field:
            marks.append(f'<span class="mark ref" data-goto="{_escape(field.references)}">'
                         f'→ {_escape(field.references)}</span>')
        why = f'<div class="why">{_escape(field.rationale)}</div>' if field.rationale else ""
        rows.append(
            f'<div class="row"><div class="head"><code>{_escape(field.name)}</code>'
            f'<span class="req {_escape(field.requirement)}">{_escape(field.requirement)}</span>'
            f'</div><div class="marks">{"".join(marks)}</div>{why}</div>'
        )
    return "".join(rows)


def _item_rows(table: TableView) -> str:
    """Render the minimal-data-set items recorded in one table.

    Parameters
    ----------
    table : TableView
        The table being described.

    Returns
    -------
    str
        HTML markup, or a note when no item lands here.
    """
    if not table.minimal_items:
        return '<p class="empty">No minimal-data-set item is recorded in this table.</p>'

    rows: list[str] = []
    for item in table.minimal_items:
        concept = item.concept
        marks: list[str] = []
        if concept.is_custom:
            marks.append('<span class="mark afbstep">AFBSTEP concept</span>')
        bounds = _bounds_text(concept)
        if bounds:
            marks.append(f'<span class="mark bound">{_escape(bounds)}</span>')
        if concept.answers:
            answers = ", ".join(_escape(a.name) for a in concept.answers)
            marks.append(f'<span class="mark answers">answers: {answers}</span>')
        rows.append(
            f'<div class="row"><div class="head"><span class="item">{_escape(item.item)}</span></div>'
            f'<div class="sub">{_escape(item.domain)} · {_escape(item.domain_label)}</div>'
            f'<div class="sub"><code>{_escape(concept.column)}</code> · '
            f"{_escape(concept.concept_id)} {_escape(concept.name)}</div>"
            f'<div class="marks">{"".join(marks)}</div></div>'
        )
    return "".join(rows)


def _panels(model: ExplorerModel) -> str:
    """Render one hidden panel per table, plus the unplaced-items panel.

    Panels are pre-rendered rather than built in the browser from embedded
    data: the page then needs only enough script to show one and hide the rest,
    and it still reads correctly if the script does not run.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the tables and the checklist.

    Returns
    -------
    str
        HTML markup.
    """
    parts: list[str] = []
    for table in model.in_scope_tables:
        custom = ('<span class="badge afbstep">AFBSTEP table</span>'
                  if table.origin != "structural" else "")
        parts.append(
            f'<section class="panel" id="panel-{_escape(table.name)}" hidden>'
            f"<h2><code>{_escape(table.name)}</code>"
            f'<span class="badge {_escape(table.tier)}">{_escape(table.tier)}</span>{custom}</h2>'
            f'<p class="rationale">{_escape(table.rationale)}</p>'
            f"<h3>Fields to populate</h3>{_field_rows(table)}"
            f"<h3>Minimal data set recorded here</h3>{_item_rows(table)}"
            f"</section>"
        )
    parts.append(_unplaced_panel(model))
    return "\n".join(parts)


def _unplaced_panel(model: ExplorerModel) -> str:
    """Render the minimal-data-set items that no table can show.

    An item naming no pinned concept has nowhere to sit on the diagram. Leaving
    it out would make the page claim the minimal data set is fully specified,
    so it gets a panel of its own.

    Parameters
    ----------
    model : ExplorerModel
        Supplies the checklist.

    Returns
    -------
    str
        HTML markup.
    """
    rows: list[str] = []
    for group in model.checklist:
        for item in group.items:
            if item.concept is not None:
                continue
            rows.append(
                f'<div class="row"><div class="head"><span class="item">'
                f'{_escape(item.item)}</span></div>'
                f'<div class="sub">{_escape(item.domain)} · '
                f"{_escape(item.domain_label)}</div>"
                f'<div class="why">{_escape(item.unresolved)}</div></div>'
            )
    body = "".join(rows) or '<p class="empty">Every item resolves.</p>'
    return (
        '<section class="panel" id="panel-unplaced" hidden>'
        "<h2>Items not yet placed</h2>"
        '<p class="rationale">These belong to the minimal data set but name no concept the '
        "specification pins, so no table can show them yet. They are listed here rather than "
        "omitted, because omitting them would overstate how complete the specification is.</p>"
        f"{body}</section>"
    )


#: Inlined because the page must render with no outbound request.
STYLE = """
:root{--ink:#12181f;--muted:#5b6673;--line:#d8dee6;--bg:#f4f6f9;--card:#fff;
--mandatory:#1c4f7c;--mandatory-bg:#dbeafe;--expected:#8a5100;--expected-bg:#fdeccd;
--optional:#4b5563;--optional-bg:#eef1f5;--afbstep:#6b21a8;}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:var(--ink);background:var(--bg)}
header{padding:14px 20px;background:var(--card);border-bottom:1px solid var(--line);
display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
header h1{font-size:16px;margin:0;font-weight:640}
header .sub{color:var(--muted);font-size:13px}
header .spacer{flex:1}
input[type=search]{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:6px;
background:var(--bg);min-width:190px}
button{font:inherit;padding:6px 11px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--muted)}
main{display:flex;align-items:stretch;gap:0;height:calc(100vh - 53px)}
#graph{flex:1;min-width:0;display:flex;padding:10px}
aside{width:500px;flex:none;background:var(--card);border-left:1px solid var(--line);
overflow-y:auto;padding:20px 22px}
svg{width:100%;height:100%;display:block}
.edge{stroke:#aab4c0;stroke-width:1.4;fill:none}
.edge.self{stroke-dasharray:3 3}
.edge.lit{stroke:#1c4f7c;stroke-width:2.6}
.node{cursor:pointer}
.node rect{fill:var(--optional-bg);stroke:var(--optional);stroke-width:1.5}
.node text{font:600 13px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
fill:var(--ink);text-anchor:middle;dominant-baseline:central;pointer-events:none}
.node text.count{font-size:11px;font-weight:700;fill:#fff;text-anchor:middle}
.node circle.disc{fill:var(--optional);stroke:var(--card);stroke-width:1.5}
.node.mandatory circle.disc{fill:var(--mandatory)}
.node.expected circle.disc{fill:var(--expected)}
.node.mandatory rect{fill:var(--mandatory-bg);stroke:var(--mandatory);stroke-width:2}
.node.expected rect{fill:var(--expected-bg);stroke:var(--expected)}
.node.custom rect{stroke-dasharray:5 3}
.node:hover rect{filter:brightness(.96)}
.node.on rect{stroke-width:3;filter:none}
.node.dim{opacity:.22}
.node:focus{outline:none}.node:focus rect{stroke-width:3}
h2{font-size:16px;margin:0 0 6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
h3{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
margin:22px 0 7px;font-weight:700}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.rationale{color:var(--muted);margin:0}
.badge{font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px;text-transform:uppercase;
letter-spacing:.03em;background:var(--optional-bg);color:var(--optional)}
.badge.mandatory{background:var(--mandatory-bg);color:var(--mandatory)}
.badge.expected{background:var(--expected-bg);color:var(--expected)}
.badge.afbstep{background:#f3e8ff;color:var(--afbstep)}
.row{border-bottom:1px solid #edf0f4;padding:9px 0}
.row:last-child{border-bottom:none}
.row .head{display:flex;align-items:baseline;gap:10px;justify-content:space-between}
.row .item{font-weight:640}
.row .sub{color:var(--muted);font-size:12px;margin-top:2px}
.row .why{color:var(--muted);font-size:12.5px;margin-top:3px}
.row .marks{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}
.row .marks:empty{margin:0}
.empty{color:var(--muted);font-style:italic;margin:0}
.req{font-size:11px;font-weight:700;padding:1px 6px;border-radius:4px;
background:var(--optional-bg);color:var(--optional)}
.req.required{background:var(--mandatory-bg);color:var(--mandatory)}
.req.expected{background:var(--expected-bg);color:var(--expected)}
.mark{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--bg);
color:var(--muted);white-space:nowrap}
.mark.ref{cursor:pointer;color:var(--mandatory);background:var(--mandatory-bg)}
.mark.afbstep{background:#f3e8ff;color:var(--afbstep)}
.mark.bound{background:#e7f5ec;color:#166534}
.mark.answers{white-space:normal}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px;align-items:center}
.key{width:11px;height:11px;border-radius:3px;display:inline-block;vertical-align:-1px;margin-right:5px}
@media(max-width:900px){main{flex-direction:column;height:auto}aside{width:auto;border-left:none;
border-top:1px solid var(--line)}#graph{height:70vh}}
"""

#: Enough script to reveal a panel and light up the edges of a table, and no
#: more. The page is readable without it.
SCRIPT = """
(function(){
var nodes=[].slice.call(document.querySelectorAll('.node'));
var edges=[].slice.call(document.querySelectorAll('.edge'));
var panels=[].slice.call(document.querySelectorAll('.panel'));
var intro=document.getElementById('intro');

function show(id){
  panels.forEach(function(p){p.hidden = p.id !== id;});
  if(intro) intro.hidden = true;
}
function select(name){
  nodes.forEach(function(n){n.classList.toggle('on', n.dataset.table===name);});
  edges.forEach(function(e){
    e.classList.toggle('lit', e.dataset.a===name || e.dataset.b===name);
  });
  show('panel-'+name);
  var panel=document.getElementById('panel-'+name);
  if(panel) panel.parentNode.scrollTop=0;
}
nodes.forEach(function(n){
  n.addEventListener('click',function(){select(n.dataset.table);});
  n.addEventListener('keydown',function(e){
    if(e.key==='Enter'||e.key===' '){e.preventDefault();select(n.dataset.table);}
  });
});
document.addEventListener('click',function(e){
  var ref=e.target.closest('.mark.ref');
  if(ref) select(ref.dataset.goto);
});
var unplaced=document.getElementById('show-unplaced');
if(unplaced) unplaced.addEventListener('click',function(){
  nodes.forEach(function(n){n.classList.remove('on');});
  edges.forEach(function(e){e.classList.remove('lit');});
  show('panel-unplaced');
});
var filter=document.getElementById('filter');
if(filter) filter.addEventListener('input',function(){
  var q=filter.value.trim().toLowerCase();
  nodes.forEach(function(n){
    n.classList.toggle('dim', q!=='' && n.dataset.table.indexOf(q)===-1);
  });
});
})();
"""


def render_page(model: ExplorerModel) -> str:
    """Render the whole explorer as one self-contained HTML document.

    Parameters
    ----------
    model : ExplorerModel
        The view model, from :func:`afbstepomop.explorer.model.build_model`.

    Returns
    -------
    str
        A complete HTML document with no external references, safe to open
        from a file path or serve as a static page.
    """
    positions = _positions(model)
    tables = model.in_scope_tables
    items = sum(len(t.minimal_items) for t in tables)
    unplaced = sum(1 for g in model.checklist for i in g.items if i.concept is None)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFBSTEP-OMOP minimal data set</title>
<style>{STYLE}</style>
</head>
<body>
<header>
  <h1>AFBSTEP-OMOP minimal data set</h1>
  <span class="sub">OMOP CDM {_escape(model.cdm_version)} · {len(tables)} tables ·
    {items} items placed</span>
  <span class="spacer"></span>
  <div class="legend">
    <span><i class="key" style="background:var(--mandatory-bg);border:2px solid var(--mandatory)"></i>mandatory</span>
    <span><i class="key" style="background:var(--expected-bg);border:1.5px solid var(--expected)"></i>expected</span>
    <span><i class="key" style="background:var(--optional-bg);border:1.5px solid var(--optional)"></i>optional</span>
  </div>
  <input type="search" id="filter" placeholder="Filter tables" aria-label="Filter tables">
  <button id="show-unplaced">Not yet placed ({unplaced})</button>
</header>
<main>
  <div id="graph">
    <svg viewBox="{_viewbox(model, positions)}" role="img"
         aria-label="Foreign-key network of the AFBSTEP tables">
      <g>{_edges_svg(model, positions)}</g>
      <g>{_nodes_svg(model, positions)}</g>
    </svg>
  </div>
  <aside>
    <section id="intro">
      <h2>Pick a table</h2>
      <p class="rationale">Each box is a table a partner populates; each line is a foreign key
      between two of them. Select one to see the fields it asks for and the minimal-data-set
      items recorded in it. The number on a box is how many of those items it carries.</p>
      <h3>What this shows</h3>
      <p class="rationale">The minimal data set only — the fields and concepts AFBSTEP asks for,
      not everything OMOP CDM {_escape(model.cdm_version)} would accept. Tables outside the
      project's scope are not drawn.</p>
    </section>
    {_panels(model)}
  </aside>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""
