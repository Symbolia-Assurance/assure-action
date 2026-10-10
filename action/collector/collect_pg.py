#!/usr/bin/env python3
"""collect_pg.py: RF-06 neutral read-only PostgreSQL collector (proposal; approves nothing).

Usage:
  python3.14 -B collect_pg.py --out <dir> --role <collection_role> \
      --privileges <csv of pg_read_all_settings,pg_read_all_stats; RF-24 (h), ruling 20> \
      --data-dir <path> [--extra-root <dir> ...] [--psql <cmd>]
      [--role-created-for-run yes|no]      (RF-24 (e): operator-stated; omitted means not stated)
      [--login-user <name>]                (RF-28 (d): the client login name; omitted means --role)
  python3.14 -B collect_pg.py --emit-queries <path>      (writes the published query list)

Every catalog read is one fixed SELECT from QUERIES (published as QUERIES.json), version-gated 14..18,
run through the module-level RUNNER callable (sql) -> (returncode, stdout, stderr). The default RUNNER
is a `psql -X -At -F <US> -w -U <login user>` subprocess (RF-28 (d)) whose session is asked to be read-only through
PGOPTIONS='-c default_transaction_read_only=on'. The first read is the collection role's own pg_roles
row; a superuser role, a role other than --role, or an unverifiable identity is a typed refusal before
any other read. Nothing is ever retried, never as another role. An unreadable, unsupported or missing
input is recorded in COLLECTION-SIDECAR.json and its catalog key is left out of the snapshot; it is
never written as an empty roster. Password and authentication strings are stripped before any byte is
retained; REDACTION-MANIFEST.json records {file, field, count} and the sanitised file digests, never a
value or a hash of a value. Volatile timing goes only to TIMING.json.

Exit codes: 0 collected, every input observed (or observed empty / declared absent);
1 collected with recorded gaps; 2 invalid arguments (nothing read, nothing written);
3 typed refusal (REFUSAL.json written, nothing else).
No network of its own, no hardware, no writes to any database; standard library only.
"""
import argparse
import datetime
import hashlib
import ipaddress          # RF-28 (e): the client address class
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, namedtuple      # RF-28 (a): namedtuple for a whole-line withholding
from pathlib import Path
from urllib.parse import quote, unquote

FLAGS = {'execution_authorized': False, 'hardware_authorized': False, 'industrial_release_authorized': False,
         'release_allowed': False, 'physical_validation': False, 'simulation': True, 'self_approved': False}
# RF-24 (h): least privilege (DESIGN-RULINGS-002 ruling 20). The collection role may hold exactly these two grants.
# pg_monitor is a strict superset of them and pg_stat_scan_tables adds lock-taking functions: the frozen collector
# accepted both; a declared or observed membership in either is now a typed refusal.
READ_ONLY_ROLES = ('pg_read_all_settings', 'pg_read_all_stats')
BROADER_READ_ROLES = ('pg_monitor', 'pg_stat_scan_tables')
SEP = '\x1f'
MAJORS = (14, 18)
OK_STATUSES = ('observed', 'observed_empty', 'declared_absent')
MAX_DEPTH = 10

# pg_settings rows collected: the settings the eight machines and the RF-01 preflight read, the file
# locations, and the conninfo/secret-bearing settings that must be stripped.
SETTINGS_COLLECTED = sorted([
    'authentication_timeout', 'config_file', 'data_directory', 'hba_file', 'hot_standby', 'ident_file',
    'krb_server_keyfile', 'listen_addresses', 'log_connections', 'max_replication_slots',
    'max_slot_wal_keep_size', 'max_wal_senders', 'password_encryption', 'port', 'primary_conninfo',
    'primary_slot_name', 'row_security', 'search_path', 'session_preload_libraries',
    'shared_preload_libraries', 'ssl', 'ssl_ca_file', 'ssl_cert_file', 'ssl_crl_file', 'ssl_key_file',
    'ssl_max_protocol_version', 'ssl_min_protocol_version', 'ssl_passphrase_command',
    'synchronous_commit', 'synchronous_standby_names', 'wal_keep_size', 'wal_level',
    'unix_socket_directories', 'unix_socket_group', 'unix_socket_permissions'])   # RF-24 (f): socket reachability
SECRET_VALUE_SETTINGS = ('ssl_passphrase_command',)
PG_SETTINGS_FIELDS = ('name', 'setting', 'unit', 'source', 'sourcefile', 'sourceline', 'boot_val', 'reset_val',
                      'pending_restart')


def _agg(fields, source, order):
    """One JSON array of row objects, deterministic order, '[]' when there are no rows."""
    pairs = ', '.join("'%s', %s" % (name, expr) for name, expr in fields)
    return ("SELECT coalesce(json_agg(json_build_object(%s) ORDER BY %s), '[]'::json) FROM %s"
            % (pairs, order, source))


_SETTING_FIELDS = [('name', 's.name'), ('setting', 's.setting'), ('unit', 's.unit'), ('source', 's.source'),
                   ('sourcefile', 's.sourcefile'), ('sourceline', 's.sourceline'), ('boot_val', 's.boot_val'),
                   ('reset_val', 's.reset_val'), ('pending_restart', 's.pending_restart')]
_NSP_FILTER = ("n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_toast%%' "
               "AND n.nspname NOT LIKE 'pg\\_temp\\_%%'").replace('%%', '%')
_HBA_COMMON = [('line_number', 'h.line_number'), ('type', 'h.type'), ('database', 'h.database'),
               ('user_name', 'h.user_name'), ('address', 'h.address'), ('netmask', 'h.netmask'),
               ('auth_method', 'h.auth_method'), ('options', 'h.options'), ('error', 'h.error')]
_IDENT_COMMON = [('line_number', 'i.line_number'), ('map_name', 'i.map_name'), ('sys_name', 'i.sys_name'),
                 ('pg_username', 'i.pg_username'), ('error', 'i.error')]
_SUB_COMMON = [('subname', 's.subname'), ('subowner', 'pg_catalog.pg_get_userbyid(s.subowner)'),
               ('subenabled', 's.subenabled'), ('subslotname', 's.subslotname'),   # RF-24 (a): no subconninfo
               ('subsynccommit', 's.subsynccommit'), ('subpublications', 's.subpublications'),
               ('database', 'd.datname')]
_SUB_SOURCE = ('pg_catalog.pg_subscription s LEFT JOIN pg_catalog.pg_database d ON d.oid = s.subdbid')
# RF-24 (a): the subconninfo-free rows travel under their own snapshot key. The frozen derive reads
# catalog_snapshot.json#subscriptions as rows whose subconninfo was observed (its M8 conninfo defaults would then
# become premises); under this key it keeps the pg_subscription source missing, as on every least-privilege run.
SUB_KEY = 'subscriptions_observed'
# RF-24 (a) (b): fields the collector never reads under least privilege (DESIGN-RULINGS-002 ruling 20). Each is
# written into catalog_snapshot.json collection.not_observed_fields, so its absence is typed, never a silent gap.
NOT_OBSERVED_FIELDS = {
    'roles[].has_password': {
        'status': 'not_observed',
        'reason': 'not computed: whether a role has a stored credential is readable only from the superuser-only '
                  'catalog pg_authid (pg_roles shows a constant mask), and the collector reads no credential hash '
                  '(rulings 17 and 20)'},
    SUB_KEY + '[].subconninfo': {
        'status': 'not_observed',
        'reason': 'never selected: the column holds connection strings that can carry credentials and is withheld '
                  'from non-superusers by column privilege; every other pg_subscription column is read (rulings 17 '
                  'and 20)'},
}
_MEMBER_COMMON = [('roleid', 'pg_catalog.pg_get_userbyid(m.roleid)'),
                  ('member', 'pg_catalog.pg_get_userbyid(m.member)'),
                  ('grantor', 'pg_catalog.pg_get_userbyid(m.grantor)'), ('admin_option', 'm.admin_option')]
_MEMBER_ORDER = ('pg_catalog.pg_get_userbyid(m.roleid), pg_catalog.pg_get_userbyid(m.member), '
                 'pg_catalog.pg_get_userbyid(m.grantor)')


def _q(qid, key, views, lo, hi, target, sql, purpose):
    return {'id': qid, 'key': key, 'views': views, 'min_major': lo, 'max_major': hi, 'target': target,
            'sql': sql, 'purpose': purpose}


QUERIES = [
    _q('collector_identity', None, ['pg_roles'], 14, 18, 'control',
       "SELECT json_build_object('current_user', current_user::text, 'session_user', session_user::text, "
       "'rolsuper', r.rolsuper, 'rolcanlogin', r.rolcanlogin, 'rolbypassrls', r.rolbypassrls, "
       "'rolcreaterole', r.rolcreaterole, 'rolcreatedb', r.rolcreatedb, 'rolreplication', r.rolreplication) "
       "FROM pg_catalog.pg_roles r WHERE r.rolname = current_user",
       'first read: the collection role row; superuser, a different role or no row is a typed refusal'),
    _q('server_version', None, [], 14, 18, 'control',
       "SELECT json_build_object('server_version_num', pg_catalog.current_setting('server_version_num'), "
       "'server_version', pg_catalog.current_setting('server_version'))",
       'major selects the version-gated queries; outside 14..18 is a typed refusal'),
    _q('collector_memberships', None, ['pg_auth_members', 'pg_roles'], 14, 18, 'control',
       "SELECT coalesce(json_agg(b.rolname::text ORDER BY b.rolname), '[]'::json) FROM pg_catalog.pg_auth_members m "
       "JOIN pg_catalog.pg_roles b ON b.oid = m.roleid JOIN pg_catalog.pg_roles u ON u.oid = m.member "
       "WHERE u.rolname = current_user",
       'the grants actually provisioned to the collection role (compared with --privileges in the sidecar)'),
    _q('session_settings', None, [], 14, 18, 'control',                                                          # RF-28 (e)
       "SELECT json_build_object('transaction_read_only', pg_catalog.current_setting('transaction_read_only'), "  # RF-28 (e)
       "'default_transaction_read_only', pg_catalog.current_setting('default_transaction_read_only'), "           # RF-28 (e)
       "'client_addr', pg_catalog.inet_client_addr()::text)",                                                     # RF-28 (e)
       'session fact, observed only: the effective read-only settings and the client address of this session '    # RF-28 (e)
       '(a failure is a recorded gap, never a refusal)'),                                                          # RF-28 (e)
    _q('session_tls', None, ['pg_stat_ssl'], 14, 18, 'control',                                                  # RF-28 (e)
       "SELECT json_build_object('row', (SELECT json_build_object('ssl', s.ssl, 'version', s.version, "           # RF-28 (e)
       "'cipher', s.cipher, 'bits', s.bits) FROM pg_catalog.pg_stat_ssl s "                                       # RF-28 (e)
       "WHERE s.pid = pg_catalog.pg_backend_pid()))",                                                             # RF-28 (e)
       "session fact, observed only: this backend's own pg_stat_ssl row, row null when the backend has none "     # RF-28 (e)
       '(a failure is a recorded gap, never a refusal)'),                                                          # RF-28 (e)
    _q('file_locations', None, ['pg_settings'], 14, 18, 'control',
       "SELECT coalesce(json_object_agg(s.name, s.setting ORDER BY s.name), '{}'::json) FROM pg_catalog.pg_settings s "
       "WHERE s.name IN ('config_file', 'hba_file', 'ident_file', 'data_directory')",
       'where the server says its configuration files are (remapped onto --data-dir when they lie under it)'),
    _q('server_times', None, [], 14, 18, 'timing',
       "SELECT json_build_object('pg_conf_load_time', pg_catalog.pg_conf_load_time()::text, "
       "'pg_postmaster_start_time', pg_catalog.pg_postmaster_start_time()::text)",
       'volatile; written only to TIMING.json (configuration load time, start time)'),
    _q('command_line_settings', None, ['pg_settings'], 14, 18, 'command_line',
       _agg(_SETTING_FIELDS, "pg_catalog.pg_settings s WHERE s.source IN ('command line', 'environment variable')",
            's.name'),
       'settings whose source is the server command line or environment (raw/command_line.json)'),
    _q('roles', 'roles', ['pg_roles'], 14, 18, 'catalog_snapshot',
       _agg([('rolname', 'r.rolname::text'), ('rolsuper', 'r.rolsuper'), ('rolinherit', 'r.rolinherit'),
             ('rolcreaterole', 'r.rolcreaterole'), ('rolcreatedb', 'r.rolcreatedb'),
             ('rolreplication', 'r.rolreplication'), ('rolbypassrls', 'r.rolbypassrls'),
             ('rolcanlogin', 'r.rolcanlogin'), ('rolconnlimit', 'r.rolconnlimit'),
             ('rolvaliduntil', 'r.rolvaliduntil'), ('bootstrap', 'r.oid = 10')],   # RF-24 (b): bootstrap flag
            'pg_catalog.pg_roles r', 'r.rolname'),
       'roles (pg_roles; the password column is never selected; bootstrap marks the bootstrap superuser, oid 10; '
       'RF-24 (b))'),
    _q('memberships_14_15', 'memberships', ['pg_auth_members'], 14, 15, 'catalog_snapshot',
       _agg(_MEMBER_COMMON, 'pg_catalog.pg_auth_members m', _MEMBER_ORDER),
       'role memberships, majors 14-15 (no inherit_option/set_option columns)'),
    _q('memberships_16_18', 'memberships', ['pg_auth_members'], 16, 18, 'catalog_snapshot',
       _agg(_MEMBER_COMMON + [('inherit_option', 'm.inherit_option'), ('set_option', 'm.set_option')],
            'pg_catalog.pg_auth_members m', _MEMBER_ORDER),
       'role memberships, majors 16-18 (inherit_option, set_option)'),
    _q('objects', 'objects', ['pg_class', 'pg_namespace', 'pg_rewrite', 'pg_depend'], 14, 18, 'catalog_snapshot',
       _agg([('relname', 'c.relname::text'), ('schema', 'n.nspname::text'), ('relkind', 'c.relkind::text'),
             ('owner', 'pg_catalog.pg_get_userbyid(c.relowner)'), ('relacl', 'c.relacl::text[]'),
             ('relrowsecurity', 'c.relrowsecurity'), ('relforcerowsecurity', 'c.relforcerowsecurity'),
             ('reloptions', 'c.reloptions'),
             ('base_tables', "CASE WHEN c.relkind IN ('v', 'm') THEN (SELECT coalesce(json_agg(DISTINCT t.relname::text), "
                             "'[]'::json) FROM pg_catalog.pg_rewrite w JOIN pg_catalog.pg_depend d "
                             "ON d.classid = 'pg_catalog.pg_rewrite'::regclass AND d.objid = w.oid "
                             "AND d.refclassid = 'pg_catalog.pg_class'::regclass JOIN pg_catalog.pg_class t "
                             "ON t.oid = d.refobjid WHERE w.ev_class = c.oid AND t.oid <> c.oid) ELSE NULL END")],
            'pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
            "WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S') AND " + _NSP_FILTER, 'n.nspname, c.relname'),
       'relations with ACL, owner and RLS flags; views and materialized views with their base tables'),
    _q('default_acl', 'default_acl', ['pg_default_acl', 'pg_namespace'], 14, 18, 'catalog_snapshot',
       _agg([('defaclrole', 'pg_catalog.pg_get_userbyid(d.defaclrole)'), ('defaclnamespace', 'n.nspname::text'),
             ('defaclobjtype', 'd.defaclobjtype::text'), ('defaclacl', 'd.defaclacl::text[]')],
            'pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace',
            'pg_catalog.pg_get_userbyid(d.defaclrole), n.nspname NULLS FIRST, d.defaclobjtype'),
       'default privileges (global rows have defaclnamespace null)'),
    _q('policies', 'policies', ['pg_policy', 'pg_class', 'pg_namespace'], 14, 18, 'catalog_snapshot',
       _agg([('polname', 'p.polname::text'), ('polrelid', 'c.relname::text'), ('schema', 'n.nspname::text'),
             ('polcmd', 'p.polcmd::text'), ('polpermissive', 'p.polpermissive'),
             ('polroles', "(SELECT json_agg(CASE WHEN u.r = 0 THEN 'public' ELSE pg_catalog.pg_get_userbyid(u.r)::text "
                          "END ORDER BY u.i) FROM unnest(p.polroles) WITH ORDINALITY AS u(r, i))"),
             ('polqual', 'pg_catalog.pg_get_expr(p.polqual, p.polrelid)'),
             ('polwithcheck', 'pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid)')],
            'pg_catalog.pg_policy p JOIN pg_catalog.pg_class c ON c.oid = p.polrelid '
            'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace', 'n.nspname, c.relname, p.polname'),
       'row-level security policies (relation by name, roles by name, expressions deparsed)'),
    # serve-065 (R-A item 3, 3488 / 3492): table inheritance and partitioning, so a reader can tell when a parent's
    # row-level security covers a child (derive_observed gap (6)); identical rows on 14.24 / 15.19 / 16.15 / 17.11 /
    # 18.6 (3498)
    _q('inherits', 'inherits', ['pg_inherits', 'pg_class', 'pg_namespace'], 14, 18, 'catalog_snapshot',
       _agg([('child', 'c.relname::text'), ('child_schema', 'cn.nspname::text'), ('parent', 'p.relname::text'),
             ('parent_schema', 'pn.nspname::text'), ('seqno', 'i.inhseqno'), ('detach_pending', 'i.inhdetachpending')],
            'pg_catalog.pg_inherits i JOIN pg_catalog.pg_class c ON c.oid = i.inhrelid '
            'JOIN pg_catalog.pg_namespace cn ON cn.oid = c.relnamespace '
            'JOIN pg_catalog.pg_class p ON p.oid = i.inhparent '
            'JOIN pg_catalog.pg_namespace pn ON pn.oid = p.relnamespace', 'cn.nspname, c.relname, i.inhseqno'),
       'table inheritance and partitions (child and parent by schema and name; detach_pending from 14)'),
    _q('functions', 'functions', ['pg_proc', 'pg_namespace'], 14, 18, 'catalog_snapshot',
       _agg([('proname', 'p.proname::text'), ('schema', 'n.nspname::text'),
             ('arguments', 'pg_catalog.pg_get_function_identity_arguments(p.oid)'), ('prokind', 'p.prokind::text'),
             ('prosecdef', 'p.prosecdef'), ('proconfig', 'p.proconfig'), ('proacl', 'p.proacl::text[]'),
             ('proowner', 'pg_catalog.pg_get_userbyid(p.proowner)')],
            'pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE '
            "n.nspname NOT IN ('pg_catalog', 'information_schema')",
            'n.nspname, p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)'),
       'functions and procedures outside pg_catalog/information_schema: owner, SECURITY DEFINER, proconfig, ACL'),
    # serve-076 (M-U4 + M-U6, 3806 / 3817): which functions an extension maintains, so the observed reading can name
    # them as the extension's (owner_class `extension`) instead of the customer's. Same schema filter and identity
    # arguments as `functions`, so each row matches one `functions` row; class is read through pg_class, so it does
    # not depend on the session's search_path
    _q('extension_members', 'extension_members', ['pg_depend', 'pg_extension', 'pg_proc', 'pg_namespace', 'pg_class'],
       14, 18, 'catalog_snapshot',
       _agg([('class', '(SELECT k.relname::text FROM pg_catalog.pg_class k WHERE k.oid = d.classid)'),
             ('extname', 'e.extname::text'), ('schema', 'n.nspname::text'), ('name', 'p.proname::text'),
             ('arguments', 'pg_catalog.pg_get_function_identity_arguments(p.oid)')],
            'pg_catalog.pg_depend d JOIN pg_catalog.pg_extension e ON e.oid = d.refobjid '
            "AND d.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass "
            "JOIN pg_catalog.pg_proc p ON d.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass AND p.oid = d.objid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE d.deptype = 'e' AND "
            "n.nspname NOT IN ('pg_catalog', 'information_schema')",
            'e.extname, n.nspname, p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)'),
       'functions an extension maintains (pg_depend deptype e), outside pg_catalog/information_schema'),
    _q('schemas', 'schemas', ['pg_namespace'], 14, 18, 'catalog_snapshot',
       _agg([('nspname', 'n.nspname::text'), ('nspowner', 'pg_catalog.pg_get_userbyid(n.nspowner)'),
             ('nspacl', 'n.nspacl::text[]')],
            "pg_catalog.pg_namespace n WHERE n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp\\_%'",
            'n.nspname'),
       'schemas with owner and ACL'),
    _q('replication_slots', 'replication_slots', ['pg_replication_slots'], 14, 18, 'catalog_snapshot',
       _agg([('slot_name', 'r.slot_name::text'), ('plugin', 'r.plugin::text'), ('slot_type', 'r.slot_type'),
             ('database', 'r.database::text'), ('temporary', 'r.temporary'), ('active', 'r.active'),
             ('wal_status', 'r.wal_status'), ('safe_wal_size', 'r.safe_wal_size'),
             ('restart_lsn', 'r.restart_lsn::text')], 'pg_catalog.pg_replication_slots r', 'r.slot_name'),
       'replication slots'),
    _q('publications', 'publications', ['pg_publication'], 14, 18, 'catalog_snapshot',
       _agg([('pubname', 'p.pubname::text'), ('pubowner', 'pg_catalog.pg_get_userbyid(p.pubowner)'),
             ('puballtables', 'p.puballtables'), ('pubinsert', 'p.pubinsert'), ('pubupdate', 'p.pubupdate'),
             ('pubdelete', 'p.pubdelete'), ('pubtruncate', 'p.pubtruncate'), ('pubviaroot', 'p.pubviaroot')],
            'pg_catalog.pg_publication p', 'p.pubname'),
       'publications'),
    _q('publication_rels', 'publication_rels', ['pg_publication_rel', 'pg_publication', 'pg_class'], 14, 18,
       'catalog_snapshot',
       _agg([('pubname', 'p.pubname::text'), ('relname', 'c.relname::text'), ('schema', 'n.nspname::text')],
            'pg_catalog.pg_publication_rel pr JOIN pg_catalog.pg_publication p ON p.oid = pr.prpubid '
            'JOIN pg_catalog.pg_class c ON c.oid = pr.prrelid JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace',
            'p.pubname, n.nspname, c.relname'),
       'tables named by publications'),
    _q('publication_namespaces', 'publication_namespaces', ['pg_publication_namespace'], 15, 18, 'catalog_snapshot',
       _agg([('pubname', 'p.pubname::text'), ('nspname', 'n.nspname::text')],
            'pg_catalog.pg_publication_namespace pn JOIN pg_catalog.pg_publication p ON p.oid = pn.pnpubid '
            'JOIN pg_catalog.pg_namespace n ON n.oid = pn.pnnspid', 'p.pubname, n.nspname'),
       'schemas named by publications (catalog exists from major 15)'),
    _q('subscriptions_14_15', SUB_KEY, ['pg_subscription'], 14, 15, 'catalog_snapshot',   # RF-24 (a): own key
       _agg(_SUB_COMMON, _SUB_SOURCE, 's.subname'),
       'subscriptions, majors 14-15 (subconninfo is never selected; RF-24 (a))'),
    _q('subscriptions_16_18', SUB_KEY, ['pg_subscription'], 16, 18, 'catalog_snapshot',   # RF-24 (a): own key
       _agg(_SUB_COMMON + [('subpasswordrequired', 's.subpasswordrequired'), ('subrunasowner', 's.subrunasowner')],
            _SUB_SOURCE, 's.subname'),
       'subscriptions, majors 16-18 (subconninfo is never selected; RF-24 (a))'),
    _q('subscription_rels', 'subscription_rels', ['pg_subscription_rel', 'pg_subscription', 'pg_class'], 14, 18,
       'catalog_snapshot',
       _agg([('subname', 's.subname::text'), ('relname', 'c.relname::text'), ('schema', 'n.nspname::text'),
             ('srsubstate', 'sr.srsubstate::text')],
            'pg_catalog.pg_subscription_rel sr JOIN pg_catalog.pg_subscription s ON s.oid = sr.srsubid '
            'JOIN pg_catalog.pg_class c ON c.oid = sr.srrelid JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace',
            's.subname, n.nspname, c.relname'),
       'subscription target tables (attached to subscriptions[].tables when both reads succeed)'),
    _q('pg_settings', 'pg_settings', ['pg_settings'], 14, 18, 'catalog_snapshot',
       _agg(_SETTING_FIELDS, 'pg_catalog.pg_settings s WHERE s.name IN (%s)'
            % ', '.join("'%s'" % name for name in SETTINGS_COLLECTED), 's.name'),
       'settings with source, sourcefile and sourceline for the fixed setting list'),
    _q('pg_file_settings', 'pg_file_settings', ['pg_file_settings'], 14, 18, 'catalog_snapshot',
       _agg([('sourcefile', 'f.sourcefile'), ('sourceline', 'f.sourceline'), ('seqno', 'f.seqno'),
             ('name', 'f.name'), ('setting', 'f.setting'), ('applied', 'f.applied'), ('error', 'f.error')],
            'pg_catalog.pg_file_settings f', 'f.seqno'),
       'configuration file rows and error rows (current file contents)'),
    _q('pg_hba_file_rules_14_15', 'pg_hba_file_rules', ['pg_hba_file_rules'], 14, 15, 'catalog_snapshot',
       _agg(_HBA_COMMON, 'pg_catalog.pg_hba_file_rules h', 'h.line_number'),
       'pg_hba rules and error rows as parsed from the current file, majors 14-15'),
    _q('pg_hba_file_rules_16_18', 'pg_hba_file_rules', ['pg_hba_file_rules'], 16, 18, 'catalog_snapshot',
       _agg([('rule_number', 'h.rule_number'), ('file_name', 'h.file_name')] + _HBA_COMMON,
            'pg_catalog.pg_hba_file_rules h', 'h.file_name, h.line_number'),
       'pg_hba rules and error rows as parsed from the current files (with includes), majors 16-18'),
    _q('pg_ident_file_mappings_15', 'pg_ident_file_mappings', ['pg_ident_file_mappings'], 15, 15,
       'catalog_snapshot', _agg(_IDENT_COMMON, 'pg_catalog.pg_ident_file_mappings i', 'i.line_number'),
       'pg_ident mappings and error rows, major 15 (view exists from major 15)'),
    _q('pg_ident_file_mappings_16_18', 'pg_ident_file_mappings', ['pg_ident_file_mappings'], 16, 18,
       'catalog_snapshot',
       _agg([('map_number', 'i.map_number'), ('file_name', 'i.file_name')] + _IDENT_COMMON,
            'pg_catalog.pg_ident_file_mappings i', 'i.file_name, i.line_number'),
       'pg_ident mappings and error rows (with includes), majors 16-18'),
    _q('pg_db_role_setting', 'pg_db_role_setting', ['pg_db_role_setting', 'pg_database', 'pg_roles'], 14, 18,
       'catalog_snapshot',
       _agg([('setdatabase', 'd.datname::text'), ('setrole', 'r.rolname::text'), ('setconfig', 's.setconfig')],
            'pg_catalog.pg_db_role_setting s LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase '
            'LEFT JOIN pg_catalog.pg_roles r ON r.oid = s.setrole', 'd.datname NULLS FIRST, r.rolname NULLS FIRST'),
       'per-role and per-database settings (null database or role means all)'),
    _q('databases', 'databases', ['pg_database'], 14, 18, 'catalog_snapshot',
       _agg([('datname', 'd.datname::text'), ('owner', 'pg_catalog.pg_get_userbyid(d.datdba)'),
             ('datallowconn', 'd.datallowconn'), ('datistemplate', 'd.datistemplate'),
             ('datacl', 'd.datacl::text[]'), ('is_current', 'd.datname = current_database()')],
            'pg_catalog.pg_database d', 'd.datname'),
       'databases (is_current marks the database the catalog reads were made in)'),
]
CATALOG_KEYS = list(dict.fromkeys(q['key'] for q in QUERIES if q['key']))


