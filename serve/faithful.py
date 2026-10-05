"""The check reads the customer's own file, or nothing (refutation 004, WH-2 and WH-3). Standard library only; imports
no engine byte and holds no checker logic, so the public Action tree ships it and the server runs it before admission.

Three things live here, shared by the Action (action/withhold.py) and the hosted API (serve/api.py, serve/worker.py):

1. Which files the checker's derive step reads, and with which grammar. `conf_reading` and `_hba_logical` read a file
   the way the frozen derive step does (str.splitlines after a UTF-8 decode with replacement; its setting regular
   expression and value rule; its token rule), only far enough to find include directives. `grammars(files)` follows
   include, include_if_exists and include_dir from postgresql.conf, postgresql.auto.conf, pg_hba.conf and pg_ident.conf,
   and resolves every target the way derive does (WH-3): join it to the including file's directory, normalise, and
   accept any path that lies under raw/, including one that leaves raw/ and comes back in through the directory name
   `raw` (derive's work layout). An absolute postgresql.conf include names raw/<basename>; any other absolute target, or
   a relative one that leaves raw/ for good, is not followed. A file no include reaches, or reached with two grammars,
   is `unknown`.

2. Continuation: a pg_hba.conf-grammar line ending in a backslash continues from PostgreSQL 16. The major comes from up
   to three sources: raw/declaration.json `major` (the declared checker's derive reads it), and raw/COLLECTION-SIDECAR.json
   `server.major` and `server.server_version_num` (the intent-free checker's derive reads the version number). When the
   sources that are present disagree about which side of 16 the server is on, and any pg_hba.conf-grammar file (or a
   file of unknown grammar) has a line ending in a backslash, the upload is refused as `bad_input` naming the file, the
   line and two sources that disagree: the two checkers would join that line differently, and nothing is guessed.
   Otherwise the first present source decides (declaration, then server.major, then server_version_num); with none, the
   line continues (which withholds more).

3. `check(files)`: the frozen collector writes one whole-line marker, `# [collect_pg: line withheld, ...]`, in place of
   a line it cannot keep. It begins with `#`, so derive reads it as a comment: a rule or setting behind it would read
   as absent. The collector's record of why is raw/COLLECTION-SIDECAR.json `redaction_withheld` (file, reason label,
   count; never a line number or text). For every file derive reads with pg_hba.conf grammar or postgresql.conf grammar
   (and every file of unknown grammar, held to both), when the file holds any marker line, the upload is refused as
   `collector_refused` (exit 3; HTTP 422) when:
   (i)   the sidecar is absent, unreadable, has no `redaction_withheld` list, or has no row for that file;
   (ii)  the file has more marker lines than rows that say a comment was withheld whole (pg_hba.conf grammar:
         `line:comment:withheld_whole`; postgresql.conf grammar: `line:comment:withheld_whole`,
         `line:line:withheld_whole` and `#<name>:<name>:withheld_whole` for a commented-out setting, less the
         commented-out lines that keep that setting with a withheld value);
   (iii) a row gives a pg_hba.conf-grammar file any whole-line reason other than a withheld comment (a quoted or @file
         name, a regular-expression user, an unclosed quote, a secret pattern, a control character, a continued rule),
         or gives a postgresql.conf-grammar file more `<name>:<name>:withheld_whole` rows for a setting than lines that
         keep that setting with a withheld value;
   (iv)  the server says a setting came from a marker line (raw/pg_settings.json sourcefile/sourceline for the
         collector's fixed setting list; raw/catalog_snapshot.json `pg_file_settings` when the role may read it).
   The reason names the file and line numbers and the collector's reason labels, never a line's text.

   `as_collected=True` (the Action, before its own withholding pass) also discounts, from the pg_hba.conf comment rows,
   the kept rules whose trailing comment the collector withheld in place: there the collector's bytes are known, so a
   row for a withheld rule cannot be made up for by those. After the Action's pass a customer's own trailing comment
   reads the same, so the server (`as_collected=False`) counts every comment row.

   One case stays open (DATA.md): a setting withheld whole for a control character or a secret pattern carries
   `line:line:withheld_whole`, the reason the collector also gives a prose comment; without a pg_settings or
   pg_file_settings row naming its line (for example a fixed-list setting such as `ssl` on a line changed since the last
   reload, or any setting outside the collector's fixed list when pg_file_settings is not readable), it reads as absent.

4. `check_binding(files, manifest)` (refutation 005, WH-4): the sidecar accounts for marker lines by count only, so a
   sidecar from another run could count a withheld rule as a comment. The frozen collector
   writes REDACTION-MANIFEST.json beside raw/ in the same run as the sidecar: its `entries` ({file, field, count}; the
   sidecar's `redaction_withheld` is the subset whose label holds `withheld` or `unparsed`) and `sanitised_sha256`, the
   digest of every raw/ file as it wrote it. For every file `check` holds (a pg_hba.conf-grammar, postgresql.conf-grammar
   or unknown-grammar file with at least one marker line), `collector_refused` unless the manifest is present and
   readable, its digest for the file equals the sha256 of the file's bytes as collected, and (when the sidecar is
   readable; `check` refuses when it is not) its rows for the file equal the sidecar's rows for the file, label by label
   and count by count. A file with no marker needs no manifest. The reason names the file, its marker lines and what
   did not match, never a line's text, and shows a digest only as its first 12 hex characters.
   Only the runner can run it: the bytes must be the collector's own, before the Action withholds comments. The Action
   (action/withhold.py `apply`, api and local mode, a connection or an `artefacts` directory) and the local command
   (serve/check.py) run it; the manifest stays in the runner and is never uploaded. The API and the worker cannot (the
   bytes they receive from the Action have their comments withheld) and run `check` alone: a direct API caller is
   responsible for sending the collector's own output from one run (docs/customer/DATA.md, QUICKSTART-API.md).
   The binding has a limit (refutation 006, G-1): records from another run are caught only when a file that holds a
   withheld line differs, byte for byte, from that run's file. Records kept from an earlier run of the same server pass
   if the withheld lines sit at the same places with the same marker, even where a line that was a comment is now a
   rule: the frozen collector writes REDACTED_LINE for both, so the bytes and their digest are identical, and the earlier
   records, which agree with each other, read the line as a withheld comment.
   No binding over these bytes can close this for the earlier collector; the customer must use the sidecar and
   manifest written by the same collector run as raw/. It is closed for the RF-28 collector, whose marker for a withheld
   rule or setting is not a comment and names its own line and reason (item 5; tests/serving/test_faithful.py
   KnownGapSameServerEarlierRecords keeps the earlier form's assertion and inverts it for the RF-28 form).

5. Two collector generations, side by side (coordination heading 1620; MARKER-CONTRACT-001, accepted). The RF-28
   collector writes a withheld rule, setting or other parsed line as `!collect_pg-withheld line <N> reason <CODE>[
   setting <name>]` (serve/markers.py recognises it exactly), and never writes the comment marker of items 3 and 4.
   Which collector wrote the upload comes from the sidecar (serve/markers.py `generation`: the RF-28 sidecar carries
   `connection` and `session`, and its rows carry `line` and `reason`). `check_generation`, run first by `check` and
   `check_binding`: a broken RF-28 marker (a line number that is not its own, a reason outside the closed list, a line
   that begins like a marker but is not one, a marker after a line break the checker counts and this layer does not,
   a marker in a JSON file) is `bad_input` naming the file and line; an upload
   that mixes the generations (both marker forms, the comment marker with an RF-28 sidecar, an RF-28 marker with an
   earlier sidecar, an RF-28 sidecar whose rows lack line and reason) is `collector_refused`. For an RF-28 collection
   the rules of items 3 and 4 still run but hold no file, so none fires: the marker identifies itself and reads as not
   observed. For an earlier collection everything above is unchanged. An RF-28 upload without a sidecar is not refused
   for its markers: each says what it withheld.

Every `bad_input` and `collector_refused` raised here carries `detail.malformation` (serve/outcomes.py): a closed kind,
the file, the line and the expected form, never a line's text.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re

from . import markers
from .outcomes import Refusal, malformation

# The frozen collector's fixed markers (collect_pg.py REDACTED_LINE, WITHHELD_COMMENT, WITHHELD_VALUE): no customer text.
REDACTED_LINE = '# [collect_pg: line withheld, an authentication secret pattern could not be stripped field by field]'
WITHHELD_COMMENT = '# <withheld comment>'
WITHHELD_VALUE = "'<withheld: structured value>'"
SNAPSHOT = 'raw/catalog_snapshot.json'
DECLARATION = 'raw/declaration.json'
SIDECAR = 'raw/COLLECTION-SIDECAR.json'
TIMING = 'raw/TIMING.json'
# The frozen collector's redaction manifest, written beside raw/ in the same run as the sidecar. A runner-only record:
# serve/bundle.py `from_directory` keeps it out of the upload (Collected.records).
MANIFEST = 'REDACTION-MANIFEST.json'
TOP = (('raw/postgresql.conf', 'conf'), ('raw/postgresql.auto.conf', 'conf'), ('raw/pg_hba.conf', 'hba'),
       ('raw/pg_ident.conf', 'ident'))
INCLUDES = ('include', 'include_if_exists', 'include_dir')
HBA_TYPES = ('local', 'host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
_DERIVE_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*(=\s*|\s+)(.*)$")      # derive.py parse_conf, exactly
_LABEL_KEY = re.compile(r'(#?)([a-z_][a-z0-9_.]*):([a-z_][a-z0-9_.]*):withheld_whole')
_COMMENTED_VALUE = re.compile(r"\s*#\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(?:=\s*|\s+)" + re.escape(WITHHELD_VALUE))
_HBA_COMMENT = 'line:comment:withheld_whole'
_CONF_COMMENT = ('line:comment:withheld_whole', 'line:line:withheld_whole')
# derive's work directory, as a path no target can name: a target that leaves raw/ and re-enters it through `raw`
# resolves under it, as derive's own resolve() does; one that climbs past it names a directory nobody can predict.
_WORK_RAW = '/\x00work/raw'


# ---------- what derive reads from one file, as far as includes go ----------
def _derive_lines(data):
    """derive.py's lines: read_text(encoding='utf-8', errors='replace').splitlines()."""
    return bytes(data).decode('utf-8', 'replace').splitlines()


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


