"""The Assure Action's entry point, run by `action.yml` in the customer's own runner (DIRECTOR-DIRECTION-SERVE-003;
SERVE-001 U2).

    "$ASSURE_PYTHON" -I -B "$GITHUB_ACTION_PATH/entry.py"

Every input arrives as an environment variable (INPUT_MODE, INPUT_API_KEY, INPUT_API_URL, INPUT_PROFILE,
INPUT_ARTEFACTS, INPUT_CONNECTION, INPUT_COLLECTION_ROLE, INPUT_COLLECTION_PRIVILEGES, INPUT_DATA_DIR, INPUT_CONFIG_DIRS,
INPUT_FAIL_ON, INPUT_ALLOW_PARTIAL, INPUT_SCOPE, INPUT_SCOPE_BINDING, INPUT_ACCEPTED_SCOPE_REF, INPUT_IDENTITY_KEY,
INPUT_REPORT, INPUT_FEEDBACK, INPUT_ALLOW_OVERAGE, INPUT_REQUIREMENTS, INPUT_COMPILE_REQUIREMENTS, INPUT_FRESH_CHECK,
INPUT_OUTPUT, INPUT_DECLARATION), with
GITHUB_STEP_SUMMARY, GITHUB_OUTPUT and RUNNER_TEMP, and (serve-019) GITHUB_WORKSPACE, GITHUB_REPOSITORY and GITHUB_SHA
for `requirements_upload`. Issue #1953: run from the source tree as `python3 -m action.entry --mode local --artefacts DIR
--profile P [--fail-on ...] [--out FILE]`, each `--<input> VALUE` sets its INPUT_* name (`--out` is INPUT_OUTPUT) before
any input is read; an unknown flag is `bad_input` naming its INPUT_ form, and the API key, the connection and the
identity key are never read from a flag. Before anything else is printed,
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
  `feedback` is separately off by default. One deliberate JSON object or workflow-written file path sends one note
  only in api mode, after the primary file, outputs and summary. The actual server check id overrides the note's id.
  Its bounded, single-attempt request adds only a validated receipt or a known typed outcome to the summary; no note
  text, path, server reason or exception message is displayed. A feedback fault never changes the check result.
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
Issue #3168: every lint run says LINT_PREFLIGHT (a pre-flight, no check ran, remove `mode: lint`) as the job
summary's first line and one notice, and on a pull request as the one Assure comment.
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
`unauthenticated` exits 2, red, as DD-073's table puts auth and key failures (serve-016, REFUTATION-028 F5); so does
`key_expired` (issue #1262).
`allow-partial` is still accepted and changes no exit (serve-016). Every failure writes the failure envelope at the output path, its
summary and one `::error` line. The summary names a check only when the check reached the server: the server's check id
is kept in `detail.check_id` (from its failure envelope, or from a verdict that came back and then could not be used);
a refusal the API answered says which request it refused (`detail.answered`, set by the client): the profile list
(`GET /v1/profiles`, before anything is collected: nothing was sent), the upload (the files were sent and not kept) or
a poll (the check was sent; the failure file carries the id from the 202); a refusal in the runner reads "No check was
sent." (`serve.render.check_line`). The key, the connection, its password and the collector's raw output are never printed,
and customer text reaches stdout only escaped as workflow-command data.

Before anything is checked or sent, `action.withhold` withholds every configuration comment and every string literal in
the policy expressions but a `current_setting(` setting name (issue #2551), in every mode and for a connection or an artefacts directory alike (the customer's directory is
never changed); the counts are printed and added to the job summary. First, `action.withhold.apply` checks that the
collector's REDACTION-MANIFEST.json (read beside raw/, never uploaded) binds its sidecar to the bytes as collected
(refutation 005, WH-4). When the collector's sidecar records the session facts (the collector this Action ships
does), the job summary states them in two plain lines: whether the collection session was read-only, and TLS to the
server as the server reported it (`serve.markers.session_lines`). In api mode the verdict's shape is checked before it
is rendered: a malformed verdict is `api_error` (exit 3), with the failure file and the step outputs written.

Issue #1186 part 2: on a `postgresql-observed-baseline` verdict (api and local mode alike), after the verdict file is
written, the Action drafts a declaration from the bundle it already collected and withheld in the runner
(`draft_proposal`: raw/catalog_snapshot.json and the server major in raw/COLLECTION-SIDECAR.json) and writes two files
beside the verdict file: assure-declaration-proposal.json (the proposal record, `assure.declare_proposal.propose`) and
assure-requirements-draft.md (`requirements_draft`), with its typed companion assure-requirements-typed.json
(`typed_companion`; in api mode `typed_requirements` sends each unchanged drafted sentence as its typed row). The job summary adds one short section naming the leaves proposed,
the keys to confirm and the rows that need intent (`proposal_markdown`). Nothing new is sent to the API: the drafter
reads only the withheld bytes, so the proposal holds no literal the withholding pass replaced. With no snapshot, no
readable server major, or a major outside 14..18, nothing is drafted and nothing is said; a write fault is one
`::warning`. The verdict file and the exit never change; the one output it adds is `requirements-draft`, the draft's
path, which action.yml's next step uploads with `continue-on-error`, so a failed upload leaves the exit as it was. The
drafter is imported only there (`_proposal_module`): action/declare_proposal.py in the public tree,
assure/declare_proposal.py in this checkout.

Issue #2435: in api mode, with a PostgreSQL connection and profile `postgresql-declared-model`, the Action collects as
for the observed baseline and places the checkout's `.assure/postgresql-declared-model.json`, else
`.assure/declaration.json` (issue #2927; under GITHUB_WORKSPACE; a link, a
linked `.assure/`, a file that is not regular or cannot be read is `bad_input`) in the collector's raw/ as
raw/declaration.json (`checkout_declaration`, `action.collect._gather` `declare`), before the bundle limits and the one
withholding pass, so its `declared_predicate` literals are numbered with the snapshot's. With no such file it drafts
one from the collected snapshot before that pass (`draft_proposal`; the draft holds the customer's own literals, so the
merged draft reads as the draft did), checks on it, writes the proposal record (assure-declaration-proposal.json)
beside the verdict file and proposes it in Assure's own pull request (`action.declaration_draft.propose`, as for
python-auth): the run says `declaration=unaccepted-draft`. When nothing can be drafted the missing file is refused as
before. On a pull request, a checkout declaration not yet on the base branch bounds the run the same way. The
`declaration` input stays refused with a PostgreSQL connection.

Issue #2189: on a pull_request event with GITHUB_TOKEN set, after the job summary is written, the verdict is also
posted as one pull request comment (`post_pr_comment`, the body `serve.render.pr_comment_markdown`, decided from the
summary's own red findings), found again by its marker and updated in place on each later run. A 403 (the job's token
lacks `pull-requests: write`) is one `::notice` naming the line to add; any other GitHub refusal is one `::warning`; the
verdict file, the outputs and the exit never change.

This module imports, at its top, the standard library and modules that never import the engine: `action.client`,
`action.declaration_draft` (python-auth's declaration drafted and proposed in Assure's own pull request through
`action.client.GitHub` with the workflow token GITHUB_TOKEN, never printed; serve-102 r2),
`action.repository_manifest` (python-auth's raw/REPOSITORY.json, serve-099), `action.withhold`, `serve` (flags), `serve.bundle`, `serve.markers`, `serve.outcomes` and `serve.render`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from action import client as client_mod, declaration_draft, http_identity, repository_manifest, withhold  # noqa: E402
from action.client import CHECK_ID_RE, DEFAULT_URL, FEEDBACK_BODY_BYTES, FEEDBACK_LIMITS, LINT_SCHEMA, VERDICT_SCHEMA, Client, GitHub, allow_list, canonical_fail_on  # noqa: E402
from serve import FLAGS, bundle, is_development, markers, proof_tree, render  # noqa: E402
from serve.outcomes import OUTCOMES, Refusal, malformation  # noqa: E402

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
# Issue #397: the lines the Action prints, exported so docs/customer/README-ACTION.md ("Lines the Action prints") can
# show each with its placeholders and the docs test can render them; each `%(name)s` is the README's `<name>`.
NOTICE_LINE = '::notice title=Assure::%(count)d name(s) not read by profile %(profile)s: %(names)s'
LINT_LINE = 'Assure: lint: %(reading)s; %(findings)d finding(s); nothing was charged; policy exit %(exit)d; %(output)s'
WITHHELD_LINE = 'Assure: %(withheld)s'
# Issue #1960: the order each mode prints the lines above in, each only when its condition holds; README-ACTION.md
# lists the same order under its table and tests/serving/test_issue_1960_accept.py pins it against a run in each mode.
ORDER = {'api': ('WITHHELD_LINE', 'NOTICE_LINE'),
         'local': ('WITHHELD_LINE', 'NOTICE_LINE'),
         'lint': ('WITHHELD_LINE', 'NOTICE_LINE', 'LINT_LINE')}
# issue #1263 (GitHub OIDC sign-in): with no api-key the Action signs in with the job's GitHub OIDC token; with neither,
# it stops before anything is collected or sent and names the one workflow line to add
NO_CREDENTIAL_REASON = ('Assure needs this workflow\'s GitHub identity or an api-key. Add `permissions: id-token: write` '
                        'to the job that runs Assure (keep `contents: read` beside it), or pass api-key from a secret.')
OIDC_LINE = 'Assure: signed in with this workflow\'s GitHub identity as account %s; the key for this run expires at %s'
MAX_LINT_LINES = 50
# Issue #3168: a workflow left on `mode: lint` ran on every pull request for days and never checked anything, and a
# clean lint exits 0. Every lint run says so first: the job summary's first line, one notice and, on a pull request,
# the one Assure comment (`post_pr_comment` with `body`).
LINT_PREFLIGHT = ('This was a pre-flight: no check ran. '
                  'Remove `mode: lint` from your workflow to check every pull request.')
# Issue #1186 part 2: on the observed PostgreSQL profile the Action drafts a declaration beside the verdict file,
# from the catalog snapshot it already collected and withheld (`draft_proposal`). serve/envelope.py PROPOSAL_FILE
# names the same file.
PROPOSAL_PROFILE = 'postgresql-observed-baseline'
DECLARED_PROFILE = 'postgresql-declared-model'      # issue #2435: run on a connection with the checkout's declaration
DECLARED_TITLE = declaration_draft.TITLE        # issue #2927: one proposal pull request, one title for every profile
DECLARED_CHECKOUT_PATH = '.assure/postgresql-declared-model.json'   # issue #2927: PostgreSQL's draft, at its own path
DECLARED_SOURCE = 'the collected catalog snapshot'
PROPOSAL_FILE = 'assure-declaration-proposal.json'
REQUIREMENTS_DRAFT_FILE = 'assure-requirements-draft.md'
# Issue #1186 (coordination 7588): the draft's typed companion, written beside it; read beside the requirements file
# that is sent (`typed_requirements`)
REQUIREMENTS_TYPED_FILE = 'assure-requirements-typed.json'
# Issue #2651: the check's proof tree, written beside the verdict for every account (`write_proof_tree`); the pull
# request comment links the API's page for it only when the verdict carries a `tree_url` (Premium and above)
PROOF_TREE_HTML = 'assure-proof-tree.html'
PROOF_TREE_JSON = 'assure-proof-tree.json'
MAX_TYPED_BYTES = 256 * 1024
PROPOSAL_SNAPSHOT = 'raw/catalog_snapshot.json'
PROPOSAL_SIDECAR = 'raw/COLLECTION-SIDECAR.json'
PROPOSAL_MAJOR_SOURCE = 'COLLECTION-SIDECAR.json#/server/server_version_num'
PROPOSAL_LINE = ('Assure drafted a declaration from your database: %(leaves)d leaves proposed, '
                 '%(confirm)d to confirm — commit it as .assure/declaration.json (with a connection; '
                 'raw/declaration.json in an artefacts directory) and run postgresql-declared-model '
                 'to decide %(rows)d rows that need intent.')
PROPOSAL_FILES_LINE = ('The draft is %(proposal)s (commit its `declaration` object after you confirm each key its '
                       '`confirm` list names), with %(draft)s beside it. A proposal changes no reading.')
# Issue #2934: once Assure's pull request is open; the observed run reads the merged file (issue #2928 declared_reading)
PROPOSED_LINE = ('Assure drafted a declaration from your database: %(leaves)d leaves proposed, %(confirm)d to confirm '
                 '— merge Assure\'s proposal pull request; the next check then also reads postgresql-declared-model '
                 'beside this reading, to decide %(rows)d rows that need intent.')
PROPOSAL_NO_READING = ' A proposal changes no reading.'    # PROPOSAL_FILES_LINE's end; issue #2934: dropped once
# the pull request exists
PROPOSAL_UNCHANGED = ' The verdict, its file and the exit never change; the pull request adds no output.'
# Issue #2934: the observed profile's pull request body leads with what merging it decides, never "bounded by"
OBSERVED_LEAD = ('Assure drafted `%(rel)s` from %(source)s. Merging it commits the declaration; the next check then '
                 'also reads `postgresql-declared-model` beside this reading, to decide the %(rows)d rows that need '
                 'intent.')
# issue #2892: action.yml's upload-artifact step ships the draft under this name; the section links the run's artifacts
REQUIREMENTS_DRAFT_ARTIFACT = 'assure-requirements-draft'
PROPOSAL_ARTIFACT_LINE = 'This run uploads %(draft)s as its %(artifact)s artifact: <%(url)s>.'
_RUN_SERVER = re.compile(r'https?://[A-Za-z0-9.-]{1,253}(?::[0-9]{1,5})?')
_RUN_REPOSITORY = re.compile(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}')
_RUN_ID = re.compile(r'[0-9]{1,20}')
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


def _notice_line(ignored, profile):
    """NOTICE_LINE for the names the profile does not read: the first MAX_NOTICE_NAMES, then ` and N more`."""
    names = ignored[:MAX_NOTICE_NAMES]
    more = len(ignored) - len(names)
    line = NOTICE_LINE % {'count': len(ignored), 'profile': profile,
                          'names': ', '.join(names) + ((' and %d more' % more) if more else '')}
    head, sep, data = line.partition('title=Assure::')       # the data part escaped and capped as one, as before
    return head + sep + _cmd_data(data)


def _mask(value):
    """One `::add-mask::` line; the value is escaped as workflow-command data, never truncated."""
    return '::add-mask::' + str(value).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def scrub_process_env(environ):
    """Cut `environ` (os.environ when run as a script) to KEEP_ENV, so no child inherits a secret."""
    for k in list(environ):
        if k not in KEEP_ENV:
            del environ[k]


# issue #1953: the inputs a command-line flag may set (`--fail-on` is INPUT_FAIL_ON; `--out` is `--output`). A secret
# on a command line is visible to every process on the host, so the three secret inputs are read from the environment only.
FLAG_INPUTS = ('MODE', 'API_URL', 'PROFILE', 'ARTEFACTS', 'DECLARATION', 'COLLECTION_ROLE', 'COLLECTION_PRIVILEGES',
               'DATA_DIR', 'CONFIG_DIRS', 'FAIL_ON', 'ALLOW_PARTIAL', 'SCOPE', 'SCOPE_BINDING', 'ACCEPTED_SCOPE_REF',
               'REPORT', 'FEEDBACK', 'ALLOW_OVERAGE', 'REQUIREMENTS', 'COMPILE_REQUIREMENTS', 'FRESH_CHECK', 'OUTPUT')
SECRET_INPUTS = ('API_KEY', 'CONNECTION', 'IDENTITY_KEY')


def argv_inputs(argv):
    """issue #1953: `--<input> VALUE` or `--<input>=VALUE` as {INPUT_<INPUT>: VALUE}, or (inputs read so far,
    `bad_input` Refusal naming the INPUT_ form) for an unknown flag, a secret flag or a flag with no value."""
    inputs, args = {}, list(argv)
    while args:
        arg = str(args.pop(0))
        flag, eq, value = arg.partition('=')
        name = flag[2:].upper().replace('-', '_') if flag.startswith('--') else ''
        name = 'OUTPUT' if name == 'OUT' else name
        if name in SECRET_INPUTS:
            return inputs, Refusal('bad_input', '--%s is not a flag: set INPUT_%s in the environment'
                                   % (flag[2:].lower(), name))
        if name not in FLAG_INPUTS:
            shown = 'INPUT_%s' % name if name and len(name) <= 64 and name.replace('_', '').isalnum() else 'an INPUT_ name'
            return inputs, Refusal('bad_input', 'unknown flag: %s names no input (%s)'
                                   % (_cmd_data(flag[:66]) if name else 'an argument', shown))
        if not eq:
            if not args:
                return inputs, Refusal('bad_input', '%s needs a value (INPUT_%s)' % (flag, name))
            value = str(args.pop(0))
        inputs['INPUT_' + name] = value
    return inputs, None


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


NO_RAW_REASON = 'no raw/ directory under the artefacts path'


def _with_layout(e, allow, art):
    """Issue #274: the no-raw/ refusal carries what the renderer needs to name the expected layout per profile: the
    profile id, the listing's required raw/ paths, and whether manifest.json sits where raw/ was looked for (an endpoint
    manifest given with the wrong profile, or with a scope-binding file). The reason text is unchanged."""
    if e.outcome != 'bad_input' or e.reason != NO_RAW_REASON:
        return e
    try:
        manifest = stat.S_ISREG(os.lstat(Path(art) / 'manifest.json').st_mode)
    except OSError:
        manifest = False
    return Refusal(e.outcome, e.reason, profile=allow.id, layout=[r.path for r in allow.required], manifest=manifest,
                   **e.detail)


def failure_envelope(check_id, refusal, charged=False):
    """The failure envelope (`assure.serve.failure/v1`), the same object `serve.envelope.failure` builds. Its `charged`
    (issue #1103) is the one the server's failure envelope stated, else `charged`: False when nothing reached the
    server, None when a check did and the Action could not read its charge."""
    doc = {'schema': FAILURE_SCHEMA, 'check_id': check_id}
    doc.update(refusal.to_dict())
    stated = doc['detail'].pop('server_charged', None)
    doc['charged'] = stated if isinstance(stated, bool) else charged
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
    if is_development(v):                              # serve-105: never rendered as a served verdict
        raise bad('it is a development verdict, which the API never serves')
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


PR_EVENTS = ('pull_request',)              # the event the docs name for the comment
PR_COMMENT_NOTICE = ('the pull request comment was not posted: GitHub answered 403. To have it posted, add '
                     '`pull-requests: write` under the job\'s `permissions:` (keep `contents: read` beside it)')
PR_COMMENT_PAGES = 10                       # 100 comments a page: the marker is looked for in the first 1000


def _pull_number(env):
    """The pull request number from the event file (GITHUB_EVENT_PATH, bounded), or None."""
    path = str(env.get('GITHUB_EVENT_PATH') or '').strip()
    if not path:
        return None
    try:
        doc = bundle.parse_json(bundle._read_capped(Path(path), MAX_EVENT_BYTES),
                                bundle.Limits(body_bytes=MAX_EVENT_BYTES, json_depth=128))
        n = ((doc.get('pull_request') or {}).get('number') or doc.get('number')) if isinstance(doc, dict) else None
    except (OSError, Refusal, AttributeError):
        return None
    return n if type(n) is int and n > 0 else None


def post_pr_comment(env, verdict, github, tree=None, tree_bases=(), body=None):
    """Issue #2189: on a pull_request event, post `render.pr_comment_markdown(verdict)` as one comment on the pull
    request, or update in place the comment that carries `render.PR_COMMENT_MARKER` (the first 1000 comments are
    looked through). Returns 'posted', 'updated', or None when the event is not a pull request or names no number.
    A GitHub answer that is not 2xx is `api_error` naming its status, with `detail.status` (a 403 is the missing
    `pull-requests: write`; `main` prints it as one notice). Issue #2651: `tree` ({url, proven, total}) adds the
    footer's proof tree line when its url is the verdict's `tree_url` on one of `tree_bases` (`render.pr_tree_line`).
    Issue #3168: `body` (a `mode: lint` run's LINT_PREFLIGHT) is posted in place of the verdict's comment, under the
    same marker, so the one Assure comment says no check ran."""
    if env.get('GITHUB_EVENT_NAME') not in PR_EVENTS:
        return None
    repo, number = str(env.get('GITHUB_REPOSITORY') or '').strip(), _pull_number(env)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or number is None:
        return None
    if body is not None:
        body = '%s\n%s\n' % (render.PR_COMMENT_MARKER, body)
    else:
        body = render.pr_comment_markdown(verdict, commit=_head_commit(env), repository=repo, tree=tree,
                                          tree_bases=tree_bases)
    root = '/repos/%s/issues' % repo

    def ok(status, what):
        if not 200 <= status < 300:
            raise Refusal('api_error', 'the pull request comment could not be %s (GitHub answered %d)' % (what, status),
                          status=status)
    for page in range(1, PR_COMMENT_PAGES + 1):
        status, found = github.call('GET', '%s/%d/comments?per_page=100&page=%d' % (root, number, page))
        ok(status, 'read')
        found = found if isinstance(found, list) else []
        for c in found:
            if isinstance(c, dict) and type(c.get('id')) is int and str(c.get('body') or '').startswith(
                    render.PR_COMMENT_MARKER):
                ok(github.call('PATCH', '%s/comments/%d' % (root, c['id']), {'body': body})[0], 'updated')
                return 'updated'
        if len(found) < 100:
            break
    ok(github.call('POST', '%s/%d/comments' % (root, number), {'body': body})[0], 'posted')
    return 'posted'


def write_proof_tree(verdict, directory, goals=(), text=None, repository=None, commit=None, **layer2):
    """Issue #2651: the check's proof tree (`serve.proof_tree.build` over the verdict, the goals sent and the
    requirements text as read) written beside the verdict as PROOF_TREE_JSON and PROOF_TREE_HTML, for every account;
    returns the tree. The repository and commit make the tree's blob links only when they validate. `layer2` (tier,
    model, repository_files, budget, remodel_quote_usd, remodel_parts) is passed to `build` as given: the formal-model
    layer, absent while the caller names no tier."""
    tree = proof_tree.build(verdict, goals=list(goals or ()) or None, requirements_text=text,
                            proposal=_proposal_module() if goals else None, repository=repository, commit=commit,
                            **layer2)
    _write_file(Path(directory) / PROOF_TREE_JSON, (json.dumps(tree, indent=2, sort_keys=True, ensure_ascii=False)
                                                    + '\n').encode('utf-8'))
    _write_file(Path(directory) / PROOF_TREE_HTML, proof_tree.render_html(tree).encode('utf-8'))
    return tree


def pr_tree(verdict, tree):
    """{url, proven, total} for the comment's proof tree line: the verdict's own `tree_url` (the API adds it on
    Premium and above; a free account's verdict carries none, so no line) and the tree's counts; None without either."""
    url = verdict.get('tree_url') if isinstance(verdict, dict) else None
    if not isinstance(url, str) or not isinstance(tree, dict):
        return None
    x, y = proof_tree.proven(tree)
    return {'url': url, 'proven': x, 'total': y}


def requirements_upload(env, cwd, goals=None, source=None):
    """serve-019 (coordination 2136): ({requirements?, repository?, commit?, provenance?}, notice or None). The text is
    the `requirements` input's file (relative to the working directory): one that is missing, unreadable, a link,
    not a regular file, beyond the bounds or not UTF-8 is `bad_input` before anything is collected or sent. The input
    `none` (NONE_SENTINEL) sends no text and prints no notice; a file named `none` is then reached as `./none`. Issue
    #2174: with the input empty no text is sent and no notice is printed, whatever the repository root holds; the
    upload is opt-in (name the file, e.g. `requirements.md`). GITHUB_REPOSITORY and the head commit (`_head_commit`)
    go as repository and commit with `provenance: runner`; the API reads them as metadata, never as authority.
    Issue #1186: a sent file with the draft's typed companion beside it goes through `typed_requirements`, and the
    notice then names the lines changed since they were compiled, if any; `goals`, a list when given, receives the
    goals sent, and `source`, a list when given, the requirements text as read, before any goal was expanded (issue
    #2651: the proof tree's goal lines). With goals sent, `requirement_goals` carries their goal map
    (`proof_tree.goal_map`: each goal's sentence, its line in the text as read and its children's ids and plain
    sentences), which the API keeps with the check for its proof tree."""
    out, notice, sent, text = {}, None, [], None
    named = _plain(env, 'INPUT_REQUIREMENTS')
    if named == NONE_SENTINEL:                       # REFUTATION-034-R2 N5: send no text, print no notice
        pass
    elif named:
        path = Path(named) if Path(named).is_absolute() else Path(cwd or os.getcwd()) / named
        text = _read_requirements(path)
        out['requirements'], notice, sent = typed_requirements(text, path.parent)
    if sent and 'requirements' in out:       # issue #2651: the goal map, so the served proof tree shows the goals
        try:                                 # a map beyond the bounds is not sent; the check runs as before
            out['requirement_goals'] = bundle.check_goals(proof_tree.goal_map(sent, text), out['requirements'])
        except Refusal:
            pass
    repo, sha = str(env.get('GITHUB_REPOSITORY') or '').strip(), _head_commit(env)
    if repo and sha:
        out.update(bundle.upload_fields({'repository': repo, 'commit': sha, 'provenance': 'runner'}))
    if goals is not None:
        goals[:] = sent
    if source is not None:
        source[:] = [text] if isinstance(text, str) else []
    return out, notice


def typed_requirements(text, directory):
    """Issue #1186 (coordination 7588): (text, sentence or None, goals). `text` with each drafted goal sentence that
    REQUIREMENTS_TYPED_FILE in `directory` pins by sha256 sent as its children's typed rows
    (`declare_proposal.typed_text`); an edited or new line is sent as written, and the sentence names the lines changed
    since they were compiled (`declare_proposal.changed_sentence`); `goals` are the goals sent, for the summary's
    roll-up (`goal_rollup_markdown`). A companion that is absent, a link, not a regular file, larger than
    MAX_TYPED_BYTES, not JSON, or whose goals do not check is ignored, and so is a result beyond the requirements
    bounds: `text` is sent unchanged."""
    path = Path(directory) / REQUIREMENTS_TYPED_FILE
    try:
        if os.path.islink(path) or not path.is_file():
            return text, None, []
        companion = bundle.parse_json(bundle._read_capped(path, MAX_TYPED_BYTES),
                                      bundle.Limits(body_bytes=MAX_TYPED_BYTES, json_depth=32))
        dp = _proposal_module()
        typed, changed, goals = dp.typed_text(text, companion)
        return bundle.check_requirements(typed), dp.changed_sentence(changed), goals
    except (OSError, Refusal, ValueError, TypeError, AttributeError, KeyError):
        return text, None, []


def goal_rollup_markdown(goals, verdict):
    """Issue #1186: the job summary's roll-up of the goals sent (`typed_requirements`), one line per goal from its
    children's requirement states in the verdict (`declare_proposal.rollup`); '' when no goal was sent or the verdict
    carries no requirement rows."""
    rows = render.requirement_rows(verdict)
    if not goals or rows is None:
        return ''
    states = {r.get('id'): r.get('state') for r in rows}
    dp = _proposal_module()
    return '\n### Requirement goals\n\n' + ''.join('- %s %s\n' % (render.esc(goal['english']),
                                                                       render.esc(dp.rollup(goal, states)))
                                                    for goal in goals)


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


def _inputs(env, conn, conn_error, collect, collector_dir=None, cwd=None, is_mysql=False):
    profile = _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE
    artefacts = _plain(env, 'INPUT_ARTEFACTS')
    declaration_text = _plain(env, 'INPUT_DECLARATION')
    has_conn = bool(str(env.get('INPUT_CONNECTION') or '').strip())
    # serve-102 (DD-156 item 3): python-auth with neither reads the checkout itself, in one step
    checkout = profile == declaration_draft.PROFILE and not artefacts and not has_conn
    if bool(artefacts) == has_conn and not checkout:
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
    # MySQL connection: profile must be mysql-declared-model, declaration required, PG-only inputs refused.
    # Exit 3 (could not look): nothing was collected or checked, the inputs are wrong for this connection type.
    if is_mysql:
        if profile != 'mysql-declared-model':
            raise Refusal('bad_input', 'a mysql:// connection requires profile mysql-declared-model', exit_code=3)
        if not declaration_text:
            raise Refusal('bad_input', 'declaration is required with a mysql connection', exit_code=3)
        if _plain(env, 'INPUT_COLLECTION_PRIVILEGES'):
            priv = _plain(env, 'INPUT_COLLECTION_PRIVILEGES')
            if priv and {x.strip() for x in priv.split(',') if x.strip()} != {'pg_read_all_settings', 'pg_read_all_stats'}:  # not the default, in any order
                raise Refusal('bad_input', 'collection-privileges applies only to PostgreSQL connections', exit_code=3)
        if data_dir_text:
            raise Refusal('bad_input', 'data-dir applies only to PostgreSQL connections', exit_code=3)
        if str(config_dirs_text or '').strip(' \t\r\n:'):
            raise Refusal('bad_input', 'config-dirs applies only to PostgreSQL connections', exit_code=3)
    # PostgreSQL or artefacts with a declaration: refused
    if not is_mysql and declaration_text:
        if artefacts and declaration_text:
            raise Refusal('bad_input', 'declaration applies only with a mysql connection', exit_code=3)
        if has_conn and declaration_text:
            raise Refusal('bad_input', 'declaration applies only with a mysql connection', exit_code=3)
    if conn_error is not None:
        raise conn_error
    out = {'profile': profile, 'fail_on': fail_on, 'artefacts': artefacts or None, 'allow_partial': allow_partial,
           'scope': _json_input(env, 'INPUT_SCOPE', 'scope_missing', None, cwd),
           'scope_binding': _json_input(env, 'INPUT_SCOPE_BINDING', 'scope_binding', 'scope_binding', cwd),
           'accepted_scope_ref': None}
    if is_mysql:
        declaration_path = Path(declaration_text) if Path(declaration_text).is_absolute() \
            else Path(cwd or os.getcwd()) / declaration_text
        collect.check_declaration(declaration_path)
        role_text = _plain(env, 'INPUT_COLLECTION_ROLE')
        out['role'] = role_text.strip() if role_text.strip() else (conn.user if conn is not None else None)
        if not out['role']:
            raise Refusal('bad_input', 'collection-role is empty and the connection names no user', exit_code=3)
        if len(out['role']) > 80 or out['role'].startswith('-') or any(ord(c) < 32 or ord(c) == 127 for c in out['role']):
            raise Refusal('bad_input', 'collection-role is not a usable MySQL user name', exit_code=3)
        out['declaration'] = str(declaration_path)
        return out
    if artefacts:
        if data_dir_text:
            raise Refusal('bad_input', 'data-dir applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        if str(config_dirs_text or '').strip(' \t\r\n:'):
            raise Refusal('bad_input', 'config-dirs applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        return out
    if checkout:
        out['checkout'] = True
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
    """serve-014, DD-103: the `report` input: unset or '' is False in every mode (issue #2174: the report sends the
    verdict record to a third-party model, so it is opt-in); 'false' or '0' is False; 'true' or '1' is True
    (case-insensitive); else bad_input."""
    v = (text or '').strip().lower()
    if v in ('', 'false', '0'):
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


def parse_compile_requirements(text):
    """Issue #2252: the `compile-requirements` input, read as `fresh-check` is, but on by default: true (the default)
    lets the server read requirement lines outside the grammar with Claude Haiku; false sends `compile_requirements:
    false` with the requirements text, and the lines are matched exactly."""
    v = (text or '').strip().lower()
    if v in ('', 'true', '1'):
        return True
    if v in ('false', '0'):
        return False
    raise Refusal('bad_input', 'compile-requirements must be true or false')


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


def _proposal_module():
    """assure/declare_proposal.py: shipped byte for byte as action/declare_proposal.py in the public tree (build_dist
    PUBLIC_DECLARATION_ASSETS); in this checkout it is the private package's own module (build_dist LOCAL_ONLY_MODULES:
    the closure never follows it). Standard library only either way."""
    try:
        from action import declare_proposal
    except ImportError:
        import assure.declare_proposal as declare_proposal
    return declare_proposal


def _declaration_leaves(node):
    """How many leaves `node` holds: a scalar, an empty list or an empty object is one."""
    if isinstance(node, dict):
        return sum(_declaration_leaves(v) for v in node.values()) if node else 1
    if isinstance(node, list):
        return sum(_declaration_leaves(v) for v in node) if node else 1
    return 1


def draft_proposal(files):
    """Issue #1186 part 2: (proposal record, draft requirements.md text, drafter notes) drafted from `files`, the bundle as collected
    and withheld in the runner (`action.withhold.apply` has already replaced every SQL literal in the snapshot's policy
    expressions but a `current_setting(` setting name, so the proposal holds only what the upload holds); None when there is no catalog snapshot or the
    collector's sidecar names no server major the drafter reads. Nothing here is sent anywhere."""
    snap, side = files.get(PROPOSAL_SNAPSHOT), files.get(PROPOSAL_SIDECAR)
    if snap is None or side is None:
        return None
    try:
        snapshot = json.loads(bytes(snap).decode('utf-8'))
        major = int(str(json.loads(bytes(side).decode('utf-8'))['server']['server_version_num'])) // 10000
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None
    dp = _proposal_module()
    try:
        record, notes = dp.propose_with_notes(snapshot, major=major, major_source=PROPOSAL_MAJOR_SOURCE)
    except ValueError:                       # a major outside 14..18, or a snapshot that is not an object
        return None
    return record, dp.requirements_draft(record, notes), notes


def checkout_declaration(top, cap):
    """Issue #2435: the bytes of the checkout's declaration under `top`, at most `cap` + 1 of them (the bundle limits
    refuse more); None when it or `.assure/` is absent. Issue #2927: `.assure/postgresql-declared-model.json` is read
    first and `.assure/declaration.json` (where a #2435 proposal was merged) second."""
    got = checkout_declaration_at(top, cap)
    return None if got is None else got[1]


def _same_json(data, value):
    """Issue #3153: whether `data` (committed bytes) parses as UTF-8 JSON equal to `value`; False for anything else."""
    try:
        return json.loads(bytes(data).decode('utf-8')) == value
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False


def checkout_declaration_at(top, cap, skip_links=False):
    """(rel, bytes) of the first of DECLARED_CHECKOUT_PATH and `.assure/declaration.json` present under `top`; None
    when neither is. `bad_input` for a link, a linked `.assure/`, a file that is not regular, or one that cannot be
    read: a present declaration is never drafted over. Issue #3153 (#2249): with `skip_links` (the observed profile's
    intent flow) a link at either path is not committed intent and is passed over, as if absent."""
    for rel in (DECLARED_CHECKOUT_PATH, declaration_draft.CHECKOUT_PATH):
        if skip_links and os.path.islink(top / rel):
            continue
        try:
            data = _checkout_file(top, rel, cap)
        except Refusal:
            if rel == DECLARED_CHECKOUT_PATH and not stat.S_ISDIR(os.lstat(top / '.assure').st_mode):
                continue                             # a linked `.assure/` is refused as #2435 named it, below
            raise
        if data is not None:
            return rel, data
    return None


def _checkout_file(top, rel, cap):
    parent = top / Path(rel).parent
    target = top / rel
    for p, kind in ((parent, stat.S_ISDIR), (target, stat.S_ISREG)):
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            return None
        except OSError:
            raise Refusal('bad_input', '%s could not be read' % rel) from None
        if not kind(st.st_mode):                     # lstat: a link is neither a directory nor a regular file
            raise Refusal('bad_input', '%s is a link or not a regular file' % rel)
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as f:
            return f.read(cap + 1)
    except OSError:
        raise Refusal('bad_input', '%s could not be read' % rel) from None


# issue #2928: the declared profile an observed profile's run also checks when intent is committed in the checkout
OBSERVED_DECLARED = {'postgresql-observed-baseline': DECLARED_PROFILE}
DECIDED = ('holds', 'fails', 'deviates')
BOTH_LINE = ('decided %(n)d of %(m)d rows across both readings (%(observed)s %(a)d of %(b)d; %(declared)s %(c)d of '
             '%(d)d, with `%(intent)s`)')


# REFUTATION-r3 HIGH-1: the fail-on words the declared profile accepts (`serve.envelope.listed_fail_on_words` of its row;
# the public tree ships no profile row, so a test holds the two equal)
DECLARED_FAIL_ON = ('fails', 'representation', 'missing_method', 'missing_premise', 'not_evaluated', 'not_collected',
                    'unresolved-security', 'never')


def declared_fail_on(text):
    """The observed run's fail-on for the declared check: `never` alone as given, else only the words the declared
    profile accepts (an observed-only word such as `deviates` is dropped, never sent to be refused); None (the default,
    `fails`) when none is left or nothing was given. The declared reading's exit is informational either way."""
    if not isinstance(text, str):
        return None
    words = [w.strip().lower() for w in text.split(',') if w.strip()]
    if words == ['never']:
        return 'never'
    return ','.join(w for w in words if w in DECLARED_FAIL_ON and w != 'never') or None


def _decided(verdict):
    """{row id: decided} for the verdict's rows that carry an id; decided is holds, fails or deviates, and never a row
    the checker kept on a machine it reports refused (`render.kept_on_refused`: every surface reads it not observed)."""
    out = {}
    for row in verdict.get('rows') or ():
        if isinstance(row, dict) and isinstance(row.get('id'), str):
            out[row['id']] = out.get(row['id'], False) or (row.get('status') in DECIDED
                                                            and not render.kept_on_refused(verdict, row))
    return out


def both_readings_line(observed, declared, intent):
    """Issue #2928: the first line of a run that read committed intent; N counts ids decided in either verdict, M the
    union of ids, so N >= c."""
    o, d = _decided(observed), _decided(declared)
    union = set(o) | set(d)
    return BOTH_LINE % {'n': sum(1 for k in union if o.get(k) or d.get(k)), 'm': len(union),
                        'observed': _pid(observed), 'a': sum(o.values()), 'b': len(o),
                        'declared': _pid(declared), 'c': sum(d.values()), 'd': len(d), 'intent': intent}


def _pid(verdict):
    pid = verdict.get('profile')
    return pid if isinstance(pid, str) and re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}', pid) else 'an unnamed profile'


