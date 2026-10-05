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
"""
from __future__ import annotations

import html
import re

CAP = 300
MAX_ANNOTATIONS = 50
_MD_SPECIAL = re.compile(r'([\\`*_\[\]|~])')   # customer text never starts a line, so # and - need no escape
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


def first_line(envelope):
    """The first line's coverage phrase: the scope phrase then the machines phrase for a profile scoped by another
    unit, `machines_line` otherwise (None when the envelope carries neither)."""
    scope, machines = scope_line(envelope), machines_line(envelope)
    if scope is None:
        return machines
    return scope if machines is None else '%s; %s' % (scope, machines)


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


def summary_markdown(envelope):
    env = envelope
    precedence = list(env.get('vocabulary', {}).get('precedence') or sorted(env.get('counts', {})))
    counts = env.get('counts', {})
    policy = env.get('policy', {})
    fail_on = policy.get('fail_on') or []
    out = ['## Assure: %s' % _headline(env), '']
    up_front = scope_notes_line(env)              # serve-012: a selected scope's bound sits under the headline
    if up_front is not None:
        out += ['Scope: %s' % esc(up_front), '']
    out.append('Profile %s, check %s.' % (esc(env.get('profile')), esc(env.get('check_id'))))
    reason = policy.get('reason')
    code = esc(policy.get('exit'))
    machines = _machines(env)
    if env.get('a0') is not None:
        out.append('')
        out.append('The input integrity gate stopped the check, so no obligation was read: %s' % esc(env.get('a0')))
    elif env.get('outcome') != 'verdict':
        out.append('')
        out.append('None of the readings is a verdict that checked something; a vacuous reading only says a domain was '
                   'empty. Read each status below for what was and was not checked.')
    if fail_on:
        out.append('Policy: the job stops with exit 1 when any reading is %s.' % ' or '.join(esc(label(s)) for s in fail_on))
    if reason == 'never' or not fail_on:
        out.append('Policy: readings never stop the job. This run: exit %s.' % code)
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


def _cmd_data(value):
    s = '' if value is None else str(value)
    s = s if len(s) <= CAP else s[:CAP - 1] + '…'
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
    `::notice` with its scope notes (`scope_notes_line`)."""
    rows = envelope.get('rows') or []
    picked = [('error', r) for r in rows if r.get('status') == 'fails']
    picked += [('warning', r) for r in rows if r.get('status') == 'deviates']
    lines = []
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
