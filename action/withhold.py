"""Withhold free text before anything leaves the runner (refutation 002, TC-1 and TC-2). Standard library only; imports
no engine byte, so the public Action tree ships it.

`withhold_files(files)` takes the bundle `{raw/... name: bytes}` the Action read (from the frozen collector's output, or
from an `artefacts` directory the customer made) and returns `(new files, counts)`. The customer's directory is never
changed: the pass works on the bytes in memory, after they are read and before any check, request body or upload.

Configuration files (every name under raw/ that does not end in .json):
- The text of every comment, whole-line or trailing, is replaced with exactly `# <withheld comment>`. A commented-out
  setting (`#shared_buffers = 128MB`) is a comment and is withheld too. Every line, every line ending (`\\r` runs
  included) and every byte of non-comment text is kept; the line count never changes.
- postgresql.conf grammar (postgresql.conf, postgresql.auto.conf and the files their include, include_if_exists and
  include_dir directives reach): `#` outside a single-quoted value starts a comment; inside a value `''` and a backslash
  escape the next character (guc-file.l STRING).
- pg_hba.conf grammar (pg_hba.conf, pg_ident.conf, their includes and the `@file` lists pg_hba.conf names): `#` outside
  a double-quoted field starts a comment. From major 16 a line whose text ends in a backslash continues on the next line
  (derive.py and hba.c read the joined line), so a comment carries on through the continued lines: each of them is
  withheld, and a withheld line that continued keeps a closing ` \\` so the grouping is unchanged. Continuation is
  read as derive.py reads it (below); a line that two or more carriage returns end does not continue (PostgreSQL strips
  one, derive.py splits at each).
- A file no include reaches has no known grammar: a line with no `#` and no quote is kept, a line that starts with `#`
  is a comment, and any other line is withheld whole. Includes are resolved as derive.py resolves them
  (serve/faithful.py), so a path that leaves raw/ and comes back in through `raw` is followed (refutation 004, WH-3);
  a file whose grammar is still unknown is held to both grammars' readings (below).
- A line that cannot be classified safely (an unterminated quote) is replaced by `<withheld: a line PostgreSQL cannot
  parse>`, never passed through raw. The marker is not a comment and holds no quote: the checker's derive step reads it
  as it read the bad line, an unparseable postgresql.conf line (a note) or a malformed pg_hba.conf record (an error row
  that HBA-6 counts). A continued group keeps its grouping (` \\` on every line but the last).
- Text after a character derive.py splits lines at but PostgreSQL does not (CR, VT, FF, FS, GS, RS, NEL, LS, PS) inside a
  comment is comment text: each such character is kept, and the text between them is withheld as `# <withheld comment>`
  (only whitespace is kept as written), so derive.py numbers the lines as before.
- Kept as they are: a line that is only whitespace, a comment holding only `#` and whitespace, and the frozen
  collector's own fixed markers (`# <withheld comment>` and its withheld-line marker), which hold no customer text.

What the checker reads never changes (refutation 003, WH-1). For every file derive.py reads (postgresql.conf grammar
and pg_hba.conf grammar, includes followed) the pass computes derive.py's own reading of the file before and after
(`conf_reading`, `hba_reading`: the same line splitting, regular expression, value and token rules) and refuses the upload
as `bad_input`, naming the file and line and never the line's text, when they differ. That is the case for a line
PostgreSQL cannot parse that derive.py reads as a setting or a rule (no marker can carry a value without its text), for a
comment whose text after a line-break character derive.py would read as a setting or a rule, for a file both
grammars reach whose lines cannot be withheld one way for both, and for a file of unknown grammar whose withholding
would change either grammar's reading. Continuation follows raw/declaration.json `major`, the
one source derive.py reads (refutation 003, B1).

The frozen collector's whole-line marker (refutation 003, B6; refutation 004, WH-2). collect_pg.py writes
`# [collect_pg: line withheld, ...]` in place of a whole line it cannot keep, and the checker skips it as a comment. In
pg_hba.conf that line can be a rule (an unterminated quote, a quoted or @file positional field, a regular-expression
user, a secret pattern left, a control character, a continued rule); in postgresql.conf a setting; but most often it is
a stock comment. No marker can stand for a rule or setting the check cannot see without changing what it reads (absent
reads better, malformed reads falsely worse), so before anything else the pass runs the server's own check,
`serve.faithful.check` (with `as_collected=True`: these are the collector's bytes), which fails closed: an upload whose
pg_hba.conf-grammar or postgresql.conf-grammar file holds a marker line is refused as `collector_refused` (exit 3) unless
raw/COLLECTION-SIDECAR.json is present and readable, has rows for that file, every row says a comment was withheld
whole, there are at least as many such rows as marker lines, and the server reports no setting from a marker line.
The refusal names the file, the candidate lines and the collector's reason, never a line's text. The upload takes the
sidecar from beside raw/, where the collector writes it (serve/bundle.py `from_directory`). One postgresql.conf case
stays open (serve/faithful.py, DATA.md): a setting outside the collector's fixed list withheld for a control character
or secret pattern, with no pg_file_settings row naming its line, still reads as absent.

SQL expressions (raw/catalog_snapshot.json `policies[].polqual` and `policies[].polwithcheck`, and
raw/declaration.json `declared_predicate`, the one expression the declared profile compares them with): every quoted
string literal (standard `'...'` with `''`, `E'...'` with backslash escapes, `U&'...'`, `B'...'`, `X'...'`, `N'...'`
and dollar-quoted `$tag$...$tag$`) is replaced by `'<withheld literal N>'`. Double-quoted identifiers are kept. N numbers
the distinct literals of one upload in order of first sight, compared as derive.py compares expressions (whitespace runs
collapsed, lower case), so an expression equals the declared predicate after the pass exactly when it did before
(derive.py build_m5 `term`); N says only that two literals of one upload were equal, never what they held. An
expression that cannot be tokenised safely (an unterminated quote or identifier, or an SQL comment) is withheld whole as
one marker; a policy expression that is present but not a string is withheld whole too. The JSON is re-serialised in
the collector's own style (sorted keys, two-space indent, UTF-8, final newline) only when something was withheld;
otherwise its bytes are untouched.

A JSON file the pass must read but cannot parse, or must re-serialise but that holds a string that is not valid
Unicode (a lone surrogate escape), is `bad_input`: it could not be checked, so it is not sent.
"""
from __future__ import annotations