def conf_reading(data):
    """derive.py parse_conf's reading of one file, line by line: [(line, key, value)] for a setting or include
    directive and [(line, None)] for a line it notes as unparseable (blank and '#' lines are skipped)."""
    out = []
    for number, line in enumerate(_derive_lines(data), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = _DERIVE_KEY.match(stripped)
        out.append((number, match.group(1).lower(), _conf_value(match.group(3))) if match else (number, None))
    return out


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


def _hba_logical(data, cont):
    """derive.py parse_hba's logical lines: (start line, tokens) for each line that has tokens."""
    pending, start = '', 0
    for number, line in enumerate(_derive_lines(data), 1):
        if not pending:
            start = number
        if cont and line.rstrip().endswith('\\'):
            pending += line.rstrip()[:-1] + ' '
            continue
        text, pending = pending + line, ''
        tokens = _hba_tokens(text)
        if tokens:
            yield start, tokens


def _directives(grammar, data, cont):
    """[(kind, target)] for the include directives (and, in pg_hba.conf, the @file lists) of one file, read with
    derive.py's own line splitting and rules (conf_reading, _hba_logical)."""
    if grammar == 'conf':
        return [(item[1], item[2]) for item in conf_reading(data) if len(item) == 3 and item[1] in INCLUDES]
    out = []
    for _, tokens in _hba_logical(data, cont):
        if tokens[0] in INCLUDES:
            out.append((tokens[0], tokens[1] if len(tokens) > 1 else ''))
        elif grammar == 'hba':
            for field in tokens[1:3]:
                out.extend(('@file', item[1:]) for item in field.split(',') if item.startswith('@') and len(item) > 1)
    return out


def _resolve(parent, target):
    """The raw/ name a relative target names from `parent` (a raw/ name) as derive resolves it (join, normalise, keep
    a path strictly under raw/), or None. A target that leaves raw/ and re-enters it through the directory name `raw`
    resolves (WH-3)."""
    if not target or target.startswith('/'):
        return None
    full = posixpath.normpath(posixpath.join(_WORK_RAW, posixpath.dirname(parent[len('raw/'):]), target))
    if not full.startswith(_WORK_RAW + '/'):
        return None
    return 'raw/' + full[len(_WORK_RAW) + 1:]


def _reach(files, cont=True):
    """{name: set of grammars} for every file the four top-level files reach, following includes the way derive.py and
    the frozen collector do."""
    seen, queue = {}, list(TOP)
    while queue:
        name, grammar = queue.pop(0)
        if name not in files:
            continue
        if grammar in seen.setdefault(name, set()):
            continue
        seen[name].add(grammar)
        for kind, target in _directives(grammar, files[name], cont):
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
    return seen


def grammars(files, cont=True):
    """{name: grammar} for every configuration file in `files`, following includes from the four top-level files the
    way derive.py and the frozen collector do. A file reached with two grammars, or by none, is 'unknown'."""
    seen = _reach(files, cont)
    out = {}
    for name in files:
        if name.startswith('raw/') and not name.endswith('.json'):
            reached = seen.get(name, set())
            out[name] = next(iter(reached)) if len(reached) == 1 else 'unknown'
    return out


def _major(files, name, path):
    if name not in files:
        return None
    try:
        doc = json.loads(bytes(files[name]))
        for key in path:
            doc = doc[key]
    except (ValueError, KeyError, TypeError, IndexError, UnicodeDecodeError, RecursionError):
        return None
    return doc if type(doc) is int else None


def _version_num(files):
    """The major from raw/COLLECTION-SIDECAR.json `server.server_version_num` (an integer, or its decimal text as the
    collector writes it), or None."""
    if SIDECAR not in files:
        return None
    try:
        value = json.loads(bytes(files[SIDECAR]))['server']['server_version_num']
    except (ValueError, KeyError, TypeError, IndexError, UnicodeDecodeError, RecursionError):
        return None
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 9:
        value = int(value)
    return value // 10000 if type(value) is int and value > 0 else None


def major_sources(files):
    """[(source, major)] for each source of the server's major that is present, in the order `continuation` trusts
    them: raw/declaration.json `major` (the declared derive), COLLECTION-SIDECAR.json `server.major`, and
    COLLECTION-SIDECAR.json `server.server_version_num` (the intent-free derive)."""
    out = []
    for label, major in (('raw/declaration.json major', _major(files, DECLARATION, ('major',))),
                         ('COLLECTION-SIDECAR.json server.major', _major(files, SIDECAR, ('server', 'major'))),
                         ('COLLECTION-SIDECAR.json server.server_version_num', _version_num(files))):
        if major is not None:
            out.append((label, major))
    return out


def _continued_line(files):
    """(name, line) of the first line ending in a backslash in a file that may be read with pg_hba.conf grammar
    (pg_hba.conf, pg_ident.conf, their includes and @file lists, reached with continuation on or off) or whose grammar
    is unknown; None when there is none. A line counts when its text, or any part of it derive.py would read as a line
    of its own, ends in a backslash."""
    hba_like = set()
    for cont in (True, False):
        reached = _reach(files, cont)
        hba_like.update(name for name, kinds in reached.items() if kinds & {'hba', 'ident', 'plain'})
        hba_like.update(n for n in files if isinstance(n, str) and n.startswith('raw/') and not n.endswith('.json')
                        and n not in reached)
    for name in sorted(hba_like):
        if name not in files:
            continue
        for number, body in enumerate(_bodies(files[name]), 1):
            if any(part.rstrip().endswith('\\') for part in (body.splitlines() or [body])):
                return name, number
    return None


def continuation(files):
    """Whether a pg_hba.conf line ending in a backslash continues (major 16 and later; module docstring, item 2). The
    declared derive reads raw/declaration.json `major` and the intent-free derive reads the sidecar's
    `server_version_num`: when the sources present disagree about which side of 16 the server is on and a
    pg_hba.conf-grammar line ends in a backslash, `bad_input` (the two readers would join the line differently; nothing
    is guessed). Otherwise the first source present decides; with none, the line continues (which withholds more)."""
    sources = major_sources(files)
    if not sources:
        return True
    if len({major >= 16 for _, major in sources}) > 1:
        hit = _continued_line(files)
        if hit is not None:
            name, line = hit
            first = sources[0]
            other = next(s for s in sources if (s[1] >= 16) != (first[1] >= 16))
            raise Refusal('bad_input', 'line %d of %s ends in a backslash, which continues the line from PostgreSQL 16, '
                          'and the sources of the server version disagree: %s says %d, %s says %d, so whether the line '
                          'continues cannot be told. Make raw/declaration.json major the server\'s major, or send the '
                          'collector\'s own COLLECTION-SIDECAR.json, then run again; nothing was sent'
                          % (line, name, first[0], first[1], other[0], other[1]), path=name, line=line,
                          malformation=malformation('continuation_major', file=name, line=line, field='major'))
    return sources[0][1] >= 16


# ---------- the collector's record ----------
def _json_or_none(files, name):
    try:
        return json.loads(bytes(files[name]))
    except (KeyError, ValueError, TypeError, UnicodeDecodeError, RecursionError):
        return None


def collector_rows(files):
    """({raw name: {reason label: count}}, None) from raw/COLLECTION-SIDECAR.json `redaction_withheld`, or (None, why)
    when the record cannot be read: the sidecar is absent, unreadable, or has no `redaction_withheld` list."""
    if SIDECAR not in files:
        return None, 'absent'
    doc = _json_or_none(files, SIDECAR)
    if not isinstance(doc, dict):
        return None, 'unreadable'
    rows = doc.get('redaction_withheld')
    if not isinstance(rows, list):
        return None, 'without its redaction_withheld list'
    out = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get('file'), str) and isinstance(row.get('field'), str) \
                and type(row.get('count')) is int and row['count'] > 0:
            bucket = out.setdefault(row['file'], {})
            bucket[row['field']] = bucket.get(row['field'], 0) + row['count']
    return out, None


