"""Typed failure outcomes (DD-054; DESIGN-001 section 5). A failure is a named outcome, never a silent pass and never an
unexplained stop. Each carries an HTTP status (API), an exit code (Action) and one plain sentence telling the customer
what to do next.

The database's outcome list (db/migrations/0001_foundation.sql) holds every name here. `lease_lost` and the other
job-internal names (lease_expired, attempts_exhausted, ...) stay in the database and hosted/jobs.py: a customer never
receives them. `python3 -B tools/ci/envelope_places.py outcome <name>` (and `key <name>` for a top-level envelope key)
prints every place an outcome must change in the same patch (issue #1384)."""
from __future__ import annotations

import re
from types import MappingProxyType

# The one not_found reason: an unknown, another account's and a malformed check id read alike (serve/store.py,
# serve/profiles.py resolve_scope_ref).
NOT_FOUND_REASON = 'no check with that id exists for this account'

_TABLE = {
    'bad_input': (400, 2, 'Fix the request so every file is allow-listed for the profile and well formed, then send it again.'),
    'oversize_input': (413, 2, 'Send fewer or smaller files, within the published size and count limits.'),
    # issue #601: the refusal names the route and, through `detail.profiles` (serve/profiles.py served_ids), the ids
    'unknown_profile': (404, 2, 'Choose a profile id from GET /v1/profiles.'),
    # serve-016 (REFUTATION-028 F5; DD-073's table: bad input, auth, key read red, exit 2)
    'unauthenticated': (401, 2, 'Send a valid, unrevoked API key in the Authorization header.'),
    # issue #1262 (key expiry 1/5): a known key past its `expires` (serve/keys.py); the next step is the rotation
    'key_expired': (401, 2, 'Rotate the key: ask Symbolia to issue a new key for this account, then send the request '
                            'with it in the Authorization header.'),
    # issue #1264 (key expiry 3/5): a rotate before the key's window (serve/keys.py rotate_opens_at); the key still works
    'rotate_too_early': (409, None, 'Send the rotate request again at detail.opens_at, or when it is null do what the '
                                    'reason names; this key keeps working until Assure-Key-Expires.'),
    'rate_limited': (429, None, 'Wait for the time given in Retry-After, then send the request again.'),
    'credit_exhausted': (402, None, 'Your free credit is spent; contact Symbolia to continue.'),
    'engine_digest_mismatch': (503, 3, 'Report it to Symbolia (or reinstall the pinned release when you run the engine yourself), because the engine files differ from their pin and no check ran.'),
    'collector_cannot_connect': (None, 3, 'Check the connection settings and that the server accepts the collection role.'),
    'collector_refused': (422, 3, 'Fix what the reason names and run again; for a rule shape not yet checkable, rewrite it as the reason says or send Symbolia the file name and line number it gives.'),
    # issue #171: an agent whose only fitting profile is the unqualified one cannot 'use another profile'; the refusal
    # says the move is to wait and its `needs` (NOT_SERVABLE_NEEDS) names what is missing.
    'profile_not_servable': (503, 3, 'Wait for this profile to be qualified; nothing on your side opens it.'),
    'profile_refused': (422, 3, 'Fix the collection or declaration fault the reason names, then run again.'),
    'checker_error': (500, 3, 'Report the check id to Symbolia, because the checker failed in a way it should not.'),
    'checker_timeout': (504, 3, 'Send a smaller input or try again later, because the check ran past its time limit.'),
    # issue #1420: the refusal names the bound that bound, the check worker's RLIMIT_CPU or RLIMIT_AS (serve/worker.py)
    'checker_cpu_limit': (504, 3, 'Send a smaller input or try again later, because the check ran past its CPU time '
                                  'limit.'),
    'checker_memory_limit': (504, 3, 'Send a smaller input or try again later, because the check ran past its memory '
                                     'limit.'),
    'server_busy': (503, None, 'Try again in a minute, because the queue is full.'),
    'not_found': (404, None, 'Check the check id, because no check with that id exists for this account.'),
    # serve-062 parts 3-4: a record the server keeps for this account (an accepted scope) no longer reads as it was
    # written. A serving fault, never a verdict and never the customer's input; nothing ran and nothing was charged.
    'server_fault': (500, 3, 'Report the check id to Symbolia, because a record the server keeps for this account no longer reads as it was written; nothing ran and nothing was charged.'),
    'secret_in_input': (422, 2, 'Remove the secret the reason names from the input, then send it again; nothing was stored.'),
    'store_unavailable': (503, None, 'Try again in a minute, because the result store cannot be reached just now.'),
    # serve-014: the account's tier does not include the claim-tree report (refused before any model call).
    # issue #4578: the price and a self-serve link, not "Ask Symbolia to move this account" (`TIER_LINK_ACTIONS`)
    'tier_excludes': (403, None, 'Upgrade to Premium (USD 20 a month) at the link `POST /v1/billing/checkout` with '
                                 '{"tier": "usd_20"} returns, or ask Symbolia for the Premium payment link, or leave the '
                                 'report off.'),
    # serve-015: a metered line's allowance is spent and nothing pays for the request (refused before any model call,
    # free of charge, counted in the rate windows).
    'allowance_exhausted': (402, None, 'Send the request again with allow_overage true (the Action input allow-overage) '
                                       'to pay the overage, or ask Symbolia to top up this account; nothing ran and '
                                       'nothing was charged.'),
    # serve-015: the month's overage would pass the account's ceiling (refused even with allow_overage), or the
    # account has had its reports for the day (UTC). Both before any model call, free of charge.
    'overage_ceiling': (402, None, 'Wait for next month, or ask Symbolia to raise this account\'s overage ceiling; '
                                   'nothing ran and nothing was charged.'),
    'daily_report_cap': (402, None, 'Wait for the time given in Retry-After (midnight UTC), or ask Symbolia to raise '
                                    'this account\'s daily report cap; nothing ran and nothing was charged.'),
    # serve-030 (DD-079 Decision 10): the job's quote is above the account's job ceiling (USD 50 unless raised);
    # refused before any model call, free of charge, not counted on the daily cap.
    'job_ceiling': (402, None, 'Ask Symbolia to raise this account\'s job ceiling, or send a smaller request; nothing '
                               'ran and nothing was charged.'),
    # serve-079 (Director's decision 3902): paid formalisation is on Premium and above; a free account is refused before
    # anything is held, written or charged, and `detail` names the tier, its monthly price and what it adds.
    # issue #4578 / PR #4612 H1: checkout is the self-service route when no Premium payment link is set.
    'tier_required': (403, None, 'Upgrade to Premium (USD 20 a month) via `POST /v1/billing/checkout` with {"tier": '
                                 '"usd_20"}, or keep the free quote beside each requirement row; nothing was held and '
                                 'nothing was charged.'),
    # serve-084: Stripe billing is not configured on this server, or Stripe could not be reached; a typed refusal of
    # the billing routes, never a 500. Nothing was written and no tier changed.
    'billing_unavailable': (503, None, 'Ask Symbolia to move this account by hand, or try the checkout link again later, '
                                       'because billing is not available on this server just now; no tier changed.'),
    # The Action's own outcomes when it reaches the hosted API: never sent by the server, so they carry no HTTP status.
    'api_unreachable': (None, 3, 'Check that the runner can reach the API over HTTPS, then run the job again.'),
    'api_error': (None, 3, 'Run the job again later, and report the check id to Symbolia if it happens again.'),
}

