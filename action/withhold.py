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
  applied unless every major the bundle states (raw/declaration.json `major`, raw/COLLECTION-SIDECAR.json
  `server.major`) is below 16.
- A file no include reaches has no known grammar: a line with no `#` and no quote is kept, a line that starts with `#`
  is a comment, and any other line is withheld whole.
- A line that cannot be classified safely (an unterminated quote) is replaced by the marker, never passed through raw.
- Kept as they are: a line that is only whitespace, a comment holding only `#` and whitespace, and the frozen
  collector's own fixed markers (`# <withheld comment>` and its withheld-line marker), which hold no customer text.

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

A JSON file the pass must read but cannot parse is `bad_input`: it could not be checked, so it is not sent.
"""
from __future__ import annotations

import json
import posixpath
import re

from serve.bundle import parse_json
from serve.outcomes import Refusal

WITHHELD_COMMENT = '# <withheld comment>'
LITERAL_MARK = "'<withheld literal %d>'"
# The frozen collector's fixed comment markers (collect_pg.py WITHHELD_COMMENT and REDACTED_LINE): no customer text.
COLLECTOR_MARKERS = frozenset({
    WITHHELD_COMMENT,
    '# [collect_pg: line withheld, an authentication secret pattern could not be stripped field by field]'})
SNAPSHOT = 'raw/catalog_snapshot.json'
DECLARATION = 'raw/declaration.json'
SIDECAR = 'raw/COLLECTION-SIDECAR.json'
POLICY_FIELDS = ('polqual', 'polwithcheck')
TOP = (('raw/postgresql.conf', 'conf'), ('raw/postgresql.auto.conf', 'conf'), ('raw/pg_hba.conf', 'hba'),
       ('raw/pg_ident.conf', 'ident'))
INCLUDES = ('include', 'include_if_exists', 'include_dir')
_CONF_KEY = re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)\s*(=\s*|\s+)(.*)$', re.S)
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


def _continues(body):
    return body.rstrip().endswith('\\')


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


def _withheld(prefix, cont):
    return prefix + WITHHELD_COMMENT + (' \\' if cont else '')


def _conf_lines(lines, counts):
    out = []
    for body, cr, nl in lines:
        try:
            at = _conf_comment(body)
        except _Unsafe:
            out.append((WITHHELD_COMMENT, cr, nl))
            counts['lines'] += 1
            continue
        if at is None or _blank_comment(body[at:]):
            out.append((body, cr, nl))
        else:
            out.append((body[:at] + WITHHELD_COMMENT, cr, nl))
            counts['comments'] += 1
    return out


def _groups(lines, cont):
    group = []
    for line in lines:
        group.append(line)
        if not (cont and _continues(line[0])):
            yield group
            group = []
    if group:
        yield group


def _hba_lines(lines, counts, cont):
    out = []
    for group in _groups(lines, cont):
        new, quoted, in_comment = [], False, False
        for k, (body, cr, nl) in enumerate(group):
            more = k < len(group) - 1
            if in_comment:                               # a continued comment: the whole line is comment text
                lead = body[:len(body) - len(body.lstrip())]
                new.append((_withheld(lead, more), cr, nl))
                counts['comments'] += 1
                continue
            at, quoted = _hba_comment(body, quoted)
            if at is None:
                new.append((body, cr, nl))
            elif _blank_comment(body[at:]) and not more:
                new.append((body, cr, nl))
            else:
                new.append((_withheld(body[:at], more), cr, nl))
                counts['comments'] += 1
                in_comment = more
        if quoted:                                       # an unterminated field: no line of the group is classified
            new = [(_withheld('', k < len(group) - 1), cr, nl) for k, (_, cr, nl) in enumerate(group)]
            counts['lines'] += len(group)
        out.extend(new)
    return out


def _unknown_lines(lines, counts):
    out, carry = [], False
    for body, cr, nl in lines:
        stripped = body.lstrip()
        more = _continues(body)
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


def withhold_config(data, grammar, *, continuation=True, counts=None):
    """One configuration file's bytes with its comment text withheld (module docstring). `grammar` is 'conf', 'hba',
    'ident', 'plain' or 'unknown'. Never raises on any input."""
    counts = counts if counts is not None else empty_counts()
    lines = _split(data)
    if grammar == 'conf':
        new = _conf_lines(lines, counts)
    elif grammar in ('hba', 'ident', 'plain'):
        new = _hba_lines(lines, counts, continuation)
    else:
        new = _unknown_lines(lines, counts)
    return _join(new)


# ---------- which grammar each file has ----------
def _conf_value(text):
    """derive.py conf_value: a quoted value up to its closing quote ('' and backslash escapes), else up to '#'."""
    text = text.strip()
    if text.startswith("'"):
        out, i = [], 1
        while i < len(text):
            c = text[i]
            if c == "'" and text[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            if c == '\\' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if c == "'":
                break
            out.append(c)
            i += 1
        return ''.join(out)
    return text.split('#', 1)[0].strip()


def _hba_tokens(line):
    """derive.py hba_tokens: whitespace-separated fields, '"' toggles quoting, '#' outside quotes ends the line."""
    tokens, current, quoted, started = [], '', False, False
    for c in line:
        if c == '"':
            quoted, started = not quoted, True
            continue
        if c == '#' and not quoted:
            break
        if c.isspace() and not quoted:
            if started:
                tokens.append(current)
            current, started = '', False
            continue
        current += c
        started = True
    if started:
        tokens.append(current)
    return tokens


def _text(data):
    return bytes(data).decode('utf-8', 'surrogateescape')


def _directives(grammar, text, cont):
    """[(kind, target)] for the include directives (and, in pg_hba.conf, the @file lists) of one file."""
    out = []
    if grammar == 'conf':
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            m = _CONF_KEY.match(s)
            if m and m.group(1).lower() in INCLUDES:
                out.append((m.group(1).lower(), _conf_value(m.group(3))))
        return out
    pending = ''
    for line in text.split('\n'):
        line = line.rstrip('\r')
        if cont and line.rstrip().endswith('\\'):
            pending += line.rstrip()[:-1] + ' '
            continue
        tokens, pending = _hba_tokens(pending + line), ''
        if not tokens:
            continue
        if tokens[0] in INCLUDES:
            out.append((tokens[0], tokens[1] if len(tokens) > 1 else ''))
        elif grammar == 'hba':
            for field in tokens[1:3]:
                out.extend(('@file', item[1:]) for item in field.split(',') if item.startswith('@') and len(item) > 1)
    return out


def _resolve(parent, target):
    """The raw/ name a relative target names from `parent` (a raw/ name), or None when it leaves raw/."""
    if not target or target.startswith('/'):
        return None
    rel = posixpath.normpath(posixpath.join(posixpath.dirname(parent[len('raw/'):]), target))
    if rel in ('.', '') or rel.startswith('../') or rel == '..' or rel.startswith('/'):
        return None
    return 'raw/' + rel


def grammars(files, cont=True):
    """{name: grammar} for every configuration file in `files`, following includes from the four top-level files the
    way derive.py and the frozen collector do. A file reached with two grammars, or by none, is 'unknown'."""
    seen, queue = {}, list(TOP)
    while queue:
        name, grammar = queue.pop(0)
        if name not in files:
            continue
        if name in seen:
            if seen[name] != grammar:
                seen[name] = 'unknown'
            continue
        seen[name] = grammar
        for kind, target in _directives(grammar, _text(files[name]), cont):
            child_grammar = 'plain' if kind == '@file' else grammar
            if kind == 'include_dir':
                folder = _resolve(name, target)
                if folder is None:
                    continue
                kids = sorted(n for n in files if posixpath.dirname(n) == folder and n.endswith('.conf')
                              and not posixpath.basename(n).startswith('.'))
                queue.extend((k, child_grammar) for k in kids)
                continue
            if grammar == 'conf' and target.startswith('/'):
                child = 'raw/' + posixpath.basename(target)       # derive.py maps an absolute include to raw/<base>
            else:
                child = _resolve(name, target)
            if child is not None:
                queue.append((child, child_grammar))
    out = {}
    for name in files:
        if name.startswith('raw/') and not name.endswith('.json'):
            out[name] = seen.get(name, 'unknown')
    return out


def _majors(files):
    found = []
    for name, path in ((DECLARATION, ('major',)), (SIDECAR, ('server', 'major'))):
        if name not in files:
            continue
        try:
            doc = json.loads(bytes(files[name]))
            for key in path:
                doc = doc[key]
        except (ValueError, KeyError, TypeError, IndexError, UnicodeDecodeError, RecursionError):
            continue
        if type(doc) is int:
            found.append(doc)
    return found


def continuation(files):
    """True unless every major the bundle states is below 16 (backslash continuation exists from major 16)."""
    majors = _majors(files)
    return not (majors and all(m < 16 for m in majors))


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


def _dump(doc):
    """The frozen collector's JSON style (collect_pg.py dump)."""
    return (json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


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
            out[SNAPSHOT] = _dump(doc)
    if DECLARATION in files:
        doc = _load(files, DECLARATION)
        if isinstance(doc, dict) and doc.get('declared_predicate') is not None:
            new = withhold_sql(doc['declared_predicate'], literals, counts)
            if new != doc['declared_predicate']:
                doc['declared_predicate'] = new
                out[DECLARATION] = _dump(doc)
    return out


# ---------- the pass ----------
def withhold_files(files):
    """(files with comment text and SQL literals withheld, counts). The input mapping is not changed."""
    counts = empty_counts()
    new = {name: bytes(data) for name, data in files.items()}
    cont = continuation(new)
    for name, grammar in sorted(grammars(new, cont).items()):
        new[name] = withhold_config(new[name], grammar, continuation=cont, counts=counts)
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
        extra.append(_n(c['lines'], 'configuration line', 'configuration lines') + ' that could not be parsed, '
                     'withheld whole')
    if extra:
        text += ' Also: %s.' % '; '.join(extra)
    return text


def summary_markdown(counts):
    return '\n### Withheld in the runner\n\n%s\n' % describe(counts)

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
