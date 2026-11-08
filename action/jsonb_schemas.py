"""Collect committed schema bytes from this repository's HEAD; never read worktree schema contents.

Issue #6339 (trial-lead 23162): the Action calls `collect` only under the rf34 opt-in the collector's --jsonb-schema is
given for. On a pull request it reads the event's `pull_request.head.sha` (only when the checkout holds it; nothing
is fetched), not the merge commit the checkout is at, and
`on_base` compares the files with the base branch as the declaration is compared. The checkout must be the
repository's top level: a schema directory is never resolved against another root, so a checkout under another path
sends no inventory and the row reads not established.
"""
import hashlib
import json
import os
from pathlib import Path
import re

from action.declaration_draft import _fetch, _git as _run_git


def _path(path):
    # #6450 (trial-lead 26245): a directory named like a sealed set is customer source here; the checker row refuses it
    return isinstance(path, str) and all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p)
        and not p.startswith('.env') and p.lower() != 'auth'
        and 'credential' not in p.lower() for p in path.split('/'))


class MissingCommit(ValueError):
    """The checkout does not hold the commit the inventory is read at (trial-lead 23457/23493: nothing is fetched)."""

    def __init__(self, commit):
        super().__init__('the checkout does not hold commit %s; the schema inventory is not read' % commit)
        self.commit = commit


def _git(repository, env):
    def git(*args):
        out = _run_git(repository, env, *args)       # rev-parse, ls-tree and cat-file only; None on any fault
        if out is None:
            raise ValueError('the schema inventory could not be read from git')
        return out
    return git


def _files(git, commit, directory):
    paths = git('ls-tree', '-r', '-z', commit, '--', directory).split(b'\0')
    files = []
    for entry in paths:
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        path = path.decode('utf-8')
        if not _path(path) or not path.endswith('.json') or not path.startswith(directory + '/'):
            continue
        mode, kind, oid = meta.decode().split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('schema inventory requires committed regular files')
        content = git('cat-file', 'blob', oid)
        if len(content) > 1048576 or len(files) >= 512:
            raise ValueError('schema inventory exceeds supported bounds')
        files.append({'path': path, 'content': content.decode('utf-8'), 'sha256': hashlib.sha256(content).hexdigest()})
    return files


def _commit(repository, env, git, rev):
    """`rev` as a commit id, only when the checkout already holds it. Nothing is fetched (trial-lead 23457 (a)): a
    pull request head the checkout lacks sends no inventory, and the row reads not established and names the
    inventory to provide."""
    got = _run_git(repository, env, 'rev-parse', '--verify', '--quiet', rev + '^{commit}')
    if got is None:
        raise MissingCommit(rev)
    return got.decode().strip()


def collect(repository, raw, directory, env=None, commit='HEAD'):
    if not _path(directory):
        raise ValueError('provide a repository-relative JSON Schema directory')
    env = os.environ if env is None else env
    git = _git(repository, env)
    top = git('rev-parse', '--show-toplevel').decode('utf-8').strip()
    if Path(top).resolve() != Path(repository).resolve():
        raise ValueError('the schema inventory reads only a checkout at the repository top level')
    commit = _commit(repository, env, git, commit)
    files = _files(git, commit, directory)
    doc = {'schema': 'assure.jsonb-schema-repository/v1', 'commit': commit, 'directory': directory, 'files': files}
    data = json.dumps(doc, sort_keys=True, indent=2).encode()
    if len(data) > 4194304:
        raise ValueError('schema inventory exceeds supported bounds')
    target = Path(raw) / 'jsonb_schema_repository.json'
    with target.open('xb') as out:
        out.write(data)
    return doc


def on_base(repository, doc, env):
    """On a pull request: does the base branch carry exactly the inventory's files under its directory (the same
    paths and sha256)? None when it cannot be read (`declaration_draft.on_base`, for the schema files)."""
    base = str(env.get('GITHUB_BASE_REF') or '').strip()
    if not base or not _fetch(repository, env, base):
        return None
    try:
        files = _files(_git(repository, env), 'FETCH_HEAD', doc['directory'])
    except (KeyError, TypeError, ValueError):
        return None
    return [(f['path'], f['sha256']) for f in files] == [(f['path'], f['sha256']) for f in doc['files']]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='.')
    parser.add_argument('--raw', required=True)
    parser.add_argument('--schema-directory', required=True)
    args = parser.parse_args()
    collect(Path(args.repository), Path(args.raw), args.schema_directory)
