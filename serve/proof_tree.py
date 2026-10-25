"""The proof tree of one check (issue #2651, layer 1): goals, then the checks under each goal, then the evidence.

`build(verdict, companion=None, requirements_text=None, ...)` gives the tree as JSON; `render_html(tree)` gives one
self-contained static HTML page. Deterministic and standard library only: no model, no network, nothing written anew.

Every state is the verdict's own:
- a check that is a requirement row reads the row's `state` (holds, disproven, not_established);
- a check that is an obligation reading no requirement row names reads `disproven` when the job summary lists it as a
  disproof (`render.red_findings`), `holds` when its status is `holds` on a machine that was read, and
  `not_established` otherwise: the sets the pull request comment decides from (`render.pr_reading`);
- a goal's roll-up is the job summary's (`declare_proposal.rollup`, issue #1186) over its children's requirement
  states (`rollup`, its copy, when no drafter module is given: the server's kept goal map). Without goals (no companion
  or no drafter module, and no goals given) each requirement row stands as its own goal with the row's state and no
  roll-up of its own;
- every count is a count of those nodes.

The words are render.py's: the requirement's sentence, the profile's plain words (`obligation_words`: short name,
plain_checked, the fix filled from the witness), the plain sentence for each reason class, the checker's own reason,
its witness and the row's establishing action. The one link kind is a file:line at the commit's blob on GitHub, built
by `render.blob_url` from validated parts only.

The page (`render_html`) follows render.py's contract: words only (no tick, cross or coloured symbol), every string
escaped, no script, no external font, stylesheet or image. Everything is collapsed to the goals; each goal opens to
its checks and each check to its evidence (`<details>`). Light and dark colours follow the reader's setting.
The page shows and does not justify (the Director, 16 Oct 2026; the Born brief): its colours and type are custom
properties in the one block that opens the stylesheet (light, then dark), one accent for links and controls only,
and the three state words in restrained colour, never filled badges. The register is the approved one (one column of
about 520px, serif headings, hairlines). A goal or check that does not hold opens by default; Expand all and Collapse
are links to the page's own fragments: Expand all shows every node's content (`::details-content`, no script), Collapse
returns the page to its default (a node opened by hand stays open; with no script the page cannot close it).

Layer 2 (Premium, `formal_model`; the Director's design of 14 and 16 Oct 2026): the formal model, built on remodel,
dated and drift-watched. Its inputs are given, never fetched: `tier` (the account's tier name), `model` (the shadow
model `runner/tools/codeauth/maintain.construct` returns under `model`: its `repo_digests`, the file digests it was
built from, its `read_set`, and `verified_utc`, its build time, or `built_at`), `repository_files` (this run's
raw/REPOSITORY.json, or its {path: sha256} map), `budget` ({allowance_usd, overage_usd, spent_usd}: the plan's
allowance, the customer's overage budget and what is spent), `remodel_quote_usd` (the modelled cost of a remodel) and
`remodel_parts` ([{id, usd}]: the cost per model part, in the order a remodel covers them). A caller that names no
tier gets no layer 2 and the layer-1 page unchanged; a tier without the formal model (`FORMAL_MODEL_TIERS`) or no
model gets one line. The free tier's line links `upgrade_url` (the server's Premium payment link with the account's
`client_reference_id`, serve/api.py `upgrade_for`) when it is a buy.stripe.com link (`render._UPGRADE_URL`, the one
test the PR comment applies); no link otherwise. The model's pinned digests are compared with this run's as `maintain.recheck` compares them: a
path added, removed or changed counts only when it is inside the model's read set (`_in_read_set`, the checker's
rule); none is "current", any is "drifted", and no file list for this run or no read set in the model is "unknown"
(drift is not claimed either way). A drifted model offers the remodel as the API call (`REMODEL_ROUTE`, served since issue #6055), with
its cost against the remaining budget; a remodel that does not fit names the parts it cannot cover (when costs per
part are given) and quotes the extension. The page never acts: nothing runs or is charged until the person makes the
call.

execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false."""
from __future__ import annotations

import html
import math
import re

from . import FLAGS, render

SCHEMA = 'assure.proof-tree/v1'
STATES = ('holds', 'not_established', 'disproven')
STATE_WORDS = {'holds': 'holds', 'not_established': 'not established', 'disproven': 'disproven'}
MAX_FACTS = 6
MAX_NAMED = 5
GOALS_FROM_ROWS = ('Each requirement row stands as its own goal: the goal sentences of requirements.md were not '
                   'stored with this check, only the typed checks they were sent as.')
# a typed goal row as the Action sends it (declare_proposal.typed_text): '- G1.1 [postgres]: <statement>'
TYPED_GOAL_LINE = re.compile(r'(?m)^- G[1-9][0-9]{0,5}\.[1-9][0-9]{0,5} \[')
LEDE = 'Each goal is a line of requirements.md.'
# PR #2662 round 3 (LOW-3): the lede of a tree whose goals are the requirement rows (GOALS_FROM_ROWS)
LEDE_ROWS = 'Each goal is a requirement row the check read.'
FOOTER = 'Assure'
# Layer 2 (Premium): the tiers whose plan includes the formal model (hosted/tiers.json `formal_heads`; a test holds the
# two equal), the remodel call (issue #1228's on-demand recheck route, so the page and the API agree; served since
# issue #6055, so `route_planned` is false) and the lines a page carries without a model
FORMAL_MODEL_TIERS = ('usd_20', 'usd_200', 'usage', 'enterprise')
REMODEL_ROUTE = 'POST /v1/premium/recheck'
UPGRADE_LINE = 'Premium builds the formal model when you upgrade.'
NOT_BUILT_LINE = 'Your formal model is being built; it shows here when it is ready.'
UPGRADE_LINK_WORDS = 'Upgrade to Premium'
MAX_CHANGED = 50
_BUILT = re.compile(r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})?)?')
_BLOB = re.compile(r'https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}/blob/'
                   r'[0-9a-f]{7,40}/[A-Za-z0-9_./@+-]{1,512}#L[1-9][0-9]{0,6}')


def _text(value):
    """Plain, bounded text (render's clip and format space); None for nothing."""
    if value is None:
        return None
    t = render.format_space(render._clip(value)).strip()
    return t or None


def _named(values, cap=MAX_NAMED):
    vals = [v for v in dict.fromkeys(_text(v) for v in values) if v]
    if not vals:
        return None
    more = len(vals) - cap
    return ', '.join(vals[:cap]) + (' and %d more' % more if more > 0 else '')


def _row_state(env, row, disproven, read):
    if (row.get('machine'), row.get('id')) in disproven:
        return 'disproven'
    if row.get('status') == 'holds' and row.get('machine') in read:
        return 'holds'
    return 'not_established'


def _locators(env, req, row, repository, commit):
    return [{'text': loc, 'href': render.blob_url(loc, repository, commit)}
            for loc in render._pr_locators(env, req, row)]