def demote_headings(md):
    """Each markdown heading one level deeper (`##` to `###`), no further."""
    return re.sub(r'(?m)^(#{1,5}) ', r'#\1 ', md)


def declared_markdown(declared, profile, intent, charged_two):
    """Issue #2928: the "Declared reading" section; a Refusal is "not measured (<reason>)", never a count."""
    head = '\n### Declared reading (%s, with `%s`)\n\n' % (profile, intent)
    if isinstance(declared, Refusal):
        return head + 'declared reading: not measured (%s).\n' % render.esc(declared.reason)
    note = ('This reading is informational: the verdict file, the outputs and the exit stay the observed reading\'s '
            'until you set `profile: %s`.' % profile)
    if charged_two:
        note += ' This run submitted two checks: two checks charged.'
    return head + note + '\n\n' + demote_headings(render.summary_markdown(declared))


def _raw_bounded(raw, name, cap):
    """`raw`/`name`'s bytes when it is a regular file of at most `cap` bytes, else None (the bundle refuses it)."""
    try:
        st = os.lstat(raw / name)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        return (raw / name).read_bytes()
    except OSError:
        return None


def proposal_counts(record, verdict):
    """{leaves, confirm, rows}: the proposed declaration's leaves (schema and the seven flags aside), the keys its
    `confirm` list names, and the verdict's rows with an id whose status is needs_intent."""
    decl = record.get('declaration') or {}
    leaves = sum(_declaration_leaves(v) for k, v in decl.items() if k != 'schema' and k not in FLAGS)
    rows = sum(1 for r in verdict.get('rows') or () if isinstance(r, dict) and r.get('id') is not None
               and r.get('status') == 'needs_intent')
    return {'leaves': leaves, 'confirm': len(record.get('confirm') or ()), 'rows': rows}