def render_queries():
    doc = dict(FLAGS, schema='symbolia.rf06.pg-collector-queries.v1', majors=list(MAJORS),
               output_contract='each query returns exactly one JSON value on stdout (psql -At)',
               read_only='every query is a single SELECT; the default runner session sets '
                         'default_transaction_read_only=on; nothing is retried, never as another role',
               secret_keywords='SECRET-KEYWORDS.json', queries=QUERIES)
    return json.dumps(doc, indent=2, ensure_ascii=False) + '\n'


# ---------------------------------------------------------------- runner
_PSQL = {'argv': None, 'env': None}


def build_psql_command(psql, login):          # RF-28 (d): -U takes the login name (--login-user, default --role)
    argv = shlex.split(psql or 'psql') + ['-X', '-At', '-F', SEP, '-w', '-v', 'ON_ERROR_STOP=1', '-U', login]   # RF-28 (d)
    env = dict(os.environ)
    prior = env.get('PGOPTIONS', '').strip()
    env['PGOPTIONS'] = (prior + ' ' if prior else '') + '-c default_transaction_read_only=on'
    env['PGAPPNAME'] = 'symbolia-rf06-readonly-collector'
    return argv, env


def psql_runner(sql):
    if _PSQL['argv'] is None:
        return 2, '', 'psql runner not configured'
    try:
        run = subprocess.run(_PSQL['argv'] + ['-c', sql], env=_PSQL['env'], capture_output=True, text=True,
                             timeout=120)
    except FileNotFoundError:
        return 127, '', 'psql executable not found'
    except subprocess.TimeoutExpired:
        return 124, '', 'psql timed out after 120 s'
    return run.returncode, run.stdout, run.stderr


RUNNER = psql_runner


class Refusal(Exception):
    def __init__(self, kind, reason, code=3):
        super().__init__(reason)
        self.kind, self.reason, self.code = kind, reason, code


# ---------------------------------------------------------------- redaction
SECRET_KEYS = ('password', 'sslpassword', 'passfile')
HBA_SECRET_OPTIONS = ('ldapbindpasswd', 'radiussecrets', 'radiussecret')
# The secret keyword list, pinned per major to the libpq parameter documentation (published as SECRET-KEYWORDS.json).
# Documentation pointers are the PostgreSQL manual's section anchors as the author reads them; the network was closed,
# so no page was fetched for this follow-up. Over-redaction is the safe side: any keyword whose name contains one of
# SECRET_NAME_WORDS is a secret keyword too, whatever the major, unless it is a named non-secret setting.
_DOC = 'https://www.postgresql.org/docs/%d/libpq-connect.html#LIBPQ-PARAMKEYWORDS (%s)'
SECRET_KEYWORDS = [
    {'keyword': 'password', 'majors': [14, 15, 16, 17, 18], 'kind': 'libpq connection parameter',
     'documentation': [_DOC % (m, 'LIBPQ-CONNECT-PASSWORD') for m in range(14, 19)]},
    {'keyword': 'passfile', 'majors': [14, 15, 16, 17, 18], 'kind': 'libpq connection parameter (a path; withheld '
     'because the brief lists it with the password fields)',
     'documentation': [_DOC % (m, 'LIBPQ-CONNECT-PASSFILE') for m in range(14, 19)]},
    {'keyword': 'sslpassword', 'majors': [14, 15, 16, 17, 18], 'kind': 'libpq connection parameter',
     'documentation': [_DOC % (m, 'LIBPQ-CONNECT-SSLPASSWORD') for m in range(14, 19)]},
    {'keyword': 'oauth_client_secret', 'majors': [18], 'kind': 'libpq connection parameter (new in 18)',
     'documentation': [_DOC % (18, 'LIBPQ-CONNECT-OAUTH-CLIENT-SECRET')]},
    {'keyword': 'scram_client_key', 'majors': [18], 'kind': 'libpq connection parameter used by SCRAM pass-through '
     '(author recollection of the 18 source; withheld conservatively)',
     'documentation': ['https://www.postgresql.org/docs/18/postgres-fdw.html (use_scram_passthrough); not in the '
                       'libpq-connect keyword list as the author recalls it']},
    {'keyword': 'scram_server_key', 'majors': [18], 'kind': 'libpq connection parameter used by SCRAM pass-through '
     '(author recollection of the 18 source; withheld conservatively)',
     'documentation': ['https://www.postgresql.org/docs/18/postgres-fdw.html (use_scram_passthrough); not in the '
                       'libpq-connect keyword list as the author recalls it']},
]
HBA_SECRET_KEYWORDS = [
    {'option': 'ldapbindpasswd', 'majors': [14, 15, 16, 17, 18],
     'documentation': ['https://www.postgresql.org/docs/%d/auth-ldap.html' % m for m in range(14, 19)]},
    {'option': 'radiussecrets', 'majors': [14, 15, 16, 17, 18],
     'documentation': ['https://www.postgresql.org/docs/%d/auth-radius.html' % m for m in range(14, 19)]},
]
SECRET_NAME_WORDS = ('password', 'passwd', 'passphrase', 'secret', 'token')
NON_SECRET_NAMES = ('password_encryption', 'ssl_passphrase_command_supports_reload', 'md5_password_warnings',
                    'password_required')
_SECRET_NAMES = frozenset(k['keyword'] for k in SECRET_KEYWORDS) | frozenset(k['option'] for k in HBA_SECRET_KEYWORDS)
_KW_CHARS = r'A-Za-z0-9_.%-'
SECRET_KW_RE = re.compile(r'(?i)(?<![%s])([%s]*?(?:%s)[%s]*)\s*=' % (
    _KW_CHARS, _KW_CHARS, '|'.join(SECRET_NAME_WORDS + tuple(sorted(_SECRET_NAMES))), _KW_CHARS))
# a URI whose userinfo (everything before an '@' that precedes the first '/') holds a ':' -> a password
SECRET_URI_RE = re.compile(r'(?i)postgres(?:ql)?://(?:[^/]*:[^/]*@|[^/@?]*:[^@?]*/[^?]*@)')
URI_PREFIX_RE = re.compile(r'(?i)^(\s*postgres(?:ql)?://)')
MAX_NEST = 4


def is_secret_keyword(name):
    """True for a libpq keyword, URI parameter keyword (percent-decoded) or pg_hba option name that carries a secret."""
    if not isinstance(name, str):
        return False
    norm = unquote(name).strip().lower()
    if norm in NON_SECRET_NAMES:
        return False
    return norm in _SECRET_NAMES or any(word in norm for word in SECRET_NAME_WORDS)


def render_secret_keywords():
    doc = dict(FLAGS, schema='symbolia.rf06.secret-keywords.v1', majors=list(range(MAJORS[0], MAJORS[1] + 1)),
               keywords=SECRET_KEYWORDS, hba_options=HBA_SECRET_KEYWORDS, name_contains=list(SECRET_NAME_WORDS),
               non_secret_names=list(NON_SECRET_NAMES), conninfo_class=CONNINFO_CLASS,
               hba_option_allowlist=list(HBA_OPTION_ALLOWLIST), withheld_value_marker=WITHHELD_VALUE,
               withheld_option_marker=WITHHELD_OPTION, safe_value_charset=SAFE_VALUE_RE.pattern,
               safe_literals={name: rx.pattern for name, rx in sorted(SAFE_LITERALS.items())},
               structure_words=list(STRUCTURE_WORDS),
               safe_url_grammar=SAFE_URL_RE.pattern, uri_userinfo_rule=URI_USERINFO_RE.pattern,
               custom_guc_allowlist=CUSTOM_GUC_ALLOWLIST_DOCS, line_unsafe_characters=LINE_UNSAFE_RE.pattern,
               follow_up_5_rules=('lines are split on \\n only (hba/ident: one trailing \\r stripped); a retained '
                                  'conf/hba/ident line holding a character of line_unsafe_characters is withheld whole; '
                                  'any string holding :// is withheld whole unless it fully matches safe_url_grammar; '
                                  'a URI with userinfo (uri_userinfo_rule, any scheme) is a secret pattern; a dotted '
                                  '(custom) GUC value is withheld whole unless its full name is in custom_guc_allowlist '
                                  '(manifest reason custom_guc); every refusal removes every output byte first'),
               follow_up_6_rule=('safe_url_grammar now also admits lower-case ldap:// and ldaps:// URLs: host, '
                                 'optional port, and a DN path whose characters are [A-Za-z0-9=,._/-] (= and , '
                                 'only in the ldap(s) branch); no userinfo, ?, #, %, @, [ or whitespace. A pg_hba '
                                 'ldapurl value holding :// is judged by safe_url_grammar alone (not by '
                                 'safe_value_charset, which does not widen), after the structure-word test. The '
                                 'one quoted option spelling retained is ldapurl="<url>" with the url matching '
                                 'safe_url_grammar, because hba.c ends an unquoted token at a comma. A '
                                 'pg_hba_file_rules ldapurl item may hold a comma under the same grammar. Every '
                                 'other option is judged as in follow-up 5; ldapbinddn with = or , is still '
                                 'withheld.'),
               inversion_rule='follow-up 4: a conf or setting value is retained only when its decoded form (GUC_scanstr) '
                              'is empty, or its name is not in conninfo_class and not secret-named and the value holds '
                              'no =, no :// and no structure_words substring and matches safe_value_charset (after '
                              'safe_literals); otherwise the WHOLE value becomes withheld_value_marker. A pg_hba option '
                              'is retained only when its name is in hba_option_allowlist and its value is one unquoted '
                              'token without comma or backslash matching safe_value_charset; otherwise the WHOLE option '
                              'becomes withheld_option_marker. Any other string that parses as a libpq conninfo or URI is '
                              'withheld whole. Nothing is stripped out of a value.',
               rule='a conninfo keyword, URI parameter (percent-decoded) or pg_hba option is secret when it is listed '
                    'here or its lower-cased name contains one of name_contains and is not in non_secret_names; the '
                    'whole value is removed. Pointers are documentation anchors as the author reads them (network '
                    'closed: not fetched in this follow-up); the name rule makes the list conservative.')
    return json.dumps(doc, indent=2, ensure_ascii=False) + '\n'
# ssl_passphrase_command in every spelling the server accepts on a command line or in a setting string:
# name=value (argv item, -c item, setconfig item), --ssl_passphrase_command=..., --ssl-passphrase-command=...
PASSPHRASE_NAME = r'ssl[_-]passphrase[_-]command'
# a passphrase-command assignment that still carries a value (empty '' or a closing quote is no value)
PASSPHRASE_SET_RE = re.compile(r"(?i)%s\s*=\s*(?:[^\s'\"#]|'[^']|\"[^\s\"])" % PASSPHRASE_NAME)
PASSPHRASE_ITEM_RE = re.compile(r'(?is)^(\s*(?:-c\s*|--?)?%s\s*=)(.*)$' % PASSPHRASE_NAME)
PASSPHRASE_QUOTED_RE = re.compile(r'(?i)(["\'])((?:-c\s*|--?)?%s\s*=)' % PASSPHRASE_NAME)
KV_RE = re.compile(r"(\s*)([A-Za-z_]\w*)(\s*=\s*)('(?:[^'\\]|\\.)*'?|\S*)")
URI_RE_FU2 = re.compile(r'^(\s*postgres(?:ql)?://)([^@/?#]*@)?([^?#]*)(\?[^#]*)?(#.*)?$', re.S)
HBA_OPTION_RE = re.compile(r'(\s+)(ldapbindpasswd|radiussecrets|radiussecret)=("[^"]*"|\S*)', re.I)
REDACTED_LINE = '# [collect_pg: line withheld, an authentication secret pattern could not be stripped field by field]'
# RF-28 (a): REDACTED_LINE above now appears only in error text inside the sidecar; no retained file holds it. A
# withheld rule, setting or other parsed line is written as a whole-line marker that is NOT a comment in the file's
# grammar (MARKER-CONTRACT-001.md). It starts with '!': no setting name and no pg_hba record type or include keyword
# starts with it, so the frozen parse_conf reports 'unparseable line' and the frozen parse_hba 'malformed record'. It
# holds the physical line number, a closed reason code and, for a setting whose name is safe, that name; it holds no
# '=', quote, comma or '#'. A withheld COMMENT line stays a comment (WITHHELD_COMMENT): it decides nothing.
MARKER_PREFIX = '!collect_pg-withheld'                                                    # RF-28 (a)
MARKER_RE = re.compile(r'!collect_pg-withheld line ([1-9][0-9]{0,8}) reason ([A-Z][A-Z0-9-]+)'
                       r'(?: setting ([a-z_][a-z0-9_.]{0,62}))?')                         # RF-28 (a)
