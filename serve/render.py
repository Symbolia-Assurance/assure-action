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
            if _extra_reason(r):
                line += ' (%s)' % esc(r.get('reason'))
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
            out.append('- %s: %s' % (esc(r.get('machine')), esc(r.get('reason'))))
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


def annotations(envelope):
    """`::error` for fails and `::warning` for deviates, fails first, at most fifty."""
    rows = envelope.get('rows') or []
    picked = [('error', r) for r in rows if r.get('status') == 'fails']
    picked += [('warning', r) for r in rows if r.get('status') == 'deviates']
    lines = []
    for level, r in picked[:MAX_ANNOTATIONS]:
        where = '%s %s' % (r.get('machine'), r.get('id')) if r.get('id') is not None else str(r.get('machine'))
        title = 'Assure %s %s' % (label(r.get('status')), where)
        msg = str(r.get('status_text') or '')
        if _extra_reason(r):
            msg += ' (%s)' % r.get('reason')
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


def failure_markdown(failure_envelope):
    f = failure_envelope
    return '\n'.join(['## Assure: no reading', '',
                      'Outcome: %s.' % esc(f.get('outcome')), '',
                      'Reason: %s' % esc(f.get('reason')), '',
                      'What to do: %s' % esc(f.get('action')), ''] +
                     ([esc(_malformation_line(f['detail'].get('malformation'))), '']
                      if isinstance(f.get('detail'), dict) and _malformation_line(f['detail'].get('malformation'))
                      else []) +
                     ['Check %s.' % esc(f.get('check_id'))]) + '\n'

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
