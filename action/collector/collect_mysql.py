#!/usr/bin/env python3
"""collect_mysql.py: read-only MySQL collector for the `mysql-declared-model` profile (proposal; approves nothing).

Usage:
  python3.14 -I -B collect_mysql.py --out <dir> --role <collection_role> --declaration <declaration.json>
      --mysql <client command> [--login-user <name>]

Produces <out>/raw/submission.json, the `symbolia.mysql-declared-input.v0` document the frozen MySQL derive reads
(INPUT-FORM-004): the OBSERVABLE sections come from fixed SELECT/SHOW reads of the server through the `mysql` client
(grant tables, mysql.user lock facts, the five global variables the checker reads, replication applier channels, stored
program definitions, the server version); the DECLARED sections (declared_policy, m3, collection claims) are carried
verbatim from the customer's declaration file. The collector never invents policy and never reads a password hash: it
never selects authentication_string, and the whole merged document passes the frozen sensitive-field filter (revision 20,
shipped beside this file, digest checked) before a byte is written; any finding refuses the run naming the path and kind,
never the value.

The connection reaches the client by environment only (MYSQL_HOST, MYSQL_TCP_PORT, MYSQL_PWD, as the mysql client reads
them); the login user goes to the client as `-u <login user>`; no password is ever on a command line or printed. Every
query is one fixed string from QUERIES below (published; never built from input), fed on the client's stdin, and is a
SELECT or SHOW; the collector performs no write. An unreadable source after the first read is recorded in `sources[]`
as `unreadable` and its section is left absent (never an empty roster).

Exit codes: 0 collected, every source supplied; 1 collected with recorded gaps; 2 invalid arguments (nothing written);
3 typed refusal (REFUSAL.json written, nothing else). Standard library only; no network of its own; no writes to any
database. Flags: execution_authorized false; hardware_authorized false; industrial_release_authorized false;
release_allowed false; physical_validation false; simulation true; self_approved false."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FLAGS = {'execution_authorized': False, 'hardware_authorized': False, 'industrial_release_authorized': False,
         'release_allowed': False, 'physical_validation': False, 'simulation': True, 'self_approved': False}
SCHEMA = 'symbolia.mysql-declared-input.v0'
DECLARATION_SCHEMA = 'symbolia.mysql-declaration.v0'
# The frozen data-protection filter the registry pins for mysql-declared-model (rev 20). Its bytes ship beside this
# collector as sensitive_field_filter_rev20.py (byte-equal to the registry copy under assure/checkers/) and are imported
# as an ordinary module only after their digest is checked against the pin; a mismatch is a typed refusal. The
# collector keeps no secret shape list of its own and loads no code dynamically.
FILTER_MODULE = 'sensitive_field_filter_rev20'
FILTER_SHA256 = '575549c5e02a11e986c3ba1ac1d06eb6623812e201f61d51e086f12359916104'
SERIES = {'8.0.': 800, '8.4.': 840, '9.7.': 970}
MAX_DECLARATION = 64 * 1024
ROW_CAP = 4096                       # rows read per source; beyond it the source is recorded unreadable (bounded)
OUT_CAP = 16 << 20

# The published query list. Each is a SELECT or SHOW; the column order is the row order the projections below read.
# mysql.user: never authentication_string. The secondary password lives under User_attributes; only its presence is read.
QUERIES = {
    'version': "SELECT VERSION()",
    'mysql.user': ("SELECT User, Host, account_locked, plugin, password_lifetime, password_lock_time, failed_login_attempts, "
                   "IF(JSON_EXTRACT(User_attributes, '$.additional_password') IS NULL, 'N', 'Y'), "
                   "JSON_EXTRACT(User_attributes, '$.Restrictions') FROM mysql.user ORDER BY User, Host"),
    'show_grants': "SHOW GRANTS FOR %s",                      # the one parametrised read: an account the user table named, quoted below
    'mysql.db': ("SELECT User, Host, Db, Select_priv, Insert_priv, Update_priv, Delete_priv, Create_priv, Drop_priv, Grant_priv, "
                 "References_priv, Index_priv, Alter_priv, Create_tmp_table_priv, Lock_tables_priv, Create_view_priv, Show_view_priv, "
                 "Create_routine_priv, Alter_routine_priv, Execute_priv, Event_priv, Trigger_priv FROM mysql.db ORDER BY User, Host, Db"),
    'mysql.tables_priv': "SELECT User, Host, Db, Table_name, Table_priv FROM mysql.tables_priv ORDER BY User, Host, Db, Table_name",
    'mysql.columns_priv': "SELECT User, Host, Db, Table_name, Column_name, Column_priv FROM mysql.columns_priv ORDER BY User, Host, Db, Table_name, Column_name",
    'mysql.procs_priv': "SELECT User, Host, Db, Routine_name, Routine_type, Proc_priv FROM mysql.procs_priv ORDER BY User, Host, Db, Routine_name",
    'mysql.proxies_priv': "SELECT User, Host, Proxied_user, Proxied_host, With_grant FROM mysql.proxies_priv ORDER BY User, Host",
    'mysql.global_grants': "SELECT USER, HOST, PRIV, WITH_GRANT_OPTION FROM mysql.global_grants ORDER BY USER, HOST, PRIV",
    'mysql.role_edges': "SELECT FROM_HOST, FROM_USER, TO_HOST, TO_USER, WITH_ADMIN_OPTION FROM mysql.role_edges ORDER BY TO_USER, TO_HOST, FROM_USER",
    'mysql.default_roles': "SELECT HOST, USER, DEFAULT_ROLE_HOST, DEFAULT_ROLE_USER FROM mysql.default_roles ORDER BY USER, HOST",
    'system-variables': "SHOW GLOBAL VARIABLES",
    'replication-channel-declarations': ("SELECT CHANNEL_NAME, PRIVILEGE_CHECKS_USER, REQUIRE_ROW_FORMAT, REQUIRE_TABLE_PRIMARY_KEY_CHECK "
                                         "FROM performance_schema.replication_applier_configuration ORDER BY CHANNEL_NAME"),
    'routines': "SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SECURITY_TYPE FROM information_schema.ROUTINES ORDER BY ROUTINE_SCHEMA, ROUTINE_NAME",
    'views': "SELECT TABLE_SCHEMA, TABLE_NAME, DEFINER, SECURITY_TYPE FROM information_schema.VIEWS ORDER BY TABLE_SCHEMA, TABLE_NAME",
    'triggers': "SELECT TRIGGER_SCHEMA, TRIGGER_NAME, DEFINER FROM information_schema.TRIGGERS ORDER BY TRIGGER_SCHEMA, TRIGGER_NAME",
    'events': "SELECT EVENT_SCHEMA, EVENT_NAME, DEFINER FROM information_schema.EVENTS ORDER BY EVENT_SCHEMA, EVENT_NAME",
}
# mysql.db privilege columns, in the order QUERIES['mysql.db'] selects them, with the name GRANT spells.
DB_PRIV_COLUMNS = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'GRANT OPTION', 'REFERENCES', 'INDEX', 'ALTER',
                   'CREATE TEMPORARY TABLES', 'LOCK TABLES', 'CREATE VIEW', 'SHOW VIEW', 'CREATE ROUTINE', 'ALTER ROUTINE',
                   'EXECUTE', 'EVENT', 'TRIGGER')
# The only global variables kept: the three M1/M7 read verbatim (strings) and the two typed ones M2 reads. M3 reads
# `m3.server_variables` from the declaration, so no TLS variable is kept (REFUTATION-MYSQL-COLLECTOR-C1-001 A-1).
M1_M7_VARIABLES = ('partial_revokes', 'activate_all_roles_on_login', 'mandatory_roles')
M2_SYSVARS = ('default_password_lifetime', 'password_require_current')
_GRANT_LINE = re.compile(r'^GRANT\s+(.*?)\s+ON\s+(.+?)\s+TO\s+', re.I | re.S)
_REVOKE_LINE = re.compile(r'^REVOKE\s+(.*?)\s+ON\s+`?([^`.]+)`?\.\*\s+FROM\s+', re.I | re.S)
_ACCOUNT = re.compile(r"^['`\"]?([^'`\"@]*)['`\"]?@['`\"]?([^'`\"]*)['`\"]?$")


class Refuse(Exception):
    def __init__(self, kind, reason):
        self.kind, self.reason = kind, reason
        super().__init__(kind + ': ' + reason)


# ---------- the frozen filter ----------
def load_filter():
    """The shipped rev-20 filter module, digest-checked before a byte of it runs. The collector runs as a script under
    -I (no script directory on sys.path), so its own directory is placed first and the module is then imported by a
    plain import statement: no importlib, no exec, no code from anywhere but the checked file."""
    here = Path(__file__).resolve().parent
    path = here / (FILTER_MODULE + '.py')
    try:
        data = path.read_bytes()
    except OSError:
        raise Refuse('filter_mismatch', 'the frozen sensitive-field filter is absent beside the collector') from None
    if hashlib.sha256(data).hexdigest() != FILTER_SHA256:
        raise Refuse('filter_mismatch', 'the sensitive-field filter differs from its pinned digest')
    if sys.path[:1] != [str(here)]:
        sys.path.insert(0, str(here))
    import sensitive_field_filter_rev20 as flt
    if Path(getattr(flt, '__file__', '') or '').resolve() != path:
        raise Refuse('filter_mismatch', 'the imported sensitive-field filter is not the checked file')
    return flt


# ---------- the client ----------
class Client:
    """One `mysql` client subprocess per query; the SQL on stdin; rows as lists of str or None (NULL)."""
    def __init__(self, command, login_user, env):
        self.argv = [command, '-u', login_user, '--batch', '--raw', '--skip-column-names']
        self.env = env
        self.queries_run = 0
        self.filter = None

    def rows(self, sql):
        self.queries_run += 1
        try:
            p = subprocess.run(self.argv, input=sql.encode('utf-8'), env=self.env, capture_output=True, timeout=120,
                               stdin=None, start_new_session=True)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, type(e).__name__
        if p.returncode != 0:
            err = p.stderr.decode('utf-8', 'replace').strip()
            return None, err
        out = []
        for line in p.stdout.decode('utf-8', 'replace').splitlines():
            if not line.strip():
                continue
            out.append([None if v == 'NULL' else v for v in line.split('\t')])
            if len(out) > ROW_CAP:
                return None, 'more than %d rows' % ROW_CAP
        return out, None


def scrub(text, env, flt):
    """Error text fit to quote: the password value removed, then the frozen filter's redact()."""
    pw = env.get('MYSQL_PWD')
    if pw:
        text = text.replace(pw, '<withheld>')
    return flt.redact(text)[:500] if flt is not None else text[:200]