def _line_number(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def setting_locations(files):
    """{raw name: {line: setting name}} for every line the server says a setting came from: raw/pg_settings.json
    rows (`sourcefile` mapped by the collector to its raw/ copy, `sourceline`; the collector's fixed setting list, as
    loaded) and raw/catalog_snapshot.json `pg_file_settings` rows (every line of the files on disk, read only when the
    collection role may read that view), their server paths mapped to raw/ names through the sidecar's file entries
    and the pg_settings rows. A path that maps to no raw/ name is not guessed."""
    server_to_raw = {}
    side = _json_or_none(files, SIDECAR)
    for entry in (side.get('entries') if isinstance(side, dict) else None) or ():
        if isinstance(entry, dict) and entry.get('kind') == 'file' and isinstance(entry.get('server_path'), str) \
                and isinstance(entry.get('target'), str) and entry['target'].startswith('file:raw/'):
            server_to_raw[posixpath.normpath(entry['server_path'])] = entry['target'][len('file:'):]
    out = {}

    def add(raw_name, line, setting):
        if isinstance(raw_name, str) and line is not None and isinstance(setting, str):
            out.setdefault(raw_name, {}).setdefault(line, setting)
    rows = _json_or_none(files, 'raw/pg_settings.json')
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict) or not isinstance(row.get('sourcefile'), str):
            continue
        if row.get('sourcefile_mapping') == 'raw-relative copy of the server file':
            raw_name = 'raw/' + row['sourcefile']
            if isinstance(row.get('server_sourcefile'), str):
                server_to_raw.setdefault(posixpath.normpath(row['server_sourcefile']), raw_name)
            add(raw_name, _line_number(row.get('sourceline')), row.get('name'))
    snap = _json_or_none(files, SNAPSHOT)
    for row in (snap.get('pg_file_settings') if isinstance(snap, dict) else None) or ():
        if isinstance(row, dict) and isinstance(row.get('sourcefile'), str):
            add(server_to_raw.get(posixpath.normpath(row['sourcefile'])), _line_number(row.get('sourceline')),
                row.get('name') if isinstance(row.get('name'), str) else '(an error row)')
    return out


