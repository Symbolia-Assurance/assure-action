"""Run the frozen read-only collector in the customer's runner (SERVE-001 U2; DESIGN-001 section 3).

- `parse_connection(text)`: a bounded parser for the `connection` input, a libpq keyword/value string or a
  `postgres://`/`postgresql://` URI, into PG* environment variables. Unknown keywords (including `options`, `service` and
  `passfile`), duplicates, control characters and oversize input are `bad_input`; an error never quotes a value.
- `mask_commands`: the `::add-mask::` lines for every secret value, printed before anything else.
- `verify_collector(dir)`: every file of `COLLECTOR-PIN.json` re-hashed, links refused, and the pinned `collect_pg.py`
  equal to the frozen digest. Any difference is `engine_digest_mismatch`.
- `check_config_dirs(text)`: the `config-dirs` input (line-break or colon separated directories holding configuration
  files outside the data directory) as resolved paths; each becomes one `--extra-root` argument item.
- `collect(...)`: runs `collect_pg.py` as a child process with an argument list (never a shell), an explicit minimal
  environment (PATH, LC_ALL, PGAPPNAME, PGCONNECT_TIMEOUT and the parsed PG* variables; the collector adds PGOPTIONS
  itself), stdin closed, its own process group and a wall clock. Its output is captured to files, read bounded, and never
  echoed: only a typed outcome with a bounded, sanitised reason leaves this module. Exit 0 or 1: collected (gaps become
  `not observed` readings); exit 3: REFUSAL.json gives `collector_refused`, or `collector_cannot_connect` when the first
  query could not reach the server; exit 2 or anything else: `checker_error`. The collector's `out/raw/*`,
  `out/COLLECTION-SIDECAR.json` and `out/TIMING.json` become `raw/...` names loaded through `bundle.from_directory`, so the
  bounds of an artefacts directory apply. Then `action/withhold.py` withholds every configuration comment and every
  string literal in the policy expressions (refutation 002, TC-1 and TC-2), before anything else reads the bytes.

The collector's `--psql` command is this file in `--psql-shim` mode in front of the resolved psql: it appends one line to
a progress file and then replaces itself with psql, so on a wall-clock expiry the Action knows whether the collector was
still on its first query (cannot connect) or later (timeout). The shim reads and changes nothing else.
"""
from __future__ import annotations

import os
import sys


def _psql_shim(argv):
    """`collect.py --psql-shim <progress file> -- <psql> <args...>`: count the query, then exec psql unchanged."""
    if len(argv) < 3 or argv[1] != '--':
        os.write(2, b'assure psql shim: bad arguments\n')
        return 2
    try:
        fd = os.open(argv[0], os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            os.write(fd, b'q\n')
        finally:
            os.close(fd)
    except OSError:
        pass
    try:
        os.execv(argv[2], argv[2:])
    except OSError:
        os.write(2, b'psql executable not found\n')
        return 127
    return 127


if __name__ == '__main__' and sys.argv[1:2] == ['--psql-shim']:
    sys.exit(_psql_shim(sys.argv[2:]))

import hashlib  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import unquote  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from action import withhold  # noqa: E402
from serve import FLAGS  # noqa: E402
from serve.bundle import LIMITS, from_directory, parse_json  # noqa: E402
from serve.outcomes import Refusal  # noqa: E402

FROZEN_COLLECTOR_SHA256 = '0568f68ee7ef750441b04cd55f4c0a52f9b910599975377a3a123e38d53157c6'
COLLECTOR_DIR = Path(__file__).resolve().parent / 'collector'
COLLECTOR = 'collect_pg.py'
PIN_NAME = 'COLLECTOR-PIN.json'
PIN_SCHEMA = 'assure.serve.collector-pin/v1'
MAX_PIN_BYTES = 64 * 1024
MAX_CONNECTION = 4096
MAX_VALUE = 1024
OUTPUT_CAP = 64 * 1024
REASON_CAP = 300
DEFAULT_TIMEOUT = 300
DEFAULT_CONNECT_TIMEOUT = '10'
APP_NAME = 'assure-action'
DEFAULT_PRIVILEGES = 'pg_read_all_settings,pg_read_all_stats'
READ_ONLY_ROLES = ('pg_read_all_settings', 'pg_read_all_stats', 'pg_stat_scan_tables', 'pg_monitor')
ROLE_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,62}')       # the frozen collector's own --role rule
NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')