# Issue #4578: a tier refusal whose `detail.upgrade.url` is the server's Premium payment link (serve/api.py
# `upgrade_for`, a buy.stripe.com link: `UPGRADE_URL`, render's `_UPGRADE_URL`) gives that link in its action.
UPGRADE_URL = re.compile(r'https://buy\.stripe\.com/[A-Za-z0-9_./-]+(\?[A-Za-z0-9_.~%=&-]*)?')
TIER_LINK_ACTIONS = {
    'tier_excludes': 'Upgrade this account to Premium for USD 20 a month at %s, or leave the report off.',
    'tier_required': 'Upgrade this account to Premium for USD 20 a month at %s, or keep the free quote beside each '
                     'requirement row; nothing was held and nothing was charged.',
}

OUTCOMES = MappingProxyType({name: MappingProxyType({'http': http, 'exit': code, 'action': action})
                             for name, (http, code, action) in _TABLE.items()})

# Issue #1103: the one table of the failures a paid check is charged for, read by the API's charge decision
# (serve/api.py), the lint's findings (serve/lint.py) and the envelopes' `charged` (serve/envelope.py): the outcomes
# only a checker gives once it has started. A refusal before the run is never charged; a verdict always is.
CHARGED_OUTCOMES = frozenset({'checker_error', 'checker_timeout', 'checker_cpu_limit', 'checker_memory_limit',
                              'profile_refused'})  # Main issue #1420: the worker's limit outcomes
VERDICT_OUTCOMES = frozenset({'verdict', 'no_verdict'})


def charged(outcome, detail=None, started=None):
    """Issue #1103: True when a check that ends in `outcome` is charged. A verdict is; a failure is when its outcome is
    in CHARGED_OUTCOMES (or, when the worker said whether the checker started, when it did), except one whose detail
    says `charge: false` (the assembler's own internal_error, the checker's fault), which is never charged."""
    if outcome in VERDICT_OUTCOMES:
        return True
    if isinstance(detail, dict) and detail.get('charge') is False:
        return False
    return (outcome in CHARGED_OUTCOMES) if started is None else bool(started)

# ---------- what was malformed (DIRECTOR-DECISIONS-SERVE-002 Addendum 1, decision 10) ----------
# A typed failure whose cause is in the customer's input carries `detail.malformation`: {kind, file, line, field,
# expected}. Every value is closed: `kind` and `expected` come from this table, `field` from FIELDS (or a derive kind
# from DERIVE_KINDS), `file` is a raw/ name that passes NAME_RE (the allow-list grammar of the profile rows), or, for
# `file_name` only (issue #940), a name of the same grammar outside raw/ (FILE_RE), so a bundle keyed from its root
# reads the name the caller sent; anything else reads `other`; `line` is a positive integer or None. No value is ever
# free text taken from the input's bytes.
MALFORMATIONS = MappingProxyType({
    # the request
    'body_encoding': 'a body sent with one Content-Length header and no Transfer-Encoding',
    'body_not_utf8': 'a body that is UTF-8 text',
    'body_not_json': 'a body that is one JSON document without duplicate keys or non-finite numbers',
    'body_shape': 'a JSON object with exactly the keys profile and files, profile a string and files an object',
    'file_value': 'each file as a strict base64 string',
    'oversize_input': 'each file within the published per-file size limit',
    'file_name': 'a relative name under raw/ that the profile accepts, without control characters, backslashes or '
                 'empty, "." or ".." segments',
    'file_missing': 'every file the profile requires',
    'file_conflict': 'one name per file, and no name that is both a file and a directory',
    'query': 'only the query parameters this route accepts, each at most once',
    'fail_on': 'a comma list of the words this profile accepts, or never alone',
    'allow_partial': 'true or false (the API query: 1 or 0)',
    'idempotency_key': 'one Idempotency-Key of 16 to 64 characters of A-Z, a-z, 0-9, _ and -',
    'report_body': 'no body, or a JSON object whose only key is allow_overage, true or false (serve-015)',
    # serve-030 (REFUTATION-042 F3): the key tool's grant of the free report balance
    'email_address': 'one email address, local@domain, with one @, a local part and a domain of dot-separated labels',
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
    # issue #1504: raw/declaration.json names a stack REGISTRY.json registers but this build has no runner leg for; the
    # expected names the stack and the missing leg (stack_expected), both the registry row's own strings
    'stack_not_wired': 'a stack with a runner leg on this build; the declared stack is registered but not wired',
    # issue #1959: the python-auth reader's own schema fault of raw/declaration.json (the check's detail.kind), at
    # the malformation's pointer
    'declaration_invalid': 'a raw/declaration.json that meets its schema at the pointer named (QUICKSTART-API.md '
                           'section 15 gives the shape)',
    # the selected scope a profile row reads from the request (docs/PROFILES.md), bound before the checker runs
    'scope_missing': 'the selected scope this profile checks, as a list of 1 to 256 distinct ids of A-Z, a-z, 0-9, '
                     '_, . and -; a profile whose scope is fixed takes none',
    # serve-006 gap 1: the selected scope's binding, and a reference to an accepted scope (no store resolves one yet)
    'scope_binding': 'for a profile that declares a scope binding, an object with one key, the map the profile names, '
                     'that maps every selected id to its own token of 1 to 63 characters of A-Z, a-z, 0-9, _, . and '
                     '-; a profile that declares none takes none',
    'scope_ref': 'no accepted_scope_ref: no accepted scope record can be resolved yet, so a first-run comparison '
                 'omits it; a profile whose scope is fixed takes none; a profile that declares '
                 'scope.context.accepts_prior reads one of its own earlier checks of this account, by its check_id',
    # serve-019 (coordination 2136): the requirements upload fields
    'requirements': 'requirements as UTF-8 text of at most 65536 bytes, 256 lines and 8192 bytes per line',
    'quote_body': 'a JSON object with exactly the keys profile and sentence: one sentence of 1 to 8192 bytes of UTF-8 '
                  'text without control characters',
    'provenance': 'repository (owner/name) and commit (40 lower-case hex) together, or neither; provenance caller '
                  'or runner, only with them',
    # DD-105 Addendum 2: the agent feedback note
    'feedback_body': 'a JSON object with kind (friction, wrong_reading, coverage_gap or model_proposal_intent) and text '
                     '(1 to 4096 bytes of UTF-8 without control characters but LF and TAB), and optionally check_id, '
                     'profile, profile_wanted, obligation, package {name, version}, agent {model_id, client} and '
                     'consent_follow_up',
    # serve-085: the operator's state of a note, POST /v1/feedback/{id}/status (internal accounts)
    # issue #4230: the coverage proposal (serve/coverage_proposals.py; QUICKSTART-API.md "Propose coverage")
    'coverage_proposal_body': 'a JSON object with answers {profile, kind, shape, and optionally check_id, requirement, '
                              'at}, fixture {files}, acceptance {before, after, text}, planted_defect {text, files, '
                              'expected: disproven}, change {kind: patch or description, text, patch} and optionally '
                              'agent {model_id, client}; files are relative paths the reader reads, each at most '
                              '16384 bytes of text',
    'feedback_status': 'a JSON object with state (received, in_pr, merged or declined) and the field the state takes: '
                       'pr (1 to 1000000) for in_pr, release (40-hex engine commit) and optionally pr for merged, '
                       'reason (1 to 300 bytes) for declined',
})
# A field path the malformation may name: request fields, JSON fields the checks read, and derive locators.
FIELDS = frozenset({'profile', 'files', 'Content-Length', 'Transfer-Encoding', 'Idempotency-Key', 'fail_on',
                    'allow_partial', 'redaction_withheld', 'sanitised_sha256', 'entries', 'major', 'server.major',
                    'server.server_version_num', 'policies', 'declared_predicate', 'collection.role', 'role',
                    'scope_binding', 'accepted_scope_ref', 'allow_overage', 'requirements', 'repository', 'commit',
                    'provenance', 'sentence', 'kind', 'text', 'check_id', 'obligation', 'package', 'agent',
                    'consent_follow_up', 'profile_wanted', 'stack', 'compile_requirements',
                    'requirement_goals', 'answers', 'fixture', 'acceptance', 'planted_defect', 'change'})
