"""The RF-28 collector's whole-line marker, recognised exactly as MARKER-CONTRACT-001 states it (accepted at
coordination heading 1620). Standard library and serve.outcomes only; imports no engine byte, so the public Action tree
ships it and the server runs it at admission (serve/faithful.py `check`).

The marker. The RF-28 collector replaces a rule, setting or other parsed line it cannot keep by exactly one line:

    !collect_pg-withheld line <N> reason <CODE>
    !collect_pg-withheld line <N> reason <CODE> setting <name>

- `MARKER_RE` is the contract's grammar; a line is a marker only by `fullmatch` on the line without its line ending.
- Lines are counted at '\\n' only. Exactly one '\\r' before the '\\n' is line ending; a further '\\r' is part of the line,
  so such a line is not a marker (`physical_lines`).
- `<N>` must equal the line's own physical number; `<CODE>` must be in `MARKER_REASONS`, copied from the contract's
  closed list. A line that starts with the prefix (after any whitespace, as the checker reads it; `starts_marker`) and
  fails either rule, or fails the grammar, is a broken collection (contract reading rule 5): `bad_input` naming the
  file and line, never the line's text. So is any such line in a JSON file.
- The checker splits lines with `str.splitlines`, which also breaks at a lone '\\r', '\\x0b', '\\x0c', '\\x1c' to
  '\\x1e', U+0085, U+2028 and U+2029. A '\\n'-line in which the prefix begins a piece after one of those breaks would be a
  marker to the checker at a line number this layer does not count, so it is `bad_input` too (`marker_grammar`, or
  `marker_in_json` in a JSON file), naming the file and this layer's line (refutation 008, G1).

What a marker means (contract reading rules 1 to 4). It is never a comment and never absent: it is a rule, setting or
line that was NOT OBSERVED. The serving layer keeps it byte for byte (the Action's withholding pass sees no '#' and no
quote in it), reports it as `not observed: <file> line <N> (<reason in plain words>)`, and leaves the reading to the
checker. How the shipped observed checker (derive_observed) reads it:
- pg_hba.conf and the files it includes: every reading built on the rules reads `not observed: pg_hba raw/<file>:<N>
  withheld by the collector (reason <CODE>)` (ruling 26, `hba_withheld_gap`), and the machines that read the rules
  are refused.
- postgresql.conf grammar: the frozen parse_conf notes the marker as an unparseable line, and the checker re-classes
  that note as `collector_marker`, which refuses nothing (derive_observed MS-2, `note_is_conf_marker`). A marker that
  names a setting makes that setting not observed (`setting_withheld`). A marker without a setting name changes no
  reading at all. That is safe only because a configured line is never a verdict premise (setting_tag, R8): the
  checker reads settings from pg_settings, so the gap text names the configured line, never the withheld one.
  tests/serving/test_rf28_markers.py runs the shipped checker with and without such a marker and pins that no reading
  differs.
The serving layer never reads a marked line better or worse than the checker: it adds no verdict, removes none and
changes no status.

Which collector wrote the collection (`generation`). The sidecar tells it: the RF-28 sidecar carries the objects
`connection` and `session` (RF-28 (d), (e)) and every `redaction_withheld` row carries `line` and `reason`; an earlier
sidecar carries neither. `collector` reports the sidecar's `collector.tool_sha256` prefix for the record only; the
generation is never decided by a digest (the RF-28 freeze may still change it).
"""
from __future__ import annotations

import json
import re
from collections import namedtuple

from .outcomes import Refusal, malformation

PREFIX = '!collect_pg-withheld'
MARKER_RE = re.compile(r'!collect_pg-withheld line ([1-9][0-9]{0,8}) reason ([A-Z][A-Z0-9-]+)'
                       r'(?: setting ([a-z_][a-z0-9_.]{0,62}))?')
