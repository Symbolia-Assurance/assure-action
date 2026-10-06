"""The job summary (Markdown) and GitHub annotations for a verdict envelope, and the summary for a failure envelope.

Wording rules (INTERFACE-CONTRACT-OB-001 section 5) bind: vacuous is never shown as holds; deviates is never called a
failure; non-verdict statuses are never shown as satisfied; a result with no verdict reads "No verdicts"; an input-integrity
gate (a0) reads "No reading: input integrity". Words only: no tick, cross or coloured symbol. Every string that could
derive from customer input is bounded to 300 characters and escaped for Markdown and HTML, and a URL, `www.` name or
e-mail address in it is shown as a code span, so it never becomes a clickable link; annotation messages and properties
are escaped per the workflow-command rules so that no value can start a new command.

A row's reason follows its status text in brackets only when it differs from that text.

`not_observed_lines` (the RF-28 collector's withheld lines) are listed under "Not observed: lines the collector
withheld", one line each: `not observed: <file> line <N> (<reason in plain words>)`. A failure envelope whose detail
carries a malformation (serve/outcomes.py) adds one line naming its kind, file, line, field and expected form.

The policy line states the run's exit in plain words from `policy.reason`: `policy_met`, `policy_failed`, `no_verdict`
("No verdicts: nothing was checked, so the job stops with exit 3."), `input_integrity`, `machines_refused` or `never`.

The first line says how many machines were read and how many were refused, then the outcome (DIRECTOR_DIRECTION-057 item
3; coordination 1591): "## Assure: 5 of 8 machines read, 3 refused. Readings", or "No machine could be read (8 refused)"
when none was. `machines_line(envelope)` gives that phrase (the Action's stdout line uses it too), or None for an
envelope without `machines` (an older server), whose headline is unchanged. Each refused machine is listed with its
reason. An inferred set (`source: inferred`) says so in the first line, in the Action's stdout line, and in a note
printed whether or not a machine was refused (refutation-007 G3).

An envelope whose profile is scoped by another unit (`scope_observed`, serve/envelope.py) leads with that scope:
`first_line(envelope)` is "1 of 2 endpoints observed, 1 refused; 5 of 5 machines read, none refused", with "(accepted
scope reduced)" after the scope phrase when a unit was removed from the accepted scope; each refused unit is listed
under "<Label> not <verb>" with its reason, and the policy reason `scope_refused` has its own plain line. For a
machine-scoped envelope `first_line` is `machines_line`, unchanged.

SELFHOSTED-001 (the self-hosted lab run, 5 Oct 2026):
- A reason the checker writes as a bound comparison, "domain bound exceeded (users 5 > 6 or databases 4 > 3)", prints
  every comparison, true or false. The checker's text is shown unchanged; a serving-side gloss follows it, naming only
  the bounds actually exceeded: "in plain words: domain bound exceeded: databases 4 (cap 3)" (`bound_gloss`).
- A `fails` row whose reason is empty (the declared profile's rows) shows its witness from the envelope's `readings`
  (`witnesses` or `witness` of that obligation), bounded and escaped like any reason (`witness_text`).
- A failure page names a check only when the check reached the server: the server's check id came back in
  `detail.check_id`. A refusal in the runner before anything was sent reads "No check was sent."; an `api_unreachable`
  or `api_error` with no check id from the server reads "No check id came back from the API." (`check_line`).

Refutation-010 (5 Oct 2026):
- G1: a typed refusal the API answered without a check id (the client marks it `detail.answered`) reads "The API
  refused the request before a check started; the collected files were sent and not kept." The upload left the
  runner, so "No check was sent." is kept for refusals raised in the runner.
- Round 2 G1: the client marks which request the API answered (`detail.answered`: 'profiles', 'check' or 'poll').
  A refusal of `GET /v1/profiles`, which comes before anything is collected (a wrong or revoked key, a rate limit),
  reads "The API refused the request for the profile list before anything was collected; nothing from your system
  was sent."; a refused poll reads "Check <id>. The check was sent; the API refused the poll for its result."
  (`check_line`).
- F1: a `bad_input` caused by a workflow input (fail-on, allow-partial, the artefacts path, another named input) shows
  that input's next step under "What to do" (`next_step`); the envelope's `action` is unchanged.

serve-016 (DIRECTOR_DECISION-073 and Addendum 1; DESIGN-004 section 2): an envelope that carries `colour` leads with
one deterministic line in closed words (`verdict_line`), the job summary's headline, the Action's one first notice and
the subject of its log line:
- red: "red: <coverage>; <bounds>[; prove-class obligations: p (unproven: u)]; disproven: <id> — <object>, <access
  path>, <locator>" from the first of `red_findings` and its first witness; a prove-class obligation with no holds
  reads "not proven: <id> — <reason>; <action>", and a security obligation the strict preset names "unresolved by your
  choice (strict): <id> — <reason>; <action>".
- green: "green: <coverage>; <bounds>[; prove-class ...]; nothing disproven; established: h of N; not established:
  n", where N counts every obligation reading and h the holds on machines that were read (one denominator,
  REFUTATION-028 F7); with no holds (coordination 2098, item A21) "green: <coverage>; <bounds>[; prove-class ...];
  nothing could be established (0 of N obligations hold); not established: n", so a count never reads as success.
- red after REFUTATION-028 and round 2 (`decide`): a fails reading on a read machine is red whatever fail-on says; a
  status you name in fail-on also turns the reading red and sets the exit. A status chosen that is not a verdict reads
  "stopped by your choice: <status> — <id>"; a red line whose exit is 0 ends "(exit 0 by your fail-on: <words>)", and
  one whose exit 1 comes from another finding than the one it leads with ends "(exit 1 by your fail-on: <status> —
  <id>)". The yellow action for the representation case is "re-collect with the pinned collector" (2133's example);
  the summary prints the gate's reason and the file it names under it (R2-7).
- DD-073 Addendum 2: `meaning_line` gives one plain sentence per colour from a closed template, and `why_lines` one line
  per disproven or deviating obligation from its statement and the profile's consequence ("Consequence not yet stated
  for <id>." where none is given); nothing is written by a model. One line per not-established obligation follows,
  "<id>: <reason> — <action>[ — quote USD a–b]" (`not_established_line`).
- yellow: "yellow: could not look: <reason>; <action>".
The coverage is "[E of F <units> <verb>; ]N of M machines read[, K refused]" (with "(inferred)" for an inferred machine
set, refutation-007 G3); the bounds "declared premises: n; version pins: <pins or none>", where an observed profile that
declares nothing reads "declared premises: none (observed profile)". Heading 2073's build notes, as REFUTATION-028
corrected them: every green line ends "not established: n — top action: <action>[ — quote USD a–b]", the action of the
most frequent reason class leaving out the representation fallback when any other class is present (N1; 2129 W2, W3); deviates readings on read machines are their own count,
"deviations: d", never folded into not-established (N2); a prove-class obligation whose inputs could not be read reads
"not proven: <id> — input not observed" (N5); the strict preset with no obligation marked adds "strict: no obligations
marked" after the bounds (N6). The reason words and actions
are the closed table of DESIGN-004 section 2 (`REASON_WORDS`). Green reads "nothing disproven" within these bounds,
never "safe". An envelope without `colour` (an older server) renders as before. `red_findings` and `could_not_look`
are the policy's own tests (serve/envelope.py imports them), kept here because this module ships in the Action.

serve-014: a claim-tree report that was not written reads one line, the same on the report page and in the Action's job
summary: "The report was withheld: <reason in plain words>." (`report_withheld_line`), from REPORT_WITHHELD for the
fallback reasons; any other reason (a typed refusal's own text) is bounded and escaped like any customer string.
A written body enters the job summary through `report_markdown`: at most REPORT_CAP characters, every line HTML-escaped
with link brackets, pipes, backticks and tildes escaped and link-shaped text as a code span, so it can carry its one
bold span and its paragraphs and nothing else; `report_page_line(url)` names the page as a code span.
"""
from __future__ import annotations

import html
import re

CAP = 300
MAX_ANNOTATIONS = 50
REPORT_WITHHELD = {'lint_failed': 'the written text did not pass the deterministic check',
                   'writer_unavailable': 'the writer could not be reached',
                   'profile_unqualified': 'the writer is not yet qualified for this profile',
                   'writer_substituted': 'another model answered in place of the qualified writer',   # serve-015
                   # serve-015 (REFUTATION-027-R2 F2): the worker's attempts are bounded; the charge is 0
                   'settlement_failed': 'the report could not be settled after three attempts; nothing was charged'}
# serve-015: why a withheld report was still charged, said on its cost line
REPORT_CHARGED_WHY = {'lint_failed': 'the writer was called; the gate refused its text',
                      'writer_substituted': 'the writer was called; another model answered'}