# The observed derive's typed kinds (INTERFACE-CONTRACT-OB-001 section 4.6, STABLE).
DERIVE_KINDS = frozenset({'derived', 'schema_gate_every_machine', 'major_not_observed', 'major_disagreement',
                          'major_out_of_range', 'collection_role_disagreement', 'collection_role_not_observed',
                          'raw_missing', 'raw_unreadable', 'inputs_unreadable', 'derive_digest', 'internal'})
# issue #171: what a `profile_not_servable` refusal waits for, the same `needs` shape the not-established rows use
# (serve.render.CLASS_NEEDS): the checker binding, or the report writer's qualification for the profile.
NOT_SERVABLE_NEEDS = frozenset({'checker_binding', 'writer_qualification'})
_SEGMENTS = r'(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}/){0,10}[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}'
NAME_RE = re.compile(r'raw/' + _SEGMENTS)
# issue #900: a warning locator's `path` is a repository path with NAME_RE's segments and no raw/ prefix: relative, up
# to 11 segments, none empty, each starting with a letter, digit or underscore (so no `.`, `..` or leading dash).
REPO_PATH_RE = re.compile(_SEGMENTS)
# issue #940: what a `file_name` malformation's `file` may name besides a raw/ name: a name of the same grammar outside
# raw/ (the bundle root zipped instead of raw/, the mistake the reason then tells the caller to fix). Same alphabet,
# bounds and no `.`/`..` segment as NAME_RE; other kinds and the profiles' own locator checks keep NAME_RE.
# REQUIREMENTS_LABEL stays `other` (REFUTATION-r1 F1): it is the lint's fixed label for the body's `requirements` text
# (serve.lint.REQUIREMENTS_FILE, issue #170), never the name of a file sent.
FILE_RE = re.compile(r'(?:raw/)?' + _SEGMENTS)
REQUIREMENTS_LABEL = 'requirements.md'


def _closed_file(kind, file):
    """Whether `file` may stand as a `kind` malformation's `file`."""
    if not isinstance(file, str):
        return False
    if kind == 'file_name' and file != REQUIREMENTS_LABEL:
        return FILE_RE.fullmatch(file) is not None
    return NAME_RE.fullmatch(file) is not None


# issue #497: a derive_refused malformation's `expected` is the derive kind's own next step where one is written here;
# a kind without a row keeps the generic derive_refused text. Closed: the text is chosen by the closed `field`, or
# (issue #1032) for a field without a row of its own by the record's closed `cause_code`, and by nothing else.
DERIVE_EXPECTED = MappingProxyType({
    'raw_unreadable': 'a JSON object; re-copy the file from the collector\'s out/raw/ or collect again',
    'major_disagreement': 'one major across COLLECTION-SIDECAR.json server_version_num, command_line.json argv[0] and '
                          'the catalog roles; send the files of one collection run',
    'major_not_observed': 'server_version_num in COLLECTION-SIDECAR.json; send the sidecar from the same run',
    # issue #1032: the HTTP derive's one customer kind is input_fault; its closed cause code chooses the next step
    'ARTEFACT-DIGEST-MISMATCH': 'the file as collected: re-run the producer and collector with a new key and send the '
                                'bundle as collected, without editing any file',
    'UNEXPECTED-ARTEFACT': 'exactly the files raw/COLLECTION-SIDECAR.json lists under sanitized_sha256, plus the '
                           'sidecar: send every raw/response-heads/<id>.txt the sidecar lists and no other file but an '
                           'optional raw/HTTP-INTENT.json',
    'JSON-INVALID': 'a JSON object; re-copy raw/HTTP-FACTS.json and raw/COLLECTION-SIDECAR.json from the collector\'s '
                    'bundle',
    'FLAGS-INVALID': 'the seven standing flags as the collector wrote them; re-copy raw/HTTP-FACTS.json and '
                     'raw/COLLECTION-SIDECAR.json from the collector\'s bundle',
})
MALFORMATION_KEYS = ('kind', 'file', 'line', 'field', 'expected')
# issue #644: the optional closed key `pointer`, the RFC 6901 JSON pointer of the key the validator stopped on (such as
# /files/raw~1submission.json or /scope_binding/endpoint_tokens/endpoint-003), present only where it holds the path.
# Every segment is a key of the closed alphabet A-Z, a-z, 0-9, _, ., - and / ('/' escaped as ~1); `json_pointer` stops
# at the first key outside it, so the pointer then names the nearest closed parent and never other text of the input.
POINTER_KEY = 'pointer'
_POINTER_KEY_RE = re.compile(r'[A-Za-z0-9_./-]{1,255}')
POINTER_RE = re.compile(r'(?:/(?:[A-Za-z0-9_.-]|~1){1,510}){1,8}')