# ---------- one file ----------
def _bodies(data):
    """The physical lines (PostgreSQL's numbering: lines end at '\\n'), each without its trailing '\\r' run."""
    parts = bytes(data).split(b'\n')
    if parts and not parts[-1]:
        parts.pop()
    return [p.decode('utf-8', 'surrogateescape').rstrip('\r') for p in parts]


def redacted_lines(data):
    """The 1-based numbers of the collector's whole-line marker lines."""
    return [n for n, body in enumerate(_bodies(data), 1) if body == REDACTED_LINE]


def _lines_text(numbers):
    return ', '.join('line %d' % n for n in numbers[:12]) + (' and %d more' % (len(numbers) - 12)
                                                            if len(numbers) > 12 else '')


def _commented_values(data):
    """{setting: count} of commented-out lines that keep a setting with the collector's withheld-value marker."""
    out = {}
    for body in _bodies(data):
        m = _COMMENTED_VALUE.match(body)
        if m:
            out[m.group(1).lower()] = out.get(m.group(1).lower(), 0) + 1
    return out


def _conf_setting_withheld(fields, data):
    """The setting names whose line the collector withheld whole: more `<name>:<name>:withheld_whole` rows than lines
    that keep the setting with the withheld-value marker (collect_pg.py writes one such row per withheld value)."""
    kept = {}
    for body in _bodies(data):
        stripped = body.strip()
        match = _DERIVE_KEY.match(stripped) if stripped and not stripped.startswith('#') else None
        if match and match.group(3).startswith(WITHHELD_VALUE):
            kept[match.group(1).lower()] = kept.get(match.group(1).lower(), 0) + 1
    out = []
    for field, count in sorted(fields.items()):
        m = _LABEL_KEY.fullmatch(field)
        # 'line:line:withheld_whole' is the collector's reason for a prose comment as well as for a setting line it
        # withheld for a control character or secret pattern: the reason alone cannot tell them apart; the setting
        # locations can
        if m and not m.group(1) and m.group(2) == m.group(3) and m.group(2) != 'line' \
                and count > kept.get(m.group(2), 0):
            out.append(m.group(2))
    return out