# serve-015: why a withheld report was charged nothing, said on its cost line whatever its charge reads
REPORT_UNCHARGED_WHY = {'settlement_failed': REPORT_WITHHELD['settlement_failed']}
_MD_SPECIAL = re.compile(r'([\\`*_\[\]|~])')   # customer text never starts a line, so # and - need no escape
REPORT_CAP = 8000
_REPORT_SPECIAL = re.compile(r'([\\`\[\]|~])')    # a written body keeps its * (one bold span) and nothing else
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')


def _clip(value):
    s = '' if value is None else str(value)
    s = _CONTROL.sub(' ', s)
    return s if len(s) <= CAP else s[:CAP - 1] + '…'


# A URL (any scheme://), a www. name or an e-mail address: rendered as a code span, never as a link (ACTION-07).
_LINKISH = re.compile(r'(?i)\b[a-z][a-z0-9+.-]*://[^\s`<>"\']*|\bwww\.[^\s`<>"\']*'
                      r'|[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+')


def _esc_plain(s):
    return _MD_SPECIAL.sub(r'\\\1', html.escape(s, quote=True))


def _esc_line(s):
    """`esc` for a line whose parts were bounded one by one (serve-016: the verdict line): escaped, never clipped whole."""
    s = _CONTROL.sub(' ', '' if s is None else str(s))
    out, pos = [], 0
    for m in _LINKISH.finditer(s):
        out.append(_esc_plain(s[pos:m.start()]))
        out.append('`%s`' % m.group(0).replace('`', ''))
        pos = m.end()
    out.append(_esc_plain(s[pos:]))
    return ''.join(out)


def esc(value):
    """Bounded, single-line, HTML- and Markdown-escaped text; link-shaped parts become code spans."""
    s = _clip(value)
    out, pos = [], 0
    for m in _LINKISH.finditer(s):
        out.append(_esc_plain(s[pos:m.start()]))
        out.append('`%s`' % m.group(0))      # a code span shows its text literally: no link, no HTML, no Markdown
        pos = m.end()
    out.append(_esc_plain(s[pos:]))
    return ''.join(out)


def label(status):
    return str(status).replace('_', ' ')


def _extra_reason(row):
    """The reason is shown beside the status text only when it adds something: for the observed profile the two are
    equal on every verdict (contract section 5), and the summary would otherwise say each one twice."""
    reason = row.get('reason')
    return bool(reason) and str(reason) != str(row.get('status_text') or '')


# The checker's bound text (assure/.../derive_observed.py): "domain bound exceeded (users 5 > 6 or databases 4 > 3)".
_BOUND_RE = re.compile(r'domain bound exceeded \(([a-z_ ]+ [0-9]+ > [0-9]+(?: or [a-z_ ]+ [0-9]+ > [0-9]+)*)\)')
_BOUND_PART_RE = re.compile(r'([a-z_ ]+?) ([0-9]+) > ([0-9]+)')


def bound_gloss(reason):
    """'in plain words: domain bound exceeded: databases 4 (cap 3)' for a checker reason that lists bound comparisons,
    naming only the bounds whose count is over the cap; None when the reason lists none or none is exceeded."""
    m = _BOUND_RE.search('' if reason is None else str(reason))
    if m is None:
        return None
    over = []
    for part in m.group(1).split(' or '):
        p = _BOUND_PART_RE.fullmatch(part.strip())
        if p and int(p.group(2)) > int(p.group(3)):
            over.append('%s %s (cap %s)' % (p.group(1).strip(), p.group(2), p.group(3)))
    return 'in plain words: domain bound exceeded: %s' % ', '.join(over) if over else None


def _reason(reason):
    """An escaped, bounded reason, with the bound gloss after it when it has one."""
    gloss = bound_gloss(reason)
    return esc(reason) + ('; %s' % esc(gloss) if gloss else '')


MAX_WITNESSES = 5
# The witness fields shown first, in this order; a witness with none of them shows its own scalar fields.
_WITNESS_KEYS = ('path', 'command', 'outcome', 'old_row', 'new_row', 'role', 'capability', 'object', 'owner', 'reason')
_FLAG_KEYS = frozenset({'execution_authorized', 'hardware_authorized', 'industrial_release_authorized',
                        'physical_validation', 'release_allowed', 'self_approved', 'simulation'})


def _scalar(v):
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _one_witness(w):
    if _scalar(w):
        return str(w)
    if not isinstance(w, dict):
        return None
    items = [(k, w[k]) for k in _WITNESS_KEYS if _scalar(w.get(k))]
    if not items:
        items = [(k, v) for k, v in sorted(w.items(), key=lambda kv: str(kv[0]))
                 if isinstance(k, str) and k not in _FLAG_KEYS and _scalar(v)][:6]
    return ', '.join('%s %s' % (k.replace('_', ' '), v) for k, v in items) or None