def json_pointer(*keys):
    """The closed RFC 6901 pointer of `keys` from the document root (module comment above), or None when the first key
    is outside the closed alphabet."""
    segments = []
    for key in keys[:8]:
        if not (isinstance(key, str) and _POINTER_KEY_RE.fullmatch(key)):
            break
        segments.append(key.replace('~', '~0').replace('/', '~1'))
    return ''.join('/' + s for s in segments) or None


def file_pointer(name, kind='file_name'):
    """/files/<name> when `name` may stand as a `kind` malformation's `file`, else /files: a pointer never quotes a
    sent name that the malformation itself would not (issue #644; such as raw/../x or a control character, and for
    file_value and oversize_input a name outside raw/, REFUTATION-r4 F1)."""
    return json_pointer('files', name) if _closed_file(kind, name) else json_pointer('files')


def malformation(kind, file=None, line=None, field=None, kinds=(), expected=None, code=None, pointer=None):
    """The closed description of what was malformed (module comment above). An unknown kind is a ValueError: the
    vocabulary is closed in code, never at run time. `kinds` adds a profile row's own closed derive kinds (its
    `derive_result.kinds`, checked against KIND_RE when the row is loaded) to the fields a malformation may name.
    `expected` (issue #414) replaces the kind's generic text with one built from a profile row by `scope_expected`;
    any other text falls back to the generic one. `code` (issue #1032) is a derive's closed cause code: when the field
    has no DERIVE_EXPECTED row of its own and the code has one, the code's row is the next step. `pointer` (issue #644)
    is added as the key `pointer` when it is a closed JSON pointer (`json_pointer`), and left out otherwise."""
    if kind not in MALFORMATIONS:
        raise ValueError('unknown malformation kind: %r' % (kind,))
    if file is not None:
        file = file if _closed_file(kind, file) else 'other'
    if not (type(line) is int and line > 0):
        line = None
    if field is not None and field not in FIELDS and field not in DERIVE_KINDS and field not in _row_kinds(kinds):
        field = None
    if kind == 'derive_refused' and field in DERIVE_EXPECTED:
        expected = DERIVE_EXPECTED[field]
    elif kind == 'derive_refused' and isinstance(code, str) and code in _CODE_EXPECTED:
        expected = _CODE_EXPECTED[code]
    elif not _row_expected(kind, expected):
        expected = MALFORMATIONS[kind]
    out = {'kind': kind, 'file': file, 'line': line, 'field': field, 'expected': expected}
    if isinstance(pointer, str) and POINTER_RE.fullmatch(pointer):
        out[POINTER_KEY] = pointer
    return out


# issue #414: a scope refusal's `expected` built from the profile row the reason was raised against, so an agent that
# follows the action ("the shape detail.malformation.expected gives") builds a body the row accepts. The text is closed
# by template: each hole takes only a value the row loader already checked (serve/profiles.py: a label of
# SCOPE_WORD_RE, an input field of INPUT_FIELD_RE, max_ids 1..256, a grammar of up to MAX_GRAMMAR_CHARS printable
# characters, a map and record names of SCOPE_NAME_RE, a record schema of RECORD_SCHEMA_RE, max_bytes 1..16384).
GENERIC_ID_FORM = 'of A-Z, a-z, 0-9, _, . and -'
GENERIC_TOKEN_FORM = 'of 1 to 63 characters of A-Z, a-z, 0-9, _, . and -'
_GRAMMAR = r'[\x20-\x7e\x80-\U0010ffff]{1,128}'
_NAME = r'[a-z][a-z0-9_]{0,31}'
_PROFILE = r'[a-z0-9][a-z0-9-]{0,63}'
SCOPE_EXPECTED_RE = {
    'scope_missing': re.compile(
        r'the selected [a-z][a-z ]{0,31} profile %s checks, in %s: a list of 1 to (?:[1-9][0-9]{0,2}) distinct ids '
        r'(?:of the form %s|%s)' % (_PROFILE, _NAME, _GRAMMAR, re.escape(GENERIC_ID_FORM))),
    'scope_binding': re.compile(
        r'for profile %s, scope_binding as an object with exactly the key(?:s)? %s(?:, %s)*: %s maps every selected '
        r'id to its own token (?:matching %s|%s), the tokens distinct(?:; %s is an object whose schema is '
        r'[a-z0-9][a-z0-9._/-]{0,127}, of at most (?:[1-9][0-9]{0,4}) bytes)*'
        % (_PROFILE, _NAME, _NAME, _NAME, _GRAMMAR, re.escape(GENERIC_TOKEN_FORM), _NAME)),
}


# issue #1504: a stack_not_wired refusal's `expected`, built from the REGISTRY.json row of the declared stack: its
# `stack` (language/framework) and its `package` (the adapter's directory, the leg this build does not run).
_STACK = r'[a-z][a-z0-9+-]{0,31}/[a-z][a-z0-9.+-]{0,63}'
SCOPE_EXPECTED_RE['stack_not_wired'] = re.compile(
    r'a stack with a runner leg on this build; (%s) is registered but not wired \(missing: assure/checkers/%s\)'
    % (_STACK, _SEGMENTS))


def stack_expected(stack, leg):
    """The `expected` text of a `stack_not_wired` malformation for a registered `stack` whose adapter package `leg` has
    no runner leg on this build (issue #1504); None outside the closed template, so the generic text then stands."""
    text = 'a stack with a runner leg on this build; %s is registered but not wired (missing: %s)' % (stack, leg)
    return text if _row_expected('stack_not_wired', text) else None


def _row_expected(kind, expected):
    pattern = SCOPE_EXPECTED_RE.get(kind)
    return pattern is not None and isinstance(expected, str) and pattern.fullmatch(expected) is not None