MARKER_SETTING_RE = re.compile(r'[a-z_][a-z0-9_.]{0,62}')                                 # RF-28 (a)
MARKER_REASONS = {                                                                        # RF-28 (a): closed list
    'HBA-UNTERMINATED-QUOTE': 'pg_hba: a double quote opens a token that does not close on the line',
    'HBA-POSITIONAL': 'pg_hba: the record type, field count or a positional field is not retainable',
    'HBA-OVER-LENGTH': 'pg_hba: the logical record is longer than HBA_LINE_MAX characters',
    'HBA-SECRET-LEFT': 'pg_hba: a secret pattern is left after options were withheld',
    'HBA-CONTROL-CHARACTER': 'pg_hba: the line holds a control or line-separator character',
    'HBA-CONTINUATION': 'pg_hba: a physical line of a backslash-continued record that is withheld',
    'CONF-UNPARSED-LINE': 'postgresql.conf: a line that is not a setting and holds a secret pattern',
    'CONF-UNTERMINATED-VALUE': 'postgresql.conf: a quoted value that does not close on the line',
    'CONF-TRAILING-TEXT': 'postgresql.conf: text that is not a comment follows the value',
    'CONF-SECRET-LEFT': 'postgresql.conf: a secret pattern is left after the value was withheld',
    'CONF-CONTROL-CHARACTER': 'postgresql.conf: the line holds a control or line-separator character',
    'PLAIN-SECRET-PATTERN': 'other parsed file (@file list, pg_ident.conf): the line holds a secret pattern',
    'PLAIN-CONTROL-CHARACTER': 'other parsed file: the line holds a control or line-separator character',
    'MARKER-COLLISION': 'any grammar: the source line itself starts with the marker prefix',
    'HBA-TRAILING-BACKSLASH': 'pg_hba: a retained record would end in a backslash followed by blanks',   # RF-28 (a)
    'PLAIN-TRAILING-BACKSLASH': 'other parsed file: a line ends in a backslash followed by blanks',     # RF-28 (a)
}
LINE_REASONS = {                                                                          # RF-28 (b): closed list
    'COMMENT-WITHHELD': 'a comment line replaced whole by WITHHELD_COMMENT; it stays a comment',
    'TRAILING-COMMENT-WITHHELD': 'a trailing comment replaced by WITHHELD_COMMENT; the line before it is kept',
    'CONF-VALUE-WITHHELD': "a setting value replaced in place by '<withheld: structured value>'",
    'HBA-OPTION-WITHHELD': "a pg_hba auth-option replaced in place by '<withheld option>'",
    'JSON-VALUE-WITHHELD': 'a value inside a JSON output file (no line number)',
}
COLLISION_LABEL = 'line:withheld (source line in the collector marker form)'              # RF-28 (a)
Whole = namedtuple('Whole', 'reason setting comment')     # RF-28 (a): a line withheld whole, before its number is known


def marker_line(number, reason, setting=None):
    """RF-28 (a): the marker for physical line `number`; `setting` is shown only when it is a safe name."""
    if reason not in MARKER_REASONS or not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError('marker_line needs a line number of 1 or more and a reason from MARKER_REASONS')
    text = '%s line %d reason %s' % (MARKER_PREFIX, number, reason)
    if isinstance(setting, str) and MARKER_SETTING_RE.fullmatch(setting):
        text += ' setting ' + setting
    return text


def parse_marker(text):
    """RF-28 (a): (line, reason, setting or None) for a line that is exactly a marker, else None."""
    match = MARKER_RE.fullmatch(text) if isinstance(text, str) else None
    if not match or match.group(2) not in MARKER_REASONS:
        return None
    return int(match.group(1)), match.group(2), match.group(3)


def _starts_marker(body):
    """RF-28 (a): True when a line, after blanks, starts with the marker prefix."""
    return body.lstrip(' \t\r').startswith(MARKER_PREFIX)


BACKSLASH_BLANK_LABEL = 'line:withheld (backslash followed by blanks at the end of the line)'    # RF-28 (a)


def _backslash_blank(text):
    """RF-28 (a) FIX-2: True when a line ends in a backslash followed by blanks. The server joins a pg_hba line only
    when its last character is a backslash; the frozen parse_hba joins when line.rstrip() ends in one (Python's
    rstrip also removes U+00A0, U+3000 and other blanks). A retained line of this shape would join the next line in
    that reader, and a marker there would be read as comment text, so no retained line ends this way."""
    return not text.endswith('\\') and text.rstrip().endswith('\\')


def _inline_reason(label):
    """RF-28 (b): the reason code of a label withheld inside a retained line."""
    if label.startswith('hba option:'):
        return 'HBA-OPTION-WITHHELD'
    if ':comment:withheld_whole' in label:
        return 'TRAILING-COMMENT-WITHHELD'
    return 'CONF-VALUE-WITHHELD'


def _line_text(new, number, found, record):
    """RF-28 (a) (b): the retained text of physical line `number` (a marker or the comment form for a Whole), and one
    (line, label, reason) per label in `record` when a list is given."""
    if isinstance(new, Whole):
        reason = 'COMMENT-WITHHELD' if new.comment else new.reason
        text = WITHHELD_COMMENT if new.comment else marker_line(number, new.reason, new.setting)
    else:
        text, reason = new, None
    if record is not None:
        for label in found:
            record.append((number, label, reason or _inline_reason(label)))
    return text

# ---- follow-up 4: the inversion rule. Retain only values positively known to be safe; withhold everything else
# WHOLE. Nothing is ever stripped out of a value any more.
WITHHELD_VALUE = '<withheld: structured value>'
WITHHELD_OPTION = '<withheld option>'
WITHHELD_COMMENT = '# <withheld comment>'
SAFE_VALUE_RE = re.compile(r'^[A-Za-z0-9 ._:/,+-]*$')       # applied with fullmatch to the DECODED value
# ---- follow-up 5. (1) Any string holding '://' is withheld whole unless it is exactly a plain http(s) URL of this
# pinned grammar (no userinfo, port, query, fragment or percent sign); a URI with userinfo, whatever its scheme, is a
# secret pattern. (2) A retained configuration line never holds a C0/C1 control character (tab excepted) or U+2028/
# U+2029: a line-splitting difference between this tool and the server can then never leave a fragment behind.
# (3) A custom (dotted) GUC's value is withheld unless its full name is in CUSTOM_GUC_ALLOWLIST.
# ---- follow-up 6: the grammar admits plain lower-case ldap/ldaps URLs too (host, optional port, DN path with '='
# and ',' in the ldap(s) branch ONLY); http(s) gains the optional port of the brief's pattern and nothing else.
SAFE_URL_RE = re.compile(r'^(?:https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._/-]*)?'
                         r'|ldaps?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9=,._/-]*)?)$')
URI_USERINFO_RE = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*://[^/\s]*@')
URI_USERINFO_ANY_RE = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*://[^/\s]*@')     # the same rule, anywhere in a string
LINE_UNSAFE_RE = re.compile(r'[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029]')
_EXT = 'https://www.postgresql.org/docs/%d/%s'
CUSTOM_GUC_ALLOWLIST_DOCS = [
    {'name': 'pg_stat_statements.max', 'kind': 'integer (maximum number of statements tracked)',
     'documentation': [_EXT % (m, 'pgstatstatements.html#PGSTATSTATEMENTS-CONFIG-PARAMS') for m in range(14, 19)]},
    {'name': 'pg_stat_statements.track', 'kind': 'enum (top, all, none)',
     'documentation': [_EXT % (m, 'pgstatstatements.html#PGSTATSTATEMENTS-CONFIG-PARAMS') for m in range(14, 19)]},
    {'name': 'auto_explain.log_min_duration', 'kind': 'integer with time unit',
     'documentation': [_EXT % (m, 'auto-explain.html#AUTO-EXPLAIN-CONFIGURATION-PARAMETERS') for m in range(14, 19)]},
]
CUSTOM_GUC_ALLOWLIST = tuple(entry['name'] for entry in CUSTOM_GUC_ALLOWLIST_DOCS)


def is_custom_guc(name):
    """A dotted (extension or placeholder) GUC name that is not on the pinned allowlist."""
    norm = (name or '').strip().lower().replace('-', '_')
    return '.' in norm and norm not in CUSTOM_GUC_ALLOWLIST


def withhold_reason(name):
    return 'custom_guc' if isinstance(name, str) and is_custom_guc(name) else 'structured_or_unsafe_value'


