"""Bounded customer input (DESIGN-001 section 6). Customer bytes are data: parsed with bounds checked before any object
is built, named only by allow-listed relative paths, and written by this module under the server's scratch directory.

- `parse_json` decodes strict UTF-8, refuses a nesting depth above the cap by scanning the text before the parser runs,
  refuses duplicate keys, NaN/Infinity and a number that overflows to infinity (such as 1e999).
- `from_directory` reads an artefacts directory: raw/ and, as the collector lays it out, COLLECTION-SIDECAR.json and
  TIMING.json beside raw/ (submitted under raw/; a differing copy inside raw/ is `bad_input`).
- `check_name` admits a name only when it equals a profile path or fully matches a profile pattern, after refusing,
  before any filesystem call, absolute paths, `..`/`.`/empty segments, backslashes, NUL and control characters.
- `check_files` is the one name, cap and required-file check (the API runs it before admission); a name that is also a
  directory on the path of another name is `bad_input`.
- `materialise` checks every name, cap and required file first (`check_files`), then writes with O_CREAT|O_EXCL|O_NOFOLLOW (0600)
  under directories opened with O_NOFOLLOW (0700), so a planted link is never followed.
- `canonical_json` and `dumps` are the canonical encoder (sorted keys, no spaces, UTF-8, finite standard JSON only): the
  same bytes as the engine's own canonical encoder (a test asserts it), defined here so this module imports no engine
  byte.
- `request_body` is the upload `{profile, files: {name: base64}}` the Action sends.

This module imports the standard library and `serve.outcomes` only. It holds no checker, model or engine logic, so the
public Action tree ships it: the runner applies the same bounds the server applies again.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from .outcomes import Refusal

MAX_NAME = 200
# Files the frozen collector writes beside raw/ (its own layout) that the checker contract names under raw/.
BESIDE_RAW = ('COLLECTION-SIDECAR.json', 'TIMING.json')


@dataclass(frozen=True)
class Limits:
    body_bytes: int = 8 * 2 ** 20
    file_bytes: int = 4 * 2 ** 20
    files: int = 64
    json_depth: int = 32


LIMITS = Limits()


@dataclass
class Collected:
    """What `from_directory` found: allow-listed files by name, and the names it ignored. `withheld` holds the counts
    of the Action's withholding pass (action/withhold.py) once it has run, else None."""
    files: dict = field(default_factory=dict)
    ignored: list = field(default_factory=list)
    withheld: dict | None = None


def _depth_ok(text, limit):
    depth, in_string, escaped = 0, False, False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in '[{':
            depth += 1
            if depth > limit:
                return False
        elif ch in ']}':
            depth -= 1
    return True


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('duplicate key %r' % (k[:64],))
        out[k] = v
    return out


def _no_constant(name):
    raise ValueError('non-finite number %s' % name)


def _finite_float(text):
    v = float(text)
    if v != v or v in (float('inf'), float('-inf')):
        raise ValueError('number %s is not finite' % text[:40])
    return v


def parse_json(data, limits=LIMITS):
    """Parse customer JSON bytes under `limits`; `bad_input` or `oversize_input` on any fault."""
    if not isinstance(data, (bytes, bytearray)):
        raise Refusal('bad_input', 'the body is not bytes')
    if len(data) > limits.body_bytes:
        raise Refusal('oversize_input', 'body is %d bytes; the limit is %d' % (len(data), limits.body_bytes))
    try:
        text = bytes(data).decode('utf-8')
    except UnicodeDecodeError:
        raise Refusal('bad_input', 'the body is not UTF-8') from None
    if not _depth_ok(text, limits.json_depth):
        raise Refusal('oversize_input', 'JSON nesting is deeper than %d' % limits.json_depth)
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant, parse_float=_finite_float)
    except (ValueError, RecursionError) as e:
        raise Refusal('bad_input', 'malformed JSON: %s' % (str(e)[:200],)) from None


def _rule_for(name, profile):
    for rule in tuple(profile.required) + tuple(profile.optional):
        if rule.matches(name):
            return rule
    return None


def check_name(name, profile):
    """Return `name` when it is a safe relative POSIX path on the profile's allow-list; else `bad_input`."""
    if not isinstance(name, str):
        raise Refusal('bad_input', 'a file name is not a string')
    shown = name[:80].encode('unicode_escape').decode('ascii')
    if not name or len(name) > MAX_NAME:
        raise Refusal('bad_input', 'file name empty or longer than %d characters' % MAX_NAME)
    if any(ord(c) < 32 or ord(c) == 127 or 0x80 <= ord(c) < 0xa0 for c in name):
        raise Refusal('bad_input', 'file name holds a control character: %s' % shown)
    if '\\' in name or name.startswith('/'):
        raise Refusal('bad_input', 'file name is absolute or holds a backslash: %s' % shown)
    if any(seg in ('', '.', '..') for seg in name.split('/')):
        raise Refusal('bad_input', 'file name has an empty, "." or ".." segment: %s' % shown)
    if _rule_for(name, profile) is None:
        raise Refusal('bad_input', 'file name is not accepted by profile %s: %s' % (profile.id, shown))
    return name