def scope_expected(kind, profile_id, *, label=None, field=None, max_ids=256, id_pattern=None, map=None,
                   records=None, token_pattern=None):
    """The `expected` text of a `scope_missing` or `scope_binding` malformation built from a row that reads its scope
    from the request (issue #414): the row's input field, label and id count and form; its binding map, every record
    the row declares (name, schema, max_bytes) and its token form. None for a fixed-scope row, a row without a binding
    or a value outside the closed template: the generic text then stands."""
    if kind == 'scope_missing':
        if label is None or field is None:
            return None
        text = 'the selected %s profile %s checks, in %s: a list of 1 to %d distinct ids %s' % (
            label, profile_id, field, max_ids,
            'of the form %s' % id_pattern if id_pattern is not None else GENERIC_ID_FORM)
    elif kind == 'scope_binding':
        if map is None:
            return None
        records = records or {}
        keys = [map] + sorted(records)
        text = 'for profile %s, scope_binding as an object with exactly the key%s %s: %s maps every selected id to ' \
               'its own token %s, the tokens distinct' % (
                   profile_id, 's' if len(keys) > 1 else '', ', '.join(keys), map,
                   'matching %s' % token_pattern if token_pattern is not None else GENERIC_TOKEN_FORM)
        for name in sorted(records):
            text += '; %s is an object whose schema is %s, of at most %d bytes' % (
                name, records[name].get('schema'), records[name].get('max_bytes', 0))
    else:
        return None
    return text if _row_expected(kind, text) else None


# A derive kind a profile row may declare (serve/profiles.py checks every row kind against it when loading the row).
KIND_RE = re.compile(r'[a-z][a-z0-9_]{0,63}')
# issue #1032: the DERIVE_EXPECTED rows keyed on a derive's closed cause code rather than on a kind: the next steps a
# derive_refused whose field has no row of its own may carry
_CODE_EXPECTED = MappingProxyType({k: v for k, v in DERIVE_EXPECTED.items() if not KIND_RE.fullmatch(k)})


def _row_kinds(kinds):
    return frozenset(k for k in kinds if isinstance(k, str) and KIND_RE.fullmatch(k))


def closure_failure(value, kinds=()):
    """None when `value` is a malformation built by `malformation` (every value from the closed vocabulary), else the
    name of the first clause that rejected it: `keys` (not a dict with exactly MALFORMATION_KEYS, plus at most the
    optional POINTER_KEY), `pointer` (issue #644: not a POINTER_RE pointer), `kind`, `expected`, `file`, `line` or
    `field`; `kinds` as for `malformation`. `is_closed` is this test as a bool; a test that reads the clause tells a
    wrong `field` from a wrong `expected`, which the bool could not (issue #1120)."""
    if not isinstance(value, dict) or tuple(sorted(set(value) - {POINTER_KEY})) != tuple(sorted(MALFORMATION_KEYS)):
        return 'keys'
    if POINTER_KEY in value and not (isinstance(value[POINTER_KEY], str) and POINTER_RE.fullmatch(value[POINTER_KEY])):
        return 'pointer'
    kind = value['kind']
    if kind not in MALFORMATIONS:
        return 'kind'
    if kind == 'derive_refused':
        field = value['field'] if isinstance(value['field'], str) else None
        generic = (value['expected'] == DERIVE_EXPECTED.get(field, MALFORMATIONS[kind])
                   or (field not in DERIVE_EXPECTED and value['expected'] in _CODE_EXPECTED.values()))
    else:
        generic = value['expected'] == MALFORMATIONS[kind]
    if not (generic or _row_expected(kind, value['expected'])):
        return 'expected'
    if not (value['file'] is None or value['file'] == 'other' or _closed_file(kind, value['file'])):
        return 'file'
    if not (value['line'] is None or (type(value['line']) is int and value['line'] > 0)):
        return 'line'
    if not (value['field'] is None or value['field'] in FIELDS or value['field'] in DERIVE_KINDS
            or value['field'] in _row_kinds(kinds)):
        return 'field'
    return None


def is_closed(value, kinds=()):
    """True when `value` is a malformation built by `malformation` (every value from the closed vocabulary); `kinds`
    as for `malformation`. `closure_failure` names the clause when it is not."""
    return closure_failure(value, kinds) is None


# An action that differs for one closed rule of an outcome, so the action agrees with the reason (REFUTATION-034-R2 N6;
# serve-030, REFUTATION-042 F2: the once-only free report balance, which neither allow_overage nor a top-up admits)
RULE_ACTIONS = {# issue #1263: a refused GitHub OIDC sign-in proof (`detail.identity` names the step that refused it)
                ('unauthenticated', 'oidc'):
                'Request a fresh GitHub Actions OIDC token with audience "assure" (the job needs the line '
                '`id-token: write` under `permissions:`) and sign in again, or send an API key in the Authorization '
                'header.',
                ('profile_not_servable', 'checker_metadata'):
                'Nothing to change on your side; try again after Symbolia repairs the profile, or use another profile '
                'meanwhile.',
                # issue #943: the derive could not read the raw/ file the reason names as a UTF-8 JSON object, and
                # the reason says which fault and where (serve/profiles.py _json_fault, _located)
                ('profile_refused', 'raw_unreadable'):
                'Re-run the collector or fix the file the reason names so it parses as a JSON object (or leave it out '
                'where the reason says it is optional), then send it again.',
                # issue #431: the served checker's pipeline cannot import a module the server tree lacks (a release
                # built without a shared core): the profile is qualified and the server is broken, so the action
                # names neither a qualification wait nor a check id to report
                ('profile_not_servable', 'pipeline_import'):
                'Nothing to change on your side; the server tree lacks a module this checker imports, which only a '
                'redeploy by Symbolia opens. Nothing ran and nothing was charged.',
                ('allowance_exhausted', 'once_balance'):
                'A paid plan gives more reports; the free report balance does not renew; nothing ran and nothing was '
                'charged.',
                # serve-032 (DD-083): the once-only balance is below zero; a recharge first clears what is owed
                ('allowance_exhausted', 'once_balance_debt'):
                'Recharge the free report balance, and the recharge first clears what is owed, or move to a paid plan; '
                'nothing ran and nothing was charged.',
                # serve-079 (3899 MEDIUM-1): while no paid formalisation runner is bound, no step of the customer's
                # (another profile, a retry, allow_overage, a top-up) would succeed, so the action names none
                # serve-089 (#266): a declaration whose stack this profile does not read names the served stacks
                ('profile_refused', 'stack'):
                'Declare a stack this profile serves: python/flask, python/fastapi, python/django or python/stdlib-http '
                '(the `stacks` list of the profile row in GET /v1/profiles); nothing ran and nothing was charged.',
                ('profile_not_servable', 'runner_unbound'):
                'Nothing to change on your side; the paid formalisation runner is not bound on this server yet, and '
                'the free quote beside each requirement row stands until Symbolia binds it.',
                # issue #3084: the bound runner serves Premium on python-auth-declared-model; another paid plan or
                # profile is refused before any hold, and no step of the customer's opens it today. Issue #3872: Pro
                # runs the Premium build; Enterprise, zero retention, is the plan refused here
                ('profile_not_servable', 'tier_not_bound'):
                'Nothing to change on your side; paid formalisation runs on Premium and Pro today, nothing was held '
                'or charged, and the free quote beside each requirement row stands.',
                ('profile_not_servable', 'profile_not_bound'):
                'Nothing to change on your side; paid formalisation runs on the python-auth-declared-model profile '
                'today, nothing was held or charged, and the free quote beside each requirement row stands.',
                # issues #595 and #697: GET /v1/checks/{id}/report before any POST, on a check the account holds: the
                # check exists, so "check the check id" contradicts the reason; the next step is the POST the reason
                # names, and the action says the check exists so the agent does not re-check a fine id
                ('not_found', 'report_not_requested'):
                'POST /v1/checks/{id}/report to ask for the report, then read it here; the check exists.',
                # issue #2896 (REFUTATION-r1 F1): a product read of a private model the account's data rule does not
                # allow (hosted/adapters_local.py LocalModelStore); no qualification opens it, so the action names
                # no wait
                ('profile_not_servable', 'product_data_off'):
                'Nothing to change in this request; the account\'s data rule does not allow its model to be used to '
                'improve the product, and no wait or retry opens it. Read the model with purpose \'serve\' to serve '
                'the account.',
                ('bad_input', 'bad_purpose'):
                "Send purpose 'serve' or 'product', then send the request again.",
                # issue #841: the key is bound to the raw body bytes and the query (serve/api.py _known), so a body
                # re-serialised with other whitespace is "a different request" though every file is allow-listed and
                # well formed; the file action sent an agent to re-validate file names
                ('bad_input', 'idempotency_body_mismatch'):
                'This Idempotency-Key is bound to the exact bytes of an earlier request body and its query (whitespace '
                'counts). Resend those exact bytes to read the stored verdict, or send a new Idempotency-Key for a new '
                'check.'}