# libpq connection keywords this Action accepts, and the environment variable each becomes.
KEYWORDS = {
    'host': 'PGHOST', 'hostaddr': 'PGHOSTADDR', 'port': 'PGPORT', 'dbname': 'PGDATABASE', 'user': 'PGUSER',
    'password': 'PGPASSWORD', 'connect_timeout': 'PGCONNECT_TIMEOUT', 'sslmode': 'PGSSLMODE',
    'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY', 'sslpassword': 'PGSSLPASSWORD',
    'sslcrl': 'PGSSLCRL', 'sslcrldir': 'PGSSLCRLDIR', 'sslsni': 'PGSSLSNI', 'sslnegotiation': 'PGSSLNEGOTIATION',
    'ssl_min_protocol_version': 'PGSSLMINPROTOCOLVERSION', 'ssl_max_protocol_version': 'PGSSLMAXPROTOCOLVERSION',
    'gssencmode': 'PGGSSENCMODE', 'krbsrvname': 'PGKRBSRVNAME', 'channel_binding': 'PGCHANNELBINDING',
    'require_auth': 'PGREQUIREAUTH', 'target_session_attrs': 'PGTARGETSESSIONATTRS',
    'load_balance_hosts': 'PGLOADBALANCEHOSTS',
}
SECRET_KEYWORDS = ('password', 'sslpassword')
HOST_KEYWORDS = ('host', 'hostaddr')
# libpq keywords refused by name: they read other files, change the session, or carry other secrets.
REFUSED_KEYWORDS = frozenset({
    'options', 'service', 'servicefile', 'passfile', 'application_name', 'fallback_application_name', 'replication',
    'client_encoding', 'keepalives', 'keepalives_idle', 'keepalives_interval', 'keepalives_count',
    'tcp_user_timeout', 'sslcompression', 'requirepeer', 'gsslib', 'gssdelegation', 'sslcertmode', 'sslkeylogfile',
    'oauth_issuer', 'oauth_client_id', 'oauth_client_secret', 'oauth_scope', 'scram_client_key', 'scram_server_key'})
TRANSPORT_WORDS = ('could not connect', 'connection', 'timed out', 'timeout', 'not found', 'server closed')
_IDENTITY_PREFIX = 'the collection role row could not be read from pg_roles ('
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_KEY_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_URI_RE = re.compile(r'postgres(?:ql)?://')
_PCT_OK = re.compile(r'%(?![0-9A-Fa-f]{2})')
_IPV4 = re.compile(r'(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])')
_IPV6 = re.compile(r'(?<![\w:])\[?[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){3,7}\]?(?![\w:])')


@dataclass(frozen=True)
class Connection:
    """The parsed connection: PG* variables, the secret values (to mask and scrub), the user and the host values."""
    env: dict = field(default_factory=dict)
    secrets: tuple = ()
    user: str | None = None
    hosts: tuple = ()


def _bad(reason):
    return Refusal('bad_input', 'connection: ' + reason)


def _skip_ws(s, i):
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _parse_keyword_value(s):
    """libpq keyword/value rules: `key = value`, a value single-quoted (with \\' and \\\\) or a run of non-blank
    characters in which a backslash escapes the next character."""
    pairs, i, n = [], 0, len(s)
    while True:
        i = _skip_ws(s, i)
        if i >= n:
            return pairs
        m = _KEY_RE.match(s, i)
        if not m:
            raise _bad('malformed: a keyword was expected (keyword=value pairs, or a postgresql:// URI)')
        key = m.group(0)
        i = _skip_ws(s, m.end())
        if i >= n or s[i] != '=':
            raise _bad('malformed: every keyword needs "=" and a value')
        i = _skip_ws(s, i + 1)
        buf = []
        if i < n and s[i] == "'":
            i += 1
            while True:
                if i >= n:
                    raise _bad('malformed: a quoted value is not closed')
                c = s[i]
                if c == '\\':
                    if i + 1 >= n:
                        raise _bad('malformed: a quoted value ends in a backslash')
                    buf.append(s[i + 1])
                    i += 2
                elif c == "'":
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
        else:
            while i < n and not s[i].isspace():
                if s[i] == '\\':
                    if i + 1 >= n:
                        raise _bad('malformed: a value ends in a backslash')
                    buf.append(s[i + 1])
                    i += 2
                else:
                    buf.append(s[i])
                    i += 1
        pairs.append((key, ''.join(buf), None))


