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
  path>, <locator>" from the first of `red_findings` and its first witness ("disproven: k, first <id> — …" when k > 1
  are disproven, issue #1038); a prove-class obligation with no holds
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
most frequent reason class leaving out the representation fallback when any other class is present (N1; 2129 W2, W3) unless no machine's collection was read (issue #1208, `collection_unread`); deviates readings on read machines are their own count,
"deviations: d", never folded into not-established (N2); a prove-class obligation whose inputs could not be read reads
"not proven: <id> — input not observed" (N5); the strict preset with no obligation marked adds "strict: no obligations
marked" after the bounds (N6). The reason words and actions
are the closed table of DESIGN-004 section 2 (`REASON_WORDS`). Green reads "nothing disproven" within these bounds,
never "safe". An envelope without `colour` (an older server) renders as before. `red_findings` and `could_not_look`
are the policy's own tests (serve/envelope.py imports them), kept here because this module ships in the Action.

serve-019 (DD-071; DESIGN-004 Addendum 2): an envelope that carries `requirements` (the matcher's rows, sent only
when the check carried requirements.md text) adds "requirements: h hold, n not established[, d disproven]" to the
first line after the not-established count (`requirements_words`; before the finding on a red line), one line per
requirement under the not-established list ("### Requirements: ...", then '<id> — "<sentence>" — <state> — <reason
class>[ — <locator>] — <action>[ — quote USD a–b]', `requirement_line`), "<u> of <N> requirements in requirements.md could be read." after
the meaning sentence, and one annotation per requirement that does not hold (`::error` when disproven). `decide` reads
the rows as findings (`red_findings`): a disproven requirement is a disproof with its matched obligation's witness, and
one that reads not proven binds exit 1 under every fail-on; a row whose obligation is already named is listed once.

serve-014: a claim-tree report that was not written reads one line, the same on the report page and in the Action's job
summary: "The report was withheld: <reason in plain words>." (`report_withheld_line`), from REPORT_WITHHELD for the
fallback reasons; any other reason (a typed refusal's own text) is bounded and escaped like any customer string.
A written body enters the job summary through `report_markdown`: at most REPORT_CAP characters, every line HTML-escaped
with link brackets, pipes, backticks and tildes escaped and link-shaped text as a code span, so it can carry its one
bold span and its paragraphs and nothing else; `report_page_line(url)` names the page as a code span.

The pull request comment (issue #2189; the demo-grade comment, 13 Oct 2026, `pr_comment_markdown`) labels each rule by
its requirement id and sentence, says per holding rule what was checked in the checker's own words (never the default
holds sentence), reads each rule not checked yet as one plain sentence for its reason class, and closes with what
Assure read, the profile and the commit. Its one link is the file:line of a broken rule at the commit's blob on
GitHub, built only from the Action's validated repository name, a commit id and a repository path and line; customer
text in it stays a code span.
"""
from __future__ import annotations

import datetime
import html
import re
import unicodedata

from .outcomes import REPO_PATH_RE

CAP = 300
MAX_ANNOTATIONS = 50
COLLAPSE_SHARED_ACTIONS = 5     # issue #458: more rows than this sharing one next step print it once
MAX_REQUIREMENT_LINES = 256                       # serve-019: requirements.md holds at most 256 lines
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
    pair = _declared_actual_words(w)
    if pair is not None:                                 # issue #492: M7 SU-1's {declared, actual} lists
        return pair
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
    no reason, its witness; None when neither. A `fails` row whose reason is its first witness's words (issue #492,
    serve/envelope.py witness_reasons) shows the fuller witness line instead of repeating them."""
    if r.get('status') == 'fails' and (not _extra_reason(r) or r.get('reason') == witness_words(env, r)):
        w = witness_text(env, r)
        if w:
            return esc(w)
    if _extra_reason(r):
        return _reason(r.get('reason'))
    return None


def _machines(env):
    m = env.get('machines')
    if not isinstance(m, dict):
        return None
    read, refused, total = m.get('read'), m.get('refused'), m.get('total')
    if not isinstance(read, list) or not isinstance(refused, list) or type(total) is not int:
        return None
    return m


def _machines_words(env, m):
    """'5 of 8 machines read, 3 refused[, 2 out of scope][ (inferred)]': the one machines phrase every surface prints
    (serve-077 r3, REFUTATION-PR114-001 M1). A machine a scope limit names is out of scope, not refused, and leaves
    the total (3817 point 2); without a limit the phrase is byte-identical to the base's."""
    limited = scope_limited_machines(env)
    refused = [r for r in m['refused'] if not (isinstance(r, dict) and r.get('machine') in limited)]
    line = '%d of %d machines read' % (len(m['read']), int(m['total']) - len(limited))
    line += ', %d refused' % len(refused) if refused else ''
    line += ', %d out of scope' % len(limited) if limited else ''
    return line + (' (inferred)' if m.get('source') == 'inferred' else '')


def machines_line(envelope):
    """'5 of 8 machines read, 3 refused', '8 of 8 machines read, none refused', 'No machine could be read (8 refused)',
    or None when the envelope carries no `machines` block. An inferred set (`source: inferred`) says so in the phrase
    itself: '8 of 8 machines read, none refused (inferred)', 'No machine could be read (8 refused, inferred)'
    (refutation-007 G3). Scope-limited machines read as `verdict_line` reads them: '5 of 5 machines read, 3 out of
    scope', 'No machine could be read (5 refused, 3 out of scope)' (serve-077 r3, M1; #158 N7), so the report
    projection, the stored record and the Action's fallback agree."""
    m = _machines(envelope) if isinstance(envelope, dict) else None
    if m is None:
        return None
    n_read, n_refused, total = len(m['read']), len(m['refused']), int(m['total'])
    inferred = m.get('source') == 'inferred'
    if n_read == 0:
        # #158 (REFUTATION-PR114-003 N7): the scope rule `_machines_words` applies, so a scope-limited machine is
        # out of scope here too: 'No machine could be read (5 refused, 3 out of scope)'
        limited = scope_limited_machines(envelope)
        n_refused = len([r for r in m['refused'] if not (isinstance(r, dict) and r.get('machine') in limited)])
        inner = ['%d refused' % n_refused] if n_refused else []
        inner += ['%d out of scope' % len(limited)] if limited else []
        inner += ['inferred'] if inferred else []
        return 'No machine could be read' + (' (%s)' % ', '.join(inner) if inner else '')
    if n_refused == 0:
        return '%d of %d machines read, none refused' % (n_read, total) + (' (inferred)' if inferred else '')
    return _machines_words(envelope, m)


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


# serve-035 (DD-094 §7 (2); REFUTATION-036 F1): the API's replay marker. A verdict the API served from its store
# (`replay: true`) says so in the job summary's first lines, with the first check's time; a stored report's line names
# the first check's charge and this run charges nothing. A time of any other form is never printed.
FIRST_CHECKED_RE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z')
REPLAY_LINE = 'Stored verdict for the same request, first checked %s; nothing was charged this run.'
EARLIER_RUN = 'in an earlier run'


def first_checked(doc):
    """serve-035: the `first_checked_at` of an envelope as the API wrote it, or None."""
    t = doc.get('first_checked_at') if isinstance(doc, dict) else None
    return t if isinstance(t, str) and FIRST_CHECKED_RE.fullmatch(t) else None


def replay_line(envelope):
    """serve-035: "Stored verdict for the same request, first checked <time>; nothing was charged this run." for an
    envelope the API marked `replay: true`, else None."""
    if not isinstance(envelope, dict) or envelope.get('replay') is not True:
        return None
    return REPLAY_LINE % (first_checked(envelope) or EARLIER_RUN)


def report_replay_line(record, first_checked_at=None):
    """serve-035: the usage line of a stored report (`replay: true`): "Report: cost USD x.xxx, charged USD y.yyy on
    the first check <time>; nothing was charged this run", or None for a record without a line charge."""
    cost = record.get('cost') if isinstance(record, dict) else None
    if not isinstance(cost, dict) or 'charge_usd' not in cost:
        return None
    when = ('on the first check %s' % first_checked_at) if isinstance(first_checked_at, str) \
        and FIRST_CHECKED_RE.fullmatch(first_checked_at) else EARLIER_RUN
    return 'Report: cost USD %s, charged USD %s %s; nothing was charged this run' % (
        _money(cost.get('usd') or 0.0, 3), _money(cost.get('charge_usd'), 3), when)


def report_exhausted_line(needed_usd, admits=None, overage_budget_usd=None):
    """serve-015: the line for a report refused `allowance_exhausted`. serve-039 fix 2 (REFUTATION-FIX1-001 MEDIUM-2,
    LOW-4): the Action's client keeps only scalar detail values, so the line keys on `overage_budget_usd`, which every
    budget refusal carries. A budget of 0 (none set) says a top-up or a budget from Symbolia; a budget above 0 that is
    spent says a raise or a top-up. Without the figure, `admits` (a list, when the caller has it) decides as before:
    one that does not name `allow_overage` says the no-budget sentence."""
    needed = _money(needed_usd, 3)
    budget = overage_budget_usd if isinstance(overage_budget_usd, (int, float)) \
        and not isinstance(overage_budget_usd, bool) else None
    if budget is not None:
        if budget > 0:
            return 'Report: allowance exhausted: USD %s needed; ask Symbolia to raise your overage budget, or top up' % needed
        return 'Report: allowance exhausted: USD %s needed; top up, or ask Symbolia to set an overage budget' % needed
    if isinstance(admits, list) and 'allow_overage' not in admits:
        return 'Report: allowance exhausted: USD %s needed; top up, or ask Symbolia to set an overage budget' % needed
    return 'Report: allowance exhausted: USD %s needed; set allow-overage or top up' % needed


# serve-019 (DD-072 Addendum 10): the allowance line a check response's `usage` block adds when a threshold is crossed
USAGE_LINE_NAMES = {'report': 'Report allowance', 'formalisation': 'Formalisation allowance',
                    'proof_search': 'Proof search allowance'}
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def usage_notice_lines(block):
    """One line per usage line whose threshold was crossed since the last check (`crossed` true): "Report allowance:
    90 % used (USD 4.50 of 5.00); resets 1 Nov; past the limit: metered at cost x 1.2", or "...; past the limit: hard
    stop (overage budget USD 0.00)". A once-only balance (`renews` false) reads "Report allowance: 90 % used (USD
    0.90 of 1.00); does not renew; past the limit: reports stop", with ", and USD x is owed" after "does not renew"
    while something is owed. [] for none, or for a block of another shape."""
    lines = block.get('lines') if isinstance(block, dict) and isinstance(block.get('lines'), dict) else {}
    resets = block.get('resets') if isinstance(block, dict) else None
    m = re.fullmatch(r'[0-9]{4}-([0-9]{2})-([0-9]{2})', resets) if isinstance(resets, str) else None
    when = '%d %s' % (int(m.group(2)), _MONTHS[int(m.group(1)) - 1]) if m and 1 <= int(m.group(1)) <= 12 else '?'
    out = []
    for name in sorted(lines, key=lambda n: list(USAGE_LINE_NAMES).index(n) if n in USAGE_LINE_NAMES else 99):
        ln = lines[name]
        if not isinstance(ln, dict) or ln.get('crossed') is not True or name not in USAGE_LINE_NAMES:
            continue
        if ln.get('renews') is False:              # serve-032 (DD-083): a once-only balance, never reset
            debt = ln.get('debt_usd') if isinstance(ln.get('debt_usd'), (int, float)) else 0
            owed = ', and USD %s is owed' % _money(debt, 2) if debt > 0 else ''
            out.append('%s: %s %% used (USD %s of %s); does not renew%s; past the limit: reports stop' % (
                USAGE_LINE_NAMES[name], ln.get('percent') if type(ln.get('percent')) is int else '?',
                _money(ln.get('used_usd'), 2), _money(ln.get('included_usd'), 2), owed))
            continue
        if ln.get('past_limit') == 'hard_stop':
            past = 'hard stop (overage budget USD %s)' % _money(ln.get('overage_budget_usd') or 0.0, 2)
        else:
            margin = ln.get('margin') if isinstance(ln.get('margin'), (int, float)) else 0.2
            past = 'metered at cost x %s' % ('%g' % (1 + float(margin)))   # ASCII, as the docs write it
        out.append('%s: %s %% used (USD %s of %s); resets %s; past the limit: %s' % (
            USAGE_LINE_NAMES[name], ln.get('percent') if type(ln.get('percent')) is int else '?',
            _money(ln.get('used_usd'), 2), _money(ln.get('included_usd'), 2), when, past))
    return out


def report_page_line(url):
    """serve-014: the line that names the report page (the API's own URL, never customer text)."""
    return 'The report page: `%s` (send your API key in the Authorization header to open it).' % str(url).replace('`', '')


# issue #1262 (key expiry 1/5): from KEY_WARNING_DAYS before a key's `expires`, the API response (header
# Assure-Key-Warning) and the Action's summary carry this one line naming the date and the rotation path.
KEY_WARNING_DAYS = 14
KEY_EXPIRY_LINE = ('Your API key expires on %s (UTC). Rotate it before then: ask Symbolia to issue a new key for this '
                   'account and put it in the Authorization header (the Action input api-key).')


def key_expiry_line(expires, now=None):
    """The one warning line for a key whose `expires` (ISO `...Z`) is within KEY_WARNING_DAYS of `now`, else None."""
    try:
        at = datetime.datetime.strptime(expires, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if at - now > datetime.timedelta(days=KEY_WARNING_DAYS):
        return None
    return KEY_EXPIRY_LINE % expires


def first_line(envelope):
    """The first line's coverage phrase: the scope phrase then the machines phrase for a profile scoped by another
    unit, `machines_line` otherwise (None when the envelope carries neither)."""
    scope, machines = scope_line(envelope), machines_line(envelope)
    if scope is None:
        line = machines
    else:
        line = scope if machines is None else '%s; %s' % (scope, machines)
    if line is not None and http_has_needs_intent(envelope):     # serve-041 rule 3 (b)
        line += HTTP_NO_REQUIREMENT_TAIL
    return line


# serve-041: on the http-observed-baseline profile no requirements.md sentence can hold in this release, so a verdict
# with an intent-bound reading says so on its first line instead of pointing at requirements.md.
HTTP_PROFILE = 'http-observed-baseline'
HTTP_NO_REQUIREMENT_TAIL = '; no HTTP requirement can hold in this release'
HTTP_PLAIN_ACTION = ('no HTTP requirement can be stated in this release; the reading informs and asks nothing of you')
HTTP_INTENT_GROUP_ACTION = ('declare in raw/HTTP-INTENT.json the key each row names (docs/customer/VERDICTS.md); '
                            'requirements.md cannot state an HTTP requirement in this release')     # issue #2381
DEAD_END_ACTIONS = ('state it in requirements.md', 'Supply a trusted adapter binding')   # never on an HTTP row


def http_has_needs_intent(envelope):
    """True when `envelope` is an http-observed-baseline verdict with any needs_intent row or not-established entry."""
    env = envelope if isinstance(envelope, dict) else {}
    if env.get('profile') != HTTP_PROFILE:
        return False
    return (any(r.get('status') == 'needs_intent' for r in _rows(env))
            or any(isinstance(e, dict) and e.get('reason_class') == 'needs_intent'
                   for e in env.get('not_established') or ()))


LOCATOR_KEYS = frozenset({'path', 'line'})


def warning_locator(entry):
    """issue #900: (path, line) of a warning entry's optional `locator`, or None. The shape is closed: exactly the keys
    `path` (a repository path, `outcomes.REPO_PATH_RE` in full) and `line` (a positive int, not a bool); anything else
    is no locator, and the warning renders its text alone."""
    loc = entry.get('locator') if isinstance(entry, dict) else None
    if not isinstance(loc, dict) or set(loc) != LOCATOR_KEYS:
        return None
    path, line = loc['path'], loc['line']
    if not isinstance(path, str) or REPO_PATH_RE.fullmatch(path) is None:
        return None
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return None
    return path, line


def _shown_warning(entry):
    """Whether a `warnings` entry is shown to a reader: a dict with non-empty `text`, other than a `declared_ignored`
    entry for one of the seven standing flags (issue #3269: an older drafted declaration carries them, the observed
    derive drops them as it drops any key, and they are internal record flags, never a customer's declaration; the
    envelope keeps the entry as served)."""
    return isinstance(entry, dict) and isinstance(entry.get('text'), str) and bool(entry['text']) and not (
        entry.get('kind') == 'declared_ignored' and entry.get('key') in _FLAG_KEYS)


def warning_text(entry):
    """issue #900: one warning's shown text: its `text`, then " (<path>:<line>)" when it carries a locator."""
    loc = warning_locator(entry)
    return entry['text'] if loc is None else '%s (%s:%d)' % (entry['text'], loc[0], loc[1])


def warning_texts(envelope):
    """serve-041: the text of each entry of the verdict's `warnings` list (an envelope without one has none); issue #900:
    an entry with a `locator` shows it after the text as "(<path>:<line>)"."""
    env = envelope if isinstance(envelope, dict) else {}
    w = env.get('warnings')
    return [warning_text(w_) for w_ in w if _shown_warning(w_)] if isinstance(w, list) else []


WARNING_TITLES = {'endpoint_non_success': 'Assure endpoint', 'known_limit': 'Assure known limit',
                  'declared_ignored': 'Assure declaration key ignored',
                  'dynamic_registration': 'Assure dynamic registration'}


def warning_items(envelope):
    """serve-048: (kind, text) of each entry of the verdict's `warnings` list, in order, for the annotation titles."""
    env = envelope if isinstance(envelope, dict) else {}
    w = env.get('warnings')
    return [(w_.get('kind'), warning_text(w_)) for w_ in w if _shown_warning(w_)] if isinstance(w, list) else []


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
# A profile with no collector has nothing to re-collect with: its `representation` next step names its own input form.
# The one place the choice is made; every other profile keeps CLASS_ACTIONS['representation'] byte for byte.
# Issue #420: the pointer is followed by the machine's own reason (the profile's scope_notes[1]) when the row has one,
# never a fixed claim that the section is absent (the section may be present but malformed, or a field of it missing).
NO_COLLECTOR_REPRESENTATION = {
    'mysql-declared-model': 're-collect with the MySQL collector and your declaration file',
    # Issue #794: no server is contacted; the input is the repository and raw/declaration.json themselves
    'python-auth-declared-model': 'rewrite the registration the reason names as a static route registration, or move '
                                  'it outside app_roots, and resubmit the repository and declaration'}
REASON_CLIP = 200
_STRUCTURAL_REASON_CLIP = 1024
_PYTHON_INPUT_ACTION = 'review the repository or declaration input the reason names and resubmit'
_PYTHON_BOUND_ACTION = 'reduce the input to the bound the reason names and resubmit the repository and declaration'
_STRUCTURAL_REFUSAL = re.compile(r'([a-z][a-z0-9_]+) \(([^,()\r\n]{1,200}), ([1-9][0-9]*),')


def source_candidates(source, files):
    """The repository paths (raw/repository/ stripped) of the manifest `files` that a structural refusal's recorded
    `source` (a dotted module, or a file name ending .py or .html) can name: <stem>.py, <stem>/__init__.py and the
    literal name. More than one is ambiguous and is never guessed."""
    stem = source.replace('.', '/')
    names = {'raw/repository/' + stem + '.py', 'raw/repository/' + stem + '/__init__.py'}
    if source.endswith(('.py', '.html')):
        names.add('raw/repository/' + source)
    return {n[len('raw/repository/'):] for f in files or () if isinstance(f, dict)
            and isinstance(n := f.get('path'), str) and n in names}


def representation_action(profile_id=None, reason=None, files=()):
    """The next step of a `representation` row for the profile `profile_id` (None or unlisted: the engine-wide text).
    For a profile of NO_COLLECTOR_REPRESENTATION, `reason` (the row's own reason, clipped to REASON_CLIP) follows the
    pointer after ': ' when given; the pointer alone otherwise."""
    pointer = NO_COLLECTOR_REPRESENTATION.get(profile_id)
    if pointer is None:
        return CLASS_ACTIONS['representation']
    if profile_id == 'python-auth-declared-model' and isinstance(reason, dict):
        reason = (str(reason.get('reason') or '').strip() or str(reason.get('status_text') or '').strip()
                  or 'see the reason')
    original = str(reason).strip() if reason is not None else ''
    words = original[:REASON_CLIP]
    if profile_id == 'python-auth-declared-model' and words:
        if words.startswith('bound:'):
            return '%s: %s' % (_PYTHON_BOUND_ACTION, words)
        # A long source locator may finish after the displayed suffix's limit.
        match = _STRUCTURAL_REFUSAL.search(original[:_STRUCTURAL_REASON_CLIP])
        if match is None:
            return '%s: %s' % (_PYTHON_INPUT_ACTION, words)
        cls, source, line = match.groups()
        if cls != 'dynamic_registration':
            pointer = _PYTHON_INPUT_ACTION
        if files:
            if '/' not in source:
                literal = source.endswith(('.py', '.html'))
                candidates = source_candidates(source, files)
                if len(candidates) == 1:
                    source = next(iter(candidates))
                elif len(candidates) > 1:
                    source = ('source ' if literal else 'module ') + source
                elif not literal:
                    source = 'module ' + source
            return '%s at %s:%s; %s: %s' % (cls, source, line, pointer, words)
    return '%s: %s' % (pointer, words) if words else pointer


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


# ---------- serve-077 (3817): the attribution consumer ----------
# OB-ATTRIBUTION-001 (#102) puts `readings.attribution` {rule, platform, extension_members, counts, scope_limits} on the
# observed checker's output and `findings` on every reading whose witnesses name a function: {object, object_kind, owner,
# owner_class (app | unknown | platform | extension), owner_class_basis, property, writers, witness_count, fix {kind,
# statement, then} | null, fix_note}. Serving reads them and never derives them.
OWNER_CLASSES = ('app', 'unknown', 'platform', 'extension')
OTHERS_CLASSES = ('platform', 'extension')          # someone else's: Supabase's or an extension's
PLATFORM_OWNED = 'platform_owned'


def attribution_block(envelope):
    """`readings.attribution` when it is an object, else None."""
    env = envelope if isinstance(envelope, dict) else {}
    rd = env.get('readings') if isinstance(env.get('readings'), dict) else {}
    a = rd.get('attribution')
    return a if isinstance(a, dict) else None


def scope_limits(envelope):
    """The well-formed entries of `readings.attribution.scope_limits`: each with a `machines` list, `text` and
    `action` strings; [] when there are none."""
    a = attribution_block(envelope) or {}
    out = []
    for e in a.get('scope_limits') if isinstance(a.get('scope_limits'), list) else ():
        if (isinstance(e, dict) and isinstance(e.get('machines'), list) and isinstance(e.get('text'), str)
                and isinstance(e.get('action'), str)):
            out.append(e)
    return out


def scope_limited_machines(envelope):
    """The union of the scope limits' machines, within the envelope's own refused machines (3817 contract point 2;
    REFUTATION-PR114-001 L5: a limit naming a read machine never shrinks the denominator)."""
    env = envelope if isinstance(envelope, dict) else {}
    m = _machines(env)
    every = {r.get('machine') for r in m['refused'] if isinstance(r, dict)} if m is not None else None
    out = set()
    for e in scope_limits(env):
        out |= {x for x in e['machines'] if isinstance(x, str) and (every is None or x in every)}
    return out


def reading_findings(envelope, row):
    """The `findings` list of the row's own reading (each a dict with an `owner_class`), or None when the reading
    carries none."""
    env = envelope if isinstance(envelope, dict) else {}
    if not isinstance(row, dict):
        return None
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
    except (AttributeError, TypeError):
        return None
    found = ob.get('findings') if isinstance(ob, dict) else None
    if not isinstance(found, list):
        return None
    return [f for f in found if isinstance(f, dict) and f.get('owner_class') in OWNER_CLASSES]


def platform_owned(envelope, row):
    """True when the row is a `fails` reading whose findings are present, non-empty and all platform or extension:
    the disproof is someone else's (3817 contract point 1). A reading with no `findings` is the customer's, as today."""
    if not isinstance(row, dict) or row.get('status') != 'fails':
        return False
    found = reading_findings(envelope, row)
    return bool(found) and all(f.get('owner_class') in OTHERS_CLASSES for f in found)


def _findings_rows(env):
    """[(row, findings)] for every obligation row on a read machine whose reading carries findings, in row order."""
    read = _read_set(env)
    out = []
    for r in _obligation_rows(env):
        if r.get('machine') not in read or r.get('status') in MET:
            continue
        found = reading_findings(env, r)
        if found:
            out.append((r, found))
    return out


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
      vacuous) on a machine that was read (DD-079 W3: every unresolved security obligation binds, including an
      intent-bound one, reading "depends on what the system is for; state it in requirements.md", and one the pin
      could not observe, reading "not observable at collector pin <pin>"; the coverage count is observability only);
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
    # serve-077: a platform-owned disproof is listed after the customer's own, so the first line leads with theirs
    out = [f for f in out if not platform_owned(env, f[2])] + [f for f in out if platform_owned(env, f[2])]
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
        # DD-079 W3: every unresolved security obligation binds, intent-bound and unobservable at the pin included
        for i in list(bias.get('security') or ()):
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
    return out + _requirement_findings(env, out)            # serve-019: the requirement rows, after the readings


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
    (DD-076 rail 1, heading 2241: the reviewer's Q3 recommendation, Add.1's bias binds the exit). A prove-class obligation whose `fails` reading is platform-owned still binds exit 1
    as `not_proven`: it is red unless proven, and no ownership sets that aside (REFUTATION-PR114-001 L4)."""
    env = envelope if isinstance(envelope, dict) else {}
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    named = {s for s in pol.get('fail_on') or () if isinstance(s, str)} - {STRICT}
    kind, ob_id, row = finding
    status = row.get('status') if isinstance(row, dict) else None
    if isinstance(row, dict) and row.get('requirement') is not None and kind == 'not_proven':
        return 'not_proven'                        # serve-019: a prove-class requirement binds as its obligation does
    read = _read_set(env)
    held = {r.get('id') for r in _rows(env) if r.get('status') == 'holds' and r.get('machine') in read}
    # REFUTATION-028-R6, R6-1: the prove branch only when the obligation holds on no read machine
    if ob_id is not None and ob_id in _prove_ids(env) and ob_id not in held:
        return 'disproven' if kind == 'disproven' and status in named else 'not_proven'
    if not named and STRICT not in (pol.get('fail_on') or ()):
        return None
    if kind == 'disproven':
        if platform_owned(env, row):                 # serve-077 (3817 point 1): someone else's disproof never binds
            return None
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
    if never:
        return colour, 0, 'never'
    # serve-077 (3817 point 1): red with exit 0 because every disproof fail-on names is platform-owned
    named = {s for s in pol.get('fail_on') or () if isinstance(s, str)} - {STRICT}
    if any(k == 'disproven' and isinstance(r, dict) and r.get('status') in named and platform_owned(env, r)
           for k, _, r in found):
        return colour, 0, PLATFORM_OWNED
    return colour, 0, 'disproven'


# Issue #652: a not-observed entry whose reading named no gap, locator or raw/ path gets serve/envelope.py's fallback
# action 'collect the facts <id> reads'; its line says so instead of reading as a collected locator.
ACTION_SOURCES = ('row', 'class_default', 'locator_fallback')
LOCATOR_FALLBACK_WORDS = 'no locator on the row; action from the profile default'


def action_source(entry):
    """Where a not-established entry's action came from: 'locator_fallback' when a not-observed entry's action is the
    envelope's locator fallback ('collect the facts <id> reads', serve/envelope.py `_locator`); 'row' when a
    not-observed entry's action names a locator the reading itself gave (its gap, premise locator or raw/ path);
    'class_default' for every other class, whose action is the fixed text of CLASS_ACTIONS / representation_action."""
    e = entry if isinstance(entry, dict) else {}
    if e.get('reason_class') != 'not_observed':
        return 'class_default'
    if e.get('action') == 'collect the facts %s reads' % e.get('id'):
        return 'locator_fallback'
    return 'row'


def reason_words(entry, envelope=None):
    """The words of a not-established entry's reason class: "a fact was not collected: <locator>" (from its action
    'collect <locator>'; LOCATOR_FALLBACK_WORDS in the locator's place when the action is the fallback, issue #652),
    "no pinned baseline for major <n>" (from the envelope's version pins), or the class's fixed words."""
    cls = entry.get('reason_class') if isinstance(entry, dict) else None
    words = REASON_WORDS.get(cls, REASON_WORDS['representation'])
    if cls == 'not_observed':
        if action_source(entry) == 'locator_fallback':
            return '%s: %s' % (words, LOCATOR_FALLBACK_WORDS)
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


EMPTY_DOMAIN_WORDS = 'empty domain, nothing to check'


# issue #1292: the auth checker's reason when no elevation key is declared; it reads `vacuous`, or `missing_premise`
# when requirements.md claims AUTH-5 (grade.py), and either way there is nothing to elevate
EMPTY_DOMAIN_REASON = 'no elevation key is declared'
EMPTY_DOMAIN_TEXTS = ('not established (vacuous)', 'not established (missing_premise)')


def empty_domain_row(row, profile_id):
    """True for an auth row whose domain is empty (issue #1292): the checker read it `EMPTY_DOMAIN_TEXTS` because no
    elevation key is declared. An empty domain, not an input fault: it carries no owner and no action."""
    r = row if isinstance(row, dict) else {}
    return (profile_id == 'python-auth-declared-model' and r.get('status_text') in EMPTY_DOMAIN_TEXTS
            and str(r.get('reason') or '').startswith(EMPTY_DOMAIN_REASON))


def _vacuous_row(envelope, machine, ob_id):
    """The envelope's empty-domain row (`empty_domain_row`) for machine and obligation, or None."""
    env = envelope if isinstance(envelope, dict) else {}
    return next((r for r in _rows(env) if r.get('machine') == machine and r.get('id') == ob_id
                 and empty_domain_row(r, env.get('profile'))), None)


def _empty_domain(entry, envelope):
    """True for a not-established entry whose row is `_vacuous_row`."""
    return _vacuous_row(envelope, entry.get('machine'), entry.get('id')) is not None


def not_established_words(entry, envelope=None):
    """The words of a not-established line after its id: '<reason> — <owner>: <needs>[ — quote USD a–b]'; an empty
    domain (`_empty_domain`) reads '<EMPTY_DOMAIN_WORDS> — <the row's reason>', with no owner and no action."""
    e = entry if isinstance(entry, dict) else {}
    if _empty_domain(e, envelope):
        reason = _vacuous_row(envelope, e.get('machine'), e.get('id')).get('reason')
        return '%s%s' % (EMPTY_DOMAIN_WORDS, ' — %s' % _clip(reason) if reason else '')
    tail = '%s: %s' % (_clip(e['owner']), _clip(e.get('needs'))) if e.get('owner') else _clip(e.get('action'))
    return '%s — %s%s' % (_clip(reason_words(e, envelope)), tail, _quote_words(e.get('quote')))


def not_established_line(entry, envelope=None):
    """'<id>: <reason> — <owner>: <needs>[ — quote USD a–b]' for one not-established entry (coordination 2102 A22;
    plain text, parts bounded); an entry without `owner` (an earlier serve-016 envelope) shows its action."""
    e = entry if isinstance(entry, dict) else {}
    return '%s: %s' % (_clip(e.get('id')), not_established_words(e, envelope))


def not_established_lines(entries, envelope=None):
    """The summary's bullet lines for a not-established list. Issue #458: when more than COLLAPSE_SHARED_ACTIONS
    entries share the words after their id, those words print once, '- Next step for <n> obligations: <words>', with
    the ids on one sub-bullet under it, in the place of the first such entry; every other entry keeps its own line.
    The Action's annotation lines and the API's per-row `next_step` are not read from here and stay per row."""
    pairs = [(e, not_established_words(e, envelope)) for e in entries]
    groups = {}
    for e, words in pairs:
        groups.setdefault(words, []).append(e)
    out, shown = [], set()
    for e, words in pairs:
        group = groups[words]
        if len(group) <= COLLAPSE_SHARED_ACTIONS:
            out.append('- %s' % _esc_line(not_established_line(e, envelope)))
        elif words not in shown:
            shown.add(words)
            out.append('- %s' % _esc_line('Next step for %d obligations: %s' % (len(group), words)))
            out.append('  - %s' % _esc_line(', '.join(_clip(x.get('id') if isinstance(x, dict) else x) for x in group)))
    return out


NOT_OBSERVED_GROUP_ACTION = 'collect the facts each row names'


def undecided_by_cause(entries, profile_id=None):
    """Issue #1193: the not-established entries grouped by `reason_class`, one {class, rows, action, owner, ids} per
    class, ordered by row count (descending, ties by class name). `action` is the action all the group's entries share,
    for every class (the HTTP profile's needs_intent wording, a single locator, a row's own representation reason);
    when they differ, the class's fixed action: HTTP_INTENT_GROUP_ACTION for the HTTP profile's needs_intent, for
    representation `representation_action(profile_id)` without a row's
    reason, except on python-auth-declared-model, whose fallback is _PYTHON_INPUT_ACTION (its pointer is the
    dynamic-registration wording, which only a row naming that cause carries; REFUTATION-r4 HIGH-1); for every other
    class its CLASS_ACTIONS text, else NOT_OBSERVED_GROUP_ACTION."""
    groups = {}
    for e in entries or ():
        if isinstance(e, dict):
            groups.setdefault(str(e.get('reason_class') or 'representation'), []).append(e)
    out = []
    for cls, group in groups.items():
        first = group[0].get('action')
        if isinstance(first, str) and all(e.get('action') == first for e in group):
            action = first
        elif cls == 'needs_intent' and profile_id == HTTP_PROFILE:       # issue #2381: each row names its own key
            action = HTTP_INTENT_GROUP_ACTION
        elif cls == 'representation':
            action = (_PYTHON_INPUT_ACTION if profile_id == 'python-auth-declared-model'
                      else representation_action(profile_id))
        else:
            action = CLASS_ACTIONS.get(cls, NOT_OBSERVED_GROUP_ACTION)
        out.append({'class': cls, 'rows': len(group), 'action': action, 'owner': CLASS_OWNERS.get(cls),
                    'ids': [e.get('id') for e in group]})
    return sorted(out, key=lambda g: (-g['rows'], g['class']))


def decided_entries(entries, envelope=None):
    """The not-established entries the #1193 groups read: every entry but an empty domain (`_empty_domain`, issue
    #1292), which has no next step to group under."""
    return [e for e in entries or () if not (isinstance(e, dict) and _empty_domain(e, envelope))]


def undecided_lines(entries, envelope=None):
    """Issue #1193: the summary's group lines, largest first, before the per-row list: '- <n> row(s) not established
    — next step: <action> (<class label>: <reason words>)', so the first names the count and the action that decides it."""
    env = envelope if isinstance(envelope, dict) else {}
    return ['- %s' % _esc_line('%d %s not established — next step: %s (%s: %s)' % (
        g['rows'], 'row' if g['rows'] == 1 else 'rows', _clip(g['action']), label(g['class']),
        REASON_WORDS.get(g['class'], REASON_WORDS['representation'])))
        for g in undecided_by_cause(decided_entries(entries, env), env.get('profile'))]


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
        # serve-077 (3817 point 2): a machine a scope limit names is out of scope, not refused, and not in the total;
        # r3 (M1): the one phrase `machines_line` prints
        parts.append(_machines_words(env, m))
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


def row_objects(envelope, row):
    """[(object, [roles])] of an observed-profile M6 row's obligation `cases` in `readings` whose status is the row's
    own, one entry per object in the order first read, its login roles in the order read (issue #2176: derive_observed.py
    reads one case per (definer function, login), case id '<function>:<login>', and only when no function is a definer
    one V2-03 case per login, case id 'invoker:<login>', which names no object); [] for another profile or machine
    (their case ids have other shapes), when every case id of the obligation is 'invoker:<login>' (so a database whose
    only definer is named 'invoker' reads no names, never a wrong one) and when the reading carries no such cases.
    Never raises."""
    try:
        profile = envelope.get('profile')
        if (profile.get('id') if isinstance(profile, dict) else profile) != 'postgresql-observed-baseline' or \
                row.get('machine') != 'M6':
            return []
        rd = (envelope.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
        cases = ob.get('cases') if isinstance(ob, dict) else None
        cases = cases if isinstance(cases, list) else []
        ids = [c.get('case_id') for c in cases if isinstance(c, dict) and isinstance(c.get('case_id'), str)]
        if all(i.startswith('invoker:') for i in ids):
            return []
        objects = {}
        for case in cases:
            if not isinstance(case, dict) or case.get('status') != row.get('status'):
                continue
            case_id = case.get('case_id')
            if not isinstance(case_id, str) or ':' not in case_id:
                continue
            name, role = case_id.rsplit(':', 1)
            roles = objects.setdefault(name, [])
            if role not in roles:
                roles.append(role)
        return list(objects.items())
    except (AttributeError, TypeError):
        return []


def objects_text(envelope, row):
    """'15 objects: fn_a (roles app, report), fn_b (role app), ... and 10 more' for the row's objects (`row_objects`,
    at most MAX_WITNESSES named, each name and role bounded); None when the reading carries no such cases."""
    objects = row_objects(envelope, row)
    if not objects:
        return None
    named = ['%s (%s %s)' % (_clip(name), 'role' if len(roles) == 1 else 'roles', ', '.join(_clip(r) for r in roles))
             for name, roles in objects[:MAX_WITNESSES]]
    more = len(objects) - MAX_WITNESSES
    return '%d %s: %s%s' % (len(objects), 'object' if len(objects) == 1 else 'objects', ', '.join(named),
                            ' and %d more' % more if more > 0 else '')


def _witness_parts(env, row):
    """'<object>, <access path>, <locator>' from the row's first witness in `readings` (each part present only when the
    witness names it), else the row's reason or status text. Plain text, bounded."""
    words = witness_words(env, row)
    if words is not None:
        return words
    return _clip(row.get('reason') or row.get('status_text') or row.get('status'))


def _first_witness(env, row):
    """The row's first witness in `readings` (its obligation's `witnesses[0]`, else its `witness`) and the
    obligation's sibling `locator` (the M5 explorer writes one beside the witness, issue #833); (None, None) when the
    reading carries none."""
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
        if isinstance(ob, dict):
            ws = ob.get('witnesses')
            return (ws[0] if isinstance(ws, list) and ws else ob.get('witness')), ob.get('locator')
    except (AttributeError, TypeError):
        pass
    return None, None


def witness_words(env, row):
    """The row's first witness in `readings` in the first line's words: '<object>, <access path>, <locator>' (each
    part present only when the witness names it, read by `_witness_fields`, the projection the meaning line reads),
    'declared <names>, actual <names>' for the M7 SU-1 pair, a key-named application or capability. Plain text,
    bounded; None when the reading carries no witness or the witness gives no words. The envelope's row `reason`
    takes these words when the checker wrote none (issue #492)."""
    w, _ = _first_witness(env, row)
    if isinstance(w, dict):
        pair = _declared_actual_words(w)
        if pair is not None:                             # issue #365: M7 SU-1's {declared, actual} witness
            return pair
    parts = [part for part in _witness_fields(env, row) if part is not None]
    if isinstance(w, dict):
        # issue #365: the M7 witness keys a bare name would not explain; each is named with its key
        for key in ('application', 'capability'):
            if _scalar(w.get(key)):
                parts.append('%s %s' % (key, _clip(w.get(key))))
    elif _scalar(w):
        parts.append(_clip(w))
    return ', '.join(parts) if parts else None


def _declared_actual_words(w):
    """'declared <names>, actual <names>' for a witness carrying both `declared` and `actual` lists (the M7 SU-1
    shape, explorer.py: administrators declared against the superusers seen), an empty side reading 'none'; None
    when the witness is of another shape (issue #365)."""
    declared, actual = w.get('declared'), w.get('actual')
    if not isinstance(declared, list) or not isinstance(actual, list):
        return None
    def names(values):
        return _clip(', '.join(str(v) for v in values if _scalar(v)) or 'none')
    return 'declared %s, actual %s' % (names(declared), names(actual))


def _red_words(env, finding):
    kind, ob_id, row = finding
    if kind == 'disproven' and row is not None:
        k = len(disproven_rows(env))                 # issue #1038: the count, then the first in reading order
        return 'disproven: %s%s — %s' % ('%d, first ' % k if k > 1 else '',
                                         _clip(ob_id if ob_id is not None else row.get('machine')),
                                         _witness_parts(env, row))
    if kind == 'chosen':                             # REFUTATION-028 F2: never "disproven"
        return 'stopped by your choice: %s — %s' % (_clip(label((row or {}).get('status'))),
                                                     _clip(ob_id if ob_id is not None else (row or {}).get('machine')))
    lead = 'not proven: ' if kind == 'not_proven' else 'unresolved by your choice (strict): '
    if kind == 'strict':                             # serve-027: the count, then the first in reading order
        k = len([f for f in red_findings(env) if f[0] == 'strict'])
        if k > 1:
            lead += '%d, first ' % k
    entry = next((e for e in env.get('not_established') or () if isinstance(e, dict) and e.get('id') == ob_id), None)
    unread = (row is None or row.get('machine') not in _read_set(env)
              or (entry is not None and entry.get('reason_class') == 'not_observed'))
    if kind == 'not_proven' and unread:              # 2073 N5: its inputs could not be read
        return 'not proven: %s — input not observed' % _clip(ob_id)
    if entry is None and isinstance(row, dict):      # a verdict that is not holds (vacuous, deviates): its status
        return '%s%s — reads %s' % (lead, _clip(ob_id), _clip(label(row.get('status'))))
    if entry is None:                                # no reading at all: the locator fallback (issue #652: named as such)
        entry = {'id': _clip(ob_id), 'reason_class': 'not_observed', 'action': 'collect the facts %s reads' % _clip(ob_id)}
    return '%s%s — %s; %s' % (lead, _clip(ob_id), _clip(reason_words(entry, env)), _clip(entry.get('action')))


def disproven_rows(envelope):
    """issue #1038: one {id, machine, status, witness, platform_owned, requirement} per 'disproven' finding of `red_findings`, in
    its order (the customer's own before platform-owned), `witness` the first line's witness words (None when the
    reading carries none). The summary lists them so one read names every disproof the headline counts;
    REFUTATION-PR1070-001 F1: `platform_owned` (`platform_owned`) marks the ones that are someone else's to fix; F2:
    `requirement` names the requirements.md row a disproof comes from when no obligation of it is already listed (its
    `id` is then the requirement's), else None."""
    env = envelope if isinstance(envelope, dict) else {}
    return [{'id': ob_id, 'machine': row.get('machine'), 'status': row.get('status'),
             'witness': witness_words(env, row), 'platform_owned': platform_owned(env, row),
             'requirement': row.get('requirement')}
            for kind, ob_id, row in red_findings(env) if kind == 'disproven' and isinstance(row, dict)]


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
    # issue #794: a no-collector profile's line carries the first representation row's own reason (its locator)
    if env.get('profile') == 'python-auth-declared-model':
        refusal = next((r for r in _rows(env) if r.get('status') in ('representation', 'not_evaluated')),
                       {'reason': env.get('a0') or next(iter(reasons), '')})
        action = representation_action(env['profile'], refusal, (env.get('input') or {}).get('files', ()))
        return '%s; %s' % (REASON_WORDS['representation'], action)
    reason = next((r.get('reason') for r in _rows(env) if r.get('status') == 'representation' and r.get('reason')), None)
    return '%s; %s' % (REASON_WORDS['representation'], representation_action(env.get('profile'), reason))


def _yellow_action(env):
    """The action of the yellow line, the part after its reason."""
    return _could_not_look_words(env).split('; ', 1)[1]


def _yes(v):
    return 'yes' if v is True else 'no'


def completion_line(envelope, now=None):
    """Coordination 2102 A25: 'Usable readings: c of n. Coverage complete: yes|no. Job stops: no (exit 0 by your
    fail-on)|no (exit 0: platform-owned)|yes (exit <n>).' (REFUTATION-028-R2, R2-10 c; serve-077 r3 M2), with
    'Collected at <time>, <s> s before this summary.' when the sidecar named a collection time (`now`, seconds since
    the epoch, defaults to the clock); None for an envelope without `completion`."""
    c = envelope.get('completion') if isinstance(envelope, dict) else None
    if not isinstance(c, dict):
        return None
    u = c.get('usable_readings') if isinstance(c.get('usable_readings'), dict) else {}
    code = (envelope.get('policy') or {}).get('exit') if isinstance(envelope.get('policy'), dict) else None
    # R2-10 (c): whether the job stops, in closed words, never "passes" beside a red line; serve-077 r3 (M2): a
    # platform-owned exit 0 is the policy's exclusion, not the customer's fail-on
    pol = envelope.get('policy') if isinstance(envelope.get('policy'), dict) else {}
    if code == 0 and pol.get('reason') == PLATFORM_OWNED:
        stops = 'no (exit 0: platform-owned)'
    else:
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


# serve-071 (3786): a row without an `id` is a refused machine's own line, not an obligation reading. One definition,
# shipped with the Action tree; `serve.envelope` imports it.
MACHINE_REFUSAL_KIND = 'machine_refusal'
NEEDS_UNTABLED = 'what admits it is not tabled yet (the reason is kept as written)'


def is_machine_refusal(row):
    """True for a row without an obligation `id` (or one already marked `kind: machine_refusal`)."""
    return isinstance(row, dict) and (row.get('id') is None or row.get('kind') == MACHINE_REFUSAL_KIND)


def machine_refusal_rows(env):
    return [r for r in _rows(env) if is_machine_refusal(r)]


def refused_machine_entries(env):
    """The refused machines as {machine, status, ...}: the entries of `machines.refused` when the block names any
    (issue #793: the observed profile reports refusals through its readings and writes no refusal row), else the
    machine-refusal rows of an envelope without a machines block (one built before refutation-007)."""
    m = _machines(env) if isinstance(env, dict) else None
    refused = [r for r in m['refused'] if isinstance(r, dict)] if m is not None else []
    return refused or machine_refusal_rows(env if isinstance(env, dict) else {})


def _refused_counts(entries):
    by = {}
    for r in entries:
        by[r.get('status')] = by.get(r.get('status'), 0) + 1
    return {'count': sum(by.values()), 'by_status': by}


def recounted_machines_refused(env):
    """Issue #411: {count, by_status} over `machines.refused` when it names a machine and each of its entries carries
    a string `status`, as the envelope writer has derived the block since issue #793 (a verdict stored before #793
    counted its refusal rows only and says 0 beside a list of three); None otherwise, so an entry stored without a
    status (before issue #172) never becomes a None key (REFUTATION-r4 HIGH-1)."""
    m = _machines(env) if isinstance(env, dict) else None
    refused = [r for r in m['refused'] if isinstance(r, dict)] if m is not None else []
    if refused and all(isinstance(r.get('status'), str) for r in refused):
        return _refused_counts(refused)
    return None


def machines_refused_block(env):
    """The envelope's `machines_refused` {count, by_status}, or the same derived from `refused_machine_entries` for
    an older stored envelope (one built before serve-071); `recounted_machines_refused` when that is not None."""
    recount = recounted_machines_refused(env)
    if recount is not None:
        return recount
    mr = env.get('machines_refused') if isinstance(env, dict) else None
    if isinstance(mr, dict) and type(mr.get('count')) is int and isinstance(mr.get('by_status'), dict):
        return mr
    return _refused_counts(refused_machine_entries(env))


def machines_refused_line(envelope):
    """'Machines refused: n (<status> k, ...). A refused machine is not an obligation reading and is not in the table
    above.', or None when no machine was refused. Under a scope limit `n` is net of the limited machines, as the
    first line's 'n refused' is (serve-077); `machines_refused.count` in the envelope stays gross."""
    mr = machines_refused_block(envelope)
    limited = scope_limited_machines(envelope)
    if limited:                                       # serve-077: an out-of-scope machine is said once, as a scope row
        mr = _refused_counts([r for r in refused_machine_entries(envelope) if r.get('machine') not in limited])
    if not mr['count']:
        return None
    by = ', '.join('%s %d' % (esc(label(s)), int(n)) for s, n in sorted(mr['by_status'].items(),
                                                                       key=lambda kv: (-int(kv[1]), str(kv[0]))))
    return ('Machines refused: %d (%s). A refused machine is not an obligation reading and is not in the table above.'
            % (int(mr['count']), by))


def needs_words(row):
    """'<status>; needs <kind> <key>: <action>' for a machine-refusal row with tabled `needs`, or
    '<status>; <NEEDS_UNTABLED>' when `needs` is null."""
    n = row.get('needs') if isinstance(row, dict) else None
    status = esc(label(row.get('status'))) if isinstance(row, dict) else ''
    if isinstance(n, dict) and n.get('kind') and n.get('key') and n.get('action'):
        return '%s; needs %s %s: %s' % (status, esc(n['kind']), esc(n['key']), esc(n['action']))
    return '%s; %s' % (status, NEEDS_UNTABLED)


def confirm_leaves(envelope):
    """issue #651: the JSON pointers a declared-model envelope's `declaration.confirm_leaves` names (strings only);
    [] for an envelope without the block."""
    env = envelope if isinstance(envelope, dict) else {}
    block = env.get('declaration')
    leaves = block.get('confirm_leaves') if isinstance(block, dict) else None
    return [p for p in leaves if isinstance(p, str)] if isinstance(leaves, list) else []


def provisional_words(envelope):
    """'provisional: N leaves await confirmation' while the declaration has confirm leaves, else None."""
    n = len(confirm_leaves(envelope))
    return 'provisional: %d leaves await confirmation' % n if n else None     # one documented phrase, N = 1 too


def verdict_line(envelope):
    """serve-016: the one first line (module docstring), plain text with every part bounded; None for an envelope
    without `colour` (an older server). One denominator per line (REFUTATION-028 F7): N counts every obligation reading;
    established counts the holds on machines that were read. issue #651: a declared-model verdict read on a declaration
    with confirm leaves ends '; provisional: N leaves await confirmation'."""
    env = envelope if isinstance(envelope, dict) else {}
    c = env.get('colour')
    if c not in COLOURS:
        return None
    req = requirements_words(env)                     # serve-019: after the not-established count
    if c == 'yellow':
        line = 'yellow: could not look: %s%s' % (_could_not_look_words(env), '; %s' % req if req else '')
        return _provisional_line(line, env)
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
        if pol.get('exit') == 0 and pol.get('reason') == PLATFORM_OWNED:     # serve-077: someone else's disproof
            words += ' (exit 0: platform-owned)'
        elif pol.get('exit') == 0:                    # REFUTATION-028 F1, Q3: red, and the exit the customer chose
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
        if req:
            parts.append(req)
        parts.append(words)
        return _provisional_line('%s: %s' % (c, '; '.join(parts)), env)
    held = len([r for r in obligations if r.get('status') == 'holds' and r.get('machine') in read])
    entries = [e for e in env.get('not_established') or () if isinstance(e, dict)]
    # serve-064 (dogfood fb-20261009-b841067fe3d852c9): every reading class on the machines read is named, so the parts
    # add up to N; a vacuous reading was counted nowhere ("established: 4 of 12; not established: 3" hid five)
    counted = {e.get('id') for e in entries}
    others = {}
    for r in obligations:
        st = r.get('status')
        if r.get('machine') in read and st and st not in ('holds', 'deviates') and r.get('id') not in counted:
            others[label(st)] = others.get(label(st), 0) + 1
    # R5-3: an entry strict added for an obligation with no reading counts in N too, so the parts add up
    with_rows = {r.get('id') for r in obligations}
    obligations = obligations + [{'id': e.get('id')} for e in entries if e.get('id') not in with_rows]
    if held:                      # coordination 2098 A21: no holds reads in words, never as a count of success
        parts += ['nothing disproven', 'established: %d of %d' % (held, len(obligations))]
    else:
        parts.append('nothing could be established (0 of %d obligations hold)' % len(obligations))
    if deviations:
        parts.append('deviations: %d' % deviations)
    parts += ['%s: %d' % (word, n) for word, n in sorted(others.items())]
    top = top_entry(entries, env)
    if top is not None and collection_unread(env):   # issue #1208: the gaps below come from the absent collection
        parts.append(NO_COLLECTION_WORDS)
    tail = 'not established: %d' % len(entries)
    if top is not None:                               # 2129 W2, W3: the count becomes a path
        tail += ' — top action: %s%s' % (_clip(top.get('action')), _quote_words(top.get('quote')))
    parts.append(tail)
    if req:
        parts.append(req)
    return _provisional_line('%s: %s' % (c, '; '.join(parts)), env)


def _provisional_line(line, env):
    words = provisional_words(env)
    return line if words is None else '%s; %s' % (line, words)


def lead_finding(envelope):
    """The finding the red first line names: the first of `red_findings`, or, when nothing could be read (a
    prove-class obligation keeps the colour red, DD-073 Addendum 1), the first prove-class one."""
    found = red_findings(envelope)
    if found and could_not_look(envelope):
        return next((f for f in found if f[0] == 'not_proven'), found[0])
    return found[0] if found else None


NO_COLLECTION_WORDS = "no machine's collection was read"


def _refused_for_representation(r):
    """Issue #1208 (REFUTATION-r2 F1): a refused entry's stored `status` decides (serve/envelope.py refusal_status
    gives a `malformed_output:` reason the status representation, and a profile's own refusal row sets it whatever
    its reason says); only an entry stored without `status` (before serve-071) falls back to its reason prefix."""
    if not isinstance(r, dict):
        return False
    if 'status' in r:
        return r.get('status') == 'representation'
    return str(r.get('reason') or '').startswith('representation')


def collection_unread(envelope):
    """Issue #1208: True when no reading was usable (`completion.usable_readings.count` 0) and every refused machine
    (a scope-limited one aside) was refused for representation, so the other gaps exist only because the collection
    is absent; False when no machine was refused or any refusal is of another status."""
    env = envelope if isinstance(envelope, dict) else {}
    c = env.get('completion') if isinstance(env.get('completion'), dict) else {}
    u = c.get('usable_readings') if isinstance(c.get('usable_readings'), dict) else {}
    m = _machines(env)
    if type(u.get('count')) is not int or u.get('count') != 0 or m is None:
        return False
    limited = scope_limited_machines(env)
    refused = [r for r in m['refused'] if not (isinstance(r, dict) and r.get('machine') in limited)]
    return bool(refused) and all(_refused_for_representation(r) for r in refused)


def top_entry(entries, envelope=None):
    """2129 W2/W3: the not-established entry whose action stands for the most frequent reason class (the first seen on
    a tie), leaving out the representation fallback when any other class is present; None when there is none.
    Issue #1208: when `envelope` says no machine's collection was read (`collection_unread`), the first representation
    entry is the top action whatever the other classes count, since they exist only because the collection is absent;
    when no entry is of that class (the refused machines wrote no rows), an entry without an id carrying the profile's
    representation action (REFUTATION-r2 F2)."""
    entries = [e for e in entries if isinstance(e, dict) and isinstance(e.get('action'), str) and e.get('action')]
    if not entries:
        return None
    if collection_unread(envelope):
        return next((e for e in entries if e.get('reason_class') == 'representation'),
                    {'reason_class': 'representation', 'action': representation_action(envelope.get('profile'))})
    counts, first = {}, []
    for e in entries:
        cls = e.get('reason_class')
        if cls not in counts:
            first.append(cls)
        counts[cls] = counts.get(cls, 0) + 1
    pool = [k for k in first if k != 'representation'] or first
    top = max(pool, key=lambda k: (counts[k], -first.index(k)))
    return next(e for e in entries if e.get('reason_class') == top)


TOP_ACTION_RULE = ('the action of the first entry of the most frequent reason class (the first seen on a tie), leaving '
                   'out representation when any other class is present, unless no usable reading was made and every '
                   'refused machine was refused for representation')


def top_action(entries, envelope=None):
    """Issue #652: the first line's top action as a checkable object, {text, reason_class, action_source,
    from_entries, rule}: `from_entries` lists the ids of the action-bearing entries of the chosen class, the ones the
    rule counted; `text` is `top_entry`'s action, unclipped (the line clips it to CAP). None when there is no
    action-bearing entry. The caller emits it only where the line prints one (a green verdict; verdict_line); pass the
    `envelope` so the choice is the line's (issue #1208, `collection_unread`)."""
    top = top_entry(entries, envelope)
    if top is None:
        return None
    counted = [e for e in entries if isinstance(e, dict) and isinstance(e.get('action'), str) and e.get('action')
               and e.get('reason_class') == top.get('reason_class')]
    return {'text': top['action'], 'reason_class': top.get('reason_class'), 'action_source': action_source(top),
            'from_entries': [e.get('id') for e in counted], 'rule': TOP_ACTION_RULE}


# ---------- serve-019: the requirements rows (serve/requirements_adapter.py; DD-071's three states) ----------
REQUIREMENT_STATES = ('holds', 'not_established', 'disproven')
UNREAD_CLASSES = ('not_understood', 'duplicate_id')       # the parser's own classes: a line it could not read


def requirement_rows(envelope):
    """The envelope's `requirements` rows (objects only), or None for an envelope that carries none (no text was
    sent, or an earlier server)."""
    rows = envelope.get('requirements') if isinstance(envelope, dict) else None
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict)]


def requirement_counts(envelope):
    """{holds, not_established, disproven, not_proven} of the rows, or None (`requirement_rows`). not_proven is the
    overlapping subset of not_established whose display state reads not proven."""
    rows = requirement_rows(envelope)
    if rows is None:
        return None
    out = {s: len([r for r in rows if r.get('state') == s]) for s in REQUIREMENT_STATES}
    out['not_proven'] = len([r for r in rows if r.get('display_state') == 'not_proven'])
    return out


def requirements_words(envelope):
    """'requirements: h hold, n not established[, d disproven]' for the first line, or None (`requirement_rows`)."""
    c = requirement_counts(envelope)
    if c is None:
        return None
    words = 'requirements: %d hold, %d not established' % (c['holds'], c['not_established'])
    return words + (', %d disproven' % c['disproven'] if c['disproven'] else '')


def _requirement_label(row):
    if row.get('display_state') == 'not_proven' and row.get('state') == 'not_established':
        return 'not proven'
    return label(row.get('state') if row.get('state') in REQUIREMENT_STATES else 'not_established')


SENTENCE_CAP = 160                                # DD-070 item 1: the quoted sentence on the requirement line
# REFUTATION-034 F6 and R2 N3; coordination 2365/2379 (the declared-model lane's display decision): a format character
# (Unicode category Cf: bidi embeddings, overrides and isolates, zero-width marks, the BOM, the soft hyphen, the astral
# TAG characters) or a line or paragraph separator (Zl, Zp) can reorder, hide or split what a summary or an annotation
# shows. The sentence's exact code points are its identity (the JSON and the quote keep them); a human line shows each
# one as one ASCII space, one for one, so the 160-character bound holds.
_FORMAT_CATEGORIES = ('Cf', 'Zl', 'Zp')


def format_space(text):
    """`text` with every character of category Cf, Zl or Zp replaced by one ASCII space; nothing else changes."""
    t = '' if text is None else str(text)
    if t.isascii():
        return t
    return ''.join(' ' if unicodedata.category(c) in _FORMAT_CATEGORIES else c for c in t)


CONTRACT_WORDS = "the checker's PROFILE.json failed verification; nothing to do on your side — Symbolia repairs it"
# REFUTATION-034-R2 N6: the quote route's reason when a profile's metadata fails verification (its action agrees)
METADATA_ROUTE_WORDS = ("the checker's PROFILE.json failed verification; Symbolia repairs the profile; nothing to do on "
                        "your side")
_LOCATOR_KEYS = ('evidence_locator', 'locator', 'domain_locator')


def requirement_locator(row):
    """The first locator a requirement row's evidence (then its details) carries, bounded; None when it carries none.
    Never invented: a row without one prints none."""
    r = row if isinstance(row, dict) else {}
    for item in list(r.get('evidence') or ()) + list(r.get('details') or ()):
        if isinstance(item, dict):
            for key in _LOCATOR_KEYS:
                if _scalar(item.get(key)) and str(item[key]).strip():
                    return _clip(item[key])
    return None


def empty_domain_requirement(row, envelope):
    """The vacuous auth row (`_vacuous_row`) of a not-established requirement every matched obligation of which is one,
    or None: such a requirement reads as an empty domain whatever reason class its JSON row carries (issue #1292)."""
    matched = row.get('matched_obligations') if row.get('state') == 'not_established' else None
    if not isinstance(matched, list) or not matched:
        return None
    found = [_vacuous_row(envelope, m.get('machine'), m.get('id')) if isinstance(m, dict) else None for m in matched]
    return found[0] if all(found) else None


# issue #1292: the profile whose requirement line says a state once when its reason class only repeats it
SAID_ONCE_PROFILE = 'python-auth-declared-model'


def requirement_line(row, envelope=None):
    """'<id> — "<sentence>" — <state> — <reason class>[ — <locator>] — <action>[ — quote USD a–b]' for one requirement
    row (DD-070 item 1): the sentence as written, bounded to SENTENCE_CAP characters with …, the locator when the row's
    evidence carries one. With an envelope of SAID_ONCE_PROFILE, a holds or disproven line whose reason class reads the
    same as its state says it once, and an empty-domain requirement (`empty_domain_requirement`) reads
    '<state> — empty domain, nothing to check — <the row's reason>', with no action. Plain text, every part bounded;
    the summary, the annotations and the Action's log read the same words. The JSON row is never changed."""
    r = row if isinstance(row, dict) else {}
    sentence = _CONTROL.sub(' ', '' if r.get('sentence') is None else str(r.get('sentence')))
    if len(sentence) > SENTENCE_CAP:
        sentence = sentence[:SENTENCE_CAP - 1] + '…'
    vacuous = empty_domain_requirement(r, envelope) if isinstance(envelope, dict) else None
    if vacuous is not None:
        reason = vacuous.get('reason')
        return format_space('%s — "%s" — %s — empty domain, nothing to check%s' % (
            _clip(r.get('id')), sentence, _requirement_label(r), ' — %s' % _clip(reason) if reason else ''))
    locator = requirement_locator(r)
    # REFUTATION-034 F7: a failed producer verification is Symbolia's to repair, said so in the customer's words
    action = CONTRACT_WORDS if r.get('reason_class') == 'checker_contract' else _clip(r.get('establishing_action'))
    state, reason = _requirement_label(r), _clip(label(r.get('reason_class')))
    loc, quote = ' — %s' % locator if locator else '', _quote_words(r.get('formalisation_quote'))
    said_once = (isinstance(envelope, dict) and envelope.get('profile') == SAID_ONCE_PROFILE and reason == state)
    # each said-once template names its state, so tools/ci/phrase_pins.py --explain-line resolves it here (#1397)
    if said_once and state == 'holds':
        return format_space('%s — "%s" — holds%s — %s%s' % (_clip(r.get('id')), sentence, loc, action, quote))
    if said_once and state == 'disproven':
        return format_space('%s — "%s" — disproven%s — %s%s' % (_clip(r.get('id')), sentence, loc, action, quote))
    line = '%s — "%s" — %s — %s%s — %s%s' % (
        _clip(r.get('id')), sentence, state, reason, loc, action, quote)
    return format_space(line)


def _requirement_findings(env, found):
    """serve-019: the requirement rows as findings of `red_findings` (the one decision): a disproven row as
    'disproven' with its matched obligation's machine and id (so its witness is the reading's own), a row that reads
    not proven as 'not_proven'. A row whose matched obligations are already named is left out: an obligation is listed
    once."""
    named = {i for _, i, _ in found if i is not None}
    out = []
    for r in requirement_rows(env) or ():
        kind = ('disproven' if r.get('state') == 'disproven' else
                'not_proven' if r.get('display_state') == 'not_proven' and r.get('state') == 'not_established' else None)
        if kind is None:
            continue
        matched = [m for m in r.get('matched_obligations') or () if isinstance(m, dict)]
        if any(m.get('id') in named for m in matched):
            continue
        first = matched[0] if matched else {}
        out.append((kind, r.get('id'), {'machine': first.get('machine'), 'id': first.get('id'),
                                        'status': 'fails' if kind == 'disproven' else 'not_proven',
                                        'status_text': r.get('reason_class'), 'reason': r.get('reason'),
                                        'requirement': r.get('id')}))
    return out


# ---------- DD-073 Addendum 2 (heading 2133): the plain-language layer, closed templates, no model ----------
# The subject and the family each profile's meaning sentence names, by the profile id's first word.
PROFILE_WORDS = {'postgresql': ('database configuration', 'PostgreSQL'), 'http': ('HTTP responses', 'HTTP')}
DEFAULT_PROFILE_WORDS = ('system', 'software')
# issue #1292: the green head that says what the auth profile read, in the place of the generic "safe <family> setups"
# (subject, head when AUTH-1 and AUTH-2 both hold, head otherwise)
GREEN_HEADS = {'python-auth-declared-model': ('Flask app', 'Every route in your Flask app is guarded as your '
                                              'declaration says.',
                                              'Nothing read in the routes of your Flask app contradicts your '
                                              'declaration.')}
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
    """`_meaning_line`, then (serve-019) for an envelope that carries requirement rows: "<u> of <N> requirements in
    requirements.md could be read." (u leaves out the lines the parser could not read)."""
    line = _meaning_line(envelope)
    rows = requirement_rows(envelope)
    if line is None or rows is None:
        return line
    read = len([r for r in rows if r.get('reason_class') not in UNREAD_CLASSES])
    return '%s %d of %d requirements in requirements.md could be read.' % (line, read, len(rows))


def _meaning_line(envelope):
    """DD-073 Addendum 2 (a): one sentence (or two) under the first line saying what it means, from a closed template
    per colour; None for an envelope without `colour`.
    - green: "Nothing in your <subject> contradicts what is known about safe <family> setups. <n> of <N> checks could
      not be completed, mostly because <the top reason class in words>. That is a gap in what we could see; your
      <subject> is unchanged by it." ("All <N> checks could be completed." when n is 0);
    - red: the first finding's consequence, then for a disproof "The finding is at <locator> (<object>, <access
      path>)." when its witness names a locator, else "The reading <id> fails; the record carries no witness to point
      at.", and for the other kinds what was chosen or not proven;
    - yellow: "We could not read the collected files (the submitted input for Python), so nothing below is a finding
      about your <subject>. <Action>."."""
    env = envelope if isinstance(envelope, dict) else {}
    c = env.get('colour')
    if c not in COLOURS:
        return None
    subject, family = _profile_words(env)
    if c == 'yellow':
        what = 'submitted input' if env.get('profile') == 'python-auth-declared-model' else 'collected files'
        return ('We could not read the %s, so nothing below is a finding about your %s. %s'
                % (what, subject, _sentence(_yellow_action(env))))
    if c == 'green':
        entries = [e for e in env.get('not_established') or () if isinstance(e, dict)]
        n_all = len(_obligation_rows(env))
        head = 'Nothing in your %s contradicts what is known about safe %s setups.' % (subject, family)
        if env.get('profile') in GREEN_HEADS:
            subject, guarded, other = GREEN_HEADS[env['profile']]
            held = {r.get('id') for r in _rows(env) if r.get('status') == 'holds'}
            head = guarded if {'AUTH-1', 'AUTH-2'} <= held else other
        top = top_entry(entries, env)
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
    the reading carries no witness object. On the declared profile's M5 a verified declared_actionability projection
    gives all three; otherwise the witness's own keys, descending into a nested `transition` and the obligation's
    sibling `locator` {access_path, catalog_field, input_pointer} (the M5 explorer's shape, issue #833)."""
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        profile = env.get('profile')
        profile_id = profile.get('id') if isinstance(profile, dict) else profile
        if profile_id == 'postgresql-declared-model' and row.get('machine') == 'M5' and isinstance(rd, dict):
            projection = rd.get('actionability')
            if isinstance(projection, dict) and projection.get('schema') == 'assure.declared-m5.actionability/v1':
                projected = projection.get(row.get('id'))
                if isinstance(projected, dict) and projected.get('verified') is True:
                    fields = (projected.get('object'), projected.get('access_path'), projected.get('evidence_locator'))
                    if all(_scalar(value) for value in fields):
                        return tuple(_clip(value) for value in fields)
    except (AttributeError, TypeError):
        pass
    w, sibling = _first_witness(env, row)
    if not isinstance(w, dict):
        return None, None, None
    flow = w.get('flow') if isinstance(w.get('flow'), dict) else {}
    records = w.get('records') if isinstance(w.get('records'), list) else []
    transition = w.get('transition') if isinstance(w.get('transition'), dict) else {}
    locator = sibling if isinstance(sibling, dict) else {}
    out = []
    for options in ((w.get('object'), w.get('role'), w.get('owner'), flow.get('user'), flow.get('role')),
                    (w.get('path'), transition.get('path'), locator.get('access_path'), w.get('command'),
                     transition.get('command'), w.get('rule_id'), flow.get('transport'), flow.get('name')),
                    (w.get('locator'), _locator_words(locator), sibling if not locator else None,
                     records[0] if records else None)):
        v = next((x for x in options if _scalar(x)), None)
        out.append(_clip(v) if v is not None else None)
    return tuple(out)


def _locator_words(locator):
    """'<catalog_field> <input_pointer>' for the M5 explorer's locator object, whichever of the two it names; None
    when it names neither (issue #833)."""
    words = [locator.get(key) for key in ('catalog_field', 'input_pointer') if _scalar(locator.get(key))]
    return ' '.join(str(word) for word in words) if words else None


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
    """2073 N6: 'strict: no obligations marked' when the strict preset is set and the profile marks no obligation;
    otherwise 'strict: n of m security obligations observable at this pin', where m counts the intent-free security
    obligations and n those of them the collector pin can observe (serve-026)."""
    pol = env.get('policy') if isinstance(env.get('policy'), dict) else {}
    b = env.get('bias') if isinstance(env.get('bias'), dict) else {}
    if STRICT in (pol.get('fail_on') or ()) and not b.get('security'):
        return 'strict: no obligations marked'
    if STRICT in (pol.get('fail_on') or ()):           # the security obligations the collector pin can observe
        # serve-026: of the intent-free ones; an intent-bound obligation is unobservable by any collector, not this pin
        sec = [i for i in b.get('security') or () if i not in set(b.get('intent_bound') or ())]
        seen = [i for i in sec if i not in set(b.get('unobservable') or ())]
        return 'strict: %d of %d security obligations observable at this pin' % (len(seen), len(sec))
    return None


def _outcome_words(env):
    if env.get('a0') is not None:
        return 'No reading: input integrity'
    if env.get('outcome') != 'verdict':
        return 'No verdicts'
    return 'Readings'


def _sql_line(statement):
    """One line of SQL for a fenced block: control characters and newlines become spaces; a fence inside is broken;
    bounded."""
    text = _CONTROL.sub(' ', ' '.join(str(statement).splitlines()))
    text = text.replace('```', '` ` `')
    return text if len(text) <= CAP * 2 else text[:CAP * 2 - 1] + '…'


def _grouped(entries):
    """3908 (1): one entry per (object, fix statement), in first-seen order, naming every machine and obligation that
    carries it ("M6 SD-1-OB, SD-3-OB; M7 SD-1-OB"). The checker attaches the same finding to each obligation an
    object fails (3817); the reader sees the object once."""
    order, refs = [], {}
    for r, f in entries:
        fix = f.get('fix') if isinstance(f.get('fix'), dict) else {}
        key = (f.get('object'), fix.get('statement') if isinstance(fix.get('statement'), str) else None)
        if key not in refs:
            order.append((key, f))
            refs[key] = {}
        ids = refs[key].setdefault(r.get('machine'), [])
        if r.get('id') not in ids:
            ids.append(r.get('id'))
    return [('; '.join('%s %s' % (esc(m), ', '.join(esc(i) for i in ids)) for m, ids in refs[key].items()), f)
            for key, f in order]


def disclosure_lines(f):
    """3946 (as revised in 3971, absent-safe): the finding's `disclosures` ([{text, witnesses}], the checker's own
    sentences, never derived here), one line each: '<text> (<witnesses> of <witness_count> paths)', or the bare text
    when `witnesses` equals `witness_count`. [] when the finding carries no well-formed entry."""
    entries = f.get('disclosures') if isinstance(f, dict) and isinstance(f.get('disclosures'), list) else ()
    count = f.get('witness_count') if isinstance(f, dict) else None
    out = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get('text'), str) or not e['text']:
            continue
        n = e.get('witnesses')
        text = _clip(e['text'])
        if type(n) is int and type(count) is int and n != count:
            text += ' (%d of %d paths)' % (n, count)
        out.append(text)
    return out


def _fix_lines(f, lead=None):
    fix = f.get('fix') if isinstance(f.get('fix'), dict) else {}
    out = []
    if isinstance(fix.get('statement'), str) and fix['statement']:
        out += [''] + (['  %s' % lead] if lead else []) + ['```sql', _sql_line(fix['statement']), '```', '']
    if isinstance(fix.get('then'), str) and fix['then']:
        out += ['  %s' % esc(fix['then']), '']
    told = disclosure_lines(f)                        # 3946/3971: each disclosure under the fix line
    if told:
        out += ['  %s' % esc(t) for t in told] + ['']
    return out


def _section(out, title, entries, line, suffix=''):
    if not entries:
        return
    out += ['%s: %d%s' % (title, len(entries), suffix), '']
    for refs, f in entries[:MAX_ANNOTATIONS]:
        out += line(refs, f)
    if len(entries) > MAX_ANNOTATIONS:
        out.append('- and %d more' % (len(entries) - MAX_ANNOTATIONS))
    while out and out[-1] == '':
        out.pop()
    out.append('')


def findings_lines(envelope):
    """serve-077 (3817 point 4; 3908): the first screen's findings, from the readings' `findings` on read machines
    (never derived here). Each object is listed once with every machine and obligation that carries it, and counts
    are distinct objects (3908 (1)). The customer's own first: each app finding with its `fix.statement` as a
    one-line ```sql block, then its `then` sentence. A fix of kind `sql_if_intended` (3836) sits on a reading that is
    not a verdict: it goes under "To review", led by "If this is what you intend:", and never under "Your findings"
    (3908 (2)). Unknown next with its `fix_note`; platform and extension under one secondary heading with their
    counts, each with its `fix_note` (who maintains it). [] when no reading carries findings."""
    env = envelope if isinstance(envelope, dict) else {}
    groups = {c: [] for c in OWNER_CLASSES}
    review = []
    for r, found in _findings_rows(env):
        for f in found:
            fix = f.get('fix') if isinstance(f.get('fix'), dict) else {}
            if f['owner_class'] == 'app' and fix.get('kind') == 'sql_if_intended':
                review.append((r, f))
            else:
                groups[f['owner_class']].append((r, f))
    if not any(groups.values()) and not review:
        return []
    out = []

    def note(f):
        n = f.get('fix_note') if isinstance(f.get('fix_note'), str) else ''
        return ' — %s' % esc(n) if n else ''
    _section(out, '### Your findings', _grouped(groups['app']),
             lambda refs, f: ['- %s: %s' % (refs, esc(f.get('object')))] + _fix_lines(f))
    _section(out, '### To review', _grouped(review),
             lambda refs, f: ['- %s: %s' % (refs, esc(f.get('object')))] + _fix_lines(f, 'If this is what you intend:'))
    _section(out, '### Not resolved to one function', _grouped(groups['unknown']),
             lambda refs, f: ['- %s: %s%s' % (refs, esc(f.get('object')), note(f))])
    platform, extension = _grouped(groups['platform']), _grouped(groups['extension'])
    _section(out, "#### Platform-owned, someone else's to fix", platform + extension,
             lambda refs, f: ['- %s: %s (%s)%s' % (refs, esc(f.get('object')), esc(f.get('owner_class')), note(f))],
             ' (platform %d, extension %d)' % (len(platform), len(extension)))
    return out


def _headline(env):
    line = first_line(env)
    words = _outcome_words(env)
    return words if line is None else '%s. %s' % (line, words)


# Launch 2026-10-12: the only link a summary prints, the server's Premium upgrade line (serve/api.py `upgrade_for`):
# a Stripe Payment Link on buy.stripe.com, with a query of plain characters, as a Markdown autolink. Anything else in
# `upgrade` is not printed (ACTION-07 holds for every other link-shaped text).
_UPGRADE_URL = re.compile(r'https://buy\.stripe\.com/[A-Za-z0-9_./-]+(\?[A-Za-z0-9_.~%=&-]*)?')


def upgrade_markdown(envelope):
    """The job summary's first line and a blank line when the answer carries `upgrade` {"url", "line"} (a free account
    on a server with a Premium payment link): the line's words escaped, then its url as `<url>`. '' when `upgrade` is
    absent or malformed: a url that is not a buy.stripe.com link, or a line that does not end in its url."""
    up = envelope.get('upgrade') if isinstance(envelope, dict) else None
    if not isinstance(up, dict):
        return ''
    url, line = up.get('url'), up.get('line')
    if not (isinstance(url, str) and isinstance(line, str) and _UPGRADE_URL.fullmatch(url)
            and line.endswith(' ' + url)):
        return ''
    words = line[:-len(url)].rstrip()
    if not words or _CONTROL.search(words) or len(words) > CAP:
        return ''
    # issue #2306 item 4: a spent free balance is said once, at the start of the same line; a notice that is not one
    # plain sentence (a link, a control character, too long) is left out and the pay line prints as before
    notice = up.get('notice')
    if isinstance(notice, str) and notice and not _CONTROL.search(notice) and len(notice) <= CAP \
            and '://' not in notice and not _UPGRADE_URL.search(notice):
        words = notice.strip() + ' ' + words
    return '%s <%s>\n\n' % (_esc_line(words), url)


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
    shown = warning_texts(env)                    # serve-041: a warning sits right under the headline, in the first 10 lines
    if shown:
        out += ['- Warning: %s' % _esc_line(t) for t in shown[:5]]
        if len(shown) > 5:
            out.append('- and %d more warnings' % (len(shown) - 5))
        out.append('')
    up_front = scope_notes_line(env)              # serve-012: a selected scope's bound sits under the headline
    if up_front is not None:
        out += ['Scope: %s' % esc(up_front), '']
    done = completion_line(env, now)              # coordination 2102 A25: three answers under the first line
    if line is not None and done is not None:
        out += [_esc_line(done), '']
    for notice in usage_notice_lines(env.get('usage')):     # serve-019: an allowance threshold crossed
        out += [_esc_line(notice), '']
    unsupported = set(((env.get('completion') or {}).get('unsupported') or {}).get('ids') or ())
    entries = [e for e in env.get('not_established') or () if isinstance(e, dict)] if line is not None else []
    gaps = [e for e in entries if e.get('id') not in unsupported]
    if env.get('colour') == 'green' and gaps:
        out += undecided_lines(gaps, env)          # issue #1193: by cause, largest first, then row by row
        out += not_established_lines(gaps[:MAX_ANNOTATIONS], env)
        if len(gaps) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(gaps) - MAX_ANNOTATIONS))
        out.append('')
    reqs = requirement_rows(env) if line is not None else None
    if reqs:                                      # serve-019: one line per requirement, under the not-established list
        out += ['### %s' % _esc_line(requirements_words(env)[0].upper() + requirements_words(env)[1:]), '']
        out += ['- %s' % _esc_line(requirement_line(r, env)) for r in reqs[:MAX_REQUIREMENT_LINES]]
        if len(reqs) > MAX_REQUIREMENT_LINES:
            out.append('- and %d more' % (len(reqs) - MAX_REQUIREMENT_LINES))
        out.append('')
    limits = [e for e in entries if e.get('id') in unsupported]
    if limits:                                    # A25: the profile's own limits, apart from the customer's gaps
        out += ['### Unsupported by this profile version: %d' % len(limits), '']
        out += not_established_lines(limits[:MAX_ANNOTATIONS], env)
        if len(limits) > MAX_ANNOTATIONS:
            out.append('- and %d more' % (len(limits) - MAX_ANNOTATIONS))
        out.append('')
    if line is not None:                          # serve-077 (3817 point 4): the findings, yours first, on the first screen
        out += findings_lines(env)
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
    strict = (', or when an obligation marked security is not resolved, intent-bound ones included (strict)'
              if STRICT in fail_on else '')
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
    elif reason == PLATFORM_OWNED:                # serve-077 (3817 point 1): someone else's disproof, excluded
        out.append('This run: exit %s. Every disproof your fail-on names is platform-owned (its findings are all '
                   'platform or extension), so it is excluded from the exit; it stays red above, and the platform '
                   'is named below as the owner.' % code)
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
    refused_line = machines_refused_line(env)            # serve-071: the table counts the obligation rows only
    if refused_line:
        out += ['', refused_line]
    refusal_rows = machine_refusal_rows(env)
    rows = [r for r in env.get('rows') or [] if not any(r is x for x in refusal_rows)]
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
            named = objects_text(env, r) if s == 'deviates' else None
            if named:                                     # issue #2176: one entry per object, its roles as a list
                out.append('  - %s' % esc(named))
    if machines is not None and machines.get('source') == 'inferred' and not machines['refused']:
        out += ['', 'The checker did not report which machines it refused; which machines were read is inferred from the '
                'readings.']
    limits = scope_limits(env) if line is not None else []
    limited = scope_limited_machines(env) if line is not None else set()
    if limits:                                    # serve-077 (3817 point 3): each permanent limit said once
        out += ['', '### Out of scope', '']
        for e in limits[:MAX_ANNOTATIONS]:
            out.append('- %s %s' % (esc(e['text']), esc(e['action'])))
    refused_here = [r for r in machines['refused'] if not (isinstance(r, dict) and r.get('machine') in limited)] \
        if machines is not None else []
    if refused_here:
        out += ['', '### Machines not read', '']
        if machines.get('source') == 'inferred':
            out += ['The checker did not report which machines it refused; this list is inferred from the readings.', '']
        for r in refused_here:
            r = r if isinstance(r, dict) else {}
            out.append('- %s: %s' % (esc(r.get('machine')), _reason(r.get('reason'))))
            for row in refusal_rows:                  # serve-071: its own status and what admits it
                if row.get('machine') == r.get('machine'):
                    out.append('  - %s' % needs_words(row))
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
    for kind, text in warning_items(envelope)[:MAX_ANNOTATIONS]:   # serve-041 / serve-048: titled by the entry's kind
        lines.append('::warning title=%s::%s' % (_cmd_prop(WARNING_TITLES.get(kind, 'Assure') if isinstance(kind, str) else 'Assure'), _cmd_data(text)))
    for level, r in picked[:MAX_ANNOTATIONS]:
        where = '%s %s' % (r.get('machine'), r.get('id')) if r.get('id') is not None else str(r.get('machine'))
        title = 'Assure %s %s' % (label(r.get('status')), where)
        msg = str(r.get('status_text') or '')
        # issue #492: as in _row_extra, a reason taken from the witness defers to the fuller witness line
        witness = witness_text(envelope, r) if r.get('status') == 'fails' and (
            not _extra_reason(r) or r.get('reason') == witness_words(envelope, r)) else None
        if witness:
            msg += ' (%s)' % witness
        elif _extra_reason(r):
            gloss = bound_gloss(r.get('reason'))
            msg += ' (%s%s)' % (r.get('reason'), '; %s' % gloss if gloss else '')
        named = objects_text(envelope, r) if r.get('status') == 'deviates' else None
        if named:                                     # issue #2176: the annotation names the objects too
            msg += ' — %s' % named
        lines.append('::%s title=%s::%s' % (level, _cmd_prop(title), _cmd_data(msg)))
    if first is not None:                         # serve-019: each requirement that does not hold, in the same words
        for r in [r for r in requirement_rows(envelope) or () if r.get('state') != 'holds'][:MAX_ANNOTATIONS]:
            lines.append('::%s title=%s::%s' % ('error' if r.get('state') == 'disproven' else 'notice',
                                                _cmd_prop('Assure requirement %s' % _clip(r.get('id'))),
                                                _cmd_data(requirement_line(r, envelope))))
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
# issue #1263: the GitHub OIDC sign-in (`POST /v1/auth/oidc`) comes before the profile list and any collection
SIGN_IN_REFUSED = ('The API refused the GitHub sign-in before anything was collected; nothing from your system was '
                   'sent.')
ANSWERED = ('sign_in', 'profiles', 'check', 'poll')          # the request the API answered, as the client records it


def check_line(failure_envelope):
    """The last line of a failure page, from the request the API answered (`detail.answered`, set by the client):
    - 'sign_in' (`POST /v1/auth/oidc`, before anything was collected; issue #1263): SIGN_IN_REFUSED;
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
    if answered == 'sign_in' and typed:
        return SIGN_IN_REFUSED
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


NO_RAW_STEP = ('Point artefacts in the workflow step at the directory that holds raw/ (a path relative to the workspace, '
               'or absolute), then run again.')
MANIFEST_PROFILE = 'http-observed-baseline'


def _layout_step(detail):
    """Issue #274: the no-raw/ step naming the profile's expected layout, from the Action's `detail` (`profile`, `layout`
    = the listing's required raw/ paths, `manifest` = manifest.json sits where raw/ was looked for). None without them."""
    profile, layout = detail.get('profile'), detail.get('layout')
    if not isinstance(profile, str) or not isinstance(layout, list) or not all(isinstance(p, str) for p in layout):
        return None
    files = ', '.join(layout) if layout else 'the files the profile lists'
    if detail.get('manifest') is True:
        # Refutation of PR #358 F1: `esc` clips the summary's What-to-do value at CAP, so the sentence stays under it
        # for every served listing (test_issue_274_accept checks each); the second half names the other input, not the
        # same profile twice, when the profile is already http-observed-baseline (a scope-binding file was given).
        other = 'With a scope-binding file' if profile == MANIFEST_PROFILE else 'For profile %s' % profile
        return ('manifest.json without raw/ is an endpoint manifest: it needs profile: %s with scope-binding empty. '
                '%s, point artefacts at the directory that holds raw/ with %s, then run again.'
                % (MANIFEST_PROFILE, other, files))
    return ('Point artefacts in the workflow step at the directory that holds raw/ (a path relative to the workspace, '
            'or absolute); profile %s expects %s under it. Then run again.' % (profile, files))


# Refutation-010 F1: a bad_input whose cause is a workflow input, not a file, gets a next step naming the input instead
# of the files sentence. Matched on the fixed reason text the Action writes; the step is fixed text (issue #274: the
# no-raw/ step names the profile's layout when the Action's detail carries it).
_INPUT_STEPS = (
    (re.compile(r'fail-on '), 'Set fail-on in the workflow step to a comma list of statuses (for example '
                              'fails,deviates) or to never, then run again.'),
    (re.compile(r'allow-partial '), 'Set allow-partial in the workflow step to true or false, then run again.'),
    (re.compile(r'no raw/ directory under the artefacts path|the raw directory is a link or not a directory'),
     NO_RAW_STEP),
    (re.compile(r'(?:mode|output|api-url|api-key|data-dir|config-dirs|collection-role|collection-privileges'
                r'|connection)\b|set exactly one of connection and artefacts|the user in the connection'
                r'|local mode is not available'),
     'Fix the workflow step input the reason names, then run again.'),
    # assure-on-itself-001: no api-key and no id-token permission (action/entry.py oidc_sign_in), the first run of a
    # repository whose key secret is not set yet
    (re.compile(r"Assure needs this workflow's GitHub identity or an api-key"),
     'Set the repository secret ASSURE_API_KEY (gh secret set ASSURE_API_KEY, the value pasted at the prompt) and pass '
     'it to the Assure step as api-key, or add id-token: write to the job\'s permissions; then run again.'),
)


def next_step(failure_envelope):
    """The 'What to do' text: the input's own step for a bad_input caused by a workflow input, else `action`."""
    f = failure_envelope
    detail = f.get('detail') if isinstance(f.get('detail'), dict) else {}
    if f.get('outcome') == 'bad_input' and 'answered' not in detail:
        reason = str(f.get('reason') or '')
        for pattern, text in _INPUT_STEPS:
            if pattern.match(reason):
                return (_layout_step(detail) or text) if text is NO_RAW_STEP else text
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


# ---------- issue #2189: the pull request comment, from the stored envelope, no model ----------
PR_COMMENT_MARKER = '<!-- assure:pr-comment -->'
NO_READING_HEAD = 'no reading of this change'
# the red findings that are not a broken rule, in the summary's own words (`_red_words`): one count each in the heading
PR_OTHER_KINDS = (('not_proven', 'not proven', 'not proven: it must hold, and no machine that was read shows it holds'),
                  ('strict', 'not resolved under strict', 'not resolved, and strict is set'),
                  ('chosen', 'stopped by your choice', 'stopped by your choice: its status is one your fail-on names'))


# The demo-grade comment (the Director, 13 Oct 2026: the platform writes the comment the launch video showed;
# tests/serving/test_pr_comment_demo_grade.py). Every rule is labelled by the customer's requirement id and sentence
# (the obligation id only when no requirement row maps), each holding rule says what was checked in the checker's own
# words, a rule not checked yet reads one plain sentence for its reason class, and the closing line says what Assure
# read. Nothing is written anew: the plain words come from the profile row (`obligation_words`, carried in the envelope:
# a short name, what was checked when it holds, and a fix filled from the reading's own witnesses); where the envelope
# carries none, the checker's own words stand, and the catalogue's phrase names the rule.
#
# The catalogue's requirement phrase per obligation, copied from the checker's pinned catalogue
# (assure/checkers/python-auth-declared-model/catalogue/AUTH-CATALOGUE-001.json; the Action ships no checker): the
# name of a rule no requirement row maps. test_pr_comment_demo_grade pins it to the catalogue file.
PR_CATALOGUE_PHRASES = {'python-auth-declared-model': {
    'AUTH-1': 'No route outside the declared public routes is reachable without signing in.',
    'AUTH-2': 'Routes that carry a declared role guard are reachable only by that role.',
    'AUTH-3': 'The signed-in identity is set only after second-factor verification.',
    'AUTH-4': 'Signing out always returns to the signed-out state.',
    'AUTH-5': 'Elevated sessions start only from a signed-in admin.',
    'AUTH-6': 'Bearer-token routes check the caller.'}}
# serve/requirements.py's default reason for a holding or disproven row: it says nothing about the rule, so the row's
# own words (its matched obligation's reason) take its place
PR_DEFAULT_REASONS = ('The matched methods hold within the stated observed bounds.',
                      'An applicable witnessed result contradicts the sentence.')
# "Not checked yet": one plain sentence per reason class ({s}: "app" for a python-* profile, else "system")
PR_UNCHECKED_WORDS = {
    'vacuous': 'the {s} declares none, so there is nothing to check',
    'missing_method': 'this profile does not check this yet; nothing for you to do',
    'not_observed': 'the check could not look at this part',
    'missing_premise': 'the check could not look at this part',
    'not_observable_at_pin': 'the check could not look at this part; nothing for you to do',
    'missing_baseline': 'the baseline for this version is not pinned yet; nothing for you to do',
    'needs_intent': 'this depends on what the {s} is for; say so in requirements.md',
    'representation': 'the check could not read this part in the form it is written',
    'not_evaluated': 'the check did not reach this part',
    'method_stopped_early': 'the check stopped before it reached this part; nothing for you to do',
    'checker_contract': 'the profile failed its own verification; nothing for you to do, Symbolia repairs it',
    'scope_mismatch': 'no profile in this check reads this kind of rule',
    'not_understood': 'Assure could not read this line of requirements.md; write it as one sentence',
    'duplicate_id': 'this id is used twice in requirements.md; give each rule its own id'}
PR_UNCHECKED_FALLBACK = 'the check could not decide this yet; the job summary gives the reason'
PR_VACUOUS_OBSERVED = 'the {s} has none, so there is nothing to check'
NOTHING_TO_DO = 'nothing for you to do'
_PR_REPOSITORY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}')
_PR_COMMIT = re.compile(r'[0-9a-f]{7,40}')
_PR_LOCATOR = re.compile(r'(%s):([1-9][0-9]{0,6})' % REPO_PATH_RE.pattern)
_PR_PROFILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
_PR_SCOPE_READ = re.compile(r'\bover [^:.]{1,100}: ([^.]{1,300})\.')
MAX_PR_LOCATORS = 5