# MARKER-CONTRACT-001, "Closed list of reason codes", whole-line markers; the plain words are the serving layer's.
MARKER_REASONS = {
    'HBA-UNTERMINATED-QUOTE': 'a pg_hba rule with a quote that does not close on its line',
    'HBA-POSITIONAL': 'a pg_hba rule whose type, field count or a positional field could not be kept',
    'HBA-OVER-LENGTH': 'a pg_hba rule longer than the collector keeps',
    'HBA-SECRET-LEFT': 'a pg_hba rule that still showed a secret pattern after its options were withheld',
    'HBA-CONTROL-CHARACTER': 'a pg_hba rule holding a control or line-separator character',
    'HBA-CONTINUATION': 'one line of a continued pg_hba rule that was withheld',
    'CONF-UNPARSED-LINE': 'a configuration line that is not a setting and showed a secret pattern',
    'CONF-UNTERMINATED-VALUE': 'a setting whose quoted value does not close on its line',
    'CONF-TRAILING-TEXT': 'a setting followed by text that is not a comment',
    'CONF-SECRET-LEFT': 'a setting that still showed a secret pattern after its value was withheld',
    'CONF-CONTROL-CHARACTER': 'a configuration line holding a control or line-separator character',
    'PLAIN-SECRET-PATTERN': 'a line of a list file that showed a secret pattern',
    'PLAIN-CONTROL-CHARACTER': 'a line of a list file holding a control or line-separator character',
    'MARKER-COLLISION': 'a line that itself began with the collector\'s marker text',
    'HBA-TRAILING-BACKSLASH': 'a pg_hba rule ending in a backslash followed by blanks',
    'PLAIN-TRAILING-BACKSLASH': 'a line of a list file ending in a backslash followed by blanks',
}
# MARKER-CONTRACT-001, "Other withheld rows": reasons of sidecar rows that are not whole-line markers.
LINE_REASONS = frozenset({'COMMENT-WITHHELD', 'TRAILING-COMMENT-WITHHELD', 'CONF-VALUE-WITHHELD',
                          'HBA-OPTION-WITHHELD', 'JSON-VALUE-WITHHELD'})
SIDECAR = 'raw/COLLECTION-SIDECAR.json'
RF28, EARLIER = 'rf28', 'earlier'
_HEX = re.compile(r'[0-9a-f]{64}')

Marker = namedtuple('Marker', 'file line reason setting')


def physical_lines(data):
    """[(number, body)] per physical line: split at '\\n' only, a final empty piece dropped, exactly one trailing '\\r'
    removed as line ending; bytes decode as UTF-8 with surrogateescape (no byte is lost or guessed)."""
    parts = bytes(data).split(b'\n')
    if parts and not parts[-1]:
        parts.pop()
    out = []
    for n, part in enumerate(parts, 1):
        text = part.decode('utf-8', 'surrogateescape')
        out.append((n, text[:-1] if text.endswith('\r') else text))
    return out


def parse(body):
    """(line, reason, setting or None) for a line body that is exactly a marker with a known reason, else None."""
    m = MARKER_RE.fullmatch(body) if isinstance(body, str) else None
    if not m or m.group(2) not in MARKER_REASONS:
        return None
    return int(m.group(1)), m.group(2), m.group(3)


def starts_marker(body):
    """The line, after any whitespace, starts with the prefix. This is the checker's own test (derive_observed
    `line.lstrip().startswith`), which is wider than the collector's `_starts_marker` (spaces, tabs and carriage returns
    only): a line that begins with the prefix after other whitespace (a no-break space, a form feed) is read by the
    checker as a marker not in the contract form, so it is never left unrecorded here (refutation 008, G1)."""
    return body.lstrip().startswith(PREFIX)


def _after_other_break(body):
    """True when the checker, which splits at every `str.splitlines` boundary (lone '\\r', '\\x0b', '\\x0c', '\\x1c' to
    '\\x1e', U+0085, U+2028, U+2029), would read a line of this '\\n'-line that begins with the prefix after any
    whitespace (derive_observed `line.lstrip().startswith`), while this layer's line does not start there (refutation
    008, G1). The line's own ending ('\\r\\n') was removed by `physical_lines`."""
    return any(p.lstrip().startswith(PREFIX) for p in body.splitlines()[1:])


