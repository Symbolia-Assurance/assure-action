"""python-auth's declaration, drafted in the runner and proposed for one-step acceptance (serve-102; DD-150, DD-156).

When the files sent for profile python-auth-declared-model hold no `raw/declaration.json`, the Action drafts one from
the repository bytes it sends and runs the check on the draft. The verdict is then bounded by an unaccepted draft:
the log, the job summary and the step output `declaration=unaccepted-draft` say so. Under the Director's rule of 11 Oct
2026 (Assure never writes into the repository; it provides a pull request), the draft is proposed in a pull request
of Assure's own: one commit on the base branch's tip that writes only the drafts' files (issue #2927: each profile's
at its own path, a second drafter's added beside the first's while the open pull request's body names it), pushed
only to the branch `assure/declaration-proposal`, and a pull request from that branch into the base branch (the pull
request's base, or the repository's default branch on any other event); an open one is updated, never duplicated. Merging it is the
acceptance. A run on a pull request whose declaration is not yet on the base branch is bounded the same way.

The Action delegates drafting to POST /v1/declaration-proposal, which calls the identity engine's
`assure.checkers.identity.proposal.propose`. The five-field record, including per-leaf sources and confirm,
returns unchanged. A partial draft retains unread fields for review; the checker's admission still decides whether
it can check that declaration. No checker code is copied into the public Action.

Standard library, serve.outcomes and the caller's action.client.Client only. The child processes are git
with an argument list: read-only reads of the checkout, and for the proposal `fetch`, `hash-object -w`,
`read-tree`/`update-index`/`write-tree` on a private index, `commit-tree` and `push` of that one commit to
`assure/declaration-proposal` (and its deletion when the pull request cannot be opened). The work tree and the index are
never touched. execution_authorized false; hardware_authorized false; industrial_release_authorized false;
release_allowed false; physical_validation false; simulation true; self_approved false."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from serve import FLAGS
from serve.outcomes import Refusal

PROFILE = 'python-auth-declared-model'
NAME = 'raw/declaration.json'
CHECKOUT_PATH = '.assure/declaration.json'          # where an accepted declaration lives in a checked-out repository
PROPOSAL_SCHEMA = 'assure.identity.declaration-proposal/v1'
STACK = 'python/flask'
SCHEMA = 'assure.python-auth.declaration/v1'
PROPOSAL_BRANCH = 'assure/declaration-proposal'   # Assure's own branch; never the base, the head or the default
TITLE = 'Assure: proposed intent \u2014 review and merge to accept'   # issue #2927: one title for every profile's draft
NEVER_COMMITS = ('Assure never commits to your branches; it opens one pull request proposing each profile\'s draft at '
                 'its own path under .assure/; merging it is the acceptance.')
_SECTION = '<!-- assure-draft: %s -->'                 # issue #2927: where one file's section of the body starts
PERMISSIONS_SENTENCE = ('to open the proposal, give the workflow `contents: write` and `pull-requests: write` under '
                        '`permissions:` (and let GitHub Actions create pull requests in the repository settings)')
BOT = ('github-actions[bot]', '41898282+github-actions[bot]@users.noreply.github.com')
OUTPUT_BOUNDED = 'declaration=unaccepted-draft'
BOUNDED = 'bounded by an unaccepted declaration draft'
SIGNOUT = re.compile(r'(log|sign)_?(out|off)', re.I)
GIT_TIMEOUT_S = 60
SKIP_DIRS = frozenset({'tests', 'test', 'docs', 'migrations'})
SHORTCUTS = {'get': 'GET', 'post': 'POST', 'put': 'PUT', 'patch': 'PATCH', 'delete': 'DELETE'}
JUDGEMENT = ('/session_identity_key', '/guards', '/identity_writers', '/elevation_writers', '/signout_views',
             '/public_routes', '/registrations_complete', '/session_elevation_keys', '/second_factor_keys')
_ID = re.compile(r'[^A-Za-z0-9_.-]+')
# The declaration fields the drafter reads from the code; one it could not read is left out of the draft. The checker
# checks such a draft (issue #3899): an absent app_roots reads the repository root, and the obligations that read any
# other absent field read not established naming it (grade.ABSENT_NEEDS). A server before #3899 refuses the draft
# (profile_refused, declaration_invalid, keyword required) until the customer adds the field. Issue #3969: a refusal's
# next step always names a left-out READ_REQUIRED field (without app_objects no route is read; identity_writers is
# AUTH-3's premise), and a READ_DEFAULTED one only while the refusal shows the check still requires it
# (unread_refused); a verdict's declaration section on a python/flask draft names, in FIELD_WORDS, every READ_ORDER
# field the draft left out with what its default reads (summary_markdown `defaulted`, DEFAULT_READS).
READ_REQUIRED = ('app_objects', 'identity_writers')
READ_DEFAULTED = ('app_roots', 'session_identity_key', 'guards')
READ_ORDER = ('app_roots', 'app_objects', 'session_identity_key', 'guards', 'identity_writers')   # main's READ_REQUIRED
DEFAULT_READS = {'app_roots': "the repository's top-level Python entries are read as the app roots",
                 'app_objects': 'no app object: no route is read, every obligation reads not established and the '
                                'check reads yellow',
                 'session_identity_key': 'no session identity key: AUTH-3/4/5 not established',
                 'guards': 'no guard: no obligation is decided (each reads not established unless its reading is '
                           'a representation one) and the check reads yellow',
                 'identity_writers': 'no identity writer: AUTH-3 not established'}
# Issue #3118 (the Director, 16 Oct 2026; DD-150, DD-161 Add.6): the declaration is internal, so no line the customer
# reads names one of its fields. Each field of the python-auth declaration schema (python-auth-declaration-v1.schema.json)
# the customer could be asked about, in the customer's own terms; tests/serving/test_customer_words_accept.py reads the
# schema and holds this map to it. BOOKKEEPING names the rest: fields the drafter always writes and never asks about.
FIELD_WORDS = {
    'app_roots': 'where your Flask app is created',
    'app_objects': 'where your Flask app is created',
    'session_identity_key': 'which session value holds the signed-in user',
    'session_state_keys': 'which other session values your app keeps',
    'session_elevation_keys': 'which session values mark raised access',
    'second_factor_keys': 'which session values record a second sign-in step',
    'guards': 'which decorators protect your routes',
    'identity_writers': 'where the signed-in user is set',
    'elevation_writers': 'where a session is given raised access',
    'signout_views': 'where users sign out',
    'libraries': 'which sign-in libraries your app uses',
    'public_routes': 'which routes anyone may open without signing in',
    'registrations_complete': 'whether Assure read every route your app registers',
    'requirements_file': 'where your requirements file is',
    'instance_config': 'how your app loads its instance configuration',
}
BOOKKEEPING = ('schema', 'id', 'language', 'idiom') + tuple(FLAGS)
# Issue #2926: the Action's per-profile intent contract. It lives here, not in serve/profiles/*.json: the profile rows
# refuse unknown keys (serve/profiles.py ROW_KEYS) and the public tree ships no profile row (action/build_dist.py).
# A row names the profile whose run drafts intent, the drafter, and the checkout path the declared profile reads it at
# (action.entry.checkout_declaration reads CHECKOUT_PATH). postgresql-declared-model drafts its own on a connection run
# with no checkout declaration (issue #2435 pg_declare); postgresql-observed-baseline writes its proposal beside the
# verdict (action.entry.write_proposal) and, inside a checkout where `checkout_declaration` finds nothing at either
# path, proposes it at the declared profile's own path (issue #2934, action.entry.observed_draft). That run stats and,
# when present, reads both checkout paths (`reads`, in `checkout_declaration`'s order) only to decide not to propose
# over a committed declaration; its verdict reads neither, so it is not in READS_INTENT. Read by tests only until
# #2249's other parts read it.
INTENT_FLOWS = {
    PROFILE: {'drafter': 'action.declaration_draft.draft', 'intent_path': CHECKOUT_PATH, 'declared_profile': PROFILE},
    'postgresql-declared-model': {'drafter': 'action.entry.draft_proposal',          # via assure.declare_proposal
                                  'intent_path': CHECKOUT_PATH, 'declared_profile': 'postgresql-declared-model'},
    'postgresql-observed-baseline': {'drafter': 'action.entry.draft_proposal',       # via action.entry.observed_draft
                                     'intent_path': '.assure/postgresql-declared-model.json',   # DECLARED_CHECKOUT_PATH
                                     'declared_profile': 'postgresql-declared-model',
                                     'reads': ('.assure/postgresql-declared-model.json', CHECKOUT_PATH)},
}
NO_DRAFTER = ('http-observed-baseline', 'mysql-declared-model')
READS_INTENT = ('postgresql-declared-model',)      # drafts only on a connection run with no checkout declaration
NO_DRAFTER_NOTE = '`%s` has no intent drafter yet; Assure drafts no declaration for it, so this check reads %s.'
NO_DRAFTER_READS = {'http-observed-baseline': 'only what was observed',
                    'mysql-declared-model': 'the declaration supplied with the run'}   # a declared model
READS_INTENT_NOTE = ('`%s` reads the declaration supplied with the run; Assure drafts one only on its own connection '
                     'run with no `' + CHECKOUT_PATH + '` in the checkout, and proposes it in its own pull request.')


_IMPORT = re.compile(rb'(?m)^[ \t]*(?:from|import)[ \t]+(flask|fastapi|django)\b')
FRAMEWORK_STACKS = {b'fastapi': 'python/fastapi', b'django': 'python/django'}   # issue #3376; flask is STACK


# issue #4590: a repository that serves HTTP with the standard library and imports no web framework
_HTTP_SERVER = re.compile(rb'(?m)^[ \t]*(?:from[ \t]+http\.server[ \t]+import\b|import[ \t]+http\.server\b)')
STDLIB_STACK = 'python/stdlib-http'
STDLIB_REASON = ('this repository serves HTTP with the standard library (http.server) and imports no web framework; '
                 'Assure drafts declarations for Flask, FastAPI and Django only, so write the declaration: '
                 'schema assure.identity.declaration/v1 with stack python/stdlib-http, committed at '
                 + CHECKOUT_PATH + ' (QUICKSTART-API.md, the python-auth-declared-model section, lists its fields)')


def stack_of(files):
    """Issue #3376: the identity stack the repository's Python files import: python/fastapi or python/django when
    that is the one web framework they import, STACK (main's reading) when they import Flask, more than one framework
    or none. Issue #4590: STDLIB_STACK when they import no web framework and import http.server."""
    py = [bytes(d) for n, d in files.items() if str(n).endswith('.py') and isinstance(d, (bytes, bytearray))]
    seen = {m for d in py for m in _IMPORT.findall(d)}
    if not seen and any(_HTTP_SERVER.search(d) for d in py):
        return STDLIB_STACK
    return FRAMEWORK_STACKS.get(seen.pop(), STACK) if len(seen) == 1 else STACK


def draft(files, repository_id=None, *, client, library_versions=None):
    """The engine's proposal record for the repository's stack (`stack_of`); incomplete fields retain their unread
    sources for review. A Flask repository is sent as on main (no `stack`). `library_versions`: the derived
    raw/LIBRARY-VERSIONS.json bytes the collector sends (issue #3128), or None."""
    stack = stack_of(files)
    if stack == STDLIB_STACK:
        raise Refusal('bad_input', STDLIB_REASON)
    args = {}
    if stack != STACK:
        args['stack'] = stack
    if library_versions is not None:
        args['library_versions'] = library_versions
    return client.declaration_proposal(files, **args)


def dumps(decl):
    return (json.dumps(decl, indent=2) + '\n').encode('utf-8')


def repository_id(env):
    name = str(env.get('GITHUB_REPOSITORY') or '').rsplit('/', 1)[-1]
    name = _ID.sub('-', name).strip('-.')[:128]
    return name if name and name[0].isalnum() else None


# ---------------------------------------------------------------------------------------------------------- git
def _git(top, env, *args, data=None, extra=None):
    child = {k: env[k] for k in ('PATH', 'HOME', 'SYSTEMROOT') if env.get(k)}
    child.setdefault('PATH', '/usr/bin:/bin')
    child['GIT_TERMINAL_PROMPT'] = '0'
    child.update(extra or {})
    try:
        p = subprocess.run(['git', '-C', str(top), *args], env=child, input=data, capture_output=True,
                           timeout=GIT_TIMEOUT_S, stdin=None if data is not None else subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _fetch(top, env, branch):
    """Fetch `branch` from origin into FETCH_HEAD; one commit deep when the checkout is already shallow (as
    actions/checkout leaves it), so a full clone never becomes shallow. True when fetched."""
    shallow = (_git(top, env, 'rev-parse', '--is-shallow-repository') or b'').strip() == b'true'
    args = ['fetch', '--quiet', '--no-tags'] + (['--depth=1'] if shallow else []) + ['origin', 'refs/heads/' + branch]
    return _git(top, env, *args) is not None


def toplevel(path, env):
    out = _git(path, env, 'rev-parse', '--show-toplevel')
    return Path(out.decode('utf-8').strip()) if out else None


def on_base(top, rel, data, env):
    """On a pull request: does the base branch carry `rel` with exactly `data`? None when it cannot be read."""
    base = str(env.get('GITHUB_BASE_REF') or '').strip()
    if not base or not _fetch(top, env, base):
        return None
    shown = _git(top, env, 'show', 'FETCH_HEAD:' + rel)
    return shown == bytes(data)


def is_pull_request(env):
    return env.get('GITHUB_EVENT_NAME') in ('pull_request', 'pull_request_target') and bool(env.get('GITHUB_HEAD_REF'))


def _read_at(record, p):
    return record['sources'].get(p) or next((v for k, v in sorted(record['sources'].items())
                                             if k.startswith(p + '/')), 'unread')


def _section(record, rel, source, lead=None):
    """One file's section of the body; `lead`, when given, replaces its first sentence (issue #2934: an observed
    verdict is not bounded by the draft)."""
    lines = [_SECTION % rel, '', lead or 'Assure drafted `%s` from %s and checked your app against the draft. Until this '
             'pull request is merged, every Assure result is bounded by the draft.' % (rel, source), '']
    if isinstance(record.get('stack'), str) and record['stack'] in FRAMEWORK_STACKS.values():
        lines += ['Drafted for the `%s` stack.' % record['stack'], '']     # issue #3376
    lines += ['Fields to confirm:', '']
    lines += ['- %s (%s)' % (label, _where(at)) for label, at in _confirm_rows(record)]
    if record.get('kept'):                          # committed values this run read differently, kept as written
        lines += [''] + list(record['kept'])
    notes = [n.get('note') for n in record.get('to_confirm') or () if isinstance(n, dict) and isinstance(n.get('note'), str)]
    if notes:                                       # issue #2567: routes kept out of public_routes, in plain words
        lines += ['', 'To confirm (routes Assure did not draft as public):', ''] + ['- %s' % n for n in notes]
    return '\n'.join(lines) + '\n'


def _confirm_rows(record):
    """[(label, [where read])] for the record's fields to confirm. Issue #3118: a python-auth record's fields are
    labelled in the customer's terms (FIELD_WORDS), one row per field however many of its leaves are listed; any other
    profile's record keeps one row per pointer, as written."""
    rows, plain = {}, record.get('stack') == STACK
    for p in record['confirm']:
        top = p.strip('/').split('/')[0]
        label = FIELD_WORDS[top][:1].upper() + FIELD_WORDS[top][1:] if plain and top in FIELD_WORDS else '`%s`' % p
        at = rows.setdefault(label, [])
        if _read_at(record, p) not in at:
            at.append(_read_at(record, p))
    return list(rows.items())


def _where(at):
    """Where one row's leaves were read, in words: 'read at a and b', 'not read from the code', or both."""
    read = [a for a in at if a != 'unread']
    out = 'read at ' + _join(read) if read else ''
    if 'unread' in at:
        out = out + '; partly not read from the code' if out else 'not read from the code'
    return out


def _join(items, conj='and'):
    items = list(items)
    return items[0] if len(items) == 1 else '%s %s %s' % (', '.join(items[:-1]), conj, items[-1])


def plain_words(fields):
    """Issue #3118: the customer's terms for declaration `fields`, each phrase once, in order."""
    out = []
    for f in fields:
        if FIELD_WORDS.get(f, f) not in out:
            out.append(FIELD_WORDS.get(f, f))
    return out


def _kept_sections(body, keep):
    """Issue #2927: the sections of an open proposal's `body` for the files in `keep`, in their order there."""
    parts = re.split(r'(?m)^(?=<!-- assure-draft: )', body if isinstance(body, str) else '')
    return [p.rstrip('\n') + '\n' for p in parts[1:] if (m := re.match(r'<!-- assure-draft: (.+?) -->', p))
            and m.group(1) in keep]


def _named(body):
    """Issue #2927: the files an open proposal's `body` has a section for."""
    return set(re.findall(r'(?m)^<!-- assure-draft: (.+?) -->', body if isinstance(body, str) else ''))


def _carried(top, env, existing, parent, rel, named):
    """Issue #3153 (#2249: the one pull request keeps another profile's draft): {path: blob} of the regular files under
    `.assure/` on the proposal branch's tip `existing` that the base tip `parent` does not have, other than `rel`, and
    that the open proposal's body has a section for (`named`, #2927): a file it does not name has no fields to confirm
    and is left behind, as the rebuild from the base tip leaves it."""
    listed = (_git(top, env, 'ls-tree', '-r', '--full-tree', existing, '--', '.assure/') or b'').decode('utf-8', 'replace')
    out = {}
    for line in listed.split('\n'):
        meta, _, path = line.partition('\t')
        parts = meta.split()
        if len(parts) == 3 and parts[:2] == ['100644', 'blob'] and path != rel and path in named \
                and _git(top, env, 'cat-file', '-e', '%s:%s' % (parent, path)) is None:
            out[path] = parts[2]
    return out


def _parent(top, env, commit):
    """The first parent written in `commit`'s own object, or None. Read from the object, not as `commit^`: a commit
    fetched one deep (the shallow checkout actions/checkout leaves) is a shallow boundary, and git resolves no `^` for
    it (issue #2927, REFUTATION-r1 HIGH-1)."""
    raw = (_git(top, env, 'cat-file', 'commit', commit) or b'').decode('utf-8', 'replace').split('\n\n', 1)[0]
    return next((line[7:].strip() for line in raw.split('\n') if line.startswith('parent ')), None)


def pull_request_body(record, rel, source='this repository', kept=(), lead=None):
    """The proposal pull request's body: what it is, how to accept it, and one section per proposed file naming each
    field to confirm and where it was read. `source` names what the draft at `rel` was read from (issue #2435: the
    collected catalog snapshot); `kept` holds the sections of the other files already on the branch (issue #2927);
    `lead` replaces the first sentence of `rel`'s section (issue #2934)."""
    head = ('Read each draft and edit any field that is wrong, on this branch. %s This run is proposing %s; merging the '
            'pull request commits it.\n' % (NEVER_COMMITS, rel))         # issue #3153: this proposal's own path
    return '\n'.join([head] + list(kept) + [_section(record, rel, source, lead)])


PUSH_REFUSED = 'the push to'      # issue #2934: the observed profile reads a refused push as `contents: read`


def _missing(why):
    return Refusal('bad_input', '%s; %s' % (why, PERMISSIONS_SENTENCE))


def proposal_base(env, github, repo):
    """The branch a proposal targets: the pull request's base, else the repository's default branch. Raises Refusal
    when the repository cannot be read."""
    if is_pull_request(env) and str(env.get('GITHUB_HEAD_REF') or '').strip():
        return str(env.get('GITHUB_BASE_REF') or '').strip()
    status, doc = github.call('GET', '/repos/%s' % repo)
    base = doc.get('default_branch') if status == 200 and isinstance(doc, dict) else None
    if not isinstance(base, str) or not base:
        raise _missing('the repository could not be read (HTTP %d)' % status)
    return base


def propose(top, rel, data, record, env, scratch, github, title=TITLE, source='this repository', lead=None):
    """Propose `data` at `rel` in a pull request of Assure's own: one commit on the base branch's tip, pushed only to
    PROPOSAL_BRANCH, and a pull request from it into the base branch (the pull request's base, else the repository's
    default branch), or, when one is open already, that pull request's branch pushed and its body updated. No branch
    the customer works on is ever written. Returns {branch, commit, number, url, created}; raises Refusal naming the
    reason (the permission lines when the token, the push or the pull request is refused) and leaves no proposal
    branch it created behind. `github` is action.client.GitHub, or None when no workflow token reached the Action."""
    if github is None:
        raise _missing('no workflow token reached the Action')
    repo = str(env.get('GITHUB_REPOSITORY') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise Refusal('bad_input', 'GITHUB_REPOSITORY is not owner/name')
    owner = repo.split('/', 1)[0]
    head_ref = str(env.get('GITHUB_HEAD_REF') or '').strip() if is_pull_request(env) else ''
    base = proposal_base(env, github, repo)
    branch = PROPOSAL_BRANCH
    if not base or branch in (base, head_ref):           # never the customer's branch, whatever the event names
        raise Refusal('bad_input', 'the proposal branch %s is the base or head branch' % branch)
    status, pulls = github.call('GET', '/repos/%s/pulls?state=open&head=%s' % (repo, quote('%s:%s' % (owner, branch))))
    if status != 200 or not isinstance(pulls, list):
        raise _missing('the open pull requests could not be read (HTTP %d)' % status)
    open_pr = next((p for p in pulls if isinstance(p, dict) and isinstance(p.get('number'), int)), None)
    if open_pr is not None and (open_pr.get('base') or {}).get('ref') != base:
        raise Refusal('bad_input', 'the open proposal pull request #%d targets %s, not %s; merge or close it first'
                      % (open_pr['number'], (open_pr.get('base') or {}).get('ref'), base))

    if not _fetch(top, env, base):
        raise Refusal('api_error', 'the base branch %s could not be fetched' % base)
    parent = (_git(top, env, 'rev-parse', '--verify', 'FETCH_HEAD^{commit}') or b'').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', parent):
        raise Refusal('api_error', 'the base branch tip could not be read')
    existing = None
    if _fetch(top, env, branch):
        existing = (_git(top, env, 'rev-parse', '--verify', 'FETCH_HEAD^{commit}') or b'').decode().strip() or None
    # issue #2927: the branch carries every profile's draft; one still on the current base tip is the seed, so a second
    # drafter adds its file and keeps the first (a branch on an older base tip restarts from the base tip, and so does
    # one carrying a file its open pull request's body does not name, as a #2435 proposal from before #2927 does)
    seed, on_branch = parent, set()
    if existing and _parent(top, env, existing) == parent:
        on_branch = set((_git(top, env, 'diff', '--name-only', parent, existing) or b'').decode('utf-8', 'replace')
                        .split('\n')) - {''}
        if on_branch - {rel} <= _named(open_pr.get('body') if open_pr else None):
            seed = existing
    named = {n for n in _named(open_pr.get('body') if open_pr else None) if n.startswith('.assure/')}
    carry = _carried(top, env, existing, parent, rel, named) if existing and seed != existing and named else {}
    blob = (_git(top, env, 'hash-object', '-w', '--stdin', data=bytes(data)) or b'').decode().strip()
    index = {'GIT_INDEX_FILE': str(Path(scratch) / 'assure-proposal.index')}
    tree = None
    if blob and _git(top, env, 'read-tree', seed, extra=index) is not None and all(
            _git(top, env, 'update-index', '--add', '--cacheinfo', '100644,%s,%s' % (b, path), extra=index) is not None
            for path, b in [*sorted(carry.items()), (rel, blob)]):
        tree = (_git(top, env, 'write-tree', extra=index) or b'').decode().strip()
    if not tree:
        raise Refusal('api_error', 'the proposal commit could not be built')
    kept = ()
    if open_pr is not None and seed == existing:    # the other files' sections, while their files stay on the branch
        kept = _kept_sections(open_pr.get('body'), on_branch - {rel})
    elif open_pr is not None and carry:             # issue #3153: and those of the drafts carried to the new tip
        kept = _kept_sections(open_pr.get('body'), set(carry))
    body = pull_request_body(record, rel, source, kept, lead)
    commit = existing
    same = existing and seed == existing and (_git(top, env, 'rev-parse', existing + '^{tree}') or b'').decode().strip() \
        == tree
    if not same:                                    # a new or changed draft: one commit on the base tip
        who = {'GIT_AUTHOR_NAME': BOT[0], 'GIT_AUTHOR_EMAIL': BOT[1], 'GIT_COMMITTER_NAME': BOT[0],
               'GIT_COMMITTER_EMAIL': BOT[1]}
        commit = (_git(top, env, 'commit-tree', tree, '-p', parent, '-F', '-',
                       data=('%s\n\n%s' % (title, body)).encode(), extra=who) or b'').decode().strip()
        # the force is on Assure's own branch only: `branch` is never the base or the head (checked above)
        if not commit or _git(top, env, 'push', '--quiet', 'origin',
                              '+%s:refs/heads/%s' % (commit, branch)) is None:
            raise _missing(PUSH_REFUSED + ' %s was refused' % branch)
    if open_pr is not None:
        status, doc = github.call('PATCH', '/repos/%s/pulls/%d' % (repo, open_pr['number']),
                                  {'title': title, 'body': body})
        doc = doc if status == 200 and isinstance(doc, dict) else open_pr
        return {'branch': branch, 'commit': commit, 'number': open_pr['number'], 'url': str(doc.get('html_url') or ''),
                'created': False}
    status, doc = github.call('POST', '/repos/%s/pulls' % repo,
                              {'title': title, 'head': branch, 'base': base, 'body': body})
    if status != 201 or not isinstance(doc, dict) or not isinstance(doc.get('number'), int):
        if existing is None:                        # leave no branch of ours without its pull request
            _git(top, env, 'push', '--quiet', 'origin', ':refs/heads/%s' % branch)
        raise _missing('the pull request could not be opened (HTTP %d)' % status)
    return {'branch': branch, 'commit': commit, 'number': doc['number'], 'url': str(doc.get('html_url') or ''),
            'created': True}


COMMIT_URL_MAX = 8000   # issue #2249: past this a prefilled new-file link is too long for a browser; the draft stays below


def commit_link(env, branch, rel, data):
    """Issue #2249: GitHub's prefilled new-file URL committing `data` at `rel` on `branch` (the one-click fallback when
    the proposal pull request is refused), or None when the repository or branch is unknown or the URL is too long."""
    repo = str(env.get('GITHUB_REPOSITORY') or '').strip()
    server = str(env.get('GITHUB_SERVER_URL') or '').strip().rstrip('/') or 'https://github.com'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not branch or \
            not re.fullmatch(r'https://[^\s/?#]+', server):
        return None
    url = '%s/%s/new/%s?filename=%s&value=%s' % (server, repo, quote(branch, safe='/'), quote(rel, safe='/'),
                                                 quote(bytes(data), safe=''))
    return url if len(url) <= COMMIT_URL_MAX else None


def commit_markdown(env, branch, rel, data):
    """Issue #2249: the summary's 'Commit this draft' line for a refused proposal; with no link, the path to commit."""
    url = commit_link(env, branch, rel, data)
    if url is None:
        return '\nTo accept the draft, commit the file below at `%s`.\n' % rel
    return '\n[Commit this draft](%s) at `%s` (GitHub opens its commit form with the file filled in).\n' % (url, rel)


def summary_markdown(record, rel, proposed, source='the repository', defaulted=()):
    """The job summary's section for an unaccepted draft: what it is, where it was proposed, the fields to confirm,
    and (issue #3969) each READ_ORDER field in `defaulted` the draft left to its default, in the customer's words
    (FIELD_WORDS; issue #3118), with what it reads."""
    out = ['', '### Declaration: %s' % BOUNDED, '',
           'This check ran on a declaration drafted from %s (`%s`). %s' % (source, rel, proposed), '',
           '| Field to confirm | Read at |', '| --- | --- |']
    for label, at in _confirm_rows(record):
        out.append('| %s | %s |' % (label, ', '.join(at) if record.get('stack') != STACK else
                                    ', '.join('not read from the code' if a == 'unread' else a for a in at)))
    rows = [f for f in READ_ORDER if f in defaulted]
    if rows:
        out += ['', 'Assure could not find these in the code; the check read each at its default. Add one to `%s` '
                'to replace its default.' % rel, '', '| Field left to its default | The default reads |',
                '| --- | --- |']
        out += ['| %s | %s |' % (FIELD_WORDS[f], DEFAULT_READS[f]) for f in rows]
    return '\n'.join(out) + '\n'


def unread_required(data):
    """The required fields (READ_REQUIRED, in that order) a draft's bytes `data` leave out: the drafter did not read
    them from the code. () when `data` is not a JSON object."""
    try:
        decl = json.loads(bytes(data))
    except (TypeError, ValueError):
        return ()
    return tuple(f for f in READ_REQUIRED if f not in decl) if isinstance(decl, dict) else ()


def unread_defaulted(data):
    """Issue #3969: the defaulted fields (READ_DEFAULTED, in that order) a draft's bytes `data` leave out; () when
    `data` is not a JSON object."""
    try:
        decl = json.loads(bytes(data))
    except (TypeError, ValueError):
        return ()
    return tuple(f for f in READ_DEFAULTED if f not in decl) if isinstance(decl, dict) else ()


def unread_refused(data, detail):
    """Issue #3969: the fields a check refused on the draft `data` (declaration_invalid; the refusal's `detail`: its
    first `pointer` and `keyword`, and its `faults` list of {pointer, keyword}) is to name in its next step, in
    READ_ORDER: each of `unread_required(data)`, and each of `unread_defaulted(data)` whose own pointer the refusal
    names with keyword required (a check that still requires it). An unrelated fault never names a defaulted field."""
    required = unread_required(data)
    faults = detail.get('faults') if isinstance(detail.get('faults'), list) else []
    named = {r.get('pointer') for r in [detail] + faults if isinstance(r, dict) and r.get('keyword') == 'required'}
    keep = set(required) | {f for f in unread_defaulted(data) if '/' + f in named}
    return tuple(f for f in READ_ORDER if f in keep)


def next_step(unread, rel, proposed=True, number=None):
    """The one plain next step for a check refused on a partial draft: what Assure could not find in the code, in the
    customer's terms (issue #3118: never a declaration field's name), where to add it (`proposed`: Assure's pull request
    `number`, to review and merge; else the draft in full in the job summary), and that no rule was checked yet. An
    empty `unread` (issue #3969: the refusal names no field the draft left out) asks to correct what Assure read."""
    if unread:
        what, fix, at = ('No rule was checked yet: in the code, Assure could not find %s.' % _join(plain_words(unread)),
                         'add what it could not find', 'to')
    else:       # issue #3969 (REFUTATION-r5 MEDIUM-2): the refusal names no field the draft left out
        what, fix, at = ('No rule was checked yet: the check could not use a value Assure read from the code.',
                         'correct what it read', 'in')
    if not proposed:
        return ('%s Assure could not open its pull request, so the draft is in full in the job summary; %s %s `%s`, '
                'then run again.' % (what, fix, at, rel))
    where = 'pull request #%d' % number if isinstance(number, int) else 'its pull request'
    return '%s Assure proposed what it could read in %s (`%s`); %s, then merge it.' % (what, where, rel, fix)


def intent_markdown(profile, drafted=False):
    """Issue #2926: the job summary's intent section for a profile in NO_DRAFTER or READS_INTENT (fixed words, no
    customer text); '' for any other profile, and for a READS_INTENT run whose summary has a declaration section
    (`drafted`: the run is bounded by a draft, drafted this run or not yet on the base branch, and that section says
    so)."""
    if profile in NO_DRAFTER:
        line = NO_DRAFTER_NOTE % (profile, NO_DRAFTER_READS[profile])
    elif profile in READS_INTENT and not drafted:
        line = READS_INTENT_NOTE % profile
    else:
        return ''
    return '\n### Intent\n\n%s\n' % line

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