def _plural(n, one, many):
    return '%d %s' % (n, one if n == 1 else many)


def _pr_requirements(env):
    """{requirement id: row} and {(machine, obligation id): the first requirement row matched to it}."""
    by_id, by_ob = {}, {}
    for r in requirement_rows(env) or ():
        by_id.setdefault(r.get('id'), r)
        for m in r.get('matched_obligations') or ():
            if isinstance(m, dict):
                by_ob.setdefault((m.get('machine'), m.get('id')), r)
    return by_id, by_ob


def _pr_static(env):
    return str(env.get('profile') or '').startswith('python-')    # a reading of the repository's files


def _pr_shows_machine(env):
    """False when the envelope reads one machine of one, none refused: naming it adds nothing for the reader."""
    m = _machines(env)
    return m is None or len(m['read']) != 1 or int(m['total']) != 1 or bool(m['refused'])


def _pr_obligation_text(env, r):
    if r.get('machine') and _pr_shows_machine(env):
        return '%s on %s' % (_clip(r.get('id')), _clip(r.get('machine')))
    return _clip(r.get('id'))


def _pr_phrase(env, ob_id):
    table = PR_CATALOGUE_PHRASES.get(env.get('profile')) if isinstance(env.get('profile'), str) else None
    return (table or {}).get(ob_id)


