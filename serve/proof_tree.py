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

execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false."""
from __future__ import annotations

import html
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
LEDE = ('Each goal is a line of requirements.md. Under it are the checks Assure ran for it, and under each check the '
        'evidence it read. Every state is the check\'s own reading; nothing here is written by a model.')
# PR #2662 round 3 (LOW-3): the lede of a tree whose goals are the requirement rows (GOALS_FROM_ROWS)
LEDE_ROWS = ('Each goal is a requirement row the check read. Under it are the checks Assure ran for it, and under each '
             'check the evidence it read. Every state is the check\'s own reading; nothing here is written by a model.')
FOOTER = ('Assure states what it checked and what it could not establish. It reports only what it can show from the '
          'inputs it read.')
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
          commit=None, goals_unstored=False, goals_kept=False):
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
    goals without the text they came from)."""
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
    return {'schema': SCHEMA, 'check_id': _header(env, repository, commit)['check_id'],
            'header': _header(env, repository, commit), 'counts': counts, 'goals': out_goals, 'checks': checks,
            'other_checks': others,
            'not_decided': sorted(not_decided.values(), key=lambda g: (-len(g['checks']), g['reason'])),
            'no_reading': reading['no_reading'], 'note': note, **FLAGS}


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
CSS = """:root{--bg:#fbfbfa;--surface:#fff;--ink:#1b1d21;--muted:#5f6670;--faint:#e4e6ea;--line:#cfd4da;
--holds:#1a7f45;--holds-bg:#e6f4ec;--ne:#9a6200;--ne-bg:#fdf1dc;--dis:#b4232a;--dis-bg:#fbe7e8;--code-bg:#f2f3f5}
@media (prefers-color-scheme: dark){:root{--bg:#111317;--surface:#181b20;--ink:#eceef1;--muted:#9aa2ad;--faint:#262a31;
--line:#353b44;--holds:#5fd08f;--holds-bg:#16301f;--ne:#f0b54a;--ne-bg:#33270f;--dis:#ff7b81;--dis-bg:#3a1517;
--code-bg:#21252c}}
*{box-sizing:border-box}html,body{margin:0}
body{overflow-wrap:anywhere;background:var(--bg);color:var(--ink);font:18px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
"Helvetica Neue",Arial,sans-serif}
main{max-width:1080px;margin:0 auto;padding:48px 32px 72px}
h1{font-size:32px;line-height:1.2;margin:0 0 8px;font-weight:650}
.lede{color:var(--muted);margin:0;max-width:44em}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 32px}
section{background:var(--surface);border:1px solid var(--faint);border-radius:14px;padding:28px 28px 24px;
margin-bottom:28px}
section h2{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 16px;
font-weight:600}
.root .t{font-size:24px;font-weight:650;line-height:1.25}
.sum{color:var(--muted);margin:6px 0 0;font-size:16px}
.row{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.w{display:inline-block;flex:none;min-width:9.2em;text-align:center;font-weight:700;font-size:14px;
letter-spacing:.02em;padding:3px 12px;border-radius:999px;text-transform:uppercase}
.w-holds{color:var(--holds);background:var(--holds-bg)}.w-not_established{color:var(--ne);background:var(--ne-bg)}
.w-disproven{color:var(--dis);background:var(--dis-bg)}
.t{font-weight:600;overflow-wrap:anywhere;min-width:0}.tag{color:var(--muted);font:14px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.roll{color:var(--muted);font-size:16px}
ul{list-style:none;margin:0;padding:0}
ul.tree{margin:16px 0 0 10px;border-left:2px solid var(--line)}
ul.tree>li{padding:8px 0 8px 22px}
details>summary{cursor:pointer;list-style:none}details>summary::-webkit-details-marker{display:none}
details>summary:focus-visible{outline:2px solid var(--muted);outline-offset:3px;border-radius:6px}
details[open]>summary{margin-bottom:6px}
li.n-disproven{background:linear-gradient(90deg,var(--dis-bg),transparent 70%);border-radius:0 10px 10px 0}
ul.ev{margin:6px 0 4px 2px;color:var(--muted);font-size:16px}ul.ev li{padding:2px 0}ul.ev b{color:var(--ink)}
li.n-disproven ul.ev b{color:var(--dis)}
code{font:.92em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code-bg);color:var(--ink);
padding:1px 6px;border-radius:5px;overflow-wrap:anywhere}
a{color:inherit}q{color:var(--ink)}
.note{color:var(--muted);font-size:15px;margin:14px 0 0}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0;font-size:16px}
dl.facts dt{color:var(--muted)}dl.facts dd{margin:0;overflow-wrap:anywhere}
footer{color:var(--muted);font-size:14px;max-width:60em}
@media (max-width:720px){body{font-size:16px}main{padding:24px 16px 40px}section{padding:20px 16px}
ul.tree{margin-left:4px}ul.tree>li{padding-left:14px}.w{min-width:0}.root .t{font-size:21px}
dl.facts{grid-template-columns:1fr}dl.facts dd{margin-bottom:6px}}"""
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


def _check_html(c):
    return ('<li class="n n-%s"><details><summary><div class="row">%s<span class="t">%s</span><span class="tag">%s'
            '</span></div></summary>%s</details></li>' % (c['state'], _pill(c['state']), _e(c['waypoint']),
                                                         _e(c['id']), _evidence_html(c)))


def _sum(counts):
    return ('%d hold &middot; %d not established &middot; %d disproven &middot; %d checks'
            % (counts['holds'], counts['not_established'], counts['disproven'], counts['checks']))


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
           '<div class="legend">%s</div></header>' % ''.join(_pill(s) for s in ('holds', 'not_established',
                                                                                 'disproven'))]
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
        out.append('<li class="g n-%s"><details><summary><div class="row">%s<span class="t">%s</span>'
                   '<span class="tag">%s</span></div>%s</summary><ul class="tree">%s</ul>'
                   '</details></li>' % (g['state'], _pill(g['state']), _e(g.get('sentence')), tag,
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
