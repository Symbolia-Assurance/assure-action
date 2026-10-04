"""The Assure Action's entry point, run by `action.yml` in the customer's own runner (DIRECTOR-DIRECTION-SERVE-003;
SERVE-001 U2).

    "$ASSURE_PYTHON" -I -B "$GITHUB_ACTION_PATH/entry.py"

Every input arrives as an environment variable (INPUT_MODE, INPUT_API_KEY, INPUT_API_URL, INPUT_PROFILE,
INPUT_ARTEFACTS, INPUT_CONNECTION, INPUT_COLLECTION_ROLE, INPUT_COLLECTION_PRIVILEGES, INPUT_DATA_DIR, INPUT_CONFIG_DIRS,
INPUT_FAIL_ON, INPUT_OUTPUT), with GITHUB_STEP_SUMMARY, GITHUB_OUTPUT and RUNNER_TEMP. Before anything else is printed,
the API key and the connection are masked with `::add-mask::`. When run as a script, the process environment is then cut
to a short list (PATH, locale, temporary directory, proxy and CA settings), so no child process inherits a key, the
connection or a runner token.

`mode: api` (the default) is the thin client. The check runs on Symbolia's server:
  the inputs -> the API's profile list (`GET /v1/profiles`: each profile's input allow-list and the global limits) ->
  the frozen collector in the runner (or the `artefacts` directory) under those bounds, so an unlisted or oversize file
  never leaves the runner -> `POST /v1/checks?fail_on=...` over TLS with the key -> poll while 202 -> the returned
  envelope is written to the output path -> the job summary and annotations are rendered here from it -> the exit code
  is the envelope's `policy.exit` (never derived here). A failure envelope gives its outcome's exit code. `fail-on` is
  sent as written; the server checks it against the profile.
`mode: local` runs the check in the runner with the engine this tree vendors. Its code is `action/local_mode.py`,
imported only in that branch; the public Action tree does not ship it, and there `mode: local` is `bad_input`. No
engine byte runs before the engine pin is verified (`serve.pin`, which imports no engine module).

Exit codes: 0 policy met, 1 policy failed, 2 bad input, 3 nothing was checked (no verdict, or the input-integrity gate
stopped the check), a typed refusal or a delivery failure (`api_unreachable`, `api_error`); an outcome with no exit code
of its own (for example `unauthenticated`) exits 3. Every failure writes the failure envelope at the output path, its
summary and one `::error` line. The key, the connection, its password and the collector's raw output are never printed,
and customer text reaches stdout only escaped as workflow-command data.

Before anything is checked or sent, `action.withhold` withholds every configuration comment and every string literal in
the policy expressions, in every mode and for a connection or an artefacts directory alike (the customer's directory is
never changed); the counts are printed and added to the job summary. In api mode the verdict's shape is checked before it
is rendered: a malformed verdict is `api_error` (exit 3), with the failure file and the step outputs written.

This module imports, at its top, the standard library and modules that never import the engine: `action.client`,
`action.withhold`, `serve` (flags), `serve.bundle`, `serve.outcomes` and `serve.render`.
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

from action import withhold  # noqa: E402
from action.client import CHECK_ID_RE, DEFAULT_URL, VERDICT_SCHEMA, Client, allow_list  # noqa: E402
from serve import FLAGS, bundle, render  # noqa: E402
from serve.outcomes import Refusal  # noqa: E402

DEFAULT_PROFILE = 'postgresql-observed-baseline'
DEFAULT_OUTPUT = 'assure-verdict.json'
FAILURE_SCHEMA = 'assure.serve.failure/v1'
MODES = ('api', 'local')
MAX_INPUT = 4096
MAX_NOTICE_NAMES = 20
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_FAIL_ON_SHAPE = re.compile(r'[A-Za-z0-9_, ]{0,100}')
_OUTCOME_SHAPE = re.compile(r'[a-z_]{1,40}')
_FROZEN = object()
# The variables a child process of the Action may still see (ACTION-06): no input, key, connection or runner token.
KEEP_ENV = ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TZ', 'SYSTEMROOT', 'HTTPS_PROXY', 'https_proxy',
            'NO_PROXY', 'no_proxy', 'SSL_CERT_FILE', 'SSL_CERT_DIR')


def _cmd_data(value):
    s = '' if value is None else str(value)
    s = s if len(s) <= 300 else s[:299] + '…'
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
        detail = {k: (self(v) if isinstance(v, str) else v) for k, v in e.detail.items()}
        return Refusal(e.outcome, self(e.reason), **detail)


def load_collect():
    """`action.collect`, for a connection (it bounds the collected files with `serve.bundle`, as the server does)."""
    from action import collect
    return collect


def _mode(env):
    m = _plain(env, 'INPUT_MODE').lower() or 'api'
    if m not in MODES:
        raise Refusal('bad_input', 'mode must be api or local')
    return m


def _inputs(env, conn, conn_error, collect):
    profile = _plain(env, 'INPUT_PROFILE') or DEFAULT_PROFILE
    artefacts = _plain(env, 'INPUT_ARTEFACTS')
    has_conn = bool(str(env.get('INPUT_CONNECTION') or '').strip())
    if bool(artefacts) == has_conn:
        raise Refusal('bad_input', 'set exactly one of connection and artefacts (%s set)'
                      % ('both are' if has_conn else 'neither is'))
    fail_on = _plain(env, 'INPUT_FAIL_ON')
    data_dir_text = _plain(env, 'INPUT_DATA_DIR')
    config_dirs_text = env.get('INPUT_CONFIG_DIRS')      # line breaks separate items, so it is not read by _plain
    if conn_error is not None:
        raise conn_error
    out = {'profile': profile, 'fail_on': fail_on, 'artefacts': artefacts or None}
    if artefacts:
        if data_dir_text:
            raise Refusal('bad_input', 'data-dir applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        if str(config_dirs_text or '').strip(' \t\r\n:'):
            raise Refusal('bad_input', 'config-dirs applies only with connection; with artefacts, put the collected '
                          'files under raw/')
        return out
    out['role'] = collect.check_role(_plain(env, 'INPUT_COLLECTION_ROLE'), conn)
    out['privileges'] = collect.check_privileges(_plain(env, 'INPUT_COLLECTION_PRIVILEGES'))
    out['data_dir'] = collect.check_data_dir(data_dir_text)
    out['config_dirs'] = collect.check_config_dirs(config_dirs_text)
    return out


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
    first = [v for v in dict.fromkeys((raw_key, raw_key.strip(), conn_text.strip())) if v]
    for v in first:                                    # before anything else is printed
        say(_mask(v))
    scrub = _Scrub(first)
    out_text, out_path, out_error = _output_path(env, cwd)
    state = {'mode': None, 'scratch': None, 'withheld': None}

    def outputs(outcome, code):
        try:
            _append(env.get('GITHUB_OUTPUT'), 'verdict-path=%s\noutcome=%s\nexit-code=%d\n' % (out_text, outcome, code))
        except OSError as w:
            say('::warning title=Assure::%s' % _cmd_data('the step outputs could not be written (%s)' % type(w).__name__))

    def failed(e):
        e = scrub.refusal(e)
        code = e.exit if e.exit is not None else 3
        cid = e.detail.get('check_id')
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

    def run_local():
        absent = Refusal('bad_input', 'local mode is not available in this distribution; use mode: api')
        if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_mode.py')):
            raise absent
        try:
            from action import local_mode                      # standard library only at its top
        except ImportError:
            raise absent from None
        engine = local_mode.verify_engine_pin(root, pin_path)   # before any engine byte is imported
        if out_error is not None:
            raise out_error
        from action import collect                             # after the pin, like every local-mode import
        conn, conn_error = connection(collect)
        inputs = _inputs(env, conn, conn_error, collect)
        state['scratch'] = _scratch(env)
        verdict, ignored, state['withheld'] = local_mode.run(
            engine=engine, inputs=inputs, fail_on_text=inputs['fail_on'], conn=conn,
            collect_kw=None if inputs['artefacts'] else collect_kw(collect, inputs), scratch=state['scratch'], cwd=cwd,
            check_id=check_id, load_checker=load_checker, check_timeout=check_timeout, limits=limits,
            on_withheld=lambda counts: say('Assure: ' + withhold.describe(counts)))
        return verdict, ignored

    def run_api():
        if out_error is not None:
            raise out_error
        collect = load_collect() if conn_text.strip() else None
        conn, conn_error = connection(collect) if collect is not None else (None, None)
        inputs = _inputs(env, conn, conn_error, collect)
        if not _FAIL_ON_SHAPE.fullmatch(inputs['fail_on']):
            raise Refusal('bad_input', 'fail-on must be a short comma list of statuses, or never')
        url = _plain(env, 'INPUT_API_URL') or DEFAULT_URL
        client = (client_factory or Client)(url, raw_key.strip())
        allow = allow_list(client.profiles(), inputs['profile'])
        lim = limits if limits is not None else allow.limits
        if inputs['artefacts']:
            art = Path(inputs['artefacts'])
            collected = withhold.apply(bundle.from_directory(art if art.is_absolute() else Path(cwd) / art, allow,
                                                             lim))
        else:
            state['scratch'] = _scratch(env)
            work = state['scratch'] / 'collect'
            work.mkdir(mode=0o700)
            collected = collect.collect(conn, profile=allow, scratch=work, limits=lim, **collect_kw(collect, inputs))
        state['withheld'] = collected.withheld
        say('Assure: ' + withhold.describe(collected.withheld))
        bundle.check_files(collected.files, allow, lim)        # nothing unlisted or oversize leaves the runner
        body = bundle.request_body(inputs['profile'], collected.files, lim)
        verdict = client.submit(inputs['profile'], collected.files, inputs['fail_on'] or None, body=body)
        check_verdict(verdict)
        return verdict, list(collected.ignored)

    try:
        try:
            state['mode'] = _mode(env)
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

    if verdict.get('schema') != VERDICT_SCHEMA:
        return failed(Refusal('api_error' if state['mode'] == 'api' else 'checker_error', 'no verdict envelope'))
    code = verdict['policy']['exit']
    unrenderable = 'api_error' if state['mode'] == 'api' else 'checker_error'
    try:                                               # rendered before anything is written: a fault is typed
        summary = render.summary_markdown(verdict)
        if state['withheld'] is not None:
            summary += withhold.summary_markdown(state['withheld'])
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
    say('Assure: %s; policy exit %d; %s' % (_cmd_data(verdict['outcome']), code, _cmd_data(out_text)))
    outputs(verdict['outcome'], code)
    return code


if __name__ == '__main__':
    _env = dict(os.environ)
    scrub_process_env(os.environ)
    sys.exit(main(_env, root=_ROOT))

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