# serve-072 (3797, dogfood fb-20261009-ac2d8e303fa3089d): a bad_input whose malformation is a request field or body,
# not a file of the upload, says how to fix that field; the file action ("every file is allow-listed") misled an agent.
REQUEST_KINDS = frozenset({'allow_partial', 'body_encoding', 'body_not_json', 'body_not_utf8', 'body_shape',
                           'coverage_proposal_body', 'email_address', 'fail_on', 'feedback_body', 'feedback_status', 'idempotency_key', 'query', 'quote_body',
                           'report_body', 'requirements', 'scope_binding', 'scope_missing', 'scope_ref'})
# issue #589: the next step per closed cause code of the HTTP observed derive's customer refusal (profile_refused with
# detail.cause_code). `{file}` takes the malformation's file (a raw/ name that passed NAME_RE) or 'the bundle' when
# the fault is located in no one file (RAW-INVALID, a SCHEMA-INVALID raised past the readers, or the scope a standalone
# caller sent; the API validates the sent scope before the derive runs, so the scope codes it serves are the sidecar's).
# Refutation of PR #949, F2/F3: every code `binding` in checker.py can raise against the uploaded files has a row
# (tests/serving/test_issue_589_accept.py reads the set from the checker), in the groups QUICKSTART-API.md tables.
_CODE_GROUPS = (
    (('JSON-INVALID', 'JSON-NONFINITE', 'DUPLICATE-KEY'),
     '{file} is not JSON the checker reads (UTF-8, unique keys, finite numbers); re-run collect_http.py rather than '
     'editing it, then run again.'),
    (('FLAGS-INVALID',),
     '{file} must be a JSON object carrying the seven flags at their fixed values, as collect_http.py writes it; '
     're-run the collector rather than editing it, then run again.'),
    (('EXPECTED-IDENTITY-BINDING-MISMATCH',),
     'the scope_binding you sent was produced for a different manifest than the one collected into {file}; run the '
     'identity producer and the collector again with one key, then send both from that run.'),
    (('IDENTITY-BINDING-INVALID',),
     'the identity_binding record of the selected scope in {file} has the wrong shape (schema, algorithm, key id or '
     'one digest per token); re-run the collector and send the identity producer\'s record unchanged with the facts '
     'and sidecar of that run.'),
    (('EXPECTED-SCOPE-REQUIRED', 'SCOPE-INVALID', 'SCOPE-TOKEN-DUPLICATE'),
     'the selected scope recorded in {file} is missing or malformed (one to sixteen endpoint ids, each with its own '
     'token); re-run the shipped collector rather than editing it, and send its facts and sidecar together.'),
    (('SCOPE-SELECTION-MISMATCH', 'EXPECTED-SCOPE-DIGEST-MISMATCH'),
     'the scope you sent is not the endpoint set collected into {file}; send the tokens of the collection run, or '
     'collect again for the scope you want.'),
    (('REQUEST-SCOPE-MISMATCH', 'SCOPE-DIGEST-KEYS', 'SCOPE-DIGEST-MISMATCH', 'SCOPE-IDENTITY-DIGEST-MISMATCH',
      'FACTS-SCOPE-MISMATCH'),
     'the collected scope\'s own fields in {file} disagree with each other or between the facts and the sidecar; '
     're-run the shipped collector and send the facts and sidecar of one run.'),
    (('ENDPOINT-COVERAGE-MISMATCH', 'ENDPOINT-TOKEN-MISMATCH'),
     'the endpoints in {file} are not exactly the selected tokens, one each, with the binding\'s tokens; collect '
     'again for the scope you send.'),
    (('SCHEMA-INVALID', 'REQUEST-QUALIFIER-MISMATCH', 'TRANSPORT-MODE-INVALID', 'TRANSPORT-BUDGET-INVALID',
      'TRANSPORT-STATUS-INVALID', 'FIELD-DUPLICATE', 'UNKNOWN-HAS-VALUE', 'FACT-NESTING-BOUND', 'FACT-KEY-UNSUPPORTED',
      'FACT-LIST-BOUND', 'FACT-NUMBER-INVALID', 'FACT-CODE-UNSUPPORTED', 'FACT-LOCATOR-INVALID', 'FACT-ID-INVALID',
      'FACT-DIGEST-INVALID', 'FACT-CIPHER-INVALID', 'FACT-LIBRARY-INVALID', 'FACT-TIME-INVALID', 'FACT-MODE-INVALID',
      'FACT-IDENTITY-INVALID', 'FACT-ENUM-UNSUPPORTED', 'FACT-TYPE-INVALID', 'CSP-PRESENCE-INVALID',
      'SAMPLING-LIMIT-INVALID', 'TRUST-POLICY-INVALID', 'TLS-VERIFICATION-CONTEXT-INVALID',
      'TRUST-ANCHOR-RETENTION-INVALID', 'REFERRER-POLICY-ENUM-INVALID', 'CONTENT-LENGTH-RELATION-INVALID',
      'CONTENT-LENGTH-PREMISE-MISSING', 'TRANSFER-ENCODING-PREMISE-MISSING', 'HSTS-PREMISE-MISSING',
      'COOKIE-CAPTURE-PREMISE-MISSING', 'COOKIE-SYNTAX-PREMISE-MISSING', 'COOKIE-VIOLATION-PREMISE-MISSING',
      'COOKIE-SYNTAX-INVALID', 'COOKIE-SYNTAX-DISAGREEMENT', 'FRAMING-PRESENCE-PREMISE-MISSING',
      'ACTUAL-OFFER-STATUS-INVALID'),
     'a record in {file} is not in the shape the shipped collector writes (its schema, mode, endpoint and fact fields '
     'are closed); re-run collect_http.py rather than editing it, then run again.'),
    (('FACTS-DIGEST-MISMATCH', 'ARTEFACT-DIGEST-MISMATCH', 'ARTEFACT-DIGESTS-MISSING', 'ARTEFACT-PATH-INVALID',
      'UNEXPECTED-ARTEFACT'),
     '{file} differs from the digest the sidecar recorded, or the sidecar\'s digest map and the files under raw/ do '
     'not list each other; send exactly the files the collector wrote, unedited, or collect again.'),
    (('ARTEFACT-SYMLINK', 'RAW-INVALID', 'SOURCE-NOFOLLOW-READ-FAULT', 'SOURCE-NONREGULAR-OR-OVER-BOUND',
      'SOURCE-OVER-BOUND'),
     '{file} is a symbolic link, not a regular file or directory, or over its size bound; send regular files within '
     'the bound.'),
    (('SANITIZED-CONTROL', 'SANITIZED-TEXT-INVALID', 'MARKER-INVALID'),
     '{file} is not the sanitized ASCII head text the collector writes (its withheld-line markers included); re-run '
     'the collector rather than editing a head.'),
    (('MARKER-ROWS-INVALID', 'MARKER-ROW-INVALID', 'MARKER-ROW-DUPLICATE', 'MARKER-UNIT-INVALID',
      'MARKER-IDENTITY-INVALID', 'STATUS-MARKER-INVALID', 'MARKER-FACT-IDENTITY', 'MARKER-FACT-LOCATOR',
      'MARKER-BIJECTION'),
     'the redaction markers and fact locators recorded in {file} do not match the facts, the sidecar and the heads '
     'one for one; re-run the collector and send its facts, sidecar and heads together.'),
    # issue #2381: the customer writes raw/HTTP-INTENT.json, not the collector
    (('INTENT-SCHEMA',),
     '{file} is not the declared HTTP intent: the seven standing flags and one or more of redirects {allow: '
     'same_origin, same_site or any; forbid_secure_to_insecure: true or false}, response_headers {require: '
     '[header names]} and cookies {require: {httponly, secure, samesite}}; fix it or leave it out.'),
)
CODE_ACTIONS = {code: text for codes, text in _CODE_GROUPS for code in codes}
REQUEST_ACTION = ('Fix what the reason names so it has the shape detail.malformation.expected gives, then send the '
                  'request again.')