def witness_text(envelope, row):
    """'witness: path postgres:direct, command SELECT, outcome allowed, ...' (or 'witnesses: a; b; and N more') for a
    row from the obligation's `witnesses` list or `witness` object in the envelope's `readings`; None when there is
    none. Never raises: a reading of another shape gives None."""
    try:
        rd = (envelope.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = None
        if isinstance(obs, dict):
            ob = obs.get(row.get('id'))
        elif isinstance(obs, list):
            ob = next((o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None)
        if not isinstance(ob, dict):
            return None
        ws = ob.get('witnesses')
        ws = ws if isinstance(ws, list) else ([ob['witness']] if isinstance(ob.get('witness'), dict) else [])
        parts = [p for p in (_one_witness(w) for w in ws[:MAX_WITNESSES]) if p]
        if not parts:
            return None
        more = len(ws) - MAX_WITNESSES
        return '%s: %s%s' % ('witness' if len(ws) == 1 else 'witnesses', '; '.join(parts),
                             '; and %d more' % more if more > 0 else '')
    except (AttributeError, TypeError):
        return None


def _row_extra(env, r):
    """The bracketed text after a row's status text: its reason when that adds something, or for a `fails` row with
    no reason, its witness; None when neither."""
    if _extra_reason(r):
        return _reason(r.get('reason'))
    if r.get('status') == 'fails':
        w = witness_text(env, r)
        return esc(w) if w else None
    return None


def _machines(env):
    m = env.get('machines')
    if not isinstance(m, dict):
        return None
    read, refused, total = m.get('read'), m.get('refused'), m.get('total')
    if not isinstance(read, list) or not isinstance(refused, list) or type(total) is not int:
        return None
    return m


def machines_line(envelope):
    """'5 of 8 machines read, 3 refused', '8 of 8 machines read, none refused', 'No machine could be read (8 refused)',
    or None when the envelope carries no `machines` block. An inferred set (`source: inferred`) says so in the phrase
    itself: '8 of 8 machines read, none refused (inferred)', 'No machine could be read (8 refused, inferred)'
    (refutation-007 G3)."""
    m = _machines(envelope) if isinstance(envelope, dict) else None
    if m is None:
        return None
    n_read, n_refused, total = len(m['read']), len(m['refused']), int(m['total'])
    inferred = m.get('source') == 'inferred'
    if n_read == 0:
        inner = ['%d refused' % n_refused] if n_refused else []
        inner += ['inferred'] if inferred else []
        return 'No machine could be read' + (' (%s)' % ', '.join(inner) if inner else '')
    if n_refused == 0:
        line = '%d of %d machines read, none refused' % (n_read, total)
    else:
        line = '%d of %d machines read, %d refused' % (n_read, total, n_refused)
    return line + (' (inferred)' if inferred else '')


def _scope(env):
    sc = env.get('scope_observed') if isinstance(env, dict) else None
    if not isinstance(sc, dict):
        return None
    if not isinstance(sc.get('expected'), list) or not isinstance(sc.get('observed'), list) \
            or not isinstance(sc.get('refused'), list):
        return None
    return sc


def scope_line(envelope):
    """'1 of 2 endpoints observed, 1 refused', '2 of 2 endpoints observed, none refused', with ' (accepted scope
    reduced)' when a unit was removed from the accepted scope; None for an envelope without `scope_observed`."""
    sc = _scope(envelope)
    if sc is None:
        return None
    n_obs, n_ref, total = len(sc['observed']), len(sc['refused']), len(sc['expected'])
    label, verb = _clip(sc.get('label') or 'units'), _clip(sc.get('verb') or 'observed')
    line = '%d of %d %s %s, %s' % (n_obs, total, label, verb, ('%d refused' % n_ref) if n_ref else 'none refused')
    if any(isinstance(r, dict) and r.get('reason') == 'removed from the accepted scope' for r in sc['refused']):
        line += ' (accepted scope reduced)'
    return line


def report_withheld_line(reason):
    """serve-014: the one line a withheld or refused report reads (module docstring)."""
    words = REPORT_WITHHELD.get(reason) if isinstance(reason, str) else None
    if words is None:
        words = esc(reason).rstrip('.') if reason else 'no reason was given'
    return 'The report was withheld: %s.' % words


def report_markdown(text):
    """serve-014: a written report body for the job summary (module docstring)."""
    t = '' if text is None else str(text)
    if len(t) > REPORT_CAP:
        t = t[:REPORT_CAP - 1] + '…'
    lines = []
    for line in t.split('\n'):
        line = _CONTROL.sub(' ', line).lstrip('#').strip()          # no heading, no raw control character
        out, pos = [], 0
        for m in _LINKISH.finditer(line):
            out.append(_REPORT_SPECIAL.sub(r'\\\1', html.escape(line[pos:m.start()], quote=True)))
            out.append('`%s`' % m.group(0).replace('`', ''))
            pos = m.end()
        out.append(_REPORT_SPECIAL.sub(r'\\\1', html.escape(line[pos:], quote=True)))
        lines.append(''.join(out))
    return '\n'.join(lines).strip()


def _money(v, places):
    return ('%%.%df' % places) % float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else '?'


def report_cost_line(record):
    """serve-015: the report's one usage line for the job summary, or None for a record without a line charge (an
    earlier server's): "Report: cost USD x.xxx, charged USD y.yyy, allowance remaining USD z.zz"."""
    cost = record.get('cost') if isinstance(record, dict) else None
    if not isinstance(cost, dict) or 'charge_usd' not in cost:
        return None
    line = 'Report: cost USD %s, charged USD %s, allowance remaining USD %s' % (
        _money(cost.get('usd') or 0.0, 3), _money(cost.get('charge_usd'), 3), _money(cost.get('allowance_remaining'), 2))
    why = REPORT_CHARGED_WHY.get(((record.get('fallback') or {}).get('reason')))
    charged = cost.get('charge_usd')
    if why and isinstance(charged, (int, float)) and not isinstance(charged, bool) and charged > 0:
        line += ' (%s)' % why
    free = REPORT_UNCHARGED_WHY.get(((record.get('fallback') or {}).get('reason')))
    if free:
        line += ' (%s)' % free
    return line


def report_exhausted_line(needed_usd):
    """serve-015: the line for a report refused `allowance_exhausted`."""
    return 'Report: allowance exhausted: USD %s needed; set allow-overage or top up' % _money(needed_usd, 3)


def report_page_line(url):
    """serve-014: the line that names the report page (the API's own URL, never customer text)."""
    return 'The report page: `%s` (send your API key in the Authorization header to open it).' % str(url).replace('`', '')


def first_line(envelope):
    """The first line's coverage phrase: the scope phrase then the machines phrase for a profile scoped by another
    unit, `machines_line` otherwise (None when the envelope carries neither)."""
    scope, machines = scope_line(envelope), machines_line(envelope)
    if scope is None:
        return machines
    return scope if machines is None else '%s; %s' % (scope, machines)


# ---------- serve-016: the policy's tests and the verdict line (module docstring) ----------
STRICT = 'unresolved-security'
COLOURS = ('green', 'red', 'yellow')
# DESIGN-004 section 2: each closed reason class in words; not_observed adds its locator.
REASON_WORDS = {'not_observed': 'a fact was not collected', 'missing_method': 'no method for this shape',
                'not_observable_at_pin': 'not observable at collector pin',
                'missing_baseline': 'no pinned baseline for major', 'needs_intent': 'depends on what the system is for',
                'representation': 'the input could not be represented'}
CLASS_ACTIONS = {'missing_method': 'a method is a later profile version',
                 'missing_baseline': 'pin the baseline (Symbolia)', 'needs_intent': 'state it in requirements.md',
                 'representation': 're-collect with the pinned collector',
                 'not_observable_at_pin': 'collect with the collector successor (Symbolia)'}
# coordination 2102 A22: who can establish each class, and what it needs (not_observed: 'collect <locator>';
# missing_baseline: the major; representation: the row's reason). `unsupported` (A25): the product's own limits.
CLASS_OWNERS = {'not_observed': 'agent', 'needs_intent': 'operator', 'missing_baseline': 'symbolia',
                'not_observable_at_pin': 'symbolia',
                'missing_method': 'symbolia', 'representation': 'agent'}
CLASS_NEEDS = {'needs_intent': 'a requirements.md sentence', 'missing_baseline': 'a pinned baseline for major %s',
               'not_observable_at_pin': 'a collector successor that observes it',
               'missing_method': 'a method for this input shape', 'representation': 'a faithful input: %s'}
UNSUPPORTED_CLASSES = ('representation', 'missing_method')


def _rows(env):
    return [r for r in env.get('rows') or [] if isinstance(r, dict)]


def _read_set(env):
    m = _machines(env)
    return set(m['read']) if m is not None else {r.get('machine') for r in _rows(env)}


def could_not_look(envelope):
    """True when nothing could be read at all: the input-integrity gate stopped the check (`a0`), no machine was read,
    or a row with a selected scope observed none of its units (DESIGN-004 section 1 row 3 as corrected by the
    remodel lane for serve-016: "no machine read, OR a scoped row with no unit observed"). An envelope without
    `machines` looked unless `a0` is set or its scope observed nothing."""
    env = envelope if isinstance(envelope, dict) else {}
    if env.get('a0') is not None:
        return True
    sc = _scope(env)
    if sc is not None and not sc['observed']:
        return True
    m = _machines(env)
    return m is not None and not m['read']


_VERDICTS_DEFAULT = ('holds', 'fails', 'deviates', 'vacuous')


def _verdicts(env):
    v = (env.get('vocabulary') or {}).get('verdict_statuses') if isinstance(env.get('vocabulary'), dict) else None
    return (set(v) if isinstance(v, list) else set(_VERDICTS_DEFAULT)) | {'vacuous'}


# REFUTATION-028-R3, R3-1: a row of a verdict status the checker kept on a machine it refused is read, on every
# surface, as what the not-established list calls it: not observed. These statuses stop the job on it when fail-on
# names them (the not-observed class of the closed table).
KEPT_READ_AS = 'not_observed'
# REFUTATION-028-R4, R4-1: a met status on a read machine is never a disproof or a choice to stop, under any vocabulary
# or fail-on (one kept on a refused machine is read as not observed: `kept_on_refused`; R5-5)
MET = ('holds', 'vacuous')
NOT_OBSERVED_STATUSES = ('not_observed', 'missing_premise')
KEPT_WORDS = 'kept by the checker, read as not observed'


def kept_on_refused(envelope, row):
    """True when `row` is an obligation reading of a verdict status (or vacuous) that the checker kept on a machine
    it refused: coverage, read as not observed (R3-1). False for an envelope without `machines`."""
    env = envelope if isinstance(envelope, dict) else {}
    if not isinstance(row, dict) or row.get('id') is None or _machines(env) is None:
        return False
    return row.get('status') in _verdicts(env) and row.get('machine') not in _read_set(env)


def red_findings(envelope):
    """What turns the colour red (DESIGN-004 section 1 row 4; REFUTATION-028 F1, F2), in order, as [(kind, obligation
    id, row or None)]:
    - 'disproven': on a machine that was read (REFUTATION-028-R2, R2-1: one rule for both conditions), every `fails`
      reading, whatever fail-on says, and every reading of a verdict status fail-on names (`deviates`). A `fails` row
      the checker kept on a machine it refused is coverage, never a disproof: the refusal is on the first line and the
      row is listed as not established (class not_observed);
    - 'not_proven': every prove-class obligation of `bias.prove` with no holds on a machine that was read (or
      'disproven' when it reads fails: listed above);
    - 'strict': under the strict preset, every obligation of `bias.security` with no verdict (a verdict status or
      vacuous) on a machine that was read;
    - 'chosen': every reading of a non-verdict status fail-on names (`not_observed`, `not_collected`'s statuses):
      never "disproven", always "stopped by your choice".
    An obligation is listed once, under its first kind."""
    env = envelope if isinstance(envelope, dict) else {}
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    words = [s for s in pol.get('fail_on') or () if isinstance(s, str)]
    named = set(words) - {STRICT}
    verdicts = _verdicts(env)
    rows, read = _rows(env), _read_set(env)
    out = [('disproven', r.get('id'), r) for r in rows                    # R4-1: holds and vacuous never are
           if r.get('machine') in read and r.get('status') not in MET
           and (r.get('status') == 'fails' or (r.get('status') in named and r.get('status') in verdicts))]
    listed = {(r.get('machine'), r.get('id')) for _, _, r in out}
    by_id = {}
    for r in rows:
        if r.get('id') is not None:
            by_id.setdefault(r.get('id'), r)
    bias = env.get('bias') if isinstance(env.get('bias'), dict) else {}
    for i in bias.get('prove') or ():
        r = by_id.get(i)
        if r is not None and ((r.get('machine'), i) in listed
                              or (r.get('status') == 'holds' and r.get('machine') in read)):
            continue
        out.append(('not_proven', i, r))
    if STRICT in words:
        named_ids = {i for _, i, _ in out}
        unobservable = set(bias.get('unobservable') or ())        # only what the collector pin can observe counts
        for i in [x for x in bias.get('security') or () if x not in unobservable]:
            r = by_id.get(i)
            if i in named_ids or (r is not None and r.get('status') in verdicts and r.get('machine') in read):
                continue
            out.append(('strict', i, r))
    named_ids = {i for _, i, _ in out if i is not None}
    for r in rows:
        key = (r.get('machine'), r.get('id'))
        if key in listed or (r.get('id') is not None and r.get('id') in named_ids):
            continue
        if r.get('status') in named and r.get('status') not in verdicts and r.get('status') not in MET:
            out.append(('chosen', r.get('id'), r))
        elif kept_on_refused(env, r) and named & set(NOT_OBSERVED_STATUSES):        # R3-1 (i)
            out.append(('chosen', r.get('id'), dict(r, status=KEPT_READ_AS)))
    return out


# REFUTATION-028-R2, R2-10 (a): the reason for each kind of finding that sets exit 1, in the order the reason is chosen
EXIT_REASONS = (('disproven', 'disproven'), ('not_proven', 'not_proven'), ('strict', 'unresolved_strict'),
                ('chosen', 'stopped_by_choice'))


def _prove_ids(env):
    b = env.get('bias') if isinstance(env.get('bias'), dict) else {}
    return set(b.get('prove') or ())


def binding_reason(envelope, finding):
    """The reason a finding sets exit 1 under the request's fail-on, or None when it does not bind
    (REFUTATION-028-R5, R5-1: one rule; R6-1): a prove-class obligation binds unless it holds on a read machine, whatever
    kind it is listed under, `never` included: `disproven` when it reads fails and fail-on names fails, else
    `not_proven`. Otherwise a disproof of a status fail-on names (`disproven`), a strict finding
    (`unresolved_strict`) and a chosen non-verdict status (`stopped_by_choice`) bind; under `never` nothing else does
    (DD-076 rail 1, heading 2241: the reviewer's Q3 recommendation, Add.1's bias binds the exit)."""
    env = envelope if isinstance(envelope, dict) else {}
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    named = {s for s in pol.get('fail_on') or () if isinstance(s, str)} - {STRICT}
    kind, ob_id, row = finding
    status = row.get('status') if isinstance(row, dict) else None
    read = _read_set(env)
    held = {r.get('id') for r in _rows(env) if r.get('status') == 'holds' and r.get('machine') in read}
    # REFUTATION-028-R6, R6-1: the prove branch only when the obligation holds on no read machine
    if ob_id is not None and ob_id in _prove_ids(env) and ob_id not in held:
        return 'disproven' if kind == 'disproven' and status in named else 'not_proven'
    if not named and STRICT not in (pol.get('fail_on') or ()):
        return None
    if kind == 'disproven':
        return 'disproven' if status in named else None
    return dict(EXIT_REASONS).get(kind)


def binding_findings(envelope):
    """The findings that set exit 1 under the request's fail-on (`binding_reason`)."""
    env = envelope if isinstance(envelope, dict) else {}
    return [f for f in red_findings(env) if binding_reason(env, f) is not None]


def decide(envelope):
    """(colour, exit, reason) for an envelope (serve-016 after REFUTATION-028 and its rounds). The colour says whether
    anything is red: yellow 3 `could_not_look` when nothing could be read and no prove-class obligation is unproven (a
    prove-class obligation where nothing could be read is red, DD-073 Addendum 1); red when anything is in
    `red_findings`; green otherwise. `policy.reason` names the exit's cause and nothing else (R2-2): the binding reason
    first in EXIT_REASONS order (`binding_reason`; a prove-class obligation that does not hold on a read machine binds
    under every fail-on, `never` included); a red finding nothing binds stays red with exit 0, `never` under fail-on
    never, else `disproven`, and the first line says "(exit 0 by your fail-on: ...)"."""
    env = envelope if isinstance(envelope, dict) else {}
    found = red_findings(env)
    unproven = any(k == 'not_proven' for k, _, _ in found)
    looked = not could_not_look(env)
    colour = 'yellow' if not looked and not unproven else 'red' if found else 'green'
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    never = not [s for s in pol.get('fail_on') or () if isinstance(s, str)]
    if colour == 'yellow':
        return colour, 0 if never else 3, 'never' if never else 'could_not_look'
    if colour == 'green':
        return colour, 0, 'never' if never else 'nothing_disproven'
    reasons = {binding_reason(env, f) for f in found}
    for _, reason in EXIT_REASONS:
        if reason in reasons:
            return colour, 1, reason
    return colour, 0, 'never' if never else 'disproven'


def reason_words(entry, envelope=None):
    """The words of a not-established entry's reason class: "a fact was not collected: <locator>" (from its action
    'collect <locator>'), "no pinned baseline for major <n>" (from the envelope's version pins), or the class's fixed
    words."""
    cls = entry.get('reason_class') if isinstance(entry, dict) else None
    words = REASON_WORDS.get(cls, REASON_WORDS['representation'])
    if cls == 'not_observed':
        action = str(entry.get('action') or '')
        return '%s: %s' % (words, action[len('collect '):] if action.startswith('collect ') else 'unknown')
    if cls == 'not_observable_at_pin':           # the pin the registry carries, or that it names none
        pin = ((envelope or {}).get('bias') or {}).get('collector_pin')
        return '%s %s' % (words, _clip(pin) if isinstance(pin, str) else '(no collector pin is registered for this profile)')
    if cls == 'missing_baseline':
        pins = ((envelope or {}).get('bounds') or {}).get('version_pins') or []
        major = next((p[len('major '):] for p in pins if isinstance(p, str) and p.startswith('major ')), 'unknown')
        return '%s %s' % (words, major)
    return words


def _quote_words(quote):
    """' — quote USD a–b' for a quote of the served shape ({quote_usd: {low, high}}), else ''."""
    q = quote.get('quote_usd') if isinstance(quote, dict) else None
    if not isinstance(q, dict):
        return ''
    return ' — quote USD %s–%s' % (_money(q.get('low'), 2), _money(q.get('high'), 2))


def not_established_line(entry, envelope=None):
    """'<id>: <reason> — <owner>: <needs>[ — quote USD a–b]' for one not-established entry (coordination 2102 A22;
    plain text, parts bounded); an entry without `owner` (an earlier serve-016 envelope) shows its action."""
    e = entry if isinstance(entry, dict) else {}
    tail = '%s: %s' % (_clip(e['owner']), _clip(e.get('needs'))) if e.get('owner') else _clip(e.get('action'))
    return '%s: %s — %s%s' % (_clip(e.get('id')), _clip(reason_words(e, envelope)), tail, _quote_words(e.get('quote')))


def _coverage_words(env):
    parts = []
    sc = _scope(env)
    if sc is not None:
        line = '%d of %d %s %s' % (len(sc['observed']), len(sc['expected']), _clip(sc.get('label') or 'units'),
                                   _clip(sc.get('verb') or 'observed'))
        if any(isinstance(r, dict) and r.get('reason') == 'removed from the accepted scope' for r in sc['refused']):
            line += ' (accepted scope reduced)'
        parts.append(line)
    m = _machines(env)
    if m is not None:
        line = '%d of %d machines read' % (len(m['read']), int(m['total']))
        line += ', %d refused' % len(m['refused']) if m['refused'] else ''
        parts.append(line + (' (inferred)' if m.get('source') == 'inferred' else ''))
    return '; '.join(parts)


def _bounds_words(env):
    b = env.get('bounds') if isinstance(env.get('bounds'), dict) else {}
    pins = [_clip(p) for p in b.get('version_pins') or () if isinstance(p, str)]
    n = b.get('declared_premises')
    n = n if type(n) is int else 0
    # 2073 N3: an observed profile that declares nothing says so in words, never "0"
    premises = 'none (observed profile)' if n == 0 and b.get('observed') is True else str(n)
    return 'declared premises: %s; version pins: %s' % (premises, ', '.join(pins) or 'none')


def _prove_words(env):
    b = env.get('bias') if isinstance(env.get('bias'), dict) else {}
    total, unproven = b.get('prove_total'), b.get('prove_unproven')
    if type(total) is not int or total <= 0:
        return None
    return 'prove-class obligations: %d (unproven: %d)' % (total, unproven if type(unproven) is int else total)


def _witness_parts(env, row):
    """'<object>, <access path>, <locator>' from the row's first witness in `readings` (each part present only when the
    witness names it), else the row's reason or status text. Plain text, bounded."""
    w = None
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
        if isinstance(ob, dict):
            ws = ob.get('witnesses')
            w = ws[0] if isinstance(ws, list) and ws else ob.get('witness')
    except (AttributeError, TypeError):
        w = None
    parts = []
    if isinstance(w, dict):
        flow = w.get('flow') if isinstance(w.get('flow'), dict) else {}
        records = w.get('records') if isinstance(w.get('records'), list) else []
        for options in ((w.get('object'), w.get('role'), w.get('owner'), flow.get('user'), flow.get('role')),
                        (w.get('path'), w.get('command'), w.get('rule_id'), flow.get('transport'), flow.get('name')),
                        (w.get('locator'), records[0] if records else None)):
            v = next((x for x in options if _scalar(x)), None)
            if v is not None:
                parts.append(_clip(v))
    elif _scalar(w):
        parts.append(_clip(w))
    if parts:
        return ', '.join(parts)
    return _clip(row.get('reason') or row.get('status_text') or row.get('status'))


def _red_words(env, finding):
    kind, ob_id, row = finding
    if kind == 'disproven' and row is not None:
        return 'disproven: %s — %s' % (_clip(ob_id if ob_id is not None else row.get('machine')),
                                       _witness_parts(env, row))
    if kind == 'chosen':                             # REFUTATION-028 F2: never "disproven"
        return 'stopped by your choice: %s — %s' % (_clip(label((row or {}).get('status'))),
                                                     _clip(ob_id if ob_id is not None else (row or {}).get('machine')))
    lead = 'not proven: ' if kind == 'not_proven' else 'unresolved by your choice (strict): '
    entry = next((e for e in env.get('not_established') or () if isinstance(e, dict) and e.get('id') == ob_id), None)
    unread = (row is None or row.get('machine') not in _read_set(env)
              or (entry is not None and entry.get('reason_class') == 'not_observed'))
    if kind == 'not_proven' and unread:              # 2073 N5: its inputs could not be read
        return 'not proven: %s — input not observed' % _clip(ob_id)
    if entry is None and isinstance(row, dict):      # a verdict that is not holds (vacuous, deviates): its status
        return '%s%s — reads %s' % (lead, _clip(ob_id), _clip(label(row.get('status'))))
    if entry is None:                                # no reading at all: a fact that was not collected
        entry = {'reason_class': 'not_observed', 'action': 'collect the facts %s reads' % _clip(ob_id)}
    return '%s%s — %s; %s' % (lead, _clip(ob_id), _clip(reason_words(entry, env)), _clip(entry.get('action')))


def _could_not_look_words(env):
    """'<reason>; <action>' for a yellow line: the input gate is representation; no machine read is not_observed when
    every refusal says so (the locator from the first raw/ path it names), else representation."""
    sc = _scope(env)
    if env.get('a0') is None and sc is not None and not sc['observed']:
        what = 'the selected %s' % _clip(sc.get('label') or 'units')
        return '%s: %s; collect %s' % (REASON_WORDS['not_observed'], what, what)
    m = _machines(env) or {'refused': []}
    reasons = [str(r.get('reason') or '') for r in m['refused'] if isinstance(r, dict)]
    if env.get('a0') is None and reasons and all(r.startswith('not observed') for r in reasons):
        loc = re.search(r'raw/[A-Za-z0-9_./#\[\]=-]{1,200}', reasons[0])
        what = loc.group(0) if loc else 'the facts the machines read'
        return '%s: %s; collect %s' % (REASON_WORDS['not_observed'], what, what)
    return '%s; %s' % (REASON_WORDS['representation'], CLASS_ACTIONS['representation'])


def _yellow_action(env):
    """The action of the yellow line, the part after its reason."""
    return _could_not_look_words(env).split('; ', 1)[1]


def _yes(v):
    return 'yes' if v is True else 'no'


def completion_line(envelope, now=None):
    """Coordination 2102 A25: 'Usable readings: c of n. Coverage complete: yes|no. Job stops: no (exit 0 by your
    fail-on)|yes (exit <n>).' (REFUTATION-028-R2, R2-10 c), with
    'Collected at <time>, <s> s before this summary.' when the sidecar named a collection time (`now`, seconds since
    the epoch, defaults to the clock); None for an envelope without `completion`."""
    c = envelope.get('completion') if isinstance(envelope, dict) else None
    if not isinstance(c, dict):
        return None
    u = c.get('usable_readings') if isinstance(c.get('usable_readings'), dict) else {}
    code = (envelope.get('policy') or {}).get('exit') if isinstance(envelope.get('policy'), dict) else None
    # R2-10 (c): whether the job stops, in closed words, never "passes" beside a red line
    stops = 'no (exit 0 by your fail-on)' if code == 0 else 'yes (exit %s)' % (code if type(code) is int else '?')
    text = 'Usable readings: %s of %s. Coverage complete: %s. Job stops: %s.' % (
        u.get('count') if type(u.get('count')) is int else '?', u.get('of') if type(u.get('of')) is int else '?',
        _yes(c.get('coverage_complete')), stops)
    at = (c.get('snapshot') or {}).get('collected_at') if isinstance(c.get('snapshot'), dict) else None
    if isinstance(at, str):
        import datetime
        import time
        try:
            t = datetime.datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp()
            fresh = ', %d s before this summary' % max(0, int((time.time() if now is None else now) - t))
        except ValueError:
            fresh = ''
        text += ' Collected at %s%s.' % (_clip(at), fresh)
    loaded = (c.get('snapshot') or {}).get('loaded_state') if isinstance(c.get('snapshot'), dict) else None
    if isinstance(loaded, str) and loaded:          # A25 (REFUTATION-028 F6): the loaded-state identity, as collected
        text += ' Loaded state: %s.' % _clip(label(loaded))
    return text


def _obligation_rows(env):
    return [r for r in _rows(env) if r.get('id') is not None]


def verdict_line(envelope):
    """serve-016: the one first line (module docstring), plain text with every part bounded; None for an envelope
    without `colour` (an older server). One denominator per line (REFUTATION-028 F7): N counts every obligation reading;
    established counts the holds on machines that were read."""
    env = envelope if isinstance(envelope, dict) else {}
    c = env.get('colour')
    if c not in COLOURS:
        return None
    if c == 'yellow':
        return 'yellow: could not look: %s' % _could_not_look_words(env)
    parts = [p for p in (_coverage_words(env), _bounds_words(env), _prove_words(env), _strict_words(env)) if p]
    read = _read_set(env)
    obligations = _obligation_rows(env)
    deviations = len([r for r in obligations if r.get('status') == 'deviates' and r.get('machine') in read])
    if c == 'red':
        if deviations:                                # 2073 N2: deviations are their own count
            parts.append('deviations: %d' % deviations)
        lead = lead_finding(env)
        words = _red_words(env, lead) if lead else 'disproven'
        pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
        if pol.get('exit') == 0:                      # REFUTATION-028 F1, Q3: red, and the exit the customer chose
            words += ' (exit 0 by your fail-on: %s)' % (_clip(','.join(pol.get('fail_on') or ())) or 'never')
        elif pol.get('exit') == 1:                    # R2-2: the finding that set exit 1, when the line leads with another
            binding = binding_findings(env)
            if binding and lead is not None and lead not in binding:
                kind, b_id, b_row = binding[0]
                if binding_reason(env, binding[0]) == 'not_proven':
                    kind = 'not_proven'
                b_id = _clip(b_id if b_id is not None else (b_row or {}).get('machine'))
                what = {'not_proven': 'not proven', 'strict': 'unresolved (strict)'}.get(
                    kind, _clip(label((b_row or {}).get('status'))))
                if kind == 'not_proven':                  # the bias binds it, not fail-on (DD-076 rail 1)
                    words += ' (exit 1: not proven — %s)' % b_id
                else:
                    words += ' (exit 1 by your fail-on: %s — %s)' % (what, b_id)
        parts.append(words)
        return '%s: %s' % (c, '; '.join(parts))
    held = len([r for r in obligations if r.get('status') == 'holds' and r.get('machine') in read])
    entries = [e for e in env.get('not_established') or () if isinstance(e, dict)]
    # R5-3: an entry strict added for an obligation with no reading counts in N too, so the parts add up
    with_rows = {r.get('id') for r in obligations}
    obligations = obligations + [{'id': e.get('id')} for e in entries if e.get('id') not in with_rows]
    if held:                      # coordination 2098 A21: no holds reads in words, never as a count of success
        parts += ['nothing disproven', 'established: %d of %d' % (held, len(obligations))]
    else:
        parts.append('nothing could be established (0 of %d obligations hold)' % len(obligations))
    if deviations:
        parts.append('deviations: %d' % deviations)
    tail = 'not established: %d' % len(entries)
    top = top_entry(entries)
    if top is not None:                               # 2129 W2, W3: the count becomes a path
        tail += ' — top action: %s%s' % (_clip(top.get('action')), _quote_words(top.get('quote')))
    parts.append(tail)
    return '%s: %s' % (c, '; '.join(parts))


def lead_finding(envelope):
    """The finding the red first line names: the first of `red_findings`, or, when nothing could be read (a
    prove-class obligation keeps the colour red, DD-073 Addendum 1), the first prove-class one."""
    found = red_findings(envelope)
    if found and could_not_look(envelope):
        return next((f for f in found if f[0] == 'not_proven'), found[0])
    return found[0] if found else None


def top_entry(entries):
    """2129 W2/W3: the not-established entry whose action stands for the most frequent reason class (the first seen on
    a tie), leaving out the representation fallback when any other class is present; None when there is none."""
    entries = [e for e in entries if isinstance(e, dict) and isinstance(e.get('action'), str) and e.get('action')]
    if not entries:
        return None
    counts, first = {}, []
    for e in entries:
        cls = e.get('reason_class')
        if cls not in counts:
            first.append(cls)
        counts[cls] = counts.get(cls, 0) + 1
    pool = [k for k in first if k != 'representation'] or first
    top = max(pool, key=lambda k: (counts[k], -first.index(k)))
    return next(e for e in entries if e.get('reason_class') == top)


# ---------- DD-073 Addendum 2 (heading 2133): the plain-language layer, closed templates, no model ----------
# The subject and the family each profile's meaning sentence names, by the profile id's first word.
PROFILE_WORDS = {'postgresql': ('database configuration', 'PostgreSQL'), 'http': ('HTTP responses', 'HTTP')}
DEFAULT_PROFILE_WORDS = ('system', 'software')
# Why a check could not be completed, for "mostly because ...", one per closed reason class.
CLASS_BECAUSE = {'needs_intent': 'they depend on what the system is for, which has not been stated',
                 'not_observed': 'some facts were not collected',
                 'missing_baseline': 'the baselines for this major version are not pinned yet',
                 'missing_method': 'Assure has no method yet for some of these shapes',
                 'representation': 'some input could not be represented'}


def _profile_words(env):
    pid = env.get('profile') if isinstance(env.get('profile'), str) else ''
    return PROFILE_WORDS.get(pid.split('-', 1)[0], DEFAULT_PROFILE_WORDS)


def _sentence(text):
    t = _clip(text).strip().rstrip('.')
    return (t[:1].upper() + t[1:] + '.') if t else ''


def consequence(env, ob_id):
    """The obligation's consequence sentence from the profile (`consequences`, carried from the checker's PROFILE.json),
    or "Consequence not yet stated for <id>." — never invented."""
    c = env.get('consequences') if isinstance(env.get('consequences'), dict) else {}
    text = c.get(ob_id) if isinstance(c.get(ob_id), str) and c.get(ob_id).strip() else None
    return _sentence(text) if text else 'Consequence not yet stated for %s.' % _clip(ob_id)


def meaning_line(envelope):
    """DD-073 Addendum 2 (a): one sentence (or two) under the first line saying what it means, from a closed template
    per colour; None for an envelope without `colour`.
    - green: "Nothing in your <subject> contradicts what is known about safe <family> setups. <n> of <N> checks could
      not be completed, mostly because <the top reason class in words>. That is a gap in what we could see; your
      <subject> is unchanged by it." ("All <N> checks could be completed." when n is 0);
    - red: the first finding's consequence, then for a disproof "The finding is at <locator> (<object>, <access
      path>)." when its witness names a locator, else "The reading <id> fails; the record carries no witness to point
      at.", and for the other kinds what was chosen or not proven;
    - yellow: "We could not read the collected files, so nothing below is a finding about your <subject>. <Action>."."""
    env = envelope if isinstance(envelope, dict) else {}
    c = env.get('colour')
    if c not in COLOURS:
        return None
    subject, family = _profile_words(env)
    if c == 'yellow':
        return ('We could not read the collected files, so nothing below is a finding about your %s. %s'
                % (subject, _sentence(_yellow_action(env))))
    if c == 'green':
        entries = [e for e in env.get('not_established') or () if isinstance(e, dict)]
        n_all = len(_obligation_rows(env))
        head = 'Nothing in your %s contradicts what is known about safe %s setups.' % (subject, family)
        top = top_entry(entries)
        if not entries or top is None:
            return '%s All %d checks could be completed.' % (head, n_all)
        because = CLASS_BECAUSE.get(top.get('reason_class'), CLASS_BECAUSE['representation'])
        # heading 2203 (the Director's "state the positive" rule): no "x, not y" tail
        verb = 'are' if subject.endswith('s') else 'is'          # "your HTTP responses are unchanged by it"
        return ('%s %d of %d checks could not be completed, mostly because %s. That is a gap in what we could see; your '
                '%s %s unchanged by it.' % (head, len(entries), n_all, because, subject, verb))
    lead = lead_finding(env)
    if lead is None:
        return None
    kind, ob_id, row = lead
    ob_id = ob_id if ob_id is not None else (row or {}).get('machine')
    first = consequence(env, ob_id)
    if kind == 'disproven' and row is not None:
        obj, path, locator = _witness_fields(env, row)
        if locator is not None:                       # the coordinator's closed words, before the freeze
            where = ', '.join(x for x in (obj, path) if x is not None)
            return '%s The finding is at %s%s.' % (first, locator.rstrip('.'), ' (%s)' % where if where else '')
        return '%s The reading %s %s; the record carries no witness to point at.' % (
            first, _clip(ob_id), _clip(label(row.get('status'))))
    if kind == 'not_proven':
        return '%s %s is a prove-class obligation, and it was not proven.' % (first, _clip(ob_id))
    if kind == 'strict':
        return '%s %s is marked security, it is not resolved, and you chose strict.' % (first, _clip(ob_id))
    return ('%s %s reads %s, a status you chose to stop on.'          # R2-2: never asserts nothing is disproven
            % (first, _clip(ob_id), _clip(label((row or {}).get('status')))))


def _witness_fields(env, row):
    """(object, access path, locator) of the row's first witness in `readings`, each bounded or None; all None when
    the reading carries no witness object."""
    w = None
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
        if isinstance(ob, dict):
            ws = ob.get('witnesses')
            w = ws[0] if isinstance(ws, list) and ws else ob.get('witness')
    except (AttributeError, TypeError):
        w = None
    if not isinstance(w, dict):
        return None, None, None
    flow = w.get('flow') if isinstance(w.get('flow'), dict) else {}
    records = w.get('records') if isinstance(w.get('records'), list) else []
    out = []
    for options in ((w.get('object'), w.get('role'), w.get('owner'), flow.get('user'), flow.get('role')),
                    (w.get('path'), w.get('command'), w.get('rule_id'), flow.get('transport'), flow.get('name')),
                    (w.get('locator'), records[0] if records else None)):
        v = next((x for x in options if _scalar(x)), None)
        out.append(_clip(v) if v is not None else None)
    return tuple(out)


def why_lines(envelope):
    """DD-073 Addendum 2 (b): one line per disproven or deviating obligation (the envelope's `why`): "<id>: <its
    statement> <its consequence>", the statement from the reading (or the profile) and the consequence from the profile,
    "Consequence not yet stated for <id>." where it gives none. Plain text, bounded."""
    env = envelope if isinstance(envelope, dict) else {}
    out = []
    for w in env.get('why') or ():
        if not isinstance(w, dict):
            continue
        statement = _sentence(w.get('statement')) if isinstance(w.get('statement'), str) else ''
        out.append(('%s: %s %s' % (_clip(w.get('id')), statement, consequence(env, w.get('id')))).replace('  ', ' '))
    return out


def _strict_words(env):
    """2073 N6: 'strict: no obligations marked' when the strict preset is set and the profile marks no obligation."""
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    b = env.get('bias') if isinstance(env.get('bias'), dict) else {}
    if STRICT in (pol.get('fail_on') or ()) and not b.get('security'):
        return 'strict: no obligations marked'
    if STRICT in (pol.get('fail_on') or ()):           # the security obligations the collector pin can observe
        sec = list(b.get('security') or ())
        seen = [i for i in sec if i not in set(b.get('unobservable') or ())]
        return 'strict: %d of %d security obligations observable at this pin' % (len(seen), len(sec))
    return None


def _outcome_words(env):
    if env.get('a0') is not None:
        return 'No reading: input integrity'
    if env.get('outcome') != 'verdict':
        return 'No verdicts'
    return 'Readings'


def _headline(env):
    line = first_line(env)
    words = _outcome_words(env)
    return words if line is None else '%s. %s' % (line, words)


def summary_markdown(envelope, now=None):
    env = envelope
    precedence = list(env.get('vocabulary', {}).get('precedence') or sorted(env.get('counts', {})))
    counts = env.get('counts', {})
    policy = env.get('policy', {})
    fail_on = policy.get('fail_on') or []
    line = verdict_line(env)                      # serve-016: the one first line, then the not-established list
    out = ['## Assure: %s' % (_headline(env) if line is None else _esc_line(line)), '']
    meaning = meaning_line(env)                   # DD-073 Addendum 2 (a): what the first line means, in plain words
    if line is not None and meaning:
        out += [_esc_line(meaning), '']
    up_front = scope_notes_line(env)              # serve-012: a selected scope's bound sits under the headline
    if up_front is not None:
        out += ['Scope: %s' % esc(up_front), '']
    done = completion_line(env, now)              # coordination 2102 A25: three answers under the first line
    if line is not None and done is not None:
        out += [_esc_line(done), '']
    unsupported = set(((env.get('completion') or {}).get('unsupported') or {}).get('ids') or ())
    entries = [e for e in env.get('not_established') or () if isinstance(e, dict)] if line is not None else []
    gaps = [e for e in entries if e.get('id') not in unsupported]
    if env.get('colour') == 'green' and gaps:
        out += ['- %s' % _esc_line(not_established_line(e, env)) for e in gaps[:MAX_ANNOTATIONS]]
        if len(gaps) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(gaps) - MAX_ANNOTATIONS))
        out.append('')
    limits = [e for e in entries if e.get('id') in unsupported]
    if limits:                                    # A25: the profile's own limits, apart from the customer's gaps
        out += ['### Unsupported by this profile version: %d' % len(limits), '']
        out += ['- %s' % _esc_line(not_established_line(e, env)) for e in limits[:MAX_ANNOTATIONS]]
        if len(limits) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(limits) - MAX_ANNOTATIONS))
        out.append('')
    why = why_lines(env) if line is not None else []
    if why:                                       # DD-073 Addendum 2 (b): why each disproof or deviation matters
        out += ['### Why it matters', '']
        out += ['- %s' % _esc_line(w) for w in why[:MAX_ANNOTATIONS]]
        if len(why) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(why) - MAX_ANNOTATIONS))
        out.append('')
    out.append('Profile %s, check %s.' % (esc(env.get('profile')), esc(env.get('check_id'))))
    reason = policy.get('reason')
    code = esc(policy.get('exit'))
    machines = _machines(env)
    # serve-016: with the verdict line as the headline, the contract's words (section 5) lead the body instead
    lead_a0, lead_nv = ('No reading: input integrity. ', 'No verdicts: ') if line is not None else ('', '')
    if env.get('a0') is not None:
        out.append('')
        out.append('%sThe input integrity gate stopped the check, so no obligation was read: %s'
                   % (lead_a0, esc(env.get('a0'))))
        named_file = re.search(r'raw/[A-Za-z0-9_./-]{1,200}', str(env.get('a0')))   # R2-7: what the yellow line means
        if named_file:
            out.append('The file it names: %s.' % esc(named_file.group(0).rstrip('.')))
    elif env.get('outcome') != 'verdict':
        out.append('')
        out.append('%sNone of the readings is a verdict that checked something; a vacuous reading only says a domain '
                   'was empty. Read each status below for what was and was not checked.' % lead_nv)
    statuses = [s for s in fail_on if s != STRICT]
    strict = ', or when an obligation marked security is not resolved (strict)' if STRICT in fail_on else ''
    if statuses:                                  # R2-10 (b): the sentence names strict when it is set
        out.append('Policy: the job stops with exit 1 when any reading is %s%s.'
                   % (' or '.join(esc(label(s)) for s in statuses), strict))
    if not fail_on and reason == 'not_proven':    # REFUTATION-028-R6, R6-2: never, and the bias binds exit 1
        out.append('Policy: readings never stop the job. This run: exit %s, because a prove-class obligation is not '
                   'proven.' % code)
    elif reason == 'never' or not fail_on:
        out.append('Policy: readings never stop the job. This run: exit %s.' % code)
    elif reason == 'could_not_look':              # serve-016: the three new reasons
        out.append('Could not look: nothing could be read, so the job stops with exit %s.' % code)
    elif reason == 'disproven' and policy.get('exit') == 0:     # REFUTATION-028 F1: red, exit as fail-on chose
        out.append('This run: exit %s. Something is disproven, and your fail-on leaves its status out, so the job does '
                   'not stop.' % code)
    elif reason == 'disproven':
        kind = (lead_finding(env) or ('disproven', None, None))[0]
        out.append({'disproven': 'This run: exit %s, because a reading has a status the policy fails on.',
                    'not_proven': 'This run: exit %s, because a prove-class obligation is not proven.',
                    'strict': 'This run: exit %s, because an obligation marked security is not resolved and strict is '
                              'set.',
                    'chosen': 'This run: exit %s, because a reading has a status you chose to stop on.'}[kind] % code)
    elif reason == 'not_proven':                  # R2-10 (a)
        out.append('This run: exit %s, because a prove-class obligation is not proven.' % code)
    elif reason == 'unresolved_strict':
        out.append('This run: exit %s, because an obligation marked security is not resolved and strict is set.' % code)
    elif reason == 'stopped_by_choice':           # REFUTATION-028 F2; R2-2: never asserts that nothing is disproven
        out.append('This run: exit %s. The job stopped on a status you named in fail-on; the colour above says whether '
                   'anything is disproven.' % code)
    elif reason == 'nothing_disproven':
        out.append('This run: exit %s. Within these bounds, nothing disproven.' % code)
        if (machines is not None and machines['refused']) or (_scope(env) or {}).get('refused'):
            out.append('What could not be read is listed below; it bounds the result and does not stop the job.')
    elif reason == 'input_integrity':
        out.append('No reading: the input integrity gate stopped the check, so the job stops with exit %s.' % code)
    elif reason == 'no_verdict':
        out.append('No verdicts: nothing was checked, so the job stops with exit %s.' % code)
    elif reason == 'policy_failed':
        out.append('This run: exit %s, because a reading has a status the policy fails on.' % code)
    elif reason == 'machines_refused':
        out.append('Some machines could not be read, so the job stops with exit %s: the readings cover only the '
                   'machines that were read. Set allow-partial to accept a partial read.' % code)
    elif reason == 'scope_refused':
        sc = _scope(env) or {}
        out.append('Some selected %s were not %s, so the job stops with exit %s: the readings cover only what was '
                   '%s. Set allow-partial to accept a partial read.'
                   % (esc(sc.get('label') or 'units'), esc(sc.get('verb') or 'observed'), code,
                      esc(sc.get('verb') or 'observed')))
    elif policy.get('allow_partial') is True and ((machines is not None and machines['refused'])
                                                  or (_scope(env) or {}).get('refused')):
        out.append('This run: exit %s. allow-partial is set, so the machines that could not be read do not stop the '
                   'job.' % code)
    else:
        out.append('This run: exit %s.' % code)
    out += ['', '| Status | Count |', '| --- | --- |']
    for s in precedence:
        out.append('| %s | %d |' % (esc(label(s)), int(counts.get(s, 0))))
    rows = env.get('rows') or []
    kept = [r for r in rows if kept_on_refused(env, r)] if line is not None else []
    if kept:                                      # R3-1 (ii): the raw counts stand; the kept rows are coverage
        out += ['', 'Readings the checker kept on refused machines and read as not observed: %d.' % len(kept)]
        rows = [r for r in rows if not any(r is k for k in kept)]
    for s in precedence:
        group = [r for r in rows if r.get('status') == s]
        if not group:
            continue
        out += ['', '### %s' % esc(label(s)), '']
        for r in group:
            where = esc(r.get('machine')) + (' ' + esc(r.get('id')) if r.get('id') is not None else '')
            line = '- %s: %s' % (where, esc(r.get('status_text')))
            extra = _row_extra(env, r)
            if extra:
                line += ' (%s)' % extra
            out.append(line)
    if machines is not None and machines.get('source') == 'inferred' and not machines['refused']:
        out += ['', 'The checker did not report which machines it refused; which machines were read is inferred from the '
                'readings.']
    if machines is not None and machines['refused']:
        out += ['', '### Machines not read', '']
        if machines.get('source') == 'inferred':
            out += ['The checker did not report which machines it refused; this list is inferred from the readings.', '']
        for r in machines['refused']:
            r = r if isinstance(r, dict) else {}
            out.append('- %s: %s' % (esc(r.get('machine')), _reason(r.get('reason'))))
            for k in kept:                            # R3-1 (ii): under its refused machine, never under its status
                if k.get('machine') == r.get('machine'):
                    out.append('- %s refused — %s %s' % (esc(k.get('machine')), esc(k.get('id')), KEPT_WORDS))
    sc = _scope(env)
    if sc is not None and sc['refused']:
        out += ['', '### %s not %s' % (esc(str(sc.get('label') or 'units').capitalize()),
                                       esc(sc.get('verb') or 'observed')), '']
        for r in sc['refused'][:MAX_ANNOTATIONS]:
            r = r if isinstance(r, dict) else {}
            out.append('- %s: %s' % (esc(r.get('id')), esc(r.get('reason'))))
        if len(sc['refused']) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(sc['refused']) - MAX_ANNOTATIONS))
    withheld = env.get('not_observed_lines')
    if isinstance(withheld, list) and withheld:
        out += ['', '### Not observed: lines the collector withheld', '',
                'The collector withheld these rules or settings whole; the check read each one as not observed.', '']
        for item in withheld[:MAX_ANNOTATIONS]:
            out.append('- %s' % esc(_withheld_line(item)))
        if len(withheld) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(withheld) - MAX_ANNOTATIONS))
    notes = env.get('scope_notes') or []
    if notes:
        out += ['', '### Scope', '']
        out += ['- %s' % esc(n) for n in notes]
    return '\n'.join(out) + '\n'