# ---------- projections ----------
def as_int(v):
    try:
        return int(v) if v is not None and v != '' else None
    except ValueError:
        return None


def account(text):
    m = _ACCOUNT.match((text or '').strip())
    return {'user': m.group(1), 'host': m.group(2)} if m else None


def quoted_account(user, host):
    return "'%s'@'%s'" % (user.replace('\\', '\\\\').replace("'", "\\'"), host.replace('\\', '\\\\').replace("'", "\\'"))


def privilege_names(text):
    """'SELECT, INSERT, GRANT OPTION' -> ['SELECT', 'INSERT', 'GRANT OPTION']; USAGE dropped; upper-cased, spaces collapsed."""
    out = []
    for part in text.split(','):
        name = ' '.join(part.strip().upper().split())
        name = re.sub(r'\s*\(.*\)$', '', name)                 # column-level lists in a grant line: the name only
        if name and name != 'USAGE' and name not in out:
            out.append(name)
    return out


def grants_of(lines):
    """From SHOW GRANTS lines: (global privilege names, [{privileges, database}] partial revokes)."""
    privileges, revokes = [], []
    for (line,) in lines:
        m = _GRANT_LINE.match(line)
        if m:
            if m.group(2).strip() == '*.*':
                names = privilege_names(m.group(1))
                if re.search(r'\bWITH\s+GRANT\s+OPTION\b', line, re.I) and 'GRANT OPTION' not in names:
                    names.append('GRANT OPTION')
                for n in names:
                    if n not in privileges:
                        privileges.append(n)
            continue
        m = _REVOKE_LINE.match(line)
        if m:
            revokes.append({'privileges': privilege_names(m.group(1)), 'database': m.group(2)})
    return privileges, revokes


