"""The job summary (Markdown) and GitHub annotations for a verdict envelope, and the summary for a failure envelope.

Wording rules (INTERFACE-CONTRACT-OB-001 section 5) bind: vacuous is never shown as holds; deviates is never called a
failure; non-verdict statuses are never shown as satisfied; a result with no verdict reads "No verdicts"; an input-integrity
gate (a0) reads "No reading: input integrity". Words only: no tick, cross or coloured symbol. Every string that could
derive from customer input is bounded to 300 characters and escaped for Markdown and HTML, and a URL, `www.` name or
e-mail address in it is shown as a code span, so it never becomes a clickable link; annotation messages and properties
are escaped per the workflow-command rules so that no value can start a new command.

The policy line states the run's exit in plain words from `policy.reason`: `policy_met`, `policy_failed`, `no_verdict`
("No verdicts: nothing was checked, so the job stops with exit 3."), `input_integrity` or `never`.
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


def _headline(env):
    if env.get('a0') is not None:
        return 'No reading: input integrity'
    if env.get('outcome') != 'verdict':
        return 'No verdicts'
    return 'Readings'


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
    if env.get('a0') is not None:
        out.append('')
        out.append('The input integrity gate stopped the check, so no obligation was read: %s' % esc(env.get('a0')))
    elif env.get('outcome') != 'verdict':
        out.append('')
        out.append('None of the readings is a verdict. Read each status below for what was and was not checked.')
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
            if r.get('reason'):
                line += ' (%s)' % esc(r.get('reason'))
            out.append(line)
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
        if r.get('reason'):
            msg += ' (%s)' % r.get('reason')
        lines.append('::%s title=%s::%s' % (level, _cmd_prop(title), _cmd_data(msg)))
    return lines


def failure_markdown(failure_envelope):
    f = failure_envelope
    return '\n'.join(['## Assure: no reading', '',
                      'Outcome: %s.' % esc(f.get('outcome')), '',
                      'Reason: %s' % esc(f.get('reason')), '',
                      'What to do: %s' % esc(f.get('action')), '',
                      'Check %s.' % esc(f.get('check_id'))]) + '\n'

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
