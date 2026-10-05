"""Typed failure outcomes (DD-054; DESIGN-001 section 5). A failure is a named outcome, never a silent pass and never an
unexplained stop. Each carries an HTTP status (API), an exit code (Action) and one plain sentence telling the customer
what to do next.

The database's outcome list (db/migrations/0001_foundation.sql) holds every name here. `lease_lost` and the other
job-internal names (lease_expired, attempts_exhausted, ...) stay in the database and hosted/jobs.py: a customer never
receives them."""
from __future__ import annotations

import re
from types import MappingProxyType

_TABLE = {
    'bad_input': (400, 2, 'Fix the request so every file is allow-listed for the profile and well formed, then send it again.'),
    'oversize_input': (413, 2, 'Send fewer or smaller files, within the published size and count limits.'),
    'unknown_profile': (404, 2, 'Choose a profile from the list of served profiles.'),
    'unauthenticated': (401, None, 'Send a valid, unrevoked API key in the Authorization header.'),
    'rate_limited': (429, None, 'Wait for the time given in Retry-After, then send the request again.'),
    'credit_exhausted': (402, None, 'Your free credit is spent; contact Symbolia to continue.'),
    'engine_digest_mismatch': (503, 3, 'Report it to Symbolia (or reinstall the pinned release when you run the engine yourself), because the engine files differ from their pin and no check ran.'),
    'collector_cannot_connect': (None, 3, 'Check the connection settings and that the server accepts the collection role.'),
    'collector_refused': (422, 3, 'Fix what the reason names and run again; for a rule shape not yet checkable, rewrite it as the reason says or send Symbolia the file name and line number it gives.'),
    'profile_not_servable': (503, 3, 'Use another profile, because this one is not yet qualified to serve readings.'),
    'profile_refused': (422, 3, 'Fix the collection or declaration fault the reason names, then run again.'),
    'checker_error': (500, 3, 'Report the check id to Symbolia, because the checker failed in a way it should not.'),
    'checker_timeout': (504, 3, 'Send a smaller input or try again later, because the check ran past its time limit.'),
    'server_busy': (503, None, 'Try again in a minute, because the queue is full.'),
    'not_found': (404, None, 'Check the check id, because no check with that id exists for this account.'),
    'secret_in_input': (422, 2, 'Remove the secret the reason names from the input, then send it again; nothing was stored.'),
    'store_unavailable': (503, None, 'Try again in a minute, because the result store cannot be reached just now.'),
    # The Action's own outcomes when it reaches the hosted API: never sent by the server, so they carry no HTTP status.
    'api_unreachable': (None, 3, 'Check that the runner can reach the API over HTTPS, then run the job again.'),
    'api_error': (None, 3, 'Run the job again later, and report the check id to Symbolia if it happens again.'),
}

OUTCOMES = MappingProxyType({name: MappingProxyType({'http': http, 'exit': code, 'action': action})
                             for name, (http, code, action) in _TABLE.items()})

# ---------- what was malformed (DIRECTOR-DECISIONS-SERVE-002 Addendum 1, decision 10) ----------
# A typed failure whose cause is in the customer's input carries `detail.malformation`: {kind, file, line, field,
# expected}. Every value is closed: `kind` and `expected` come from this table, `field` from FIELDS (or a derive kind
# from DERIVE_KINDS), `file` is a raw/ name that passes NAME_RE (the allow-list grammar of the profile rows; anything
# else reads `other`), `line` is a positive integer or None. No value is ever text taken from the input's bytes.
MALFORMATIONS = MappingProxyType({
    # the request
    'body_encoding': 'a body sent with one Content-Length header and no Transfer-Encoding',
    'body_not_utf8': 'a body that is UTF-8 text',
    'body_not_json': 'a body that is one JSON document without duplicate keys or non-finite numbers',
    'body_shape': 'a JSON object with exactly the keys profile and files, profile a string and files an object',
    'file_value': 'each file as a strict base64 string',
    'file_name': 'a relative name under raw/ that the profile accepts, without control characters, backslashes or '
                 'empty, "." or ".." segments',
    'file_missing': 'every file the profile requires',
    'file_conflict': 'one name per file, and no name that is both a file and a directory',
    'query': 'only the query parameters this route accepts, each at most once',
    'fail_on': 'a comma list of the words this profile accepts, or never alone',
    'allow_partial': 'true or false (the API query: 1 or 0)',
    'idempotency_key': 'one Idempotency-Key of 16 to 64 characters of A-Z, a-z, 0-9, _ and -',
    # a file's content
    'json_file': 'valid JSON in this file',
    'json_unicode': 'strings in this file that are valid Unicode',
    'reading_changed': 'a line whose comment can be withheld without changing what the check reads from it',
    'continuation_major': 'one server major across raw/declaration.json and COLLECTION-SIDECAR.json',
    # the collector's RF-28 whole-line marker (MARKER-CONTRACT-001)
    'marker_grammar': 'a whole line of exactly the form !collect_pg-withheld line <N> reason <CODE>, optionally '
                      'followed by setting <name>',
    'marker_line': 'a marker whose line number is its own physical line number',
    'marker_reason': 'a marker whose reason code is in the collector\'s closed list',
    'marker_in_json': 'no marker line in a JSON file',
    'collector_mixed': 'one collector run: RF-28 markers with the RF-28 COLLECTION-SIDECAR.json, or earlier comment '
                       'markers with the earlier sidecar, never both',
    # the earlier collector's comment marker and its records
    'sidecar_absent': 'the COLLECTION-SIDECAR.json the collector wrote in the same run as raw/',
    'sidecar_unreadable': 'a readable COLLECTION-SIDECAR.json with its redaction_withheld list',
    'sidecar_rows': 'a COLLECTION-SIDECAR.json redaction_withheld row for each withheld line of this file',
    'marker_unaccounted': 'as many sidecar rows saying a comment was withheld as there are withheld lines',
    'rule_withheld': 'a pg_hba.conf rule the collector can keep (or the RF-28 collector, which marks it)',
    'setting_withheld': 'a setting line the collector can keep (or the RF-28 collector, which marks it)',
    'manifest_absent': 'the REDACTION-MANIFEST.json the collector wrote in the same run as raw/',
    'manifest_unreadable': 'a readable REDACTION-MANIFEST.json with sanitised_sha256 and entries',
    'manifest_digest': 'this file byte for byte as the collector wrote it in the run the manifest records',
    'manifest_rows': 'COLLECTION-SIDECAR.json and REDACTION-MANIFEST.json rows that agree for this file',
    # the checker's derive refused the collection (the derive's own typed kind is in `field`)
    'derive_refused': 'a collection the derive step accepts; the field names the derive\'s own refusal kind',
    # the selected scope a profile row reads from the request (docs/PROFILES.md), bound before the checker runs
    'scope_missing': 'the selected scope this profile checks, as a list of 1 to 256 distinct ids of A-Z, a-z, 0-9, '
                     '_, . and -; a profile whose scope is fixed takes none',
    # serve-006 gap 1: the selected scope's binding, and a reference to an accepted scope (no store resolves one yet)
    'scope_binding': 'for a profile that declares a scope binding, an object with one key, the map the profile names, '
                     'that maps every selected id to its own token of 1 to 63 characters of A-Z, a-z, 0-9, _, . and '
                     '-; a profile that declares none takes none',
    'scope_ref': 'no accepted_scope_ref: no accepted scope record can be resolved yet, so a first-run comparison '
                 'omits it; a profile whose scope is fixed takes none',
})
# A field path the malformation may name: request fields, JSON fields the checks read, and derive locators.
FIELDS = frozenset({'profile', 'files', 'Content-Length', 'Transfer-Encoding', 'Idempotency-Key', 'fail_on',
                    'allow_partial', 'redaction_withheld', 'sanitised_sha256', 'entries', 'major', 'server.major',
                    'server.server_version_num', 'policies', 'declared_predicate', 'collection.role', 'role',
                    'scope_binding', 'accepted_scope_ref'})