KIND_ACTIONS = {'feedback_body': 'Fix the field the reason names so it has the shape detail.malformation.expected '
                                 'gives, then send the note again; nothing was stored.',
                'coverage_proposal_body': 'Fix the field the reason names so it has the shape detail.shapes gives '
                                          '(detail.example is one valid body), then send the proposal again; nothing '
                                          'was stored.'}


# issue #1045: what to correct for a free run's profile_refused, per (detail.kind, detail.rule) (QUICKSTART-API.md
# section 15: "its `action` says what to correct"). Keyed on detail, not attached to the Refusal, because the API
# rebuilds a child's refusal from its failure envelope's (outcome, reason, detail) (serve/worker.py `_refusal_from`;
# refutation of PR #1087, F1). `%(path)s` is the checker's repository-relative path; `%(pointer)s` a JSON pointer into
# the file the reason names. A manifest fault at one of the seven flags is answered with the flags themselves.
MANIFEST_RECIPE = 'rebuild raw/REPOSITORY.json with the recipe in QUICKSTART-API.md section 15'
REGENERATE_ACTION = 'Regenerate raw/REPOSITORY.json from the files you send (%s), then send again.' % MANIFEST_RECIPE
FREE_ACTIONS = {
    ('input_pin_differs', 'file_sha256'): REGENERATE_ACTION,
    ('input_pin_differs', 'file_bytes'): REGENERATE_ACTION,
    ('input_pin_differs', 'tree'): REGENERATE_ACTION,
    ('input_pin_differs', 'file_absent'): 'Send raw/repository/%(path)s or remove its row from raw/REPOSITORY.json, '
                                          'then send again.',
    ('input_pin_differs', 'file_unlisted'): 'Add a row for raw/repository/%(path)s to raw/REPOSITORY.json (' +
                                            MANIFEST_RECIPE + ') or do not send the file, then send again.',
    ('representation', 'bundle'): 'Rewrite %(path)s as the reason says (' + MANIFEST_RECIPE + '), then send again.',
    ('representation', 'manifest'): 'Fix raw/REPOSITORY.json at %(pointer)s as the reason says (' + MANIFEST_RECIPE +
                                    '), then send again.',
    ('representation', 'path'): 'Rename raw/repository/%(path)s to a relative path with no `..`, leading `/` or NUL '
                                'and regenerate raw/REPOSITORY.json (' + MANIFEST_RECIPE + '), then send again.',
    ('representation', 'unsupported_entry'): 'Remove raw/repository/%(path)s from what you send (the checker reads '
                                             'regular files only), ' + MANIFEST_RECIPE + ', then send again.',
    ('representation', 'size'): 'Shrink or leave out raw/repository/%(path)s so the .py files fit the bound the reason '
                                'gives, regenerate raw/REPOSITORY.json (' + MANIFEST_RECIPE + '), then send again.',
    ('representation', 'parse'): 'Fix raw/repository/%(path)s so it is UTF-8 Python that parses (the reason gives the '
                                 'position), regenerate raw/REPOSITORY.json (' + MANIFEST_RECIPE + '), then send again.',
    ('declaration_invalid', None): 'Fix raw/declaration.json at %(pointer)s so it meets its schema there (the reason '
                                   'gives the keyword; QUICKSTART-API.md section 15 gives the shape), then send again.',
    ('declaration_invalid', 'parse'): 'Rewrite raw/declaration.json as UTF-8 JSON (the reason gives the position), '
                                      'then send again.',
    ('stack_not_wired', None): 'Send this declaration once its stack has a runner leg on this build (the reason names '
                               'the missing leg), or send a repository of a stack python-auth-declared-model serves: '
                               'python/flask, python/fastapi, python/django or python/stdlib-http (the `stacks` list '
                               'of its row in GET /v1/profiles); nothing was charged.',
}
FLAGS_ACTION = ('Add the seven flags at their standing values to raw/REPOSITORY.json (execution_authorized, '
                'hardware_authorized, industrial_release_authorized, release_allowed and physical_validation false; '
                'simulation true; self_approved false), then send again.')
