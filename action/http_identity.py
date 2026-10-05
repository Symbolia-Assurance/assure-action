"""The HTTP identity producer in the customer's runner (serve-012), for a profile whose `GET /v1/profiles` listing names
the `identity_binding` binding record (http-observed-baseline).

Before anything is collected the Action makes one 32-byte key for this job in memory (`secrets.token_bytes`), and:
1. runs the identity producer, `action_identity_fixture.py --fixture-dir <the caller's endpoint manifest directory>
   --out <scratch>/identity-scope.json --identity-key-fd <fd> --identity-key-id <label>`: the producer's own interface,
   which reads the key from the named descriptor only, a fresh nonblocking pipe holding exactly the 32 bytes and EOF.
   It reads the caller's manifest (never a response file) and writes {endpoint_tokens, identity_binding};
2. runs the collector over the same manifest with the same key on a second fresh pipe, `collector/collect_http.py
   --fixture-dir ... --out <scratch>/bundle --identity-key-fd <fd> --identity-key-id <label>`;
3. drops the key. The producer's record goes to the API as the wrapped `scope_binding` ({endpoint_tokens, identity_binding})
   and its ids as `scope`; the bundle is the upload.

The key never reaches an argument, an environment variable or a file the Action writes; the children run with `-I -B`
and an environment of PATH alone; nothing persists between runs (the scratch directory is removed by the caller). A
fresh key each job is fine while no accepted scope exists (the API refuses accepted_scope_ref): a later comparison with
an accepted scope needs a key held across runs.

The three files run from `action/http/` in the public Action tree (build_dist copies them byte for byte from the
checker's tree) or from `assure/checkers/http-observed-baseline/` in a source checkout; each is re-hashed against
FILES before it runs, every path component refused if it is a link. A child's refusal is shown by its closed code only.

This module imports the standard library and serve.outcomes only."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

from serve.outcomes import Refusal, malformation

RECORD = 'identity_binding'
KEY_SOURCE = 'pipe'
KEY_BYTES = 32
KEY_ID = 'action-job-key'
SHIPPED_DIR = 'action/http'
SOURCE_DIR = 'assure/checkers/http-observed-baseline'
PRODUCER = 'action_identity_fixture.py'
COLLECTOR = 'collector/collect_http.py'
#: the producer, the scope helper it verifies and the collector, at the checker entry's listed digests
FILES = {
    'action_identity_fixture.py': '5348fa3d66b24a2611bf4116fc5c963f52461e652ab69a9366398cb1debe5916',
    'scope_binding.py': '64889563b2b974c736dab5f45f66c9cf1be464a9a16e81cb17e3508f2220be8c',
    'collector/collect_http.py': '916af00b93b49df84fc2e186e95b8d184fc93917a06696bed5c7f4aa394cae9b',
}
SCOPE_FILE = 'identity-scope.json'
MAX_SCOPE_BYTES = 65536
TIMEOUT_S = 60
_CODE = re.compile(r'[A-Z][A-Z0-9-]{0,63}')
# Codes a child gives for the caller's manifest or response files: the customer's to fix (bad_input). Any other code
# (a package digest, the key pipe, the output, an internal fault) is the Action's own fault.
CUSTOMER_CODES = frozenset({'MANIFEST-INVALID', 'SCOPE-INTEGRITY-FAULT', 'IDENTITY-BINDING-INVALID', 'PATH-ESCAPE',
                            'SOURCE-MISSING', 'ENDPOINT-INVALID', 'SCOPE-INVALID'})


def declares_identity(allow):
    """True when the API's listing of the profile names the identity_binding record."""
    scope = getattr(allow, 'scope', None) or {}
    return RECORD in (scope.get('records') or ())


def parse_key_source(text):
    """The `identity-key` input: empty or `pipe` (a fresh per-job key on a pipe). Anything else is bad_input; the
    caller has already masked the value, which may be a pasted key."""
    v = (text or '').strip()
    if v in ('', KEY_SOURCE):
        return KEY_SOURCE
    raise Refusal('bad_input', 'identity-key takes only pipe: the Action makes a fresh key for each job and passes it to '
                               'the identity producer on a pipe; never paste a key into an input',
                  malformation=malformation('scope_binding', field='scope_binding'))


def _verified_dir(root):
    """The directory holding the three files, each re-hashed against FILES, no link on any component below root."""
    for rel_dir in (SHIPPED_DIR, SOURCE_DIR):
        base = Path(root) / rel_dir
        if not os.path.isdir(base):
            continue
        for rel, digest in FILES.items():
            cur = Path(root)
            for part in (rel_dir + '/' + rel).split('/'):
                cur = cur / part
                try:
                    st = os.lstat(cur)
                except OSError:
                    raise _mismatch(rel, 'missing') from None
                if stat.S_ISLNK(st.st_mode):
                    raise _mismatch(rel, 'a symbolic link')
            if not stat.S_ISREG(st.st_mode) or hashlib.sha256(cur.read_bytes()).hexdigest() != digest:
                raise _mismatch(rel, 'digest differs')
        return base
    raise _mismatch('', 'the identity producer is missing')