def _hba_record_reasons(fields):
    """The collector's reasons for withholding a whole pg_hba.conf-grammar line that are not a comment."""
    return sorted(f for f in fields if f.startswith('line:') and f != _HBA_COMMENT)


def _hba_comment_rows(fields, data, as_collected):
    rows = fields.get(_HBA_COMMENT, 0)
    if as_collected:                     # kept rules whose trailing comment the collector withheld in place
        rows -= sum(1 for body in _bodies(data) if body != REDACTED_LINE and body.endswith(WITHHELD_COMMENT)
                    and not body.lstrip().startswith('#'))
    return max(0, rows)


def _conf_comment_rows(fields, data):
    rows = sum(fields.get(f, 0) for f in _CONF_COMMENT)
    kept = _commented_values(data)
    for field, count in fields.items():
        m = _LABEL_KEY.fullmatch(field)
        if m and m.group(1) and m.group(2) == m.group(3):
            rows += max(0, count - kept.get(m.group(2), 0))
    return rows


NEXT_STEP_RULE = ('This deployment has a pg_hba.conf rule shape the collector withholds whole (a quoted name, an @file '
                  'list or a regular-expression user, for example); Assure cannot read it, so this rule shape cannot be '
                  'checked yet. What you can do today: remove quotes a name does not need; write an @file list\'s '
                  'names inline; use a +group role in place of a list; list a regular-expression user\'s roles by name. '
                  'Send Symbolia the file name and the line number (through your Symbolia contact) so the shape is '
                  'counted; nothing was sent')