def _pr_words(env, ob_id, key):
    """The profile's plain words for an obligation (the envelope's `obligation_words`, from the profile row:
    short_name, plain_checked, plain_broken, remedy, remedy_generic), or None when the envelope carries none."""
    words = env.get('obligation_words') if isinstance(env.get('obligation_words'), dict) else {}
    w = words.get(ob_id) if isinstance(ob_id, str) else None
    t = w.get(key) if isinstance(w, dict) else None
    return t if isinstance(t, str) and t.strip() else None


def _pr_reading_ob(env, row):
    """The obligation's entry in `readings` for a row ({machine, id}), or None."""
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) \
            if isinstance(obs, list) else None
    except (AttributeError, TypeError):
        return None
    return ob if isinstance(ob, dict) else None


_PR_PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')


def _pr_fill(env, row, key):
    """The profile's template `key` for a failing obligation, its placeholders filled from the reading's own witnesses
    (each distinct value of the field, at most MAX_PR_LOCATORS); None when the profile gives none, or a witness lacks a
    field the template names, or the reading carries no witness. Never a value the witnesses do not hold."""
    row = row if isinstance(row, dict) else {}
    template = _pr_words(env, row.get('id'), key)
    names = _PR_PLACEHOLDER.findall(template) if template is not None else []
    if not names:
        return template
    ob = _pr_reading_ob(env, row) or {}
    ws = ob.get('witnesses') if isinstance(ob.get('witnesses'), list) else (
        [ob['witness']] if isinstance(ob.get('witness'), dict) else [])
    values = {}
    for n in names:
        vals = [w.get(n) if isinstance(w, dict) else None for w in ws]
        if not vals or not all(_scalar(v) and str(v).strip() for v in vals):
            return None
        seen = []
        for v in vals:
            if format_space(_clip(v)).strip() not in seen:
                seen.append(format_space(_clip(v)).strip())
        values[n] = ', '.join(seen[:MAX_PR_LOCATORS])
    return _PR_PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def _pr_remedy(env, row):
    """The profile's fix for a failing obligation filled from its witnesses (`_pr_fill`), else the obligation's unfilled
    generic remedy; None when the profile gives no fix."""
    row = row if isinstance(row, dict) else {}
    return _pr_fill(env, row, 'remedy') or _pr_words(env, row.get('id'), 'remedy_generic')