def _evidence_facts(req, row):
    """The facts a check read, from the verdict: the premises, the declaration entry and the gaps a requirement row's
    evidence names, then the checker's own reason for the reading."""
    facts = []
    ev = [e for e in (req.get('evidence') if isinstance(req, dict) else None) or () if isinstance(e, dict)]
    premises = [p.get('premise_id') or p.get('id') for e in ev for p in e.get('premise_pins') or ()
                if isinstance(p, dict)]
    if _named(premises):
        facts.append('premises read: %s' % _named(premises))
    decl = [e.get('policy_declaration') for e in ev if render._scalar(e.get('policy_declaration'))]
    if _named(decl):
        facts.append('declaration entry: %s' % _named(decl))
    gaps = [g for e in ev for g in e.get('gap_ids') or () if render._scalar(g)]
    if _named(gaps):
        facts.append('not visible to the check: %s' % _named(gaps))
    if isinstance(row, dict) and _text(row.get('reason')):
        facts.append('the checker read: %s' % _text(row['reason']))
    return facts[:MAX_FACTS]


def _bound(req):
    ev = [e for e in (req.get('evidence') if isinstance(req, dict) else None) or () if isinstance(e, dict)]
    scopes = [(e.get('native_machine_bounds') or {}).get('scope') for e in ev
              if isinstance(e.get('native_machine_bounds'), dict)]
    return _named(scopes)


def _entry(env, row):
    """The verdict's not-established entry for an obligation row, or {}."""
    for e in env.get('not_established') or ():
        if isinstance(e, dict) and e.get('id') == row.get('id') and e.get('machine') == row.get('machine'):
            return e
    return {}


def _check(env, cid, req, row, state, waypoint, *, repository, commit, source_line=None):
    """One check node: its id, waypoint, state, what was checked and its evidence. `source_line` maps the row's
    `line` (a line of the text the matcher read) to the requirements.md line it came from (`_source_lines`)."""
    row = row if isinstance(row, dict) else {}
    lab, name = render._pr_label(env, req, row)
    node = {'id': _text(cid), 'label': lab, 'waypoint': _text(waypoint) or name or lab, 'state': state,
            'status': row.get('status'), 'obligation': row.get('id'), 'machine': row.get('machine'),
            'plain_checked': render._pr_checked(env, req, row if req is None else None),
            'requirement': None, 'evidence': {}}
    if req is not None:
        line = req.get('line') if type(req.get('line')) is int else None
        node['requirement'] = {'id': _text(req.get('id')),
                               'line': source_line(line, req.get('id')) if source_line is not None and line is not None
                               else line,
                               'sentence': _text(req.get('sentence'))}
        sm = req.get('stored_method')
        if isinstance(sm, dict) and isinstance(sm.get('claim'), str):   # issue #4213: read by the Premium model's method
            node['stored_method'] = {'claim': _text(sm['claim']), 'route': _text(sm.get('route'))}
    ev = {'facts': _evidence_facts(req, row), 'locators': _locators(env, req, row, repository, commit)}
    if state == 'disproven':
        item = render._pr_item(env, ('disproven', row.get('id'), row), *render._pr_requirements(env))
        ev['what'] = _text(item.get('what'))
        ev['witness'] = _text(re.sub(r'^witness(?:es)?: ', '', render.witness_text(env, row) or '')) if row else None
        ev['remedy'] = _text(item.get('fix'))
        ev['locators'] = [{'text': loc, 'href': render.blob_url(loc, repository, commit)}
                          for loc in item.get('locators') or ()] or ev['locators']
    elif state == 'holds':
        ev['bound'] = _bound(req)
    else:
        cls = (req.get('reason_class') if req is not None else None) or render._pr_reason_class(env, row)
        entry = _entry(env, row) if req is None else {}
        ev['reason_class'] = cls
        ev['cause'] = entry.get('reason_class') or cls      # the class the verdict's undecided_by_cause groups by
        ev['reason'] = render._pr_unchecked_words(env, cls)
        ev['action'] = _text(req.get('establishing_action') if req is not None else entry.get('action'))
    node['evidence'] = ev
    return node


