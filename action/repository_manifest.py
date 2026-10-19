"""The repository manifest `raw/REPOSITORY.json`, computed in the runner (serve-099; issue #322).

For profile python-auth-declared-model the bundle carries `raw/REPOSITORY.json`: `schema`
(assure.codeauth.repository/v1), `commit` (40 hex), `tree` (the git tree id of the exact file set sent), one
`{path, bytes, sha256, mode}` row per `raw/repository/<path>` file sent, and the seven flags; with a declaration of
schema assure.identity.declaration/v1 naming its `stack` in raw/declaration.json, also `declaration_sha256`, that file's
SHA-256 (#3840). Everything in it is
mechanical, so when the customer's artefacts do not hold one the Action writes it here, after the files are read and
the withholding pass has run, over exactly the bytes that will be uploaded. No customer input and no acceptance step.
A supplied `raw/REPOSITORY.json` is kept byte for byte; the server checks it as it checks any upload.

- `path`: the name under `raw/repository/`; `bytes` and `sha256`: of the bytes sent.
- `mode`: `100755` when the file under the artefacts directory has its owner execute bit, else `100644` (git's rule
  for a regular file; links and other entries never reach here, `serve.bundle.from_directory` refuses them).
- `tree`: git's object hashing, the checker's own (its stage-1 ingest, `git_blob_id` / `git_tree_id`): a blob is
  sha1(`blob <n>\\0` + bytes); a tree lists `<mode> <name>\\0<20-byte id>` with subdirectories as mode `40000`, sorted
  as git sorts them (a directory's name compares as `name/`). It equals `git rev-parse HEAD:<dir>` for a committed
  directory, and it is what the checker recomputes from the files and compares to `tree`.
- `commit`: the checkout's HEAD (`git rev-parse --verify HEAD` in the artefacts directory, read only, an argument
  list), else GITHUB_SHA when that is 40 hex; neither is `bad_input` naming both ways to go on.

serve-102: with neither artefacts nor a connection, `from_checkout` reads the repository from the checkout itself (its
tracked Python files and requirements.md, listed by `git ls-files -s`, read only), with git's index modes. Issue #3841:
when the checkout's `.assure/declaration.json` names `app_roots`, only the Python files under those directories are
read (requirements.md always); a request that would still pass the body limit stops in the runner naming its size, the
limit and `app_roots`, the one setting that narrows it.
Issue #3128: it also reads the tracked dependency files (requirements*.txt / *.in, constraints*.txt, Pipfile.lock,
poetry.lock, uv.lock, pyproject.toml) in the runner and sends none of them: only the derived `raw/LIBRARY-VERSIONS.json`,
one entry per package the checker reads a guard of (flask-login; flask-httpauth, issue #3320; flask-jwt-extended, issue #3253) or a pass-through
decorator of (flask-apispec, issue #3331) or the routes of (flask-restful, issue #3330),
`{version | range | unread, source: path:line}`.

Standard library, `serve` (the seven flags, serve.bundle's names) and serve.outcomes only; the child processes are
those two read-only git commands.
execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
from pathlib import Path

from serve import FLAGS
from serve.outcomes import Refusal

PROFILE = 'python-auth-declared-model'
NAME = 'raw/REPOSITORY.json'
PREFIX = 'raw/repository/'
SCHEMA = 'assure.codeauth.repository/v1'
DECLARATION = 'raw/declaration.json'
IDENTITY_SCHEMA = 'assure.identity.declaration/v1'
_HEX40 = re.compile(r'[0-9a-f]{40}')
GIT_TIMEOUT_S = 30
CHECKOUT_DECLARATION = '.assure/declaration.json'      # action.declaration_draft.CHECKOUT_PATH


def git_blob_id(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def git_tree_id(entries):
    """Tree id of `entries` {relative posix path: (mode, blob id)}, as the checker computes it."""
    def build(prefix):
        rows = {}
        for path, (mode, blob) in entries.items():
            if prefix and not path.startswith(prefix):
                continue
            head, sep, _tail = path[len(prefix):].partition('/')
            if sep:
                rows.setdefault(head, ('40000', None))
            else:
                rows[head] = (mode, blob)
        body = b''
        for name in sorted(rows, key=lambda n: n + '/' if rows[n][0] == '40000' else n):
            mode, blob = rows[name]
            oid = build('%s%s/' % (prefix, name)) if mode == '40000' else blob
            body += ('%s %s' % (mode, name)).encode('utf-8') + b'\0' + bytes.fromhex(oid)
        return hashlib.sha1(b'tree %d\0' % len(body) + body).hexdigest()
    return build('')


def raw_dir(root):
    """The directory `serve.bundle.from_directory` read as raw/ under `root`."""
    root = Path(root)
    return root / 'raw' if (root / 'raw').is_dir() or root.name != 'raw' else root


def head_commit(root, env):
    """The checkout's HEAD commit, else GITHUB_SHA; None when neither is a 40-hex commit."""
    child_env = {k: env[k] for k in ('PATH', 'HOME', 'SYSTEMROOT') if env.get(k)}
    child_env.setdefault('PATH', '/usr/bin:/bin')
    try:
        p = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', '--quiet', 'HEAD'], env=child_env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
        sha = p.stdout.strip() if p.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        sha = ''
    if _HEX40.fullmatch(sha):
        return sha
    sha = str(env.get('GITHUB_SHA') or '').strip().lower()
    return sha if _HEX40.fullmatch(sha) else None