def _pr_trim(text):
    """`text` bounded, without its final full stop, its first letter upper case; None when empty."""
    t = format_space(_clip(text)).strip().rstrip('.').strip() if text is not None else ''
    return (t[:1].upper() + t[1:]) if t else None


def _pr_own_words(row, text):
    """`text` less serve/requirements.py's default reason and less a bare repeat of the row's status; None when nothing
    is left (the row then says nothing of its own)."""
    t = format_space(text).strip() if isinstance(text, str) else ''
    for d in PR_DEFAULT_REASONS:
        if t.startswith(d):
            t = t[len(d):].strip()
    if not t or t in (row.get('status'), row.get('status_text'), label(row.get('status'))):
        return None
    return t


def _pr_ob_row(env, machine, ob_id):
    return next((r for r in _obligation_rows(env) if r.get('machine') == machine and r.get('id') == ob_id), None)


def _pr_matched_rows(env, req):
    out = []
    for m in req.get('matched_obligations') or ():
        r = _pr_ob_row(env, m.get('machine'), m.get('id')) if isinstance(m, dict) else None
        if r is not None:
            out.append(r)
    return out


def _pr_reading_text(env, req):
    """The reading's own requirement line after its '<id> reads <state> through <obligation>:' lead, or None."""
    for rd in (env.get('readings') or {}).values() if isinstance(env.get('readings'), dict) else ():
        for q in (rd.get('requirements') if isinstance(rd, dict) else None) or ():
            if isinstance(q, dict) and q.get('id') == req.get('id') and isinstance(q.get('text'), str):
                m = re.match(r'\S+ reads \S+ through \S+: (.+)$', q['text'], re.S)
                if m:
                    return m.group(1)
    return None