NEXT_STEP_SETTING = ('This setting line cannot be checked yet. Send Symbolia the file name and the line number (through '
                     'your Symbolia contact) so it is counted; nothing was sent')
NEXT_STEP_SIDECAR = ('A collector output cannot be checked without the COLLECTION-SIDECAR.json the collector wrote with '
                     'it. Upload the collector output as written (its COLLECTION-SIDECAR.json beside raw/ or inside '
                     'it), then run again; nothing was sent')
NEXT_STEP_MANIFEST = ('Give the collector\'s output from one run as it wrote it: raw/ with COLLECTION-SIDECAR.json and '
                      'REDACTION-MANIFEST.json beside it (or inside raw/), all from that run, then run again; nothing '
                      'was sent')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_SAFE_LABEL = re.compile(r'[A-Za-z0-9_#:.,()@/^$ +-]{1,120}')


def _refuse(name, reason, line, kind):
    raise Refusal('collector_refused', '%s: %s' % (name, reason), path=name, line=line,
                  malformation=malformation(kind, file=name, line=line,
                                            field='redaction_withheld' if kind.startswith(('sidecar', 'marker_u'))
                                            else None))


_WHY_KIND = {'absent': 'sidecar_absent', 'unreadable': 'sidecar_unreadable',
             'without its redaction_withheld list': 'sidecar_unreadable', 'without a row for this file': 'sidecar_rows'}


def check_file(name, kinds, data, fields, why_absent, located, *, as_collected=False):
    """`collector_refused` when a whole-line marker in `name` may hide a rule or setting derive reads (module
    docstring). `kinds` is the set of grammars derive reads the file with ({'conf'}, {'hba'} or both); `fields` the
    sidecar's rows for the file (None when the record cannot be read, `why_absent` then says why); `located` the
    file's {line: setting} from `setting_locations`."""
    marks = redacted_lines(data)
    if not marks:
        return
    first = marks[0]
    if 'conf' in kinds:
        hits = [(n, located[n]) for n in marks if n in located]
        if hits:
            _refuse(name, 'the collector withheld whole %s, which the server reports as the source of %s; the check '
                    'would read it as absent. %s' % (_lines_text([n for n, _ in hits]),
                                                     ', '.join(sorted({s for _, s in hits})), NEXT_STEP_SETTING),
                    hits[0][0], 'setting_withheld')
    if fields is None:
        _refuse(name, 'the collector withheld whole %s, and its record of why (COLLECTION-SIDECAR.json) is %s, so a '
                'withheld comment cannot be told from a withheld rule or setting, which the check would read as '
                'absent. %s' % (_lines_text(marks), why_absent, NEXT_STEP_SIDECAR), first,
                _WHY_KIND.get(why_absent, 'sidecar_unreadable'))
    if 'conf' in kinds:
        names = _conf_setting_withheld(fields, data)
        if names:
            _refuse(name, 'the collector withheld whole a line that sets %s (reason %s); it is one of %s, and the '
                    'check would read that setting as absent. %s'
                    % (', '.join(names), ', '.join('%s:%s:withheld_whole' % (k, k) for k in names),
                       _lines_text(marks), NEXT_STEP_SETTING), first, 'setting_withheld')
    if 'hba' in kinds:
        reasons = _hba_record_reasons(fields)
        if 'conf' in kinds:                          # a file held to both grammars: conf's comment reasons are not rules
            reasons = [r for r in reasons if r not in _CONF_COMMENT]
        if reasons:
            _refuse(name, 'the collector withheld whole a rule it could not keep (reason %s); it is one of %s, and the '
                    'check would read it as absent. %s' % ('; '.join(reasons), _lines_text(marks), NEXT_STEP_RULE),
                    first, 'rule_withheld')
    budgets = []
    if 'conf' in kinds:
        budgets.append(_conf_comment_rows(fields, data))
    if 'hba' in kinds:
        budgets.append(_hba_comment_rows(fields, data, as_collected))
    comments = max(budgets) if budgets else 0
    if len(marks) > comments:
        _refuse(name, 'the collector withheld whole %d lines (%s), and its record of why (COLLECTION-SIDECAR.json) '
                'shows %s withheld whole, so a withheld rule or setting may be among them, which the check would '
                'read as absent. %s' % (len(marks), _lines_text(marks),
                                        'no comment' if not comments else
                                        ('only %d comment%s' % (comments, '' if comments == 1 else 's')),
                                        NEXT_STEP_SIDECAR), first, 'marker_unaccounted')