_CONTROL_BUT_NEWLINES = re.compile(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]')


def _cmd_data(value, cap=CAP):
    s = '' if value is None else str(value)
    s = s if cap is None or len(s) <= cap else s[:cap - 1] + '…'
    s = _CONTROL_BUT_NEWLINES.sub(' ', s)
    return s.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def _cmd_prop(value):
    return _cmd_data(value).replace(':', '%3A').replace(',', '%2C')


def scope_notes_line(envelope):
    """serve-012: the row's scope notes as one line for an envelope whose scope unit is not a machine (it carries
    `scope_observed`), else None. That bound (for the HTTP row: freshness, replay, intent-only coverage) is shown under
    the headline, as the first annotation and in the Action's log, not only at the summary's end. A machine-scoped
    envelope (both PostgreSQL rows) renders as before."""
    notes = envelope.get('scope_notes') if isinstance(envelope, dict) else None
    if _scope(envelope) is None or not isinstance(notes, list) or not notes:
        return None
    return ' '.join(str(n) for n in notes)


def annotations(envelope):
    """`::error` for fails and `::warning` for deviates, fails first, at most fifty; first, for a selected scope, one
    `::notice` with its scope notes (`scope_notes_line`). serve-016: before them, the verdict line as the one first
    notice; under the strict preset, after them, one `::notice` per not-established obligation (at most fifty)."""
    rows = envelope.get('rows') or []
    if envelope.get('colour') in COLOURS:         # R2-1: a row the checker kept on a refused machine is coverage
        read = _read_set(envelope)
        rows = [r for r in rows if r.get('machine') in read]
    picked = [('error', r) for r in rows if r.get('status') == 'fails']
    picked += [('warning', r) for r in rows if r.get('status') == 'deviates']
    lines = []
    first = verdict_line(envelope)
    if first is not None:
        lines.append('::notice title=Assure::%s' % _cmd_data(first, cap=None))
    notes = scope_notes_line(envelope)
    if notes is not None:
        lines.append('::notice title=%s::%s' % (_cmd_prop('Assure scope'), _cmd_data(notes)))
    for level, r in picked[:MAX_ANNOTATIONS]:
        where = '%s %s' % (r.get('machine'), r.get('id')) if r.get('id') is not None else str(r.get('machine'))
        title = 'Assure %s %s' % (label(r.get('status')), where)
        msg = str(r.get('status_text') or '')
        if _extra_reason(r):
            gloss = bound_gloss(r.get('reason'))
            msg += ' (%s%s)' % (r.get('reason'), '; %s' % gloss if gloss else '')
        elif r.get('status') == 'fails' and witness_text(envelope, r):
            msg += ' (%s)' % witness_text(envelope, r)
        lines.append('::%s title=%s::%s' % (level, _cmd_prop(title), _cmd_data(msg)))
    if first is not None and STRICT in ((envelope.get('policy') or {}).get('fail_on') or ()):
        for e in [e for e in envelope.get('not_established') or () if isinstance(e, dict)][:MAX_ANNOTATIONS]:
            lines.append('::notice title=%s::%s' % (_cmd_prop('Assure not established %s' % e.get('id')),
                                                    _cmd_data(not_established_line(e, envelope))))
    return lines