import json
import re

from serve.bundle import parse_json
from serve.faithful import (DECLARATION, HBA_TYPES, INCLUDES, REDACTED_LINE, SIDECAR, SNAPSHOT, TOP,  # noqa: F401
                            WITHHELD_VALUE, _conf_value, _derive_lines, _directives, _hba_logical, _hba_tokens, _reach,
                            _resolve, conf_reading, continuation, grammars, setting_locations)
from serve import faithful
from serve.outcomes import Refusal

WITHHELD_COMMENT = '# <withheld comment>'
UNPARSEABLE_MARK = '<withheld: a line PostgreSQL cannot parse>'
LITERAL_MARK = "'<withheld literal %d>'"
# The frozen collector's fixed comment markers (collect_pg.py WITHHELD_COMMENT and REDACTED_LINE): no customer text.
COLLECTOR_MARKERS = frozenset({WITHHELD_COMMENT, REDACTED_LINE})
POLICY_FIELDS = ('polqual', 'polwithcheck')
_BREAK = re.compile('([\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029])')        # str.splitlines boundaries other than \n
_DOLLAR = re.compile(r'\$(?:[^\W\d][\w]*)?\$')
_WS = re.compile(r'\s+')
COUNT_KEYS = ('comments', 'lines', 'literals', 'expressions')


class _Unsafe(Exception):
    """An SQL expression that cannot be tokenised safely."""


def empty_counts():
    return {k: 0 for k in COUNT_KEYS}


# ---------- lines ----------
def _split(data):
    """[(body, cr, newline)] with body the line without its '\\n' and trailing '\\r' run; bytes decode as UTF-8 with
    surrogateescape, so encoding the pieces back gives the same bytes."""
    parts = bytes(data).split(b'\n')
    out = []
    for n, part in enumerate(parts):
        last = n == len(parts) - 1
        if last and not part:
            break
        text = part.decode('utf-8', 'surrogateescape')
        body = text.rstrip('\r')
        out.append((body, text[len(body):], not last))
    return out