# The observed derive's typed kinds (INTERFACE-CONTRACT-OB-001 section 4.6, STABLE).
DERIVE_KINDS = frozenset({'derived', 'schema_gate_every_machine', 'major_not_observed', 'major_disagreement',
                          'major_out_of_range', 'collection_role_disagreement', 'collection_role_not_observed',
                          'raw_missing', 'raw_unreadable', 'inputs_unreadable', 'derive_digest', 'internal'})
NAME_RE = re.compile(r'raw/(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}/){0,10}[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}')
MALFORMATION_KEYS = ('kind', 'file', 'line', 'field', 'expected')


def malformation(kind, file=None, line=None, field=None, kinds=()):
    """The closed description of what was malformed (module comment above). An unknown kind is a ValueError: the
    vocabulary is closed in code, never at run time. `kinds` adds a profile row's own closed derive kinds (its
    `derive_result.kinds`, checked against KIND_RE when the row is loaded) to the fields a malformation may name."""
    if kind not in MALFORMATIONS:
        raise ValueError('unknown malformation kind: %r' % (kind,))
    if file is not None:
        file = file if isinstance(file, str) and NAME_RE.fullmatch(file) else 'other'
    if not (type(line) is int and line > 0):
        line = None
    if field is not None and field not in FIELDS and field not in DERIVE_KINDS and field not in _row_kinds(kinds):
        field = None
    return {'kind': kind, 'file': file, 'line': line, 'field': field, 'expected': MALFORMATIONS[kind]}


# A derive kind a profile row may declare (serve/profiles.py checks every row kind against it when loading the row).
KIND_RE = re.compile(r'[a-z][a-z0-9_]{0,63}')


def _row_kinds(kinds):
    return frozenset(k for k in kinds if isinstance(k, str) and KIND_RE.fullmatch(k))


def is_closed(value, kinds=()):
    """True when `value` is a malformation built by `malformation` (every value from the closed vocabulary); `kinds`
    as for `malformation`."""
    if not isinstance(value, dict) or tuple(sorted(value)) != tuple(sorted(MALFORMATION_KEYS)):
        return False
    kind = value['kind']
    return (kind in MALFORMATIONS and value['expected'] == MALFORMATIONS[kind]
            and (value['file'] is None or value['file'] == 'other'
                 or (isinstance(value['file'], str) and NAME_RE.fullmatch(value['file']) is not None))
            and (value['line'] is None or (type(value['line']) is int and value['line'] > 0))
            and (value['field'] is None or value['field'] in FIELDS or value['field'] in DERIVE_KINDS
                 or value['field'] in _row_kinds(kinds)))


class Refusal(Exception):
    """A typed outcome: `Refusal(outcome, reason, **detail)`. An unknown outcome name is a ValueError at construction."""

    def __init__(self, outcome, reason='', **detail):
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise ValueError('unknown outcome: %r' % (outcome,))
        self.outcome = outcome
        self.reason = str(reason)
        self.detail = dict(detail)
        super().__init__('%s: %s' % (outcome, self.reason))

    @property
    def http(self):
        return OUTCOMES[self.outcome]['http']

    @property
    def exit(self):
        return OUTCOMES[self.outcome]['exit']

    @property
    def action(self):
        return OUTCOMES[self.outcome]['action']

    def to_dict(self):
        return {'outcome': self.outcome, 'reason': self.reason, 'action': self.action, 'detail': dict(self.detail)}

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