def _withheld_line(item):
    """'not observed: raw/pg_hba.conf line 4 (<the reason in plain words>[; setting <name>])' for one item."""
    item = item if isinstance(item, dict) else {}
    setting = item.get('setting')
    return 'not observed: %s line %s (%s%s)' % (item.get('file'), item.get('line'), item.get('text') or 'a withheld line',
                                               '; setting %s' % setting if setting else '')


def _malformation_line(m):
    if not isinstance(m, dict) or not isinstance(m.get('kind'), str):
        return None
    where = []
    if m.get('file'):
        where.append(str(m['file']))
    if m.get('line') is not None:
        where.append('line %s' % m['line'])
    if m.get('field'):
        where.append('field %s' % m['field'])
    return 'What was malformed: %s%s. Expected: %s.' % (m['kind'].replace('_', ' '),
                                                       (' (%s)' % ', '.join(where)) if where else '', m.get('expected'))


NOT_SENT = 'No check was sent.'
NO_ID_BACK = 'No check id came back from the API.'
API_REFUSED = 'The API refused the request before a check started; the collected files were sent and not kept.'
PROFILES_REFUSED = ('The API refused the request for the profile list before anything was collected; nothing from '
                    'your system was sent.')
POLL_REFUSED = 'The check was sent; the API refused the poll for its result.'
ANSWERED = ('profiles', 'check', 'poll')          # the request the API answered, as the client records it