FLAG_POINTERS = frozenset('/' + k for k in ('execution_authorized', 'hardware_authorized',
                                            'industrial_release_authorized', 'release_allowed',
                                            'physical_validation', 'simulation', 'self_approved'))


# Beta feedback #4597, #4591: a python/stdlib-http app of a shape the native reader does not read (serve/profiles.py
# STDLIB_NATIVE_SHAPE_RULES) is pointed at the adapter bridge (assure/adapter_bridge.py, assure.adapter-bridge/v1),
# and a bridge refused by its own verification (rule `bridge:<rule>`) at the local self-check. `detail.adapter_bridge`
# is the contract's link (adapter_bridge.DOC), a plain string so the Action's client keeps it and rebuilds this action.
BRIDGE_DOC_RE = re.compile(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/blob/[A-Za-z0-9_./-]+\.md')
BRIDGE_TEMPLATE = 'python3.14 -B -m action.adapter_bridge template'
BRIDGE_CHECK = 'python3.14 -B -m action.adapter_bridge check'
BRIDGE_BUILD_ACTION = ("Assure's native stdlib reader reads one shape: one literal route table and one dispatcher. For "
                       "any other shape, build an adapter bridge: run " + BRIDGE_TEMPLATE + ", complete it, run "
                       + BRIDGE_CHECK + " until it passes, then commit .assure/declaration.json. Contract: %s")
BRIDGE_FAULT_ACTION = ("Your adapter bridge disagrees with your code: run " + BRIDGE_CHECK + ", which prints every fault "
                       "with its path:line, correct each, then commit .assure/declaration.json and run again. "
                       "Contract: %s")


def bridge_action(detail):
    """The adapter bridge's action for a profile_refused `detail` carrying `adapter_bridge` (the contract link), or
    None: the self-check for a bridge's own fault (rule `bridge:<rule>`), else how to build one."""
    doc = detail.get('adapter_bridge')
    if not (isinstance(doc, str) and BRIDGE_DOC_RE.fullmatch(doc)):
        return None
    rule = detail.get('rule')
    return (BRIDGE_FAULT_ACTION if isinstance(rule, str) and rule.startswith('bridge:') else BRIDGE_BUILD_ACTION) % doc


def free_action(detail):
    """The free run's own action for a profile_refused `detail` (kind, rule, path, pointer), or None."""
    kind, rule = detail.get('kind'), detail.get('rule')
    fields = {k: detail.get(k) if isinstance(detail.get(k), str) and detail.get(k) else None
              for k in ('path', 'pointer')}
    if (kind, rule) == ('representation', 'manifest') and fields['pointer'] in FLAG_POINTERS:
        return FLAGS_ACTION
    template = FREE_ACTIONS.get((kind, rule))
    if template is None or any('%%(%s)s' % k in template and fields[k] is None for k in fields):
        return None
    return template % fields


# issue #601: an `unknown_profile` refusal's action lists the served ids it carries in `detail.profiles`, so an agent
# needs no second round trip to GET /v1/profiles. The list is the row names serve/profiles.py found (each of ID_RE).
UNKNOWN_PROFILE_ACTION = 'Choose a profile id from GET /v1/profiles: %s.'


def served_profiles(detail):
    """The `detail.profiles` list of an `unknown_profile` refusal when it is one (a list of id strings), else None."""
    ids = detail.get('profiles') if isinstance(detail, dict) else None
    if isinstance(ids, list) and ids and all(isinstance(i, str) and i for i in ids):
        return ids
    return None


class Refusal(Exception):
    """A typed outcome: `Refusal(outcome, reason, **detail)`. An unknown outcome name is a ValueError at construction.

    `detail` is an open object (issue #984): keys are additive. A key once served under an outcome keeps its name and
    meaning, and a later change may add keys beside it; a reader holds the keys it knows and ignores the rest. A test
    of a served Failure therefore asserts the keys it names as a subset (`assertGreaterEqual(detail.items(), ...)`),
    never the whole object; `tests/serving/test_issue_984_accept.py` states the rule."""

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
        rule = RULE_ACTIONS.get((self.outcome, self.detail.get('rule')))
        if rule is not None:
            return rule
        m = self.detail.get('malformation')
        kind = m.get('kind') if isinstance(m, dict) else None
        code = self.detail.get('cause_code')
        if self.outcome == 'profile_refused' and kind == 'derive_refused' and code in CODE_ACTIONS:
            file = m.get('file')
            file = file if isinstance(file, str) and NAME_RE.fullmatch(file) else 'the bundle'
            return CODE_ACTIONS[code].replace('{file}', file)
        if self.outcome == 'bad_input' and kind in REQUEST_KINDS:
            return KIND_ACTIONS.get(kind, REQUEST_ACTION)
        if self.outcome == 'profile_refused' and isinstance(self.detail.get('kind'), str):
            own = bridge_action(self.detail) or free_action(self.detail)
            if own is not None:
                return own
        if self.outcome == 'unknown_profile' and served_profiles(self.detail) is not None:
            return UNKNOWN_PROFILE_ACTION % ', '.join(served_profiles(self.detail))
        up = self.detail.get('upgrade')
        url = up.get('url') if isinstance(up, dict) else None
        if self.outcome in TIER_LINK_ACTIONS and isinstance(url, str) and UPGRADE_URL.fullmatch(url):
            return TIER_LINK_ACTIONS[self.outcome] % url
        return OUTCOMES[self.outcome]['action']

    def to_dict(self):
        return {'outcome': self.outcome, 'reason': self.reason, 'action': self.action, 'detail': dict(self.detail)}

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