def _join(lines):
    return ''.join(b + cr + ('\n' if nl else '') for b, cr, nl in lines).encode('utf-8', 'surrogateescape')


def _continues(body, cr=''):
    """A line ending in a backslash continues (pg_hba.conf grammar, major 16 and later), unless two or more carriage
    returns end it: PostgreSQL strips one, and derive.py splits at each, so neither joins it to the next line."""
    return len(cr) <= 1 and body.rstrip().endswith('\\')


def _blank_comment(text):
    """A comment that holds nothing (only '#' and whitespace) or only a collector marker is kept as written."""
    return text.rstrip() == '#' or text.strip() == '#' or text in COLLECTOR_MARKERS


def _conf_comment(body):
    """The index of the comment's '#' in a postgresql.conf line, None for no comment; _Unsafe for an unterminated
    single-quoted value."""
    i, n, quoted = 0, len(body), False
    while i < n:
        c = body[i]
        if quoted:
            if c == '\\':
                i += 2
                continue
            if c == "'":
                if body[i + 1:i + 2] == "'":
                    i += 2
                    continue
                quoted = False
        elif c == "'":
            quoted = True
        elif c == '#':
            return i
        i += 1
    if quoted:
        raise _Unsafe('unterminated value')
    return None


def _hba_comment(body, quoted):
    """(index of the comment's '#' or None, quote state at the end) for one pg_hba.conf-grammar line."""
    for i, c in enumerate(body):
        if c == '"':
            quoted = not quoted
        elif c == '#' and not quoted:
            return i, False
    return None, quoted


def _comment_text(text):
    """The replacement for comment text (from its '#', or a whole continued line): `# <withheld comment>`, then for each
    character derive.py splits lines at (module docstring) that character and, for the text after it, the same marker
    (whitespace alone is kept), so derive.py's line numbering is unchanged."""
    parts = _BREAK.split(text)
    out = [WITHHELD_COMMENT]
    for k in range(1, len(parts), 2):
        seg = parts[k + 1]
        out.append(parts[k] + (seg if not seg.strip() else WITHHELD_COMMENT))
    return ''.join(out)


def _marked(text, first=UNPARSEABLE_MARK):
    """The replacement for a line that cannot be classified: the marker, then each character derive.py splits lines at,
    each followed by the marker again (whitespace alone is kept), so derive.py numbers the lines as before."""
    parts = _BREAK.split(text)
    out = [first]
    for k in range(1, len(parts), 2):
        seg = parts[k + 1]
        out.append(parts[k] + (seg if not seg.strip() else UNPARSEABLE_MARK))
    return ''.join(out)


def _withheld(prefix, cont, text=''):
    return prefix + _comment_text(text) + (' \\' if cont else '')


def _conf_lines(lines, counts, marked):
    out = []
    for n, (body, cr, nl) in enumerate(lines):
        try:
            at = _conf_comment(body)
        except _Unsafe:
            out.append((_marked(body), cr, nl))
            counts['lines'] += 1
            marked.add(n)
            continue
        if at is None or _blank_comment(body[at:]):
            out.append((body, cr, nl))
        else:
            out.append((_withheld(body[:at], False, body[at:]), cr, nl))
            counts['comments'] += 1
    return out


def _groups(lines, cont):
    group = []
    for line in lines:
        group.append(line)
        if not (cont and _continues(line[0], line[1])):
            yield group
            group = []
    if group:
        yield group