def from_request(body, limits=LIMITS):
    """Parse an API body `{profile, files: {name: base64}}` into (profile_id, {name: bytes}). Names are checked later,
    against the profile, by `materialise`."""
    doc = parse_json(body, limits)
    if not isinstance(doc, dict) or set(doc) != {'profile', 'files'}:
        raise Refusal('bad_input', 'the body must be an object with exactly the keys profile and files')
    profile_id, enc = doc['profile'], doc['files']
    if not isinstance(profile_id, str) or not isinstance(enc, dict):
        raise Refusal('bad_input', 'profile must be a string and files an object')
    if len(enc) > limits.files:
        raise Refusal('oversize_input', '%d files; the limit is %d' % (len(enc), limits.files))
    files = {}
    for name, value in enc.items():
        if not isinstance(value, str):
            raise Refusal('bad_input', 'a file value is not a base64 string')
        if len(value) // 4 * 3 > limits.file_bytes + 2:
            raise Refusal('oversize_input', 'a file is larger than %d bytes' % limits.file_bytes)
        try:
            data = base64.b64decode(value.encode('ascii'), validate=True)
        except (binascii.Error, ValueError, UnicodeEncodeError):
            raise Refusal('bad_input', 'a file value is not strict base64') from None
        if len(data) > limits.file_bytes:
            raise Refusal('oversize_input', 'a file is larger than %d bytes' % limits.file_bytes)
        files[name] = data
    return profile_id, files


def _read_capped(path, cap):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Refusal('bad_input', 'not a regular file')
        chunks, total = [], 0
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            total += len(b)
            if total > cap:
                raise Refusal('oversize_input', 'a file grew past its cap while being read')
            chunks.append(b)
        return b''.join(chunks)
    finally:
        os.close(fd)


def from_directory(root, profile, limits=LIMITS):
    """Collect allow-listed files from `root` (a directory holding `raw/`, or the `raw` directory itself). Links are
    never followed: a symlink or non-regular file at an allow-listed name is `bad_input`; unlisted names are ignored and
    reported. Sizes are checked from lstat before any byte is read. COLLECTION-SIDECAR.json and TIMING.json beside
    `raw/` (where the frozen collector writes them) are taken as raw/COLLECTION-SIDECAR.json and raw/TIMING.json."""
    root = Path(root)
    raw = None
    for cand in (root / 'raw', root):
        try:
            st = os.lstat(cand)
        except FileNotFoundError:
            continue
        if cand is root and root.name != 'raw':
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise Refusal('bad_input', 'the raw directory is a link or not a directory')
        raw = cand
        break
    if raw is None:
        raise Refusal('bad_input', 'no raw/ directory under the artefacts path')
    out = Collected()
    walk_errors = []
    for dirpath, dirnames, filenames in os.walk(raw, followlinks=False, onerror=walk_errors.append):
        dirnames.sort()
        # A real directory is walked into, never matched or reported; a link to a directory is an entry like a file.
        linked = [d for d in dirnames if os.path.islink(Path(dirpath) / d)]
        for entry in sorted(linked + filenames):
            full = Path(dirpath) / entry
            name = 'raw/' + full.relative_to(raw).as_posix()
            rule = _rule_for(name, profile)
            if rule is None:
                out.ignored.append(name)
                continue
            check_name(name, profile)
            st = os.lstat(full)
            if not stat.S_ISREG(st.st_mode):
                raise Refusal('bad_input', '%s is a link or not a regular file' % name)
            cap = min(rule.max_bytes, limits.file_bytes)
            if st.st_size > cap:
                raise Refusal('oversize_input', '%s is %d bytes; the limit is %d' % (name, st.st_size, cap))
            if len(out.files) >= limits.files:
                raise Refusal('oversize_input', 'more than %d files' % limits.files)
            out.files[name] = _read_capped(full, cap)
    if walk_errors:
        raise Refusal('bad_input', 'a directory under raw/ cannot be listed')
    _beside(raw.parent, profile, limits, out)
    out.ignored.sort()
    return out