def _decode(text):
    if _PCT_OK.search(text):
        raise _bad('malformed URI: a "%" is not followed by two hexadecimal digits')
    try:
        return unquote(text, errors='strict')
    except UnicodeDecodeError:
        raise _bad('malformed URI: a percent-encoded value is not UTF-8') from None


def _parse_uri(s, m):
    rest = s[m.end():]
    rest, _, query = rest.partition('?')
    authority, _, path = rest.partition('/')
    userinfo, at, hostspec = authority.rpartition('@')
    if not at:
        userinfo, hostspec = '', authority
    pairs = []
    if userinfo:
        user, colon, pw = userinfo.partition(':')
        if user:
            pairs.append(('user', _decode(user), None))
        if colon:
            pairs.append(('password', _decode(pw), pw))
    if hostspec:
        hosts, ports = [], []
        for item in hostspec.split(','):
            if item.startswith('['):
                end = item.find(']')
                if end < 0:
                    raise _bad('malformed URI: an IPv6 address is not closed with "]"')
                host, tail = item[1:end], item[end + 1:]
                if tail and not tail.startswith(':'):
                    raise _bad('malformed URI: unexpected text after an IPv6 address')
                port = tail[1:] if tail else ''
            else:
                host, _, port = item.partition(':')
            hosts.append(_decode(host))
            ports.append(_decode(port))
        if any(hosts):
            pairs.append(('host', ','.join(hosts), None))
        if any(ports):
            pairs.append(('port', ','.join(ports), None))
    if path:
        pairs.append(('dbname', _decode(path), None))
    if query:
        for part in query.split('&'):
            k, eq, v = part.partition('=')
            if not eq or not k:
                raise _bad('malformed URI: every parameter needs "name=value"')
            raw = v if _decode(k) in SECRET_KEYWORDS else None
            pairs.append((_decode(k), _decode(v), raw))
    return pairs


def parse_connection(text):
    """The `connection` input as a Connection; `bad_input` on any fault. No value is ever quoted in a reason."""
    if not isinstance(text, str):
        raise _bad('not text')
    if len(text) > MAX_CONNECTION:
        raise _bad('longer than %d characters' % MAX_CONNECTION)
    if _CONTROL.search(text):
        raise _bad('holds a control character or a line break')
    s = text.strip()
    m = _URI_RE.match(s)
    pairs = _parse_uri(s, m) if m else _parse_keyword_value(s)
    env, secrets, hosts, seen, user = {}, [], [], set(), None
    for key, value, raw in pairs:
        if key in seen:
            raise _bad('a keyword is given twice')
        seen.add(key)
        if key not in KEYWORDS:
            if key in REFUSED_KEYWORDS:
                raise _bad('the keyword %s is not accepted by the Action' % key)
            raise _bad('an unrecognised keyword; accepted: %s' % ', '.join(sorted(KEYWORDS)))
        if _CONTROL.search(value) or len(value) > MAX_VALUE:
            raise _bad('a value holds a control character or is longer than %d characters' % MAX_VALUE)
        if value == '':
            continue
        env[KEYWORDS[key]] = value
        if key in SECRET_KEYWORDS:
            for v in (value, raw):
                if v and v not in secrets:
                    secrets.append(v)
        if key in HOST_KEYWORDS:
            hosts.extend(h for h in value.split(',') if h)
        if key == 'user':
            user = value
    return Connection(env=env, secrets=tuple(secrets), user=user, hosts=tuple(dict.fromkeys(hosts)))


def _cmd_data(value):
    return str(value).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def mask_commands(conn, raw_text=''):
    """`::add-mask::` lines: every secret of a parsed connection, or the whole input when it could not be parsed."""
    values = list(conn.secrets) if conn is not None else ([raw_text.strip()] if raw_text and raw_text.strip() else [])
    return ['::add-mask::' + _cmd_data(v) for v in dict.fromkeys(values) if v]


def child_env(conn, *, path=None):
    """The collector's whole environment: nothing is inherited from the runner but PATH."""
    env = {'PATH': path or '/usr/bin:/bin', 'LC_ALL': 'C', 'PGAPPNAME': APP_NAME,
           'PGCONNECT_TIMEOUT': DEFAULT_CONNECT_TIMEOUT}
    env.update(conn.env if conn is not None else {})
    return env