def _hba_lines(lines, counts, cont, marked):
    out = []
    for group in _groups(lines, cont):
        new, quoted, in_comment = [], False, False
        for k, (body, cr, nl) in enumerate(group):
            more = k < len(group) - 1 or (cont and _continues(body, cr))   # a last line may continue into nothing
            if in_comment:                               # a continued comment: the whole line is comment text
                lead = body[:len(body) - len(body.lstrip())]
                new.append((_withheld(lead, more, body[len(lead):]), cr, nl))
                counts['comments'] += 1
                continue
            at, quoted = _hba_comment(body, quoted)
            if at is None:
                new.append((body, cr, nl))
            elif _blank_comment(body[at:]) and not more:
                new.append((body, cr, nl))
            else:
                new.append((_withheld(body[:at], more, body[at:]), cr, nl))
                counts['comments'] += 1
                in_comment = more
        if quoted:                                       # an unterminated field: the group becomes one marked record
            new = [(_marked(body, UNPARSEABLE_MARK if k == 0 else '')
                    + (' \\' if k < len(group) - 1 or (cont and _continues(body, cr)) else ''), cr, nl)
                   for k, (body, cr, nl) in enumerate(group)]
            counts['lines'] += 1
            marked.update(range(len(out), len(out) + len(group)))
        out.extend(new)
    return out


def _unknown_lines(lines, counts):
    out, carry = [], False
    for body, cr, nl in lines:
        stripped = body.lstrip()
        more = _continues(body, cr)
        if carry:
            out.append((_withheld('', more), cr, nl))
            counts['comments'] += 1
        elif not any(c in body for c in '#\'"'):
            out.append((body, cr, nl))
        elif stripped.startswith('#'):
            if _blank_comment(stripped) and not more:
                out.append((body, cr, nl))
            else:
                out.append((_withheld(body[:len(body) - len(stripped)], more), cr, nl))
                counts['comments'] += 1
        else:
            out.append((_withheld('', more), cr, nl))
            counts['lines'] += 1
        carry = (carry or stripped.startswith('#') or (any(c in body for c in '#\'"'))) and more
    return out


def withhold_config(data, grammar, *, continuation=True, counts=None, marked=None):
    """One configuration file's bytes with its comment text withheld (module docstring). `grammar` is 'conf', 'hba',
    'ident', 'plain' or 'unknown'. `marked`, when given, receives the 0-based numbers of the lines replaced by the
    unparseable-line marker. Never raises on any input; whether derive.py reads the result as it read the input is
    checked by `withhold_files`."""
    counts = counts if counts is not None else empty_counts()
    marked = marked if marked is not None else set()
    lines = _split(data)
    if grammar == 'conf':
        new = _conf_lines(lines, counts, marked)
    elif grammar in ('hba', 'ident', 'plain'):
        new = _hba_lines(lines, counts, continuation, marked)
    else:
        new = _unknown_lines(lines, counts)
    return _join(new)


# ---------- what derive.py reads from one file ----------
def hba_reading(data, cont):
    """derive.py parse_hba's reading of one file: [(start line, tokens)] per logical line that has tokens, with the
    tokens of a line derive.py counts as a malformed record replaced by ('<malformed record>',): derive.py keeps only
    the error `<file>:<start> malformed record` from such a line, so any two such lines read the same."""
    out = []
    for start, tokens in _hba_logical(data, cont):
        kind = tokens[0]
        if kind not in INCLUDES and (kind not in HBA_TYPES or len(tokens) < (4 if kind == 'local' else 5)):
            tokens = ['<malformed record>']
        out.append((start, tuple(tokens)))
    return out


def _passline_of(data, number):
    """The 1-based physical line (PostgreSQL's numbering, lines end at '\\n') that holds derive.py's line `number`."""
    seen = 0
    for n, (body, cr, nl) in enumerate(_split(data), 1):
        seen += len((body + cr + ('\n' if nl else '')).splitlines()) or 1
        if seen >= number:
            return n
    return max(1, len(_split(data)))


def _first_difference(a, b):
    for x, y in zip(a, b):
        if x != y:
            return min(x[0], y[0])
    rest = a[len(b):] or b[len(a):]
    return rest[0][0]