def manifest(files, root, commit, modes=None):
    """The manifest document for the `raw/repository/` files in `files` ({name: bytes}) read from `root`; `modes`
    ({path: git mode}) when the files were read from git's index (the checkout, serve-102), else from lstat."""
    base = raw_dir(root) / 'repository'
    rows, entries = [], {}
    for name in sorted(n for n in files if n.startswith(PREFIX)):
        rel = name[len(PREFIX):]
        data = bytes(files[name])
        try:
            if modes is not None:
                mode = '100755' if modes.get(rel) == '100755' else '100644'
            else:
                st = os.lstat(base / rel)
                mode = '100755' if stat.S_ISREG(st.st_mode) and st.st_mode & stat.S_IXUSR else '100644'
        except OSError:
            mode = '100644'
        rows.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode})
        entries[rel] = (mode, git_blob_id(data))
    return {'schema': SCHEMA, 'commit': commit, 'tree': git_tree_id(entries), 'files': rows, **FLAGS}


def complete(collected, profile, root, env, modes=None):
    """Add `raw/REPOSITORY.json` to `collected.files` when `profile` is python-auth and none was supplied. Returns the
    document written, or None when nothing was added."""
    if profile != PROFILE or NAME in collected.files:
        return None
    commit = head_commit(root, env)
    if commit is None:
        raise Refusal('bad_input', '%s is not in the artefacts and the commit could not be read: run actions/checkout '
                      'before this step so the artefacts directory is inside the git checkout, or send %s yourself'
                      % (NAME, NAME), path=NAME)
    doc = manifest(collected.files, root, commit, modes)
    decl = collected.files.get(DECLARATION)
    if decl is not None and _declared_stack(decl) is not None:
        doc['declaration_sha256'] = hashlib.sha256(bytes(decl)).hexdigest()
    collected.files[NAME] = (json.dumps(doc, indent=1, sort_keys=True) + '\n').encode('utf-8')
    return doc

# ------------------------------------------------------------------ issue #3128: the derived library-version record
#: The one derived fact the runner sends about the repository's dependency files (the Director's standing direction of
#: 16 Oct, "free tier reads wide, sends minimal"): the lock and requirement files are read here and never sent.
LIBRARY_VERSIONS = 'raw/LIBRARY-VERSIONS.json'
#: The packages whose version the checker reads (its LIBRARY_GUARDS); no other package name is ever sent. Issue #3253:
#: flask-jwt-extended, whose guards and identity claim the checker reads by version; #3331: flask-apispec, whose
#: use_kwargs / marshal_with the checker reads as argument parsing and response shaping by version; #3330:
#: flask-restful, whose Api / Resource routes the checker reads by version; #3320: flask-httpauth, whose guards the
#: checker reads by version.
LIBRARY_PACKAGES = ('flask-apispec', 'flask-httpauth', 'flask-jwt-extended', 'flask-login', 'flask-restful')
LOCK_FILE = re.compile(r'(?i)^(requirements[^/]*\.(txt|in)|constraints[^/]*\.txt|pipfile\.lock|poetry\.lock|uv\.lock|'
                       r'pyproject\.toml)$')
LOCK_FILE_BYTES = 16 * 1024 * 1024