def _pr_label(env, req, row):
    """(label, name): the requirement id and its sentence, or the obligation (with its machine when more than one is
    read) and the profile's short name for it, else the catalogue's phrase; name None when there is none."""
    if req is not None:
        return _clip(req.get('id')), _pr_trim(req.get('sentence'))
    row = row if isinstance(row, dict) else {}
    return _pr_obligation_text(env, row), _pr_trim(_pr_words(env, row.get('id'), 'short_name')
                                                   or _pr_phrase(env, row.get('id')))


def _pr_checked(env, req, row):
    """What Assure checked for a rule that holds, never the default holds sentence: the profile's plain sentence for
    each matched obligation (`obligation_words` plain_checked, when every one has it), then the matched obligation's
    reason (the checker's own words), then the requirement row's reason, then the reading's requirement line, then the obligation's
    catalogue phrase, then the rule's sentence or status."""
    rows = _pr_matched_rows(env, req) if req is not None else [row]
    if req is not None:
        rows = rows or [{'id': m.get('id'), 'machine': m.get('machine')} for m in req.get('matched_obligations') or ()
                        if isinstance(m, dict)]
    plain = [_pr_words(env, r.get('id'), 'plain_checked') for r in rows]
    if plain and all(plain):
        return '; '.join(dict.fromkeys(_pr_trim(p) for p in plain))
    for r in rows:
        w = _pr_own_words(r, r.get('reason'))
        if w:
            return _pr_trim(w)
    if req is not None:
        for text in (_pr_own_words(req, req.get('reason')), _pr_reading_text(env, req)):
            if text:
                return _pr_trim(text)
    for r in rows:
        if _pr_phrase(env, r.get('id')):
            return _pr_trim(_pr_phrase(env, r.get('id')))
    if req is not None:
        return _pr_trim(req.get('sentence')) or 'Holds'
    return _pr_trim(row.get('status_text') or row.get('status')) or 'Holds'