def check_line(failure_envelope):
    """The last line of a failure page, from the request the API answered (`detail.answered`, set by the client):
    - 'profiles' (`GET /v1/profiles`, before anything was collected): PROFILES_REFUSED;
    - the server's check id came back (`detail.check_id` equals `check_id`): 'Check <id>.';
    - 'poll' (`GET /v1/checks/{id}` refused without the id): 'Check <id>. ' + POLL_REFUSED, the id from the 202
      (`detail.sent_check_id`), or POLL_REFUSED alone when it is not known;
    - 'check' (`POST /v1/checks`, the upload left the runner): API_REFUSED;
    - a delivery failure, or an `answered` mark this renderer does not know: NO_ID_BACK (the request may have left
      the runner);
    - no mark, a refusal in the runner before anything was sent: NOT_SENT."""
    f = failure_envelope
    cid = f.get('check_id')
    detail = f.get('detail') if isinstance(f.get('detail'), dict) else {}
    answered = detail.get('answered')
    typed = f.get('outcome') not in ('api_unreachable', 'api_error')
    if answered == 'profiles' and typed:
        return PROFILES_REFUSED
    if isinstance(cid, str) and cid and detail.get('check_id') == cid:
        return 'Check %s.' % esc(cid)
    if answered == 'poll' and typed:
        sent = detail.get('sent_check_id')
        if isinstance(sent, str) and re.fullmatch(r'[0-9a-f]{32}', sent) and sent == cid:
            return 'Check %s. %s' % (sent, POLL_REFUSED)
        return POLL_REFUSED
    if answered == 'check' and typed:
        return API_REFUSED
    if not typed or 'answered' in detail:
        return NO_ID_BACK
    return NOT_SENT


