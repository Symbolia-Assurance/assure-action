"""The Assure Action's entry point, run by `action.yml` in the customer's own runner (DIRECTOR-DIRECTION-SERVE-003;
SERVE-001 U2).

    "$ASSURE_PYTHON" -I -B "$GITHUB_ACTION_PATH/entry.py"

Every input arrives as an environment variable (INPUT_MODE, INPUT_API_KEY, INPUT_API_URL, INPUT_PROFILE,
INPUT_ARTEFACTS, INPUT_CONNECTION, INPUT_COLLECTION_ROLE, INPUT_COLLECTION_PRIVILEGES, INPUT_DATA_DIR, INPUT_CONFIG_DIRS,
INPUT_FAIL_ON, INPUT_ALLOW_PARTIAL, INPUT_SCOPE, INPUT_SCOPE_BINDING, INPUT_ACCEPTED_SCOPE_REF, INPUT_IDENTITY_KEY,
INPUT_REPORT, INPUT_ALLOW_OVERAGE, INPUT_REQUIREMENTS, INPUT_FRESH_CHECK, INPUT_OUTPUT), with
GITHUB_STEP_SUMMARY, GITHUB_OUTPUT and RUNNER_TEMP, and (serve-019) GITHUB_WORKSPACE, GITHUB_REPOSITORY and GITHUB_SHA
for `requirements_upload`. Before anything else is printed,
the API key and the connection are masked with `::add-mask::`. When run as a script, the process environment is then cut
to a short list (PATH, locale, temporary directory, proxy and CA settings), so no child process inherits a key, the
connection or a runner token.

`mode: api` (the default) is the thin client. The check runs on Symbolia's server:
  the inputs -> the API's profile list (`GET /v1/profiles`: each profile's input allow-list and the global limits) ->
  the frozen collector in the runner (or the `artefacts` directory) under those bounds, so an unlisted or oversize file
  never leaves the runner -> `POST /v1/checks?fail_on=...[&allow_partial=1]` over TLS with the key -> poll while 202 -> the returned
  envelope is written to the output path -> the job summary and annotations are rendered here from it -> the exit code
  is the envelope's `policy.exit` (never derived here). A failure envelope gives its outcome's exit code. `fail-on` is
  sent in its canonical form (serve-035); the server checks it against the profile; `unresolved-security` is the strict preset. `allow-partial`
  is `true` or `false` (default false; any other word is `bad_input`) and no longer changes the exit (serve-016).
  `scope` (a JSON file holding the list of selected ids), `scope-binding` (a JSON file holding the whole binding
  object, {<map>: {id: token}[, <record>: {...}]}, serve-010) and `accepted-scope-ref` (a string) are sent as
  request-body fields, never as files and never read from the collected bundle. The binding's keys must be exactly the
  map and records the API's profile list gives (a profile it lists without a map takes no `scope-binding`, and a
  profile it lists without a `scope` takes no `scope`: `bad_input` before anything is collected or sent). A non-empty `accepted-scope-ref` is refused in both modes before anything is read, collected
  or sent, with the API's own reason: no accepted scope record can be resolved yet (serve-007 F2). Unset, nothing is
  sent (serve-006 gap 1).
  A profile whose listing names the `identity_binding` record (http-observed-baseline; serve-012) with no
  `scope-binding` file reads `artefacts` as the caller's endpoint manifest directory (manifest.json and the response
  heads it names) and takes no connection: the Action makes the binding itself. Before anything is collected it runs
  the HTTP identity producer with a fresh per-job key on a pipe, then the collector with the same key
  (`action.http_identity`); the producer's record is sent as the wrapped `scope_binding` and its ids as `scope` (a
  `scope` input must list exactly them). With a `scope-binding` file (a caller who bound and collected the bundle with
  a key of their own), `artefacts` is that bundle and the wrapper is sent as written, as for any bound profile. `identity-key` takes only `pipe` (the default); any other value is masked first and refused (`bad_input`)
  before anything is read. The key is never printed, never in an environment variable or a file, and nothing persists
  between runs.
  `report` (serve-014, DD-103: `true` or `false`; unset is on in api mode and off in local mode; any other word is `bad_input` before anything is read): after
  a verdict envelope comes back, the Action asks for its claim-tree report (`Client.report`: POST, then GET while 202,
  bounded). The job summary then carries the verdict's first line, the written body and the line naming the report
  page; for a withheld report, or one the API refused (`tier_excludes`, a delivery failure), it carries the
  deterministic summary and "The report was withheld: <reason>." (`serve.render.report_withheld_line`), with the page
  line when a record came back. A refused report is one `::warning`, never an error. The verdict file, the exit code
  and the `outcome` output are the verdict's whatever the report did; the outputs add `report-status` (written,
  withheld, refused, or running when the poll ran out while the report was written: serve-015, with the page line)
  and `report-url` (the page, `<api-url>/v1/checks/<id>/report.html`, opened with the key). The
  verdict file is the envelope byte for byte, so the page is named in the summary and the outputs, never inside it.
  `mode: local` refuses `report: true` (`bad_input`) before anything is read: the report runs on the API only.
  serve-015: `allow-overage` (`true` or `false`, default false; any other word is `bad_input` before anything is
  read) sends `allow_overage: true` with the report request, so a report beyond the account's monthly allowance runs
  and its overage is charged. The summary adds one line from the record, "Report: cost USD x.xxx, charged USD y.yyy,
  allowance remaining USD z.zz" (`serve.render.report_cost_line`), or, for `allowance_exhausted` past a monthly
  allowance, "Report: allowance exhausted: USD q needed; set allow-overage or top up", or, when the account has no overage budget
  and allow-overage cannot admit the report, "...; top up, or ask Symbolia to set an overage budget" (serve-039 R1;
  serve-030: past the free
  report balance, which no top-up or overage admits, the refusal's own sentence alone, as for `job_ceiling`, DD-079
  Decision 10); the outputs add `report-cost-usd`, `report-charge-usd` and
  `report-allowance-remaining` (empty when the record carries none).
  serve-023: the check's `Idempotency-Key` is derived from the request's content (`action.client.check_key`: the
  bundle digest of the files sent, the profile, the scope fields, the requirements text's digest with the repository,
  commit and provenance sent beside it (serve-025 merge), and the query), so one check is made per distinct request:
  a later run that sends the same request gets the stored verdict back from the server, not charged again.
  serve-035 (DD-094 §7 (3) and (4)): `fail-on` is sent in one canonical form (`action.client.canonical_fail_on`) and
  is never part of the key: it is applied at render on the stored verdict, so a run under another fail-on gets the
  same check, not charged again, decided under its own fail-on.
  `fresh-check` (`true` or `false`, default false; any other word is `bad_input` before anything is read) sends a
  random key instead, for a deliberate re-check. In `mode: local` it changes nothing.
  serve-035 (DD-094 §7 (2)): the API marks a verdict it served from its store `replay: true` with `first_checked_at`;
  the job summary's first lines and the log then say "Stored verdict for the same request, first checked <time>;
  nothing was charged this run." (`serve.render.replay_line`), and a stored report (`replay: true` on the report
  answer) sets `report-charge-usd` to 0 with the line "Report: cost USD x.xxx, charged USD y.yyy on the first check
  <time>; nothing was charged this run" (`serve.render.report_replay_line`).
`mode: lint` (serve-043) runs the same local steps as `mode: api` up to and including the local file check, then sends the
upload to `POST /v1/lint` instead of `POST /v1/checks` (never `Client.submit`): nothing is charged and no check runs.
The lint record is written to the output path; the findings go to the job summary and as `::warning` annotations; the
outputs are `outcome` (`lint`), `exit-code` (0 when nothing was found, else 2) and `lint-findings` (the count).
`mode: local` runs the check in the runner with the engine this tree vendors. Its code is `action/local_mode.py`,
imported only in that branch; the public Action tree does not ship it, and there `mode: local` is `bad_input`. No
engine byte runs before the engine pin is verified (`serve.pin`, which imports no engine module).

The last stdout line reads `Assure: <the verdict line>; <outcome>; policy exit <n>; <path>` (serve-016: the verdict
line is `serve.render.verdict_line`, the job summary's headline and the first `::notice`), for example `Assure: green: 5
of 8 machines read, 3 refused; declared premises: 0; version pins: major 18; nothing disproven; not established: 4;
verdict; policy exit 0; assure-verdict.json`. An envelope without `colour`, from an older server, gives the coverage
phrase there instead (`serve.render.first_line`), or nothing for one without `machines`. The step outputs add `colour`
(green, red or yellow) and `not-established` (how many obligations were not established); a failure gives `colour` red
for exit 2 and yellow otherwise, and an empty `not-established`. serve-019: a verdict that carries requirement rows adds
`requirements-not-established` and `requirements-disproven` (counts of those rows); the summary and the annotations
carry the rows (`serve.render`).

Exit codes: 0 nothing disproven (or fail-on never), 1 something disproven, 2 bad input, 3 could not look (the
input-integrity gate stopped the check, or nothing could be read), a typed refusal or a delivery failure
(`api_unreachable`, `api_error`); an outcome with no exit code of its own (for example `rate_limited`) exits 3.
`unauthenticated` exits 2, red, as DD-073's table puts auth and key failures (serve-016, REFUTATION-028 F5).
`allow-partial` is still accepted and changes no exit (serve-016). Every failure writes the failure envelope at the output path, its
summary and one `::error` line. The summary names a check only when the check reached the server: the server's check id
is kept in `detail.check_id` (from its failure envelope, or from a verdict that came back and then could not be used);
a refusal the API answered says which request it refused (`detail.answered`, set by the client): the profile list
(`GET /v1/profiles`, before anything is collected: nothing was sent), the upload (the files were sent and not kept) or
a poll (the check was sent; the failure file carries the id from the 202); a refusal in the runner reads "No check was
sent." (`serve.render.check_line`). The key, the connection, its password and the collector's raw output are never printed,
and customer text reaches stdout only escaped as workflow-command data.

Before anything is checked or sent, `action.withhold` withholds every configuration comment and every string literal in
the policy expressions, in every mode and for a connection or an artefacts directory alike (the customer's directory is
never changed); the counts are printed and added to the job summary. First, `action.withhold.apply` checks that the
collector's REDACTION-MANIFEST.json (read beside raw/, never uploaded) binds its sidecar to the bytes as collected
(refutation 005, WH-4). When the collector's sidecar records the session facts (the collector this Action ships
does), the job summary states them in two plain lines: whether the collection session was read-only, and TLS to the
server as the server reported it (`serve.markers.session_lines`). In api mode the verdict's shape is checked before it
is rendered: a malformed verdict is `api_error` (exit 3), with the failure file and the step outputs written.

This module imports, at its top, the standard library and modules that never import the engine: `action.client`,
`action.withhold`, `serve` (flags), `serve.bundle`, `serve.markers`, `serve.outcomes` and `serve.render`.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from action import http_identity, withhold  # noqa: E402
from action.client import CHECK_ID_RE, DEFAULT_URL, LINT_SCHEMA, VERDICT_SCHEMA, Client, allow_list, canonical_fail_on  # noqa: E402
from serve import FLAGS, bundle, markers, render  # noqa: E402
from serve.outcomes import Refusal, malformation  # noqa: E402

DEFAULT_PROFILE = 'postgresql-observed-baseline'
DEFAULT_OUTPUT = 'assure-verdict.json'
FAILURE_SCHEMA = 'assure.serve.failure/v1'
MODES = ('api', 'lint', 'local')
MAX_INPUT = 4096
MAX_SCOPE_FILE = 65536
# serve-007 F2: the API's own reason (serve.profiles.SCOPE_REF_REASON; a test holds the two equal). The server refuses
# every accepted-scope-ref, so the Action refuses it before anything is collected, read or sent.
SCOPE_REF_REASON = ('no accepted scope record can be resolved for this account and profile yet; omit '
                    'accepted_scope_ref for a first-run comparison')
MAX_NOTICE_NAMES = 20
MAX_LINT_LINES = 50
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_FAIL_ON_SHAPE = re.compile(r'[A-Za-z0-9_, -]{0,100}')     # serve-016: '-' for unresolved-security
_OUTCOME_SHAPE = re.compile(r'[a-z_]{1,40}')
_FROZEN = object()
# The variables a child process of the Action may still see (ACTION-06): no input, key, connection or runner token.
KEEP_ENV = ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TZ', 'SYSTEMROOT', 'HTTPS_PROXY', 'https_proxy',
            'NO_PROXY', 'no_proxy', 'SSL_CERT_FILE', 'SSL_CERT_DIR')


def _cmd_data(value, cap=300):
    s = '' if value is None else str(value)
    s = s if cap is None or len(s) <= cap else s[:cap - 1] + '…'
    return s.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def _cmd_prop(value):
    return _cmd_data(value).replace(':', '%3A').replace(',', '%2C')


def _mask(value):
    """One `::add-mask::` line; the value is escaped as workflow-command data, never truncated."""
    return '::add-mask::' + str(value).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def scrub_process_env(environ):
    """Cut `environ` (os.environ when run as a script) to KEEP_ENV, so no child inherits a secret."""
    for k in list(environ):
        if k not in KEEP_ENV:
            del environ[k]


def _plain(env, name, default=''):
    """An input as stripped text; `bad_input` when it is too long or holds a control character."""
    v = env.get(name)
    v = default if v is None else str(v)
    if len(v) > MAX_INPUT or _CONTROL.search(v):
        raise Refusal('bad_input', '%s is longer than %d characters or holds a control character'
                      % (name[len('INPUT_'):].lower().replace('_', '-'), MAX_INPUT))
    return v.strip()


def _output_path(env, cwd):
    """(text as given, absolute Path, deferred Refusal or None). A bad path falls back to the default name."""
    text = env.get('INPUT_OUTPUT')
    text = DEFAULT_OUTPUT if text is None or not str(text).strip() else str(text).strip()
    if len(text) > MAX_INPUT or _CONTROL.search(text):
        return DEFAULT_OUTPUT, Path(cwd) / DEFAULT_OUTPUT, Refusal('bad_input', 'output is too long or holds a '
                                                                   'control character')
    p = Path(text)
    return text, (p if p.is_absolute() else Path(cwd) / p), None


def _write_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.%s.%s.tmp' % (path.name, secrets.token_hex(4)))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _append(path_text, text):
    if path_text:
        with open(path_text, 'a', encoding='utf-8') as fh:
            fh.write(text)


def failure_envelope(check_id, refusal):
    """The failure envelope (`assure.serve.failure/v1`), the same object `serve.envelope.failure` builds."""
    doc = {'schema': FAILURE_SCHEMA, 'check_id': check_id}
    doc.update(refusal.to_dict())
    doc.update(FLAGS)
    return doc


def check_verdict(v):
    """The shape the Action renders, checked before anything is written (TC-3): a verdict envelope whose policy exit
    is an int in 0..125 and whose outcome is a short word; `counts` an object of status -> int; `rows` a list of
    objects; `vocabulary` an object whose `precedence` is a list of strings; `policy.fail_on` and `scope_notes` lists.
    Anything else is `api_error`."""
    def bad(what):
        return Refusal('api_error', 'the verdict from the API is malformed: %s' % what)
    if not isinstance(v, dict) or v.get('schema') != VERDICT_SCHEMA:
        raise bad('it is not a verdict envelope')
    policy = v.get('policy')
    code = policy.get('exit') if isinstance(policy, dict) else None
    if type(code) is not int or not 0 <= code <= 125 or not isinstance(v.get('outcome'), str) \
            or not _OUTCOME_SHAPE.fullmatch(v['outcome']):
        raise Refusal('api_error', 'the verdict from the API carries no policy exit or outcome')
    if not isinstance(policy.get('fail_on', []), list):
        raise bad('policy.fail_on is not a list')
    counts = v.get('counts', {})
    if not isinstance(counts, dict) or not all(isinstance(k, str) and type(n) is int and n >= 0
                                               for k, n in counts.items()):
        raise bad('counts is not an object of status to count')
    rows = v.get('rows', [])
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise bad('rows is not a list of objects')
    vocab = v.get('vocabulary', {})
    if not isinstance(vocab, dict):
        raise bad('vocabulary is not an object')
    prec = vocab.get('precedence', [])
    if not isinstance(prec, list) or not all(isinstance(s, str) for s in prec):
        raise bad('vocabulary.precedence is not a list of words')
    if not isinstance(v.get('scope_notes', []), list):
        raise bad('scope_notes is not a list')
    return v


class _Scrub:
    """Removes every secret (the API key, the connection's secrets) from text the Action writes about a failure."""

    def __init__(self, values=()):
        self.values = []
        self.add(values)

    def add(self, values):
        self.values = sorted(set(self.values) | {v for v in values if v and len(v) >= 4}, key=len, reverse=True)

    def __call__(self, text):
        s = str(text)
        for v in self.values:
            s = s.replace(v, '***')
        return s

    def refusal(self, e):
        detail = {k: (self(v) if isinstance(v, str) and k != 'answered' else v) for k, v in e.detail.items()}
        return Refusal(e.outcome, self(e.reason), **detail)


def load_collect():
    """`action.collect`, for a connection (it bounds the collected files with `serve.bundle`, as the server does)."""
    from action import collect
    return collect


def _mode(env):
    m = _plain(env, 'INPUT_MODE').lower() or 'api'
    if m not in MODES:
        raise Refusal('bad_input', 'mode must be api, lint or local')
    return m


def _json_input(env, name, kind, field, cwd):
    """serve-006 gap 1: the JSON value of the file an input names (relative to the working directory, a regular file of
    at most 64 KiB, never a link), or None when the input is unset. `bad_input` with the malformation `kind`
    otherwise; the file's text is never shown."""
    text = _plain(env, name)
    if not text:
        return None
    shown = name[len('INPUT_'):].lower().replace('_', '-')
    p = Path(text) if Path(text).is_absolute() else Path(cwd or os.getcwd()) / text
    try:
        data = bundle._read_capped(p, MAX_SCOPE_FILE)
        return bundle.parse_json(data)
    except (OSError, Refusal):
        raise Refusal('bad_input', '%s must name a readable JSON file of at most %d bytes' % (shown, MAX_SCOPE_FILE),
                      malformation=malformation(kind, field=field)) from None


REQUIREMENTS_FILE = 'requirements.md'
MAX_EVENT_BYTES = 16 * 2 ** 20
NONE_SENTINEL = 'none'        # REFUTATION-034-R2 N5: `requirements: none` sends no requirements text and prints no notice;
# compared exact-case (serve-025): `NONE` is a file name
_SILENCE = 'to keep it and silence this notice, set requirements to none.'
# REFUTATION-034-R2 N5: why a repository-root requirements.md was not sent, and the one way to send it (serve-025:
# one instruction for each case, then the way to silence the notice)
SKIPPED_HOW = {
    'link': ('it is a symbolic link', 'To send it, name the file it points to in the requirements input; '),
    'irregular': ('it is not a regular file', 'To send it, name a regular file in the requirements input; '),
    'unreadable': ('it could not be read', 'To send it, make it readable; '),
    'size': ('it is larger than %d bytes' % bundle.MAX_REQUIREMENTS_BYTES, 'To send it, shorten it to within the '
             'bounds; '),
    'encoding': ('it is not UTF-8 text', 'To send it, save it as UTF-8; '),
    'bounds': (None, 'To send it, shorten it to within the bounds; '),
}
LOCAL_REQUIREMENTS_NOTICE = ('requirements are read in api mode only: local mode did not read or send requirements.md')


def skipped_notice(kind, why=None):
    """The one notice for a repository-root requirements.md that was not sent (SKIPPED_HOW)."""
    words, how = SKIPPED_HOW[kind]
    return 'requirements.md at the repository root was not sent (%s). %s%s' % (why or words, how, _SILENCE)


def _read_requirements(path):
    """The text of a requirements file, or Refusal('bad_input') naming why it cannot be sent, with `detail.kind` one
    of SKIPPED_HOW's keys (a link, not a regular file, unreadable, larger than the bound, not UTF-8, beyond the line
    bounds). Its content is never quoted."""
    def bad(why, kind):
        return Refusal('bad_input', 'requirements %s' % why, kind=kind,
                       malformation=malformation('requirements', field='requirements'))
    if os.path.islink(path):
        raise bad('is a symbolic link; name the file it points to', 'link')
    try:
        data = bundle._read_capped(path, bundle.MAX_REQUIREMENTS_BYTES)
    except Refusal as e:
        if e.outcome == 'oversize_input':           # REFUTATION-034-R2 N4: a directory or FIFO is not "too large"
            raise bad('is larger than %d bytes' % bundle.MAX_REQUIREMENTS_BYTES, 'size') from None
        raise bad('is not a regular file', 'irregular') from None
    except OSError:
        if os.path.exists(path) and not os.path.isfile(path):
            raise bad('is not a regular file', 'irregular') from None
        raise bad('must name a readable file', 'unreadable') from None
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise bad('is not UTF-8 text', 'encoding') from None
    try:
        return bundle.check_requirements(text)
    except Refusal as e:
        e.detail['kind'] = 'bounds'
        raise


def _head_commit(env):
    """REFUTATION-034 D2: the commit a check is about. On a pull_request event GITHUB_SHA is the synthetic merge
    commit, so the event's `pull_request.head.sha` (GITHUB_EVENT_PATH, bounded) is sent when it is a commit id; any
    other event, or an event file that cannot be read, sends GITHUB_SHA."""
    sha = str(env.get('GITHUB_SHA') or '').strip()
    path = str(env.get('GITHUB_EVENT_PATH') or '').strip()
    if path:
        try:
            doc = bundle.parse_json(bundle._read_capped(Path(path), MAX_EVENT_BYTES),
                                    bundle.Limits(body_bytes=MAX_EVENT_BYTES, json_depth=128))
            head = ((doc.get('pull_request') or {}).get('head') or {}).get('sha') if isinstance(doc, dict) else None
        except (OSError, Refusal, AttributeError):
            head = None
        if bundle.commit_ok(head):
            return head
    return sha


def requirements_upload(env, cwd):
    """serve-019 (coordination 2136): ({requirements?, repository?, commit?, provenance?}, notice or None). The text is
    the `requirements` input's file (relative to the working directory): one that is missing, unreadable, a link,
    not a regular file, beyond the bounds or not UTF-8 is `bad_input` before anything is collected or sent. The input
    `none` (NONE_SENTINEL) sends no text and prints no notice; a file named `none` is then reached as `./none`. With the input empty, the
    repository root's requirements.md (GITHUB_WORKSPACE) is sent when it can be; REFUTATION-034 F1: when it cannot,
    no text is sent and the notice says why (`skipped_notice`), so a file the operator never selected never stops the
    run. GITHUB_REPOSITORY and the head commit (`_head_commit`) go as repository and commit with `provenance:
    runner`; the API reads them as metadata, never as authority."""
    out, notice = {}, None
    named = _plain(env, 'INPUT_REQUIREMENTS')
    workspace = str(env.get('GITHUB_WORKSPACE') or '').strip()
    if named == NONE_SENTINEL:                       # REFUTATION-034-R2 N5: send no text, print no notice
        pass
    elif named:
        path = Path(named) if Path(named).is_absolute() else Path(cwd or os.getcwd()) / named
        out['requirements'] = _read_requirements(path)
    elif workspace and os.path.lexists(os.path.join(workspace, REQUIREMENTS_FILE)):
        try:
            out['requirements'] = _read_requirements(Path(workspace) / REQUIREMENTS_FILE)
        except Refusal as e:
            kind = e.detail.get('kind', 'bounds')
            why = e.reason.replace('requirements are ', '', 1).replace('requirements ', '', 1) \
                if kind == 'bounds' else None        # "400 lines; the limit is 256", "line 3 is longer than ..."
            notice = skipped_notice(kind, why)
    repo, sha = str(env.get('GITHUB_REPOSITORY') or '').strip(), _head_commit(env)
    if repo and sha:
        out.update(bundle.upload_fields({'repository': repo, 'commit': sha, 'provenance': 'runner'}))
    return out, notice


def local_requirements_notice(env):
    """REFUTATION-034 F2: LOCAL_REQUIREMENTS_NOTICE when local mode finds a requirements file it will not read (the
    `requirements` input set, or a requirements.md at the repository root); None otherwise."""
    workspace = str(env.get('GITHUB_WORKSPACE') or '').strip()
    named = str(env.get('INPUT_REQUIREMENTS') or '').strip()
    if named == NONE_SENTINEL:
        return None
    if named or (
            workspace and os.path.lexists(os.path.join(workspace, REQUIREMENTS_FILE))):
        return LOCAL_REQUIREMENTS_NOTICE
    return None


def _inputs(env, conn, conn_error, collect, collector_dir=None, cwd=None):
    profile = _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE
    artefacts = _plain(env, 'INPUT_ARTEFACTS')
    has_conn = bool(str(env.get('INPUT_CONNECTION') or '').strip())
    if bool(artefacts) == has_conn:
        raise Refusal('bad_input', 'set exactly one of connection and artefacts (%s set)'
                      % ('both are' if has_conn else 'neither is'))
    http_identity.parse_key_source(env.get('INPUT_IDENTITY_KEY'))     # serve-012: masked already, refused here
    if _plain(env, 'INPUT_ACCEPTED_SCOPE_REF'):          # serve-007 F2: before any file is read or collected
        raise Refusal('bad_input', SCOPE_REF_REASON,
                      malformation=malformation('scope_ref', field='accepted_scope_ref'))
    fail_on = canonical_fail_on(_plain(env, 'INPUT_FAIL_ON'))     # serve-025's form, carried: one form, both modes
    allow_partial = parse_allow_partial(_plain(env, 'INPUT_ALLOW_PARTIAL'))
    data_dir_text = _plain(env, 'INPUT_DATA_DIR')
    config_dirs_text = env.get('INPUT_CONFIG_DIRS')      # line breaks separate items, so it is not read by _plain
    if conn_error is not None:
        raise conn_error
    out = {'profile': profile, 'fail_on': fail_on, 'artefacts': artefacts or None, 'allow_partial': allow_partial,
           'scope': _json_input(env, 'INPUT_SCOPE', 'scope_missing', None, cwd),
           'scope_binding': _json_input(env, 'INPUT_SCOPE_BINDING', 'scope_binding', 'scope_binding', cwd),
           'accepted_scope_ref': None}
    if artefacts:
        if data_dir_text:
            raise Refusal('bad_input', 'data-dir applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        if str(config_dirs_text or '').strip(' \t\r\n:'):
            raise Refusal('bad_input', 'config-dirs applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        return out
    out['role'] = collect.check_role(_plain(env, 'INPUT_COLLECTION_ROLE'), conn)
    out['privileges'] = collect.check_privileges(_plain(env, 'INPUT_COLLECTION_PRIVILEGES'),
                                                 collect.pin_generation(collector_dir))
    out['data_dir'] = collect.check_data_dir(data_dir_text)
    out['config_dirs'] = collect.check_config_dirs(config_dirs_text)
    return out


def parse_allow_partial(text):
    """The `allow-partial` input: '', 'false' or '0' is False; 'true' or '1' is True (case-insensitive); else bad_input.
    The same words `serve.envelope.parse_allow_partial` accepts, which the server applies again."""
    v = (text or '').strip().lower()
    if v in ('', 'false', '0'):
        return False
    if v in ('true', '1'):
        return True
    raise Refusal('bad_input', 'allow-partial must be true or false')


def parse_report(text, mode='api'):
    """serve-014, DD-103: the `report` input: unset or '' is True in api mode and False in any other mode; 'false' or
    '0' is False; 'true' or '1' is True (case-insensitive); else bad_input."""
    v = (text or '').strip().lower()
    if v == '':
        return mode == 'api'
    if v in ('false', '0'):
        return False
    if v in ('true', '1'):
        return True
    raise Refusal('bad_input', 'report must be true or false')


def parse_allow_overage(text):
    """serve-015: the `allow-overage` input, read as `allow-partial` is."""
    v = (text or '').strip().lower()
    if v in ('', 'false', '0'):
        return False
    if v in ('true', '1'):
        return True
    raise Refusal('bad_input', 'allow-overage must be true or false')


def parse_fresh_check(text):
    """serve-023: the `fresh-check` input, read as `allow-partial` is."""
    v = (text or '').strip().lower()
    if v in ('', 'false', '0'):
        return False
    if v in ('true', '1'):
        return True
    raise Refusal('bad_input', 'fresh-check must be true or false')


def _report_usage(report, first_checked_at=None):
    """serve-015: (summary line or None, step outputs text) of a report record or refusal. serve-035: a stored report
    (`replay: true`) names the first check's charge (`render.report_replay_line`) and this run's `report-charge-usd`
    is 0."""
    cost = report.get('cost') if isinstance(report, dict) and isinstance(report.get('cost'), dict) else {}
    replay = isinstance(report, dict) and report.get('replay') is True
    if isinstance(report, Refusal) and report.outcome == 'allowance_exhausted' and 'topup_needed_usd' in report.detail:
        # serve-030: a once-only balance (no top-up needed, overage never admits it) has its reason line only
        line = render.report_exhausted_line(report.detail.get('topup_needed_usd'), report.detail.get('admits'),
                                            report.detail.get('overage_budget_usd'))
    elif isinstance(report, Refusal):
        line = None
    elif replay:
        line = render.report_replay_line(report, first_checked_at)
    else:
        line = render.report_cost_line(report) if isinstance(report, dict) else None

    def num(v):
        return '' if isinstance(v, bool) or not isinstance(v, (int, float)) else repr(float(v))
    charge = num(cost.get('charge_usd'))
    outs = 'report-cost-usd=%s\nreport-charge-usd=%s\nreport-allowance-remaining=%s\n' % (
        num(cost.get('usd')) if 'charge_usd' in cost else '', num(0.0) if replay and charge else charge,
        num(cost.get('allowance_remaining')))
    return line, outs


def _with_report(summary, report, url, first_checked_at=None):
    """(summary, report-status, report-url) for a requested report (module docstring). `report` is the record or the
    Refusal that ended the request."""
    tail = _usage_tail(report, first_checked_at)
    if isinstance(report, dict) and report.get('status') == 'written':
        head = summary.split('\n', 1)[0]
        return (head + '\n\n' + render.report_markdown(report.get('body_md')) + '\n\n' + render.report_page_line(url)
                + '\n' + tail, 'written', url)
    if isinstance(report, dict):
        fallback = report.get('fallback') if isinstance(report.get('fallback'), dict) else {}
        return (summary + '\n' + render.report_withheld_line(fallback.get('reason')) + '\n'
                + render.report_page_line(url) + '\n' + tail, 'withheld', url)
    reason = report.reason if isinstance(report, Refusal) else None
    if isinstance(report, Refusal) and report.detail.get('report_running') is True:
        # serve-015: the poll ran out while the report was being written; the page will carry it
        return (summary + '\n' + render.report_withheld_line(reason) + '\n' + render.report_page_line(url) + '\n',
                'running', url)
    return summary + '\n' + render.report_withheld_line(reason) + '\n' + tail, 'refused', ''


def _usage_tail(report, first_checked_at=None):
    line = _report_usage(report, first_checked_at)[0]
    return '' if line is None else line + '\n'


def _replay_lead(summary, verdict):
    """serve-035 (DD-094 §7 (2)): the summary with `render.replay_line` after its first line, for a verdict the API
    served from its store; unchanged otherwise."""
    lead = render.replay_line(verdict)
    if lead is None:
        return summary
    head, _, rest = summary.partition('\n')
    return head + '\n\n' + lead + '\n' + rest


def _lint_line(f):
    where = [str(f[k]) for k in ('endpoint_id', 'file') if isinstance(f.get(k), str)]
    if type(f.get('line')) is int:
        where.append('line %d' % f['line'])
    return '%s: %s%s' % (f.get('stage'), f.get('text'), ' (%s)' % ', '.join(where) if where else '')


def _lint_markdown(found):
    """serve-043: the job summary of a lint record: a headline, then one short line per finding."""
    if not found:
        return '## Assure lint: ready\n\nNo problems found. Nothing was charged.\n'
    lines = ['## Assure lint: %d finding(s)' % len(found), '', 'Fix these before a check. Nothing was charged.', '']
    lines += ['- %s' % render.esc(_lint_line(f)) for f in found[:MAX_LINT_LINES]]
    if len(found) > MAX_LINT_LINES:
        lines.append('- and %d more in the lint file' % (len(found) - MAX_LINT_LINES))
    return '\n'.join(lines) + '\n'


def _scratch(env):
    temp_root = env.get('RUNNER_TEMP') or None
    if temp_root and not os.path.isdir(temp_root):
        temp_root = None
    return Path(tempfile.mkdtemp(prefix='assure-', dir=temp_root))


def main(env, *, root, stdout=None, load_checker=None, pin_path=None, collector_dir=None, collector_sha256=_FROZEN,
         psql='psql', collect_timeout=None, check_timeout=60, limits=None, cwd=None, client_factory=None) -> int:
    """Run one check as the Action; return the exit code. `load_checker`, `pin_path`, `collector_dir`,
    `collector_sha256`, `psql`, `limits` and `client_factory(base_url, api_key) -> Client` are test seams; production
    passes none of them."""
    out = stdout if stdout is not None else sys.stdout

    def say(line):
        out.write(line + '\n')
        out.flush()

    env = dict(env)
    cwd = cwd or os.getcwd()
    check_id = secrets.token_hex(16)
    raw_key = str(env.get('INPUT_API_KEY') or '')
    conn_text = str(env.get('INPUT_CONNECTION') or '')
    id_key = str(env.get('INPUT_IDENTITY_KEY') or '')
    pasted = (id_key, id_key.strip()) if id_key.strip() not in ('', http_identity.KEY_SOURCE) else ()
    first = [v for v in dict.fromkeys((raw_key, raw_key.strip(), conn_text.strip()) + pasted) if v]
    for v in first:                                    # before anything else is printed
        say(_mask(v))
    scrub = _Scrub(first)
    out_text, out_path, out_error = _output_path(env, cwd)
    state = {'mode': None, 'scratch': None, 'withheld': None, 'session': [], 'report_on': False, 'report': None,
             'report_url': '', 'allow_overage': False, 'requirements_notice': None, 'fresh_check': False}

    def outputs(outcome, code, extra='', verdict=None, lint_colour=None):
        if lint_colour is not None:               # serve-043: a lint answer is green with no findings, else red
            colour, n = lint_colour, ''
        elif verdict is None:                     # serve-016: a failure is red for bad input, yellow otherwise
            colour, n = ('red' if code == 2 else 'yellow'), ''
        else:
            colour = verdict.get('colour') if verdict.get('colour') in render.COLOURS else ''
            n = str(len(verdict['not_established'])) if isinstance(verdict.get('not_established'), list) else ''
            counts = render.requirement_counts(verdict)          # serve-019: only when requirements were sent
            if counts is not None:
                extra = 'requirements-not-established=%d\nrequirements-disproven=%d\n%s' % (
                    counts['not_established'], counts['disproven'], extra)
        try:
            _append(env.get('GITHUB_OUTPUT'), 'verdict-path=%s\noutcome=%s\nexit-code=%d\ncolour=%s\nnot-established=%s\n%s'
                    % (out_text, outcome, code, colour, n, extra))
        except OSError as w:
            say('::warning title=Assure::%s' % _cmd_data('the step outputs could not be written (%s)' % type(w).__name__))

    def failed(e):
        e = scrub.refusal(e)
        code = e.exit if e.exit is not None else 3
        server_cid = state.get('server_check_id')
        if 'check_id' not in e.detail and isinstance(server_cid, str) and CHECK_ID_RE.fullmatch(server_cid):
            e.detail['check_id'] = server_cid          # a verdict came back, so the check reached the server
        cid = e.detail.get('check_id') or e.detail.get('sent_check_id')    # a refused poll: the id from the 202
        doc = failure_envelope(cid if isinstance(cid, str) and CHECK_ID_RE.fullmatch(cid) else check_id, e)
        try:
            _write_file(out_path, bundle.dumps(doc))
        except (OSError, ValueError) as w:
            say('::error title=Assure::%s' % _cmd_data('the failure file could not be written (%s)' % type(w).__name__))
        try:
            _append(env.get('GITHUB_STEP_SUMMARY'), render.failure_markdown(doc))
        except OSError:
            pass
        say('::error title=%s::%s' % (_cmd_prop('Assure %s' % e.outcome), _cmd_data('%s: %s' % (e.outcome, e.reason))))
        outputs(e.outcome, code)
        return code

    def connection(collect):
        """Parse the connection (when set) and mask its secrets; (conn, deferred Refusal or None)."""
        if not conn_text.strip():
            return None, None
        try:
            conn = collect.parse_connection(conn_text)
        except Refusal as e:
            return None, e
        for line in collect.mask_commands(conn, conn_text):
            if line not in (_mask(v) for v in first):
                say(line)
        scrub.add(conn.secrets)
        return conn, None

    def collect_kw(collect, inputs):
        return dict(role=inputs['role'], privileges=inputs['privileges'], data_dir=inputs['data_dir'],
                    extra_roots=inputs['config_dirs'], collector_dir=collector_dir,
                    frozen_sha256=collect.FROZEN_COLLECTOR_SHA256 if collector_sha256 is _FROZEN else collector_sha256,
                    psql=psql, path=env.get('PATH') or '/usr/bin:/bin',
                    timeout=collect.DEFAULT_TIMEOUT if collect_timeout is None else collect_timeout)

    def session(files):
        """The session facts the collector's sidecar records, as plain lines for the log and the job summary."""
        state['session'] = markers.session_lines(files)
        for line in state['session']:
            say('Assure: ' + _cmd_data(line))

    def run_local():
        absent = Refusal('bad_input', 'local mode is not available in this distribution; use mode: api')
        if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_mode.py')):
            raise absent
        try:
            from action import local_mode                      # standard library only at its top
        except ImportError:
            raise absent from None
        engine = local_mode.verify_engine_pin(root, pin_path)   # before any engine byte is imported
        state['requirements_notice'] = local_requirements_notice(env)     # REFUTATION-034 F2
        if state['requirements_notice']:
            say('::notice title=Assure requirements::%s' % _cmd_data(state['requirements_notice'], cap=None))
        if out_error is not None:
            raise out_error
        from action import collect                             # after the pin, like every local-mode import
        conn, conn_error = connection(collect)
        inputs = _inputs(env, conn, conn_error, collect, collector_dir, cwd)
        state['scratch'] = _scratch(env)
        verdict, ignored, state['withheld'] = local_mode.run(
            engine=engine, inputs=inputs, fail_on_text=inputs['fail_on'], conn=conn, allow_partial=inputs['allow_partial'],
            collect_kw=None if inputs['artefacts'] else collect_kw(collect, inputs), scratch=state['scratch'], cwd=cwd,
            check_id=check_id, load_checker=load_checker, check_timeout=check_timeout, limits=limits,
            on_withheld=lambda counts: say('Assure: ' + withhold.describe(counts)), on_collected=session)
        return verdict, ignored

    def run_api():
        if out_error is not None:
            raise out_error
        collect = load_collect() if conn_text.strip() else None
        conn, conn_error = connection(collect) if collect is not None else (None, None)
        inputs = _inputs(env, conn, conn_error, collect, collector_dir, cwd)
        if not _FAIL_ON_SHAPE.fullmatch(inputs['fail_on']):
            raise Refusal('bad_input', 'fail-on must be a short comma list of statuses, or never')
        upload, state['requirements_notice'] = requirements_upload(env, cwd)   # serve-019: before anything is sent
        if state['requirements_notice']:
            say('::notice title=Assure requirements::%s' % _cmd_data(state['requirements_notice'], cap=None))
        url = _plain(env, 'INPUT_API_URL') or DEFAULT_URL
        client = (client_factory or Client)(url, raw_key.strip())
        allow = allow_list(client.profiles(), inputs['profile'])
        if inputs['scope'] is not None and allow.scope is None:     # serve-007 F2: refused before collection
            raise Refusal('bad_input', 'profile %s checks a fixed scope and takes no scope' % inputs['profile'],
                          malformation=malformation('scope_missing'))
        binding = inputs['scope_binding']
        # serve-012: with no scope-binding file, the Action makes the binding with the identity producer
        identity = http_identity.declares_identity(allow) and binding is None
        if identity and not inputs['artefacts']:
            raise Refusal('bad_input', 'profile %s reads an endpoint manifest: set artefacts to the directory holding '
                          'manifest.json and the response heads it names (it takes no connection)' % inputs['profile'])
        if binding is not None:      # serve-010: the file is the wrapper; its keys are the listing's map and records
            name = (allow.scope or {}).get('binding')
            if name is None:
                raise Refusal('bad_input', 'profile %s takes no scope-binding' % inputs['profile'],
                              malformation=malformation('scope_binding', field='scope_binding'))
            keys = {name} | set(allow.scope.get('records') or ())
            if not isinstance(binding, dict) or set(binding) != keys:
                raise Refusal('bad_input', 'scope-binding for profile %s must be an object with exactly the keys %s'
                              % (inputs['profile'], ', '.join(sorted(keys))),
                              malformation=malformation('scope_binding', field='scope_binding'))
        lim = limits if limits is not None else allow.limits
        scope = inputs['scope']
        if identity:
            art = Path(inputs['artefacts'])
            state['scratch'] = _scratch(env)
            # resolved: the producer and the collector open every component with no-follow, and a runner's temporary
            # directory may sit behind a link (macOS /var)
            produced, binding = http_identity.produce_and_collect(
                root, (art if art.is_absolute() else Path(cwd) / art).resolve(), state['scratch'].resolve(), scope=scope)
            scope = sorted(binding['endpoint_tokens'])
            collected = withhold.apply(bundle.from_directory(produced, allow, lim), allow)
        elif inputs['artefacts']:
            art = Path(inputs['artefacts'])
            collected = withhold.apply(bundle.from_directory(art if art.is_absolute() else Path(cwd) / art, allow,
                                                             lim), allow)
        else:
            state['scratch'] = _scratch(env)
            work = state['scratch'] / 'collect'
            work.mkdir(mode=0o700)
            collected = collect.collect(conn, profile=allow, scratch=work, limits=lim, **collect_kw(collect, inputs))
        state['withheld'] = collected.withheld
        say('Assure: ' + withhold.describe(collected.withheld))
        session(collected.files)
        bundle.check_files(collected.files, allow, lim)        # nothing unlisted or oversize leaves the runner
        extra = {'allow_partial': True} if inputs['allow_partial'] else {}
        extra.update(upload)
        if state['mode'] == 'lint':               # serve-043: the free pre-flight; nothing is submitted or charged
            return client.lint(inputs['profile'], collected.files, inputs['fail_on'] or None, limits=lim, scope=scope,
                               scope_binding=binding, accepted_scope_ref=inputs['accepted_scope_ref'],
                               **extra), list(collected.ignored)
        verdict = client.submit(inputs['profile'], collected.files, inputs['fail_on'] or None, limits=lim,
                                scope=scope, scope_binding=binding,
                                accepted_scope_ref=inputs['accepted_scope_ref'],
                                key_from_bundle=not state['fresh_check'], **extra)
        if isinstance(verdict, dict):
            state['server_check_id'] = verdict.get('check_id')
        check_verdict(verdict)
        if state['report_on']:                    # serve-014: never changes the verdict, its file or its exit
            state['report_url'] = client.base + '/v1/checks/%s/report.html' % verdict['check_id']
            try:
                state['report'] = client.report(verdict['check_id'], allow_overage=state['allow_overage'])
            except Refusal as e:
                state['report'] = scrub.refusal(e)
            except Exception as e:  # typed, never a traceback; the class name only
                state['report'] = Refusal('api_error', 'the report request failed unexpectedly (%s)' % type(e).__name__)
        return verdict, list(collected.ignored)

    def finish_lint(doc, ignored):
        """serve-043: write the lint record to the output path, the findings to the job summary and as warnings, and the
        outputs outcome `lint`, exit-code (0 when ok, else 2) and lint-findings. Never a charge, never a check."""
        if doc.get('schema') != LINT_SCHEMA:
            return failed(Refusal('api_error', 'no lint record'))
        found = [f for f in doc['findings'] if isinstance(f, dict)]
        code = 0 if doc.get('ok') is True and not found else 2
        try:
            summary = _lint_markdown(found)
        except Exception as e:  # the class name only, never a value
            return failed(Refusal('api_error', 'the lint record could not be rendered (%s)' % type(e).__name__))
        try:
            _write_file(out_path, bundle.dumps(doc))
        except (OSError, ValueError) as w:
            return failed(Refusal('checker_error', 'the lint file could not be written (%s)' % type(w).__name__))
        try:
            _append(env.get('GITHUB_STEP_SUMMARY'), summary)
        except OSError as w:
            say('::warning title=Assure::%s' % _cmd_data('the job summary could not be written (%s)' % type(w).__name__))
        for f in found:
            say('::warning title=%s::%s' % (_cmd_prop('Assure lint'), _cmd_data(_lint_line(f))))
        if ignored:
            names = ignored[:MAX_NOTICE_NAMES]
            more = len(ignored) - len(names)
            say('::notice title=Assure::%s' % _cmd_data('%d name(s) not read by profile %s: %s%s' % (
                len(ignored), _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE, ', '.join(names),
                (' and %d more' % more) if more else '')))
        say('Assure: lint: %s; %d finding(s); nothing was charged; policy exit %d; %s' % (
            'ready for a check' if code == 0 else 'fix these before a check', len(found), code, _cmd_data(out_text)))
        outputs('lint', code, 'lint-findings=%d\n' % len(found), lint_colour='green' if code == 0 else 'red')
        return code

    try:
        try:
            state['mode'] = _mode(env)
            state['report_on'] = parse_report(_plain(env, 'INPUT_REPORT'), state['mode'])   # serve-014: before anything is read
            state['allow_overage'] = parse_allow_overage(_plain(env, 'INPUT_ALLOW_OVERAGE'))     # serve-015
            state['fresh_check'] = parse_fresh_check(_plain(env, 'INPUT_FRESH_CHECK'))           # serve-023
            if state['report_on'] and state['mode'] != 'api':
                raise Refusal('bad_input', 'report is available in api mode only; set mode: api or leave report off')
            verdict, ignored = run_local() if state['mode'] == 'local' else run_api()
            inputs_profile = _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE
        except Refusal as e:
            return failed(e)
        except Exception as e:  # typed, never a traceback; the class name only, never a value
            outcome = 'api_error' if state['mode'] == 'api' else 'checker_error'
            return failed(Refusal(outcome, 'the Action failed unexpectedly (%s)' % type(e).__name__))
    finally:
        if state['scratch'] is not None:
            shutil.rmtree(state['scratch'], ignore_errors=True)

    if state['mode'] == 'lint':
        return finish_lint(verdict, ignored)
    if verdict.get('schema') != VERDICT_SCHEMA:
        return failed(Refusal('api_error' if state['mode'] == 'api' else 'checker_error', 'no verdict envelope'))
    code = verdict['policy']['exit']
    unrenderable = 'api_error' if state['mode'] == 'api' else 'checker_error'
    report_extra = ''
    try:                                               # rendered before anything is written: a fault is typed
        summary = render.summary_markdown(verdict)
        when = render.first_checked(verdict)            # serve-035: the first check's time, as the API wrote it
        if state['report_on']:
            summary, report_status, report_url = _with_report(summary, state['report'], state['report_url'], when)
            report_extra = 'report-status=%s\nreport-url=%s\n' % (report_status, report_url) \
                + _report_usage(state['report'], when)[1]
        summary = _replay_lead(summary, verdict)
        lead = render.replay_line(verdict)
        if state['withheld'] is not None:
            summary += withhold.summary_markdown(state['withheld'])
        summary += markers.session_markdown(state['session'])
        if state['requirements_notice']:                  # REFUTATION-034 F1/F2: the same words in the summary
            summary += '\n' + render.esc(state['requirements_notice']) + '\n'
        notes = render.annotations(verdict)
    except Exception as e:  # the class name only, never a value
        return failed(Refusal(unrenderable, 'the verdict could not be rendered (%s)' % type(e).__name__))
    try:
        _write_file(out_path, bundle.dumps(verdict))
    except (OSError, ValueError) as w:
        return failed(Refusal('checker_error', 'the verdict file could not be written (%s)' % type(w).__name__))
    try:
        _append(env.get('GITHUB_STEP_SUMMARY'), summary)
    except OSError as w:
        say('::warning title=Assure::%s' % _cmd_data('the job summary could not be written (%s)' % type(w).__name__))
    for line in notes:
        say(line)
    if ignored:
        names = ignored[:MAX_NOTICE_NAMES]
        more = len(ignored) - len(names)
        say('::notice title=Assure::%s' % _cmd_data('%d name(s) not read by profile %s: %s%s' % (
            len(ignored), inputs_profile, ', '.join(names), (' and %d more' % more) if more else '')))
    if state['report_on']:
        if isinstance(state['report'], dict):
            say('Assure: report %s; %s' % (_cmd_data(state['report'].get('status')), _cmd_data(state['report_url'])))
        else:
            say('::warning title=%s::%s' % (_cmd_prop('Assure report'), _cmd_data(
                render.report_withheld_line(getattr(state['report'], 'reason', None)))))
    if lead is not None:                               # serve-035: a stored verdict says so in the log too
        say('Assure: ' + _cmd_data(lead))
    bound = render.scope_notes_line(verdict)          # serve-012: a selected scope's bound, just before the last line
    if bound is not None:
        say('Assure: scope: %s' % _cmd_data(bound))
    line = render.verdict_line(verdict)              # serve-016: the verdict line; an older server's coverage phrase
    line = render.first_line(verdict) if line is None else line
    say('Assure: %s%s; policy exit %d; %s' % ('' if line is None else _cmd_data(line, cap=None) + '; ',
                                              _cmd_data(verdict['outcome']), code, _cmd_data(out_text)))
    outputs(verdict['outcome'], code, report_extra, verdict)
    return code


if __name__ == '__main__':
    _env = dict(os.environ)
    scrub_process_env(os.environ)
    sys.exit(main(_env, root=_ROOT))

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