def server_lines(data):
    """The physical lines of a configuration file exactly as the server breaks them: at '\\n' ONLY (guc-file.l and
    hba.c read to '\\n'; no other character ends a line). Bytes are split with bytes.split(b'\\n') and each line is
    decoded afterwards (UTF-8, surrogateescape); a str is split on '\\n' the same way. Every item but a final
    unterminated one keeps its '\\n'."""
    if isinstance(data, bytes):
        parts = [part.decode('utf-8', 'surrogateescape') for part in data.split(b'\n')]
    else:
        parts = data.split('\n')
    lines = [part + '\n' for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def hba_body(line):
    """An hba/ident physical line without its '\\n' and exactly ONE trailing '\\r' (hba.c strips only that)."""
    body = line[:-1] if line.endswith('\n') else line
    return body[:-1] if body.endswith('\r') else body


def conf_body(line):
    """A postgresql.conf physical line without its '\\n' and exactly ONE trailing '\\r'. RF-28 (a) FIX-2: as hba_body;
    a further '\\r' stays in the body, so the line is withheld (LINE_UNSAFE_RE) and every marker number stays the
    reader's own line number (read_text() reads '\\r\\r\\n' as two lines)."""
    body = line[:-1] if line.endswith('\n') else line                           # RF-28 (a)
    return body[:-1] if body.endswith('\r') else body                           # RF-28 (a)
# documented literal spellings retained for one setting each (the only exceptions to SAFE_VALUE_RE)
SAFE_LITERALS = {'listen_addresses': re.compile(r'\*'), 'search_path': re.compile(r'"\$user"')}
STRUCTURE_WORDS = ('password', 'secret', 'token', 'passphrase')
_RC = 'https://www.postgresql.org/docs/%d/runtime-config-%s.html#%s'
CONNINFO_CLASS = [
    {'name': 'primary_conninfo', 'kind': 'libpq connection string',
     'documentation': [_RC % (m, 'replication', 'GUC-PRIMARY-CONNINFO') for m in range(14, 19)]},
    {'name': 'ssl_passphrase_command', 'kind': 'shell command (may embed a passphrase)',
     'documentation': [_RC % (m, 'connection', 'GUC-SSL-PASSPHRASE-COMMAND') for m in range(14, 19)]},
    {'name': 'archive_command', 'kind': 'shell command (may embed credentials)',
     'documentation': [_RC % (m, 'wal', 'GUC-ARCHIVE-COMMAND') for m in range(14, 19)]},
    {'name': 'restore_command', 'kind': 'shell command (may embed credentials)',
     'documentation': [_RC % (m, 'wal', 'GUC-RESTORE-COMMAND') for m in range(14, 19)]},
    {'name': 'archive_cleanup_command', 'kind': 'shell command (may embed credentials)',
     'documentation': [_RC % (m, 'wal', 'GUC-ARCHIVE-CLEANUP-COMMAND') for m in range(14, 19)]},
    {'name': 'recovery_end_command', 'kind': 'shell command (may embed credentials)',
     'documentation': [_RC % (m, 'wal', 'GUC-RECOVERY-END-COMMAND') for m in range(14, 19)]},
]
for _entry in CONNINFO_CLASS:
    _entry['majors'] = [14, 15, 16, 17, 18]
CONNINFO_CLASS_GUCS = tuple(entry['name'] for entry in CONNINFO_CLASS)
HBA_OPTION_ALLOWLIST = ('map', 'clientcert', 'clientname', 'include_realm', 'krb_realm', 'compat_realm',
                        'upn_username', 'pamservice', 'pam_use_hostname', 'ldapserver', 'ldapport', 'ldapscheme',
                        'ldaptls', 'ldapprefix', 'ldapsuffix', 'ldapbasedn', 'ldapbinddn', 'ldapsearchattribute',
                        'ldapsearchfilter', 'ldapurl', 'radiusservers', 'radiusports', 'radiusidentifiers')
# libpq connection keywords 14-18 as the author reads the libpq-connect pages (not fetched: network closed); a string
# that parses as keyword/value with one of these (or a secret keyword) is a conninfo and is withheld whole
LIBPQ_KEYWORDS = frozenset((
    'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'passfile', 'require_auth', 'channel_binding',
    'connect_timeout', 'client_encoding', 'options', 'application_name', 'fallback_application_name', 'keepalives',
    'keepalives_idle', 'keepalives_interval', 'keepalives_count', 'tcp_user_timeout', 'replication', 'gssencmode',
    'sslmode', 'requiressl', 'sslnegotiation', 'sslcompression', 'sslcert', 'sslkey', 'sslkeylogfile',
    'sslpassword', 'sslcertmode', 'sslrootcert', 'sslcrl', 'sslcrldir', 'sslsni', 'requirepeer',
    'ssl_min_protocol_version', 'ssl_max_protocol_version', 'min_protocol_version', 'max_protocol_version',
    'krbsrvname', 'gsslib', 'gssdelegation', 'service', 'target_session_attrs', 'load_balance_hosts',
    'oauth_issuer', 'oauth_client_id', 'oauth_client_secret', 'oauth_scope'))


# Secret values met during one run, held in memory only and never written: the redaction self-check scans
# every retained byte for each of them (and for fragments of them) before the run may finish.
SELFCHECK_MIN = 6
_SECRETS = {'whole': set(), 'needles': set(), 'short': set()}
# RF-27 (e): database and user tokens (quotes removed) of the retained pg_hba records of this run, @file
# references excepted. A pg_hba_file_rules item equal to one of them is already in a retained file.
_HBA_RETAINED = set()
CONNINFO_SPACE = ' \t\n\r\v\f'          # libpq uses C isspace(), not Unicode whitespace
LOOSE_SECRET_RE = re.compile(r"(?i)(?:(?:ssl)?password|passfile|pg(?:ssl)?password)\s*=\s*")


def _reset_secrets():
    for bucket in _SECRETS.values():
        bucket.clear()
    _HBA_RETAINED.clear()                # RF-27 (e): retained pg_hba identifiers belong to one run


def _note_secret(value, command=False):
    """Remember a secret value (and its fragments) for the self-check; nothing is ever written from here."""
    if not isinstance(value, str) or not value.strip():
        return
    value = value.strip()
    if len(value) < SELFCHECK_MIN:
        _SECRETS['short'].add(value)
    else:
        _SECRETS['whole'].add(value)
        _SECRETS['needles'].add(value)
    for piece in re.split(r"[\s'\"\\@#?&]+", value):
        if len(piece) >= SELFCHECK_MIN and not (command and piece[:1] in '/-'):
            _SECRETS['needles'].add(piece)


def _note_loose(text):
    """For a string that is not parseable libpq keyword/value: remember what follows each secret keyword up to the
    next 'name=' token (it is withheld whole anyway; this only widens the self-check)."""
    for match in SECRET_KW_RE.finditer(text):
        if not is_secret_keyword(match.group(1)):
            continue
        words = []
        for word in re.split(r'[ \t\n\r\v\f]+', text[match.end():]):
            if words and re.match(r"[^=\s'\"]+\s*=", word):
                break
            if word:
                words.append(word.strip("'\""))
        _note_secret(' '.join(words))


def parse_conninfo_kv(text):
    """libpq conninfo_parse for the keyword/value form: [(start, end, keyword, value)], where start is the
    whitespace before the keyword and value is unescaped. None when libpq would reject the string (a word with
    no '=', an empty keyword, an unterminated quote). Unquoted values end at unescaped whitespace; a backslash
    escapes the next character, in quoted and unquoted values alike."""
    tokens, i, n = [], 0, len(text)
    while True:
        start = i
        while i < n and text[i] in CONNINFO_SPACE:
            i += 1
        if i >= n:
            return tokens
        name_start = i
        while i < n and text[i] != '=' and text[i] not in CONNINFO_SPACE:
            i += 1
        name = text[name_start:i]
        while i < n and text[i] in CONNINFO_SPACE:
            i += 1
        if not name or i >= n or text[i] != '=':
            return None
        i += 1
        while i < n and text[i] in CONNINFO_SPACE:
            i += 1
        value = []
        if i < n and text[i] == "'":
            i += 1
            closed = False
            while i < n:
                char = text[i]
                if char == '\\':
                    if i + 1 < n:
                        value.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                if char == "'":
                    closed = True
                    break
                value.append(char)
            if not closed:
                return None
        else:
            while i < n and text[i] not in CONNINFO_SPACE:
                if text[i] == '\\':
                    if i + 1 < n:
                        value.append(text[i + 1])
                    i += 2
                    continue
                value.append(text[i])
                i += 1
        tokens.append((start, min(i, n), name, ''.join(value)))


def _libpq_quote(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _decoded_forms(text):
    """The text and its successive percent-decodings (libpq decodes URI keywords and values once; a few
    rounds are checked so that a double-encoded keyword is also caught, at the cost of over-redaction)."""
    forms = [text]
    while '%' in forms[-1] and len(forms) < 4:
        decoded = unquote(forms[-1])
        if decoded == forms[-1]:
            break
        forms.append(decoded)
    return forms


def has_secret(text):
    """True when the text, raw or percent-decoded, still shows a secret pattern or a valued passphrase command."""
    if not isinstance(text, str):
        return False
    for form in _decoded_forms(text):
        if SECRET_URI_RE.search(form) or PASSPHRASE_SET_RE.search(form) or URI_USERINFO_ANY_RE.search(form):
            return True
        if any(is_secret_keyword(match.group(1)) and _valued(form, match.start(1), match.end())
               for match in SECRET_KW_RE.finditer(form)):
            return True
    return False


def _valued(text, start, at):
    """libpq reads a value after '=' and any whitespace; nothing, or an empty quoted value, is no secret."""
    rest = text[at:]
    value = rest.lstrip(CONNINFO_SPACE)
    if not value or re.match(r"(?:''|\"\")(?:[ \t\n\r\v\f]|$)", value):
        return False
    closing = value[0] in '\'"' and (len(value) == 1 or value[1] in CONNINFO_SPACE)
    return not (closing and rest[:1] == value[0] and start > 0 and text[start - 1] == value[0])


def strip_passphrase(text):
    """Remove the value of an ssl_passphrase_command assignment. Returns (text, [field...]).

    A string that is itself the assignment (an argv item, a -c item, a setconfig item) keeps only
    'name='. Inside a longer string, an assignment that opens a quoted item (as postmaster.opts quotes
    every argument) loses everything up to the closing quote. Anything else is left for has_secret, which
    then withholds the whole value."""
    whole = PASSPHRASE_ITEM_RE.match(text)
    if whole:
        _note_secret(whole.group(2), command=True)
        return whole.group(1), (['ssl_passphrase_command:value'] if whole.group(2).strip() else [])
    out, last, removed = [], 0, []
    for match in PASSPHRASE_QUOTED_RE.finditer(text):
        if match.start() < last:
            continue
        close = text.find(match.group(1), match.end())
        end = len(text) if close < 0 else close
        out.append(text[last:match.end()])
        if text[match.end():end].strip():
            _note_secret(text[match.end():end], command=True)
            removed.append('ssl_passphrase_command:value')
        last = end
    out.append(text[last:])
    return ''.join(out), removed


def _looks_like_conninfo(value):
    return bool(URI_PREFIX_RE.match(value)) or '=' in value


def _nested(value, depth):
    """(new_value or None-for-unchanged, removed) for a value that may itself be a conninfo; raises ValueError when
    it holds a secret pattern but is not parseable (the caller withholds the whole string)."""
    if not _looks_like_conninfo(value):
        return None, []
    if depth >= MAX_NEST:
        if has_secret(value):
            raise ValueError('nesting too deep')
        return None, []
    inner, removed = strip_conninfo(value, depth + 1)
    if inner is None:
        if has_secret(value):
            raise ValueError('nested value not parseable')
        return None, []
    return (inner if removed else None), removed


def strip_uri(text, depth=0):
    """libpq URI: the userinfo runs to the '@' that precedes the first '/' (libpq's look-ahead stops only at '@' or
    '/'; the LAST such '@' is taken, so '@', ':', '#', '?' and whitespace inside a password are removed with it);
    everything after the first ':' of the userinfo is the password and is removed whole. Parameters follow the first
    '?' after the netloc; a parameter whose percent-decoded keyword is secret is removed whole, and a value that is
    itself a conninfo is stripped recursively."""
    head = URI_PREFIX_RE.match(text).group(1)
    body = text[len(head):]
    slash = body.find('/')
    authority = body if slash < 0 else body[:slash]
    removed, rest_start = [], 0
    at = authority.rfind('@')
    if at >= 0:
        userinfo = body[:at]
        if ':' in userinfo:
            user, secret = userinfo.split(':', 1)
            _note_secret(secret)
            _note_secret(unquote(secret))
            removed.append('password(uri userinfo)')
            body = user + body[at:]
            at = len(user)
        rest_start = at + 1
    query = body.find('?', rest_start)
    if query < 0:
        return head + body, removed
    kept = []
    for part in body[query + 1:].split('&'):
        keyword, eq, value = part.partition('=')
        if is_secret_keyword(keyword):
            _note_secret(value)
            _note_secret(unquote(value))
            removed.append(unquote(keyword).strip().lower() + '(uri parameter)')
            continue
        try:
            inner, inner_removed = _nested(unquote(value), depth) if eq else (None, [])
        except ValueError:
            return None, removed
        if inner is not None:
            part = keyword + '=' + quote(inner, safe='')
            removed.extend('%s(nested in uri parameter %s)' % (item, unquote(keyword).lower())
                           for item in inner_removed)
        kept.append(part)
    return head + body[:query] + (('?' + '&'.join(kept)) if kept else ''), removed


def strip_conninfo(text, depth=0):
    """Remove every secret keyword (is_secret_keyword: SECRET-KEYWORDS.json) from a libpq conninfo string or URI.
    Returns (text, [field...]); text is None when the string is not parseable as libpq would parse it and holds a
    secret pattern somewhere (the caller withholds it whole). The keyword/value form is parsed as libpq parses it
    and the whole token is removed; any value that itself parses as a conninfo (dbname with expand_dbname, a URI
    parameter, any other) is stripped recursively, up to MAX_NEST levels, and re-quoted."""
    if URI_PREFIX_RE.match(text):
        return strip_uri(text, depth)
    removed = []
    tokens = parse_conninfo_kv(text)
    if tokens is None:
        return None, removed
    out, last = [], 0
    for start, end, name, value in tokens:
        if is_secret_keyword(name):
            _note_secret(value)
            _note_secret(text[start:end].strip().split('=', 1)[1].strip())
            out.append(text[last:start])
            last = end
            removed.append(name.lower())
            continue
        try:
            inner, inner_removed = _nested(value, depth)
        except ValueError:
            return None, removed
        if inner is not None:
            lead = text[start:end][:len(text[start:end]) - len(text[start:end].lstrip(CONNINFO_SPACE))]
            out.append(text[last:start] + lead + name + '=' + _libpq_quote(inner))
            last = end
            removed.extend('%s(nested in %s)' % (item, name.lower()) for item in inner_removed)
    out.append(text[last:])
    new = ''.join(out)
    if removed and not text[:1].isspace():
        new = new.lstrip()
    return new, removed


def _legacy_strip(text):
    """The follow-up 1-3 field-by-field stripper. Follow-up 4: UNREACHABLE for retention; it is called only by
    _note_withheld to remember secret values for the self-check, and its output is discarded."""
    if not has_secret(text):
        return text, []
    new, fields = strip_passphrase(text)
    if has_secret(new):
        before = new
        stripped, removed = strip_conninfo(new)
        if stripped is None:   # not parseable as libpq keyword/value: never strip part of it, withhold it whole
            _note_loose(new)
            return '[collect_pg: value withheld, secret pattern not strippable field by field]', \
                fields + ['unparsed secret pattern']
        new = stripped
        fields.extend(removed)
        if has_secret(new):
            new = HBA_OPTION_RE.sub('', ' ' + new)[1:] if HBA_OPTION_RE.search(' ' + new) else new
            if new != before and not removed:
                fields.append('authentication option')
    if has_secret(new):
        new = '[collect_pg: value withheld, secret pattern not strippable field by field]'
        fields.append('unparsed secret pattern')
    return new, fields


def guc_scanstr(quoted):
    """A faithful port of GUC_scanstr (src/backend/utils/misc/guc-file.l, PostgreSQL 14-18; cited by symbol: the
    source was not fetched, the network is closed). The argument is the whole STRING token, quotes included
    (lexer rule STRING  \\'([^'\\\\\\n]|\\\\.|\\'\\')*\\'). The leading quote is skipped; for each character:
    a backslash takes the next character as  b f n r t -> \\b \\f \\n \\r \\t,  0-7 -> up to three octal digits,
    the value cast to (char) (so it is taken modulo 256),  anything else -> that character;  '' -> one quote;
    any other character is copied. The copied closing quote is then dropped (newStr[--j] = '\\0')."""
    if len(quoted) < 2 or quoted[0] != "'" or quoted[-1] != "'":
        raise ValueError('GUC_scanstr needs a single-quoted token')
    body, out, i = quoted[1:], [], 0
    n = len(body)
    while i < n:
        char = body[i]
        if char == '\\':
            i += 1
            nxt = body[i] if i < n else ''
            if nxt in GUC_ESCAPES and nxt:
                out.append(GUC_ESCAPES[nxt])
            elif nxt and '0' <= nxt <= '7':
                k, value = 0, 0
                while k < 3 and i + k < n and '0' <= body[i + k] <= '7':
                    value = (value << 3) + (ord(body[i + k]) - ord('0'))
                    k += 1
                i += k - 1
                out.append(chr(value & 0xFF))
            else:
                out.append(nxt)
        elif char == "'" and i + 1 < n and body[i + 1] == "'":
            i += 1
            out.append("'")
        else:
            out.append(char)
        i += 1
    return ''.join(out[:-1])


GUC_ESCAPES = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}


def _conf_value_parts(rest):
    """(lead, raw, decoded, quoted, tail, closed) for the text after 'name =' on a postgresql.conf line. A quoted
    value runs as the lexer's STRING token does (a backslash takes the next character; '' is a quote) and is decoded
    with guc_scanstr; closed is False for an unterminated quote. An unquoted value runs to whitespace or '#'."""
    lead = rest[:len(rest) - len(rest.lstrip())]
    body = rest[len(lead):]
    if body.startswith("'"):
        index = 1
        while index < len(body):
            char = body[index]
            if char == '\\' and index + 1 < len(body):
                index += 2
                continue
            if char == "'" and body[index + 1:index + 2] == "'":
                index += 2
                continue
            if char == "'":
                raw = body[:index + 1]
                return lead, raw, guc_scanstr(raw), True, body[index + 1:], True
            index += 1
        return lead, body, None, True, '', False
    match = re.match(r'([^#\s]*)(.*)$', body, re.S)
    return lead, match.group(1), match.group(1), False, match.group(2), True


def _conf_value_span(rest):
    """(leading, decoded value, quoted, tail): kept for the include reader; decoding is guc_scanstr's."""
    lead, raw, value, quoted, tail, closed = _conf_value_parts(rest)
    return lead, (value if closed else raw[1:]), quoted, tail


def _quote(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


CONF_LINE_RE = re.compile(r'^(\s*#*\s*)([A-Za-z_][A-Za-z0-9_.]*)(\s*=\s*|\s+)(.*)$', re.S)


def _guc_norm(name):
    return (name or '').strip().lower().replace('-', '_')


def value_withheld(name, value):
    """True when a setting value may not be retained (follow-up 4 inversion rule). A value is retained only when it
    is empty, or when its name is not in the conninfo class and is not secret-named, and its DECODED form holds no
    '=', no '://', no password/secret/token/passphrase substring, and matches SAFE_VALUE_RE (after removing the
    documented literals of SAFE_LITERALS for that name)."""
    if not isinstance(value, str) or value == '':
        return False
    norm = _guc_norm(name)
    if norm in CONNINFO_CLASS_GUCS or secret_guc(norm)[0] or is_custom_guc(norm):
        return True
    low = value.lower()
    if '=' in value or '://' in value or any(word in low for word in STRUCTURE_WORDS):
        return True
    probe = SAFE_LITERALS[norm].sub('', value) if norm in SAFE_LITERALS else value
    return not SAFE_VALUE_RE.fullmatch(probe)


def _text_ok(text):
    """A comment (or a trailing comment) is retained only without '=', '://' or a secret word."""
    low = text.lower()
    return '=' not in text and '://' not in text and not any(word in low for word in STRUCTURE_WORDS + ('passwd',))


def _note_withheld(value, command=False):
    """Remember the secret values inside a value that is withheld whole, for the self-check only: the earlier
    field-by-field parsers (_legacy_strip) still run here, but only to find values; their output is discarded and
    no byte of it is retained anywhere (follow-up 4: no partial stripping remains)."""
    if not isinstance(value, str) or not value:
        return
    if command:
        _note_secret(value, command=True)
    try:
        _legacy_strip(value)
    except Exception:  # noting is best effort; the value is withheld whole regardless
        pass
    _note_loose(value)


def _conf_comment(body):
    """RF-28 (a): a comment line in the postgresql.conf grammar: '#' after spaces and tabs only (B-18-config-setting:
    'Hash marks (#) designate the remainder of the line as a comment')."""
    return body.lstrip(' \t').startswith('#')


def _conf_setting(key):
    """RF-28 (a): the setting name a marker shows (lower case, as the label does), or None when it is not safe."""
    name = key.lower()
    return name if MARKER_SETTING_RE.fullmatch(name) else None


def _redact_conf_line(body):
    """(new, fields). RF-28 (a): `new` is the retained text, or a Whole when the line is withheld whole."""
    if _starts_marker(body):                                                      # RF-28 (a)
        return Whole('MARKER-COLLISION', None, False), [COLLISION_LABEL]          # RF-28 (a)
    match = CONF_LINE_RE.match(body)
    if not match:
        if body.strip() and not _text_ok(body):
            _note_loose(body)
            return Whole('CONF-UNPARSED-LINE', None, _conf_comment(body)), ['line:line:withheld_whole']   # RF-28 (a)
        return body, []
    prefix, key, sep, rest = match.groups()
    commented = '#' in prefix
    comment = commented and _conf_comment(body)                                   # RF-28 (a)
    setting = None if commented else _conf_setting(key)                           # RF-28 (a)
    label = ('#' if commented else '') + key.lower()
    if commented and '=' not in sep:          # prose comment, not a commented-out assignment
        if _text_ok(body):
            return body, []
        _note_loose(body)
        return Whole('CONF-UNPARSED-LINE', None, comment), ['line:comment:withheld_whole']   # RF-28 (a)
    lead, raw, value, quoted, tail, closed = _conf_value_parts(rest)
    if not closed:
        _note_withheld(rest[len(lead) + 1:], command=secret_guc(key)[0])
        return Whole('CONF-UNTERMINATED-VALUE', setting, comment), [               # RF-28 (a)
            '%s:%s:withheld_whole' % (label, key.lower())]
    found = []
    if value_withheld(key, value):
        _note_withheld(value, command=secret_guc(key)[0])
        raw = "'" + WITHHELD_VALUE + "'"
        found.append('%s:%s:withheld_whole' % (label, key.lower()))
    stripped = tail.strip()
    if stripped and not stripped.startswith('#'):
        _note_loose(tail)
        return Whole('CONF-TRAILING-TEXT', setting, comment), found + [            # RF-28 (a)
            '%s:%s:withheld_whole' % (label, key.lower())]
    if stripped and not _text_ok(stripped):
        _note_loose(tail)
        tail = ' ' + WITHHELD_COMMENT
        found.append('%s:comment:withheld_whole' % label)
    new = prefix + key + sep + lead + raw + tail
    if has_secret(new.replace("'" + WITHHELD_VALUE + "'", "''")):
        return Whole('CONF-SECRET-LEFT', setting, comment), found + ['line:line:withheld_whole']   # RF-28 (a)
    return new, found


def redact_conf_text(text, record=None):                                         # RF-28 (b)
    """postgresql.conf grammar, line by line (guc-file.l lexer and GUC_scanstr); line count unchanged. Follow-up 4:
    a value is retained as written only when value_withheld() is False for its decoded form; otherwise the WHOLE
    value is replaced by '<withheld: structured value>'. Nothing is ever stripped out of a value.
    RF-28 (a): a line withheld whole is a marker (or the comment form for a comment); RF-28 (b): `record`, when a
    list, receives one (line, label, reason) per withheld label."""
    lines, fields = [], []
    for number, line in enumerate(server_lines(text), 1):                        # RF-28 (a)
        body = conf_body(line)
        new, found = _redact_conf_line(body)
        if not isinstance(new, Whole) and LINE_UNSAFE_RE.search(new):             # RF-28 (a)
            _note_loose(body)
            match = CONF_LINE_RE.match(body)                                      # RF-28 (a)
            setting = _conf_setting(match.group(2)) if match and '#' not in match.group(1) else None   # RF-28 (a)
            new, found = Whole('CONF-CONTROL-CHARACTER', setting, _conf_comment(body)), found + [   # RF-28 (a)
                'line:line:withheld_whole']
        fields.extend(found)
        lines.append(_line_text(new, number, found, record) + line[len(body):])   # RF-28 (a) (b)
    return ''.join(lines), fields


def structured_string(text):
    """True for a string from the catalog, a command line or an error that must be withheld whole: any secret
    pattern, any postgres URI, or a string that parses as libpq keyword/value with a libpq keyword, or with a
    non-empty value whose keyword is secret or whose keyword or value holds a STRUCTURE_WORDS substring (checked on
    the text and its percent-decodings). 'name=' with an empty value (a value already withheld) is kept."""
    if not isinstance(text, str) or not text:
        return False
    if has_secret(text):
        return True
    for form in _decoded_forms(text):
        if '://' in form and not SAFE_URL_RE.fullmatch(form):
            return True
        tokens = parse_conninfo_kv(form)
        if tokens and any(name.lower() in LIBPQ_KEYWORDS or (value and (is_secret_keyword(name) or any(
                word in (name + value).lower() for word in STRUCTURE_WORDS))) for _, _, name, value in tokens):
            return True
    return False


def redact_string(text):
    """(new_text, [field...]) for one string value from the catalog, a conninfo, an argv item or an error.
    Follow-up 4: a structured string is withheld WHOLE; any other string is kept as it is."""
    if structured_string(text):
        _note_withheld(text)
        return WITHHELD_VALUE, ['withheld_whole']
    return text, []


HBA_BLANK = ' \t\r'       # hba.c pg_isblank: ' ', '\t', '\r'
HBA_TYPES = ('local', 'host', 'hostssl', 'hostnossl', 'hostgssenc', 'hostnogssenc')
HBA_INCLUDES = ('include', 'include_if_exists', 'include_dir')
HBA_IP_RE = re.compile(r'[0-9.]+|[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*')


def hba_next_token(line, pos):
    """A faithful port of next_token (src/backend/libpq/hba.c, PostgreSQL 14-18; cited by symbol, the source was
    not fetched): skip blanks AND commas; then build the token up to EOL, an unquoted comma or unquoted blank; an
    unquoted '#' skips to EOL; a '"' is dropped unless it follows a '"' inside quotes (was_quote: '""' is a literal
    quote) and toggles in_quote ANYWHERE in the token; initial_quote is set when a quote opens an empty buffer.
    Returns a dict: token, initial_quote, comma (terminating_comma), start/end (raw span), next, found
    (saw_quote || len > 0), unterminated (in_quote at EOL: hba.c reads to EOL; here it is ambiguity), comment
    (index of the unquoted '#', or None)."""
    n, i = len(line), pos
    while i < n and (line[i] in HBA_BLANK or line[i] == ','):
        i += 1
    start, buf = i, []
    in_quote = was_quote = saw_quote = initial_quote = comma = False
    comment = None
    while i < n and (line[i] not in HBA_BLANK or in_quote):
        char = line[i]
        if char == '#' and not in_quote:
            comment = i
            break
        if char == ',' and not in_quote:
            comma = True
            break
        if char != '"' or was_quote:
            buf.append(char)
        was_quote = (not was_quote) if (in_quote and char == '"') else False
        if char == '"':
            in_quote = not in_quote
            saw_quote = True
            if not buf:
                initial_quote = True
        i += 1
    end = i
    return {'token': ''.join(buf), 'initial_quote': initial_quote, 'comma': comma, 'start': start, 'end': end,
            'next': n if comment is not None else (i + 1 if comma else i), 'found': saw_quote or bool(buf),
            'unterminated': in_quote, 'comment': comment}


def _hba_scan(line):
    """next_field_expand over one logical line (hba.c): a field is the tokens read while each ends in an unquoted
    comma. Returns (fields, comment_index, unterminated); a field is (start, end, [(token, initial_quote, raw)])."""
    fields, pos, n, comment, unterminated = [], 0, len(line), None, False
    while pos < n and comment is None:
        tokens, first, last = [], None, None
        while True:
            tok = hba_next_token(line, pos)
            pos = tok['next']
            if tok['comment'] is not None:
                comment = tok['comment']
            if not tok['found']:
                break
            unterminated = unterminated or tok['unterminated']
            first = tok['start'] if first is None else first
            last = tok['end']
            tokens.append((tok['token'], tok['initial_quote'], line[tok['start']:tok['end']]))
            if not tok['comma'] or comment is not None:
                break
        if tokens:
            fields.append((first, last, tokens))
        elif pos >= n or comment is not None:
            break
    return fields, comment, unterminated


def hba_fields(line):
    """The fields of one pg_hba.conf logical line as hba.c tokenises them: [(start, end, [(token, quote, raw)])]."""
    return _hba_scan(line)[0]


def _hba_plain(line, field, allow_list=False):
    """A positional field is retained only unquoted, without backslash, one token (or a comma list of names for
    database and user), every token matching SAFE_VALUE_RE without blanks."""
    start, end, tokens = field
    raw = line[start:end]
    if '"' in raw or '\\' in raw or (len(tokens) > 1 and not allow_list):
        return False
    return all(tok and ' ' not in tok and SAFE_VALUE_RE.fullmatch(tok) for tok, _, _ in tokens)


# RF-27 (a): the database and user fields (fields 1 and 2 of every authentication record) are identifiers by the
# pg_hba grammar (premise-pins-001/sources/B-14..B-18-auth-pg-hba-conf.html): quoted names, comma lists, +role,
# @file, /regex (16 and later; a literal name before 16) and the keywords. Each token is retained byte for byte,
# quotes included, when it is non-empty, within HBA_TOKEN_MAX characters, and free of control, line-separator and
# undecodable (surrogate-escaped) characters. A logical record longer than HBA_LINE_MAX is withheld whole.
HBA_TOKEN_MAX = 512           # RF-27 (a): characters of one raw database or user token, quotes included
HBA_LINE_MAX = 4096           # RF-27 (a): characters of one logical record (continued lines joined)
HBA_IDENTIFIER_UNSAFE_RE = re.compile(r'[\x00-\x1f\x7f-\x9f  \udc80-\udcff]')   # RF-27 (a)
HBA_IDENTIFIER_FIELDS = ((1, 'database'), (2, 'user'))      # RF-27 (a)


def _hba_identifier(field):
    """RF-27 (a): True when every token of a database or user field is retainable as an identifier."""
    for token, _, raw in field[2]:
        if not token or len(raw) > HBA_TOKEN_MAX or HBA_IDENTIFIER_UNSAFE_RE.search(raw):
            return False
    return True


def hba_token_forms(field):
    """RF-27 (b): the opaque forms of one database or user field, no values: 'quoted' (the raw token holds a
    double quote), 'file' (the raw token starts with an unquoted @ and names a file), 'regex' (the token the
    server reads starts with /; a regular expression on 16 and later, per the pinned PostgreSQL 16 page)."""
    forms = set()
    for token, _, raw in field[2]:
        if '"' in raw:
            forms.add('quoted')
        if raw.startswith('@') and len(token) > 1:
            forms.add('file')
        if token.startswith('/'):
            forms.add('regex')
    return sorted(forms)


HBA_HEXLIKE_RE = re.compile(r'0[xX][0-9A-Fa-f]*|[0-9A-Fa-f.]+')     # RF-27 (g)


def _hba_address_uncertain(field):
    """RF-27 (g): True when the address (before any /len) looks numeric but does not fully match HBA_IP_RE: it
    starts with 0x, or holds only hex digits and dots. No pinned source says whether the server reads it as a
    number (and then expects a mask field) or as a host name, so the field count is not established."""
    if len(field[2]) != 1:
        return False
    address = field[2][0][0].split('/', 1)[0]
    return bool(HBA_HEXLIKE_RE.fullmatch(address)) and not HBA_IP_RE.fullmatch(address)


def _hba_positional(line, fields):
    """Number of positional fields when the record's positional fields are all retainable, else None.
    RF-27 (a): the database and user fields pass the identifier rule; type, address, mask and method keep the
    strict plain rule, so the field count (and with it the method position) is the one the server reads."""
    if not fields:
        return 0
    first = fields[0][2][0][0] if len(fields[0][2]) == 1 and not fields[0][2][0][1] else None
    if first in HBA_INCLUDES:
        return 2 if len(fields) == 2 and _hba_plain(line, fields[1]) else None
    if first not in HBA_TYPES:
        return None
    count = 4 if first == 'local' else 5
    if first != 'local' and len(fields) >= 4 and _hba_address_uncertain(fields[3]):   # RF-27 (g)
        return None
    if first != 'local' and len(fields) >= 4 and len(fields[3][2]) == 1 and '/' not in fields[3][2][0][0] \
            and HBA_IP_RE.fullmatch(fields[3][2][0][0]):
        count = 6                                   # an address without /len is followed by a netmask field
    if len(fields) < count:
        return None
    for index in range(count):
        if index in (1, 2):                         # RF-27 (a): identifier rule for database and user
            if not _hba_identifier(fields[index]):
                return None
            continue
        if not _hba_plain(line, fields[index]):     # RF-27 (a): type, address, mask, method stay strict
            return None
    return count


def _hba_identifier_spans(fields):
    """RF-27 (a): the (start, end) spans of the database and user fields when the record starts with an unquoted
    record type and both fields pass the identifier rule; else []. The server reads these two fields by
    position, before any address, mask, method or auth-option, so they hold names and never an option."""
    if len(fields) < 3 or len(fields[0][2]) != 1 or fields[0][2][0][1] or fields[0][2][0][0] not in HBA_TYPES:
        return []
    if not all(_hba_identifier(fields[index]) for index, _ in HBA_IDENTIFIER_FIELDS):
        return []
    return [fields[index][:2] for index, _ in HBA_IDENTIFIER_FIELDS]


def _hba_mask_identifiers(text, fields):
    """RF-27 (a): the text with the database and user field spans blanked (offsets kept). The secret-pattern
    backstop and the self-check noting read this masked text: an identifier is the server's name, so it is
    neither scanned as an option nor remembered as a secret value (that would refuse a run retaining it)."""
    for start, end in _hba_identifier_spans(fields):
        text = text[:start] + ' ' * (end - start) + text[end:]
    return text


def _note_hba_withheld(body):
    """RF-27 (a): remember the secret values of a withheld record for the self-check, identifiers excepted."""
    fields = _hba_scan(body)[0]
    spans = _hba_identifier_spans(fields)
    for field in fields:
        if field[:2] not in spans:
            _note_hba_tokens(field[2])
    _note_loose(_hba_mask_identifiers(body, fields))


def _hba_masked_bodies(joined, bodies):
    """RF-27 (a): the physical pieces of a continued record with the identifier spans blanked, or None when a
    continuation joint falls inside the database or user field (a split the collector does not follow)."""
    pieces = [body[:-1] if body.endswith('\\') else body for body in bodies]
    joints, offset = [], 0
    for piece in pieces[:-1]:
        offset += len(piece)
        joints.append(offset)
    fields = _hba_scan(joined)[0]
    spans = _hba_identifier_spans(fields)
    if any(start < joint < end for start, end in spans for joint in joints):
        return None
    masked, out, offset = _hba_mask_identifiers(joined, fields), [], 0
    for piece in pieces:
        out.append(masked[offset:offset + len(piece)])
        offset += len(piece)
    return out


def _hba_value_ok(name, value):
    low = value.lower()
    if any(word in low for word in STRUCTURE_WORDS + ('passwd',)):
        return False
    if name == 'ldapurl' and '://' in value:        # follow-up 6: the URL grammar alone judges an ldapurl URL
        return bool(SAFE_URL_RE.fullmatch(value))
    if not value or ' ' in value or not SAFE_VALUE_RE.fullmatch(value):
        return False
    return '://' not in value or bool(SAFE_URL_RE.fullmatch(value))


def _ldapurl_quoted(raw, tokens):
    """Follow-up 6: the one quoted option spelling retained. hba.c next_token ends an unquoted token at a comma,
    so a DN with a comma is one ldapurl only inside double quotes: raw is exactly ldapurl=\"<value>\" and the value
    fully matches SAFE_URL_RE (which admits no quote, backslash, blank, '?', '#', '%' or '@')."""
    name, _, value = tokens[0][0].partition('=')
    return name == 'ldapurl' and raw == 'ldapurl="%s"' % value and bool(SAFE_URL_RE.fullmatch(value))


def hba_option_ok(raw, tokens):
    """An auth-method option is retained only when ALL hold: one token, no quote, comma or backslash in its raw
    bytes, a name=value form whose name is in HBA_OPTION_ALLOWLIST (exact, as hba.c compares it), and a value that
    matches SAFE_VALUE_RE with no secret word ('://' only for ldapurl, which has no userinfo: '@' is not safe).
    Follow-up 6: an ldapurl URL is judged by SAFE_URL_RE instead, and ldapurl=\"<url>\" is the one quoted form."""
    if len(tokens) != 1 or '\\' in raw:
        return False
    if any(char in raw for char in '",') and not _ldapurl_quoted(raw, tokens):
        return False
    name, eq, value = tokens[0][0].partition('=')
    return bool(eq) and name in HBA_OPTION_ALLOWLIST and _hba_value_ok(name, value)


def _hba_option_label(name):
    return name if re.fullmatch(r'[a-z_]{1,40}', name) else '(unnamed)'


def _note_hba_tokens(tokens):
    for token, _, raw in tokens:
        name, eq, value = token.partition('=')
        if eq and name not in HBA_OPTION_ALLOWLIST:
            _note_secret(value)
            _note_secret(raw.split('=', 1)[-1])


def _redact_hba_line(body):
    """(new_body, fields) for one logical line. Positional fields are kept only when _hba_positional accepts
    them, options only through hba_option_ok; every other option is replaced WHOLE by '<withheld option>', and a
    line that is not unambiguously tokenisable, or whose positional fields are not retainable, is withheld whole.
    RF-28 (a): a line withheld whole is returned as a Whole; redact_hba_text writes its marker."""
    if _starts_marker(body):                                                      # RF-28 (a)
        return Whole('MARKER-COLLISION', None, False), [COLLISION_LABEL]          # RF-28 (a)
    fields, comment, unterminated = _hba_scan(body)
    if unterminated:
        for field in fields:
            _note_hba_tokens(field[2])
        _note_loose(body)
        return Whole('HBA-UNTERMINATED-QUOTE', None, False), [                     # RF-28 (a)
            'line:withheld (unterminated quote: not tokenisable unambiguously)']
    found = []
    tail = body[comment:] if comment is not None else ''
    if not fields:
        if tail and not _text_ok(tail):
            _note_loose(tail)
            return Whole('COMMENT-WITHHELD', None, True), ['line:comment:withheld_whole']   # RF-28 (a)
        return body, []
    if len(body) > HBA_LINE_MAX:                    # RF-27 (a): over the line bound means withheld
        _note_hba_withheld(body)                    # RF-27 (a)
        return Whole('HBA-OVER-LENGTH', None, False), [                            # RF-28 (a)
            'line:record:withheld_whole (over the length bound)']
    count = _hba_positional(body, fields)
    if count is None:
        _note_hba_withheld(body)                    # RF-27 (a)
        return Whole('HBA-POSITIONAL', None, False), [                             # RF-28 (a)
            'line:record:withheld_whole (positional fields not retainable)']
    new = body
    if tail and not _text_ok(tail):
        _note_loose(tail)
        new = body[:comment] + WITHHELD_COMMENT
        found.append('line:comment:withheld_whole')
    for start, end, tokens in reversed(fields[count:]):
        if hba_option_ok(body[start:end], tokens):
            continue
        _note_hba_tokens(tokens)
        new = new[:start] + WITHHELD_OPTION + new[end:]
        found.extend('hba option:%s:withheld_whole' % _hba_option_label(tok.partition('=')[0]) for tok, _, _ in tokens)
    if has_secret(_hba_mask_identifiers(new, fields).replace(WITHHELD_OPTION, '')):   # RF-27 (a)
        _note_loose(_hba_mask_identifiers(new, fields))                                # RF-27 (a)
        return Whole('HBA-SECRET-LEFT', None, False), found + [                        # RF-28 (a)
            'line:withheld (secret pattern left after withholding options)']
    return new, found


def _hba_comment(body):
    """RF-28 (a): True when a physical line holds no field in the pg_hba grammar (blank or comment only), as
    _hba_scan reads it (hba.c next_token: blanks are ' ', '\\t', '\\r'). Only such a line keeps the comment form."""
    fields, _, unterminated = _hba_scan(body)
    return not fields and not unterminated


def _hba_backslash_blank(body, new, found):
    """RF-28 (a) FIX-2: a retained pg_hba line `new` (source `body`) that ends in a backslash followed by blanks. A
    comment line becomes the comment form; a record loses its trailing comment to WITHHELD_COMMENT (the server's
    meaning is unchanged, the text was a comment); a record with no comment is withheld whole."""
    if _hba_comment(body):
        return Whole('COMMENT-WITHHELD', None, True), found + ['line:comment:withheld_whole']
    _, comment, _ = _hba_scan(new)
    if comment is not None:
        return new[:comment] + WITHHELD_COMMENT, found + ['line:comment:withheld_whole']
    return Whole('HBA-TRAILING-BACKSLASH', None, False), found + [BACKSLASH_BLANK_LABEL]


def _hba_groups(text):
    """Physical lines grouped into logical lines: a line whose text ends in a backslash continues on the next
    (tokenize_auth_file, 16 and later; applied to every major here)."""
    physical = server_lines(text)
    index = 0
    while index < len(physical):
        group = [physical[index]]
        while hba_body(group[-1]).endswith('\\') and index + len(group) < len(physical):
            group.append(physical[index + len(group)])
        index += len(group)
        bodies = [hba_body(line) for line in group]
        yield group, bodies, [line[len(body):] for line, body in zip(group, bodies)]


def redact_hba_text(text, record=None):                                          # RF-28 (b)
    """pg_hba.conf as hba.c reads it: every logical line through _redact_hba_line. A logical line that spans
    several physical lines is kept byte for byte only when nothing in it is withheld; otherwise every physical
    line of it is withheld whole. The line count is unchanged.
    RF-28 (a): each withheld physical line is a marker with its own line number (the comment form only for a line
    with no field); RF-28 (b): `record`, when a list, receives one (line, label, reason) per withheld label."""
    lines, fields = [], []
    number = 0                                                                    # RF-28 (a)
    for group, bodies, eols in _hba_groups(text):
        first, number = number + 1, number + len(group)                            # RF-28 (a)
        if len(group) == 1:
            new, found = _redact_hba_line(bodies[0])
            if not isinstance(new, Whole) and LINE_UNSAFE_RE.search(new):         # RF-28 (a)
                _note_loose(bodies[0])
                new, found = Whole('HBA-CONTROL-CHARACTER', None, _hba_comment(bodies[0])), found + [   # RF-28 (a)
                    'line:withheld (control or line-separator character)']
            if not isinstance(new, Whole) and _backslash_blank(new):              # RF-28 (a) FIX-2
                new, found = _hba_backslash_blank(bodies[0], new, found)          # RF-28 (a) FIX-2
            fields.extend(found)
            lines.append(_line_text(new, first, found, record) + eols[0])          # RF-28 (a) (b)
            continue
        joined = ''.join(body[:-1] if body.endswith('\\') else body for body in bodies)
        new, found = _redact_hba_line(joined)
        masked = _hba_masked_bodies(joined, bodies)                         # RF-27 (a)
        if not found and new == joined and masked is not None and not any(
                has_secret(part) or LINE_UNSAFE_RE.search(body) for part, body in zip(masked, bodies)) \
                and not _backslash_blank(bodies[-1]):                             # RF-28 (a) FIX-2
            lines.extend(group)
            continue
        _note_hba_withheld(joined)                                           # RF-27 (a)
        for part in (masked or [body.rstrip('\\') for body in bodies]):     # RF-27 (a)
            _note_loose(part)
        reason = 'line:withheld (backslash continuation joins a withheld line: %d physical lines)' % len(group)
        for offset, (body, eol) in enumerate(zip(bodies, eols)):                   # RF-28 (a)
            whole = Whole('HBA-CONTINUATION', None, _hba_comment(body))             # RF-28 (a)
            lines.append(_line_text(whole, first + offset, [reason], record) + eol)   # RF-28 (a) (b)
            fields.append(reason)
    return ''.join(lines), fields


def hba_identifier_forms(text):
    """RF-27 (b): for a RETAINED pg_hba text, one entry per retained authentication record whose database or user
    field holds a quoted, @file or /regex token: {line (first physical line of the record), forms, fields:
    {database: [...], user: [...]}}. Forms only, never a value, so the checker can tell opaque tokens without
    re-parsing. Withheld records (markers, RF-28 (a)) and plain records have no entry."""
    out, number = [], 0
    for group, bodies, _ in _hba_groups(text):
        number += 1
        first, number = number, number + len(group) - 1
        if len(group) == 1 and _starts_marker(bodies[0]):                          # RF-28 (a)
            continue
        joined = ''.join(body[:-1] if body.endswith('\\') else body for body in bodies)
        fields, _, unterminated = _hba_scan(joined)
        count = _hba_positional(joined, fields)
        if unterminated or not count or count < 4:
            continue
        per_field = {name: hba_token_forms(fields[index]) for index, name in HBA_IDENTIFIER_FIELDS}
        forms = sorted(set(per_field['database']) | set(per_field['user']))
        if forms:
            out.append({'line': first, 'forms': forms, 'fields': per_field})
    return out


def structural_check_text(text, grammar):
    """Line numbers of a RETAINED conf or hba text that break the structural rule, independent of any secret
    value: no '=' inside a conf value or comment (outside the withheld markers); no hba option outside the
    allowlist path; no unknown record kept."""
    hits = []
    if grammar == 'conf':
        for number, physical in enumerate(server_lines(text), 1):
            line = conf_body(physical)
            if _starts_marker(line):                                              # RF-28 (a)
                if (parse_marker(line) or (0,))[0] != number:                     # RF-28 (a): exact, own number
                    hits.append(number)
                continue
            probe = line.replace("'" + WITHHELD_VALUE + "'", "''").replace(WITHHELD_COMMENT, '')
            match = CONF_LINE_RE.match(probe)
            rest = match.group(4) if match and ('=' in match.group(3) or '#' not in match.group(1)) else probe
            if '=' in rest or has_secret(probe) or LINE_UNSAFE_RE.search(line):
                hits.append(number)
        return hits
    if grammar == 'hba':
        number = 0
        for group, bodies, _ in _hba_groups(text):
            number += 1
            if len(group) == 1 and _starts_marker(bodies[0]):                     # RF-28 (a)
                if (parse_marker(bodies[0]) or (0,))[0] != number:                # RF-28 (a): exact, own number
                    hits.append(number)
                continue
            joined = ''.join(body[:-1] if body.endswith('\\') else body for body in bodies)
            probe = joined.replace(WITHHELD_OPTION, '<withheld_option>').replace(WITHHELD_COMMENT, '')
            fields, comment, unterminated = _hba_scan(probe)
            count = _hba_positional(probe, fields)
            bad = unterminated or (comment is not None and not _text_ok(probe[comment:])) or count is None \
                or any(LINE_UNSAFE_RE.search(body) for body in bodies) \
                or _backslash_blank(bodies[-1])                                   # RF-28 (a) FIX-2
            for start, end, tokens in fields[count or 0:]:
                if probe[start:end] != '<withheld_option>' and not hba_option_ok(probe[start:end], tokens):
                    bad = True
            if bad:
                hits.append(number)
            number += len(group) - 1
        return hits
    return hits


def redact_plain_text(text, record=None):                                        # RF-28 (b)
    """RF-28 (a): @file lists, pg_ident.conf and other files read with the pg_hba tokeniser. A withheld line is a
    marker, or the comment form when it holds no field; RF-28 (b): `record` as in redact_hba_text."""
    lines, fields = [], []
    for number, line in enumerate(server_lines(text), 1):                        # RF-28 (a)
        body = hba_body(line)
        if _starts_marker(body):                                                  # RF-28 (a)
            whole, found = Whole('MARKER-COLLISION', None, False), [COLLISION_LABEL]   # RF-28 (a)
        elif has_secret(body) or LINE_UNSAFE_RE.search(body):
            _note_withheld(body)                     # RF-27 (h): the self-check learns what is withheld
            code = 'PLAIN-CONTROL-CHARACTER' if LINE_UNSAFE_RE.search(body) else 'PLAIN-SECRET-PATTERN'   # RF-28 (a)
            whole, found = Whole(code, None, _hba_comment(body)), ['line:unparsed secret pattern']        # RF-28 (a)
        elif _backslash_blank(body):                                              # RF-28 (a) FIX-2
            comment = _hba_comment(body)                                          # RF-28 (a) FIX-2
            whole = Whole('PLAIN-TRAILING-BACKSLASH', None, comment)              # RF-28 (a) FIX-2
            found = ['line:comment:withheld_whole' if comment else BACKSLASH_BLANK_LABEL]   # RF-28 (a) FIX-2
        else:
            lines.append(line)
            continue                                                              # RF-28 (a)
        fields.extend(found)                                                      # RF-28 (a)
        lines.append(_line_text(whole, number, found, record) + line[len(body):])  # RF-28 (a) (b)
    return ''.join(lines), fields


CONFIG_LIST_KEYS = ('setconfig', 'proconfig', 'useconfig', 'rolconfig')
CONNINFO_FIELDS = ('subconninfo',)
# RF-28 (c): pg_proc.proconfig 'search_path=<list>' is the fact the definer-function obligations read. Its value is
# an identifier list (schema names, quoted or not), so it is retained byte for byte when it is at most
# SEARCH_PATH_MAX characters, holds no control, line-separator or undecodable character, and shows no secret pattern
# (has_secret: a URI with userinfo, a valued secret keyword, a passphrase command). A quoted identifier can hold any
# printable text, so a value that shows a secret pattern takes the existing rule and is withheld and noted. Only the
# exact spelling 'search_path=' at the start of a proconfig entry takes this rule; every other entry, and search_path
# in setconfig, useconfig or rolconfig, keeps the existing rule.
SEARCH_PATH_MAX = 2048                                                                    # RF-28 (c)


def _function_search_path(item):
    """RF-28 (c): True for a proconfig entry 'search_path=<value>' that is retained byte for byte."""
    if not isinstance(item, str) or not item.startswith('search_path='):
        return False
    value = item[len('search_path='):]
    return len(value) <= SEARCH_PATH_MAX and not HBA_IDENTIFIER_UNSAFE_RE.search(value) and not has_secret(item)


def _hba_option_item(item, path, fields):
    """One pg_hba_file_rules.options item ('name=value', decoded by the server): kept only through the allowlist."""
    if isinstance(item, str):
        name, eq, value = item.partition('=')
        comma_ok = ',' not in value or (name == 'ldapurl' and bool(SAFE_URL_RE.fullmatch(value)))   # follow-up 6
        if eq and name in HBA_OPTION_ALLOWLIST and comma_ok and '"' not in value and '\\' not in value \
                and _hba_value_ok(name, value):
            return item
        if eq and name not in HBA_OPTION_ALLOWLIST:
            _note_secret(value)
            _note_secret(value.strip('"'))
        fields.append('%s.options:%s:withheld_whole' % (path, _hba_option_label(name)))
        return WITHHELD_OPTION
    return redact_tree(item, path + '.options[]', fields)


def note_hba_retained(text):
    """RF-27 (e): remember the database and user tokens, quotes removed, of every retained authentication record
    in a RETAINED pg_hba text. A token whose raw text starts with an unquoted '@' is an @file reference: the server
    expands it to the file's content (unpinned), so it admits nothing. Withheld records hold no fields."""
    for group, bodies, _ in _hba_groups(text):
        joined = ''.join(body[:-1] if body.endswith('\\') else body for body in bodies)
        fields, _, unterminated = _hba_scan(joined)
        count = None if unterminated else _hba_positional(joined, fields)
        if not count or count < 4 or not _hba_identifier_spans(fields):
            continue
        for index, _ in HBA_IDENTIFIER_FIELDS:
            _HBA_RETAINED.update(token for token, _, raw in fields[index][2] if not raw.startswith('@'))


def _hba_identifier_item(name, path, fields):
    """RF-27 (c), narrowed by RF-27 (e): one pg_hba_file_rules database or user_name item, as the server parsed
    it. It keeps the identifier rule (within HBA_TOKEN_MAX, no control, line-separator or undecodable character,
    never remembered as a secret value) only when it equals a token note_hba_retained saw in a retained file.
    Every other item, such as a name expanded from @file content, takes the RF-24 path item by item."""
    if isinstance(name, str) and name in _HBA_RETAINED and len(name) <= HBA_TOKEN_MAX \
            and not HBA_IDENTIFIER_UNSAFE_RE.search(name):
        return name
    return _redact_list([name], path, fields)[0]      # RF-27 (e): the RF-24 path for this one item


def _string_leaf(value, path, name, fields):
    new, removed = redact_string(value)
    if removed:
        fields.append('%s:%s:withheld_whole' % (path, _label_name(name)))
    return new


def _label_name(name):
    return name if isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$-]{0,62}', name) else 'item'


def redact_tree(value, path, fields, config=False):
    """Withhold structured values in a JSON value (follow-up 4: whole values only, never a part of one); append
    field labels '<path>:<name>:withheld_whole' (never values)."""
    if isinstance(value, dict):
        out = {}
        name = value.get('name') if isinstance(value.get('name'), str) else None
        for key, item in value.items():
            if name is not None and key in ('setting', 'boot_val', 'reset_val') and isinstance(item, str) \
                    and value_withheld(name, item):
                _note_withheld(item, command=secret_guc(name)[0])
                out[key] = WITHHELD_VALUE
                fields.append('%s.%s:%s:withheld_whole' % (path, key, _label_name(name)))
                continue
            if key in CONNINFO_FIELDS and isinstance(item, str) and item:
                _note_withheld(item)
                out[key] = WITHHELD_VALUE
                fields.append('%s.%s:%s:withheld_whole' % (path, key, key))
                continue
            if key == 'options' and isinstance(item, list) and 'pg_hba_file_rules' in path:
                out[key] = [_hba_option_item(option, path, fields) for option in item]
                continue
            if key in ('database', 'user_name') and isinstance(item, list) and 'pg_hba_file_rules' in path:
                out[key] = [_hba_identifier_item(name, '%s.%s' % (path, key), fields) for name in item]   # RF-27 (c)
                continue
            if isinstance(item, str):
                out[key] = _string_leaf(item, '%s.%s' % (path, key), key, fields)
                continue
            out[key] = redact_tree(item, '%s.%s' % (path, key), fields, config=key in CONFIG_LIST_KEYS)
        return out
    if isinstance(value, list):
        return _redact_list(value, path, fields, config)
    if isinstance(value, str):
        return _string_leaf(value, path, 'item', fields)
    return value


def _redact_list(value, path, fields, config=False):
    out = []
    for item in value:
        if config and path.endswith('.proconfig') and _function_search_path(item):     # RF-28 (c)
            out.append(item)                                                         # RF-28 (c)
            continue                                                                 # RF-28 (c)
        if isinstance(item, str) and re.match(r'(?i)(%s)\s*=' % '|'.join(HBA_SECRET_OPTIONS), item):
            _note_secret(item.split('=', 1)[1].strip('"'))
            fields.append('%s[]:%s:withheld_whole' % (path, item.split('=', 1)[0].strip().lower()))
            out.append(WITHHELD_OPTION)
            continue
        assignment = re.match(r'\s*([A-Za-z_][A-Za-z0-9_.$-]*)\s*=(.*)$', item, re.S) \
            if isinstance(item, str) else None
        if assignment and secret_guc(assignment.group(1))[0] and assignment.group(2).strip():
            _note_secret(assignment.group(2), command=True)
            fields.append('%s[]:%s:withheld_whole' % (path, secret_guc(assignment.group(1))[1]))
            out.append(assignment.group(1) + '=')
            continue
        if config and assignment and value_withheld(assignment.group(1), assignment.group(2)):
            _note_withheld(assignment.group(2))
            fields.append('%s[]:%s:withheld_whole' % (path, _label_name(_guc_norm(assignment.group(1)))))
            out.append(assignment.group(1) + '=' + WITHHELD_VALUE)
            continue
        label = path + ('[%s]' % item['name'] if isinstance(item, dict) and isinstance(item.get('name'), str)
                        and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', item['name']) else '[]')
        out.append(redact_tree(item, label, fields))
    return out


# ---------------------------------------------------------------- postmaster.opts
# PostgreSQL writes the program path, then ' "<arg>"' for every argument, with no escaping inside the quotes.
OPTS_LINE_RE = re.compile(r'^([^"\n]+?)((?: "[^"\n]*")*)$')
OPTS_ITEM_RE = re.compile(r' "([^"\n]*)"')
# the postmaster's getopt letters (src/backend/postmaster/postmaster.c, "B:bC:c:D:d:EeFf:h:ijk:lN:nOPp:r:S:sTt:W:-:");
# this list is the author's reading of the source, not a pinned premise
GETOPT_WITH_ARG = frozenset('BCcDdfhkNprStW-')
GETOPT_NO_ARG = frozenset('bEeFijlnOPsT')
SECRET_GUC_RE = re.compile(r'(?i)(password|passwd|passphrase|secret)')
NON_SECRET_GUCS = ('password_encryption', 'ssl_passphrase_command_supports_reload')
OPTS_WITHHELD = ('postmaster.opts could not be parsed unambiguously as PostgreSQL writes it (the program path, then '
                 'each argument in double quotes with no inner escaping, every argument an option or the argument '
                 'of one): %s; argv and lines are withheld whole, no fragment is kept')


def secret_guc(name):
    norm = name.strip().lower().replace('-', '_')
    return norm not in NON_SECRET_GUCS and bool(SECRET_GUC_RE.search(norm)), norm


def _opts_assignment(prefix, assignment, fields):
    """A -c / -c<attached> / --name=value assignment: secret-bearing GUC values are withheld whole."""
    if '=' not in assignment:
        raise ValueError('an assignment option without name=value')
    name, value = assignment.split('=', 1)
    secret, norm = secret_guc(name)
    if secret:
        if value.strip():
            _note_secret(value, command=True)
            fields.extend('postmaster_opts.%s[]:%s:value' % (part, norm) for part in ('argv', 'lines'))
        return prefix + name + '='
    if value_withheld(norm, value) or structured_string(value):
        _note_withheld(value)
        fields.extend('postmaster_opts.%s[]:%s:withheld_whole' % (part, _label_name(norm)) for part in ('argv', 'lines'))
        return prefix + name + '=' + WITHHELD_VALUE
    return prefix + assignment


def parse_postmaster_opts(text):
    """(argv, lines, fields) with secret values removed; raises ValueError(reason) when not unambiguous."""
    body = text[:-1] if text.endswith('\n') else text
    if not body:
        return [], [], []
    if '\n' in body:
        raise ValueError('more than one line')
    match = OPTS_LINE_RE.match(body)
    if not match:
        raise ValueError('an argument is not exactly one double-quoted item (embedded or unbalanced quote)')
    prog, items, fields = match.group(1), OPTS_ITEM_RE.findall(match.group(2)), []
    out, pending, plain = [], None, []
    for number, item in enumerate(items, 1):
        if pending is not None:
            out.append(_opts_assignment('', item, fields) if pending == 'c' else item)
            plain.append(None if pending == 'c' else item)
            pending = None
            continue
        if not item.startswith('-') or item == '-':
            raise ValueError('argument %d is neither an option nor the argument of one' % number)
        if item.startswith('--'):
            if item == '--':
                raise ValueError('argument %d ends the options' % number)
            out.append(_opts_assignment('--', item[2:], fields))
            continue
        for index in range(1, len(item)):
            letter = item[index]
            if letter in GETOPT_WITH_ARG:
                if index + 1 < len(item):
                    attached = item[index + 1:]
                    out.append(_opts_assignment(item[:index + 1], attached, fields) if letter == 'c' else item)
                    plain.append(None if letter == 'c' else item)
                else:
                    out.append(item)
                    plain.append(item)
                    pending = letter
                break
            if letter not in GETOPT_NO_ARG:
                raise ValueError('argument %d has an option letter the postmaster does not accept' % number)
        else:
            out.append(item)
            plain.append(item)
    if any(structured_string(item) for item in plain if item is not None):   # option letters, paths, ports
        raise ValueError('an argument holds a structured value (conninfo, URI or secret pattern)')
    if pending is not None:
        raise ValueError('the last option has no argument')
    if has_secret(prog):
        raise ValueError('the program path shows a secret pattern')
    return [prog] + out, [prog + ''.join(' "%s"' % item for item in out)], fields


# ---------------------------------------------------------------- redaction self-check
def _needle_forms(needle):
    forms = {needle, json.dumps(needle, ensure_ascii=False)[1:-1], json.dumps(needle)[1:-1],
             needle.replace('\\', '\\\\').replace("'", "''"), needle.replace('\\', '\\\\').replace("'", "\\'"),
             sha256(needle.encode('utf-8'))}
    return [form.encode('utf-8', 'surrogateescape') for form in forms if form]


def selfcheck_scan(out):
    """Relative paths of retained files holding any remembered secret value or fragment (no value is returned)."""
    forms = [form for needle in sorted(_SECRETS['needles']) for form in _needle_forms(needle)]
    hits = []
    for path in sorted(out.rglob('*')):
        if path.is_file():
            blob = path.read_bytes()
            if any(form in blob for form in forms):
                hits.append(path.relative_to(out).as_posix())
    return hits


def structural_check_out(out, grammars):
    """Relative paths of retained files that break the structural rule (conf/hba text; pg_settings rows; the
    snapshot's setting rows and hba options), independent of any secret value."""
    hits = []
    for rel, grammar in sorted(grammars.items()):
        path = out / rel
        if grammar in ('conf', 'hba') and path.is_file() and \
                structural_check_text(path.read_bytes().decode('utf-8', 'surrogateescape'), grammar):
            hits.append(rel)

    def bad_rows(rows):
        return any(isinstance(row, dict) and any(isinstance(row.get(key), str) and '=' in row[key]
                                                 and row[key] != WITHHELD_VALUE
                                                 for key in ('setting', 'boot_val', 'reset_val'))
                   for row in rows or [] if isinstance(rows, list))
    settings = out / 'raw' / 'pg_settings.json'
    if settings.is_file() and bad_rows(json.loads(settings.read_text())):
        hits.append('raw/pg_settings.json')
    snapshot = out / 'raw' / 'catalog_snapshot.json'
    if snapshot.is_file():
        snap = json.loads(snapshot.read_text())
        rules = snap.get('pg_hba_file_rules') if isinstance(snap.get('pg_hba_file_rules'), list) else []
        options_bad = any(isinstance(rule, dict) and isinstance(rule.get('options'), list) and
                          any(option != WITHHELD_OPTION and (not isinstance(option, str) or
                                                             _hba_option_item(option, 'check', []) != option)
                              for option in rule['options']) for rule in rules)
        if bad_rows(snap.get('pg_settings')) or bad_rows(snap.get('pg_file_settings')) or options_bad:
            hits.append('raw/catalog_snapshot.json')
    return hits


def wipe(out):
    for path in sorted(out.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()


# ---------------------------------------------------------------- helpers
def dump(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


def flagged(value):
    return dict(FLAGS, **value)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def file_stat(path):
    """RF-24 (d): the one stat of a copied configuration file, taken after its read (patchable in tests)."""
    return os.stat(path)


def mtime_ns_record(ns):
    """RF-24 (d): an st_mtime_ns as the integer and as UTC text with all nine fractional digits."""
    whole, fraction = divmod(ns, 10 ** 9)
    stamp = datetime.datetime.fromtimestamp(whole, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    return {'st_mtime_ns': ns, 'utc': '%s.%09d+00:00' % (stamp, fraction)}


def clean_error(text):
    text = (text or '').strip()
    new, _ = redact_string(text)
    new = '\n'.join(REDACTED_LINE if has_secret(line) else line for line in new.split('\n'))
    return new[:500]


def classify(stderr):
    low = (stderr or '').lower()
    if 'permission denied' in low or 'must be superuser' in low or 'privileges of' in low:
        return 'unreadable', 'permission_denied'
    if 'does not exist' in low:
        return 'unsupported', 'undefined_object'
    if any(word in low for word in ('could not connect', 'connection', 'timed out', 'timeout', 'not found',
                                    'server closed')):
        return 'unreadable', 'transport'
    return 'unreadable', 'other'


def hba_tokens(line):
    tokens, current, quoted, started = [], '', False, False
    for char in line:
        if char == '"':
            quoted, started = not quoted, True
            continue
        if char == '#' and not quoted:
            break
        if char.isspace() and not quoted:
            if started:
                tokens.append(current)
            current, started = '', False
            continue
        current += char
        started = True
    if started:
        tokens.append(current)
    return tokens


def conf_value(text):
    _, value, quoted, _ = _conf_value_span(text.strip())
    return value if quoted else text.strip().split('#', 1)[0].strip()


# ---------------------------------------------------------------- collection
class Collector:
    def __init__(self, args, local_dd, roots=None):
        self.args, self.local_dd = args, local_dd
        self.roots = list(roots or [os.path.realpath(local_dd)])
        self.entries, self.files, self.server_to_raw = [], {}, {}
        self.timing = {'query_elapsed_ms': {}, 'file_mtimes': {}, 'file_mtimes_ns': {}}   # RF-24 (d)
        self.results = {}
        self.server_dd = None
        self.major = None

    # ---- queries
    def run(self, query):
        start = time.monotonic()
        try:
            code, stdout, stderr = RUNNER(query['sql'])
        except Exception as error:  # a runner failure is recorded, never retried
            code, stdout, stderr = 1, '', 'runner raised ' + type(error).__name__
        self.timing['query_elapsed_ms'][query['id']] = round((time.monotonic() - start) * 1000, 3)
        if code != 0:
            status, error_class = classify(stderr)
            return status, None, clean_error(stderr) or ('exit %d with no error text' % code), error_class
        try:
            value = json.loads((stdout or '').strip())
        except ValueError:
            return 'unreadable', None, 'output is not one JSON value (psql -At)', 'malformed_output'
        if value is None:
            return 'unreadable', None, 'query returned no row', 'malformed_output'
        return ('observed_empty' if value in ([], {}) else 'observed'), value, None, None

    def record_query(self, query, status, value, error, error_class):
        rows = len(value) if isinstance(value, (list, dict)) else None
        self.entries.append({'kind': 'query', 'target': 'query:' + query['id'], 'id': query['id'],
                             'key': query['key'] or query['id'], 'views': query['views'], 'status': status,
                             'error': error, 'error_class': error_class, 'rows': rows})

    # ---- paths
    def remap(self, server_path):
        if server_path and self.server_dd and (server_path == self.server_dd or
                                               server_path.startswith(self.server_dd.rstrip('/') + '/')):
            return str(Path(self.local_dd) / server_path[len(self.server_dd.rstrip('/')):].lstrip('/'))
        return server_path

    def confine(self, local):
        """None when the local path, links resolved, lies inside a declared root; else the refusal text."""
        real = os.path.realpath(local)
        for root in self.roots:
            if real == root or real.startswith(root.rstrip('/') + '/'):
                return None
        return ('outside the declared roots (--data-dir%s): %s resolves to %s; refused, not read'
                % (' and --extra-root' if len(self.roots) > 1 else '', local, real))

    def file_entry(self, raw_rel, server_path, status, error=None, via=None, kind='file', optional=False):
        target = ('file:raw/' + raw_rel) if raw_rel else ('file:' + str(server_path))
        entry = {'kind': kind, 'target': target, 'server_path': server_path, 'status': status, 'error': error,
                 'via': via}
        if optional:
            entry['optional'] = True
        self.entries.append(entry)

    def take(self, grammar, server_path, raw_rel, via=None, depth=0, optional=False):
        """Copy one configuration file into the raw/ placement and follow its include directives."""
        if raw_rel in self.files:
            if self.files[raw_rel]['server'] != server_path:
                self.file_entry(None, server_path, 'unsupported', 'raw placement raw/%s already holds %s' %
                                (raw_rel, self.files[raw_rel]['server']), via)
            return
        if depth > MAX_DEPTH:
            self.file_entry(raw_rel, server_path, 'unsupported', 'include nesting deeper than %d' % MAX_DEPTH, via)
            return
        local = self.remap(server_path)
        refused = self.confine(local)
        if refused:
            self.file_entry(raw_rel, server_path, 'unsupported', refused, via)
            return
        try:
            data = Path(local).read_bytes()
        except FileNotFoundError:
            if optional:
                self.file_entry(raw_rel, server_path, 'declared_absent',
                                'include_if_exists target not present (the configuration declares it optional)',
                                via, optional=True)
            else:
                self.file_entry(raw_rel, server_path, 'missing', 'FileNotFoundError: no file at ' + str(local), via)
            return
        except PermissionError:
            self.file_entry(raw_rel, server_path, 'unreadable', 'PermissionError reading ' + str(local), via)
            return
        except OSError as error:
            self.file_entry(raw_rel, server_path, 'unreadable', type(error).__name__ + ' reading ' + str(local), via)
            return
        self.files[raw_rel] = {'bytes': data, 'server': server_path, 'grammar': grammar}
        self.server_to_raw[posixpath.normpath(server_path)] = raw_rel
        try:   # RF-24 (d): ONE stat gives both precisions; a failed stat is a typed not-observed mtime, never silent
            stat = file_stat(local)
        except OSError as error:
            self.timing['file_mtimes_ns']['raw/' + raw_rel] = {'status': 'not_observed',
                                                          'error_class': type(error).__name__}
        else:   # RF-24 (d): the nanosecond mtime sits beside the frozen second-precision one
            self.timing['file_mtimes']['raw/' + raw_rel] = datetime.datetime.fromtimestamp(
                stat.st_mtime, datetime.timezone.utc).isoformat(timespec='seconds')   # RF-24 (d): same stat
            self.timing['file_mtimes_ns']['raw/' + raw_rel] = mtime_ns_record(stat.st_mtime_ns)   # RF-24 (d)
        self.file_entry(raw_rel, server_path, 'observed' if data else 'observed_empty', None, via)
        text = data.decode('utf-8', 'surrogateescape')
        for number, kind, target in self.directives(grammar, text):
            self.follow(grammar, server_path, raw_rel, number, kind, target, depth)

    def directives(self, grammar, text):
        out = []
        if grammar == 'conf':
            for number, line in enumerate(server_lines(text), 1):
                stripped = conf_body(line).strip()
                if not stripped or stripped.startswith('#'):
                    continue
                match = re.match(r'([A-Za-z_][A-Za-z0-9_.]*)\s*(=\s*|\s+)(.*)$', stripped)
                if match and match.group(1).lower() in ('include', 'include_if_exists', 'include_dir'):
                    out.append((number, match.group(1).lower(), conf_value(match.group(3))))
            return out
        # RF-27 (f): the scan reads the logical records the redaction reads: _hba_groups joins a backslash
        # continuation on every major (pinned on B-14..B-18), and _hba_scan builds the fields as next_field_expand
        # does, so a comma list with a blank after the comma is one field. An @file target is a token whose raw text
        # starts with an unquoted '@' (the 'file' form of hba_token_forms); the target is the token without it.
        number = 0
        for group, bodies, _ in _hba_groups(text):
            number += 1
            start, number = number, number + len(group) - 1
            joined = ''.join(body[:-1] if body.endswith('\\') else body for body in bodies)
            fields = _hba_scan(joined)[0]
            if not fields:
                continue
            if grammar == 'plain':      # RF-27 (d): an @file list may name further @files (nested @ is allowed)
                scope = fields
            elif fields[0][2][0][0] in HBA_INCLUDES:
                target = fields[1][2][0][0] if len(fields) > 1 else ''
                out.append((start, fields[0][2][0][0], target))
                continue
            else:                       # RF-27 (f): fields 1 and 2 of an hba record
                scope = fields[1:3] if grammar == 'hba' else []
            for field in scope:
                for token, _, raw in field[2]:
                    if raw.startswith('@') and len(token) > 1:
                        out.append((start, '@file', token[1:]))
        return out

    def follow(self, grammar, server_parent, raw_parent, number, kind, target, depth):
        via = 'raw/%s:%d %s' % (raw_parent, number, kind)
        if not target:
            self.file_entry(None, server_parent + ':%d' % number, 'unsupported', kind + ' with no target', via)
            return
        if grammar != 'conf' and kind != '@file' and self.major < 16:
            self.file_entry(None, target, 'unsupported',
                            '%s directive in a %s file before major 16: not followed' % (kind, grammar), via)
            return
        absolute = target.startswith('/')
        server_child = posixpath.normpath(target if absolute else
                                          posixpath.join(posixpath.dirname(server_parent), target))
        if absolute:
            if grammar == 'conf' and kind in ('include', 'include_if_exists'):
                raw_child = posixpath.basename(server_child)  # derive maps an absolute include to raw/<basename>
            else:
                self.file_entry(None, server_child, 'unsupported',
                                'absolute %s target: the frozen derive resolves it outside raw/; not copied' % kind, via)
                return
        else:
            raw_child = posixpath.normpath(posixpath.join(posixpath.dirname(raw_parent), target))
            if raw_child.startswith('..') or raw_child.startswith('/'):
                self.file_entry(None, server_child, 'unsupported',
                                'relative %s target escapes the raw/ placement; not copied' % kind, via)
                return
        child_grammar = 'plain' if kind == '@file' else grammar
        if kind != 'include_dir':
            self.take(child_grammar, server_child, raw_child, via, depth + 1, optional=(kind == 'include_if_exists'))
            return
        local_dir = Path(self.remap(server_child))
        refused = self.confine(str(local_dir))
        if refused:
            self.file_entry(raw_child, server_child, 'unsupported', refused, via, kind='directory')
            return
        if not local_dir.is_dir():
            status = 'missing' if not local_dir.exists() else 'unreadable'
            self.file_entry(raw_child, server_child, status, 'include_dir is not a readable directory: ' +
                            str(local_dir), via, kind='directory')
            return
        try:
            names = sorted(child.name for child in local_dir.iterdir()
                           if child.name.endswith('.conf') and not child.name.startswith('.') and child.is_file())
        except OSError as error:
            self.file_entry(raw_child, server_child, 'unreadable', type(error).__name__ + ' listing ' + str(local_dir),
                            via, kind='directory')
            return
        self.file_entry(raw_child, server_child, 'observed' if names else 'observed_empty', None, via,
                        kind='directory')
        for name in names:
            self.take(grammar, posixpath.join(server_child, name), posixpath.join(raw_child, name), via, depth + 1)


# RF-28 (d): the client login name. Through a pooler the login name carries a suffix (for example
# 'role.project'); the role whose row, attributes and grants are examined stays --role.
LOGIN_USER_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,127}')                             # RF-28 (d)
# RF-28 (e): the session facts, read after the three checks by two control queries of their own: session_settings
# (no view) and session_tls (pg_stat_ssl). Recorded as observed facts, with no judgement: a pooler may drop the
# startup option, end TLS itself and connect from its own address. A failed session read is a recorded gap (its
# query entry), never a refusal. A value of an unexpected shape is never retained: it reads unreadable.
READ_ONLY_REQUESTED = {'default_transaction_read_only': 'on',
                       'via': "PGOPTIONS '-c default_transaction_read_only=on'"}          # RF-28 (e)
SESSION_VALUES = ('on', 'off')                                                            # RF-28 (e)
TLS_VERSION_RE = re.compile(r'TLSv1(?:\.[1-3])?')                                         # RF-28 (e)
TLS_CIPHER_RE = re.compile(r'[A-Z0-9][A-Z0-9_-]{0,63}')                                   # RF-28 (e)
SESSION_READS = ('session_settings', 'session_tls')                                       # RF-28 (e)
OBSERVED_STATUSES = ('observed', 'observed_empty')                                        # RF-28 (e)


def _session_setting(settings, name):
    """RF-28 (e): one effective setting the session reports: observed ('on' or 'off'), unreadable (any other
    value, not retained) or not_observed (the object has no such key)."""
    if name not in settings:
        return {'status': 'not_observed', 'value': None}
    value = settings[name]
    if isinstance(value, str) and value in SESSION_VALUES:
        return {'status': 'observed', 'value': value}
    return {'status': 'unreadable', 'value': None}


def _tls_field(key, value):
    """RF-28 (e): (retained value, field status). A server null is observed null; a value of an unexpected shape is
    unreadable and recorded as null, so null with status observed always means the server returned null."""
    if value is None:
        return None, 'observed'
    if key == 'ssl':
        ok = isinstance(value, bool)
    elif key == 'bits':
        ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 65536
    elif key == 'version':
        ok = isinstance(value, str) and bool(TLS_VERSION_RE.fullmatch(value))
    else:
        ok = isinstance(value, str) and bool(TLS_CIPHER_RE.fullmatch(value))
    return (value, 'observed') if ok else (None, 'unreadable')


def _tls_fact(result):
    """RF-28 (e): the backend's own pg_stat_ssl row (ssl, version, cipher, bits) from the session_tls read."""
    status, value, error, error_class = result
    if status not in OBSERVED_STATUSES:
        return {'status': 'unreadable', 'error_class': error_class, 'error': error}
    if 'row' not in value:
        return {'status': 'not_observed', 'reason': 'the session_tls object has no row key'}
    row = value['row']
    if not isinstance(row, dict):
        return {'status': 'not_observed', 'reason': 'pg_stat_ssl has no row for this backend'}
    kept, field_status = {}, {}
    for key in ('ssl', 'version', 'cipher', 'bits'):
        kept[key], field_status[key] = _tls_field(key, row.get(key))
    return {'status': 'observed', 'pg_stat_ssl': kept, 'field_status': field_status}


def _address_class(identity):
    """RF-28 (e): the class of inet_client_addr(), never the address: unix_socket (null), loopback, link_local,
    private, global, or other (anything else, or text that is not an address)."""
    if 'client_addr' not in identity:
        return {'status': 'not_observed', 'value': None}
    text = identity['client_addr']
    if text is None:
        return {'status': 'observed', 'value': 'unix_socket'}
    try:
        address = ipaddress.ip_interface(text).ip if isinstance(text, str) else None
    except ValueError:
        address = None
    if address is None:
        klass = 'other'
    elif address.is_loopback:
        klass = 'loopback'
    elif address.is_link_local:
        klass = 'link_local'
    elif address.is_private:
        klass = 'private'
    elif address.is_global:
        klass = 'global'
    else:
        klass = 'other'
    return {'status': 'observed', 'value': klass}


def read_session(collector):
    """RF-28 (e): run session_settings and session_tls once each, record each as a query entry, and return the
    sidecar 'session' record. A failed read is that query's gap; it never refuses the run."""
    results = {}
    for qid in SESSION_READS:
        query = by_id(qid)
        status, value, error, error_class = collector.run(query)
        if status in OBSERVED_STATUSES and not isinstance(value, dict):
            status, value, error, error_class = ('unreadable', None, 'output is not one JSON object',
                                                 'malformed_output')
        collector.record_query(query, status, value, error, error_class)
        results[qid] = (status, value, error, error_class)
    return session_facts(results)


def session_facts(results):
    """RF-28 (e): the sidecar 'session' record from the two session reads."""
    status, settings, error, error_class = results['session_settings']
    names = ('transaction_read_only', 'default_transaction_read_only')
    if status in OBSERVED_STATUSES:
        effective = {name: _session_setting(settings, name) for name in names}
        address = _address_class(settings)
    else:
        failed = {'status': 'unreadable', 'value': None, 'error_class': error_class}
        effective = {name: dict(failed) for name in names}
        address = dict(failed)
    seen = [entry['value'] for entry in effective.values() if entry['status'] == 'observed']
    if any(value != 'on' for value in seen):
        read_only = False
    elif len(seen) == len(effective):
        read_only = True
    else:
        read_only = None
    return {'requested': dict(READ_ONLY_REQUESTED), 'effective': effective, 'read_only_effective': read_only,
            'tls': _tls_fact(results['session_tls']), 'client_address_class': address,
            'source': 'two control reads after the identity, version and membership checks: session_settings '
                      '(effective read-only settings, client address) and session_tls (the backend\'s own '
                      'pg_stat_ssl row). Each query runs in its own psql session with the same options, so these '
                      'are the facts of such a session.',
            'reading': 'observed facts only; the checker gives them a reading. A read-write session is a gap '
                       '(session:read_only), not a refusal, in this revision. A failed session read is the gap of '
                       'its query entry.'}


def session_gaps(session):
    """RF-28 (e): the typed gap entries for the session facts (a read-write session, a value of an unexpected
    shape). A failed session read is already a gap: its query entry."""
    effective = session['effective']
    if session['read_only_effective'] is False:
        return [{'kind': 'session', 'target': 'session:read_only', 'status': 'unsupported',
                 'error': 'the runner requested default_transaction_read_only=on; the session reports '
                          'transaction_read_only=%s and default_transaction_read_only=%s (a pooler may drop the '
                          'startup option); recorded, not refused' % (
                              effective['transaction_read_only']['value'],
                              effective['default_transaction_read_only']['value']),
                 'error_class': 'read_only_not_effective'}]
    if any(entry['status'] == 'unreadable' and 'error_class' not in entry for entry in effective.values()):
        return [{'kind': 'session', 'target': 'session:read_only', 'status': 'unreadable',
                 'error': 'the session reported a read-only setting in an unexpected form (not retained)',
                 'error_class': 'malformed_output'}]
    return []


# RF-24 (e): the collection role's creation fact. The collector itself never creates it; whether the role was made
# for this run is known only to whoever provisioned it, so it is recorded as operator-stated or not stated.
ROLE_CREATION_BASIS = ('collect_pg runs only single SELECT statements in a read-only session; it creates, alters '
                       'and grants nothing')


def role_creation(args):
    stated = getattr(args, 'role_created_for_run', None)
    return {'by_collector': False, 'by_collector_basis': ROLE_CREATION_BASIS,
            'for_run': None if stated is None else stated == 'yes',
            'for_run_source': 'not_stated' if stated is None else 'operator_flag'}


def parse_args(argv):
    parser = argparse.ArgumentParser(prog='collect_pg.py', add_help=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--role', required=True)
    parser.add_argument('--privileges', required=True)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--extra-root', action='append', default=[])
    parser.add_argument('--psql', default='psql')
    parser.add_argument('--role-created-for-run', choices=('yes', 'no'), default=None)   # RF-24 (e)
    parser.add_argument('--login-user', default=None)                                    # RF-28 (d)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        raise Refusal('invalid_arguments', 'argument parsing failed (see usage)', 2) from None
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,62}', args.role) or args.role.upper() == 'PUBLIC' \
            or args.role.startswith('pg_'):
        raise Refusal('invalid_arguments', '--role must be an identifier that is neither PUBLIC nor pg_-prefixed', 2)
    if args.login_user is None:                                                   # RF-28 (d): default is the role
        args.login_user, args.login_user_source = args.role, 'default_role'        # RF-28 (d)
    elif LOGIN_USER_RE.fullmatch(args.login_user):                                 # RF-28 (d)
        args.login_user_source = 'operator_flag'                                   # RF-28 (d)
    else:                                                                          # RF-28 (d)
        raise Refusal('invalid_arguments', '--login-user must be a name of 1 to 128 characters: a letter or '
                      'underscore, then letters, digits, underscores, dots or hyphens (RF-28 (d))', 2)
    privileges = [item.strip() for item in args.privileges.split(',') if item.strip()]
    bad = [item for item in privileges if item not in READ_ONLY_ROLES]
    broader = [item for item in bad if item in BROADER_READ_ROLES]   # RF-24 (h)
    if broader:   # RF-24 (h): accepted by the frozen collector, broader than ruling 20 allows
        raise Refusal('invalid_arguments', '--privileges names %s, broader than the least-privilege grants of '
                      'ruling 20 (only: %s)' % (', '.join(broader), ', '.join(READ_ONLY_ROLES)), 2)
    if not privileges or bad or len(set(privileges)) != len(privileges):
        raise Refusal('invalid_arguments', '--privileges must list, without duplicates, only: ' +
                      ', '.join(READ_ONLY_ROLES) + (' (refused entries: %s)' % ', '.join(bad) if bad else ''), 2)
    args.privilege_list = privileges
    roots = []
    for label, given in [('--data-dir', args.data_dir)] + [('--extra-root', item) for item in args.extra_root]:
        real = os.path.realpath(given)
        if not os.path.isdir(real) or real == '/':
            raise Refusal('invalid_arguments', '%s must name an existing directory other than the filesystem root'
                          % label, 2)
        if real not in roots:
            roots.append(real)
    args.roots = roots
    return args


def refuse(out, error, queries_run, role, staging=None):
    """The ONE refusal path for a run that owns --out: the staging directory and everything under --out are
    removed first; only then is the refusal document written, as the only output file."""
    if staging is not None and os.path.lexists(staging):
        shutil.rmtree(staging)
    if out.is_dir() and not out.is_symlink():
        wipe(out)
    doc = flagged({'schema': 'symbolia.rf06.pg-collector-refusal.v1', 'refusal': {'type': error.kind,
                   'reason': error.reason}, 'role': role, 'queries_run': queries_run, 'output_wiped': True,
                   'note': 'typed refusal: every byte this run had written (staging directory and --out) was removed '
                           'before this file was written; nothing was retried as another role'})
    out.mkdir(parents=True, exist_ok=True)
    (out / 'REFUSAL.json').write_text(dump(doc), encoding='utf-8')
    print(json.dumps(flagged({'status': 'refused', 'refusal': doc['refusal']}), sort_keys=True))
    return error.code


def selfcheck_refusal(hits):
    return Refusal('redaction_selfcheck_failed', 'a secret value this run stripped, or a fragment of one, was found in '
                   'the retained bytes of %s; every output file was removed (no value is reported)' % ', '.join(hits))


def run_staged(args, final, started):
    """Collect into a fresh staging directory beside --out, run every check there, then publish it as --out with
    one rename, or remove it and refuse. Nothing is ever written under --out except by the publish rename or by
    refuse()."""
    try:
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.%s.collect_pg-staging-' % final.name, dir=str(final.parent)))
    except OSError as error:
        print(json.dumps(flagged({'status': 'refused', 'refusal': {'type': 'output_unwritable', 'reason':
                                  'no staging directory beside --out: ' + type(error).__name__}}), sort_keys=True))
        return 3
    state = {}

    def ran():
        collector = state.get('collector')
        return list(collector.timing['query_elapsed_ms']) if collector else []
    try:
        code, message = _collect(args, staging, started, state)
    except Refusal as error:
        return refuse(final, error, ran(), args.role, staging)
    except Exception as failure:  # typed refusal, never a traceback; the class name only, never a value
        return refuse(final, Refusal('internal_error', type(failure).__name__ + ' (no traceback is printed; every '
                                     'partial output byte was removed)'), ran(), args.role, staging)
    try:
        os.rename(staging, final)               # POSIX: atomic, and allowed onto an empty directory
    except OSError:
        try:
            final.rmdir()
            os.rename(staging, final)
        except OSError as error:
            return refuse(final, Refusal('output_unwritable', 'the checked staging directory could not be published '
                                         'as --out: ' + type(error).__name__), ran(), args.role, staging)
    print(json.dumps(flagged(message), sort_keys=True))
    return code


def by_id(qid):
    return next(q for q in QUERIES if q['id'] == qid)


PRIVILEGED_ATTRIBUTES = ('rolbypassrls', 'rolcreaterole', 'rolcreatedb', 'rolreplication')


def check_identity(collector, role):
    query = by_id('collector_identity')
    status, value, error, error_class = collector.run(query)
    if status not in ('observed',) or not isinstance(value, dict):
        raise Refusal('collection_role_unverified', 'the collection role row could not be read from pg_roles (%s): %s'
                      % (status, error or 'no row'))
    if value.get('rolsuper') is True:
        raise Refusal('collection_role_superuser', 'pg_roles.rolsuper is true for the collection role %r; a superuser '
                      'is never used for collection' % value.get('current_user'))
    if value.get('current_user') != role or value.get('session_user') != role:
        raise Refusal('collection_role_mismatch', 'connected as current_user %r / session_user %r, not the declared '
                      'collection role %r' % (value.get('current_user'), value.get('session_user'), role))
    if value.get('rolsuper') is not False:
        raise Refusal('collection_role_unverified', 'pg_roles.rolsuper is not a boolean false for the collection role')
    granted = [name for name in PRIVILEGED_ATTRIBUTES if value.get(name) is True]
    if granted:
        raise Refusal('collection_role_not_read_only', 'the collection role row has %s true; a read-only collection '
                      'role holds none of %s' % (', '.join(granted), ', '.join(PRIVILEGED_ATTRIBUTES)))
    unknown = [name for name in PRIVILEGED_ATTRIBUTES if value.get(name) is not False]
    if unknown:
        raise Refusal('collection_role_unverified', 'pg_roles %s not a boolean false for the collection role'
                      % ', '.join(unknown))
    collector.record_query(query, status, value, None, None)
    return value


def check_memberships(collector):
    """The collection role's direct role memberships must lie within READ_ONLY_ROLES (RF-24 (h): the two of ruling 20)."""
    query = by_id('collector_memberships')
    status, value, error, error_class = collector.run(query)
    if status not in ('observed', 'observed_empty') or not isinstance(value, list) or \
            not all(isinstance(item, str) for item in value):
        raise Refusal('collection_role_unverified', 'the collection role memberships could not be read from '
                      'pg_auth_members (%s): %s' % (status, error or 'not a list of role names'))
    outside = sorted(set(value) - set(READ_ONLY_ROLES))
    if outside and set(outside) <= set(BROADER_READ_ROLES):   # RF-24 (h): read-only, but broader than ruling 20
        raise Refusal('collection_role_not_least_privilege', 'the collection role is a direct member of %s, broader '
                      'than the least-privilege grants of ruling 20 (%s); nothing is collected'
                      % (', '.join(outside), ', '.join(READ_ONLY_ROLES)))
    if outside:
        raise Refusal('collection_role_not_read_only', 'the collection role is a direct member of %s, outside the '
                      'read-only collection roles (%s); nothing is collected' % (', '.join(outside),
                                                                                 ', '.join(READ_ONLY_ROLES)))
    collector.record_query(query, status, value, None, None)
    return status, value


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--emit-queries'] and len(argv) == 2:
        Path(argv[1]).write_text(render_queries(), encoding='utf-8')
        return 0
    if argv[:1] == ['--emit-secret-keywords'] and len(argv) == 2:
        Path(argv[1]).write_text(render_secret_keywords(), encoding='utf-8')
        return 0
    started = now()
    _reset_secrets()
    try:
        args = parse_args(argv)
    except Refusal as error:
        print(json.dumps(flagged({'status': 'refused', 'refusal': {'type': error.kind, 'reason': error.reason}}),
                         sort_keys=True))
        return error.code
    out = Path(args.out)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        print(json.dumps(flagged({'status': 'refused', 'refusal': {'type': 'output_not_empty', 'reason':
                                  '--out must be a new or empty directory'}}), sort_keys=True))
        return 3
    return run_staged(args, out, started)


def withheld_row_list(manifest, line_records):
    """RF-28 (b): the sidecar redaction_withheld rows. The field names file, field and count are kept; each row gains
    line and reason. A text file the collector parses has one row per (line, field, reason); a JSON output file
    keeps one row per field with line null and reason JSON-VALUE-WITHHELD. Per (file, field) the counts sum to the
    REDACTION-MANIFEST.json entry."""
    def kept(field):
        return 'withheld' in field or 'unparsed' in field
    counts = Counter((file, number, field, reason) for file, record in line_records.items()
                     for number, field, reason in record if kept(field))
    rows = [{'file': file, 'field': field, 'count': count, 'line': number, 'reason': reason}
            for (file, number, field, reason), count in counts.items()]
    rows += [{'file': file, 'field': field, 'count': count, 'line': None, 'reason': 'JSON-VALUE-WITHHELD'}
             for (file, field), count in manifest.items() if kept(field) and file not in line_records]
    return sorted(rows, key=lambda row: (row['file'], row['line'] or 0, row['field'], row['reason']))


def _collect(args, out, started, state):
    """The collection itself. `out` is the STAGING directory; a Refusal (or any exception) raised here makes
    run_staged remove it and refuse. Returns (exit code, the status message printed after publishing)."""
    if RUNNER is psql_runner:
        _PSQL['argv'], _PSQL['env'] = build_psql_command(args.psql, getattr(args, 'login_user', args.role))   # RF-28 (d)
    collector = Collector(args, str(Path(args.data_dir).resolve()), args.roots)
    state['collector'] = collector
    try:
        identity = check_identity(collector, args.role)
        query = by_id('server_version')
        status, value, error, error_class = collector.run(query)
        if status != 'observed' or not isinstance(value, dict):
            raise Refusal('server_version_unreadable', 'server_version_num could not be read: %s' % error)
        try:
            major = int(str(value.get('server_version_num'))) // 10000
        except ValueError:
            raise Refusal('server_version_unreadable', 'server_version_num is not an integer') from None
        if not MAJORS[0] <= major <= MAJORS[1]:
            raise Refusal('unsupported_major', 'major %d is outside the published query list (14..18)' % major)
        collector.record_query(query, status, value, None, None)
        member_result = check_memberships(collector)
    except Refusal:
        raise
    collector.major = major
    session = read_session(collector)                                            # RF-28 (e)
    collector.entries.extend(session_gaps(session))                               # RF-28 (e)
    server = {'major': major, 'server_version': value.get('server_version'),
              'server_version_num': value.get('server_version_num')}

    # ---- every other applicable query, once each, in published order
    raw_results = {'collector_memberships': member_result}
    for query in QUERIES:
        if query['id'] in ('collector_identity', 'server_version', 'collector_memberships') + SESSION_READS:  # RF-28 (e)
            continue
        if not query['min_major'] <= major <= query['max_major']:
            continue
        status, value, error, error_class = collector.run(query)
        raw_results[query['key'] or query['id']] = (status, value)
        if query['target'] == 'timing':
            collector.entries.append({'kind': 'query', 'target': 'query:' + query['id'], 'id': query['id'],
                                      'key': query['id'], 'views': query['views'],
                                      'status': status if status != 'observed' else 'observed',
                                      'error': error, 'error_class': error_class, 'rows': None,
                                      'note': 'values volatile; written only to TIMING.json'})
            continue
        collector.record_query(query, status, value, error, error_class)
    for key in CATALOG_KEYS:
        if key not in raw_results:
            gated = [q for q in QUERIES if q['key'] == key]
            collector.entries.append({'kind': 'query', 'target': 'query:' + key, 'id': None, 'key': key,
                                      'views': gated[0]['views'], 'status': 'declared_absent',
                                      'error': 'no published query for major %d (version gate %s)' % (
                                          major, ', '.join('%d-%d' % (q['min_major'], q['max_major']) for q in gated)),
                                      'error_class': 'version_gate', 'rows': None})

    def ok(key):
        return key in raw_results and raw_results[key][0] in ('observed', 'observed_empty')

    # ---- file locations (server view, remapped onto --data-dir)
    locations = raw_results.get('file_locations', (None, None))[1] if ok('file_locations') else {}
    locations = locations if isinstance(locations, dict) else {}
    collector.server_dd = locations.get('data_directory') if isinstance(locations.get('data_directory'), str) else None
    where = {}
    defaults = {'config_file': 'postgresql.conf', 'hba_file': 'pg_hba.conf', 'ident_file': 'pg_ident.conf'}
    base_server = collector.server_dd or collector.local_dd
    location_query = [e for e in collector.entries if e.get('id') == 'file_locations']
    for name, default in defaults.items():
        value = locations.get(name)
        if isinstance(value, str) and value.startswith('/'):
            where[name] = {'server': value, 'basis': 'pg_settings.' + name}
            continue
        if not ok('file_locations'):
            status, error_class = 'unreadable', (location_query[0]['error_class'] if location_query else 'other')
            why = 'the file_locations read did not succeed'
        elif name not in locations:
            status, error_class, why = 'missing', 'row_absent', 'pg_settings.%s was not returned' % name
        else:
            status, error_class, why = 'unreadable', 'malformed_output', 'pg_settings.%s is not an absolute path' % name
        where[name] = {'server': None, 'basis': 'not observed (%s); no default location is used and %s is not '
                       'collected' % (why, default)}
        collector.entries.append({'kind': 'location', 'target': 'location:' + name, 'status': status,
                                  'error': why + '; the server location of %s is unknown, so no file is copied for it'
                                  % default, 'error_class': error_class})
    where['postgresql.auto.conf'] = {'server': posixpath.join(base_server, 'postgresql.auto.conf'),
                                     'basis': 'the data directory (%s)' % ('pg_settings.data_directory'
                                                                           if collector.server_dd else '--data-dir')}
    where['postmaster.opts'] = {'server': posixpath.join(base_server, 'postmaster.opts'),
                                'basis': 'the data directory (%s)' % ('pg_settings.data_directory'
                                                                      if collector.server_dd else '--data-dir')}
    for item in where.values():
        item['read_from'] = collector.remap(item['server'])

    for grammar, name, raw_rel in (('conf', 'config_file', 'postgresql.conf'),
                                   ('conf', 'postgresql.auto.conf', 'postgresql.auto.conf'),
                                   ('hba', 'hba_file', 'pg_hba.conf'), ('ident', 'ident_file', 'pg_ident.conf')):
        if where[name]['server'] is not None:
            collector.take(grammar, where[name]['server'], raw_rel)

    manifest = Counter()

    def note_fields(file, fields):
        for field in fields:
            manifest[(file, field)] += 1

    # ---- raw files: redacted, then retained
    raw = out / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    (raw / 'clients').mkdir(exist_ok=True)
    identifier_forms = []                          # RF-27 (b): sidecar hba_identifier_forms
    line_records = {}                              # RF-28 (b): per-line withheld rows of each text file
    for raw_rel in sorted(collector.files):
        item = collector.files[raw_rel]
        text = item['bytes'].decode('utf-8', 'surrogateescape')
        redactor = {'conf': redact_conf_text, 'hba': redact_hba_text}.get(item['grammar'], redact_plain_text)
        record = line_records.setdefault('raw/' + raw_rel, [])                      # RF-28 (b)
        new, fields = redactor(item['bytes'], record=record)   # RF-28 (b); split at b'\n', each line decoded afterwards
        note_fields('raw/' + raw_rel, fields)
        target = raw / raw_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new.encode('utf-8', 'surrogateescape') if fields else item['bytes'])
        if item['grammar'] == 'hba':          # RF-27 (b): forms of the retained records, no values
            identifier_forms.extend(dict(file='raw/' + raw_rel, **entry) for entry in hba_identifier_forms(new))
            note_hba_retained(new)                  # RF-27 (e): the view keeps only these identifiers

    # ---- command line closure
    command = flagged({'schema': 'symbolia.rf06.command-line.v1',
                       'reading': 'postmaster.opts holds the command line the running server was started with; '
                                  'settings_from_command_line are pg_settings rows whose source is the command line '
                                  'or the environment. A key is absent when its read failed (see the sidecar).'})
    opts_server = where['postmaster.opts']['server']
    opts_local = collector.remap(opts_server)
    try:
        refused = collector.confine(opts_local)
        if refused:
            raise PermissionError(refused)
        opts_text = Path(opts_local).read_bytes().decode('utf-8', 'replace')
        try:
            argv_items, opts_lines, opts_fields = parse_postmaster_opts(opts_text)
        except ValueError as ambiguous:
            reason = OPTS_WITHHELD % ambiguous
            _note_loose(opts_text)
            for found in re.finditer(r'(?i)%s\s*=' % PASSPHRASE_NAME, opts_text):
                _note_secret(opts_text[found.end():].split('" "', 1)[0], command=True)
            command['postmaster_opts'] = {'file': 'postmaster.opts', 'server_path': opts_server,
                                          'argv': None, 'lines': None, 'withheld': reason}
            collector.file_entry(None, opts_server, 'unreadable', reason, 'raw/command_line.json postmaster_opts')
            collector.entries[-1]['error_class'] = 'malformed_output'
            note_fields('raw/command_line.json', ['postmaster_opts:withheld (not parseable unambiguously)'])
        else:
            command['postmaster_opts'] = {'file': 'postmaster.opts', 'server_path': opts_server,
                                          'argv': argv_items, 'lines': opts_lines}
            note_fields('raw/command_line.json', ['command_line.' + field for field in opts_fields])
            collector.file_entry(None, opts_server, 'observed' if opts_text else 'observed_empty', None,
                                 'raw/command_line.json postmaster_opts')
    except FileNotFoundError:
        collector.file_entry(None, opts_server, 'missing', 'FileNotFoundError: no file at ' + str(opts_local),
                             'raw/command_line.json postmaster_opts')
    except PermissionError as error:
        text = str(error) if 'outside the declared roots' in str(error) else 'PermissionError reading ' + str(opts_local)
        collector.file_entry(None, opts_server, 'unsupported' if 'outside the declared roots' in text else 'unreadable',
                             text, 'raw/command_line.json postmaster_opts')
    except OSError as error:
        collector.file_entry(None, opts_server, 'unreadable', type(error).__name__ + ' reading ' + str(opts_local),
                             'raw/command_line.json postmaster_opts')
    if ok('command_line_settings'):
        command['settings_from_command_line'] = raw_results['command_line_settings'][1]
    fields = []
    vetted = command.pop('postmaster_opts', None)   # parse_postmaster_opts already applied the follow-up 4 rule item by item
    command = redact_tree(command, 'command_line', fields)
    if vetted is not None:
        command['postmaster_opts'] = vetted
    note_fields('raw/command_line.json', fields)
    (raw / 'command_line.json').write_text(dump(command), encoding='utf-8')

    # ---- catalog snapshot (a key only for a catalog that was read)
    unreadable_views = sorted({view for q in QUERIES if q['key'] and q['key'] in raw_results
                               and raw_results[q['key']][0] == 'unreadable'
                               and q['min_major'] <= major <= q['max_major'] for view in q['views'][:1]})
    snapshot = flagged({'collection': {'role': args.role, 'privileges': args.privilege_list,
                                       'unreadable_views': unreadable_views,
                                       'server_version_num': server['server_version_num'],   # RF-24 (c)
                                       'role_creation': role_creation(args),                 # RF-24 (e)
                                       'not_observed_fields':                                # RF-24 (a) (b)
                                           json.loads(json.dumps(NOT_OBSERVED_FIELDS))}})
    for key in CATALOG_KEYS:
        if ok(key):
            snapshot[key] = raw_results[key][1]
    assembled = []
    if ok(SUB_KEY) and ok('subscription_rels') and isinstance(snapshot.get(SUB_KEY), list):   # RF-24 (a)
        for sub in snapshot[SUB_KEY]:
            if isinstance(sub, dict):
                sub['tables'] = [row.get('relname') for row in snapshot['subscription_rels']
                                 if isinstance(row, dict) and row.get('subname') == sub.get('subname')]
        assembled.append(SUB_KEY + '[].tables from subscription_rels (both reads succeeded)')   # RF-24 (a)
    fields = []
    snapshot = redact_tree(snapshot, 'catalog_snapshot', fields)
    note_fields('raw/catalog_snapshot.json', [f[len('catalog_snapshot.'):] for f in fields])
    (raw / 'catalog_snapshot.json').write_text(dump(snapshot), encoding='utf-8')

    # ---- pg_settings dump in the RF-01 preflight shape (every value a string or null)
    if ok('pg_settings') and isinstance(raw_results['pg_settings'][1], list):
        rows, returned = [], set()
        for row in raw_results['pg_settings'][1]:
            if not isinstance(row, dict):
                continue
            returned.add(row.get('name'))
            out_row = {}
            for field in PG_SETTINGS_FIELDS:
                value = row.get(field)
                out_row[field] = None if value is None else (('true' if value else 'false')
                                                             if isinstance(value, bool) else str(value))
            server_file = row.get('sourcefile')
            out_row['server_sourcefile'] = server_file
            if isinstance(server_file, str) and posixpath.normpath(server_file) in collector.server_to_raw:
                out_row['sourcefile'] = collector.server_to_raw[posixpath.normpath(server_file)]
                out_row['sourcefile_mapping'] = 'raw-relative copy of the server file'
            elif server_file is not None:
                out_row['sourcefile_mapping'] = 'server path kept: no raw/ copy of this file'
            rows.append(flagged(out_row))
        fields = []
        for row in rows:
            name = row['name'] if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', row['name'] or '') else '?'
            for field in sorted(row):
                if not isinstance(row[field], str) or field in FLAGS or field == 'name':
                    continue
                if field in ('setting', 'boot_val', 'reset_val') and value_withheld(name, row[field]):
                    _note_withheld(row[field], command=secret_guc(name)[0])
                    row[field] = WITHHELD_VALUE
                    fields.append('%s.%s:%s:withheld_whole' % (name, field, name))
                elif structured_string(row[field]):
                    _note_withheld(row[field])
                    row[field] = WITHHELD_VALUE
                    fields.append('%s.%s:%s:withheld_whole' % (name, field, field))
        note_fields('raw/pg_settings.json', fields)
        (raw / 'pg_settings.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                                              encoding='utf-8')
        for name in SETTINGS_COLLECTED:
            if name not in returned:
                collector.entries.append({'kind': 'setting_row', 'target': 'pg_settings:' + name,
                                          'status': 'missing', 'error': 'row not returned by pg_settings to the '
                                          'collection role', 'error_class': 'row_absent'})
    else:
        collector.entries.append({'kind': 'file', 'target': 'file:raw/pg_settings.json', 'server_path': None,
                                  'status': 'unreadable', 'error': 'not written: the pg_settings read did not '
                                  'succeed', 'via': 'query pg_settings'})

    (out / 'QUERIES.json').write_text(render_queries(), encoding='utf-8')
    (out / 'SECRET-KEYWORDS.json').write_text(render_secret_keywords(), encoding='utf-8')

    # ---- redaction manifest (labels and counts only; digests of sanitised files)
    digests = {p.relative_to(out).as_posix(): sha256(p.read_bytes()) for p in sorted(raw.rglob('*')) if p.is_file()}
    manifest_doc = flagged({'schema': 'symbolia.rf06.redaction-manifest.v1',
                            'entries': [{'file': file, 'field': field, 'count': count}
                                        for (file, field), count in sorted(manifest.items())],
                            'sanitised_sha256': digests,
                            'withheld_whole': [{'file': file, 'name': field.rsplit(':', 2)[-2], 'field': field,
                                                'withheld_whole': True, 'count': count,
                                                'reason': withhold_reason(field.rsplit(':', 2)[-2])}
                                               for (file, field), count in sorted(manifest.items())
                                               if field.endswith(':withheld_whole') and field.count(':') >= 2],
                            'inversion_rule': 'see SECRET-KEYWORDS.json inversion_rule; a withheld_whole entry names '
                                              'a setting or field present in the source whose value is not retained',
                            'rule': 'every secret keyword of SECRET-KEYWORDS.json (password, passfile, sslpassword, oauth_client_secret and any name containing password, passwd, passphrase, secret or token; conninfo keywords parsed with libpq '
                                    'keyword/value rules, whole values, nested conninfo recursively; URI userinfo up to the last @ before '
                                    'the first / and '
                                    'URI parameters, '
                                    'percent-encoded keywords included), PGPASSWORD/PGSSLPASSWORD assignments, '
                                    'ldapbindpasswd and radiussecret(s) (pg_hba options, hba.c next_token rules, continued lines '
                                    'withheld whole) and ssl_passphrase_command '
                                    'values (conf lines, setting rows, and command-line items: name=value, -c, '
                                    '--name=value, dashed spelling) are stripped before any byte is retained; every '
                                    'check also runs on the percent-decoded text; a line or value with a secret '
                                    'pattern that cannot be stripped field by field is withheld whole. No value and no '
                                    'hash of a value is recorded.'})
    (out / 'REDACTION-MANIFEST.json').write_text(dump(manifest_doc), encoding='utf-8')

    # ---- sidecar
    memberships = raw_results.get('collector_memberships', (None, None))
    observed_grants = sorted(memberships[1]) if memberships[0] in ('observed', 'observed_empty') and \
        isinstance(memberships[1], list) else None
    entries = sorted(collector.entries, key=lambda e: (e['kind'], e['target']))
    gaps = [e for e in entries if e['status'] not in OK_STATUSES]
    withheld_rows = withheld_row_list(manifest, line_records)                     # RF-28 (b)
    sidecar = flagged({
        'schema': 'symbolia.rf06.collection-sidecar.v1',
        'status_vocabulary': ['observed', 'observed_empty', 'declared_absent', 'unreadable', 'missing', 'unsupported'],
        'collector': {'tool': 'collect_pg.py', 'tool_sha256': sha256(Path(__file__).read_bytes()),
                      'queries_sha256': sha256(render_queries().encode('utf-8'))},
        'role': args.role, 'privileges_declared': args.privilege_list,
        'collection_role_row': {k: identity.get(k) for k in sorted(identity) if k.startswith('rol')},
        'privileges_observed': observed_grants,
        'privileges_check': None if observed_grants is None else {
            'declared_not_observed': sorted(set(args.privilege_list) - set(observed_grants)),
            'observed_not_declared': sorted(set(observed_grants) - set(args.privilege_list))},
        'server': server, 'data_dir': collector.local_dd, 'server_data_directory': collector.server_dd,
        'declared_roots': collector.roots,
        'confinement': 'every file is read only if its path, links resolved, lies under a declared root '
                       '(--data-dir, --extra-root); anything else is refused and recorded unsupported',
        'locations': where, 'entries': entries, 'gap_count': len(gaps), 'complete': not gaps,
        'assembled': assembled,
        'redaction_withheld': withheld_rows,          # RF-28 (b): one row per withheld line, with line and reason
        'connection': {'login_user': getattr(args, 'login_user', args.role),              # RF-28 (d)
                       'login_user_source': getattr(args, 'login_user_source', 'default_role'),
                       'role_examined': args.role},
        'session': session,                           # RF-28 (e)
        'hba_identifier_forms': identifier_forms,     # RF-27 (b)
        'loaded_identity': {'status': 'not_observed',
                            'reason': 'pg_hba_file_rules and pg_file_settings parse the current files on disk; the '
                                      'collector reads no view of the rules the server last loaded, so loaded-versus-'
                                      'disk identity is not observed here (configuration load time is in TIMING.json)'},
        'operator_supplied': ['raw/declaration.json', 'raw/clients.json', 'raw/clients/'],
        'retry_policy': 'each query ran at most once, as the declared collection role only',
        'redaction_selfcheck': {
            'status': 'passed', 'secret_values': len(_SECRETS['whole']),
            'short_values_not_scanned': len(_SECRETS['short']),
            'rule': 'every secret value the run stripped (and every fragment of %d or more characters, split at '
                    'whitespace, quotes and backslashes) is held in memory only and searched for, raw, JSON-escaped, '
                    'conf-quoted, libpq-quoted and as a sha256 hex digest, in every retained file; any hit removes '
                    'every output file and exits 3 with REFUSAL.json (redaction_selfcheck_failed). This sidecar is '
                    'kept only when the scan of raw/, QUERIES.json and REDACTION-MANIFEST.json and the final scan '
                    'of every file found nothing. Values shorter than %d characters are counted, not scanned.'
                    % (SELFCHECK_MIN, SELFCHECK_MIN)}})
    (out / 'COLLECTION-SIDECAR.json').write_text(dump(sidecar), encoding='utf-8')

    times = raw_results.get('server_times', (None, None))
    timing = flagged({'schema': 'symbolia.rf06.timing.v1', 'started_at': started, 'finished_at': now(),
                      'query_elapsed_ms': collector.timing['query_elapsed_ms'],
                      'file_mtimes': collector.timing['file_mtimes'],
                      'server_times': times[1] if times[0] == 'observed' else None,
                      'config_file_mtimes_ns': collector.timing['file_mtimes_ns']})   # RF-24 (d)
    (out / 'TIMING.json').write_text(dump(timing), encoding='utf-8')
    # ---- every check runs on the complete staging directory before anything is published
    structural = structural_check_out(out, {('raw/' + rel): item['grammar'] for rel, item in collector.files.items()})
    if structural:
        raise Refusal('redaction_structural_check_failed', 'a retained conf value, hba option or setting value breaks '
                      'the structural rule (no = inside a retained value outside the allowlist path; no control or '
                      'line-separator character in a retained line) in: ' + ', '.join(structural))
    hits = selfcheck_scan(out)
    if hits:
        raise selfcheck_refusal(hits)
    return (0 if not gaps else 1), {'status': 'collected', 'complete': not gaps, 'gap_count': len(gaps),
                                    'out': 'COLLECTION-SIDECAR.json'}


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as failure:  # typed refusal, never a traceback; the class name only, never a value
        print(json.dumps(flagged({'status': 'refused', 'refusal': {
            'type': 'internal_error', 'reason': type(failure).__name__ + ' (no traceback is printed; any partial '
                                                'output under --out must be discarded)'}}), sort_keys=True))
        sys.exit(3)