def yn_privileges(values, names):
    return [n for v, n in zip(values, names) if v == 'Y']


def collect_observable(client, declaration_series):
    """The observable sections and the sources list; (sections, sources, exact version, series)."""
    rows, err = client.rows(QUERIES['version'])
    if rows is None or not rows or not rows[0]:
        raise Refuse('collector_cannot_connect', 'the first read (SELECT VERSION()) failed: %s' % (err or 'no row'))
    exact = rows[0][0]
    series = next((s for p, s in SERIES.items() if exact.startswith(p)), None)
    if series is None:
        raise Refuse('unsupported_series', 'the server version is outside the modelled series 8.0 / 8.4 / 9.7')
    if declaration_series is not None and declaration_series != series:
        raise Refuse('series_mismatch', 'the declaration names a series the server does not report')
    sections, sources = {'grant_tables': {}}, []

    def source(name, status):
        sources.append({'name': name, 'status': status, 'sha256': None, 'reading': 'collected by collect_mysql.py' if status == 'supplied' else 'the collection role could not read this source'})

    # mysql.user: lock facts (M2), the account roster and SHOW GRANTS projection (M1/M6/M7/M8), 840 restrictions
    rows, err = client.rows(QUERIES['mysql.user'])
    if rows is None:
        source('mysql.user', 'unreadable')
    else:
        mysql_user, users, show_grants = [], [], []
        for r in rows:
            r = (r + [None] * 9)[:9]
            user, host, locked, plugin, lifetime, lock_time, attempts, secondary, restrictions = r
            mysql_user.append({'User': user, 'Host': host, 'account_locked': locked, 'plugin': plugin,
                               'failed_login_attempts': as_int(attempts), 'password_lock_time': as_int(lock_time),
                               'has_secondary_password': None if secondary is None else secondary == 'Y',
                               'password_lifetime': as_int(lifetime)})
            g, gerr = client.rows(QUERIES['show_grants'] % quoted_account(user, host))
            if g is None:
                source('mysql.user', 'unreadable')
                mysql_user = None
                break
            privileges, revokes = grants_of(g)
            row = {'User': user, 'Host': host, 'privileges': privileges}
            if restrictions not in (None, '', 'null'):
                try:
                    row['User_attributes'] = {'Restrictions': json.loads(restrictions)}
                except ValueError:
                    pass
            users.append(row)
            if revokes:
                show_grants.append({'User': user, 'Host': host, 'revokes': revokes})
        if mysql_user is not None:
            sections['mysql_user'] = mysql_user
            sections['grant_tables']['user'] = users
            if show_grants:
                sections['show_grants'] = show_grants
            source('mysql.user', 'supplied')
    # the other grant tables
    projections = {
        'mysql.db': ('db', lambda r: {'User': r[0], 'Host': r[1], 'Db': r[2], 'privileges': yn_privileges(r[3:22], DB_PRIV_COLUMNS)}),
        'mysql.tables_priv': ('tables_priv', lambda r: {'User': r[0], 'Host': r[1], 'Db': r[2], 'Table_name': r[3], 'privileges': privilege_names(r[4] or '')}),
        'mysql.columns_priv': ('columns_priv', lambda r: {'User': r[0], 'Host': r[1], 'Db': r[2], 'Table_name': r[3], 'Column_name': r[4], 'privileges': privilege_names(r[5] or '')}),
        'mysql.procs_priv': ('procs_priv', lambda r: {'User': r[0], 'Host': r[1], 'Db': r[2], 'Routine_name': r[3], 'Routine_type': r[4], 'Proc_priv': r[5] or ''}),
        'mysql.proxies_priv': ('proxies_priv', lambda r: {'proxy_user': r[0], 'proxy_host': r[1], 'proxied_user': r[2], 'proxied_host': r[3], 'grant_flag': r[4] in ('1', 'Y')}),
        'mysql.global_grants': ('global_grants', lambda r: {'USER': r[0], 'HOST': r[1], 'PRIV': r[2], 'WITH_GRANT_OPTION': r[3]}),
        'mysql.role_edges': ('role_edges', lambda r: {'FROM_HOST': r[0], 'FROM_USER': r[1], 'TO_HOST': r[2], 'TO_USER': r[3], 'WITH_ADMIN_OPTION': r[4]}),
        'mysql.default_roles': ('default_roles', lambda r: {'HOST': r[0], 'USER': r[1], 'DEFAULT_ROLE_HOST': r[2], 'DEFAULT_ROLE_USER': r[3]}),
    }
    for name, (table, project) in projections.items():
        rows, err = client.rows(QUERIES[name])
        if rows is None:
            source(name, 'unreadable')
            continue
        try:
            sections['grant_tables'][table] = [project(r) for r in rows]
        except IndexError:
            source(name, 'unreadable')
            continue
        source(name, 'supplied')
    # global variables
    rows, err = client.rows(QUERIES['system-variables'])
    if rows is None:
        source('system-variables', 'unreadable')
    else:
        values = {r[0]: r[1] for r in rows if len(r) >= 2}
        sysvars = {}
        if 'default_password_lifetime' in values:
            sysvars['default_password_lifetime'] = as_int(values['default_password_lifetime'])
        if 'password_require_current' in values:
            sysvars['password_require_current'] = values['password_require_current']
        sections['system_variables'] = sysvars
        sections['variables'] = {k: values[k] for k in M1_M7_VARIABLES if k in values}
        source('system-variables', 'supplied')
    # replication applier channels (M8 form)
    rows, err = client.rows(QUERIES['replication-channel-declarations'])
    if rows is None:
        source('replication-channel-declarations', 'unreadable')
    else:
        channels = []
        for r in rows:
            r = (r + [None] * 4)[:4]
            rrf = as_int(r[2])
            channels.append({'channel': r[0], 'configuration': {'form': 'options', 'options': {
                'PRIVILEGE_CHECKS_USER': account(r[1]) if r[1] else None,
                'REQUIRE_ROW_FORMAT': rrf if rrf in (0, 1) else None,
                'REQUIRE_TABLE_PRIMARY_KEY_CHECK': r[3]}}})
        sections['replication_channels'] = channels
        source('replication-channel-declarations', 'supplied')
    # stored programs (M6)
    programs, ok = [], True
    for name, kind in (('routines', None), ('views', 'VIEW'), ('triggers', 'TRIGGER'), ('events', 'EVENT')):
        rows, err = client.rows(QUERIES[name])
        if rows is None:
            ok = False
            break
        for r in rows:
            if name == 'routines':
                db, obj, typ, definer, sec = (r + [None] * 5)[:5]
            else:
                db, obj, definer = (r + [None] * 3)[:3]
                typ = kind
                sec = r[3] if name == 'views' and len(r) > 3 else None
            programs.append({'id': '%s:%s:%s' % (typ, db, obj), 'type': typ, 'database': db, 'name': obj,
                             'definer': account(definer), 'sql_security': sec})
    if ok:
        sections['stored_programs'] = programs
        source('stored program definitions', 'supplied')
    else:
        source('stored program definitions', 'unreadable')
    return sections, sources, exact, series