def _beside(parent, profile, limits, out):
    """The collector writes COLLECTION-SIDECAR.json and TIMING.json beside raw/, not inside it: take each one found
    there (a regular file, never a link) under the name the profile lists, raw/<name>. A copy inside raw/ that differs
    from the one beside it is `bad_input`: which one belongs to the collection cannot be told."""
    for base in BESIDE_RAW:
        name = 'raw/' + base
        rule = _rule_for(name, profile)
        if rule is None:
            continue
        src = Path(parent) / base
        try:
            st = os.lstat(src)
        except FileNotFoundError:
            continue
        except OSError:
            raise Refusal('bad_input', '%s beside raw/ cannot be read' % base) from None
        if not stat.S_ISREG(st.st_mode):
            raise Refusal('bad_input', '%s beside raw/ is a link or not a regular file' % base)
        cap = min(rule.max_bytes, limits.file_bytes)
        if st.st_size > cap:
            raise Refusal('oversize_input', '%s beside raw/ is %d bytes; the limit is %d' % (base, st.st_size, cap))
        data = _read_capped(src, cap)
        if name in out.files:
            if out.files[name] != data:
                raise Refusal('bad_input', '%s beside raw/ and %s inside it differ; keep the one the collector wrote '
                              'with this output' % (base, name), path=name)
            continue
        if len(out.files) >= limits.files:
            raise Refusal('oversize_input', 'more than %d files' % limits.files)
        out.files[name] = data


def check_files(files, profile, limits=LIMITS):
    """The one check of a file set against a profile: a mapping of at most `limits.files` names, each name on the
    allow-list (`check_name`), each content bytes within its rule's cap and the file cap, the total within the body cap,
    and every required file present. Returns the total bytes. `bad_input` or `oversize_input` on the first fault. The API
    runs it before admission (so a refused request is never charged); `materialise` runs it before writing anything."""
    if not isinstance(files, dict):
        raise Refusal('bad_input', 'files must be a mapping of name to bytes')
    if len(files) > limits.files:
        raise Refusal('oversize_input', '%d files; the limit is %d' % (len(files), limits.files))
    total = 0
    names = set(files)
    for name, data in files.items():
        check_name(name, profile)
        parts = name.split('/')
        for i in range(1, len(parts)):
            if '/'.join(parts[:i]) in names:
                raise Refusal('bad_input', '%s is a file and also a directory on the path of %s'
                              % ('/'.join(parts[:i]), name))
        if not isinstance(data, (bytes, bytearray)):
            raise Refusal('bad_input', 'the content of %s is not bytes' % name)
        cap = min(_rule_for(name, profile).max_bytes, limits.file_bytes)
        if len(data) > cap:
            raise Refusal('oversize_input', '%s is %d bytes; the limit is %d' % (name, len(data), cap))
        total += len(data)
    if total > limits.body_bytes:
        raise Refusal('oversize_input', 'the files total %d bytes; the limit is %d' % (total, limits.body_bytes))
    for rule in profile.required:
        if rule.path not in files:
            raise Refusal('bad_input', 'missing required file %s' % rule.path, path=rule.path)
    return total


def _open_dir(parent_fd, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise Refusal('bad_input', 'a directory in the scratch tree is not a directory')
    return fd


def materialise(files, profile, work_dir, limits=LIMITS):
    """Check, then write `files` under `work_dir`; return the manifest [{path, bytes, sha256}] sorted by path."""
    check_files(files, profile, limits)
    manifest = []
    root_fd = os.open(str(work_dir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in sorted(files):
            data = bytes(files[name])
            parts = name.split('/')
            fds = [root_fd]
            try:
                for d in parts[:-1]:
                    fds.append(_open_dir(fds[-1], d))
                try:
                    fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fds[-1])
                except FileExistsError:
                    raise Refusal('bad_input', '%s names a file that already exists (two names for one file)' % name) from None
                try:
                    os.fchmod(fd, 0o600)
                    view = memoryview(data)
                    while view:
                        n = os.write(fd, view)
                        view = view[n:]
                finally:
                    os.close(fd)
            finally:
                for fd_ in fds[1:]:
                    os.close(fd_)
            manifest.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    finally:
        os.close(root_fd)
    return manifest


def bundle_sha256(manifest):
    """sha256 of the canonical JSON of a manifest."""
    return hashlib.sha256(canonical_json(manifest)).hexdigest()


# ---------- canonical JSON (byte-identical to the engine's canonical encoder) ----------
class CanonicalError(ValueError):
    """A value that is not finite, standard JSON."""


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise CanonicalError('Only finite, standard JSON metadata is admitted')


def canonical_json(value):
    """Sorted keys, no spaces, UTF-8, finite standard JSON only; CanonicalError (a ValueError) otherwise."""
    _json_value(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise CanonicalError('Invalid canonical JSON') from exc


def dumps(obj):
    """Canonical JSON plus one newline: the bytes of a verdict file and of every API answer."""
    return canonical_json(obj) + b'\n'


def request_body(profile_id, files, limits=LIMITS):
    """The upload body `{profile, files: {name: base64}}`; `oversize_input` when the encoded body passes the body cap."""
    body = json.dumps({'profile': profile_id,
                       'files': {n: base64.b64encode(bytes(files[n])).decode('ascii') for n in sorted(files)}},
                      sort_keys=True, separators=(',', ':')).encode('ascii')
    if len(body) > limits.body_bytes:
        raise Refusal('oversize_input', 'the encoded upload is %d bytes; the limit is %d' % (len(body), limits.body_bytes))
    return body

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