def held_files(files):
    """[(name, kinds)], sorted by name, for every file in which a collector whole-line marker may hide what derive
    reads: a raw/ configuration file holding at least one marker line, read with pg_hba.conf grammar, postgresql.conf
    grammar, or neither as derive resolves includes (then held to both). pg_ident.conf and @file lists are not held:
    derive reads neither."""
    reach = _reach(files, continuation(files))
    out = []
    for name in sorted(n for n in files if isinstance(n, str)):
        if not name.startswith('raw/') or name.endswith('.json'):
            continue
        data = files[name]
        if REDACTED_LINE.encode('utf-8') not in bytes(data) or not redacted_lines(data):
            continue
        reached = reach.get(name, set())
        kinds = reached & {'conf', 'hba'}
        if not kinds:
            if reached:                              # pg_ident.conf and @file lists only: derive reads neither
                continue
            kinds = {'conf', 'hba'}                  # no include reaches it as derive resolves: held to both
        out.append((name, kinds))
    return out


def first_old_marker(files):
    """(name, line) of the first earlier-collector comment marker in any raw/ configuration file, or None."""
    for name in sorted(n for n in files if isinstance(n, str) and n.startswith('raw/') and not n.endswith('.json')):
        data = files[name]
        if REDACTED_LINE.encode('utf-8') in bytes(data):
            lines = redacted_lines(data)
            if lines:
                return name, lines[0]
    return None


MIXED_NEXT_STEP = ('Send the output of one collector run as it wrote it: raw/ with the COLLECTION-SIDECAR.json of the same '
                   'run; nothing was sent')


def check_generation(files):
    """Item 5 of the module docstring: [markers.Marker] for the RF-28 markers of `files`. `bad_input` for a broken
    marker (serve/markers.py `scan`); `collector_refused` (`collector_mixed`) when the collection mixes the two
    collectors: an RF-28 marker and an earlier comment marker in the same upload, an earlier comment marker with an
    RF-28 sidecar, an RF-28 marker with an earlier sidecar, or an RF-28 sidecar whose rows are not in the RF-28 form."""
    found = markers.scan(files)
    old = first_old_marker(files)
    gen = markers.generation(files)

    def mixed(name, line, why):
        raise Refusal('collector_refused', '%s: line %d %s, so this upload mixes the RF-28 collector\'s output with an '
                      'earlier collector\'s. %s' % (name, line, why, MIXED_NEXT_STEP), path=name, line=line,
                      malformation=malformation('collector_mixed', file=name, line=line))
    if old is not None and found:
        mixed(old[0], old[1], 'is the earlier collector\'s comment marker and %s line %d is an RF-28 marker'
              % (found[0].file, found[0].line))
    if old is not None and gen == markers.RF28:
        mixed(old[0], old[1], 'is the earlier collector\'s comment marker and COLLECTION-SIDECAR.json is the RF-28 '
              'collector\'s')
    if found and gen == markers.EARLIER:
        mixed(found[0].file, found[0].line, 'is an RF-28 marker and COLLECTION-SIDECAR.json is an earlier collector\'s')
    if gen == markers.RF28 and markers.rows_in_new_form(files) is False:
        line = found[0].line if found else 1
        name = found[0].file if found else markers.SIDECAR
        mixed(name, line, 'is read with an RF-28 COLLECTION-SIDECAR.json whose redaction_withheld rows lack the RF-28 '
              'line and reason')
    return found