def _check_reading(name, grammars_reached, before, after, cont, marked, unknown=False):
    """`bad_input` when derive.py would read `after` differently from `before` in any grammar that reaches the file.
    `unknown`: no include reaches the file by a path the pass can follow (refutation 004, WH-3), so both grammars'
    readings are held."""
    both = len(grammars_reached & {'conf', 'hba'}) > 1
    for grammar in sorted({'conf', 'hba'} if unknown else grammars_reached & {'conf', 'hba'}):
        if grammar == 'conf':
            a, b = conf_reading(before), conf_reading(after)
        else:
            a, b = hba_reading(before, cont), hba_reading(after, cont)
        if a == b:
            continue
        line = _passline_of(before, _first_difference(a, b))
        near = ''.join(b for b, _, _ in _split(before)[max(0, line - 2):line])
        if line - 1 in marked:
            why = ('is a line PostgreSQL cannot parse (an unclosed quote), and the check would read it as a setting or '
                   'a rule. Fix that line, then run again')
        elif both:
            why = ('belongs to a file that both postgresql.conf and pg_hba.conf include, and its comment cannot be '
                   'withheld so that both read it as before. Include the file from one of them only, then run again')
        elif unknown:
            why = ('belongs to a file no include in postgresql.conf or pg_hba.conf reaches by a path the check can '
                   'follow, so its grammar is not known, and its text cannot be withheld without changing what the '
                   'check could read from it. Include the file by a plain relative path, or leave it out of the '
                   'upload, then run again')
        elif _BREAK.search(near):
            why = ('holds a comment with a carriage return, vertical tab, form feed or Unicode line separator in it; '
                   'the check would read the text after that character as a separate line, so the comment cannot be '
                   'withheld without changing what the check reads. Remove that character, then run again')
        else:
            why = ('cannot have its comment withheld without changing what the check reads from the file. Check the '
                   'line, then run again')
        raise Refusal('bad_input', 'line %d of %s %s; nothing was sent' % (line, name, why), path=name, line=line)


# ---------- SQL expressions ----------
def _identish(c):
    return c.isalnum() or c in '_$'