# ---------- the declaration ----------
def read_declaration(path):
    p = Path(path)
    try:
        st = os.lstat(p)
    except OSError:
        raise Refuse('declaration_unreadable', 'the declaration file is absent') from None
    if not os.path.isfile(p) or os.path.islink(p) or st.st_size > MAX_DECLARATION:
        raise Refuse('declaration_unreadable', 'the declaration must be a regular file of at most 64 KiB, never a link')
    try:
        doc = json.loads(p.read_bytes().decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        raise Refuse('declaration_unreadable', 'the declaration is not UTF-8 JSON') from None
    if not isinstance(doc, dict) or doc.get('schema') != DECLARATION_SCHEMA:
        raise Refuse('declaration_unreadable', 'the declaration must be an object with schema %s' % DECLARATION_SCHEMA)
    flags = doc.get('flags')
    if flags is not None:
        expected = {k: v for k, v in FLAGS.items() if k != 'self_approved' or 'self_approved' in flags}
        if flags != expected:
            raise Refuse('flags_not_standing', 'the declaration flags are not the standing values')
    return doc


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def build(args, env, flt):
    decl = read_declaration(args.declaration)
    collection = decl.get('collection')
    if not isinstance(collection, dict) or collection.get('role') != args.role:
        raise Refuse('role_mismatch', 'the declaration collection.role must equal --role')
    series_declared = (decl.get('version') or {}).get('series') if isinstance(decl.get('version'), dict) else None
    client = Client(args.mysql, args.login_user or args.role, env)
    try:
        sections, sources, exact, series = collect_observable(client, series_declared)
    except Refuse as r:
        r.queries_run = client.queries_run
        raise
    submission = {'schema': SCHEMA, 'material': 'mysql', 'version': {'series': series, 'exact': exact},
                  'flags': dict(FLAGS), 'collection': dict(collection), 'sources': sources,
                  'required_sources': [s['name'] for s in sources]}
    submission['collection'].setdefault('snapshot_complete', True)
    submission.update(sections)
    for key in ('declared_policy', 'm3'):
        if key in decl:
            submission[key] = decl[key]
    submission['configuration_sha256'] = hashlib.sha256(canonical({k: sections.get(k) for k in sorted(sections)} | {'version': submission['version']})).hexdigest()
    findings = flt.scan(submission)
    if findings:
        raise Refuse('sensitive_field', 'the submission holds a field that must not be stored: ' +
                     '; '.join('%s (%s)' % (f.path, f.kind) for f in findings[:20]))
    gaps = [s['name'] for s in sources if s['status'] != 'supplied']
    return submission, gaps, client.queries_run


def write_new(path, data):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--out', required=True)
    ap.add_argument('--role', required=True)
    ap.add_argument('--declaration', required=True)
    ap.add_argument('--mysql', required=True)
    ap.add_argument('--login-user', default=None)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not args.role or not args.out or not args.mysql:
        return 2
    out = Path(args.out)
    if out.exists():
        sys.stderr.write('collect_mysql: refusal out_exists\n')
        return 2 if not out.is_dir() else _refuse(out, Refuse('out_exists', 'the output directory already exists'), 0, {}, None, create=False)
    env = {k: v for k, v in os.environ.items() if k in ('MYSQL_HOST', 'MYSQL_TCP_PORT', 'MYSQL_PWD', 'MYSQL_UNIX_PORT', 'PATH', 'LC_ALL', 'LANG')}
    env.update({k: v for k, v in os.environ.items() if k.startswith('FAKE_')})   # test seams of a fake client only
    env.setdefault('LC_ALL', 'C')
    out.mkdir(mode=0o700)
    flt = None
    try:
        read_declaration(args.declaration)          # flags and shape first: a refused declaration reads nothing from the server
        flt = load_filter()
        submission, gaps, queries = build(args, env, flt)
    except Refuse as r:
        return _refuse(out, r, getattr(r, 'queries_run', 0), env, flt)
    (out / 'raw').mkdir(mode=0o700)
    data = (json.dumps(submission, sort_keys=True, indent=1, ensure_ascii=True) + '\n').encode('ascii')
    if len(data) > OUT_CAP:
        return _refuse(out, Refuse('output_too_large', 'the submission exceeds the output cap'), queries, env, flt)
    write_new(out / 'raw' / 'submission.json', data)
    return 1 if gaps else 0


def _refuse(out, r, queries, env, flt, create=True):
    reason = scrub(r.reason, env, flt)
    doc = dict(FLAGS, refusal_type=r.kind, reason=reason, queries_run=queries)
    try:
        write_new(out / 'REFUSAL.json', (json.dumps(doc, sort_keys=True, indent=1) + '\n').encode())
    except OSError:
        pass
    sys.stderr.write('collect_mysql: refusal %s: %s\n' % (r.kind, reason))
    return 3


if __name__ == '__main__':
    sys.exit(main())
