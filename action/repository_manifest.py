"""The repository manifest `raw/REPOSITORY.json`, computed in the runner (serve-099; issue #322).

For profile python-auth-declared-model the bundle carries `raw/REPOSITORY.json`: `schema`
(assure.codeauth.repository/v1), `commit` (40 hex), `tree` (the git tree id of the exact file set sent), one
`{path, bytes, sha256, mode}` row per `raw/repository/<path>` file sent, and the seven flags. Everything in it is
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

Standard library, `serve` (the seven flags) and serve.outcomes only; the one child process is that read-only git command.
execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false."""
from __future__ import annotations

import hashlib
import json
import os
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
_HEX40 = re.compile(r'[0-9a-f]{40}')
GIT_TIMEOUT_S = 30


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


def manifest(files, root, commit):
    """The manifest document for the `raw/repository/` files in `files` ({name: bytes}) read from `root`."""
    base = raw_dir(root) / 'repository'
    rows, entries = [], {}
    for name in sorted(n for n in files if n.startswith(PREFIX)):
        rel = name[len(PREFIX):]
        data = bytes(files[name])
        try:
            st = os.lstat(base / rel)
            mode = '100755' if stat.S_ISREG(st.st_mode) and st.st_mode & stat.S_IXUSR else '100644'
        except OSError:
            mode = '100644'
        rows.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode})
        entries[rel] = (mode, git_blob_id(data))
    return {'schema': SCHEMA, 'commit': commit, 'tree': git_tree_id(entries), 'files': rows, **FLAGS}


def complete(collected, profile, root, env):
    """Add `raw/REPOSITORY.json` to `collected.files` when `profile` is python-auth and none was supplied. Returns the
    document written, or None when nothing was added."""
    if profile != PROFILE or NAME in collected.files:
        return None
    commit = head_commit(root, env)
    if commit is None:
        raise Refusal('bad_input', '%s is not in the artefacts and the commit could not be read: run actions/checkout '
                      'before this step so the artefacts directory is inside the git checkout, or send %s yourself'
                      % (NAME, NAME), path=NAME)
    doc = manifest(collected.files, root, commit)
    collected.files[NAME] = (json.dumps(doc, indent=1, sort_keys=True) + '\n').encode('utf-8')
    return doc

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