def _pr_reason_class(env, row):
    """A reading's reason class: its obligation's own `reason_class` in `readings` (vacuous, missing_method), else the
    row's status."""
    try:
        rd = (env.get('readings') or {}).get(row.get('machine'))
        rd = rd.get('reading') if isinstance(rd, dict) and isinstance(rd.get('reading'), dict) else rd
        obs = rd.get('obligations') if isinstance(rd, dict) else None
        ob = obs.get(row.get('id')) if isinstance(obs, dict) else next(
            (o for o in obs if isinstance(o, dict) and o.get('id') == row.get('id')), None) if isinstance(obs, list) \
            else None
        if isinstance(ob, dict) and isinstance(ob.get('reason_class'), str) and ob['reason_class']:
            return ob['reason_class']
    except (AttributeError, TypeError):
        pass
    return row.get('status')


def _pr_unchecked_words(env, cls):
    """The plain sentence for a reason class; "nothing for you to do" when the class is Symbolia's."""
    s = 'app' if _pr_static(env) else 'system'
    if cls == 'vacuous' and not _pr_static(env):
        words = PR_VACUOUS_OBSERVED.format(s=s)
    else:
        words = PR_UNCHECKED_WORDS.get(cls, PR_UNCHECKED_FALLBACK).format(s=s)
    if CLASS_OWNERS.get(cls) == 'symbolia' and NOTHING_TO_DO not in words:
        words += '; ' + NOTHING_TO_DO
    return words


def _pr_locators(env, req, row):
    """The locators a finding carries: the requirement row's (`requirement_locator`), then each witness's `locator`
    and the obligation's sibling `locator` in `readings`; at most MAX_PR_LOCATORS, never invented."""
    out = []
    if req is not None and requirement_locator(req):
        out.append(requirement_locator(req))
    if isinstance(row, dict):
        ob = _pr_reading_ob(env, row)
        if isinstance(ob, dict):
            ws = ob.get('witnesses') if isinstance(ob.get('witnesses'), list) else [ob.get('witness')]
            for w in ws + [ob]:
                loc = w.get('locator') if isinstance(w, dict) else None
                if _scalar(loc) and str(loc).strip():
                    out.append(_clip(loc))
    seen = []
    for loc in out:
        if loc not in seen:
            seen.append(loc)
    return seen[:MAX_PR_LOCATORS]


def blob_url(locator, repository=None, commit=None):
    """'https://github.com/<repo>/blob/<commit>/<path>#L<line>' for a repository path and line locator when the
    repository and commit are known and every part validates; None otherwise. The one place a blob link is built
    (the pull request comment and the proof tree, serve/proof_tree.py)."""
    m = _PR_LOCATOR.fullmatch(str(locator))
    repo_ok = (isinstance(repository, str) and _PR_REPOSITORY.fullmatch(repository) is not None
               and '..' not in repository)
    if m and repo_ok and isinstance(commit, str) and _PR_COMMIT.fullmatch(commit):
        return 'https://github.com/%s/blob/%s/%s#L%s' % (repository, commit, m.group(1), m.group(2))
    return None


