"""The Action's client of the hosted Assure API (DIRECTOR-DIRECTION-SERVE-003; DD-054). The only module of the Action
that opens a network connection.

    c = Client(base_url, api_key)
    listing = c.profiles()                                  # GET /v1/profiles
    envelope = c.submit(profile_id, files, fail_on)          # POST /v1/checks, then GET /v1/checks/{id} while 202
    record = c.report(check_id)                               # serve-014: POST, then GET /v1/checks/{id}/report while 202

Rules:
- `base_url` is `https://<host>[:port][/prefix]` with no userinfo, query or fragment; `http://` only for a loopback host
  (127.0.0.1, ::1, localhost). TLS verification is the default context's and is never turned off. A redirect is never
  followed (the key could otherwise reach another host): a 3xx answer is `api_error`. Loopback requests use no proxy.
- The key goes only in `Authorization: Bearer`. No error text holds the key, a request body or a response header.
- One submit sends one `Idempotency-Key` (32 hex) and reuses it on every retry, so the server creates and charges the
  check once. By default it is random; `key_from_bundle=True` (serve-023, the Action's default) derives it from the
  request's content with `check_key`, so a later submit of the same request gets the stored check back (the server's
  idempotency: 200 with the stored envelope, not charged again) and a changed byte is a new check. serve-035 (DD-094
  §7 (4)): fail-on is applied at render on the stored verdict, so the key leaves it out: one bundle under any policy is
  one key, one check and one charge, and each answer is decided under the fail-on this submit sends.
- Delivery failures (refused or reset connection, DNS, TLS, timeout, a 5xx with no failure envelope, a body that is not
  bounded JSON or has no known schema, a body over 16 MiB) are retried on the same route with bounded backoff (3
  attempts by default), then raised as `api_unreachable` (connection) or `api_error` (bad answer). `server_busy` is
  retried the same way. `rate_limited` waits for `Retry-After` once when it is at most 60 s. A typed failure envelope
  is raised as a Refusal with the server's outcome, reason and check id (an outcome name this client does not know is
  `api_error`), and `detail.answered` naming the request the API answered: 'profiles', 'check' or 'poll' (a refused
  poll also carries `detail.sent_check_id`, the id from the 202); `unauthenticated`, `bad_input`, `oversize_input`, `unknown_profile`, `credit_exhausted`,
  `profile_not_servable` and every outcome of a check that ran are never retried.
- A 202 is polled with bounded backoff until a final envelope or `total_wait_s`, then `checker_timeout`.
- `fail_on` is sent in its canonical form (`canonical_fail_on`, serve-025's, carried by serve-035: lower case, no
  spaces, each word once, sorted); the server checks it against the profile and decides the exit. The poll of a 202
  sends it too (`GET /v1/checks/{id}?fail_on=...`), so the verdict is decided under it.
  `allow_partial=True` adds `allow_partial=1` to the query; false sends nothing (the server's default).
- `scope`, `scope_binding` (the body's form, {<map>: {id: token}[, <record>: {...}]}, serve-010) and
  `accepted_scope_ref` are request-body fields when given, never `files` entries; unset, the body is byte for byte what
  it was. The server checks them against the profile row (serve-006 gap 1).
- `report(check_id)` (serve-014) asks for a verdict's claim-tree report: `POST /v1/checks/{id}/report` with an empty
  body, then `GET` the same route while 202, with the same backoff and `total_wait_s` bound (past it, `api_error`); a
  typed refusal carries `detail.answered = 'report'`. The answer must be a report record (`assure.serve.report/v1`,
  status written or withheld), else `api_error`. serve-015: `allow_overage=True` sends the body
  `{"allow_overage":true}` (the operator pays overage beyond the monthly allowance); false sends the empty body as
  before. `allowance_exhausted` is never retried.
Every failure is a typed Refusal; nothing here returns a pass that did not come from the server.

`allow_list(listing, profile_id)` builds a profile's allow-list from `GET /v1/profiles`: exact paths and full-match
patterns, each with a byte cap, plus the API's global limits. It has the attributes `serve.bundle` reads (`id`,
`required`, `optional`, rules with `path`, `pattern`, `max_bytes`, `matches`), so `serve.bundle.from_directory` and
`check_files` bound an upload in the runner with the same rules the server applies again. Its `scope` is the listing's
`{max_ids, binding[, records]}` for a row whose scope comes with the request (the binding map's name and the record
names, so the Action can check the keys of the `scope_binding` it sends), else None.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from serve import bundle
from serve.outcomes import OUTCOMES, Refusal

VERDICT_SCHEMA = 'assure.serve.verdict/v1'
FAILURE_SCHEMA = 'assure.serve.failure/v1'
REPORT_SCHEMA = 'assure.serve.report/v1'
DEFAULT_URL = 'https://api.symbolia.ai'
LOOPBACK = frozenset({'127.0.0.1', '::1', 'localhost'})
MAX_RESPONSE = 16 * 2 ** 20
RESPONSE_LIMITS = bundle.Limits(body_bytes=MAX_RESPONSE, file_bytes=MAX_RESPONSE, files=1, json_depth=128)
MAX_KEY = 512
MAX_RETRY_AFTER_S = 60
NEVER_RETRY = frozenset({'unauthenticated', 'bad_input', 'oversize_input', 'unknown_profile', 'credit_exhausted',
                         'profile_not_servable', 'allowance_exhausted'})
RETRY_TYPED = frozenset({'server_busy'})
CHECK_ID_RE = re.compile(r'[0-9a-f]{32}')
_KEY_OK = re.compile(r'[\x21-\x7e]+')
_TEXT_CAP = 300
_CLIENT_KEYS = frozenset({'check_id', 'answered', 'sent_check_id'})    # set by the client only, never by a server


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Every 3xx stays an HTTPError: nothing is re-sent to another location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Delivery(Exception):
    """A delivery failure: `kind` is 'unreachable' (connection level) or 'error' (a bad answer)."""

    def __init__(self, kind, reason):
        super().__init__(reason)
        self.kind, self.reason = kind, reason


def _clip(value):
    s = '' if value is None else str(value)
    s = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', s)
    return s if len(s) <= _TEXT_CAP else s[:_TEXT_CAP - 1] + '…'


def _digest_of(value):
    """sha256 hex of a JSON value encoded as the request body encodes it, or None for None."""
    if value is None:
        return None
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def canonical_fail_on(text):
    """serve-025, carried by serve-035 (DD-094 §7 (3)): the fail-on words as one canonical query value: each
    comma-separated word stripped of spaces and lower-cased, each once, sorted, joined with commas, so "fails,deviates",
    "fails, deviates" and "deviates,fails" are one policy. An empty word stays (the server still refuses it); None and
    '' are returned as given (no query)."""
    if not text:
        return text
    return ','.join(sorted({w.strip().lower() for w in str(text).split(',')}))


def check_key(profile_id, files, query, *, scope=None, scope_binding=None, requirements=None, repository=None,
              commit=None, provenance=None):
    """serve-023: the Idempotency-Key of one request, derived from its content: the first 32 hex of
    sha256(canonical JSON of {bundle_sha256, profile, scope_sha256, scope_binding_sha256, requirements_sha256,
    repository, commit, provenance, query}).
    `bundle_sha256` is the digest of the bundle's manifest ([{path, bytes, sha256}] sorted by path, the manifest the
    server computes); `scope_sha256` and `scope_binding_sha256` are the digests of those body fields (null when unset);
    `requirements_sha256` is the sha256 of the requirements text's UTF-8 bytes (the digest the server keeps with the
    check), null when no text is sent; `repository`, `commit` and `provenance` are the body's own values, null when
    unset (serve-025 merge with serve-019), so a new commit on an unchanged bundle is a new check; `query` is the query
    string the server's key compares: serve-035 (DD-094 §7 (4)), every parameter as sent but `fail_on` (`allow_partial`;
    `submit` passes it), so the key never holds the fail-on words. The server compares the body and that query and
    answers a repeated key whose request differs with `bad_input`; fail-on is applied at render on the stored verdict,
    so a repeat under another fail-on is the same check, decided under the fail-on it sends. The key is a digest of the
    whole document, never the bundle digest itself."""
    manifest = [{'path': n, 'bytes': len(files[n]), 'sha256': hashlib.sha256(bytes(files[n])).hexdigest()}
                for n in sorted(files)]
    req = None if requirements is None else hashlib.sha256(requirements.encode('utf-8')).hexdigest()
    doc = {'bundle_sha256': bundle.bundle_sha256(manifest), 'profile': profile_id, 'scope_sha256': _digest_of(scope),
           'scope_binding_sha256': _digest_of(scope_binding), 'requirements_sha256': req, 'repository': repository,
           'commit': commit, 'provenance': provenance, 'query': query or ''}
    return hashlib.sha256(bundle.canonical_json(doc)).hexdigest()[:32]


def check_base_url(text):
    """(scheme, host, base URL without a trailing slash) or `bad_input`."""
    reason = 'api-url must be https://<host> with no user, query or fragment (http:// only for a loopback host)'
    if not isinstance(text, str) or not text or len(text) > 2048 or re.search(r'[\x00-\x20\x7f-\x9f]', text):
        raise Refusal('bad_input', reason)
    try:
        parts = urllib.parse.urlsplit(text)
        host = parts.hostname
        parts.port                                    # a malformed port raises ValueError
    except ValueError:
        raise Refusal('bad_input', reason) from None
    if (parts.scheme not in ('https', 'http') or not host or '@' in parts.netloc or parts.query or parts.fragment
            or '?' in text or '#' in text):
        raise Refusal('bad_input', reason)
    if parts.scheme == 'http' and host not in LOOPBACK:
        raise Refusal('bad_input', 'api-url must use https:// (http:// is accepted only for a loopback host)')
    return parts.scheme, host, text.rstrip('/')


class Client:
    def __init__(self, base_url, api_key, *, timeout_s=30, total_wait_s=300, attempts=3, opener=None,
                 sleep=time.sleep, clock=time.monotonic, backoff_s=(1, 2, 4), poll_s=(1, 2, 4, 8, 15),
                 max_response=MAX_RESPONSE):
        self.scheme, self.host, self.base = check_base_url(base_url)
        if not isinstance(api_key, str) or not api_key or len(api_key) > MAX_KEY or not _KEY_OK.fullmatch(api_key):
            raise Refusal('bad_input', 'api-key is required in api mode, as one line of printable text; pass it '
                                       'from a secret')
        self._auth = 'Bearer ' + api_key
        self.timeout_s = float(timeout_s)
        self.total_wait_s = float(total_wait_s)
        self.attempts = max(1, int(attempts))
        self.sleep, self.clock = sleep, clock
        self.backoff_s, self.poll_s = tuple(backoff_s) or (1,), tuple(poll_s) or (1,)
        self.max_response = int(max_response)
        if opener is None:
            handlers = [_NoRedirect()]
            if self.host in LOOPBACK:
                handlers.append(urllib.request.ProxyHandler({}))
            if self.scheme == 'https':
                handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            opener = urllib.request.build_opener(*handlers)
        self.opener = opener

    def __repr__(self):                       # never the key
        return 'Client(%r)' % self.base

    # ---------- one HTTP exchange ----------
    def _read(self, fp):
        try:
            data = fp.read(self.max_response + 1)
        except (OSError, http.client.HTTPException) as e:
            raise _Delivery('unreachable' if isinstance(e, OSError) else 'error',
                            'the answer could not be read (%s)' % type(e).__name__) from None
        if len(data) > self.max_response:
            raise _Delivery('error', 'the answer is larger than %d bytes' % self.max_response)
        return data

    def _exchange(self, method, path, body=None, headers=None):
        """(status, Retry-After text or None, body bytes); _Delivery on a connection or read failure."""
        h = {'Authorization': self._auth, 'Accept': 'application/json', 'User-Agent': 'assure-action'}
        if body is not None:
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)
        try:
            resp = self.opener.open(req, timeout=self.timeout_s)
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.headers.get('Retry-After') if e.headers is not None else None, self._read(e)
            finally:
                e.close()
        except urllib.error.URLError as e:
            why = e.reason
            kind = 'TLS' if isinstance(why, ssl.SSLError) else type(why).__name__ if isinstance(why, BaseException) \
                else 'connection'
            raise _Delivery('unreachable', 'the API could not be reached (%s)' % kind) from None
        except (OSError, ValueError) as e:            # timeout, reset, refused; ValueError: a malformed answer line
            raise _Delivery('unreachable', 'the API could not be reached (%s)' % type(e).__name__) from None
        except http.client.HTTPException as e:
            raise _Delivery('error', 'the API answer is malformed (%s)' % type(e).__name__) from None
        try:
            return resp.status, resp.headers.get('Retry-After'), self._read(resp)
        finally:
            resp.close()

    @staticmethod
    def _doc(data):
        try:
            return bundle.parse_json(data, RESPONSE_LIMITS)
        except Refusal:
            raise _Delivery('error', 'the API answer is not bounded JSON') from None

    @staticmethod
    def _typed(doc, status, route):
        """The Refusal for a failure envelope. A known outcome carries `detail.answered = route`, the request the API
        answered: 'profiles' (`GET /v1/profiles`, before anything is collected or sent), 'check' (`POST /v1/checks`,
        the upload left the runner) or 'poll' (`GET /v1/checks/{id}`, the check was sent). It is set last, so the
        server's own detail can neither unset nor change it; a server `sent_check_id` is dropped (only the client's
        own 202 gives one) (refutation-010 G1, round 2 G1)."""
        name = doc.get('outcome')
        cid = doc.get('check_id')
        detail = {}
        if isinstance(cid, str) and CHECK_ID_RE.fullmatch(cid):
            detail['check_id'] = cid
        if not isinstance(name, str) or name not in OUTCOMES or name in ('api_unreachable', 'api_error'):
            return Refusal('api_error', 'the API answered %s with an outcome this Action does not know: %s'
                           % (status, _clip(name)[:64]), **detail)
        extra = doc.get('detail')
        if isinstance(extra, dict):
            for k, v in list(extra.items())[:16]:
                if isinstance(k, str) and re.fullmatch(r'[a-z_]{1,32}', k) and k not in _CLIENT_KEYS \
                        and (v is None or isinstance(v, (bool, int, float)) or isinstance(v, str)):
                    detail[k] = _clip(v) if isinstance(v, str) else v
        detail['answered'] = route       # which request the API answered: the page says what left the runner
        return Refusal(name, _clip(doc.get('reason')), **detail)

    def _call(self, method, path, body=None, headers=None, *, route):
        """Send with retries on the same route (`route` names it for `_typed`). Returns (status, doc) for 200 and 202 with a parsed object; raises the
        typed Refusal for a failure envelope, `api_unreachable` or `api_error` once the attempts are spent."""
        waited_retry_after = False
        attempt = 0
        last = None
        while True:
            attempt += 1
            try:
                status, retry_after, data = self._exchange(method, path, body, headers)
                if 300 <= status < 400:
                    raise Refusal('api_error', 'the API answered with a redirect (%d), which the Action never follows'
                                  % status)
                try:
                    doc = self._doc(data)
                except _Delivery:
                    if status >= 500 or status in (200, 202):
                        raise
                    raise Refusal('api_error', 'the API answered %d without a failure envelope' % status) from None
                if isinstance(doc, dict) and doc.get('schema') == FAILURE_SCHEMA:
                    refusal = self._typed(doc, status, route)
                    if refusal.outcome == 'rate_limited' and not waited_retry_after:
                        wait = _retry_after(retry_after)
                        if wait is not None and wait <= MAX_RETRY_AFTER_S:
                            waited_retry_after = True
                            self.sleep(wait)
                            attempt -= 1                 # the honoured wait is not a delivery attempt
                            continue
                    if refusal.outcome in RETRY_TYPED and attempt < self.attempts:
                        last = refusal
                        self.sleep(self._backoff(attempt))
                        continue
                    raise refusal
                if status in (200, 202) and isinstance(doc, dict):
                    return status, doc
                if status >= 500 or status in (200, 202):
                    raise _Delivery('error', 'the API answered %d without a known envelope' % status)
                raise Refusal('api_error', 'the API answered %d without a failure envelope' % status)
            except _Delivery as d:
                last = d
                if attempt >= self.attempts:
                    break
                self.sleep(self._backoff(attempt))
        if isinstance(last, Refusal):
            raise last
        outcome = 'api_unreachable' if last.kind == 'unreachable' else 'api_error'
        raise Refusal(outcome, '%s, after %d attempts' % (last.reason, attempt), attempts=attempt)

    def _backoff(self, attempt):
        return self.backoff_s[min(attempt - 1, len(self.backoff_s) - 1)]

    # ---------- the routes ----------
    def profiles(self):
        """The `GET /v1/profiles` answer (the served profiles' input allow-lists and the global limits)."""
        status, doc = self._call('GET', '/v1/profiles', route='profiles')
        if status != 200:
            raise Refusal('api_error', 'the profile list answered %d' % status)
        return doc

    def submit(self, profile_id, files, fail_on=None, *, body=None, allow_partial=False, scope=None,
               scope_binding=None, accepted_scope_ref=None, limits=None, requirements=None, repository=None,
               commit=None, provenance=None, key_from_bundle=False):
        """Send one check and return the final verdict envelope (a dict with schema assure.serve.verdict/v1). Every
        other end is a Refusal. `body` is the encoded upload when the caller has already built it; otherwise it is
        built here under `limits` (default the serving limits) with the scope fields and the serve-019 requirements
        fields (requirements, repository, commit, provenance) that are not None.
        `key_from_bundle=True` sends `check_key` of the request (it needs `files`), else a random key."""
        started = self.clock()
        if key_from_bundle and (files is None or body is not None):
            raise ValueError('a key from the bundle is derived from the files and the scope fields, not a built body')
        if body is None:
            body = bundle.request_body(profile_id, files, limits if limits is not None else bundle.LIMITS, scope=scope,
                                       scope_binding=scope_binding, accepted_scope_ref=accepted_scope_ref,
                                       requirements=requirements, repository=repository, commit=commit,
                                       provenance=provenance)
        elif (scope, scope_binding, accepted_scope_ref, requirements, repository, commit,
              provenance) != (None,) * 7:
            raise ValueError('pass the scope fields or a built body, not both')
        path = '/v1/checks'
        query = {}
        if fail_on:
            query['fail_on'] = canonical_fail_on(fail_on)
        if allow_partial is True:
            query['allow_partial'] = '1'
        query_text = urllib.parse.urlencode(query) if query else ''
        if query_text:
            path += '?' + query_text
        poll_query = '?' + urllib.parse.urlencode({'fail_on': query['fail_on']}) if 'fail_on' in query else ''
        if key_from_bundle:      # serve-035: the key's query leaves fail_on out (check_key)
            keyed = urllib.parse.urlencode({k: v for k, v in query.items() if k != 'fail_on'})
            idem = check_key(profile_id, files, keyed, scope=scope, scope_binding=scope_binding,
                             requirements=requirements, repository=repository, commit=commit, provenance=provenance)
        else:
            idem = secrets.token_hex(16)
        status, doc = self._call('POST', path, body, {'Idempotency-Key': idem}, route='check')
        polls = 0
        while status == 202:
            cid = doc.get('check_id')
            if not isinstance(cid, str) or not CHECK_ID_RE.fullmatch(cid):
                raise Refusal('api_error', 'the API answered 202 without a check id')
            if self.clock() - started >= self.total_wait_s:
                raise Refusal('checker_timeout', 'the check did not finish within %d s; check %s'
                              % (int(self.total_wait_s), cid), check_id=cid)
            self.sleep(self.poll_s[min(polls, len(self.poll_s) - 1)])
            polls += 1
            try:
                status, doc = self._call('GET', '/v1/checks/' + cid + poll_query, route='poll')
            except Refusal as e:
                if e.detail.get('answered') == 'poll' and 'check_id' not in e.detail:
                    e.detail['sent_check_id'] = cid          # the poll was refused; the 202 named the check
                raise
        if doc.get('schema') != VERDICT_SCHEMA:
            raise Refusal('api_error', 'the API answered without a verdict envelope')
        return doc

    def report(self, check_id, *, allow_overage=False):
        """serve-014: the claim-tree report record of one verdict (module docstring). Every other end is a Refusal."""
        if not isinstance(check_id, str) or not CHECK_ID_RE.fullmatch(check_id):
            raise Refusal('bad_input', 'a report needs the check id of a verdict')
        started = self.clock()
        path = '/v1/checks/%s/report' % check_id
        body = b'{"allow_overage":true}' if allow_overage is True else b''     # serve-015
        status, doc = self._call('POST', path, body, route='report')
        polls = 0
        while status == 202:
            if self.clock() - started >= self.total_wait_s:
                raise Refusal('api_error', 'the report did not finish within %d s' % int(self.total_wait_s),
                              report_running=True)     # serve-015: still being written; the page will hold it
            self.sleep(self.poll_s[min(polls, len(self.poll_s) - 1)])
            polls += 1
            status, doc = self._call('GET', path, route='report')
        if doc.get('schema') != REPORT_SCHEMA or doc.get('status') not in ('written', 'withheld') \
                or (doc.get('status') == 'written' and not isinstance(doc.get('body_md'), str)):
            raise Refusal('api_error', 'the API answered without a report record')
        return doc


# ---------- the allow-list from GET /v1/profiles ----------
MAX_NAME = 200
MAX_PATTERN = 512
MAX_RULES = 256
ID_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
# Ceilings on the limits a listing may announce: a listing beyond them is a malformed answer, never a wider gate.
CEILING = {'body_bytes': 64 * 2 ** 20, 'file_bytes': 64 * 2 ** 20, 'files': 4096, 'json_depth': 128}


@dataclass(frozen=True)
class Rule:
    path: str | None
    pattern: str | None
    max_bytes: int
    _re: object = field(default=None, compare=False, repr=False)

    def matches(self, name):
        if self.path is not None:
            return name == self.path
        return self._re.fullmatch(name) is not None


@dataclass(frozen=True)
class AllowList:
    id: str
    required: tuple
    optional: tuple
    limits: bundle.Limits = bundle.LIMITS
    scope: dict | None = None


def _bad_listing(why):
    return Refusal('api_error', 'the API profile list is malformed: %s' % why)


def _safe_path(p):
    return (isinstance(p, str) and p.startswith('raw/') and len(p) <= MAX_NAME and '\\' not in p
            and not any(ord(c) < 32 or ord(c) == 127 for c in p)
            and all(seg not in ('', '.', '..') for seg in p.split('/')))


def _rule(r, required):
    keys = set(r) if isinstance(r, dict) else None
    allowed = ({'path', 'max_bytes'},) if required else ({'path', 'max_bytes'}, {'pattern', 'max_bytes'})
    if keys not in allowed:
        raise _bad_listing('an input rule has unexpected keys')
    mb = r['max_bytes']
    if type(mb) is not int or mb <= 0:
        raise _bad_listing('max_bytes must be a positive integer')
    if 'path' in r:
        if not _safe_path(r['path']):
            raise _bad_listing('an input path is not a safe raw/ path')
        return Rule(r['path'], None, mb)
    pat = r['pattern']
    if not isinstance(pat, str) or not pat.startswith('raw/') or len(pat) > MAX_PATTERN:
        raise _bad_listing('a pattern must begin raw/ and be at most %d characters' % MAX_PATTERN)
    try:
        rx = re.compile(pat)
    except re.error:
        raise _bad_listing('a pattern does not compile') from None
    return Rule(None, pat, mb, rx)


def _limits(doc):
    if doc is None:
        return bundle.LIMITS
    if not isinstance(doc, dict) or set(doc) != set(CEILING):
        raise _bad_listing('limits must hold exactly %s' % ', '.join(sorted(CEILING)))
    for k, v in doc.items():
        if type(v) is not int or v <= 0 or v > CEILING[k]:
            raise _bad_listing('limit %s is not a positive integer within its ceiling' % k)
    return bundle.Limits(**doc)


SCOPE_NAME_RE = re.compile(r'[a-z][a-z0-9_]{0,31}')


def _scope(doc):
    """serve-006 gap 1: a listed row's `scope` ({max_ids, binding[, records]}), or None when the row lists none.
    `records` (serve-010) is the list of binding-record names the wrapper must carry beside the map."""
    if doc is None:
        return None
    if (not isinstance(doc, dict) or not {'max_ids', 'binding'} <= set(doc) <= {'max_ids', 'binding', 'records'}
            or type(doc['max_ids']) is not int or not 1 <= doc['max_ids'] <= 256
            or not (doc['binding'] is None or (isinstance(doc['binding'], str) and SCOPE_NAME_RE.fullmatch(doc['binding'])))):
        raise _bad_listing('a profile scope must be {max_ids: 1 to 256, binding: a lower-case name or null[, records]}')
    out = {'max_ids': doc['max_ids'], 'binding': doc['binding']}
    if 'records' in doc:
        rec = doc['records']
        if (doc['binding'] is None or not isinstance(rec, list) or not rec or len(set(rec)) != len(rec)
                or not all(isinstance(n, str) and SCOPE_NAME_RE.fullmatch(n) and n != doc['binding'] for n in rec)):
            raise _bad_listing('a profile scope records list must name distinct binding records')
        out['records'] = list(rec)
    return out


def allow_list(listing, profile_id):
    """The allow-list of `profile_id` from a `GET /v1/profiles` answer. `unknown_profile` when the API does not list
    it; `api_error` when the answer is malformed."""
    if not isinstance(profile_id, str) or not ID_RE.fullmatch(profile_id):
        raise Refusal('unknown_profile', 'no profile with that id')
    if not isinstance(listing, dict) or not isinstance(listing.get('profiles'), list):
        raise _bad_listing('no profiles list')
    limits = _limits(listing.get('limits'))
    for row in listing['profiles']:
        if not isinstance(row, dict) or row.get('id') != profile_id:
            continue
        inputs = row.get('inputs')
        if (not isinstance(inputs, dict) or not isinstance(inputs.get('required'), list)
                or not isinstance(inputs.get('optional'), list)
                or len(inputs['required']) + len(inputs['optional']) > MAX_RULES):
            raise _bad_listing('profile %s has no inputs {required, optional}' % profile_id)
        return AllowList(profile_id, tuple(_rule(r, True) for r in inputs['required']),
                         tuple(_rule(r, False) for r in inputs['optional']), limits, _scope(row.get('scope')))
    raise Refusal('unknown_profile', 'the API serves no profile %s' % profile_id)


def _retry_after(text):
    if text is None:
        return None
    t = str(text).strip()
    return int(t) if re.fullmatch(r'[0-9]{1,6}', t) else None

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