def check(files, *, as_collected=False):
    """Refuse (`collector_refused`) an upload in which a collector whole-line marker may hide a rule or setting that
    derive reads (module docstring). Returns None when every file is faithful. Reads only the given bytes.

    The RF-28 markers are checked first (`check_generation`). For an RF-28 collection the earlier marker's rules below
    still run as defence in depth, but no file holds the earlier marker (a mix is refused above), so none of them holds a
    file and none fires: an RF-28 marker identifies itself and reads as not observed."""
    check_generation(files)
    held = held_files(files)
    if not held:
        return
    rows, why = collector_rows(files)
    located = setting_locations(files)
    for name, kinds in held:
        fields = None if rows is None else rows.get(name)
        check_file(name, kinds, files[name], fields, why if rows is None else 'without a row for this file',
                   located.get(name, {}), as_collected=as_collected)


# ---------- the binding of the sidecar to the collected bytes (refutation 005, WH-4) ----------
def _sidecar_kept(field):
    """The frozen collector's own rule for which manifest entries its sidecar's `redaction_withheld` carries."""
    return 'withheld' in field or 'unparsed' in field


def _manifest_rows(entries):
    """{raw name: {reason label: count}} from the manifest's `entries`, the rows the sidecar would carry."""
    out = {}
    for row in entries:
        if isinstance(row, dict) and isinstance(row.get('file'), str) and isinstance(row.get('field'), str) \
                and type(row.get('count')) is int and row['count'] > 0 and _sidecar_kept(row['field']):
            bucket = out.setdefault(row['file'], {})
            bucket[row['field']] = bucket.get(row['field'], 0) + row['count']
    return out


def _label(text):
    return text if _SAFE_LABEL.fullmatch(text) else '(a label with other characters)'


def _short(digest):
    return digest[:12] + '...' if isinstance(digest, str) and _HEX64.fullmatch(digest) else 'no sha256'


def check_binding(files, manifest):
    """Refuse (`collector_refused`) unless the collector's REDACTION-MANIFEST.json (`manifest`, its bytes, or None when
    absent) binds the sidecar to these bytes for every held file (module docstring, item 4). `files` must be the bytes
    as collected, before any withholding. Returns None when no file is held or every held file is bound."""
    check_generation(files)
    held = held_files(files)
    if not held:
        return

    def refuse(name, why, kind):
        marks = redacted_lines(files[name])
        _refuse(name, 'the collector withheld whole %s, and %s, so its COLLECTION-SIDECAR.json cannot be shown to be the '
                'record of these bytes; a sidecar from another run could count a withheld rule as a comment. %s'
                % (_lines_text(marks), why, NEXT_STEP_MANIFEST), marks[0], kind)

    first = held[0][0]
    if manifest is None:
        refuse(first, 'its REDACTION-MANIFEST.json, which the collector writes beside raw/ in the same run as the '
                      'sidecar, is absent', 'manifest_absent')
    try:
        doc = json.loads(bytes(manifest))
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError):
        doc = None
    digests = doc.get('sanitised_sha256') if isinstance(doc, dict) else None
    entries = doc.get('entries') if isinstance(doc, dict) else None
    if not isinstance(digests, dict) or not isinstance(entries, list):
        refuse(first, 'its REDACTION-MANIFEST.json is unreadable or has no sanitised_sha256 or entries',
               'manifest_unreadable')
    side_rows, _ = collector_rows(files)
    man_rows = _manifest_rows(entries)
    for name, _kinds in held:
        want = digests.get(name)
        got = hashlib.sha256(bytes(files[name])).hexdigest()
        if not isinstance(want, str):
            refuse(name, 'REDACTION-MANIFEST.json records no digest for this file', 'manifest_digest')
        if want != got:
            refuse(name, 'REDACTION-MANIFEST.json records the digest %s for this file but the file as collected has %s '
                         '(the manifest is from another run, or the file changed after collection; a checkout or '
                         'copy that converts line endings also changes the bytes)'
                   % (_short(want), _short(got)), 'manifest_digest')
        if side_rows is None:
            continue                                 # `check` refuses: the sidecar is absent or unreadable
        mine, theirs = side_rows.get(name, {}), man_rows.get(name, {})
        if mine != theirs:
            differ = sorted(f for f in set(mine) | set(theirs) if mine.get(f, 0) != theirs.get(f, 0))
            refuse(name, 'COLLECTION-SIDECAR.json and REDACTION-MANIFEST.json disagree on what the collector withheld '
                         'in this file (%s%s)'
                   % ('; '.join('%s: sidecar %d, manifest %d' % (_label(f), mine.get(f, 0), theirs.get(f, 0))
                                for f in differ[:6]), '; and %d more' % (len(differ) - 6) if len(differ) > 6 else ''),
                   'manifest_rows')

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