def _pr_where(locator, repository=None, commit=None):
    """A file:line locator as a link to the commit's blob on GitHub when the repository and commit are known and the
    locator is a repository path and line ('[`app/x.py:7`](https://github.com/<repo>/blob/<commit>/app/x.py#L7)',
    `blob_url`), else as a code span; any other locator is escaped text. The link is built only from validated parts."""
    loc = str(locator)
    m = _PR_LOCATOR.fullmatch(loc)
    url = blob_url(loc, repository, commit)
    if url is not None:
        return '[`%s`](%s)' % (loc, url)
    if m or REPO_PATH_RE.fullmatch(loc):
        return '`%s`' % loc
    return esc(loc)


# Issue #3148: a broken sign-out rule says what is wrong with the declared sign-out view, from the reading's premise
# record for it (python-auth-declared-model extract_premises.py: 'premise signout-view:<module.view> (signout_view,
# declared): fault: <fault>[; <fault>]', with the view's locator), and gives the concrete fix. Each fault the checker
# writes (grade.py `signout_faults`, extract_premises.py) maps to (what the change does, the fix), '{v}' the view's
# name; a fault with no entry leaves the profile's words in place.
_PR_SIGNOUT = re.compile(r'premise signout-view:([A-Za-z_][A-Za-z0-9_.]{0,200}) \(signout_view, declared\): fault: (.+)')
_PR_SIGNOUT_WORDS = {
    'first statement is not the clearing write': ('your sign-out view {v} does not clear the session first',
                                                  'Make {c} the first line of {v}'),
    'the statements after the clearing write are not straight-line': (
        'your sign-out view {v} branches after it clears the session',
        'Keep {v} to plain steps after {c}, with no branch or loop'),
    'guarded': ('your sign-out view {v} is behind a guard', 'Remove the guard from {v}, so every signed-in user can '
                                                            'sign out'),
    'not registered as a route': ('your sign-out view {v} is not registered as a route', 'Register {v} as a route')}
_PR_SIGNOUT_PROFILE, _PR_SIGNOUT_OB = 'python-auth-declared-model', 'AUTH-4'


def _pr_signout(env, rows):
    """[(view, locator or None, (what, fix))] for a broken sign-out obligation among `rows`: one per declared sign-out
    view whose premise record carries a fault with words in _PR_SIGNOUT_WORDS (the first such fault), its locator
    'path:line' when the record gives one; [] otherwise (another profile, no fault, a fault with no words)."""
    if env.get('profile') != _PR_SIGNOUT_PROFILE or not any(
            isinstance(r, dict) and r.get('id') == _PR_SIGNOUT_OB for r in rows):
        return []
    rd = (env.get('readings') or {}) if isinstance(env.get('readings'), dict) else {}
    out = []
    for reading in rd.values():
        for w in (reading.get('warnings') if isinstance(reading, dict) else None) or ():
            m = _PR_SIGNOUT.fullmatch(w.get('text') or '') if isinstance(w, dict) and isinstance(
                w.get('text'), str) else None
            if m is None:
                continue
            words = next((_PR_SIGNOUT_WORDS[f.split(' (')[0].strip()] for f in m.group(2).split('; ')
                          if f.split(' (')[0].strip() in _PR_SIGNOUT_WORDS), None)
            if words is None:
                continue
            loc = next(('%s:%s' % (x.get('path'), x.get('line')) for x in w.get('locators') or ()
                        if isinstance(x, dict) and _PR_LOCATOR.fullmatch('%s:%s' % (x.get('path'), x.get('line')))),
                       None)
            out.append((m.group(1).rsplit('.', 1)[-1], loc, words))
    return out[:MAX_PR_LOCATORS]


def _pr_signout_text(signout, part, code=False, where=None):
    """The `part` (0 what, 1 fix) of each sign-out fault, joined: names in code spans when `code`, and for the fix
    each view's locator in brackets rendered by `where` (plain when None)."""
    out = []
    for view, loc, words in signout:
        t = words[part].format(v='`%s`' % view if code else view, c='`session.clear()`' if code else 'session.clear()')
        if part == 1 and loc is not None:
            t += ' (%s)' % (where(loc) if where else loc)
        out.append(t)
    return '; '.join(out)


def _pr_item(env, finding, by_id, by_ob):
    """{label, name, text, what, where, locators, fix, requirement, sentence, escaped} for one red finding: for a
    requirement row (or an obligation a requirement row is matched to) its id and sentence, what the change does (the
    profile's `plain_broken` filled from the witnesses, else the row's own reason, else its matched obligation's), the
    locators, and the fix (the profile's remedy filled from the witnesses, `_pr_remedy`, else the row's action); else
    the obligation and its machine, the profile's short name for it, its status text, the witness the summary shows and
    the profile's remedy."""
    kind, ob_id, row = finding
    row = row if isinstance(row, dict) else {}
    req = by_id.get(row.get('requirement')) if row.get('requirement') is not None else by_ob.get(
        (row.get('machine'), row.get('id')))
    lab, name = _pr_label(env, req, row if row.get('id') is not None else {'id': ob_id})
    locators = _pr_locators(env, req, row)
    if req is not None:
        obs = [row] + _pr_matched_rows(env, req)        # the finding's own obligation, then the rule's matched ones
        fix = CONTRACT_WORDS if req.get('reason_class') == 'checker_contract' else (
            next((x for x in map(lambda r: _pr_remedy(env, r), obs) if x), None) or req.get('establishing_action'))
        what = (next((x for x in map(lambda r: _pr_fill(env, r, 'plain_broken'), obs) if x), None)
                or _pr_own_words(req, req.get('reason')) or _pr_own_words(row, row.get('reason')))
        if what is None:
            what = next((_pr_own_words(r, r.get('reason')) for r in _pr_matched_rows(env, req)
                         if _pr_own_words(r, r.get('reason'))), None) or witness_words(env, row)
        signout = _pr_signout(env, obs)              # issue #3148: the sign-out view's own fault, line and fix
        if signout:
            what, fix = _pr_signout_text(signout, 0), _pr_signout_text(signout, 1)
            locators = [loc for _, loc, _ in signout if loc] or locators
        return {'label': lab, 'name': name, 'text': format_space(req.get('sentence') or req.get('id')),
                'what': what, 'where': locators[0] if locators else None, 'locators': locators, 'fix': fix,
                'requirement': req.get('id'), 'sentence': format_space(req.get('sentence') or ''), 'escaped': None,
                'signout': signout}
    text = _pr_obligation_text(env, row) if row.get('id') is not None else _clip(ob_id)
    plain = _pr_fill(env, row, 'plain_broken') if row.get('id') is not None else None
    return {'label': lab, 'name': name, 'text': text,
            'what': plain or row.get('status_text') or (label(row['status']) if row.get('status') else None),
            'where': None, 'locators': locators, 'fix': _pr_remedy(env, row) if row.get('id') is not None else None,
            'requirement': None, 'sentence': None,
            # the plain words say what the witness shows, and its locators are under Where
            'escaped': None if plain else (_row_extra(env, row) if row else None)}


# Issue #3146: a refusal that names the line Assure could not read (the checker's incomplete-reading reason
# `<class> (<module>, <line>, <what>)`, grade.py `_REASON_RE`); several are joined with '; '.
_PR_UNREAD = re.compile(r'([a-z][a-z0-9_]+) \(([^,()\r\n]{1,200}), ([1-9][0-9]{0,6}), ([^;\r\n]{0,200}?)\)(?=;|\s*$)')
_PR_UNREAD_WHAT = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,79}')
MAX_PR_UNREAD = 3


def _pr_unread(env):
    """[(what, 'path:line')] for the lines a refused check names as unread (`machines.refused` reasons, then the rows'
    reasons), each module resolved to the one repository file the manifest holds for it (`source_candidates`; none or
    several: that line is skipped, never guessed); `what` is the source text when it is a plain dotted name, else
    None. At most MAX_PR_UNREAD + 1 (the comment says how many more), deduplicated, in order."""
    m = _machines(env)
    reasons = [r.get('reason') for r in (m['refused'] if m is not None else ()) if isinstance(r, dict)]
    reasons += [r.get('reason') for r in _rows(env)]
    files = (env.get('input') or {}).get('files') if isinstance(env.get('input'), dict) else None
    out = []
    for reason in reasons:
        if not isinstance(reason, str):
            continue
        for x in _PR_UNREAD.finditer(reason[:_STRUCTURAL_REASON_CLIP]):
            _, source, line, what = (g.strip() for g in x.groups())
            if '/' in source:
                path = source if REPO_PATH_RE.fullmatch(source) else None
            else:
                found = source_candidates(source, files)
                path = next(iter(found)) if len(found) == 1 else None
            if path is None or not _PR_LOCATOR.fullmatch('%s:%s' % (path, line)):
                continue
            item = (what if _PR_UNREAD_WHAT.fullmatch(what) else None, '%s:%s' % (path, line))
            if item not in out:
                out.append(item)
    return out


def _pr_unread_words(unread, where=None):
    """'Assure could not read <what> at <where>[, ... and ...], so it checked nothing in this change.': plain text
    (the proof tree) when `where` is None, else Markdown with each `what` a code span (`_PR_UNREAD_WHAT` admits no
    character Markdown reads) and each locator rendered by `where` (a link or code span, `_pr_where`)."""
    code = where is not None
    where = where or (lambda loc: loc)
    parts = [('%s at %s' % ('`%s`' % w if code else w, where(loc)) if w else where(loc))
             for w, loc in unread[:MAX_PR_UNREAD]]
    if len(unread) > MAX_PR_UNREAD:
        parts.append(_plural(len(unread) - MAX_PR_UNREAD, 'more line', 'more lines'))
    joined = parts[0] if len(parts) == 1 else '%s and %s' % (', '.join(parts[:-1]), parts[-1])
    return 'Assure could not read %s, so it checked nothing in this change.' % joined


def pr_reading(envelope):
    """The comment's reading (issue #2189), decided from the sets the job summary decides from: `red_findings` (the
    obligation readings on machines that were read, then the requirement rows), the read set, `could_not_look`, `a0`
    and `outcome`. Returns {no_reading, red, broken, deviations, others, holds, unchecked}:
    - no_reading: None, or the summary's words for why there is no reading (`a0`: "No reading: input integrity";
      an outcome that is not `verdict`: the lines a refusal names as unread when it names any (issue #3146,
      `_pr_unread`), else "No verdicts"; nothing could be read: "Could not look");
    - unread: those lines, [(what, 'path:line')], for the comment to link; empty otherwise;
    - red: `red_findings(envelope)`, unchanged; every red finding is in exactly one of broken, deviations (those
      marked red) and others, so their counts add up to len(red);
    - broken: the 'disproven' findings whose reading is not `deviates` (a deviation is never called broken);
    - deviations: every `deviates` reading on a machine that was read, as (item, red);
    - others: the 'not_proven', 'strict' and 'chosen' findings, as (kind, item);
    - holds: the requirement rows that hold, then the `holds` readings on read machines no requirement row names, each
      {label, name, checked} (`_pr_label`, `_pr_checked`);
    - unchecked: every other requirement row and reading, vacuous ones included (never shown as holds), and a reading
      the checker kept on a refused machine as not observed, each {label, name, requirement, words}: the plain
      sentence for its reason class (`_pr_unchecked_words`), None when `unread` is the reason for all of them."""
    env = envelope if isinstance(envelope, dict) else {}
    by_id, by_ob = _pr_requirements(env)
    red = red_findings(env)
    read = _read_set(env)
    broken, others, red_dev = [], [], set()
    shown_reqs, shown_rows, shown_ids = set(), set(), set()
    for f in red:
        kind, ob_id, row = f
        item = _pr_item(env, f, by_id, by_ob)
        if item['requirement'] is not None:
            shown_reqs.add(item['requirement'])
        if isinstance(row, dict) and row.get('requirement') is None:
            shown_rows.add((row.get('machine'), row.get('id')))
        if kind in ('not_proven', 'strict'):
            shown_ids.add(ob_id)
        if kind == 'disproven' and isinstance(row, dict) and row.get('status') == 'deviates':
            red_dev.add((row.get('machine'), row.get('id')))
        elif kind == 'disproven':
            broken.append(item)
        else:
            others.append((kind, item))
    obligations = [r for r in _obligation_rows(env) if not is_machine_refusal(r)]
    deviations = []
    for r in obligations:
        if r.get('status') == 'deviates' and r.get('machine') in read:
            key = (r.get('machine'), r.get('id'))
            item = _pr_item(env, ('disproven', r.get('id'), r), by_id, by_ob)
            shown_rows.add(key)
            if item['requirement'] is not None:
                shown_reqs.add(item['requirement'])
            deviations.append((item, key in red_dev))
    holds, unchecked = [], []
    spent_rows = _pr_spent_rows(env)
    # issue #3146: when the check could not read a named line, that line is the reason for every rule; no rule's
    # wording is blamed
    unread = _pr_unread(env) if env.get('a0') is None and env.get('outcome') != 'verdict' else []
    for r in requirement_rows(env) or ():
        if r.get('id') in shown_reqs:
            continue
        shown_reqs.add(r.get('id'))
        lab, name = _pr_label(env, r, None)
        if r.get('state') == 'holds':
            holds.append({'label': lab, 'name': name, 'checked': _pr_checked(env, r, None)})
        else:
            words = None if unread else _pr_unchecked_words(env, r.get('reason_class'))
            if spent_rows and _pr_unread_row(r):    # the Director, 14 Oct 2026: the spent balance left it unread
                words = PR_SPENT_ROW if words is None else words + '; ' + PR_SPENT_ROW
            unchecked.append({'label': lab, 'name': name, 'requirement': r.get('id'), 'words': words})
    for r in obligations:
        key = (r.get('machine'), r.get('id'))
        if key in shown_rows or r.get('id') in shown_ids:
            continue
        req = by_ob.get(key)
        if req is not None and req.get('id') in shown_reqs:
            continue                                   # its requirement row is listed already
        lab, name = _pr_label(env, None, r)
        if kept_on_refused(env, r):
            unchecked.append({'label': lab, 'name': name, 'requirement': None,
                              'words': '%s (machine %s was not read)' % (_pr_unchecked_words(env, KEPT_READ_AS),
                                                                        _clip(r.get('machine')))})
        elif r.get('machine') not in read:
            continue                                   # a refused machine's rows: the closing line names the machine
        elif r.get('status') == 'holds':
            holds.append({'label': lab, 'name': name, 'checked': _pr_checked(env, None, r)})
        else:
            unchecked.append({'label': lab, 'name': name, 'requirement': None,
                              'words': None if unread else _pr_unchecked_words(env, _pr_reason_class(env, r))})
    if env.get('a0') is not None:
        no_reading = ('No reading: input integrity. The input integrity gate stopped the check, so no rule was read: '
                      '%s' % _clip(env.get('a0')))
    elif env.get('outcome') != 'verdict' and unread:
        no_reading = _pr_unread_words(unread)       # issue #3146: the line it could not read
    elif env.get('outcome') != 'verdict':
        no_reading = ('No verdicts: none of the readings is a verdict that checked something, so no rule was read; '
                      'a vacuous reading only says a domain was empty.')
    elif could_not_look(env):
        no_reading = 'Could not look: %s.' % _could_not_look_words(env)
    else:
        no_reading = None
    return {'no_reading': no_reading, 'red': red, 'broken': broken, 'deviations': deviations, 'others': others,
            'holds': holds, 'unchecked': unchecked, 'unread': unread}


def pr_heading(reading):
    """'Assure: <n> rules broken by this change' ('no rule', '1 rule'), or 'Assure: no reading of this change' when
    the reading has none, then one count per other red kind and the deviations; the counts of broken, red deviations
    and other kinds add up to the red findings."""
    parts = []
    n = len(reading['broken'])
    if reading['no_reading'] is not None:
        parts.append(NO_READING_HEAD)
    if reading['no_reading'] is None or n:
        parts.append('%s broken by this change' % ('no rule' if n == 0 else _plural(n, 'rule', 'rules')))
    if reading['deviations']:
        parts.append(_plural(len(reading['deviations']), 'deviation', 'deviations'))
    for kind, words, _ in PR_OTHER_KINDS:
        k = len([1 for x, _ in reading['others'] if x == kind])
        if k:
            parts.append('%d %s' % (k, words))
    return 'Assure: ' + '; '.join(parts)


def _pr_bullet(item, label_what):
    line = '- **%s**' % esc(item['text'])
    sub = []
    if item['what']:
        sub.append('  - %s: %s%s' % (label_what, esc(item['what']), ' (%s)' % esc(item['where'])
                                     if item['where'] else ''))
    elif item['where']:
        sub.append('  - Where: %s' % esc(item['where']))
    if item.get('escaped'):
        sub.append('  - Witness: %s' % item['escaped'])          # `_row_extra` is escaped and bounded already
    if item['fix']:
        sub.append('  - Fix: %s' % esc(item['fix']))
    return [line] + sub