# Refutation-010 F1: a bad_input whose cause is a workflow input, not a file, gets a next step naming the input instead
# of the files sentence. Matched on the fixed reason text the Action writes; the step is fixed text.
_INPUT_STEPS = (
    (re.compile(r'fail-on '), 'Set fail-on in the workflow step to a comma list of statuses (for example '
                              'fails,deviates) or to never, then run again.'),
    (re.compile(r'allow-partial '), 'Set allow-partial in the workflow step to true or false, then run again.'),
    (re.compile(r'no raw/ directory under the artefacts path|the raw directory is a link or not a directory'),
     'Point artefacts in the workflow step at the directory that holds raw/ (a path relative to the workspace, or '
     'absolute), then run again.'),
    (re.compile(r'(?:mode|output|api-url|api-key|data-dir|config-dirs|collection-role|collection-privileges'
                r'|connection)\b|set exactly one of connection and artefacts|the user in the connection'
                r'|local mode is not available'),
     'Fix the workflow step input the reason names, then run again.'),
)


def next_step(failure_envelope):
    """The 'What to do' text: the input's own step for a bad_input caused by a workflow input, else `action`."""
    f = failure_envelope
    detail = f.get('detail') if isinstance(f.get('detail'), dict) else {}
    if f.get('outcome') == 'bad_input' and 'answered' not in detail:
        reason = str(f.get('reason') or '')
        for pattern, text in _INPUT_STEPS:
            if pattern.match(reason):
                return text
    return f.get('action')