def _sql_pieces(text):
    """[(is_literal, text)] for an SQL expression; _Unsafe when it cannot be tokenised safely."""
    pieces, i, seg, n = [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':                                      # a quoted identifier: kept, but skipped as a unit
            j = i + 1
            while True:
                k = text.find('"', j)
                if k < 0:
                    raise _Unsafe('unterminated identifier')
                if text[k + 1:k + 2] == '"':
                    j = k + 2
                    continue
                break
            i = k + 1
            continue
        if text.startswith('--', i) or text.startswith('/*', i):
            raise _Unsafe('comment')
        if c == "'":
            start, escapes = i, False
            if i >= 1 and text[i - 1] in 'eEbBxXnN' and (i < 2 or not _identish(text[i - 2])):
                start, escapes = i - 1, text[i - 1] in 'eE'
            elif i >= 2 and text[i - 2:i] in ('U&', 'u&') and (i < 3 or not _identish(text[i - 3])):
                start = i - 2
            j = i + 1
            while True:
                if j >= n:
                    raise _Unsafe('unterminated literal')
                ch = text[j]
                if escapes and ch == '\\':
                    j += 2
                    continue
                if ch == "'":
                    if text[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            if start > seg:
                pieces.append((False, text[seg:start]))
            pieces.append((True, text[start:j + 1]))
            i = seg = j + 1
            continue
        if c == '$' and (i == 0 or not _identish(text[i - 1])):
            m = _DOLLAR.match(text, i)
            if m:
                tag = m.group(0)
                k = text.find(tag, m.end())
                if k < 0:
                    raise _Unsafe('unterminated dollar quote')
                if i > seg:
                    pieces.append((False, text[seg:i]))
                pieces.append((True, text[i:k + len(tag)]))
                i = seg = k + len(tag)
                continue
        i += 1
    if seg < n:
        pieces.append((False, text[seg:]))
    return pieces


def _norm_sql(text):
    """derive.py norm_sql."""
    return _WS.sub(' ', str(text).strip().strip('()')).strip().lower()


class Literals:
    """The numbering of one upload's withheld literals and expressions (module docstring)."""

    def __init__(self):
        self.numbers = {}

    def mark(self, key):
        if key not in self.numbers:
            self.numbers[key] = len(self.numbers) + 1
        return LITERAL_MARK % self.numbers[key]


def withhold_sql(text, literals, counts):
    """An SQL expression with every string literal withheld; the whole expression as one marker when it cannot be
    tokenised safely. Never raises."""
    if not isinstance(text, str):
        counts['expressions'] += 1
        return literals.mark('value:' + json.dumps(text, sort_keys=True, default=repr))
    try:
        pieces = _sql_pieces(text)
    except _Unsafe:
        counts['expressions'] += 1
        return literals.mark('expr:' + _norm_sql(text))
    out = []
    for is_literal, piece in pieces:
        if is_literal:
            counts['literals'] += 1
            out.append(literals.mark('lit:' + _WS.sub(' ', piece).lower()))
        else:
            out.append(piece)
    return ''.join(out)


def _dump(doc, name):
    """The frozen collector's JSON style (collect_pg.py dump); `bad_input` for a string that is not valid Unicode (a
    lone surrogate escape), which cannot be written back (refutation 003, B3)."""
    try:
        return (json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    except UnicodeEncodeError:
        raise Refusal('bad_input', '%s holds a string that is not valid Unicode (a lone surrogate escape), so its SQL '
                      'expressions could not be written back with their literals withheld; nothing was sent' % name,
                      path=name) from None


def _load(files, name):
    try:
        return parse_json(bytes(files[name]))
    except Refusal:
        raise Refusal('bad_input', '%s is not valid JSON, so its SQL expressions could not be checked for string '
                      'literals; nothing was sent' % name, path=name) from None


def _withhold_json(files, literals, counts):
    out = {}
    if SNAPSHOT in files:
        doc, changed = _load(files, SNAPSHOT), False
        rows = doc.get('policies') if isinstance(doc, dict) else None
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                continue
            for key in POLICY_FIELDS:
                if row.get(key) is not None:
                    new = withhold_sql(row[key], literals, counts)
                    if new != row[key]:
                        row[key], changed = new, True
        if changed:
            out[SNAPSHOT] = _dump(doc, SNAPSHOT)
    if DECLARATION in files:
        doc = _load(files, DECLARATION)
        if isinstance(doc, dict) and doc.get('declared_predicate') is not None:
            new = withhold_sql(doc['declared_predicate'], literals, counts)
            if new != doc['declared_predicate']:
                doc['declared_predicate'] = new
                out[DECLARATION] = _dump(doc, DECLARATION)
    return out


# ---------- the pass ----------
def withhold_files(files):
    """(files with comment text and SQL literals withheld, counts). The input mapping is not changed. `bad_input` when
    derive.py would read any configuration file differently after the pass, and `collector_refused` when a line the
    frozen collector withheld whole may hide a rule or setting (serve/faithful.py `check`, the server's own check, run
    here on the collector's bytes before anything else; module docstring)."""
    counts = empty_counts()
    new = {name: bytes(data) for name, data in files.items()}
    faithful.check(new, as_collected=True)
    cont = continuation(new)
    reach = _reach(new, cont)
    for name, grammar in sorted(grammars(new, cont).items()):
        reached = reach.get(name, set())
        base = new[name]
        marked = set()
        out = withhold_config(base, grammar, continuation=cont, counts=counts, marked=marked)
        _check_reading(name, reached, base, out, cont, marked, unknown=grammar == 'unknown')
        new[name] = out
    new.update(_withhold_json(new, Literals(), counts))
    return new, counts


def apply(collected):
    """Withhold in a `bundle.Collected` in place; returns it with `withheld` set to the counts."""
    collected.files, collected.withheld = withhold_files(collected.files)
    return collected


def _n(count, one, many):
    return '%d %s' % (count, one if count == 1 else many)


def describe(counts):
    """One plain sentence, counts only."""
    c = dict(empty_counts(), **(counts or {}))
    text = ('Withheld in the runner before anything was sent: %s and %s.'
            % (_n(c['comments'], 'configuration comment', 'configuration comments'),
               _n(c['literals'], 'string literal in SQL expressions', 'string literals in SQL expressions')))
    extra = []
    if c['expressions']:
        extra.append(_n(c['expressions'], 'SQL expression', 'SQL expressions') + ' withheld whole')
    if c['lines']:
        extra.append(_n(c['lines'], 'configuration line', 'configuration lines') + ' PostgreSQL cannot parse, kept '
                     'as a marked unparseable line')
    if extra:
        text += ' Also: %s.' % '; '.join(extra)
    return text


def summary_markdown(counts):
    return '\n### Withheld in the runner\n\n%s\n' % describe(counts)

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