def _pr_broken(item, repository, commit):
    """One broken rule: '### Broken: <name> (<id>)', what the change does with each locator (a link to the commit's
    blob when the repository and commit are known), the witness the summary shows, the requirement as quoted, the fix."""
    head = ('%s (%s)' % (esc(item['name']), esc(item['label'])) if item['name'] else esc(item['label']))
    out = ['### Broken: %s' % head, '']
    where = ', '.join(_pr_where(x, repository, commit) for x in item['locators'])
    parts = []
    if item.get('signout'):
        parts.append('What this change does: %s.' % _pr_signout_text(item['signout'], 0, code=True))
    elif item['what']:
        parts.append('What this change does: %s.' % esc(str(item['what']).rstrip('.')))
    if where:
        parts.append('Where: %s.' % where)
    if item.get('escaped'):
        parts.append('Witness: %s.' % str(item['escaped']).rstrip('.'))     # `_row_extra` is escaped already
    if parts:
        out += [' '.join(parts), '']
    if item['requirement'] is not None and item['sentence']:
        out += ['> **%s** (`requirements.md`): %s' % (esc(item['requirement']), esc(item['sentence'])), '']
    if item.get('signout'):
        out += ['**Fix:** %s.' % _pr_signout_text(item['signout'], 1, code=True,
                                                 where=lambda loc: _pr_where(loc, repository, commit)), '']
    elif item['fix']:
        out += ['**Fix:** %s' % esc(item['fix']), '']
    return out


def _pr_rule(lab, name):
    return '**%s** %s' % (esc(lab), esc(name)) if name else '**%s**' % esc(lab)


def _pr_closing(env, commit):
    """The closing line: a static check that could not look says so; otherwise what Assure read (for a python-* profile the profile's own scope note, '... over <catalogue>:
    <what it reads>.'; else the machines read and not read when there is more than one or one was refused, else the
    inputs the profile lists), that it ran none of the app's code (python-* profiles, which read the repository's
    files), the profile and the commit."""
    words = None
    if _pr_static(env):
        for note in env.get('scope_notes') or ():
            m = _PR_SCOPE_READ.search(note) if isinstance(note, str) else None
            if m:
                words = esc(m.group(1).strip())
                break
    m = _machines(env)
    if words is None and m is not None and _pr_shows_machine(env):
        refused = [r.get('machine') for r in m['refused'] if isinstance(r, dict)]
        words = ('machines %s' % ', '.join(esc(x) for x in m['read'])) if m['read'] else 'no machine'
        words += ('; it could not read %s' % ', '.join(esc(x) for x in refused)) if refused else ''
    if words is None:
        words = 'the inputs the profile lists'
    profile = env.get('profile')
    profile = ('`%s`' % profile if isinstance(profile, str) and _PR_PROFILE.fullmatch(profile) else esc(profile))
    named = '`%s`' % commit[:7] if isinstance(commit, str) and _PR_COMMIT.fullmatch(commit) else (
        esc(commit[:12]) if commit else 'not named')
    reading = ('Assure could not read this change.' if _pr_static(env) and could_not_look(env)
               else 'Assure read %s.' % words)
    return '%s%s Profile %s, commit %s.' % (
        reading, " It ran none of the app's code." if _pr_static(env) else '', profile, named)


# The Director, 14 Oct 2026: "after the $1 ends the comment says please buy credits or upgrade". Free credits are not
# purchasable (assure/pricing.py: paying begins at the USD 20 tier), so the line offers the Premium upgrade only.
PR_SPENT_WORDS = ('Your free USD 1 for reading your requirements and writing reports is used up. '
                  'The checks above still run.')
PR_SPENT_UPGRADE = 'To keep Assure reading your own words, upgrade to Premium (USD 20 a month):'
# a requirement line left unread because the shared free balance was spent (#2315's `requirements_compilation` block,
# status `refused` with refusal `allowance_exhausted`, on a verdict carrying the spent notice): said on its "Not
# checked yet" row
PR_SPENT_ROW = 'not read: your free balance for reading requirements is used up'
# serve/requirements_compiler.py CANDIDATE_CLASSES (issue #2544: never a grammar-refused row). render ships in the
# Action, which imports no API-side module, so this is a copy; tests/serving/test_spent_pr_comment_accept.py pins it
_PR_COMPILE_CANDIDATES = ('missing_method',)


def _spent_notice(up):
    """True when `upgrade` carries the server's spent notice (serve/api.py `_with_upgrade`, usage.SPENT_NOTICE) as one
    plain sentence: the same test `upgrade_markdown` applies before it prints the notice."""
    notice = up.get('notice') if isinstance(up, dict) else None
    return (isinstance(notice, str) and bool(notice.strip()) and not _CONTROL.search(notice) and len(notice) <= CAP
            and '://' not in notice and not _UPGRADE_URL.search(notice))


def pr_spent_line(envelope):
    """The comment's one line for a free account whose shared once-only USD 1 is spent (`upgrade.notice`), or None:
    PR_SPENT_WORDS, then PR_SPENT_UPGRADE and `upgrade.url` as `<url>` only when that url is the server's own
    buy.stripe.com payment link (`_UPGRADE_URL`). None when the verdict carries no `upgrade` (a paid account, or a
    server with no payment link) or no notice (the balance is not spent)."""
    up = envelope.get('upgrade') if isinstance(envelope, dict) else None
    if not _spent_notice(up):
        return None
    url = up.get('url')
    if isinstance(url, str) and _UPGRADE_URL.fullmatch(url):
        return '%s %s <%s>' % (_esc_line(PR_SPENT_WORDS), _esc_line(PR_SPENT_UPGRADE), url)
    return _esc_line(PR_SPENT_WORDS)


def _pr_spent_rows(env):
    """True when #2315's `requirements_compilation` block says the lines were not read because the free balance was
    spent: status `refused`, refusal `allowance_exhausted`, and the verdict carries the server's spent notice
    (`upgrade.notice`, a free account whose once-only balance is spent). False otherwise: the block absent or saying
    anything else, a paid account's spent month (no `upgrade`), a server with no payment link, balance left."""
    block = env.get('requirements_compilation')
    return (isinstance(block, dict) and block.get('status') == 'refused'
            and block.get('refusal') == 'allowance_exhausted' and _spent_notice(env.get('upgrade')))


def _pr_unread_row(r):
    """A requirement row the compiler would have read and did not (`requirements_compiler.candidates`, with no
    `compiled` reading): not established, a candidate reason class, a sentence."""
    return (r.get('state') == 'not_established' and r.get('reason_class') in _PR_COMPILE_CANDIDATES
            and isinstance(r.get('sentence'), str) and bool(r['sentence'].strip()) and 'compiled' not in r)


# Issue #2651: the footer's link to the check's proof tree, served by the API (`GET /v1/trees/{id}?exp=&sig=`). The
# suffix is where layer 2 appends its formal-model status (" · formal model current"); layer 1 writes none.
PR_TREE_LINE = 'Proof tree: %d of %d checks proven%s →'
TREE_URL_PATH = re.compile(r'/v1/trees/[0-9a-f]{32}\?exp=[1-9][0-9]{0,11}&sig=[0-9a-f]{64}')
_TREE_BASE = re.compile(r'https://[A-Za-z0-9.-]{1,253}(?::[0-9]{1,5})?|http://(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?')


def tree_url_ok(url, bases=()):
    """True when `url` is '<base>/v1/trees/<32 hex>?exp=<unix>&sig=<64 hex>' for one of `bases` (each an https origin,
    or http on a loopback host), nothing else in it; the only shape the comment links to."""
    if not isinstance(url, str):
        return False
    for base in bases:
        base = str(base or '').rstrip('/')
        if _TREE_BASE.fullmatch(base) and url.startswith(base) and TREE_URL_PATH.fullmatch(url[len(base):]):
            return True
    return False


def pr_tree_line(tree, bases=()):
    """'[Proof tree: X of Y checks proven →](<url>)' for `tree` {url, proven, total[, suffix]} whose url passes
    `tree_url_ok` for `bases` and whose counts are integers with 0 <= X <= Y; None otherwise (no line)."""
    t = tree if isinstance(tree, dict) else {}
    x, y = t.get('proven'), t.get('total')
    if type(x) is not int or type(y) is not int or not 0 <= x <= y or not tree_url_ok(t.get('url'), bases):
        return None
    return '[%s](%s)' % (PR_TREE_LINE % (x, y, ''), t['url'])


# ---------- assure-on-itself-001 (the Director, 17 Oct 2026; night read of #3843, H1) ----------
# The comment states no model provenance until a verdict carries it (#3870's served remodel data): `engine` names the
# engine that ran the check, so a Premium or Pro comment (one carrying the proof-tree link the server adds for those
# plans, serve/api.py `_with_tree`) names that engine and nothing more. A free comment is unchanged.
_PR_ENGINE = re.compile(r'[0-9a-f]{40}')


def pr_engine_line(env):
    """'Checked by Assure engine `<7 hex>`.' from the verdict's `engine.commit` (40 hex), else None."""
    eng = env.get('engine') if isinstance(env, dict) else None
    c = eng.get('commit') if isinstance(eng, dict) else None
    return 'Checked by Assure engine `%s`.' % c[:7] if isinstance(c, str) and _PR_ENGINE.fullmatch(c) else None


def pr_comment_markdown(envelope, commit=None, repository=None, tree=None, tree_bases=()):
    """The one pull request comment for a verdict envelope (issue #2189), from `pr_reading`: the marker the Action
    finds it by; the heading (`pr_heading`); for no reading, the summary's words for why; then the sections that have
    entries, each headed in words: one "Broken: <rule>" per broken rule (what the reading says the change does, each
    file:line linked to the commit's blob on GitHub when `repository` ('owner/name') and `commit` are known, the
    requirement as quoted, the fix), Deviations (each says whether your fail-on stops on it; a deviation is never
    called broken), Other findings (not proven, not resolved under strict, stopped by your choice), Still holds (a
    table: the rule, labelled by its requirement id, and what Assure checked for it), Not checked yet (one plain
    sentence per remaining rule for its reason class, "nothing for you to do" when the class is Symbolia's); then a
    rule, the proof tree's line when `tree` carries a validated tree_url (`pr_tree_line`, issue #2651), and one
    closing line (`_pr_closing`) under it. A free account whose once-only USD 1 is spent (`upgrade.notice`) reads one
    line above that rule (`pr_spent_line`), and a requirement row the spent balance left unread says so on its "Not
    checked yet" row (PR_SPENT_ROW). Deterministic: closed templates over the envelope's own words,
    each escaped and bounded with `esc`; the one link is built from the validated repository, commit and locator."""
    env = envelope if isinstance(envelope, dict) else {}
    rd = pr_reading(env)
    out = [PR_COMMENT_MARKER, '## %s' % _esc_line(pr_heading(rd)), '']
    if rd['unread']:                          # issue #3146: the lines it could not read, linked
        out += [_pr_unread_words(rd['unread'], lambda loc: _pr_where(loc, repository, commit)), '']
    elif rd['no_reading'] is not None:
        out += [esc(rd['no_reading']), '']
    for item in rd['broken'][:MAX_ANNOTATIONS]:
        out += _pr_broken(item, repository, commit)
    if rd['deviations']:
        out += ['### Deviations', '', 'A deviation differs from the baseline; it is not a broken rule.', '']
        for item, red in rd['deviations'][:MAX_ANNOTATIONS]:
            out += _pr_bullet(item, 'Reading')
            if red:
                out.append('  - Your fail-on names deviates, so it stops the job.')
        out.append('')
    if rd['others']:
        out += ['### Other findings', '']
        words = {k: w for k, _, w in PR_OTHER_KINDS}
        for kind, item in rd['others'][:MAX_ANNOTATIONS]:
            out.append('- **%s**: %s.' % (esc(item['text']), words[kind]))
        out.append('')
    if rd['holds']:
        out += ['### Still holds', '', '| Rule | What Assure checked |', '| --- | --- |']
        out += ['| %s | %s |' % (_pr_rule(h['label'], h['name']), esc(h['checked']))
                for h in rd['holds'][:MAX_ANNOTATIONS]]
        out.append('')
    if rd['unchecked']:
        out += ['### Not checked yet', '']
        for u in rd['unchecked'][:MAX_ANNOTATIONS]:
            if u['words'] is None:                  # issue #3146: the reason is the unread line, said once above
                out.append('- %s' % (_pr_rule(u['label'], u['name']) if u['requirement'] is not None
                                     else '**%s**' % esc(u['name'] or u['label'])))
                continue
            if u['requirement'] is not None:
                rule = '%s:' % _pr_rule(u['label'], u['name'])
            else:
                rule = '**%s:**' % esc(u['name'] or u['label'])
            out.append('- %s %s.' % (rule, esc(u['words'])))
        out.append('')
    engine = pr_engine_line(env) if pr_tree_line(tree, tree_bases) is not None else None   # Premium and Pro only
    if engine is not None:
        out += [engine, '']
    spent = pr_spent_line(env)                   # the Director, 14 Oct 2026: the spent free balance, above the footer
    if spent is not None:
        out += [spent, '']
    out.append('---')
    line = pr_tree_line(tree, tree_bases)       # issue #2651: only for a verdict that carries a validated tree_url
    if line is not None:
        out += [line, '']
    out.append('<sub>%s</sub>' % _pr_closing(env, commit))
    return '\n'.join(out) + '\n'


# ---------- assure-on-itself-001 (the Director, 17 Oct 2026; requirements.md A2): the comment for a refused run ----------
PR_REFUSED_HEADING = 'Assure could not check this pull request'
PR_MAX_PROMISES = 100       # within GitHub's comment size at the requirements bounds' line length
PR_PROMISES_HEADING = 'Your requirements.md, promise by promise'
PR_UNREAD_PROMISES = ('The requirements file the Assure step names was not read: this run was refused before it, so no '
                      'promise is listed.')
PR_NO_PROMISES = ('No requirements file was sent, so no promise is listed. Add `requirements: requirements.md` to the '
                  'Assure step to send yours.')
PR_REFUSED_TREE = ('Proof tree: none for this run. A proof tree comes with a verdict, on the Premium and Pro plans; '
                   'this run was refused before a verdict.')
#: a promise line as serve/requirements.py `_parse` reads one: an optional list marker, an id holding a digit, an
#: optional [scope] tag, a colon, the sentence. For listing only: the server alone decides a promise.
_PR_PROMISE = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)?([A-Za-z][A-Za-z0-9_.-]{0,63})\s*(?:\[[^\]\n]*\])?\s*:\s*(\S.*?)\s*$')
_PR_OUTCOME = re.compile(r'[a-z][a-z_]{0,40}')


def pr_promises(text):
    """[(id, sentence)] for each line of requirements text that names a promise id (one holding a digit, as the server's
    parser requires), in file order; [] for no text."""
    out = []
    for line in (text or '').split('\n'):
        m = _PR_PROMISE.match(line)
        if m and re.search(r'[0-9]', m.group(1)):
            out.append((m.group(1), m.group(2)))
    return out


def pr_refusal_markdown(failure, requirements_text=None, step=None, commit=None, named=False):
    """The one pull request comment for a refused run (a failure envelope): the marker; the heading; the refusal's
    outcome and reason; one next step (`step` when the Action has one, else `next_step`); each promise of the
    requirements text sent (`pr_promises`) reading `not established` with the refusal as its reason, or the line that
    names the input to send one; the proof tree's line (none for this run); and the commit. Deterministic; every
    customer-facing value is escaped with `esc`."""
    f = failure if isinstance(failure, dict) else {}
    outcome = f.get('outcome')
    word = '`%s`' % outcome if isinstance(outcome, str) and _PR_OUTCOME.fullmatch(outcome) else esc(outcome)
    out = [PR_COMMENT_MARKER, '## %s' % PR_REFUSED_HEADING, '',
           'This run was refused (%s): %s' % (word, esc(f.get('reason'))), '',
           '**Next step:** %s' % esc(step or next_step(f)), '']
    promises = pr_promises(requirements_text)
    if promises:
        why = 'nothing was checked: this run was refused (%s) before any promise was read' % word
        out += ['### %s' % PR_PROMISES_HEADING, '', 'Assure decides 0 of %d promises on this run.' % len(promises), '',
                '| Promise | Reading | Why |', '| --- | --- | --- |']
        out += ['| **%s** %s | not established | %s |' % (esc(pid), esc(sentence), why)
                for pid, sentence in promises[:PR_MAX_PROMISES]]
        if len(promises) > PR_MAX_PROMISES:
            out += ['', 'And %d more, each not established for the same reason.' % (len(promises) - PR_MAX_PROMISES)]
        out.append('')
    else:
        out += [PR_UNREAD_PROMISES if named else PR_NO_PROMISES, '']   # night read L1: named, refused before the read
    named = '`%s`' % commit[:7] if isinstance(commit, str) and _PR_COMMIT.fullmatch(commit) else 'not named'
    out += ['---', PR_REFUSED_TREE, '', '<sub>Assure reached no verdict on this run. Commit %s.</sub>' % named]
    return '\n'.join(out) + '\n'

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