def _mismatch(rel, why):
    return Refusal('engine_digest_mismatch', 'http identity/%s (%s)' % (rel, why), path='http/' + rel)


def _child(command, key, cwd, run):
    """One child with `key` on a fresh nonblocking pipe named by --identity-key-fd; (returncode, stdout, stderr)."""
    reader, writer = os.pipe()
    try:
        os.set_blocking(reader, False)
        view = memoryview(key)
        while view:
            view = view[os.write(writer, view):]
        os.close(writer)
        writer = None
        try:
            done = run([sys.executable, '-I', '-B', *map(str, command), '--identity-key-fd', str(reader),
                        '--identity-key-id', KEY_ID], pass_fds=(reader,), capture_output=True, timeout=TIMEOUT_S,
                       cwd=str(cwd), env={'PATH': os.defpath}, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise Refusal('checker_error', 'the HTTP identity producer ran past its %d s limit' % TIMEOUT_S) from None
        return done.returncode, done.stdout or b'', done.stderr or b''
    finally:
        os.close(reader)
        if writer is not None:
            os.close(writer)


def _refused(what, code):
    code = code if isinstance(code, str) and _CODE.fullmatch(code) else 'UNKNOWN'
    if code in CUSTOMER_CODES:
        return Refusal('bad_input', 'the %s refused the endpoint manifest: %s' % (what, code),
                       malformation=malformation('scope_binding', field='scope_binding'))
    return Refusal('checker_error', 'the %s failed: %s' % (what, code))


def _producer_code(stderr):
    m = re.fullmatch(rb'HTTP identity producer refused: ([A-Z0-9-]{1,64})\n?', stderr)
    return m.group(1).decode('ascii') if m else None


def _collector_code(stdout):
    try:
        doc = json.loads(stdout.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return None
    return doc.get('code') if isinstance(doc, dict) else None


def new_key():
    """This job's key: KEY_BYTES random bytes, in memory only."""
    return bytearray(secrets.token_bytes(KEY_BYTES))


def produce_and_collect(root, manifest_dir, scratch, *, scope=None, run=None):
    """Steps 1-3 of the module docstring: (bundle directory, wrapped scope_binding). `manifest_dir` holds the caller's
    manifest.json and the response heads it names; `scratch` is this job's 0700 directory. A `scope` input (a list of
    ids) must equal the ids the producer bound, checked before the collector runs. `run` is a test seam."""
    run = run if run is not None else subprocess.run
    base = _verified_dir(root)
    scratch = Path(scratch)
    out = scratch / SCOPE_FILE
    key = new_key()
    try:
        rc, stdout, stderr = _child([base / PRODUCER, '--fixture-dir', manifest_dir, '--out', out], bytes(key), scratch,
                                    run)
        if rc != 0:
            raise _refused('HTTP identity producer', _producer_code(stderr))
        try:
            with open(out, 'rb') as fh:
                data = fh.read(MAX_SCOPE_BYTES + 1)
            binding = json.loads(data.decode('utf-8'))
        except (OSError, UnicodeDecodeError, ValueError):
            raise Refusal('checker_error', 'the HTTP identity producer wrote no readable record') from None
        if (len(data) > MAX_SCOPE_BYTES or not isinstance(binding, dict)
                or set(binding) != {'endpoint_tokens', RECORD} or not isinstance(binding['endpoint_tokens'], dict)):
            raise Refusal('checker_error', 'the HTTP identity producer wrote a record of another shape')
        if scope is not None and (not isinstance(scope, list) or sorted(scope) != sorted(binding['endpoint_tokens'])):
            raise Refusal('bad_input', 'scope must list exactly the endpoint ids of the endpoint manifest; leave it '
                                       'empty to check every endpoint the manifest names',
                          malformation=malformation('scope_missing'))
        _verified_dir(root)                       # the collector's bytes, again, just before it runs
        bundle = scratch / 'bundle'
        rc, stdout, stderr = _child([base / COLLECTOR, '--fixture-dir', manifest_dir, '--out', bundle], bytes(key),
                                    scratch, run)
        if rc != 0:
            raise _refused('HTTP collector', _collector_code(stdout))
        return bundle, binding
    finally:
        for i in range(len(key)):
            key[i] = 0
        del key

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