def run_artifacts_url(env):
    """Issue #2892: `<server>/<repo>/actions/runs/<run id>#artifacts` when GITHUB_SERVER_URL, GITHUB_REPOSITORY and
    GITHUB_RUN_ID each look like that URL part (an http(s) origin, owner/name, digits); None otherwise."""
    server, repo, run_id = (str(env.get(k) or '').strip() for k in ('GITHUB_SERVER_URL', 'GITHUB_REPOSITORY',
                                                                     'GITHUB_RUN_ID'))
    if not (_RUN_SERVER.fullmatch(server.rstrip('/')) and _RUN_REPOSITORY.fullmatch(repo) and _RUN_ID.fullmatch(run_id)):
        return None
    return '%s/%s/actions/runs/%s#artifacts' % (server.rstrip('/'), repo, run_id)


def proposal_markdown(counts, artifacts_url=None, proposed=False):
    """The job summary's short section for a written proposal: fixed words and three counts, no customer text; with
    `artifacts_url` (`run_artifacts_url`), one more line naming the run artifact the draft is uploaded as; with
    `proposed` (issue #2934: the pull request exists) it no longer says a proposal changes no reading."""
    files = PROPOSAL_FILES_LINE % {'proposal': PROPOSAL_FILE, 'draft': REQUIREMENTS_DRAFT_FILE}
    if proposed:
        files = files[:-len(PROPOSAL_NO_READING)] + PROPOSAL_UNCHANGED
    if artifacts_url is not None:
        files += '\n\n' + PROPOSAL_ARTIFACT_LINE % {'draft': REQUIREMENTS_DRAFT_FILE,
                                                    'artifact': REQUIREMENTS_DRAFT_ARTIFACT, 'url': artifacts_url}
    return '\n### Declaration proposal\n\n%s %s\n' % ((PROPOSED_LINE if proposed else PROPOSAL_LINE) % counts, files)