def sanitise(text, conn=None):
    """One bounded line with every secret, host value and network address of the connection replaced."""
    s = '' if text is None else str(text)
    if conn is not None:
        for secret in sorted(conn.secrets, key=len, reverse=True):
            s = s.replace(secret, '***')
        for host in sorted(conn.hosts, key=len, reverse=True):
            s = re.sub(r'(?<![\w.-])%s(?![\w.-])' % re.escape(host), '<host>', s)
    s = _IPV4.sub('<address>', s)
    s = _IPV6.sub('<address>', s)
    s = _CONTROL.sub(' ', s)
    return s if len(s) <= REASON_CAP else s[:REASON_CAP - 1] + '…'


# ---------- the collector pin ----------
def _mismatch(name, why):
    return Refusal('engine_digest_mismatch', 'collector/%s (%s)' % (name, why), path='collector/' + name)


def _hash_regular(path, name):
    try:
        st = os.lstat(path)
    except OSError:
        raise _mismatch(name, 'missing') from None
    if not stat.S_ISREG(st.st_mode):
        raise _mismatch(name, 'a link or not a regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        h = hashlib.sha256()
        while True:
            b = os.read(fd, 1 << 20)
            if not b:
                return h.hexdigest()
            h.update(b)
    finally:
        os.close(fd)


def verify_collector(collector_dir=None, frozen_sha256=FROZEN_COLLECTOR_SHA256):
    """Verify the collector directory against its COLLECTOR-PIN.json; return {collector_sha256, files}."""
    d = Path(collector_dir) if collector_dir is not None else COLLECTOR_DIR
    try:
        st = os.lstat(d)
    except OSError:
        raise _mismatch('', 'the collector directory is missing') from None
    if not stat.S_ISDIR(st.st_mode):
        raise _mismatch('', 'the collector directory is a link or not a directory')
    pin_path = d / PIN_NAME
    try:
        pst = os.lstat(pin_path)
    except OSError:
        raise _mismatch(PIN_NAME, 'missing') from None
    if not stat.S_ISREG(pst.st_mode) or pst.st_size > MAX_PIN_BYTES:
        raise _mismatch(PIN_NAME, 'a link, not a regular file, or too large')
    try:
        doc = parse_json(pin_path.read_bytes())
    except Refusal:
        raise _mismatch(PIN_NAME, 'malformed') from None
    ok = (isinstance(doc, dict) and set(doc) == {'schema', 'files', 'source', 'flags'} and doc['schema'] == PIN_SCHEMA
          and doc['flags'] == FLAGS and isinstance(doc['files'], dict) and COLLECTOR in doc['files']
          and all(isinstance(k, str) and NAME_RE.fullmatch(k) and isinstance(v, str)
                  and re.fullmatch(r'[0-9a-f]{64}', v) for k, v in doc['files'].items()))
    if not ok:
        raise _mismatch(PIN_NAME, 'malformed')
    if frozen_sha256 is not None and doc['files'][COLLECTOR] != frozen_sha256:
        raise _mismatch(COLLECTOR, 'the pin does not name the frozen collector')
    for name in sorted(doc['files']):
        if _hash_regular(d / name, name) != doc['files'][name]:
            raise _mismatch(name, 'digest differs')
    return {'collector_sha256': doc['files'][COLLECTOR], 'files': dict(doc['files'])}


# ---------- inputs ----------
def check_role(role, conn):
    """The collection role: the input, else the connection's user; they must agree. `bad_input` otherwise."""
    role = (role or '').strip()
    user = conn.user if conn is not None else None
    if not role and not user:
        raise Refusal('bad_input', 'collection-role is empty and the connection names no user')
    if role and user and role != user:
        raise Refusal('bad_input', 'collection-role differs from the user in the connection; they must be the same role')
    role = role or user
    if not ROLE_RE.fullmatch(role) or role.upper() == 'PUBLIC' or role.startswith('pg_'):
        raise Refusal('bad_input', 'collection-role must be an identifier that is neither PUBLIC nor pg_-prefixed')
    return role


def check_privileges(text):
    items = [p.strip() for p in (text if text and text.strip() else DEFAULT_PRIVILEGES).split(',') if p.strip()]
    if not items or len(set(items)) != len(items) or any(p not in READ_ONLY_ROLES for p in items):
        raise Refusal('bad_input', 'collection-privileges must list, without repeats, only: %s' % ', '.join(READ_ONLY_ROLES))
    return ','.join(items)


def check_data_dir(text):
    """None when empty; else an existing directory other than /. `bad_input` otherwise."""
    t = (text or '').strip()
    if not t:
        return None
    if len(t) > 4096 or _CONTROL.search(t):
        raise Refusal('bad_input', 'data-dir is too long or holds a control character')
    real = os.path.realpath(t)
    if not os.path.isdir(real) or real == '/':
        raise Refusal('bad_input', 'data-dir must name an existing directory other than the filesystem root')
    return real


MAX_CONFIG_DIRS = 16
MAX_PATH = 4096


def check_config_dirs(text):
    """The `config-dirs` input: directories outside the data directory that hold the server's configuration files (the
    Debian layout keeps them under /etc/postgresql/<major>/<cluster>). Items are separated by line breaks or colons;
    blank items are skipped. Each must be an existing directory other than /, with no control character. Returns the
    resolved paths in order, without repeats, each to become one `--extra-root` argument item. `bad_input` otherwise."""
    if text is None:
        return ()
    t = str(text)
    if len(t) > MAX_CONFIG_DIRS * (MAX_PATH + 1):
        raise Refusal('bad_input', 'config-dirs is longer than %d characters' % (MAX_CONFIG_DIRS * (MAX_PATH + 1)))
    items = [i.strip() for i in re.split(r'[\n:]', t)]
    items = [i for i in items if i]
    if len(items) > MAX_CONFIG_DIRS:
        raise Refusal('bad_input', 'config-dirs names more than %d directories' % MAX_CONFIG_DIRS)
    out = []
    for n, item in enumerate(items, 1):
        if len(item) > MAX_PATH or _CONTROL.search(item):
            raise Refusal('bad_input', 'config-dirs item %d is too long or holds a control character' % n)
        real = os.path.realpath(item)
        if not os.path.isdir(real) or real == '/':
            raise Refusal('bad_input', 'config-dirs item %d must name an existing directory other than the '
                          'filesystem root' % n)
        if real not in out:
            out.append(real)
    return tuple(out)


def resolve_psql(psql, path):
    """The absolute psql executable, or `collector_cannot_connect` when it is absent."""
    if os.path.isabs(psql):
        found = psql if os.path.isfile(psql) and os.access(psql, os.X_OK) else None
    else:
        found = shutil.which(psql, path=path)
    if not found:
        raise Refusal('collector_cannot_connect', 'psql is not installed on the runner or not on its PATH; install '
                      'the PostgreSQL client (postgresql-client)')
    return os.path.abspath(found)


# ---------- running ----------
def _read_bounded(path, cap=OUTPUT_CAP):
    try:
        with open(path, 'rb') as fh:
            return fh.read(cap).decode('utf-8', 'replace')
    except OSError:
        return ''


def _count_queries(progress):
    try:
        with open(progress, 'rb') as fh:
            return fh.read(OUTPUT_CAP).count(b'\n')
    except OSError:
        return 0


def _refusal_doc(out, stdout_text):
    """The collector's refusal: REFUSAL.json when it is a plain file, else the last JSON line it printed."""
    p = Path(out) / 'REFUSAL.json'
    try:
        st = os.lstat(p)
        if stat.S_ISREG(st.st_mode) and st.st_size <= OUTPUT_CAP:
            doc = parse_json(p.read_bytes())
            if isinstance(doc, dict):
                return doc
    except (OSError, Refusal):
        pass
    for line in reversed(stdout_text.splitlines()):
        try:
            doc = parse_json(line.strip().encode('utf-8'))
        except Refusal:
            continue
        if isinstance(doc, dict):
            return doc
    return {}


def _is_transport(kind, reason, queries_run):
    return (kind == 'collection_role_unverified' and isinstance(queries_run, list)
            and all(q == 'collector_identity' for q in queries_run)
            and any(w in reason.lower() for w in TRANSPORT_WORDS))


def _refused(out, stdout_text, conn, rc):
    doc = _refusal_doc(out, stdout_text)
    ref = doc.get('refusal') if isinstance(doc.get('refusal'), dict) else {}
    kind = ref.get('type') if isinstance(ref.get('type'), str) else 'unknown'
    kind = kind if re.fullmatch(r'[a-z_]{1,64}', kind) else 'unknown'
    reason = ref.get('reason') if isinstance(ref.get('reason'), str) else ''
    if _is_transport(kind, reason, doc.get('queries_run')):
        tail = reason.split('): ', 1)[1] if reason.startswith(_IDENTITY_PREFIX) and '): ' in reason else reason
        return Refusal('collector_cannot_connect', sanitise('the first query could not reach the server as the '
                       'collection role: ' + tail, conn), collector_exit=rc, collector_refusal=kind)
    if not doc:
        return Refusal('collector_refused', 'the collector refused without a refusal document', collector_exit=rc)
    return Refusal('collector_refused', sanitise('%s: %s' % (kind, reason or 'no reason given'), conn),
                   collector_exit=rc, collector_refusal=kind)


def _gather(out, profile, limits):
    """The collector's output as the raw/ bundle: out/raw/* plus the sidecar and timing, moved into raw/."""
    out = Path(out)
    try:
        st = os.lstat(out)
        rst = os.lstat(out / 'raw')
    except OSError:
        raise Refusal('checker_error', 'the collector reported a collection but wrote no raw/ directory') from None
    if not stat.S_ISDIR(st.st_mode) or not stat.S_ISDIR(rst.st_mode):
        raise Refusal('checker_error', 'the collector output is a link or not a directory')
    for name in ('COLLECTION-SIDECAR.json', 'TIMING.json'):
        src, dst = out / name, out / 'raw' / name
        try:
            sst = os.lstat(src)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(sst.st_mode):
            raise Refusal('checker_error', 'the collector wrote %s as a link or not a regular file' % name)
        if os.path.lexists(dst):
            raise Refusal('checker_error', 'the collector wrote raw/%s itself; the bundle name is taken' % name)
        os.rename(src, dst)
    return withhold.apply(from_directory(out, profile, limits))   # before any check, body or upload sees the bytes


def collect(conn, *, role, privileges, profile, scratch, data_dir=None, extra_roots=(), collector_dir=None,
            frozen_sha256=FROZEN_COLLECTOR_SHA256, psql='psql', path=None, timeout=DEFAULT_TIMEOUT, python=None,
            limits=LIMITS):
    """Verify and run the collector into `scratch`; return the bundle (`bundle.Collected`). Every fault is a Refusal."""
    d = Path(collector_dir) if collector_dir is not None else COLLECTOR_DIR
    verify_collector(d, frozen_sha256)
    path = path or '/usr/bin:/bin'
    psql_path = resolve_psql(psql, path)
    scratch = Path(scratch)
    if data_dir is None:
        data_dir = scratch / 'no-data-dir'          # empty: every configuration file reads as a recorded gap
        data_dir.mkdir(mode=0o700)
    out, progress = scratch / 'collect-out', scratch / 'psql-progress'
    stdout_p, stderr_p = scratch / 'collector.stdout', scratch / 'collector.stderr'
    py = python or sys.executable
    shim = shlex.join([py, '-I', '-B', str(Path(__file__).resolve()), '--psql-shim', str(progress), '--', psql_path])
    argv = [py, '-I', '-B', str(d / COLLECTOR), '--out', str(out), '--role', role, '--privileges', privileges,
            '--data-dir', str(data_dir), '--psql', shim]
    for root in extra_roots:                        # config-dirs: each one argument item, never through a shell
        argv += ['--extra-root', str(root)]
    with open(stdout_p, 'wb') as so, open(stderr_p, 'wb') as se:
        proc = subprocess.Popen(argv, env=child_env(conn, path=path), stdin=subprocess.DEVNULL, stdout=so, stderr=se,
                                cwd=str(scratch), start_new_session=True, close_fds=True)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
            if _count_queries(progress) <= 1:
                raise Refusal('collector_cannot_connect', 'the first query did not finish within %d s; check the host, '
                              'the network path from the runner and pg_hba.conf' % timeout) from None
            raise Refusal('checker_timeout', 'the collector ran past its %d s limit' % timeout) from None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    if rc in (0, 1):
        return _gather(out, profile, limits)
    if rc == 3:
        raise _refused(out, _read_bounded(stdout_p), conn, rc)
    printed = _refusal_doc(scratch / 'no-such-output', _read_bounded(stdout_p)).get('refusal')
    if isinstance(printed, dict) and isinstance(printed.get('reason'), str):
        detail = '%s: %s' % (printed.get('type'), printed['reason'])
    else:
        lines = _read_bounded(stderr_p).strip().splitlines()
        detail = lines[-1] if lines else ''
    detail = sanitise(detail, conn)
    raise Refusal('checker_error', 'the collector exited %s%s' % (rc, (': ' + detail) if detail else ''),
                  collector_exit=rc)

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