def _broken(name, number, kind, why):
    raise Refusal('bad_input', 'line %d of %s %s, so the collection is broken and cannot be read; collect again with '
                  'the collector and send its output as written; nothing was sent' % (number, name, why),
                  path=name, line=number, malformation=malformation(kind, file=name, line=number))


def scan(files):
    """[Marker] for every RF-28 marker line in the raw/ configuration files of `files`, sorted by file and line.
    `bad_input` (module docstring) for a marker-shaped line that is not a valid marker in its place."""
    out = []
    for name in sorted(n for n in files if isinstance(n, str) and n.startswith('raw/')):
        data = bytes(files[name])
        if PREFIX.encode('ascii') not in data:
            continue
        is_json = name.endswith('.json')
        for number, body in physical_lines(data):
            if _after_other_break(body):
                _broken(name, number, 'marker_in_json' if is_json else 'marker_grammar',
                        'holds the collector marker after a line break other than a newline, where the checker would '
                        'read a line this layer does not count')
            if not starts_marker(body):
                continue
            if is_json:
                _broken(name, number, 'marker_in_json', 'is a collector marker line inside a JSON file')
            m = MARKER_RE.fullmatch(body)
            if m is None:
                _broken(name, number, 'marker_grammar', 'begins like a collector marker but is not one exactly')
            if m.group(2) not in MARKER_REASONS:
                _broken(name, number, 'marker_reason', 'is a collector marker whose reason code is not in the '
                        'collector\'s closed list')
            if int(m.group(1)) != number:
                _broken(name, number, 'marker_line', 'is a collector marker that names another line number')
            out.append(Marker(name, number, m.group(2), m.group(3)))
    return out


def _sidecar(files):
    try:
        doc = json.loads(bytes(files[SIDECAR]))
    except (KeyError, ValueError, TypeError, UnicodeDecodeError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None


def generation(files):
    """'rf28', 'earlier', or None when the sidecar is absent or unreadable (module docstring)."""
    doc = _sidecar(files)
    if doc is None:
        return None
    return RF28 if isinstance(doc.get('connection'), dict) and isinstance(doc.get('session'), dict) else EARLIER


def rows_in_new_form(files):
    """True when every `redaction_withheld` row carries `line` (a positive integer, or null for a JSON file) and a
    `reason` from the closed lists; None when there is no readable list."""
    doc = _sidecar(files)
    rows = doc.get('redaction_withheld') if doc is not None else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or 'line' not in row or 'reason' not in row:
            return False
        line, reason = row['line'], row['reason']
        if not (line is None or (type(line) is int and line > 0)):
            return False
        if reason not in MARKER_REASONS and reason not in LINE_REASONS:
            return False
    return True


def collector(files):
    """The sidecar's `collector.tool_sha256` as its first 12 hex characters, or None: for the record only."""
    doc = _sidecar(files)
    tool = doc.get('collector') if doc is not None else None
    digest = tool.get('tool_sha256') if isinstance(tool, dict) else None
    return digest[:12] if isinstance(digest, str) and _HEX.fullmatch(digest) else None


def plain(reason):
    """The reason code in plain words."""
    return MARKER_REASONS.get(reason, 'a withheld line')


def not_observed(files):
    """[{file, line, reason, setting, text}] for every marker: the serving layer's record of the rules and settings that
    were withheld and so were not observed (`text` is the plain words of the reason)."""
    return [{'file': m.file, 'line': m.line, 'reason': m.reason, 'setting': m.setting, 'text': plain(m.reason)}
            for m in scan(files)]


def describe(item):
    """'not observed: raw/pg_hba.conf line 4 (a pg_hba rule ...)' for one `not_observed` item; the setting name, when the
    collector showed one, is named."""
    setting = item.get('setting')
    return 'not observed: %s line %s (%s%s)' % (item.get('file'), item.get('line'), item.get('text') or
                                               plain(item.get('reason')),
                                               '; setting %s' % setting if setting else '')

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