def write_proposal(verdict, files, directory, say, artifacts_url=None, proposed=False):
    """On a postgresql-observed-baseline verdict: PROPOSAL_FILE and REQUIREMENTS_DRAFT_FILE written in `directory`
    (beside the verdict file) from `files`, and the summary section (`proposal_markdown`, with `artifacts_url`)
    returned; '' on any other profile, when nothing could be drafted, or when a file could not be written (one
    `::warning`, class name only). The verdict file and the exit never change; the caller adds the
    `requirements-draft` output only when a section came back (issue #2892)."""
    if not isinstance(verdict, dict) or verdict.get('profile') != PROPOSAL_PROFILE or not isinstance(files, dict):
        return ''
    try:
        drafted = draft_proposal(files)
        if drafted is None:
            return ''
        record, text, notes = drafted
        counts = proposal_counts(record, verdict)
        _write_file(directory / PROPOSAL_FILE,
                    (json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
        _write_file(directory / REQUIREMENTS_DRAFT_FILE, text.encode('utf-8'))
        snap = hashlib.sha256(bytes(files[PROPOSAL_SNAPSHOT])).hexdigest()
        companion = _proposal_module().typed_companion(record, text, PROPOSAL_SNAPSHOT + ' sha256:' + snap, notes)
        _write_file(directory / REQUIREMENTS_TYPED_FILE,
                    (json.dumps(companion, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
    except Exception as w:  # the class name only, never a value
        say('::warning title=Assure::%s' % _cmd_data('the declaration proposal could not be written (%s)'
                                                     % type(w).__name__))
        return ''
    return proposal_markdown(counts, artifacts_url, proposed)


def _scratch(env):
    temp_root = env.get('RUNNER_TEMP') or None
    if temp_root and not os.path.isdir(temp_root):
        temp_root = None
    return Path(tempfile.mkdtemp(prefix='assure-', dir=temp_root))


def _feedback_note(text, cwd, check_id, secrets_to_refuse=()):
    """Bounded JSON string or plain regular-file path; input values are never shown.

    Object/array/quoted/numeric/literal-looking inputs are JSON, including malformed JSON. A caller can name a file
    with such a name explicitly as ./name. Field validation remains the server's; only transport bounds live here.
    """
    try:
        raw_text = str(text)
        text = raw_text.strip()
        if len(raw_text.encode('utf-8')) > FEEDBACK_BODY_BYTES:
            raise Refusal('oversize_input', 'the feedback input exceeds its byte limit')
        inline = text[:1] in ('{', '[', '"', '-') or text[:1].isdigit() \
            or re.match(r'^(?:true|false|null|NaN|Infinity)(?:\b|$)', text) is not None
        if inline:
            data = raw_text.encode('utf-8')
        else:
            if _CONTROL.search(raw_text):
                raise Refusal('bad_input', 'the feedback input is invalid')
            path = Path(text) if Path(text).is_absolute() else Path(cwd) / text
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0))
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise Refusal('bad_input', 'the feedback input is invalid')
                chunks, remaining = [], FEEDBACK_BODY_BYTES + 1
                while remaining:
                    part = os.read(fd, remaining)
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                data = b''.join(chunks)
            finally:
                os.close(fd)
        note = bundle.parse_json(data, FEEDBACK_LIMITS)
        if not isinstance(note, dict):
            raise Refusal('bad_input', 'the feedback body must be one JSON object')

        def contains_secret(value):
            if isinstance(value, str):
                return any(secret in value for secret in secrets_to_refuse if secret)
            if isinstance(value, dict):
                return any(contains_secret(k) or contains_secret(v) for k, v in value.items())
            if isinstance(value, list):
                return any(contains_secret(v) for v in value)
            return False

        if contains_secret(note):
            raise Refusal('bad_input', 'the feedback input contains a known secret')
        note['check_id'] = check_id
        encoded = json.dumps(note, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(encoded) > FEEDBACK_BODY_BYTES:
            raise Refusal('oversize_input', 'the feedback body exceeds its byte limit')
        return note
    except Refusal as e:
        raise Refusal(e.outcome, 'the feedback input is invalid') from None
    except (OSError, ValueError, UnicodeError):
        raise Refusal('bad_input', 'the feedback input is invalid') from None


def main(env=None, *, root, argv=None, stdout=None, load_checker=None, pin_path=None, collector_dir=None, collector_sha256=_FROZEN,
         psql='psql', mysql='mysql', collect_timeout=None, check_timeout=60, limits=None, cwd=None, client_factory=None) -> int:
    """Run one check as the Action; return the exit code. `load_checker`, `pin_path`, `collector_dir`,
    `collector_sha256`, `psql`, `limits` and `client_factory(base_url, api_key) -> Client` are test seams; production
    passes none of them. `argv` (issue #1953): each `--<input> VALUE` sets its INPUT_* name over `env` before any
    input is read; an unknown or secret flag is `bad_input`."""
    out = stdout if stdout is not None else sys.stdout

    def say(line):
        out.write(line + '\n')
        out.flush()

    flags, argv_error = argv_inputs(argv or ())
    env = {**dict(env or {}), **flags}
    cwd = cwd or os.getcwd()
    check_id = secrets.token_hex(16)
    raw_key = str(env.get('INPUT_API_KEY') or '')
    conn_text = str(env.get('INPUT_CONNECTION') or '')
    id_key = str(env.get('INPUT_IDENTITY_KEY') or '')
    pasted = (id_key, id_key.strip()) if id_key.strip() not in ('', http_identity.KEY_SOURCE) else ()
    # MySQL: the password is masked FIRST, before the URI that embeds it; extract it early with a lightweight match
    conn_password = ()
    _conn_masked = conn_text.strip()
    if _conn_masked.lower().startswith('mysql'):
        try:
            from action import collect as _c
            if _c.is_mysql_connection(conn_text):
                _parsed = _c.parse_mysql_connection(conn_text)
                conn_password = tuple(_parsed.secrets)
                _t = _conn_masked
                for _s in conn_password:
                    _t = _t.replace(_s, '***')
                _conn_masked = _t
        except Exception:
            pass
    first = [v for v in dict.fromkeys(conn_password + (raw_key, raw_key.strip(), _conn_masked) + pasted) if v]
    # serve-060 (dogfood INC 3372): `::add-mask::` is a GitHub runner command; printed anywhere else it shows the
    # secret it was meant to hide. Emit it only on a GitHub runner; the scrub below still keeps every value out of output.
    on_runner = env.get('GITHUB_ACTIONS') == 'true'          # the exact value GitHub sets on its runners
    feedback_known_secrets = list(first)
    for v in first:                                    # before anything else is printed
        if on_runner:
            say(_mask(v))
    scrub = _Scrub(first)
    scrub.add([str(env.get('GITHUB_TOKEN') or '')])   # serve-102 r2: the workflow token, never printed (GitHub masks it)

    def protect(value):
        """Issue #1263: a secret learnt during the run is masked (on a runner) and scrubbed before any use."""
        if on_runner:
            say(_mask(value))
        scrub.add((value,))
        feedback_known_secrets.append(value)

    def oidc_sign_in(url):
        """Issue #1263: no api-key. With ACTIONS_ID_TOKEN_REQUEST_URL and _TOKEN set (the job has `id-token: write`),
        ask GitHub for this job's OIDC token with audience "assure" and exchange it at POST /v1/auth/oidc for a key
        that lives for this run; the key is masked before any use. Without them, `bad_input` naming the line to add."""
        req_url = str(env.get('ACTIONS_ID_TOKEN_REQUEST_URL') or '').strip()
        req_token = str(env.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN') or '').strip()
        if not req_url or not req_token:
            raise Refusal('bad_input', NO_CREDENTIAL_REASON)
        protect(req_token)
        proof = client_mod.request_oidc_token(req_url, req_token, audience=client_mod.OIDC_AUDIENCE)
        protect(proof)
        got = Client(url, None, sign_in=True).exchange_oidc(proof)
        protect(got['key'])
        state['oidc'] = {'account_id': got['account_id'], 'expires_at': got['expires_at']}
        say(OIDC_LINE % (_cmd_data(got['account_id']), _cmd_data(got['expires_at'])))
        return got['key']
    out_text, out_path, out_error = _output_path(env, cwd)
    state = {'mode': None, 'scratch': None, 'withheld': None, 'session': [], 'report_on': False, 'report': None,
             'report_url': '', 'allow_overage': False, 'requirements_notice': None, 'fresh_check': False,
             'compile_requirements': True, 'draft': None, 'proposed': False, 'files': None, 'goals': [],
             'pg_proposal': None, 'observed_raw': None, 'pg_checkout': None, 'pg_checkout_rel': None,
             'requirements_text': [], 'tree': None, 'declared': None}

    def finish_feedback():
        """After the primary file, summary and outputs: a feedback fault can change none of them."""
        if state['mode'] != 'api':
            return
        text = env.get('INPUT_FEEDBACK')
        if text is None or not str(text).strip():
            return
        try:
            candidates = (state.get('server_check_id'), state.get('feedback_server_check_id'),
                          getattr(state.get('client'), '_feedback_check_id', None))
            cid = next((candidate for candidate in candidates
                        if isinstance(candidate, str) and CHECK_ID_RE.fullmatch(candidate)), None)
            if cid is None:
                raise Refusal('bad_input', 'feedback needs the server check id')
            note = _feedback_note(text, cwd, cid, feedback_known_secrets)
            receipt = state['client'].feedback(note)
            line = 'Feedback: accepted; id %s; duplicate %s' % (receipt['id'], str(receipt['duplicate']).lower())
        except Refusal as e:
            outcome = e.outcome if e.outcome in OUTCOMES else 'api_error'
            line = 'Feedback: %s; note not confirmed.' % outcome
        except Exception:
            line = 'Feedback: api_error; note not confirmed.'
        try:
            _append(env.get('GITHUB_STEP_SUMMARY'), '\n' + line + '\n')
        except Exception:
            pass                                  # no secondary warning, value, path or exception text

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
        if e.detail.get('answered') in ('check', 'poll'):
            cid = e.detail.get('check_id') or e.detail.get('sent_check_id')
            if isinstance(cid, str) and CHECK_ID_RE.fullmatch(cid):
                state['feedback_server_check_id'] = cid
        e = scrub.refusal(e)
        code = e.detail.pop('exit_code', None) or (e.exit if e.exit is not None else 3)
        server_cid = state.get('server_check_id')
        if 'check_id' not in e.detail and isinstance(server_cid, str) and CHECK_ID_RE.fullmatch(server_cid):
            e.detail['check_id'] = server_cid          # a verdict came back, so the check reached the server
        cid = e.detail.get('check_id') or e.detail.get('sent_check_id')    # a refused poll: the id from the 202
        reached = state['mode'] == 'api' and any(isinstance(c, str) and CHECK_ID_RE.fullmatch(c) for c in (
            cid, server_cid, getattr(state.get('client'), '_feedback_check_id', None)))   # issue #1103: a 202 came
        doc = failure_envelope(cid if isinstance(cid, str) and CHECK_ID_RE.fullmatch(cid) else check_id, e,
                               charged=None if reached else False)
        try:
            _write_file(out_path, bundle.dumps(doc))
        except (OSError, ValueError) as w:
            say('::error title=Assure::%s' % _cmd_data('the failure file could not be written (%s)' % type(w).__name__))
        d = state['draft']                        # a check refused on a partial draft: propose it and name its gaps
        unread = declaration_draft.unread_required(d['data']) if d is not None and d['record'] is not None and \
            e.outcome == 'profile_refused' and e.detail.get('kind') == 'declaration_invalid' else ()
        step, decl_line, decl_md, decl_out = '', '', '', ''
        if unread:
            try:
                decl_line, decl_md, decl_out = declaration_note()
            except Exception as w:  # the class name only, never a value; the refusal stands as it is
                say('::warning title=Assure declaration::%s' % _cmd_data(
                    'the draft could not be proposed (%s)' % type(w).__name__))
            step = declaration_draft.next_step(unread, d['rel'],
                                               proposed=bool(decl_line) and 'not proposed' not in decl_line)
        try:
            _append(env.get('GITHUB_STEP_SUMMARY'), ('## Assure: next step\n\n%s\n\n' % step if step else '')
                    + render.failure_markdown(doc) + decl_md)
        except OSError:
            pass
        if decl_line:
            say(decl_line)
        if state['mode'] != 'lint':      # assure-on-itself-001 (requirements.md A2): the refusal on the pull request too
            try:                         # never changes the failure file or the exit; pr_comment types its own faults
                named = str(env.get('INPUT_REQUIREMENTS') or '').strip() not in ('', NONE_SENTINEL)
                body = render.pr_refusal_markdown(doc, (state['requirements_text'] or [None])[0], step or None,
                                                  _head_commit(env), named=named)
                pr_comment(None, body=body.split('\n', 1)[1].rstrip('\n'))
            except Exception as w:  # the class name only, never a value (a refusal before the comment step exists)
                say('::warning title=Assure comment::%s' % _cmd_data(
                    'the pull request comment failed unexpectedly (%s)' % type(w).__name__))
        say('::error title=%s::%s' % (_cmd_prop('Assure %s' % e.outcome), _cmd_data(
            '%s: %s%s' % (e.outcome, e.reason, '. ' + step if step else ''), cap=None if step else 300)))
        outputs(e.outcome, code, decl_out)
        finish_feedback()
        return code

    def connection(collect):
        """Parse the connection (when set) and mask its secrets; (conn, deferred Refusal or None, is_mysql)."""
        if not conn_text.strip():
            return None, None, False
        is_mysql = collect.is_mysql_connection(conn_text)
        try:
            conn = collect.parse_mysql_connection(conn_text) if is_mysql else collect.parse_connection(conn_text)
        except Refusal as e:
            return None, e, is_mysql
        for line in collect.mask_commands(conn, conn_text):
            if on_runner and line not in (_mask(v) for v in first):
                say(line)
        scrub.add(conn.secrets)
        feedback_known_secrets.extend(conn.secrets)
        return conn, None, is_mysql

    def collect_kw(collect, inputs):
        return dict(role=inputs['role'], privileges=inputs['privileges'], data_dir=inputs['data_dir'],
                    extra_roots=inputs['config_dirs'], collector_dir=collector_dir,
                    frozen_sha256=collect.FROZEN_COLLECTOR_SHA256 if collector_sha256 is _FROZEN else collector_sha256,
                    psql=psql, path=env.get('PATH') or '/usr/bin:/bin',
                    timeout=collect.DEFAULT_TIMEOUT if collect_timeout is None else collect_timeout)

    def session(files):
        """The session facts the collector's sidecar records, as plain lines for the log and the job summary."""
        state['files'] = files                    # issue #1186 part 2: the bundle as collected and withheld
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
        conn, conn_error, is_mysql = connection(collect)
        inputs = _inputs(env, conn, conn_error, collect, collector_dir, cwd, is_mysql=is_mysql)
        state['scratch'] = _scratch(env)
        if is_mysql and not inputs.get('artefacts'):
            ckw = dict(role=inputs['role'], declaration=inputs['declaration'],
                       collector_dir=collector_dir,
                       frozen_sha256=collect.FROZEN_MYSQL_COLLECTOR_SHA256 if collector_sha256 is _FROZEN
                       else collector_sha256,
                       mysql=mysql, path=env.get('PATH') or '/usr/bin:/bin',
                       timeout=collect.DEFAULT_TIMEOUT if collect_timeout is None else collect_timeout,
                       runner_env=env)
        elif inputs.get('artefacts'):
            ckw = None
        else:
            ckw = collect_kw(collect, inputs)
        held = []
        verdict, ignored, state['withheld'] = local_mode.run(
            engine=engine, inputs=inputs, fail_on_text=inputs['fail_on'], conn=conn, allow_partial=inputs['allow_partial'],
            collect_kw=ckw, scratch=state['scratch'], cwd=cwd,
            check_id=check_id, load_checker=load_checker, check_timeout=check_timeout, limits=limits,
            on_withheld=lambda counts: say(WITHHELD_LINE % {'withheld': withhold.describe(counts)}), on_collected=session,
            is_mysql=is_mysql, root=root, on_bundle=held.append,   # issue #206: the identity producer's tree
            observe=lambda c: observed_bundle(c, inputs['profile']))   # issue #3153: proposed as in api mode

        def declared_check(pid, files, counts):  # issue #2928: the same withheld bundle, never a second pass
            work = state['scratch'] / 'declared'
            work.mkdir(mode=0o700)
            got = bundle.Collected(files=files, ignored=list(held[0].ignored), withheld=counts, records=held[0].records)
            return local_mode.run(
                engine=engine, inputs=dict(inputs, profile=pid, scope=None, scope_binding=None),
                fail_on_text=declared_fail_on(inputs['fail_on']), conn=None, allow_partial=inputs['allow_partial'],
                collect_kw=None, scratch=work, cwd=cwd, check_id=check_id, load_checker=load_checker, check_timeout=check_timeout,
                limits=limits, is_mysql=False, root=root, collected=got)[0]
        declared_reading(inputs['profile'], held[0] if held else None, declared_check, limits, 'checker_error')
        return dict(verdict, charged=False), ignored             # issue #1103: no API was contacted; nothing charged

    def declared_reading(profile, collected, check, lim, unexpected):
        """Issue #2928: on an observed profile with intent committed in the checkout, `check(declared profile, the same
        withheld files plus raw/declaration.json = the committed bytes with their literals withheld in the snapshot's
        numbering, counts)` (`withhold.with_declaration`); `state['declared']` is (profile, verdict or Refusal, the
        checkout path read), None when the profile has no declared one or nothing is committed. REFUTATION-r4 HIGH-1:
        the path named is the one `checkout_declaration_at` read (#2927's own path first). Never raises: an unreadable
        intent file or a refused or failed declared check is a typed Refusal shown in its section."""
        pid = OBSERVED_DECLARED.get(profile)
        if pid is None or collected is None:
            return
        rel = declaration_draft.CHECKOUT_PATH
        try:
            try:
                at = checkout_declaration_at(Path(env.get('GITHUB_WORKSPACE') or cwd), (lim or bundle.LIMITS).file_bytes,
                                             skip_links=True)       # issue #3153: a link is never the intent
            except Refusal as e:                  # the refused file is the one its reason names
                rel = next((r for r in (DECLARED_CHECKOUT_PATH, declaration_draft.CHECKOUT_PATH)
                            if str(e.reason).startswith(r + ' ')), rel)
                raise
            if at is None:
                return
            rel, data = at
            files, counts = withhold.with_declaration(collected, data)
            say('Assure: declared check: %s' % withhold.describe(counts))
            got = check(pid, files, counts)
            if not isinstance(got, dict) or got.get('schema') != VERDICT_SCHEMA:
                raise Refusal(unexpected, 'no verdict envelope')
            say('Assure: declared reading: %s, with %s' % (pid, rel))   # issue #3153: the log names it too
        except Refusal as e:
            got = Refusal(e.outcome, scrub(e.reason))
        except Exception as e:  # typed, never a traceback; the class name only
            got = Refusal(unexpected, 'the declared check failed unexpectedly (%s)' % type(e).__name__)
        state['declared'] = (pid, got, rel)

    def manifest_written(written):
        if written is not None:
            say('Assure: %s written in the runner: %d repository file(s), commit %s, tree %s' % (
                repository_manifest.NAME, len(written['files']), written['commit'], written['tree']))

    def declaration(collected, where, target, checkout, data=None):
        """serve-102 (DD-150, DD-156): python-auth with no declaration runs on a draft, bounded by it; on a pull
        request, a checkout's declaration that is not yet on the base branch is the same unaccepted draft. `data` is
        the checkout's bytes when the bundle holds them withheld (issue #2435)."""
        top = declaration_draft.toplevel(where, env)
        rel = target.resolve().relative_to(top.resolve()).as_posix() if top is not None and \
            str(target.resolve()).startswith(str(top.resolve()) + os.sep) else declaration_draft.CHECKOUT_PATH
        if declaration_draft.NAME not in collected.files:
            repo = {n[len(repository_manifest.PREFIX):]: d for n, d in collected.files.items()
                    if n.startswith(repository_manifest.PREFIX)}
            record = declaration_draft.draft(repo, client=state['client'])
            data = declaration_draft.dumps(record['declaration'])
            collected.files[declaration_draft.NAME] = data
            state['draft'] = {'record': record, 'data': data, 'top': top, 'rel': rel}
            say('Assure: %s drafted in the runner from %d repository file(s); %d field(s) to confirm' % (
                declaration_draft.NAME, len(repo), len(record['confirm'])))
        elif checkout and declaration_draft.is_pull_request(env) and top is not None:
            # tri-state: True is a known match; False is a known absence; None is an unknown reading, bounded too
            on_base = declaration_draft.on_base(
                top, rel, collected.files[declaration_draft.NAME] if data is None else data, env)
            if on_base is not True:
                state['draft'] = {'record': None, 'data': None, 'top': top, 'rel': rel, 'unread': on_base is None}

    def declaration_note():
        """(log line, summary markdown, output line) for a run bounded by an unaccepted draft, proposing a new draft
        first; ('', '', '') otherwise. Never changes the verdict, its file or its exit."""
        d = state['draft']
        if d is None:
            return '', '', ''
        base = _plain(env, 'GITHUB_BASE_REF') or 'the base branch'
        if d['record'] is None:
            told = '%s %s on %s%s; merging the pull request accepts it' % (
                d['rel'], 'could not be read' if d.get('unread') else 'is not', base, '' if d.get('unread') else ' yet')
            md = '\n### Declaration: bounded by an unaccepted declaration draft\n\n%s.\n' % render.esc(told)
        else:
            tmp = _scratch(env)
            github = None
            try:
                if d['top'] is None:
                    raise Refusal('bad_input', 'the artefacts directory is not inside a git checkout')
                token = str(env.get('GITHUB_TOKEN') or '').strip()
                github = GitHub(_plain(env, 'GITHUB_API_URL') or None, token) if token else None
                got = declaration_draft.propose(d['top'], d['rel'], d['data'], d['record'], env, tmp, github,
                                                **d.get('words', {}))
                told = 'proposed in pull request #%d (%s), from %s into the base branch (commit %s); merging it %s' % (
                    got['number'], got['url'] or 'no link returned', got['branch'], got['commit'][:12],
                    'commits the declaration' if d.get('observed') else 'accepts it')
                state['proposed'] = True
            except Refusal as e:
                if d.get('observed') and e.reason.startswith(declaration_draft.PUSH_REFUSED):
                    # REFUTATION-r1 HIGH-2: a `contents: read` token (the documented observed jobs, a fork) is not
                    # asked to propose; main's files and section beside the verdict stay, with no warning
                    return 'Assure: declaration proposal: not proposed (%s)' % _cmd_data(scrub(e.reason)), '', ''
                told = 'not proposed (%s); the draft is below' % scrub(e.reason)
                say('::warning title=Assure declaration::%s' % _cmd_data(told))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if d.get('observed'):                     # issue #2934: an observed verdict is not bounded by the draft
                md = '\n### Declaration pull request\n\n%s.\n' % render.esc(told[:1].upper() + told[1:])
                if not state['proposed'] and d.get('shown') is not None:   # REFUTATION-r6 MEDIUM-2: withheld only
                    md += '\n```json\n%s```\n' % d['shown'].decode('utf-8')
                    if d['shown'] == d['data']:   # issue #3153: a link commits the proposal's own bytes, never placeholders
                        md += commit_line(github, d)
                return 'Assure: declaration proposal: %s' % _cmd_data(told), md, ''
            md = declaration_draft.summary_markdown(d['record'], d['rel'], render.esc(told[:1].upper() + told[1:] + '.'),
                                                    *(['the collected catalog snapshot'] if d.get('words') else []))
            if told.startswith('not proposed'):
                md += commit_line(github, d)
                md += '\n```json\n%s```\n' % d['data'].decode('utf-8')
        return ('Assure: declaration: %s: %s' % (declaration_draft.BOUNDED, _cmd_data(told)), md,
                declaration_draft.OUTPUT_BOUNDED + '\n')

    def commit_line(github, d):
        """Issue #2249: a refused proposal leaves a one-click commit of the draft on the branch the proposal targets
        (the pull request's base, else the default branch); unknown, the summary names the path."""
        try:
            branch = declaration_draft.proposal_base(env, github, _plain(env, 'GITHUB_REPOSITORY')) \
                if github is not None or declaration_draft.is_pull_request(env) else ''
        except Exception:  # the link is optional: never changes the reading, its file or its exit
            branch = ''
        return declaration_draft.commit_markdown(env, branch, d['rel'], d['data'])

    def observed_draft(verdict):
        """Issue #2934: on PROPOSAL_PROFILE inside a git checkout with nothing committed at the intent path (neither
        DECLARED_CHECKOUT_PATH nor `.assure/declaration.json`, `checkout_declaration`), the draft from the collector's own
        snapshot and sidecar before withholding (`state['observed_raw']`, REFUTATION-r1 HIGH-3: the literals as written,
        as `pg_declare` drafts), recorded to be proposed at DECLARED_CHECKOUT_PATH as `pg_declare` records its own.
        Issue #3153 (#2249 "keep it current"): intent committed at DECLARED_CHECKOUT_PATH whose JSON differs from the
        draft (or is not JSON) gets the draft proposed too; one equal to it, or one at `.assure/declaration.json`, none."""
        if state['draft'] is not None or not isinstance(verdict, dict) or verdict.get('profile') != PROPOSAL_PROFILE \
                or not isinstance(state['observed_raw'], dict):
            return
        if not str(env.get('GITHUB_TOKEN') or '').strip():   # no workflow token: main's files and section, silently
            return
        top = declaration_draft.toplevel(Path(env.get('GITHUB_WORKSPACE') or cwd or os.getcwd()), env)
        try:
            if top is None:
                return
            at = checkout_declaration_at(top, bundle.LIMITS.file_bytes, skip_links=True)   # #3153: links pass
            if at is not None and at[0] != DECLARED_CHECKOUT_PATH:
                return
            drafted = draft_proposal(state['observed_raw'])
        except Exception:  # a present but unreadable declaration is never drafted over; main's files and section stay
            return
        if drafted is None or (at is not None and _same_json(at[1], drafted[0]['declaration'])):
            return
        record = drafted[0]
        try:            # REFUTATION-r6 MEDIUM-2: the summary shows only the withheld draft (write_proposal's), never `data`
            withheld = draft_proposal(state['files']) if isinstance(state['files'], dict) else None
        except Exception:  # nothing is shown; the file beside the verdict says the same
            withheld = None
        state['draft'] = {'record': record, 'data': declaration_draft.dumps(record['declaration']), 'top': top,
                          'rel': DECLARED_CHECKOUT_PATH, 'observed': True,
                          'shown': None if withheld is None else declaration_draft.dumps(withheld[0]['declaration']),
                          'words': {'title': DECLARED_TITLE, 'source': DECLARED_SOURCE, 'lead': OBSERVED_LEAD % {
                              'rel': DECLARED_CHECKOUT_PATH, 'source': DECLARED_SOURCE,
                              'rows': proposal_counts(record, verdict)['rows']}}}

    def pg_declare(top, cap):
        """Issue #2435: `declare` for `action.collect._gather` on postgresql-declared-model: the checkout's
        declaration, else a draft from the collector's own (not yet withheld) snapshot and sidecar in `raw`, recorded
        to be proposed; None when nothing can be drafted (the missing file is then refused as before)."""
        def declare(raw):
            got = checkout_declaration_at(top, cap)
            if got is not None:
                state['pg_checkout_rel'], state['pg_checkout'] = got
                return got[1]
            files = {n: b for n in (PROPOSAL_SNAPSHOT, PROPOSAL_SIDECAR)
                     if (b := _raw_bounded(raw, n[len('raw/'):], cap)) is not None}
            drafted = draft_proposal(files)
            if drafted is None:
                return None
            record = state['pg_proposal'] = drafted[0]
            data = declaration_draft.dumps(record['declaration'])
            state['draft'] = {'record': record, 'data': data, 'top': declaration_draft.toplevel(top, env),
                              'rel': DECLARED_CHECKOUT_PATH,
                              'words': {'title': DECLARED_TITLE, 'source': DECLARED_SOURCE}}
            say('Assure: %s drafted in the runner from %s; %d field(s) to confirm' % (
                declaration_draft.NAME, DECLARED_SOURCE, len(record['confirm'])))
            return data
        return declare

    def observed_raw(files):
        """Issue #2934: the snapshot and sidecar of `files` (not yet withheld) kept for `observed_draft`."""
        state['observed_raw'] = {n: bytes(files[n]) for n in (PROPOSAL_SNAPSHOT, PROPOSAL_SIDECAR) if n in files}

    def observed_bundle(collected, profile):
        """`collected` unchanged; on PROPOSAL_PROFILE its raw snapshot and sidecar are kept first (`observed_raw`), so
        the artefacts path still reads into `withhold.apply` on one line (tests/serving/test_faithful.py)."""
        if profile == PROPOSAL_PROFILE:
            observed_raw(collected.files)
        return collected

    def observed_collect(cap):
        """`observe` for `action.collect._gather` on PROPOSAL_PROFILE: writes nothing, keeps the raw snapshot."""
        def observe(raw):
            observed_raw({n: b for n in (PROPOSAL_SNAPSHOT, PROPOSAL_SIDECAR)
                          if (b := _raw_bounded(raw, n[len('raw/'):], cap)) is not None})
        return observe

    def run_api():
        if out_error is not None:
            raise out_error
        collect = load_collect() if conn_text.strip() else None
        conn, conn_error, is_mysql = connection(collect) if collect is not None else (None, None, False)
        inputs = _inputs(env, conn, conn_error, collect, collector_dir, cwd, is_mysql=is_mysql)
        if not _FAIL_ON_SHAPE.fullmatch(inputs['fail_on']):
            raise Refusal('bad_input', 'fail-on must be a short comma list of statuses, or never')
        upload, state['requirements_notice'] = requirements_upload(env, cwd, state['goals'],
                                                                   state['requirements_text'])   # serve-019: before anything is sent
        if 'requirements' in upload and not state['compile_requirements']:   # issue #2252: sent only when off
            upload['compile_requirements'] = False
        if state['requirements_notice']:
            say('::notice title=Assure requirements::%s' % _cmd_data(state['requirements_notice'], cap=None))
        url = _plain(env, 'INPUT_API_URL') or DEFAULT_URL
        key = raw_key.strip() or oidc_sign_in(url)            # issue #1263: no api-key, the GitHub OIDC sign-in
        client = (client_factory or Client)(url, key)
        state['client'] = client
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
            manifest_dir = (art if art.is_absolute() else Path(cwd) / art).resolve()
            produced, binding = http_identity.produce_and_collect(root, manifest_dir, state['scratch'].resolve(),
                                                                  scope=scope)
            http_identity.send_intent(manifest_dir, produced)      # issue #2381: the customer's declared HTTP intent
            scope = sorted(binding['endpoint_tokens'])
            collected = withhold.apply(bundle.from_directory(produced, allow, lim), allow)
        elif inputs.get('checkout'):              # serve-102: python-auth from the checkout, in one step
            top = Path(env.get('GITHUB_WORKSPACE') or cwd)
            collected, modes = repository_manifest.from_checkout(top, allow, lim, env)
            collected = withhold.apply(collected, allow)
            target = top / declaration_draft.CHECKOUT_PATH
            if os.path.isfile(target) and not os.path.islink(target):
                collected.files[declaration_draft.NAME] = target.read_bytes()
            manifest_written(repository_manifest.complete(collected, inputs['profile'], top, env, modes))
            declaration(collected, top, target, checkout=True)
        elif inputs['artefacts']:
            art = Path(inputs['artefacts'])
            art = art if art.is_absolute() else Path(cwd) / art
            try:
                collected = withhold.apply(observed_bundle(bundle.from_directory(art, allow, lim), inputs['profile']), allow)
            except Refusal as e:
                raise _with_layout(e, allow, art) from None
            manifest_written(repository_manifest.complete(collected, inputs["profile"], art, env))
            if inputs["profile"] == declaration_draft.PROFILE:
                declaration(collected, art, repository_manifest.raw_dir(art) / "declaration.json", checkout=False)
        elif is_mysql:
            state['scratch'] = _scratch(env)
            work = state['scratch'] / 'collect'
            work.mkdir(mode=0o700)
            ckw = dict(role=inputs['role'], declaration=inputs['declaration'],
                       collector_dir=collector_dir,
                       frozen_sha256=collect.FROZEN_MYSQL_COLLECTOR_SHA256 if collector_sha256 is _FROZEN
                       else collector_sha256,
                       mysql=mysql, path=env.get('PATH') or '/usr/bin:/bin',
                       timeout=collect.DEFAULT_TIMEOUT if collect_timeout is None else collect_timeout,
                       runner_env=env)
            collected = collect.collect_mysql(conn, profile=allow, scratch=work, limits=lim, **ckw)
        else:
            state['scratch'] = _scratch(env)
            work = state['scratch'] / 'collect'
            work.mkdir(mode=0o700)
            pg = inputs['profile'] == DECLARED_PROFILE        # issue #2435: the checkout's declaration, else a draft
            top = Path(env.get('GITHUB_WORKSPACE') or cwd or os.getcwd())
            kw = {'declare': pg_declare(top, lim.file_bytes)} if pg else \
                {'observe': observed_collect(lim.file_bytes)} if inputs['profile'] == PROPOSAL_PROFILE else {}
            collected = collect.collect(conn, profile=allow, scratch=work, limits=lim, **collect_kw(collect, inputs),
                                        **kw)
            if pg and state['pg_checkout'] is not None:
                declaration(collected, top, top / state['pg_checkout_rel'], checkout=True,
                            data=state['pg_checkout'])
        state['withheld'] = collected.withheld
        say(WITHHELD_LINE % {'withheld': withhold.describe(collected.withheld)})
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
        declared_reading(inputs['profile'], collected, lambda pid, files, counts: client.submit(   # issue #2928
            pid, files, declared_fail_on(inputs['fail_on']), limits=lim, key_from_bundle=not state['fresh_check'],
            **extra), lim, 'api_error')
        if state['report_on']:                    # serve-014: never changes the verdict, its file or its exit
            state['report_url'] = client.base + '/v1/checks/%s/report.html' % verdict['check_id']
            try:
                state['report'] = client.report(verdict['check_id'], allow_overage=state['allow_overage'])
            except Refusal as e:
                state['report'] = scrub.refusal(e)
            except Exception as e:  # typed, never a traceback; the class name only
                state['report'] = Refusal('api_error', 'the report request failed unexpectedly (%s)' % type(e).__name__)
        return verdict, list(collected.ignored)

    def pr_comment(verdict, **kw):
        """Issue #2189: on a pull_request event with a workflow token, post or update the one Assure comment; never
        changes the verdict, its file or its exit. Issue #3168: `mode: lint` posts its LINT_PREFLIGHT through here."""
        if env.get('GITHUB_EVENT_NAME') not in PR_EVENTS or not str(env.get('GITHUB_TOKEN') or '').strip():
            return
        try:
            post_pr_comment(env, verdict, GitHub(_plain(env, 'GITHUB_API_URL') or None,
                                                 str(env.get('GITHUB_TOKEN')).strip()), **kw)
        except Refusal as e:
            if e.detail.get('status') == 403:          # the token cannot write comments: say the line to add, once
                say('::notice title=Assure comment::%s' % _cmd_data(PR_COMMENT_NOTICE))
            else:
                say('::warning title=Assure comment::%s' % _cmd_data(scrub(e.reason)))
        except Exception as e:  # the class name only, never a value
            say('::warning title=Assure comment::%s' % _cmd_data(
                'the pull request comment failed unexpectedly (%s)' % type(e).__name__))

    def finish_lint(doc, ignored):
        """serve-043: write the lint record to the output path, the findings to the job summary and as warnings, and the
        outputs outcome `lint`, exit-code (0 when ok, else 2) and lint-findings. Never a charge, never a check."""
        if doc.get('schema') != LINT_SCHEMA:
            return failed(Refusal('api_error', 'no lint record'))
        found = [f for f in doc['findings'] if isinstance(f, dict)]
        code = 0 if doc.get('ok') is True and not found else 2
        try:
            summary = LINT_PREFLIGHT + '\n\n' + _lint_markdown(found)     # issue #3168: the first line
        except Exception as e:  # the class name only, never a value
            return failed(Refusal('api_error', 'the lint record could not be rendered (%s)' % type(e).__name__))
        decl_line, decl_md, decl_out = declaration_note()       # serve-102
        summary += decl_md
        try:
            _write_file(out_path, bundle.dumps(doc))
        except (OSError, ValueError) as w:
            return failed(Refusal('checker_error', 'the lint file could not be written (%s)' % type(w).__name__))
        try:
            _append(env.get('GITHUB_STEP_SUMMARY'), summary)
        except OSError as w:
            say('::warning title=Assure::%s' % _cmd_data('the job summary could not be written (%s)' % type(w).__name__))
        say('::notice title=Assure::%s' % _cmd_data(LINT_PREFLIGHT, cap=None))     # issue #3168
        pr_comment(doc, body=LINT_PREFLIGHT)
        for f in found:
            say('::warning title=%s::%s' % (_cmd_prop('Assure lint'), _cmd_data(_lint_line(f))))
        if ignored:
            say(_notice_line(ignored, _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE))
        if decl_line:
            say(decl_line)
        say(LINT_LINE % {'reading': 'ready for a check' if code == 0 else 'fix these before a check',
                         'findings': len(found), 'exit': code, 'output': _cmd_data(out_text)})
        outputs('lint', code, 'lint-findings=%d\n%s' % (len(found), decl_out), lint_colour='green' if code == 0 else 'red')
        return code

    try:
        try:
            if argv_error is not None:                 # issue #1953: before any input is read
                raise argv_error
            state['mode'] = _mode(env)
            state['report_on'] = parse_report(_plain(env, 'INPUT_REPORT'), state['mode'])   # serve-014: before anything is read
            state['allow_overage'] = parse_allow_overage(_plain(env, 'INPUT_ALLOW_OVERAGE'))     # serve-015
            state['fresh_check'] = parse_fresh_check(_plain(env, 'INPUT_FRESH_CHECK'))           # serve-023
            state['compile_requirements'] = parse_compile_requirements(
                _plain(env, 'INPUT_COMPILE_REQUIREMENTS'))                                        # issue #2252
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
        summary += goal_rollup_markdown(state['goals'], verdict)          # issue #1186
        compiled = verdict.get('requirements_compilation')  # issue #2252: the server's sentence on the Haiku reading
        if isinstance(compiled, dict) and isinstance(compiled.get('summary'), str) and compiled['summary']:
            summary += '\n' + render.esc(compiled['summary']) + '\n'
        key_line = render.key_expiry_line(getattr(state.get('client'), 'key_expires', None))    # issue #1262
        if key_line is not None:
            summary += '\n' + render.esc(key_line) + '\n'
        notes = render.annotations(verdict)
        summary = render.upgrade_markdown(verdict) + summary   # launch 2026-10-12: the server's upgrade line, first
    except Exception as e:  # the class name only, never a value
        return failed(Refusal(unrenderable, 'the verdict could not be rendered (%s)' % type(e).__name__))
    observed_draft(verdict)                                     # issue #2934: proposed like the declared draft
    decl_line, decl_md, decl_out = declaration_note()           # serve-102: the draft bounds this verdict
    summary += decl_md
    summary += declaration_draft.intent_markdown(inputs_profile, drafted=state['draft'] is not None)   # issue #2926
    both = None
    if state['declared'] is not None:               # issue #2928: informational; never the verdict, its file or exit
        pid, got, intent = state['declared']           # REFUTATION-r4 HIGH-1: the file read is the file named
        before = summary
        try:
            summary += declared_markdown(got, pid, intent, state['mode'] == 'api' and isinstance(got, dict))
            if isinstance(got, dict):
                both = both_readings_line(verdict, got, intent)
                head, _, rest = both.partition(' (')
                up = render.upgrade_markdown(verdict)     # REFUTATION-r3 MEDIUM-3: the upgrade line stays at the top
                body = summary[len(up):] if up and summary.startswith(up) else summary
                summary = up + '**Assure: %s** (%s\n\n' % (head, rest) + body
        except Exception as e:  # the class name only, never a value
            both = None                        # REFUTATION-r4 LOW: the line sits in its section, under its head
            summary = before + declared_markdown(Refusal('checker_error', 'the declared verdict could not be rendered '
                                                         '(%s)' % type(e).__name__), pid, intent, False)
    try:
        _write_file(out_path, bundle.dumps(verdict))
    except (OSError, ValueError) as w:
        return failed(Refusal('checker_error', 'the verdict file could not be written (%s)' % type(w).__name__))
    proposal_md = write_proposal(verdict, state['files'], out_path.parent, say, run_artifacts_url(env),  # #1186 part 2
                                 state['proposed'])                                                # issue #2934
    summary += proposal_md
    draft_out = ('requirements-draft=%s\n' % (Path(out_text).parent / REQUIREMENTS_DRAFT_FILE)  # issue #2892
                 if proposal_md else '')
    try:                                               # issue #2651: never changes the verdict, its file or its exit
        repo_name = str(env.get('GITHUB_REPOSITORY') or '').strip()
        state['tree'] = write_proof_tree(verdict, out_path.parent, state['goals'],
                                         (state['requirements_text'] or [None])[0], repo_name or None,
                                         _head_commit(env))
    except Exception as w:  # the class name only, never a value
        say('::warning title=Assure::%s' % _cmd_data('the proof tree could not be written (%s)' % type(w).__name__))
    if state['pg_proposal'] is not None:              # issue #2435: the drafted declaration's record, beside the verdict
        try:
            _write_file(out_path.parent / PROPOSAL_FILE, (json.dumps(
                state['pg_proposal'], indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
        except (OSError, ValueError) as w:
            say('::warning title=Assure::%s' % _cmd_data('the declaration proposal could not be written (%s)'
                                                         % type(w).__name__))
    try:
        _append(env.get('GITHUB_STEP_SUMMARY'), summary)
    except OSError as w:
        say('::warning title=Assure::%s' % _cmd_data('the job summary could not be written (%s)' % type(w).__name__))
    if both is not None:                               # issue #2928: the verdict's first notice reads both readings
        say('::notice title=Assure::%s' % _cmd_data('Assure: ' + both, cap=None))
    client = state.get('client')
    pr_comment(verdict, tree=pr_tree(verdict, state['tree']),
               tree_bases=(DEFAULT_URL,) + ((client.base,) if getattr(client, 'base', None) else ()))
    for line in notes:
        say(line)
    if ignored:
        say(_notice_line(ignored, inputs_profile))
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
    if decl_line:
        say(decl_line)
    line = render.verdict_line(verdict)              # serve-016: the verdict line; an older server's coverage phrase
    line = render.first_line(verdict) if line is None else line
    say('Assure: %s%s; policy exit %d; %s' % ('' if line is None else _cmd_data(line, cap=None) + '; ',
                                              _cmd_data(verdict['outcome']), code, _cmd_data(out_text)))
    outputs(verdict['outcome'], code, report_extra + decl_out + draft_out, verdict)
    finish_feedback()
    return code


if __name__ == '__main__':
    _env = dict(os.environ)
    scrub_process_env(os.environ)
    sys.exit(main(_env, root=_ROOT, argv=sys.argv[1:]))

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