def _goal_line(english, requirements_text):
    """The 1-based line of '- <english>' in requirements.md, or None."""
    if not isinstance(requirements_text, str):
        return None
    for n, line in enumerate(requirements_text.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith(('- ', '* ', '+ ')) and stripped[2:].strip() == english:
            return n
    return None


# a list marker as the drafter strips it (declare_proposal._MARKER) and a Markdown heading the matcher never reads
_MARKER = re.compile(r'(?:[-*+]\s+|\d+[.)]\s+)')
_HEADING = re.compile(r'#{1,6}(?:\s|$)')


def _source_lines(requirements_text, goals, typed_stored=False):
    """(map, goal lines). `map(n)` is the requirements.md line that line `n` of the text the matcher read came from,
    or None; `goal lines` is {goal id: its requirements.md line}. PR #2662 round 2 (HIGH-1): with goals sent, the
    matcher read the typed text (`declare_proposal.typed_text`), where each goal line became its children's rows, so
    its numbering is not requirements.md's. The goal lines are found as typed_text finds them (outside code fences,
    never a heading, list marker stripped, each goal once); a row of a goal names the goal's line, any other line its
    own line less the rows the goals above it added. A goal not found in the text, or goals without the text, name no
    line. `typed_stored` (the API's stored text, which holds typed rows and never requirements.md): no line."""
    if typed_stored:
        return (lambda n, rid=None: None), {}
    if not goals:
        return (lambda n, rid=None: n), {}
    if not isinstance(requirements_text, str):
        return (lambda n, rid=None: None), {}
    by_english = {}
    for g in goals:
        by_english.setdefault(g.get('english'), g)
    spans, fenced, seen = [], False, set()
    for n, line in enumerate(requirements_text.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if fenced or not stripped or _HEADING.match(stripped):
            continue
        marker = _MARKER.match(stripped)
        g = by_english.get(stripped[marker.end():] if marker else stripped)
        if g is not None and id(g) not in seen:
            seen.add(id(g))
            spans.append((n, g))
    if len(spans) != len(goals):
        return (lambda n, rid=None: None), {}
    row_line = {rid: n for n, g in spans for rid, _s, _w in g['rows']}

    def source(t, rid=None):
        if rid in row_line:                  # a goal's row: the goal's line, when the numbering agrees
            return row_line[rid] if _span_of(t) == row_line[rid] else None
        n = _span_of(t)
        return None if n in row_line.values() else n

    def _span_of(t):
        shift = 0
        for n, g in spans:
            start = n + shift
            if t < start:
                break
            if t < start + len(g['rows']):
                return n
            shift += len(g['rows']) - 1
        return t - shift if 0 < t - shift <= requirements_text.count('\n') + 1 else None
    return source, {g.get('id'): n for n, g in spans}


def _kept_lines(typed_text, goals):
    """`_source_lines` for the server's kept goal map (`goals_of`) and the typed text it stored. Each goal names the
    requirements.md line the map carries (`goal_map` takes it from requirements.md as read, or None). Each goal's
    rows sit as one run of typed rows (`- G1.1 [`...) in the stored text: a goal's row names its goal's line, and any
    other row its own line less the rows the goals above it added. A goal whose rows are not one run in the text, or
    no text, leaves every row without a line."""
    goal_lines = {g.get('id'): g.get('line') for g in goals if type(g.get('line')) is int and g.get('line') > 0}
    none = (lambda n, rid=None: None), goal_lines
    if not isinstance(typed_text, str) or not goals:
        return none
    lines = typed_text.split('\n')
    first = {}
    for n, line in enumerate(lines, 1):
        m = re.match(r'- (G[1-9][0-9]{0,5}\.[1-9][0-9]{0,5}) \[', line)
        if m:
            first.setdefault(m.group(1), n)
    spans, row_goal = [], {}
    for g in goals:
        ids = [rid for rid, _s, _w in g['rows']]
        at = [first.get(rid) for rid in ids]
        if not ids or None in at or at != list(range(at[0], at[0] + len(ids))):
            return none
        spans.append((at[0], len(ids), g))
        row_goal.update((rid, (at[0], len(ids), g)) for rid in ids)
    spans.sort(key=lambda s: s[0])
    last = len(lines) - sum(k - 1 for _a, k, _g in spans)

    def source(t, rid=None):
        if rid in row_goal:
            a, k, g = row_goal[rid]
            return goal_lines.get(g.get('id')) if a <= t < a + k else None
        if any(a <= t < a + k for a, k, _g in spans):
            return None
        s = t - sum(k - 1 for a, k, _g in spans if a + k <= t)
        return s if 0 < s <= last else None
    return source, goal_lines


def _goal_state(states):
    if 'disproven' in states:
        return 'disproven'
    return 'holds' if states and all(s == 'holds' for s in states) else 'not_established'


def build(verdict, companion=None, requirements_text=None, *, proposal=None, goals=None, repository=None,
          commit=None, goals_unstored=False, goals_kept=False, tier=None, model=None, repository_files=None,
          budget=None, remodel_quote_usd=None, remodel_parts=None, upgrade_url=None):
    """The proof tree of `verdict` (module docstring) as a JSON-ready dict:
    {schema, header, counts, goals, checks, other_checks, not_decided, no_reading, note}.

    `companion` (assure-requirements-typed.json) with `requirements_text` (the requirements.md the check sent) and
    `proposal` (the drafter module: action/declare_proposal.py in the Action, assure/declare_proposal.py here) give
    the goals (`proposal.typed_text`); `goals`, the expanded goals the Action already holds (or the server's kept goal
    map, `goals_of`, rolled up by `rollup`), may stand in for them.
    `repository` ('owner/name') and `commit` make the blob links; each is validated before it is used.
    `goals_unstored` (the API's stored check, whose requirements text holds typed goal rows and not the sentences
    they came from) adds the note that each requirement row stands as its own goal. `goals_kept` (the server's kept
    goal map, `goals_of`): each goal node names the line the map carries, which `goal_map` takes from requirements.md
    as read and never from the companion or the typed text; its rows name no requirements.md line (`_source_lines`:
    goals without the text they came from).
    `tier`, `model`, `repository_files`, `budget`, `remodel_quote_usd`, `remodel_parts` and `upgrade_url` give layer 2,
    `formal_model` (`formal_model`, module docstring); without `tier` it is None."""
    env = verdict if isinstance(verdict, dict) else {}
    reading = render.pr_reading(env)
    rows = [r for r in render._obligation_rows(env) if not render.is_machine_refusal(r)]
    read = render._read_set(env)
    disproven = {(r.get('machine'), r.get('id')) for kind, _, r in render.red_findings(env)
                 if kind == 'disproven' and isinstance(r, dict)}
    by_id, by_ob = render._pr_requirements(env)
    reqs = [r for r in render.requirement_rows(env) or () if isinstance(r, dict)]
    if goals is None and proposal is not None and companion is not None and isinstance(requirements_text, str):
        try:
            goals = proposal.typed_text(requirements_text, companion)[2]
        except Exception:                    # a companion that does not check changes nothing
            goals = None
    goals = [g for g in goals or () if isinstance(g, dict) and isinstance(g.get('rows'), list)]
    waypoints = {rid: w for g in goals for rid, _s, w in g['rows']}
    source_line, goal_lines = (_kept_lines(requirements_text, goals) if goals_kept
                               else _source_lines(requirements_text, goals, goals_unstored))

    checks, matched = [], set()
    for req in reqs:
        ms = [m for m in req.get('matched_obligations') or () if isinstance(m, dict)]
        row = next((r for r in rows if any(r.get('machine') == m.get('machine') and r.get('id') == m.get('id')
                                           for m in ms)), None)
        matched.update((m.get('machine'), m.get('id')) for m in ms)
        state = req.get('state') if req.get('state') in STATES else 'not_established'
        words = render._pr_words(env, row.get('id'), 'short_name') if row else None
        checks.append(_check(env, req.get('id'), req, row, state,
                             waypoints.get(req.get('id')) or words or req.get('sentence'),
                             repository=repository, commit=commit, source_line=source_line))
    others = []
    for r in rows:
        key = (r.get('machine'), r.get('id'))
        if key in matched or (r.get('machine') not in read and not render.kept_on_refused(env, r)):
            continue
        cid = render._pr_obligation_text(env, r)
        name = render._pr_words(env, r.get('id'), 'short_name') or render._pr_phrase(env, r.get('id')) or cid
        others.append(_check(env, cid, None, r, _row_state(env, r, disproven, read), name,
                             repository=repository, commit=commit))

    states = {c['id']: c['state'] for c in checks}
    out_goals = []
    if goals:
        roll = proposal.rollup if proposal is not None else rollup
        for g in goals:
            ids = [rid for rid, _s, _w in g['rows']]
            out_goals.append({'id': _text(g.get('id')), 'sentence': _text(g.get('english')),
                              'line': goal_lines.get(g.get('id')) or (None if goals_kept else
                                                                       _goal_line(g.get('english'), requirements_text)),
                              'rollup': _text(roll(g, {r.get('id'): r.get('state') for r in reqs})),
                              'state': _goal_state([states.get(i) for i in ids if i in states]),
                              'checks': [i for i in ids if i in states]})
        grouped = {i for g in out_goals for i in g['checks']}
        for c in checks:                     # a row no goal names stands as its own goal
            if c['id'] not in grouped:
                out_goals.append(_row_goal(c))
        note = None
    else:
        out_goals = [_row_goal(c) for c in checks]
        note = GOALS_FROM_ROWS if (companion is not None or goals or goals_unstored) and checks else None

    every = checks + others
    counts = {s: sum(1 for c in every if c['state'] == s) for s in STATES}
    counts['checks'] = len(every)
    not_decided = {}
    for c in every:
        if c['state'] != 'not_established':
            continue
        g = not_decided.setdefault(c['evidence']['reason'], {'reason': c['evidence']['reason'], 'checks': []})
        g['checks'].append({'id': c['id'], 'waypoint': c['waypoint'], 'action': c['evidence']['action'],
                            'cause': c['evidence']['cause']})
    for g in not_decided.values():
        # the action every check of the group shares; else the verdict's own action for the class most of them are in
        # (`undecided_by_cause`), each check keeping its own action beside it
        actions = [x['action'] for x in g['checks']]
        g['action'] = actions[0] if all(a == actions[0] for a in actions) else None
        if g['action'] is None:
            causes = [x['cause'] for x in g['checks']]
            top = max(dict.fromkeys(causes), key=causes.count)
            g['action'] = next((_text(u.get('action')) for u in env.get('undecided_by_cause') or ()
                                if isinstance(u, dict) and u.get('class') == top), None)
    header = _header(env, repository, commit)
    layer2 = formal_model(tier, model, repository_files, budget=budget, remodel_quote_usd=remodel_quote_usd,
                          remodel_parts=remodel_parts, checks=checks, upgrade_url=upgrade_url,
                          obligation_words={k: render._pr_words(env, k, 'short_name')
                                            for k in env.get('obligation_words') or ()
                                            if isinstance(env.get('obligation_words'), dict)})
    return {'schema': SCHEMA, 'check_id': header['check_id'],
            'header': header, 'counts': counts, 'goals': out_goals, 'checks': checks,
            'other_checks': others, 'formal_model': layer2,
            'not_decided': sorted(not_decided.values(), key=lambda g: (-len(g['checks']), g['reason'])),
            'no_reading': reading['no_reading'], 'note': note, **FLAGS}

# ---------- layer 2: the formal model (Premium) ----------
def _usd(value):
    """A finite, non-negative dollar amount as a float, or None."""
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _cents(value):
    return None if value is None else round(value + 0.0, 2)


def _up_to_cent(value):
    return math.ceil(round(value * 100, 6)) / 100


def _digests(value):
    """{path: sha256} from a REPOSITORY.json dict ({files: [{path, sha256}]}) or a digest map; None when it is
    neither."""
    if isinstance(value, dict) and isinstance(value.get('files'), list):
        out = {}
        for f in value['files']:
            if not (isinstance(f, dict) and isinstance(f.get('path'), str)):
                return None
            out[f['path']] = f.get('sha256')
        return out
    if isinstance(value, dict) and all(isinstance(k, str) and (v is None or isinstance(v, str))
                                       for k, v in value.items()):
        return dict(value)
    return None


_READ_SET_LISTS = ('files', 'roots', 'root_suffixes', 'probe_dirs', 'probe_names', 'compiled_suffixes',
                   'template_dirs', 'template_suffixes', 'loaded')


def _read_set_body(value):
    """The model's read set body (`readset._body`: the wrapper record's `read_set`, else the body itself), or None
    when it is not one: every list the membership rule reads, when present, is a list of strings."""
    rs = value.get('read_set') if isinstance(value, dict) and isinstance(value.get('read_set'), dict) else value
    if not isinstance(rs, dict) or not rs:
        return None
    for k in _READ_SET_LISTS:
        if k in rs and not (isinstance(rs[k], list) and all(isinstance(x, str) for x in rs[k])):
            return None
    return rs


def _under(path, roots):
    return any(path == r or path.startswith(r.rstrip('/') + '/') for r in roots)


def _probe_hit(rs, path):
    dirs, names, compiled = rs.get('probe_dirs', []), rs.get('probe_names', []), rs.get('compiled_suffixes', [])
    d, _s, base = path.rpartition('/')
    if base == '__init__.py':
        d2, _s, name = d.rpartition('/')
        return d2 in dirs and name in names
    stem, dot, _rest = base.partition('.')
    return bool(dot) and d in dirs and stem in names and (base == stem + '.py' or base.rsplit('.', 1)[-1] in compiled)


def _in_read_set(read_set, path):
    """`readset.in_read_set` of the python-auth checker (the rule `maintain.recheck` decides relevance by), copied
    because the page is standard library only; a test holds the two equal. A listed file; under an app root with a
    root suffix; a shadow probe; a file under a template directory; or a loaded path."""
    rs = _read_set_body(read_set) or {}
    return (path in rs.get('files', [])
            or (_under(path, rs.get('roots', [])) and path.endswith(tuple(rs.get('root_suffixes', []))))
            or _probe_hit(rs, path)
            or any(path.startswith(d) and path.endswith(tuple(rs.get('template_suffixes', ['']))) for d in
                   rs.get('template_dirs', []))
            or path in rs.get('loaded', []))


def _budget(budget):
    """{allowance_usd, overage_usd, spent_usd, remaining_usd} with each a valid amount, or None when any is not;
    remaining is the allowance plus the overage budget less what is spent, never below zero."""
    b = budget if isinstance(budget, dict) else {}
    vals = {k: _usd(b.get(k)) for k in ('allowance_usd', 'overage_usd', 'spent_usd')}
    if None in vals.values():
        return None
    vals['remaining_usd'] = _cents(max(0.0, vals['allowance_usd'] + vals['overage_usd'] - vals['spent_usd']))
    return {k: _cents(v) for k, v in vals.items()}


def _remodel(budget, quote_usd, parts, words):
    """The Remodel control's facts: the planned call, the cost, the remaining budget, whether the remodel fits and,
    when it does not, the parts it cannot cover (from the costs per part, covered in their order while the remaining
    budget lasts) and the extension that covers it (rounded up to the cent). The page never acts on it."""
    b = _budget(budget)
    q = _usd(quote_usd)
    out = {'route': REMODEL_ROUTE, 'route_planned': False, 'quote_usd': _cents(q), 'allowance_usd': None, 'overage_usd': None,
           'spent_usd': None, 'remaining_usd': None, 'fits': None, 'uncovered': [], 'extend_usd': None}
    if b is not None:
        out.update(b)
    if q is None or b is None:
        return out
    out['fits'] = q <= b['remaining_usd'] + 1e-9
    if out['fits']:
        return out
    out['extend_usd'] = _up_to_cent(q - b['remaining_usd'])
    left, covering = b['remaining_usd'], True
    for part in parts if isinstance(parts, list) else ():
        cost = _usd(part.get('usd')) if isinstance(part, dict) else None
        pid = _text(part.get('id')) if isinstance(part, dict) and isinstance(part.get('id'), str) else None
        if cost is None or pid is None:
            out['uncovered'] = []           # a malformed list names nothing
            break
        if covering and cost <= left + 1e-9:
            left -= cost
            continue
        covering = False
        out['uncovered'].append({'id': pid, 'words': words.get(pid) or pid, 'usd': _cents(cost)})
    return out


def _drift(m, repository_files):
    """(state, changed paths) of a model against this run's files (module docstring: `maintain.recheck`'s rule), or
    None for a model without its pinned digests."""
    pinned = _digests(m.get('repo_digests'))
    if not pinned:
        return None
    current = _digests(repository_files)
    read_set = _read_set_body(m.get('read_set'))
    if current is None or read_set is None:
        return 'unknown', []
    changed = [p for p in sorted(set(pinned) | set(current)) if pinned.get(p) != current.get(p)   # maintain.recheck
               and _in_read_set(read_set, p)]
    return ('drifted' if changed else 'current'), changed


def drift(model, repository_files=None):
    """Issue #6055: 'current', 'drifted' or 'unknown' for a saved model against this run's files (as layer 2 reads
    it), or None for no model (or one without its pinned digests): the API's refresh route and the verdict's
    `model_refresh` read the same state the page shows."""
    found = _drift(model, repository_files) if isinstance(model, dict) else None
    return None if found is None else found[0]


def formal_model(tier, model, repository_files=None, *, budget=None, remodel_quote_usd=None, remodel_parts=None,
                 checks=(), obligation_words=None, upgrade_url=None):
    """Layer 2 of the tree (module docstring), or None when no tier is named. A tier without the formal model:
    {state: 'upgrade', line}. No model (or one without its pinned digests): {state: 'not_built', line}. Otherwise
    {state: current | drifted | unknown, model_id, built_at, model_commit, scope, changed_files, changed_count,
    branches, remodel}: each branch is a requirement row of the model, headed by the customer's words for it (the
    layer-1 check's waypoint, else the requirement sentence) with the model's own state, and opens to `checks`: the
    model's reading of the obligation the row matched ({id, words, state, routes}: the profile's short name for it,
    its state and the routes its reading names; none when the row matched no obligation or the model carries no
    obligation readings). `remodel` only when drifted."""
    if tier is None:
        return None
    if tier not in FORMAL_MODEL_TIERS:
        out = {'state': 'upgrade', 'line': UPGRADE_LINE}
        if isinstance(upgrade_url, str) and render._UPGRADE_URL.fullmatch(upgrade_url):
            out['url'] = upgrade_url
        return out
    m = model if isinstance(model, dict) else {}
    found = _drift(m, repository_files)
    if found is None:
        return {'state': 'not_built', 'line': NOT_BUILT_LINE}
    state, changed = found
    words, stated = {}, {}
    for c in checks or ():
        if isinstance(c, dict) and c.get('id'):
            words[c['id']] = c.get('waypoint') or (c.get('requirement') or {}).get('sentence')
            if isinstance(c.get('stored_method'), dict) and c['stored_method'].get('claim'):
                stated[c['id']] = c
    branches = []
    readings = m.get('readings') if isinstance(m.get('readings'), dict) else {}
    obs = readings.get('obligations') if isinstance(readings.get('obligations'), dict) else {}
    ob_words = obligation_words if isinstance(obligation_words, dict) else {}
    for row in readings.get('rows') or ():
        if not (isinstance(row, (list, tuple)) and len(row) >= 4 and isinstance(row[0], str)):
            continue
        rid, line = _text(row[0]), row[1] if type(row[1]) is int and row[1] > 0 else None
        fallback = 'requirement line %d' % line if line is not None else 'a requirement row'
        kids = []
        oid, ob = row[2], obs.get(row[2]) if isinstance(row[2], str) else None
        if isinstance(ob, (list, tuple)) and len(ob) >= 3:
            kids.append({'id': _text(oid), 'words': _text(ob_words.get(oid)) or 'the check of this line',
                         'state': ob[0] if ob[0] in STATES else 'not_established',
                         'routes': [_text(r) for r in ob[2] if isinstance(r, str)] if isinstance(ob[2], list) else []})
        bstate = row[3] if row[3] in STATES else 'not_established'
        c = stated.get(rid)
        if c is not None:                    # issue #4213: this check read the model's stated method for the row
            bstate = c['state'] if c.get('state') in STATES else 'not_established'
            kids = [{'id': 'stated-method', 'words': c['stored_method']['claim'], 'state': bstate,
                     'routes': [c['stored_method']['route']] if c['stored_method'].get('route') else []}]
        branches.append({'id': rid, 'words': _text(words.get(rid)) or fallback, 'line': line,
                         'state': bstate, 'checks': kids})
    built = m.get('built_at') if isinstance(m.get('built_at'), str) else m.get('verified_utc')
    commit = m.get('commit') if isinstance(m.get('commit'), str) and render._PR_COMMIT.fullmatch(m['commit']) \
        else None
    out = {'state': state, 'model_id': _text(m.get('model_id')) if isinstance(m.get('model_id'), str) else None,
           'built_at': built if isinstance(built, str) and _BUILT.fullmatch(built) else None,
           'model_commit': commit,
           'scope': [_text(x) for x in m.get('scope') or () if isinstance(x, str) and _text(x)]
           if isinstance(m.get('scope'), list) else [],
           'changed_files': [_text(p) or '' for p in changed], 'changed_count': len(changed),
           'branches': branches, 'remodel': None}
    if state == 'drifted':
        out['remodel'] = _remodel(budget, remodel_quote_usd, remodel_parts, words)
    return out


def rollup(goal, states):
    """One goal's reading from its children's requirement states: `declare_proposal.rollup`, word for word, for the
    server, which holds no drafter module (a test holds the two equal)."""
    broken = [waypoint for rid, _statement, waypoint in goal['rows'] if states.get(rid) == 'disproven']
    if broken:
        return 'broken: ' + ' '.join(broken)
    held = sum(1 for rid, _statement, _w in goal['rows'] if states.get(rid) == 'holds')
    total = len(goal['rows'])
    return 'holds for %d of %d checks' % (held, total) + ('; %d not decided yet' % (total - held) if held < total else '')


def goal_map(goals, requirements_text=None):
    """The goal map the Action sends beside the typed requirements (`requirement_goals`) and the server keeps with the
    check: for each goal sent (`declare_proposal.typed_text`), {id, english, line, rows: [[child id, waypoint]]}. The
    line is the goal's line in `requirements_text` (the requirements.md as read), else None; the typed
    statements and every provenance stay out. [] for no goals."""
    out = []
    # PR #2662 round 2: the line is requirements.md's own (as `build` finds it), or None: never the companion's
    # compiled line, which an edit may have moved
    lines = _source_lines(requirements_text, [g for g in goals or () if isinstance(g, dict)
                                              and isinstance(g.get('rows'), list)])[1]
    for g in goals or ():
        if not (isinstance(g, dict) and isinstance(g.get('rows'), list)):
            continue
        line = lines.get(g.get('id')) or _goal_line(g.get('english'), requirements_text)
        out.append({'id': g.get('id'), 'english': g.get('english'), 'line': line if type(line) is int else None,
                    'rows': [[rid, waypoint] for rid, _statement, waypoint in g['rows']]})
    return out


def goals_of(goal_map_value):
    """`build`'s goals ({id, english, line, rows: [(id, None, waypoint)]}) from a kept goal map (`goal_map`), or None
    when it is not one (anything malformed reads as no goals)."""
    if not isinstance(goal_map_value, list) or not goal_map_value:
        return None
    out = []
    for g in goal_map_value:
        try:
            rows = [(rid, None, w) for rid, w in g['rows']]
            if not (isinstance(g['id'], str) and isinstance(g['english'], str) and rows
                    and all(isinstance(r, str) and isinstance(w, str) for r, _s, w in rows)
                    and (g['line'] is None or type(g['line']) is int)):
                return None
        except (KeyError, TypeError, ValueError):
            return None
        out.append({'id': g['id'], 'english': g['english'], 'line': g['line'], 'rows': rows})
    return out


def _row_goal(check):
    return {'id': check['id'], 'sentence': (check['requirement'] or {}).get('sentence') or check['waypoint'],
            'line': (check['requirement'] or {}).get('line'), 'rollup': None,
            'state': check['state'], 'checks': [check['id']]}


def _header(env, repository, commit):
    engine = env.get('engine') if isinstance(env.get('engine'), dict) else {}
    m = render._machines(env)
    refused = [{'machine': _text(r.get('machine')), 'reason': _text(r.get('reason'))}
               for r in (m['refused'] if m else ()) if isinstance(r, dict)]
    repo_ok = render.blob_url('a:1', repository, commit or '0000000') is not None
    return {'profile': _text(env.get('profile')) if isinstance(env.get('profile'), str) else None,
            'check_id': env.get('check_id') if isinstance(env.get('check_id'), str)
            and re.fullmatch(r'[0-9a-f]{32}', env['check_id']) else None,
            'repository': repository if repo_ok else None,
            'commit': commit if isinstance(commit, str) and render._PR_COMMIT.fullmatch(commit) else None,
            'engine': {'commit': _text(engine.get('commit')), 'release': _text(engine.get('release_sha256'))},
            'first_checked_at': _text(env.get('first_checked_at')),
            'colour': env.get('colour') if env.get('colour') in render.COLOURS else None,
            'verdict_line': _text(render.verdict_line(env) or render.first_line(env)),
            'bounds': render._bounds_words(env), 'machines': _text(render.first_line(env)),
            'machines_refused': refused, 'read': _text(render._pr_closing(env, commit).replace('`', ''))}


# ---------- the page ----------
CSS = """:root{--bg:#fbfaf8;--ink:#1d1c1a;--muted:#7a746b;--faint:#b3ada3;--line:#ebe7e0;--code-bg:#efece6;
--accent:#2f5d8a;--holds:#6f7d63;--ne:#8a7650;--dis:#9b3b34;
--font-text:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,"Helvetica Neue",Arial,sans-serif;
--font-display:ui-serif,"New York",Georgia,"Times New Roman",serif;
--font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--measure:520px;--size-body:15px;--size-title:34px;--size-root:22px;--size-h2:19px;--size-small:13.5px;
--size-label:12.5px;--size-code:12px;--size-body-sm:15px;--size-title-sm:29px}
@media (prefers-color-scheme: dark){:root{--bg:#141412;--ink:#ece9e3;--muted:#9c968c;--faint:#5f5a53;--line:#2a2825;
--code-bg:#26241f;--accent:#8fb4dc;--holds:#a3b296;--ne:#c9b07e;--dis:#e0918a}}
*{box-sizing:border-box}html,body{margin:0}
body{overflow-wrap:anywhere;background-color:var(--bg);color:var(--ink);font-family:var(--font-text);
font-size:var(--size-body);line-height:1.65;-webkit-font-smoothing:antialiased}
main{max-width:var(--measure);margin:0 auto;padding:56px 16px 72px}
h1{font-family:var(--font-display);font-size:var(--size-title);line-height:1.2;margin:0 0 12px;font-weight:300}
.lede{color:var(--muted);margin:0}
.legend{display:flex;gap:20px;flex-wrap:wrap;margin:18px 0 0}.legend .w{min-width:0}
.tools{display:flex;gap:18px;margin:28px 0 0;font-size:var(--size-label)}
.tools a{color:var(--muted)}.tools a:hover{color:var(--accent);text-decoration:none}
header{margin-bottom:56px}
section{border-top:1px solid var(--line);padding:32px 0 0;margin-bottom:48px}
section h2{font-family:var(--font-display);font-size:var(--size-h2);font-weight:400;margin:0 0 20px}
.root .t{font-family:var(--font-display);font-size:var(--size-root);font-weight:300;line-height:1.3}
.sum{color:var(--muted);margin:6px 0 0;font-size:var(--size-small)}
.row{display:flex;align-items:baseline;column-gap:16px;flex-wrap:wrap}
.row .t{flex:1 1 60%;order:1}.row .w{order:2;margin-left:auto}.row .tag{order:3;flex-basis:100%}
.w{flex:none;font-size:var(--size-small);white-space:nowrap}
.w-holds{color:var(--holds)}.w-not_established{color:var(--ne)}.w-disproven{color:var(--dis)}
.t{overflow-wrap:anywhere;min-width:0}
.tag{color:var(--faint);font-family:var(--font-mono);font-size:var(--size-label)}
.roll{color:var(--muted);font-size:var(--size-small)}
ul{list-style:none;margin:0;padding:0}
ul.tree{margin:12px 0 0}
ul.tree>li{padding:12px 0;border-top:1px solid var(--line)}ul.tree>li:first-child{border-top:0}
ul.tree ul.tree{margin:4px 0 8px 3px;padding-left:16px;border-left:1px solid var(--line)}
ul.tree ul.tree>li{padding:9px 0;font-size:var(--size-small)}
details>summary{cursor:pointer;list-style:none;position:relative;padding-left:18px}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:'';position:absolute;left:0;top:.62em;width:6px;height:6px;
border-right:1px solid var(--faint);border-bottom:1px solid var(--faint);transform:rotate(-45deg)}
details[open]>summary::before{transform:rotate(45deg)}
details>summary:hover .t,details>summary:hover .roll{color:var(--accent)}
details>summary:focus-visible{outline:1px solid var(--accent);outline-offset:4px}
details[open]>summary{margin-bottom:6px}
main:has(#expand-all:target) details::details-content{content-visibility:visible}
main:has(#expand-all:target) details>summary::before{transform:rotate(45deg)}
ul.ev{margin:4px 0 4px 18px;padding-left:16px;border-left:1px solid var(--line);color:var(--muted);
font-size:var(--size-small)}ul.ev li{padding:3px 0}
ul.ev b{color:var(--ink);font-weight:500}
li.n-disproven>details>summary .t,li.n-disproven>.row .t{color:var(--ink)}
code{font-family:var(--font-mono);font-size:var(--size-code);background-color:var(--code-bg);color:var(--ink);
padding:1px 6px;border-radius:3px;overflow-wrap:anywhere}
a{color:var(--accent);text-decoration:none}a code{color:var(--accent)}a:hover{text-decoration:underline;text-underline-offset:3px}
a:focus-visible{outline:1px solid var(--accent);outline-offset:3px}
q{color:var(--ink)}
.note{color:var(--muted);font-size:var(--size-small);margin:20px 0 0}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 20px;margin:0;font-size:var(--size-small)}
dl.facts dt{color:var(--muted)}dl.facts dd{margin:0;overflow-wrap:anywhere}
footer{color:var(--faint);font-size:var(--size-label);padding-top:20px;border-top:1px solid var(--line)}
.l2-drifted ul.tree{opacity:.55}
.remodel{border-top:1px solid var(--line);margin-top:24px;padding-top:18px;font-size:var(--size-small)}
.remodel p{margin:0 0 10px}
@media (max-width:720px){body{font-size:var(--size-body-sm)}h1{font-size:var(--size-title-sm)}
main{padding:36px 16px 56px}header{margin-bottom:44px}dl.facts{grid-template-columns:1fr}dl.facts dd{margin-bottom:6px}}"""
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'"


def _e(value):
    return html.escape('' if value is None else str(value), quote=True)


def _pill(state):
    state = state if state in STATES else 'not_established'
    return '<span class="w w-%s">%s</span>' % (state, _e(STATE_WORDS[state]))


def _loc(loc):
    text = '<code>%s</code>' % _e(loc.get('text'))
    href = loc.get('href')
    if isinstance(href, str) and _BLOB.fullmatch(href):
        return '<a href="%s">%s</a>' % (_e(href), text)
    return text


def _evidence_html(c):
    ev, items = c.get('evidence') or {}, []
    req = c.get('requirement')
    if c['state'] == 'disproven':
        if ev.get('what'):
            items.append('<b>What the change does:</b> %s' % _e(ev['what']))
        if ev.get('witness'):
            items.append('<b>Counterexample:</b> %s' % _e(ev['witness']))
    elif c.get('plain_checked') and c['state'] == 'holds':
        items.append('<b>What was checked:</b> %s' % _e(c['plain_checked']))
    if ev.get('locators'):
        items.append('at %s' % ', '.join(_loc(x) for x in ev['locators']))
    for f in ev.get('facts') or ():
        items.append(_e(f))
    if ev.get('bound'):
        items.append('holds within: %s' % _e(ev['bound']))
    if c['state'] == 'not_established':
        items.append('<b>Not decided:</b> %s' % _e(ev.get('reason')))
        if ev.get('action'):
            items.append('<b>Next:</b> %s' % _e(ev['action']))
    if req and req.get('sentence'):
        where = 'requirement %s%s' % (_e(req.get('id')), ', <code>requirements.md:%d</code>' % req['line']
                                      if type(req.get('line')) is int else '')
        items.append('%s: <q>%s</q>' % (where, _e(req['sentence'])))
    if c['state'] == 'disproven' and ev.get('remedy'):
        items.append('<b>Fix:</b> %s' % _e(ev['remedy']))
    return '<ul class="ev">%s</ul>' % ''.join('<li>%s</li>' % i for i in items)


def _open(state):
    """A node that does not hold opens by default (the Director, 16 Oct 2026)."""
    return '<details open>' if state == 'disproven' else '<details>'


def _check_html(c):
    return ('<li class="n n-%s">%s<summary><div class="row">%s<span class="t">%s</span><span class="tag">%s'
            '</span></div></summary>%s</details></li>' % (c['state'], _open(c['state']), _pill(c['state']),
                                                         _e(c['waypoint']),
                                                         _e(c['id']), _evidence_html(c)))


def _sum(counts):
    return ('%d hold &middot; %d not established &middot; %d disproven &middot; %d checks'
            % (counts['holds'], counts['not_established'], counts['disproven'], counts['checks']))


def _money(value):
    return '$%.2f' % value


def _plural(n, one, many):
    return '%d %s' % (n, one if n == 1 else many)


def _branch_html(b):
    """One part of the model: its row, opening to the model's reading of the check that reads it (when it has one)."""
    row = '<div class="row">%s<span class="t">%s</span><span class="tag">%s%s</span></div>' % (
        _pill(b['state']), _e(b['words']), _e(b['id']),
        ' &middot; requirements.md:%d' % b['line'] if type(b.get('line')) is int else '')
    kids = b.get('checks') or []
    if not kids:
        return '<li class="n n-%s">%s</li>' % (b['state'], row)
    items = []
    for k in kids:
        ev = ''
        if k['state'] == 'disproven' and k.get('routes'):
            ev = '<ul class="ev"><li><b>Counterexample:</b> %s</li></ul>' % ', '.join(
                '<code>%s</code>' % _e(r) for r in k['routes'][:MAX_NAMED])
        items.append('<li class="n n-%s"><div class="row">%s<span class="t">%s</span><span class="tag">%s</span></div>%s'
                     '</li>' % (k['state'], _pill(k['state']), _e(k['words']), _e(k['id']), ev))
    return ('<li class="n n-%s">%s<summary>%s</summary><ul class="tree">%s</ul></details></li>'
            % (b['state'], _open(b['state']), row, ''.join(items)))


def _model_html(fm):
    """Layer 2's section (`formal_model`): one line without a model; else the model's date, whether it is current
    against this run's code, the files changed since it was modelled, its parts and, when it drifted, the Remodel
    control: the planned call with its cost against the remaining budget. Words only; the page never acts."""
    out = ['<section aria-labelledby="s-model">', '<h2 id="s-model">Formal model</h2>']
    if fm.get('state') not in ('current', 'drifted', 'unknown'):
        link = ' <a href="%s" rel="noopener">%s</a>' % (_e(fm['url']), UPGRADE_LINK_WORDS) \
            if fm.get('state') == 'upgrade' and isinstance(fm.get('url'), str) \
            and render._UPGRADE_URL.fullmatch(fm['url']) else ''
        return out + ['<p class="note">%s%s</p>' % (_e(fm.get('line')), link), '</section>']
    out.append('<div class="l2 l2-%s">' % _e(fm['state']))
    when = ' on %s' % _e(fm['built_at'][:10]) if fm.get('built_at') else ''
    at = ' from commit %s' % _e(fm['model_commit'][:7]) if fm.get('model_commit') else ''
    scope = ', covering %s' % _e(', '.join(fm['scope'])) if fm.get('scope') else ''
    if fm['state'] == 'current':
        out.append('<div class="root"><p class="t">Proven against this code</p><p class="sum">Modelled%s%s%s. Every '
                   'file it read is unchanged in this run.</p></div>' % (when, at, scope))
    elif fm['state'] == 'drifted':
        n = fm.get('changed_count') or 0
        out.append('<div class="root"><p class="t">%s since this was modelled</p><p class="sum">Modelled%s%s%s. The '
                   'parts below read the earlier code until it is remodelled.</p></div>'
                   % (_plural(n, 'file changed', 'files changed'), when, at, scope))
        names = fm.get('changed_files') or []
        more = len(names) - MAX_CHANGED
        out.append('<details><summary><span class="roll">The changed files</span></summary><ul class="ev">%s%s</ul>'
                   '</details>' % (''.join('<li><code>%s</code></li>' % _e(x) for x in names[:MAX_CHANGED]),
                                   '<li>and %d more</li>' % more if more > 0 else ''))
    else:
        out.append('<div class="root"><p class="t">Modelled%s%s%s</p><p class="sum">This run\'s file list was not '
                   'read, so whether the code changed since is not established.</p></div>' % (when, at, scope))
    branches = fm.get('branches') or []
    if branches:
        rows = ''.join(_branch_html(b) for b in branches)
        out.append('<details><summary><span class="roll">%s of the model</span></summary><ul class="tree">%s</ul>'
                   '</details>' % (_plural(len(branches), 'part', 'parts'), rows))
    r = fm.get('remodel')
    if fm['state'] == 'drifted' and isinstance(r, dict):
        out.append('<div class="remodel"><p><b>Remodel:</b> make the call <code>%s</code>%s. It quotes the cost '
                   'before anything runs.</p>' % (_e(r.get('route')), ' (the planned route)'
                                                  if r.get('route_planned') is not False else ''))
        if r.get('quote_usd') is not None:
            out.append('<p>A remodel is modelled at %s.</p>' % _money(r['quote_usd']))
        if r.get('remaining_usd') is not None:
            out.append('<p>Remaining budget: %s (the plan\'s %s allowance plus your %s overage budget, less %s '
                       'spent).</p>' % (_money(r['remaining_usd']), _money(r['allowance_usd']),
                                        _money(r['overage_usd']), _money(r['spent_usd'])))
        if r.get('fits') is True:
            out.append('<p>The remodel fits within the remaining budget.</p>')
        elif r.get('fits') is False:
            out.append('<p>The remodel does not fit the remaining budget.%s Raising the overage budget by %s covers '
                       'it.</p>' % (' Not covered within it: %s.' % '; '.join(
                           '%s (%s)' % (_e(u['words']), _money(u['usd'])) for u in r['uncovered'])
                                    if r.get('uncovered') else '', _money(r['extend_usd'])))
        out.append('<p>Nothing runs and nothing is charged until you make that call.</p></div>')
    return out + ['</div>', '</section>']


def render_html(tree):
    """The page for `tree` (module docstring): the header, the goals (each opening to its checks and evidence), the
    other checks the profile reads, what is not decided yet grouped by plain reason with the action that decides it,
    and what Assure read. One static document, no script, every value escaped."""
    t = tree if isinstance(tree, dict) else {}
    h, counts = t.get('header') or {}, t.get('counts') or {s: 0 for s in STATES + ('checks',)}
    by_id = {c['id']: c for c in t.get('checks') or ()}
    out = ['<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<meta name="color-scheme" content="light dark">',
           '<title>Assure proof tree</title>', '<style>%s</style>' % CSS, '</head>', '<body>', '<main>',
           '<header><h1>Proof tree%s</h1>' % (': %s' % _e(h.get('profile')) if h.get('profile') else ''),
           '<p class="lede">%s</p>' % _e(LEDE_ROWS if t.get('note') == GOALS_FROM_ROWS else LEDE),
           '<div class="legend">%s</div>' % ''.join(_pill(s) for s in ('holds', 'not_established', 'disproven')),
           '<p class="tools"><a id="expand-all" href="#expand-all">Expand all</a>'
           '<a id="collapse" href="#collapse">Collapse</a></p></header>']
    root = 'disproven' if counts.get('disproven') else 'holds' if counts.get('checks') and \
        counts.get('holds') == counts.get('checks') else 'not_established'
    title = 'Check of %s' % (h.get('repository') or 'this repository')
    if h.get('commit'):
        title += ' at commit %s' % h['commit'][:7]
    out += ['<section aria-labelledby="s-goals">', '<h2 id="s-goals">Goals</h2>',
            '<div class="root"><div class="row">%s<span class="t">%s</span></div>' % (_pill(root), _e(title)),
            '<p class="sum">%s</p></div>' % _sum(counts)]
    if t.get('no_reading'):
        out.append('<p class="note">%s</p>' % _e(t['no_reading']))
    out.append('<ul class="tree">')
    for g in t.get('goals') or ():
        tag = _e(g.get('id')) + (' &middot; requirements.md:%d' % g['line'] if type(g.get('line')) is int else '')
        kids = ''.join(_check_html(by_id[i]) for i in g.get('checks') or () if i in by_id)
        out.append('<li class="g n-%s">%s<summary><div class="row">%s<span class="t">%s</span>'
                   '<span class="tag">%s</span></div>%s</summary><ul class="tree">%s</ul>'
                   '</details></li>' % (g['state'], _open(g['state']), _pill(g['state']), _e(g.get('sentence')), tag,
                                        '<div class="roll">%s</div>' % _e(g['rollup']) if g.get('rollup') else '',
                                        kids))
    out.append('</ul>')
    if t.get('note'):
        out.append('<p class="note">%s</p>' % _e(t['note']))
    out.append('</section>')
    if t.get('other_checks'):
        oc = t['other_checks']
        out += ['<section aria-labelledby="s-other">', '<h2 id="s-other">Other checks the profile reads</h2>',
                '<p class="sum">%s</p>' % _sum({s: sum(1 for c in oc if c['state'] == s) for s in STATES}
                                               | {'checks': len(oc)}),
                '<ul class="tree">%s</ul>' % ''.join(_check_html(c) for c in oc), '</section>']
    if t.get('not_decided'):
        out += ['<section aria-labelledby="s-nd">', '<h2 id="s-nd">Not decided yet</h2>', '<ul class="tree">']
        for g in t['not_decided']:
            rows = ''.join('<li><span class="t">%s</span> <span class="tag">%s</span>%s</li>' % (
                _e(x['waypoint']), _e(x['id']), '' if not x.get('action') or x['action'] == g.get('action')
                else ' &middot; next: %s' % _e(x['action'])) for x in g['checks'])
            out.append('<li><details><summary><div class="row"><span class="t">%s</span><span class="tag">%d %s'
                       '</span></div>%s</summary><ul class="ev">%s</ul></details></li>' % (
                           _e(g['reason'][:1].upper() + g['reason'][1:]), len(g['checks']),
                           'check' if len(g['checks']) == 1 else 'checks',
                           '<div class="roll"><b>Next:</b> %s</div>' % _e(g['action']) if g.get('action') else '',
                           rows))
        out += ['</ul>', '</section>']
    facts = [('Profile', h.get('profile')), ('Repository', h.get('repository')), ('Commit', h.get('commit')),
             ('Check', h.get('check_id')), ('First checked', h.get('first_checked_at')),
             ('Reading', h.get('verdict_line')), ('Machines', h.get('machines')), ('Bounds', h.get('bounds')),
             ('Engine', ('commit %s, release %s' % ((h.get('engine') or {}).get('commit'),
                                                     (h.get('engine') or {}).get('release')))
                        if (h.get('engine') or {}).get('commit') else None)]
    facts += [('Not read', '%s: %s' % (r['machine'], r['reason'])) for r in h.get('machines_refused') or ()]
    if isinstance(t.get('formal_model'), dict):         # layer 2 (Premium)
        out += _model_html(t['formal_model'])
    out += ['<section aria-labelledby="s-read">', '<h2 id="s-read">What Assure read</h2>', '<dl class="facts">']
    out += ['<dt>%s</dt><dd>%s</dd>' % (_e(k), _e(v)) for k, v in facts if v]
    out += ['</dl>', '<p class="note">%s</p>' % _e(h.get('read')) if h.get('read') else '', '</section>',
            '<footer>%s</footer>' % _e(FOOTER), '</main>', '</body>', '</html>', '']
    return '\n'.join(out)


def proven(tree):
    """(X, Y): the checks that hold and every check, from the tree's own counts."""
    c = (tree or {}).get('counts') or {}
    return int(c.get('holds') or 0), int(c.get('checks') or 0)

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