# SELFHOSTED-001: a fixed next step for the connection errors a first run meets. Matched on the error text psql gives;
# the hint itself is fixed text and never repeats a name from the reason.
_HINTS = (
    ('collector_cannot_connect', re.compile(r'permission denied for database'),
     'Grant the collection role CONNECT on the database: GRANT CONNECT ON DATABASE <your database> TO <the collection '
     'role>; (quick start section 2).'),
    ('collector_cannot_connect', re.compile(r'no pg_hba\.conf entry'),
     'Add a pg_hba.conf rule for the collection role from the runner\'s address, then reload the server (quick start '
     'section 2).'),
    ('collector_cannot_connect', re.compile(r'root certificate file|certificate verify failed'),
     'sslmode=verify-full needs a server certificate the runner trusts: give it with sslrootcert=, or use '
     'sslmode=require (quick start section 3).'),
)


def hint_line(failure_envelope):
    """'Next step: ...' for a failure whose reason matches a known first-run error, or None."""
    f = failure_envelope
    reason = str(f.get('reason') or '')
    for outcome, pattern, text in _HINTS:
        if f.get('outcome') == outcome and pattern.search(reason):
            return 'Next step: %s' % text
    return None


def failure_markdown(failure_envelope):
    f = failure_envelope
    hint = hint_line(f)
    return '\n'.join(['## Assure: no reading', '',
                      'Outcome: %s.' % esc(f.get('outcome')), '',
                      'Reason: %s' % esc(f.get('reason')), '',
                      'What to do: %s' % esc(next_step(f)), ''] +
                     ([esc(hint), ''] if hint else []) +
                     ([esc(_malformation_line(f['detail'].get('malformation'))), '']
                      if isinstance(f.get('detail'), dict) and _malformation_line(f['detail'].get('malformation'))
                      else []) +
                     [check_line(f)]) + '\n'

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