def is_dependency_file(rel):
    """A dependency file the runner reads for the record: a LOCK_FILE name, or a .txt / .in under a `requirements/`
    directory."""
    parts = rel.split('/')
    return bool(LOCK_FILE.match(parts[-1])) or (len(parts) > 1 and parts[-2].lower() == 'requirements'
                                                 and parts[-1].lower().endswith(('.txt', '.in')))
_EXACT_KINDS = ('pipfile.lock', 'poetry.lock', 'uv.lock')
_REQ = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*((?:[<>=!~]=?|===)\s*[^;#\s,]+'
                  r'(?:\s*,\s*(?:[<>=!~]=?|===)\s*[^;#\s,]+)*)?\s*(?:;.*)?$')


#: The range form the checker reads (`extract._RANGE_RE`): comparator-led clauses joined by commas.
_RANGE = re.compile(r'(?:(?:===|==|!=|~=|>=|<=|>|<)[0-9][0-9A-Za-z.*+!-]{0,31})(?:,(?:===|==|!=|~=|>=|<=|>|<)'
                    r'[0-9][0-9A-Za-z.*+!-]{0,31}){0,7}')


def _norm(name):
    return re.sub(r'[-_.]+', '-', str(name)).lower()


def _spec(text):
    """(version, None) for one exact `==X` pin, else (None, range) with spaces removed."""
    spec = re.sub(r'\s+', '', text or '')
    m = re.fullmatch(r'===?([0-9][0-9A-Za-z.+!-]*)', spec)
    if m and '*' not in spec:
        return m.group(1), None
    return None, spec


def _caret(spec):
    """Poetry's version constraint as PEP 440: `^X.Y.Z` / `~X.Y.Z` as a range, a bare `X.Y.Z` as the exact pin
    `==X.Y.Z` (Poetry's meaning), `*` as no bound; any other text as it is."""
    text = (spec or '').strip()
    if text == '*':
        return ''
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', text):
        return '==' + text
    m = re.fullmatch(r'\s*([\^~])\s*([0-9]+(?:\.[0-9]+)*)\s*', spec or '')
    if not m:
        return spec
    parts = [int(x) for x in m.group(2).split('.')]
    if m.group(1) == '~':
        upper = parts[:2] if len(parts) > 1 else parts[:1]
        upper[-1] += 1
    else:
        i = next((k for k, v in enumerate(parts) if v), len(parts) - 1)
        upper = parts[:i + 1]
        upper[-1] += 1
    return '>=%s,<%s' % (m.group(2), '.'.join(str(x) for x in upper))


def _line_of(text, pattern, start=0):
    m = re.compile(pattern, re.M).search(text, start)
    return (text.count('\n', 0, m.start()) + 1, m) if m else (None, None)


def _read_lock(rel, text):
    """[(package, version | None, range | None, line, unread | None)] for the named libraries."""
    base = rel.rsplit('/', 1)[-1].lower()
    out = []
    if base in ('poetry.lock', 'uv.lock'):
        for m in re.finditer(r'^\[\[package\]\]\s*$', text, re.M):
            end = text.find('\n[', m.end())
            block = text[m.end():end if end >= 0 else len(text)]
            name = re.search(r'^name\s*=\s*"([^"]+)"\s*$', block, re.M)
            ver = re.search(r'^version\s*=\s*"([^"]+)"\s*$', block, re.M)
            if name and ver and _norm(name.group(1)) in LIBRARY_PACKAGES:
                line = text.count('\n', 0, m.end() + ver.start()) + 1
                out.append((_norm(name.group(1)), ver.group(1), None, line, None))
    elif base == 'pipfile.lock':
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            return out
        if not isinstance(doc, dict) or not isinstance(doc.get('default'), dict):
            return out
        for name, row in sorted(doc['default'].items()):
            if _norm(name) in LIBRARY_PACKAGES and isinstance(row, dict) and isinstance(row.get('version'), str):
                start = _line_of(text, r'^\s*"%s"\s*:\s*\{' % re.escape(name))[1]
                line, _m = _line_of(text, r'"version"\s*:', start.end() if start else 0)
                version, rng = _spec(row['version'])
                out.append((_norm(name), version, rng, line or 1, None))
    elif base == 'pyproject.toml':
        text = _toml_without_comments(text)   # sol-a3 bus 457: a comment quoting an older pin is no pin
        for m in re.finditer(r'["\']([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^"\';]*)(?:;[^"\']*)?["\']', text):
            if _norm(m.group(1)) in LIBRARY_PACKAGES and (not m.group(2).strip() or m.group(2).strip()[0] in '<>=!~'):
                version, rng = _spec(m.group(2))
                out.append((_norm(m.group(1)), version, rng, text.count('\n', 0, m.start()) + 1, None))
        for m in re.finditer(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(?:"([^"]*)"|\{[^}\n]*version\s*=\s*"([^"]*)")', text, re.M):
            if _norm(m.group(1)) in LIBRARY_PACKAGES:
                version, rng = _spec(_caret(m.group(2) if m.group(2) is not None else m.group(3)))
                out.append((_norm(m.group(1)), version, rng, text.count('\n', 0, m.start()) + 1, None))
    else:
        pending, start = '', None
        for n, line in enumerate(text.splitlines(), 1):
            body = re.split(r'\s+#', line, maxsplit=1)[0].strip()
            if not body or body.startswith('#'):
                continue
            if start is None:
                start = n
            continued = body.endswith('\\')
            pending += (' ' if pending else '') + (body[:-1].rstrip() if continued else body)
            if continued:
                continue
            body, pending, first = pending, '', start
            start = None
            # Hash options change pip's integrity check, never the requirement's version. Retain the first line.
            body = re.sub(r'\s+--hash(?:=|\s+)[A-Za-z0-9_-]+:[0-9A-Fa-f]+(?=\s|$)', '', body).strip()
            # An option after an environment marker remains an option; quoted marker values remain values.
            unquoted = re.sub(r'''"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*' ''', '', body, flags=re.X)
            m = None if re.search(r'(?:^|\s)--', unquoted) else _REQ.match(body)
            if m and _norm(m.group(1)) in LIBRARY_PACKAGES:
                version, rng = _spec(m.group(2))
                out.append((_norm(m.group(1)), version, rng, first, None))
            elif (name := re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\b', body)) \
                    and _norm(name.group(1)) in LIBRARY_PACKAGES:
                out.append((_norm(name.group(1)), None, None, first,
                            '%s requirement syntax is outside the read set' % _norm(name.group(1))))
        if pending and (name := re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\b', pending)) \
                and _norm(name.group(1)) in LIBRARY_PACKAGES:
            out.append((_norm(name.group(1)), None, None, start,
                        '%s requirement syntax is outside the read set' % _norm(name.group(1))))
    return out


def _toml_without_comments(text):
    """`text` with each TOML comment (a `#` outside a basic or literal string, to the end of its line) blanked to spaces,
    so offsets and line numbers stay those of the file."""
    out, quote, triple, i, n = [], None, False, 0, len(text)
    while i < n:
        c = text[i]
        if quote is None:
            if c == '#':
                j = text.find('\n', i)
                j = n if j < 0 else j
                out.append(' ' * (j - i))
                i = j
                continue
            if c in '"\'':
                triple = text.startswith(c * 3, i)
                quote = c
                out.append(c * 3 if triple else c)
                i += 3 if triple else 1
                continue
        else:
            if c == '\\' and quote == '"' and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if triple and text.startswith(quote * 3, i):
                out.append(quote * 3)
                quote, triple = None, False
                i += 3
                continue
            if not triple and (c == quote or c == '\n'):
                quote = None
        out.append(c)
        i += 1
    return ''.join(out)


def library_versions(files):
    """The derived record {package: entry} from the dependency files among `files` ({path: bytes}, read in the runner):
    for each package in LIBRARY_PACKAGES a file names, `{"version", "source"}` when every exact pin agrees (a lock
    file's resolved version, or `==X`), else `{"range", "source"}` for the one range the requirement files give, else
    `{"unread", "source"}` with the reason (pins or ranges that disagree, or a requirement with no bound). `source` is
    the `path:line` read. Nothing else of any file is kept."""
    found = {}
    for rel in sorted(files):
        if not is_dependency_file(rel) or len(files[rel]) > LOCK_FILE_BYTES:
            continue
        text = files[rel].decode('utf-8', 'replace')
        for pkg, version, rng, line, unread in _read_lock(rel, text):
            found.setdefault(pkg, []).append((version, rng, '%s:%d' % (rel, line), unread))
    out = {}
    for pkg in sorted(found):
        rows = found[pkg]
        pins = [(v, src) for v, _r, src, _u in rows if v is not None]
        ranges = sorted({r for v, r, _s, _u in rows if v is None and r})
        unread = next(((u, s) for _v, _r, s, u in rows if u), None)
        invalid_pin = next(((v, s) for v, s in pins if not re.fullmatch(r'[0-9][0-9A-Za-z.+!-]{0,63}', v)), None)
        if unread:
            out[pkg] = {'unread': unread[0], 'source': unread[1]}
        elif invalid_pin:
            out[pkg] = {'unread': '%s pin has a version Assure does not read' % pkg, 'source': invalid_pin[1]}
        elif pins:
            versions = sorted({v for v, _ in pins})
            if len(versions) == 1:
                out[pkg] = {'version': versions[0], 'source': pins[0][1]}
            else:
                out[pkg] = {'unread': 'dependency files pin %s at %d different versions (%d pins)' % (pkg, len(versions), len(pins)),
                            'source': pins[0][1]}
        elif len(ranges) == 1 and not _RANGE.fullmatch(ranges[0]):
            # a range the checker does not read is sent as unread, never as a value that refuses the whole record
            out[pkg] = {'unread': '%s is required by a range Assure does not read: %s' % (pkg, ranges[0][:80]),
                        'source': next(s for v, r, s, _u in rows if r == ranges[0])}
        elif len(ranges) == 1:
            out[pkg] = {'range': ranges[0], 'source': next(s for v, r, s, _u in rows if r == ranges[0])}
        elif ranges:
            out[pkg] = {'unread': 'dependency files admit %s by %d different ranges (%d entries)' % (pkg, len(ranges), len(rows)),
                        'source': rows[0][2]}
        else:
            out[pkg] = {'unread': '%s is required with no version bound' % pkg, 'source': rows[0][2]}
    # A derived fact must fit the receiver. Retain every row when deciding agreement, then bound its explanation.
    for pkg, entry in out.items():
        if 'unread' in entry and len(entry['unread']) > 512:
            entry['unread'] = '%s dependency facts are outside the read set (details exceed the record limit)' % pkg
        source = entry['source']
        path, _sep, line = source.rpartition(':')
        if not path or not re.fullmatch(r'[1-9][0-9]*', line) or any(ord(c) < 32 or ord(c) == 127 for c in path):
            out[pkg] = {'unread': '%s dependency source locator has an unreadable character' % pkg, 'source': None}
    # Normalize every locator before bounding the complete record.
    for pkg in out:
        if len(library_versions_bytes(out)) > 4096:
            out[pkg] = {'unread': '%s dependency source locator exceeds the 4096-byte record limit' % pkg, 'source': None}
    return out


def library_versions_bytes(record):
    return (json.dumps(record, sort_keys=True) + '\n').encode('utf-8')


def _declaration(top, cap):
    """The checkout's `.assure/declaration.json` under `top` as a JSON object; None when absent, a link, over `cap`
    bytes or not a JSON object."""
    path = Path(top) / CHECKOUT_DECLARATION
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        doc = json.loads(path.read_bytes().decode('utf-8'))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _roots(value):
    """Normalised relative directory names of a list of root strings; None when it is not a non-empty list of strings
    or one names the whole checkout (`.`). A root through `..` names no tracked file and is dropped."""
    if not isinstance(value, list) or not value or not all(isinstance(r, str) for r in value):
        return None
    out = []
    for raw in value:
        parts = [p for p in raw.strip().replace('\\', '/').split('/') if p not in ('', '.')]
        if not parts:
            return None                       # `.` or `/`: the whole checkout
        if '..' in parts:
            continue                          # outside the checkout: names no tracked file
        root = '/'.join(parts)
        if root not in out:
            out.append(root)
    return out or None


def app_roots(top, cap):
    """Issue #3841: the `app_roots` of the checkout's `.assure/declaration.json` under `top`, as normalised relative
    directory names (`./serve/` reads `serve`); None when there is no such file (a link is not read), it is over `cap`
    bytes or not a JSON object, `app_roots` is not a non-empty list of names, or a root names the whole checkout (`.`).
    None reads the checkout as before: the free tier reads wide."""
    doc = _declaration(top, cap)
    return _roots(doc.get('app_roots')) if doc is not None else None


_DOTTED = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*')
_LOCATOR = re.compile(r'([^\s:]+\.py)(?::[0-9]+)?')


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _ancestors(rel_dir):
    parts = rel_dir.split('/') if rel_dir else []
    return {'/'.join(parts[:k]) for k in range(len(parts))}


class Bound:
    """Issue #3841 (night read 10742 HIGH-1): what a declaration with `app_roots` sends from the checkout. The roots
    (with `resource_roots`), and everything the checker loads by name from outside them, so no file the checker reads
    on main goes missing:
    - every tracked Python file directly in a directory above a root, the checkout's top included: the launcher entry
      modules (`wsgi.py`, `app.py`; extract_readboundary `LAUNCHER_ENTRY_MODULES`), Django's and FastAPI's loaded
      modules (`manage.py`, `settings.py`, `asgi.py`, `main.py`; their readset `LOADED`), and the `<dir>/<name>.py`
      files the shadowed-import census looks for (a top-level `flask.py`);
    - every `<dir>/<name>/__init__.py` under such a directory: each root's ancestor package `__init__.py` and the
      package form of a shadowing import;
    - every module the declaration names (a dotted name such as `app.guards.login_required`, or a locator such as
      `serve/api.py:242`), and the directories above it as above;
    - r3 (night read at 15d9c77e, HIGH-1): every config module a kept module loads by name with a literal
      `from_object("a.b")` or `from_pyfile("name.py")` (extract_readboundary `CONFIG_BY_NAME_LOADERS`, resolved by
      `_config_target`), looked up as the checker does in the directories above the kept modules and their `instance/`
      folders; that file alone, not its directory.
    `requirements.md` is always sent."""

    def __init__(self, roots, resource_roots, named):
        self.roots = roots
        self.resource_roots = resource_roots
        self.named = named
        self.loaded = set()
        self.dirs = set()
        for r in roots + resource_roots:
            self.dirs |= _ancestors(r)

    def resolve(self, tracked):
        """Add the directories of each named module that is tracked (`tracked`: the checkout's paths): the checker
        adopts it, so the directories above it are searched as the roots' are."""
        for rel in self.named & set(tracked):
            self.dirs |= _ancestors(posixpath.dirname(rel)) | {posixpath.dirname(rel)}
        return self

    def config_loads(self, top, tracked, cap):
        """r3: add to `loaded` each tracked Python file a kept module (or an added one, in turn) loads by name as Flask
        config. The kept modules are parsed here, before the size check; a module over `cap` bytes or not Python 3
        is skipped (the size check or the checker names it)."""
        tset = set(tracked)
        kept = [t for t in tracked if t.endswith('.py') and self.keeps(t)]
        dirs = {''}
        for rel in kept:
            d = posixpath.dirname(rel)
            dirs |= _ancestors(d) | {d}
        todo, seen = list(kept), set()
        while todo:
            rel = todo.pop()
            if rel in seen:
                continue
            seen.add(rel)
            for kind, value in _config_loads_in(Path(top) / rel, cap):
                for cand in _config_candidates(kind, value, dirs):
                    if cand in tset and not self.keeps(cand):
                        self.loaded.add(cand)
                        todo.append(cand)
        return self

    def under(self, rel):
        return _under(rel, self.roots) or _under(rel, self.resource_roots)

    def keeps(self, rel):
        if rel == 'requirements.md' or self.under(rel) or rel in self.named or rel in self.loaded:
            return True
        d = posixpath.dirname(rel)
        if d in self.dirs:
            return True
        return posixpath.basename(rel) == '__init__.py' and d and posixpath.dirname(d) in self.dirs


CONFIG_BY_NAME = {'from_object': 'obj', 'from_pyfile': 'filename'}     # the loader and its argument's keyword
_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _config_loads_in(path, cap):
    """(loader, literal) for each `<x>.from_object("...")` / `<x>.from_pyfile("...")` in the module at `path`."""
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return []
        tree = ast.parse(path.read_bytes())
    except (OSError, SyntaxError, ValueError):
        return []
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in CONFIG_BY_NAME):
            continue
        arg = n.args[0] if n.args else next((k.value for k in n.keywords if k.arg == CONFIG_BY_NAME[n.func.attr]),
                                            None)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append((n.func.attr, arg.value))
    return out


def _config_candidates(kind, value, dirs):
    """The repository paths `kind(value)` can load from under `dirs`, as `_config_target` resolves them: a dotted
    `from_object` name's module or package at each prefix; a relative `from_pyfile` name in each directory and its
    `instance/` folder."""
    out = set()
    if kind == 'from_object':
        parts = [x for x in re.split(r'[.:]', value) if x]
        if not parts or not all(_IDENT.fullmatch(x) for x in parts):
            return out
        for d in dirs:
            for k in range(1, len(parts) + 1):
                base = posixpath.join(d, *parts[:k])
                out.update((base + '.py', base + '/__init__.py'))
        return out
    name = value.replace('\\', '/')
    if not name or name.startswith('/') or re.match(r'^[A-Za-z]:/', name):
        return out
    for d in dirs:
        for base in (d, posixpath.join(d, 'instance')):
            rel = posixpath.normpath(posixpath.join(base, name))
            if rel != '..' and not rel.startswith('../'):
                out.add(rel)
    return out


def send_bound(top, cap):
    """The `Bound` of the checkout's declaration, or None to read the checkout as before."""
    doc = _declaration(top, cap)
    roots = _roots(doc.get('app_roots')) if doc is not None else None
    if roots is None:
        return None
    # #3882 night read HIGH-1 (release 471af432 held, 18 Oct 2026): the checker's rule 15(b) decides
    # `from_object(<factory parameter>)` from every call site of a declared factory, anywhere in the repository; a
    # bounded send would withhold those in sibling directories (tests/conftest.py) and read the load as resolved where
    # the wide read refuses it. Until the send keeps a factory's call sites, a declared factory reads the checkout wide.
    objs = doc.get('app_objects')
    if isinstance(objs, list) and any(isinstance(o, dict) and o.get('factory') for o in objs):
        return None
    resource = doc.get('resource_roots')
    resource = [r for r in resource if isinstance(r, str)] if isinstance(resource, list) else []
    if any(not [p for p in r.strip().replace('\\', '/').split('/') if p not in ('', '.')] for r in resource):
        return None                           # a `.` resource root: the whole checkout
    resource_roots = _roots(resource) or []
    named = set()
    for text in _strings(doc):
        text = text.strip()
        m = _LOCATOR.fullmatch(text)
        if m and '..' not in m.group(1).split('/'):
            named.add(m.group(1).lstrip('./') if m.group(1).startswith('./') else m.group(1))
        elif _DOTTED.fullmatch(text):
            parts = text.split('.')
            for k in range(1, len(parts) + 1):
                base = '/'.join(parts[:k])
                named.update((base + '.py', base + '/__init__.py'))
    return Bound(roots, resource_roots or [], named)


def bound_line(top, files, cap):
    """The log line of a bounded checkout read (`files` as sent), or None when the read was not bounded."""
    b = send_bound(top, cap)
    if b is None:
        return None
    sent = [n[len(PREFIX):] for n in files if n.startswith(PREFIX) and n.endswith('.py')]
    inside = sum(1 for rel in sent if b.under(rel))
    return ('Assure: read %d Python file(s) under app_roots %s and %d the checker loads by name outside them, from %s'
            % (inside, json.dumps(b.roots), len(sent) - inside, CHECKOUT_DECLARATION))


def _under(rel, roots):
    return any(rel == r or rel.startswith(r + '/') for r in roots)


REQUEST_OVERHEAD = 4096       # the body's other keys (profile, the declaration's name, commit, ...), at least this


def _encoded(name, size):
    """Bytes `name` and `size` bytes of content take in the request body (`serve.bundle.request_body`):
    `"<name>":"<base64>",`, plus the file's row in `raw/REPOSITORY.json` (path, bytes, sha256, mode), base64 too."""
    row = len(name.encode('utf-8')) + 150
    return len(name.encode('utf-8')) + 4 * ((size + 2) // 3) + 6 + 4 * ((row + 2) // 3)


def _declared_stack(data):
    """#3840: the `stack` of a raw/declaration.json of schema assure.identity.declaration/v1 (FastAPI, Django,
    standard-library http.server), else None. That form's raw/REPOSITORY.json carries the declaration's sha256 as
    `declaration_sha256` (QUICKSTART-API section 15), one derived value; a Flask declaration's manifest is unchanged."""
    try:
        doc = json.loads(bytes(data).decode('utf-8'))
    except (TypeError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get('schema') != IDENTITY_SCHEMA or not isinstance(doc.get('stack'), str):
        return None
    return doc['stack']

def from_checkout(top, allow, limits, env):
    """serve-102 (DD-156 item 3, one step): the repository read from the checkout itself, when profile python-auth is
    given neither artefacts nor a connection. Every tracked regular file at HEAD's index (`git ls-files -s -z`, read
    only) that is Python source or requirements.md becomes `raw/repository/<path>`; other tracked files are not read.
    Issue #3841: with `app_roots` in the checkout's `.assure/declaration.json`, only the Python files under those roots
    are sent, with what the checker loads by name outside them (`Bound`). When the files to send would encode past
    `limits.body_bytes`, `oversize_input` names the encoded size, the limit and `app_roots` before any file is sent;
    with `app_roots`, the kept modules are parsed first for config loaded by name (`Bound.config_loads`).
    Returns (bundle.Collected, {path: git mode}). A name the profile does not admit is listed in `ignored`."""
    from serve import bundle
    child_env = {k: env[k] for k in ('PATH', 'HOME', 'SYSTEMROOT') if env.get(k)}
    child_env.setdefault('PATH', '/usr/bin:/bin')
    try:
        p = subprocess.run(['git', '-C', str(top), 'ls-files', '-s', '-z'], env=child_env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        p = None
    if p is None or p.returncode != 0:
        raise Refusal('bad_input', 'profile %s with neither artefacts nor connection reads the checkout: run '
                      'actions/checkout before this step' % PROFILE)
    bound = send_bound(top, limits.file_bytes)
    roots = bound.roots if bound is not None else None
    if bound is not None:
        tracked = []
        for row in p.stdout.split(b'\0'):
            try:
                tracked.append(row.partition(b'\t')[2].decode('utf-8'))
            except UnicodeDecodeError:
                continue
        bound.resolve(tracked).config_loads(top, tracked, limits.file_bytes)
    out, modes, chosen, encoded, locks = bundle.Collected(), {}, [], REQUEST_OVERHEAD, []
    for row in p.stdout.split(b'\0'):
        if not row:
            continue
        meta, _tab, path = row.partition(b'\t')
        mode = meta.split(b' ', 1)[0].decode('ascii', 'replace')
        try:
            rel = path.decode('utf-8')
        except UnicodeDecodeError:
            continue
        if mode in ('100644', '100755') and is_dependency_file(rel):
            locks.append(rel)                    # issue #3128: read here for the derived record, never sent
        if mode not in ('100644', '100755') or not (rel.endswith('.py') or rel == 'requirements.md'):
            continue
        if bound is not None and not bound.keeps(rel):
            continue
        name = PREFIX + rel
        try:
            bundle.check_name(name, allow)
        except Refusal:
            out.ignored.append(name)
            continue
        full = Path(top) / rel
        try:
            st = os.lstat(full)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        cap = limits.file_bytes
        if st.st_size > cap:
            raise Refusal('oversize_input', '%s is %d bytes; the limit is %d' % (name, st.st_size, cap))
        chosen.append((name, rel, mode, full))
        encoded += _encoded(name, st.st_size)
    if encoded > limits.body_bytes:
        python = sum(1 for _n, rel, _m, _f in chosen if rel != 'requirements.md')
        if roots is None:
            raise Refusal('oversize_input', 'the checkout holds %d tracked Python files that encode to %d bytes; the '
                          'limit is %d bytes: name the directories your app runs from in app_roots in %s (for example '
                          '"app_roots": ["app"]) and only the files under them are sent'
                          % (python, encoded, limits.body_bytes, CHECKOUT_DECLARATION))
        raise Refusal('oversize_input', 'the %d tracked Python files the read selects (under app_roots %s, and those the '
                      'checker loads by name outside them) encode to %d bytes; the limit is '
                      '%d bytes: narrow app_roots in %s to the directories your app runs from'
                      % (python, json.dumps(roots), encoded, limits.body_bytes, CHECKOUT_DECLARATION))
    for name, rel, mode, full in chosen:
        out.files[name] = full.read_bytes()
        modes[rel] = mode
    read = {}
    for rel in locks:
        full = Path(top) / rel
        try:
            st = os.lstat(full)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) and st.st_size <= LOCK_FILE_BYTES:
            read[rel] = full.read_bytes()
    record = library_versions(read)
    if record:
        out.files[LIBRARY_VERSIONS] = library_versions_bytes(record)
    out.ignored.sort()
    return out, modes

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
