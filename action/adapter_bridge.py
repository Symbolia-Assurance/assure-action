"""The adapter bridge (contract ``assure.adapter-bridge/v1``): your coding agent maps an app shape Assure does not read
natively onto the ``python/stdlib-http`` adapter Assure serves, and Assure re-verifies that map against your code on
every check. The map lives in your repository, in ``.assure/declaration.json`` under ``bridge``; the Action already
sends that file, so committing it is the submission.

Local self-check, before you push (no key, no network, the same verification the server runs):

    python3.14 -B -m action.adapter_bridge check            # in the public Action distribution
    python3.14 -B -m assure.adapter_bridge check            # in a private source checkout
    python3.14 -B -m action.adapter_bridge template         # print a pre-filled bridge to edit

Exit 0: the bridge matches your code, and the lines it prints are what the verdict will state as premises.
Exit 2: a fault, each printed with its rule, its path:line, what was expected and what was found.

What the bridge may say, and what Assure reads for itself:
- The bridge NAMES things: the handler class, the guard method, the credential it checks, the public routes and the
  routes behind the guard. It never says that a route is protected.
- Assure READS, from the bytes, that every ``do_<METHOD>`` of the class runs the guard as its first statement after a
  block that answers only the public paths and returns; that nothing else answers before the guard; that the guard
  reads the stated credential header and raises on a mismatch on every path; that only header tests run before that
  compare, and that each raise up to it is the denial (an exception class every do_<METHOD>'s except clause answers
  with 401 or 403); and that every stated route's selector
  literal is in the code. Any disagreement is a fault: the check is refused, never read as holding.
- What cannot be read from the bytes is STATED BY YOU and printed in the verdict as a premise (``source: declared``):
  that the route list is the one you mean, that the expected secret is set at start and never empty, and that the
  denial reply sends only the error. When startup is absent, the unmodified standard-library server is also stated.

Standard library only: this module ships byte-for-byte in the public Action and never imports Assure's engine.
It parses with ``ast`` and never executes, imports or loads the code it reads.
execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

CONTRACT = 'assure.adapter-bridge/v1'
ONTO = 'python/stdlib-http'
DOC = 'https://github.com/Symbolia-Assurance/assure-action/blob/main/docs/ADAPTER-BRIDGE.md'
DECLARATION_PATH = '.assure/declaration.json'
METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')
BASES = ('BaseHTTPRequestHandler',)
SERVER_HOOKS = ('handle', 'handle_one_request', 'parse_request', 'send_head', '__getattr__', '__getattribute__')
SAFE_DENIAL_NAMES = frozenset({'str', 'repr', 'int', 'json'})
_PATH_RE = re.compile(r'^/[^\s]*\Z')
_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\Z')
_FILE_RE = re.compile(r'^[^\s/\\][^\s\\]*\.py\Z')
MAX_ROUTES = 256
MAX_SOURCE = 2 * 1024 * 1024


# --------------------------------------------------------------------------------------------- contract (shape)
def _fault(out, rule, expected, actual, path=None, pointer=None):
    out.append({'rule': rule, 'path': path, 'pointer': pointer, 'expected': expected, 'actual': actual})


def shape_faults(bridge) -> list:
    """Every fault in the bridge object's own shape (no code read), each with its JSON pointer."""
    out = []
    if not isinstance(bridge, dict):
        _fault(out, 'bridge_shape', 'an object', type(bridge).__name__, pointer='/bridge')
        return out
    allowed = {'contract', 'onto', 'handler', 'guard', 'public', 'routes', 'stated'}
    for k in sorted(set(bridge) - allowed):
        _fault(out, 'bridge_shape', 'only ' + ', '.join(sorted(allowed)), 'unknown field %s' % k, pointer='/bridge/' + k)
    if bridge.get('contract') != CONTRACT:
        _fault(out, 'bridge_shape', CONTRACT, repr(bridge.get('contract')), pointer='/bridge/contract')
    if bridge.get('onto') != ONTO:
        _fault(out, 'bridge_shape', ONTO + ' (the served adapter this bridge maps onto)', repr(bridge.get('onto')),
               pointer='/bridge/onto')
    h = bridge.get('handler')
    if not (isinstance(h, dict) and set(h) == {'file', 'class'} and isinstance(h.get('file'), str)
            and _FILE_RE.match(h['file']) and '..' not in h['file'].split('/') and isinstance(h.get('class'), str)
            and _NAME_RE.match(h['class'])):
        _fault(out, 'bridge_shape', '{"file": "<repo-relative .py path>", "class": "<handler class name>"}',
               json.dumps(h)[:160], pointer='/bridge/handler')
    g = bridge.get('guard')
    if not (isinstance(g, dict) and set(g) == {'method', 'credential'} and isinstance(g.get('method'), str)
            and _NAME_RE.match(g['method']) and isinstance(g.get('credential'), str) and g['credential']):
        _fault(out, 'bridge_shape', '{"method": "<guard method of the handler class>", "credential": "<credentials[].id>"}',
               json.dumps(g)[:160], pointer='/bridge/guard')
    seen = set()
    for key in ('public', 'routes'):
        rows = bridge.get(key)
        if not isinstance(rows, list) or len(rows) > MAX_ROUTES or (key == 'routes' and not rows):
            _fault(out, 'bridge_shape', 'a list of at most %d routes%s' % (MAX_ROUTES, ', at least one' if key == 'routes' else ''),
                   type(rows).__name__, pointer='/bridge/' + key)
            continue
        want = {'method', 'path'} | ({'match'} if key == 'routes' else set())
        for i, r in enumerate(rows):
            ok = isinstance(r, dict) and set(r) == want and r.get('method') in METHODS \
                and isinstance(r.get('path'), str) and _PATH_RE.match(r['path']) \
                and (key == 'public' or isinstance(r.get('match'), str) and r['match'])
            if not ok:
                _fault(out, 'bridge_shape', '{"method": "GET|POST|...", "path": "/..."%s}' % (
                    ', "match": "<the literal the code selects this route by>"' if key == 'routes' else ''),
                    json.dumps(r)[:160], pointer='/bridge/%s/%d' % (key, i))
                continue
            rid = (r['method'], r['path'])
            if rid in seen:
                _fault(out, 'bridge_shape', 'each route once across public and routes', '%s %s twice' % rid,
                       pointer='/bridge/%s/%d' % (key, i))
            seen.add(rid)
    st = bridge.get('stated')
    if st is not None and not (isinstance(st, list) and all(isinstance(s, str) and 0 < len(s) <= 300 for s in st)
                               and len(st) <= 16):
        _fault(out, 'bridge_shape', 'a list of at most 16 short sentences you state', json.dumps(st)[:160],
               pointer='/bridge/stated')
    return out


# ---------------------------------------------------------------------------------------------- code helpers
def _walk_local(node):
    todo = [node]
    while todo:
        n = todo.pop()
        yield n
        for c in ast.iter_child_nodes(n):
            if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                todo.append(c)


def _self_call(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
            and node.func.value.id == 'self':
        return node.func.attr
    return None


def _terminates(body) -> bool:
    """Every path through `body` ends in a return or a raise (if/else both terminating counts)."""
    if not body:
        return False
    last = body[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If):
        return _terminates(last.body) and _terminates(last.orelse)
    return False


def _is_self_path(node) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == 'path' and isinstance(node.value, ast.Name) \
        and node.value.id == 'self'


def _path_literals(test):
    """The set of exact paths a public-block test selects (`self.path == "/x"`, `self.path in ("/a", "/b")`, an `or`
    of those), or None when the test is any other form."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        out = set()
        for v in test.values:
            r = _path_literals(v)
            if r is None:
                return None
            out |= r
        return out
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and _is_self_path(test.left):
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, ast.Eq) and isinstance(right, ast.Constant) and isinstance(right.value, str):
            return {right.value}
        if isinstance(op, ast.In) and isinstance(right, (ast.Tuple, ast.List, ast.Set)) and right.elts and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in right.elts):
            return {e.value for e in right.elts}
    return None


def _reads_header(node, name: str) -> bool:
    """`self.headers.get("<name>"...)`, `self.headers["<name>"]` (header names compare case-insensitively)."""
    def hdrs(v):
        return isinstance(v, ast.Attribute) and v.attr == 'headers' and isinstance(v.value, ast.Name) \
            and v.value.id == 'self'
    low = name.lower()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('get', 'get_all') \
                and hdrs(n.func.value) and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str) and n.args[0].value.lower() == low:
            return True
        if isinstance(n, ast.Subscript) and hdrs(n.value) and isinstance(n.slice, ast.Constant) \
                and isinstance(n.slice.value, str) and n.slice.value.lower() == low:
            return True
    return False


def _string_constants(node) -> set:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _module_literal(tree, name, depth=0):
    """The strings a module-level `name = <literal tuple/list/set/frozenset(...)/dict keys>` holds, a starred
    `*OTHER` element read through OTHER (three levels), else set()."""
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            v = n.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ('frozenset', 'set', 'tuple') \
                    and len(v.args) == 1:
                v = v.args[0]
            if isinstance(v, (ast.Tuple, ast.List, ast.Set)) and depth < 3:
                out = set()
                for e in v.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        out.add(e.value)
                    elif isinstance(e, ast.Starred) and isinstance(e.value, ast.Name):
                        out |= _module_literal(tree, e.value.id, depth + 1)
                    elif isinstance(e, ast.Starred):
                        try:
                            val = ast.literal_eval(e.value)
                        except ValueError:
                            return set()
                        out |= {x for x in val if isinstance(x, str)} if isinstance(
                            val, (tuple, list, set, frozenset, dict)) else set()
                    else:
                        return set()
                return out
            try:
                val = ast.literal_eval(v)
            except ValueError:
                return set()
            if isinstance(val, (tuple, list, set, frozenset)):
                return {x for x in val if isinstance(x, str)}
            if isinstance(val, dict):
                return {x for x in val if isinstance(x, str)}
    return set()


# ---------------------------------------------------------------------------------------------- verification
def verify(files: dict, declaration: dict) -> dict:
    """`_verify`, with a file too deep to parse or print refused as a fault instead of a crash."""
    try:
        return _verify(files, declaration)
    except (RecursionError, MemoryError) as e:
        return {'faults': [{'rule': 'handler_unparsed', 'path': None, 'pointer': '/bridge/handler/file',
                            'expected': 'a file the reader can parse', 'actual': type(e).__name__}],
                'routes': [], 'guard': None, 'premises': [], 'handler': None}


def _verify(files: dict, declaration: dict) -> dict:
    """Re-verify `declaration["bridge"]` against `files` ({repo-relative path: bytes}).

    Returns {"faults": [...], "routes": [...], "guard": {...}, "premises": [...], "handler": {...}}. Any fault means the
    reading is refused; the routes are what the served adapter then reads: each public route (answered before the guard,
    read from the code) and each stated route (behind the guard, which the code shows runs first on every path)."""
    out = {'faults': [], 'routes': [], 'guard': None, 'premises': [], 'handler': None}
    faults = out['faults']
    bridge = declaration.get('bridge') if isinstance(declaration, dict) else None
    faults += shape_faults(bridge)
    if faults:
        return out
    creds = [c for c in declaration.get('credentials') or [] if isinstance(c, dict)]
    cred = next((c for c in creds if c.get('id') == bridge['guard']['credential']), None)
    if cred is None or cred.get('carrier') != 'header' or not isinstance(cred.get('carrier_name'), str) \
            or not cred['carrier_name']:
        _fault(faults, 'bridge_credential', 'a credentials[] entry with this id, "carrier": "header" and '
               '"carrier_name": "<the header the guard reads>"', json.dumps(cred)[:160], pointer='/bridge/guard/credential')
        return out
    header = cred['carrier_name']
    hfile, hcls = bridge['handler']['file'], bridge['handler']['class']
    data = files.get(hfile)
    if data is None:
        _fault(faults, 'handler_absent', 'the file %s in the files read (under app_roots)' % hfile, 'absent',
               pointer='/bridge/handler/file')
        return out
    try:
        tree = ast.parse(bytes(data).decode('utf-8'), filename=hfile)
    except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError) as e:
        _fault(faults, 'handler_unparsed', 'a Python file that parses', str(e)[:160],
               path='%s:%s' % (hfile, getattr(e, 'lineno', None) or 1))
        return out
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == hcls]
    if len(classes) != 1:
        _fault(faults, 'handler_absent', 'one module-level class %s in %s' % (hcls, hfile), '%d found' % len(classes),
               path='%s:1' % hfile)
        return out
    cls = classes[0]
    out['handler'] = {'file': hfile, 'class': hcls, 'line': cls.lineno}
    loc = lambda n: '%s:%d' % (hfile, n.lineno)

    # 1. the class answers HTTP only through its own do_<METHOD>s: base, hooks, aliases, decorators
    bases = [b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else None for b in cls.bases]
    if bases != list(BASES) or cls.decorator_list or cls.keywords:
        _fault(faults, 'handler_base', 'class %s(BaseHTTPRequestHandler) with no decorator, metaclass or other base '
               '(another base can answer requests the bridge does not see)' % hcls,
               ast.unparse(cls).splitlines()[0][:160], path=loc(cls))
    defs = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in cls.body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                if isinstance(t, ast.Name) and (t.id.startswith('do_') or t.id in SERVER_HOOKS):
                    _fault(faults, 'handler_alias', 'do_<METHOD> and server hooks defined with def',
                           ast.unparse(n)[:160], path=loc(n))
    for name in SERVER_HOOKS:
        fn = defs.get(name)
        if fn is not None:
            sup = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == name
                      and isinstance(c.func.value, ast.Call) and isinstance(c.func.value.func, ast.Name)
                      and c.func.value.func.id == 'super' for c in ast.walk(fn))
            if name.startswith('__') or not sup:
                _fault(faults, 'server_hook', '%s left to BaseHTTPRequestHandler, or calling super().%s()' % (name, name),
                       'overridden', path=loc(fn))

    gname = bridge['guard']['method']
    _override_faults(files, hfile, hcls, gname, faults)
    server_read = _server_boundary_faults(files, hfile, hcls, faults)
    _hardening_faults(files, tree, cls, hfile, hcls, gname, header, faults)
    _denial_callee_faults({b.name: b for b in cls.body if isinstance(b, ast.FunctionDef)}, hfile, tree, faults)

    # 2. the guard method: no return, no try, reads the credential header and raises on a mismatch, unconditionally
    gfn = defs.get(gname)
    guard = {'method': gname, 'line': None, 'check_line': None, 'constant_time': False, 'header': header}
    out['guard'] = guard
    if gfn is None:
        _fault(faults, 'guard_absent', 'a method %s defined in class %s' % (gname, hcls), 'absent',
               path=loc(cls), pointer='/bridge/guard/method')
    else:
        guard['line'] = gfn.lineno
        for n in _walk_local(gfn):
            if isinstance(n, ast.Return):
                _fault(faults, 'guard_returns', 'a guard that never returns early (it denies by raising)',
                       ast.unparse(n)[:160], path=loc(n))
            if isinstance(n, (ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.Yield, ast.YieldFrom)):
                _fault(faults, 'guard_shape', 'a guard of top-level `if <test>: raise ...` statements',
                       type(n).__name__, path=loc(n))
        body = [s for s in gfn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        for s in body:
            if not (isinstance(s, ast.If) and not s.orelse and s.body and all(isinstance(b, ast.Raise) for b in s.body)):
                _fault(faults, 'guard_shape', 'a guard whose every statement is `if <test>: raise ...` with no else '
                       '(anything else can change what the compare sees)', ast.unparse(s).splitlines()[0][:160],
                       path=loc(s))
                continue
            if _reads_header(s.test, header):
                t = s.test
                ok = (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Call)) or \
                     (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.NotEq))
                if ok and guard['check_line'] is None:
                    guard['check_line'] = s.lineno
                    call = t.operand if isinstance(t, ast.UnaryOp) else None
                    fname = call.func.attr if call is not None and isinstance(call.func, ast.Attribute) else \
                        call.func.id if call is not None and isinstance(call.func, ast.Name) else None
                    guard['constant_time'] = call is not None and _stdlib_compare(tree, call.func)
        if guard['check_line'] is None:
            _fault(faults, 'guard_reads_no_credential',
                   'a top-level `if not <compare>(self.headers.get("%s"...), <expected>): raise ...` (or `!=`), with '
                   'no else, in %s' % (header, gname), 'none found', path=loc(gfn))

    # 3. each do_<METHOD>: [public block(s)] then the guard call, inside at most one try whose handlers only deny
    stated_public = {(r['method'], r['path']) for r in bridge['public']}
    code_public = set()
    methods = {}
    for name, fn in defs.items():
        if name.startswith('do_'):
            methods[name[3:]] = fn
    wanted = {r['method'] for r in bridge['routes']} | {m for m, _p in stated_public}
    for m in sorted(set(methods) - wanted):
        _fault(faults, 'method_unmapped', 'a stated route or public route for every do_<METHOD> (%s answers requests)' % m,
               'none stated', path=loc(methods[m]))
    for m in sorted(wanted - set(methods)):
        _fault(faults, 'method_absent', 'def do_%s in class %s' % (m, hcls), 'absent (BaseHTTPRequestHandler answers 501)',
               path=loc(cls))
    guard_calls, guard_tries = {}, {}
    for m, fn in sorted(methods.items()):
        body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if isinstance(fn, ast.AsyncFunctionDef) or fn.decorator_list:
            _fault(faults, 'method_shape', 'a plain def do_%s with no decorator' % m, 'async or decorated', path=loc(fn))
            continue
        tries = []
        if len(body) == 1 and isinstance(body[0], ast.Try):
            t = body[0]
            if t.orelse or t.finalbody:
                _fault(faults, 'method_shape', 'a try with except handlers only (else and finally run after the guard '
                       'outcome and can answer)', ast.unparse(t).splitlines()[0][:160], path=loc(t))
            tries.append(t)
            body = t.body
        guard_at = None
        for i, s in enumerate(body):
            if isinstance(s, ast.Expr) and _self_call(s.value) == gname:
                guard_at = i
                break
            lits = _path_literals(s.test) if isinstance(s, ast.If) else None
            if lits is not None and _terminates(s.body) and not s.orelse:
                for p in sorted(lits):
                    code_public.add((m, p))
                continue
            _fault(faults, 'pre_guard_statement', 'only `if self.path in (<literal paths>): ... return` public blocks '
                   'before `self.%s(...)` in do_%s' % (gname, m), ast.unparse(s).splitlines()[0][:160], path=loc(s))
            break
        if guard_at is None:
            if any(mm == m for mm, _p in stated_public) and not any(r['method'] == m for r in bridge['routes']):
                pass                     # a method with public routes only is caught below by the public comparison
            else:
                _fault(faults, 'guard_not_first', 'self.%s(...) as a statement of do_%s, after the public blocks only'
                       % (gname, m), 'not found there', path=loc(fn), pointer='/bridge/guard/method')
        else:
            guard_calls[m] = body[guard_at].lineno
            guard_tries[m] = tries[0] if tries else None
        for t in tries:
            for h in t.handlers:
                bad = _denial_fault(h)
                if bad:
                    _fault(faults, 'denial_handler', 'an except handler that only denies: pass, raise, or one '
                           'self.<reply>(...) call whose arguments read only the caught exception',
                           bad, path=loc(h))
    for m, p in sorted(code_public - stated_public):
        _fault(faults, 'public_unstated', 'every path answered before the guard listed in bridge.public',
               '%s %s is answered before the guard' % (m, p), path=loc(methods['%s' % m]) if m in methods else None,
               pointer='/bridge/public')
    for m, p in sorted(stated_public - code_public):
        _fault(faults, 'public_not_in_code', 'each bridge.public route answered before the guard in do_%s' % m,
               '%s %s is not (it is behind the guard, or absent)' % (m, p), pointer='/bridge/public')
    if gfn is not None and guard['check_line'] is not None:
        _guard_order_faults(files, tree, cls, gfn, header, guard['check_line'], guard_tries, hfile, faults)

    # 4. each stated route: behind the guard (not public), and its selector literal is in the code
    for i, r in enumerate(bridge['routes']):
        m = r['method']
        fn = methods.get(m)
        if fn is None:
            continue
        if (m, r['path']) in code_public:
            _fault(faults, 'route_is_public', 'a route behind the guard', '%s %s is answered before it' % (m, r['path']),
                   pointer='/bridge/routes/%d' % i)
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        lits = _string_constants(fn)
        for nm in names:
            lits |= _module_literal(tree, nm)
        # one helper level: a self.<method>() the do_ method calls (the route parser, the command dispatcher)
        for c in ast.walk(fn):
            callee = defs.get(_self_call(c) or '')
            if callee is not None and callee is not gfn:
                lits |= _string_constants(callee)
                for nm in {n.id for n in ast.walk(callee) if isinstance(n, ast.Name)}:
                    lits |= _module_literal(tree, nm)
        if r['match'] not in lits:
            _fault(faults, 'route_not_found', 'the literal %r in do_%s, a method it calls, or a module constant it '
                   'names' % (r['match'], m), 'absent', path=loc(fn), pointer='/bridge/routes/%d/match' % i)
    if faults:
        return out
    for m, p in sorted(code_public):
        out['routes'].append({'method': m, 'path': p, 'public': True, 'line': methods[m].lineno,
                              'handler': 'do_' + m, 'guard_line': None})
    for r in bridge['routes']:
        out['routes'].append({'method': r['method'], 'path': r['path'], 'public': False,
                              'line': methods[r['method']].lineno, 'handler': 'do_' + r['method'],
                              'guard_line': guard_calls.get(r['method']), 'match': r['match']})
    gl = '%s:%d' % (hfile, guard['check_line'])
    out['premises'] = [
        {'id': 'bridge:route-list', 'source': 'declared', 'text':
         'the %d routes your adapter lists are the routes you mean (stated by you; every request dispatched by the '
         'unmodified standard-library server to %s that is not '
         'on the public list reaches %s.%s first, read from the code)' % (len(bridge['routes']), hcls, hcls, gname)},
        {'id': 'bridge:expected-secret', 'source': 'declared', 'text':
         'the value %s compares the %s header against (%s) is a secret set at start and never empty (stated by you)'
         % (gname, header, gl)},
        {'id': 'bridge:denial-reply', 'source': 'declared', 'text':
         'the reply your except handlers send on a denial carries only the error (stated by you)'},
    ] + [{'id': 'bridge:server-dispatch', 'source': 'declared', 'text':
         ("the standard-library server's dispatch dependencies outside the files read are unmodified (stated by you); "
          "its constructor and handler binding are read from the code" if server_read else
          "the server that runs %s is http.server's, unmodified (stated by you); its construction is outside the "
          "files read" % hcls)}] + [{'id': 'bridge:stated:%d' % i, 'source': 'declared',
          'text': (s[:1].lower() + s[1:] if s[:2] != s[:2].upper() else s).rstrip('.') + ' (stated by you)'}
         for i, s in enumerate(bridge.get('stated') or [])]
    return out


_HANDLER_BASE_RE = re.compile(r'RequestHandler\Z')
_SERVER_CLASSES = frozenset({'http.server.HTTPServer', 'http.server.ThreadingHTTPServer'})
_SERVER_DISPATCH = frozenset({'RequestHandlerClass', 'verify_request', 'process_request', 'process_request_thread',
                              'finish_request', 'get_request', 'handle_request', '_handle_request_noblock',
                              'serve_forever', 'server_bind', 'server_activate', 'socket', 'Thread', 'TCPServer',
                              'BaseServer', 'ThreadingMixIn', '_ServerSelector', 'handle_error', 'shutdown_request',
                              'close_request', 'handle_timeout', 'service_actions'})
_SERVER_METHODS = frozenset({'serve_forever', 'handle_request', 'shutdown', 'server_close', 'fileno'})


def _server_imports(tree):
    """Only module-level absolute imports can name the supported standard-library server."""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == 'http.server':
                    out[a.asname or 'http'] = ('http.server' if a.asname else 'http', n)
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            for a in n.names:
                if n.module == 'http.server' and a.name != '*':
                    out[a.asname or a.name] = ('http.server.' + a.name, n)
                elif n.module == 'http' and a.name == 'server':
                    out[a.asname or a.name] = ('http.server', n)
    return out


def _server_ref(n, imports):
    suffix = []
    while isinstance(n, ast.Attribute):
        suffix.append(n.attr)
        n = n.value
    if not isinstance(n, ast.Name) or n.id not in imports:
        return None, None
    return '.'.join([imports[n.id][0]] + suffix[::-1]), n.id


def _server_binding(tree, root, imported):
    """A local parameter, nested binding or star import can replace even a genuine module import."""
    for n in ast.walk(tree):
        if n is not imported and (isinstance(n, ast.Name) and n.id == root and isinstance(n.ctx, (ast.Store, ast.Del)) or
                isinstance(n, ast.arg) and n.arg == root or
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == root or
                isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and n.name == root or
                isinstance(n, (ast.Global, ast.Nonlocal)) and root in n.names):
            return False
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if isinstance(n, ast.ImportFrom) and any(a.name == '*' for a in n.names):
                return False
            binds = [a for a in n.names if (a.asname or a.name.split('.')[0]) == root]
            if binds and (n is not imported or len(binds) != 1):
                return False
    return True


def _server_call(call, handler, tree, imports, handler_class):
    if handler_class is None or not isinstance(handler, ast.Name) or handler.id != handler_class.name or \
            not _server_binding(tree, handler.id, handler_class):
        return False
    target, root = _server_ref(call.func, imports)
    if target not in _SERVER_CLASSES or not _server_binding(tree, root, imports[root][1]):
        return False
    if len(call.args) not in (1, 2) or any(isinstance(a, ast.Starred) for a in call.args):
        return False
    keys = [k.arg for k in call.keywords]
    if len(set(keys)) != len(keys) or any(k not in ('RequestHandlerClass', 'bind_and_activate') for k in keys):
        return False
    if any(k.arg == 'bind_and_activate' and not (isinstance(k.value, ast.Constant) and
                                                isinstance(k.value.value, bool)) for k in call.keywords):
        return False
    return (len(call.args) == 2 and call.args[1] is handler and 'RequestHandlerClass' not in keys or
            len(call.args) == 1 and any(k.arg == 'RequestHandlerClass' and k.value is handler for k in call.keywords))


def _server_boundary_faults(files, hfile, hcls, faults):
    """Refuse custom/unproved server dispatch; a constructor outside the read files remains an explicit premise."""
    visible = False
    for path in sorted(files):
        if not path.endswith('.py'):
            continue
        parts = path.split('/')
        dependencies = ('http', 'socketserver', 'threading')
        if parts[-1] in tuple(p + '.py' for p in dependencies) or any(p in dependencies for p in parts[:-1]):
            _fault(faults, 'server_dispatch', 'no local module replacing http.server or its dispatch dependencies', path,
                   path=path + ':1')
        try:
            tree = ast.parse(bytes(files[path]).decode('utf-8'), filename=path)
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            continue
        imports = _server_imports(tree)
        handler_class = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == hcls), None) \
            if path == hfile else None
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        instances = set()
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not any(
                    _server_call(call, a, tree, imports, handler_class)
                    for a in call.args + [k.value for k in call.keywords]):
                continue
            par = parents.get(call)
            if isinstance(par, ast.Assign) and len(par.targets) == 1 and isinstance(par.targets[0], ast.Name):
                instances.add(par.targets[0].id)
            elif isinstance(par, ast.withitem) and isinstance(par.optional_vars, ast.Name):
                instances.add(par.optional_vars.id)
            elif not (isinstance(par, ast.Expr) or isinstance(par, ast.Attribute) and par.attr in _SERVER_METHODS
                      and isinstance(parents.get(par), ast.Call) and parents[par].func is par):
                _fault(faults, 'server_dispatch', 'a server instance kept local or used by its standard methods',
                       'the constructed server escapes', path='%s:%d' % (path, call.lineno))
        for n in ast.walk(tree):
            bad = None
            par = parents.get(n)
            if isinstance(n, ast.ClassDef) and any(
                    _server_ref(b, imports)[0] in _SERVER_CLASSES or
                    (b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else '').endswith('Server')
                    for b in n.bases):
                bad = 'a server subclass can answer before the declared handler'
            if (isinstance(n, ast.Import) and any(a.name.split('.')[0] in ('socketserver', 'threading') for a in n.names) or
                    isinstance(n, ast.ImportFrom) and n.module and
                    n.module.split('.')[0] in ('socketserver', 'threading')):
                bad = 'access to socketserver or threading can replace the standard-library dispatch'
            ref = (isinstance(n, ast.Name) and n.id == hcls and isinstance(n.ctx, ast.Load) or
                   isinstance(n, ast.Attribute) and n.attr == hcls)
            if ref:
                if isinstance(par, ast.keyword):
                    par = parents.get(par)
                if not isinstance(par, ast.Call) or not _server_call(par, n, tree, imports, handler_class):
                    bad = 'the handler is not the handler argument of an import-resolved, unmodified stdlib server'
                else:
                    visible = True
            target, _root = _server_ref(n, imports)
            if target and not (isinstance(parents.get(n), ast.Attribute) and parents[n].value is n):
                if target in _SERVER_CLASSES:
                    if not (isinstance(par, ast.Call) and par.func is n and any(
                            _server_call(par, a, tree, imports, handler_class) for a in par.args + [k.value for k in par.keywords]
                            if isinstance(a, ast.Name) and a.id == hcls or isinstance(a, ast.Attribute) and a.attr == hcls)):
                        bad = 'a server class escapes, is modified, or is not the proved handler constructor'
                elif target == 'http.server.BaseHTTPRequestHandler' and isinstance(par, ast.ClassDef) and \
                        path == hfile and par.name == hcls and n in par.bases:
                    pass
                else:
                    bad = 'the standard-library server module escapes or has an unproved use'
            if isinstance(n, ast.Attribute) and n.attr in _SERVER_DISPATCH and isinstance(n.ctx, (ast.Store, ast.Del)):
                bad = 'server dispatch is replaced after construction'
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('setattr', 'delattr') and \
                    len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and n.args[1].value in _SERVER_DISPATCH:
                bad = 'server dispatch is replaced through setattr/delattr'
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in instances and not (
                    isinstance(par, ast.Attribute) and par.value is n):
                bad = 'a constructed server instance escapes to an unproved use'
            if isinstance(n, ast.Attribute) and not (isinstance(par, ast.Attribute) and par.value is n):
                root = n.value
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in instances and isinstance(n.ctx, ast.Load) and not (
                        isinstance(n.value, ast.Name) and n.attr in _SERVER_METHODS and
                        isinstance(par, ast.Call) and par.func is n and all(isinstance(a, ast.Constant) for a in
                            par.args + [k.value for k in par.keywords])):
                    bad = 'a constructed server attribute escapes or calls an unproved dispatch method'
            if bad:
                _fault(faults, 'server_dispatch', 'an unmodified http.server.HTTPServer or ThreadingHTTPServer; '
                       'no read-file server subclass or dispatch replacement', bad, path='%s:%d' % (path, n.lineno))
    return visible


def _override_faults(files: dict, hfile: str, hcls: str, gname: str, faults: list) -> None:
    """Anything in the files read that can replace what the bridge names, refused at its line: an assignment to
    `self.<guard>`, `self.do_*`, `self.headers` or `self.server` (an instance override, say in setup()); an assignment
    or setattr/delattr on the handler class (`Handler.check = ...`); a class-level rebinding of the guard; a subclass
    of the handler (it may be the one the server runs); and any other request-handler class (routes it answers are
    outside the bridge)."""
    guarded = {gname, 'headers', 'server'}
    for path in sorted(files):
        parts = path.split('/')
        if parts[-1] in ('hmac.py', 'secrets.py') or any(x in ('hmac', 'secrets') for x in parts[:-1]):
            _fault(faults, 'compare_rebound', 'no module named hmac or secrets in the files read (an import of the '
                   'standard library compare can resolve to it)', path, path='%s:1' % path)
        if not path.endswith('.py'):
            continue
        try:
            tree = ast.parse(bytes(files[path]).decode('utf-8'), filename=path)
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            continue
        for n in ast.walk(tree):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else \
                [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and (
                        (t.value.id == 'self' and (t.attr in guarded or t.attr.startswith('do_')))
                        or t.value.id == hcls):
                    _fault(faults, 'handler_override', 'nothing assigns %s.%s, a do_<METHOD>, headers or server'
                           % (hcls, gname), ast.unparse(n).splitlines()[0][:160], path='%s:%d' % (path, n.lineno))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('setattr', 'delattr') \
                    and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id in (hcls, 'self'):
                _fault(faults, 'handler_override', 'no setattr/delattr on the handler', ast.unparse(n)[:160],
                       path='%s:%d' % (path, n.lineno))
            if isinstance(n, ast.ClassDef) and not (path == hfile and n.name == hcls):
                names = [b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ''
                         for b in n.bases]
                if hcls in names:
                    _fault(faults, 'handler_subclassed', 'no subclass of %s (the server may run it)' % hcls,
                           'class %s' % n.name, path='%s:%d' % (path, n.lineno))
                elif any(_HANDLER_BASE_RE.search(x or '') for x in names):
                    _fault(faults, 'handler_other', 'one request-handler class, the bridge\'s %s (another one answers '
                           'routes the bridge does not map)' % hcls, 'class %s(%s)' % (n.name, ', '.join(names)),
                           path='%s:%d' % (path, n.lineno))
            if isinstance(n, ast.ClassDef) and path == hfile and n.name == hcls:
                for b in n.body:
                    if isinstance(b, (ast.Assign, ast.AnnAssign)) and any(
                            isinstance(t, ast.Name) and t.id == gname
                            for t in (b.targets if isinstance(b, ast.Assign) else [b.target])):
                        _fault(faults, 'handler_alias', 'the guard defined once, with def', ast.unparse(b)[:160],
                               path='%s:%d' % (path, b.lineno))


# ------------------------------------------------------------------ adversarial-review prototype (allowlist hardening)
#: instance attributes the request machinery sets and the guard/public test read: a class-level def/property of these
#: names (a data descriptor) overrides what the request carries
_REQUEST_ATTRS = frozenset({'headers', 'server', 'path', 'command', 'rfile', 'wfile', 'connection', 'request',
                            'client_address', 'requestline', 'request_version', 'close_connection', 'raw_requestline'})
#: methods the request machinery runs on EVERY request before or around do_<METHOD> (so before the guard)
_PRE_GUARD_HOOKS = frozenset({'__init__', 'setup', 'handle', 'handle_one_request', 'parse_request', 'handle_expect_100',
                              'finish', 'log_message', 'log_request', 'log_error', 'send_error', 'send_response',
                              'send_response_only', 'send_header', 'end_headers', 'flush_headers', 'address_string',
                              'version_string', 'date_time_string', 'log_date_time_string', 'send_head'})
_HATCH_ATTRS = frozenset({'__class__', '__dict__', '__setattr__', '__delattr__', '__bases__', '__mro__', '__getattr__',
                          '__getattribute__', '__init_subclass__', '__set_name__', '__code__', '__globals__'})
_HATCH_NAMES = frozenset({'vars', 'globals', 'locals', 'exec', 'eval', '__import__', 'compile', 'getattr'})


def _bound_names(node):
    """Every name a statement binds in its own scope (all binding forms, nested blocks included, nested scopes not)."""
    out = []
    for n in _walk_local(node) if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else [node]:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((n.name, n))
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.append((n.id, n))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out += [((a.asname or a.name).split('.')[0], n) for a in n.names]
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            out.append((n.name, n))
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.append((n.name, n))
    # _walk_local does not descend into nested defs/classes but yields them: catch them above
    for n in ast.walk(node) if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else []:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (n.name, n) not in out:
            out.append((n.name, n))
    return out


def _is_header_read(node, header):
    """`self.headers.get("<h>")`, `.get("<h>", <str/bytes constant>)`, `self.headers["<h>"]`, optionally `or <constant>`."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2 \
            and isinstance(node.values[1], ast.Constant):
        node = node.values[0]
    hd = lambda v: isinstance(v, ast.Attribute) and v.attr == 'headers' and isinstance(v.value, ast.Name) \
        and v.value.id == 'self'
    low = header.lower()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get' \
            and hd(node.func.value) and not node.keywords and 1 <= len(node.args) <= 2 \
            and isinstance(node.args[0], ast.Constant) and str(node.args[0].value).lower() == low:
        return len(node.args) == 1 or (isinstance(node.args[1], ast.Constant)
                                       and isinstance(node.args[1].value, (str, bytes, type(None))))
    return isinstance(node, ast.Subscript) and hd(node.value) and isinstance(node.slice, ast.Constant) \
        and str(node.slice.value).lower() == low


def _is_expected(node, params, tree=None):
    """The expected side: a stored or configured value, never one the request can set. Either `self.server.<attr>...`
    (the server object, built at start) or a chain rooted at a module-level name that no function rebinds (`global`),
    optionally `.encode()`. A chain through any other `self.<attr>` (`self.command`, `self.client_address`, ...: the
    request's own data), a guard parameter or an escape hatch is refused (remodel refutation of #5285, HIGH-2)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'encode' \
            and all(isinstance(a, ast.Constant) for a in node.args) and not node.keywords:
        node = node.func.value
    chain = []
    while isinstance(node, ast.Attribute):
        if node.attr in ('headers', 'rfile', 'path', 'requestline') or node.attr in _HATCH_ATTRS:
            return False
        chain.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id in params:
        return False
    chain.reverse()
    if node.id == 'self':
        return len(chain) >= 2 and chain[0] == 'server'
    if tree is None:
        return False
    module_names = {name for name, _n in _bound_names_module(tree) if not isinstance(_n, ast.Global)}
    rebound = {x for n in ast.walk(tree) if isinstance(n, (ast.Global, ast.Nonlocal)) for x in n.names}
    return node.id in module_names and node.id not in rebound


_STDLIB_COMPARE = ('hmac', 'secrets')


def _stdlib_compare(tree, func) -> bool:
    """Whether `func` is the standard library's compare_digest, resolved by import, never by name (remodel refutation
    of #5285, HIGH-1): `hmac.compare_digest` / `secrets.compare_digest` whose base name every binding in the module
    gives by `import hmac` / `import secrets` with no alias, or a bare `compare_digest` every binding of which is
    `from hmac|secrets import compare_digest` with no alias. A method, a class attribute, a lookalike module imported
    under the stdlib name, a shadowing def or any other binding is refused."""
    binds = {}
    for name, n in _bound_names_module(tree):
        binds.setdefault(name, []).append(n)
    if isinstance(func, ast.Attribute) and func.attr == 'compare_digest' and isinstance(func.value, ast.Name) \
            and func.value.id in _STDLIB_COMPARE:
        nodes = binds.get(func.value.id) or []
        return bool(nodes) and all(isinstance(n, ast.Import) and all(
            a.asname is None and a.name == func.value.id for a in n.names
            if (a.asname or a.name).split('.')[0] == func.value.id) for n in nodes)
    if isinstance(func, ast.Name) and func.id == 'compare_digest':
        nodes = binds.get('compare_digest') or []
        return bool(nodes) and all(isinstance(n, ast.ImportFrom) and n.level == 0 and n.module in _STDLIB_COMPARE
                                   and all(a.asname is None for a in n.names if (a.asname or a.name) == 'compare_digest')
                                   for n in nodes)
    return False


def _hardening_faults(files, tree, cls, hfile, hcls, gname, header, faults):
    loc = lambda p, n: '%s:%d' % (p, getattr(n, 'lineno', 1))
    # A. the class body: docstring, plain defs, `NAME = <constant>`; no def of a request attribute, no dunder, no
    #    pre-guard hook beyond a reply-only body
    seen = {}
    for b in cls.body:
        if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant):
            continue
        if isinstance(b, ast.FunctionDef) and not b.decorator_list:
            if b.name in seen:
                _fault(faults, 'handler_shape', 'each method defined once', 'def %s twice' % b.name, path=loc(hfile, b))
            seen[b.name] = b
            if b.name in _REQUEST_ATTRS or (b.name.startswith('__') and b.name != '__init__'):
                _fault(faults, 'handler_shape', 'no method named %s (it replaces what the request carries)' % b.name,
                       'def %s' % b.name, path=loc(hfile, b))
            elif b.name in _PRE_GUARD_HOOKS and not _reply_only(b):
                _fault(faults, 'pre_guard_hook', '%s left to BaseHTTPRequestHandler, or a body of only pass, '
                       'super().%s(...), self.send_header(<constants>) and self.connection.settimeout(...) (it runs '
                       'before the guard on every request)' % (b.name, b.name), ast.unparse(b).splitlines()[0][:160],
                       path=loc(hfile, b))
            continue
        if isinstance(b, (ast.Assign, ast.AnnAssign)) and isinstance(b.value, ast.Constant) and all(
                isinstance(t, ast.Name) and t.id not in _REQUEST_ATTRS and t.id != gname and not t.id.startswith('do_')
                for t in (b.targets if isinstance(b, ast.Assign) else [b.target])):
            continue
        _fault(faults, 'handler_shape', 'a class body of plain defs and `NAME = <constant>` only (any other statement '
               'can bind a method or the guard)', ast.unparse(b).splitlines()[0][:160], path=loc(hfile, b))
    # B. the guard: plain def; every header-reading test is `not compare_digest(<header read>, <expected>)` or
    #    `<header read> != <expected>` (either order), the expected side reading no header and no parameter
    g = seen.get(gname)
    if g is not None:
        params = {a.arg for a in g.args.args + g.args.kwonlyargs + g.args.posonlyargs} - {'self'}
        params |= {a.arg for a in (g.args.vararg, g.args.kwarg) if a}
        for s in g.body:
            if isinstance(s, ast.If) and _reads_header(s.test, header):
                t = s.test
                pair = None
                if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Call):
                    c = t.operand
                    if _stdlib_compare(tree, c.func) and len(c.args) == 2 and not c.keywords:
                        pair = c.args
                elif isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.NotEq):
                    pair = [t.left, t.comparators[0]]
                if not pair or not any(_is_header_read(a, header) and _is_expected(b, params, tree)
                                       for a, b in (pair, pair[::-1])):
                    _fault(faults, 'guard_compare', 'not hmac.compare_digest or secrets.compare_digest (imported '
                           'from the standard library, no alias) of self.headers.get("%s"[, <constant>]) and a stored '
                           'value (self.server.<attr> or a module name), or `!=` of the same two' % header,
                           ast.unparse(t)[:160], path=loc(hfile, s))
        for n in ast.walk(g):
            if isinstance(n, ast.NamedExpr):
                _fault(faults, 'guard_shape', 'no assignment expression in the guard', ast.unparse(n)[:160],
                       path=loc(hfile, n))
    # B2. the handler writes no shared state the guard could compare against: no store rooted at self.server or at a
    #     module-level name, in any method of the handler class (the expected value stays what start-up set)
    module_names = {name for name, _n in _bound_names_module(tree)}
    for d in seen.values():
        local = {a.arg for a in d.args.args + d.args.kwonlyargs + d.args.posonlyargs} | \
            {n.id for n in ast.walk(d) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        for n in ast.walk(d):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else \
                [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []
            for t in targets:
                if not isinstance(t, (ast.Attribute, ast.Subscript)):
                    continue
                chain, root = [], t
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    if isinstance(root, ast.Attribute):
                        chain.append(root.attr)
                    root = root.value
                chain.reverse()
                if isinstance(root, ast.Name) and ((root.id == 'self' and chain[:1] == ['server']) or
                                                   (root.id != 'self' and root.id not in local
                                                    and root.id in module_names)):
                    _fault(faults, 'handler_shared_write', 'no write from the handler to self.server or module state '
                           '(the value the guard compares must stay what start-up set)', ast.unparse(n)[:160],
                           path=loc(hfile, n))
    # C. guard calls in do_<METHOD>: constant arguments only (arguments run before the guard)
    for d in seen.values():
        if d.name.startswith('do_'):
            for n in ast.walk(d):
                if _self_call(n) == gname and not all(isinstance(a, ast.Constant) for a in
                                                      list(n.args) + [k.value for k in n.keywords]):
                    _fault(faults, 'guard_call_args', 'self.%s(<constants only>) (arguments run before it)' % gname,
                           ast.unparse(n)[:160], path=loc(hfile, n))
    # D. the handler module binds the class name once (the top-level class) and the compare function only by import
    for name, n in _bound_names_module(tree):
        if name == hcls and n is not cls:
            _fault(faults, 'handler_rebound', 'the name %s bound once, by its class statement' % hcls,
                   ast.unparse(n).splitlines()[0][:160] if not isinstance(n, ast.Name) else name, path=loc(hfile, n))
        if name in ('secrets', 'hmac', 'compare_digest') and not isinstance(n, (ast.Import, ast.ImportFrom)):
            _fault(faults, 'compare_rebound', '%s bound only by import' % name, name, path=loc(hfile, n))
    # E. in every file read: the handler name used only as a call argument or imported; no escape hatches; no
    #    attribute/setattr write of the guard, a do_<METHOD>, a pre-guard hook or compare_digest on any object
    protected = {gname, 'compare_digest'} | _PRE_GUARD_HOOKS | _REQUEST_ATTRS
    for path in sorted(files):
        if not path.endswith('.py'):
            continue
        try:
            t = ast.parse(bytes(files[path]).decode('utf-8'), filename=path)
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            continue
        parents = {}
        for p in ast.walk(t):
            for c in ast.iter_child_nodes(p):
                parents[c] = p
        for n in ast.walk(t):
            # Import resolution is mutable too. Refuse access even through an alias or a read
            # that can hand the table to another function; the file is never executed here.
            if (isinstance(n, ast.Attribute) and n.attr in
                    {'modules', 'meta_path', 'path_hooks', 'path_importer_cache'}) or (
                    isinstance(n, ast.ImportFrom) and n.module == 'sys' and any(
                        a.name in {'modules', 'meta_path', 'path_hooks', 'path_importer_cache', '*'}
                        for a in n.names)) or (
                    isinstance(n, ast.Import) and any(a.name.split('.')[0] in {'importlib', 'builtins'}
                                                     for a in n.names)) or (
                    isinstance(n, ast.ImportFrom) and n.module and
                    n.module.split('.')[0] in {'importlib', 'builtins'}):
                _fault(faults, 'compare_rebound', 'no access to mutable import tables or import machinery '
                       'in the files read (the compare must resolve to the standard library)',
                       ast.unparse(n)[:160], path=loc(path, n))
            ref = (isinstance(n, ast.Name) and n.id == hcls and isinstance(n.ctx, ast.Load)) or \
                (isinstance(n, ast.Attribute) and n.attr == hcls)
            if ref:
                par = parents.get(n)
                if isinstance(par, ast.keyword):
                    par = parents.get(par)
                ok = isinstance(par, ast.Call) and n in par.args + [k.value for k in par.keywords] and not (
                    isinstance(par.func, ast.Name) and par.func.id in ('type', 'setattr', 'delattr', 'getattr'))
                if not ok:
                    _fault(faults, 'handler_escapes', '%s used only as the handler argument of the server call' % hcls,
                           ast.unparse(par or n).splitlines()[0][:160], path=loc(path, n))
            if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and _HANDLER_BASE_RE.search(n.id) or
                    isinstance(n, ast.Attribute) and _HANDLER_BASE_RE.search(n.attr)) and not (
                    path == hfile and (n.lineno, n.col_offset) in {(b.lineno, b.col_offset) for b in cls.bases}) and not isinstance(parents.get(n), ast.Attribute):
                _fault(faults, 'handler_other', 'a request-handler base named only as the base of %s' % hcls,
                       ast.unparse(parents.get(n) or n).splitlines()[0][:160], path=loc(path, n))
            if isinstance(n, ast.Attribute) and n.attr in _HATCH_ATTRS or \
                    isinstance(n, ast.Name) and n.id in _HATCH_NAMES:
                _fault(faults, 'escape_hatch', 'no %s in the files read (it can rebind the guard or a method)' % (
                    getattr(n, 'attr', None) or n.id), ast.unparse(parents.get(n) or n).splitlines()[0][:160],
                    path=loc(path, n))
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)) and (
                    n.attr in (protected - _REQUEST_ATTRS) or n.attr.startswith('do_')):
                _fault(faults, 'handler_override', 'nothing writes .%s' % n.attr, ast.unparse(parents.get(n) or n)
                       .splitlines()[0][:160], path=loc(path, n))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('setattr', 'delattr') and (
                    len(n.args) < 2 or not isinstance(n.args[1], ast.Constant) or str(n.args[1].value) in protected
                    or str(n.args[1].value).startswith('do_')):
                _fault(faults, 'handler_override', 'no setattr/delattr of a non-constant or protected name',
                       ast.unparse(n)[:160], path=loc(path, n))


def _bound_names_module(tree):
    out = []
    for s in tree.body:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((s.name, s))
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(s):       # `global X` then a binding inside a function rebinds the module name
                    if isinstance(n, ast.Global):
                        out += [(x, n) for x in n.names]
            continue
        out += _bound_names(s)
    return out


def _reply_only(fn):
    for s in fn.body:
        if isinstance(s, (ast.Pass,)) or isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            continue
        v = s.value if isinstance(s, (ast.Expr, ast.Return)) else None
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute):
            f = v.func
            if isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name) and f.value.func.id == 'super' \
                    and f.attr == fn.name:
                continue
            if _self_call(v) == 'send_header' and all(isinstance(a, ast.Constant) for a in v.args):
                continue
            if f.attr == 'settimeout' and isinstance(f.value, ast.Attribute) and f.value.attr == 'connection' \
                    and isinstance(f.value.value, ast.Name) and f.value.value.id == 'self':
                continue
        return False
    return True


_REPLY_ATTRS = frozenset({'send_response', 'send_header', 'end_headers', 'flush_headers', 'wfile', 'send_error'})


def _denial_callee_faults(seen, hfile, tree, faults):
    """F. an except handler's self.<reply>(...) callee may only write a reply: it touches no self attribute but the
    reply ones and calls nothing the handler module defines (no route, no device, no dispatcher)."""
    module_defs = {s.name for s in tree.body if isinstance(s, (ast.FunctionDef, ast.ClassDef))}
    for d in seen.values():
        if not d.name.startswith('do_'):
            continue
        for h in (n for n in ast.walk(d) if isinstance(n, ast.ExceptHandler)):
            for c in ast.walk(h):
                name = _self_call(c)
                callee = seen.get(name or '')
                if name is not None and callee is None and name not in ('send_error', 'log_error'):
                    _fault(faults, 'denial_handler', 'an except handler that calls a reply method of %s or '
                           'send_error' % 'the handler class', 'self.%s, defined nowhere in the class' % name,
                           path='%s:%d' % (hfile, c.lineno))
                    continue
                if callee is None:
                    continue
                for n in ast.walk(callee):
                    bad = (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self'
                           and n.attr not in _REPLY_ATTRS) or (isinstance(n, ast.Name) and n.id in module_defs)
                    if bad:
                        _fault(faults, 'denial_handler', 'a reply method that only writes the reply (send_response, '
                               'send_header, end_headers, wfile)', '%s uses %s' % (callee.name, ast.unparse(n)),
                               path='%s:%d' % (hfile, n.lineno))
                        break


def _denial_fault(h) -> str | None:
    """None when an except handler can only deny; otherwise the offending statement."""
    bound = h.name
    for s in h.body:
        if isinstance(s, (ast.Pass, ast.Raise)):
            continue
        if isinstance(s, ast.Expr) and _self_call(s.value) is not None:
            call = s.value
            names = {n.id for a in list(call.args) + [k.value for k in call.keywords] for n in ast.walk(a)
                     if isinstance(n, ast.Name)}
            attrs_on_self = any(isinstance(n, ast.Name) and n.id == 'self' for a in call.args for n in ast.walk(a))
            if bound and names <= ({bound} | SAFE_DENIAL_NAMES) and not attrs_on_self:
                continue
            if not bound and not names:
                continue
        return ast.unparse(s).splitlines()[0][:160]
    return None


# ------------------------------------------------ the guard's order and its denial (review of #5285 at 7f4c3c7c, HIGH-1)
_DENIAL_STATUS = frozenset({401, 403})


def _header_name(node):
    """The header a `self.headers.get("<h>"[, <constant>])` / `self.headers["<h>"]` (optionally `or <constant>`) reads."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2 \
            and isinstance(node.values[1], ast.Constant):
        node = node.values[0]
    key = node.args[0] if isinstance(node, ast.Call) and node.args else \
        node.slice if isinstance(node, ast.Subscript) else None
    if isinstance(key, ast.Constant) and isinstance(key.value, str) and _is_header_read(node, key.value):
        return key.value
    return None


def _header_test(test, params, tree) -> bool:
    """A test that only reads request headers against stored values, so it runs no code: `<header read> <compare>
    <self.server.<attr> | module name | constant>` (either order), `not <stdlib compare>(<header read>, <stored>)`, a
    guard parameter, and `and`/`or`/`not` of those, with at least one header read."""
    def stored(n):
        return _is_expected(n, params, tree) or isinstance(n, ast.Constant) or isinstance(
            n, (ast.Tuple, ast.List, ast.Set)) and all(isinstance(e, ast.Constant) for e in n.elts)

    def atom(n):
        if isinstance(n, ast.BoolOp):
            r = [atom(v) for v in n.values]
            return None if None in r else any(r)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            if isinstance(n.operand, ast.Call):
                c = n.operand
                return True if _stdlib_compare(tree, c.func) and len(c.args) == 2 and not c.keywords and any(
                    _header_name(a) is not None and stored(b) for a, b in (c.args, c.args[::-1])) else None
            return atom(n.operand)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in params:
            return False
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(
                n.ops[0], (ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Is, ast.IsNot)):
            pair = (n.left, n.comparators[0])
            return True if any(_header_name(a) is not None and stored(b) for a, b in (pair, pair[::-1])) else None
        return None
    return atom(test) is True


def _module_classes(tree) -> dict:
    """Module-level classes bound once, by their class statement, and never through `global`."""
    binds = {}
    for name, n in _bound_names_module(tree):
        binds.setdefault(name, []).append(n)
    return {s.name: s for s in tree.body if isinstance(s, ast.ClassDef) and binds.get(s.name) == [s]}


def _builtin_exception(name, tree) -> bool:
    import builtins
    obj = getattr(builtins, name, None)
    return isinstance(obj, type) and issubclass(obj, BaseException) and \
        not any(n == name for n, _b in _bound_names_module(tree))


def _denial_class(name, tree, classes):
    """(the class's ancestor names, {attr: ('param', index, name) | ('const', value)}, None) for an exception class
    whose construction has a bounded body: no decorator or metaclass, one built-in exception base, a
    body of `NAME = <constant>` and at most an `__init__` of `super().__init__(<parameters/constants>)` and
    `self.<attr> = <parameter/constant>`; else (None, None, (offending node, what))."""
    if name not in classes:
        if _builtin_exception(name, tree):
            import builtins
            return {c.__name__ for c in getattr(builtins, name).__mro__}, {}, None
        return None, None, (None, '%s is not a class of the handler module bound once' % name)
    c = classes[name]
    if c.decorator_list or c.keywords or len(c.bases) != 1 or not isinstance(c.bases[0], ast.Name) or \
            c.bases[0].id not in ('Exception', 'RuntimeError', 'ValueError') or \
            not _builtin_exception(c.bases[0].id, tree):
        return None, None, (c, 'class %s: expected one direct built-in exception base, no decorator or metaclass' % name)
    ancestors, attrs = {name}, {}
    anc, _unused, _bad = _denial_class(c.bases[0].id, tree, {})
    ancestors |= anc
    init_seen = False
    for s in c.body:
        if isinstance(s, (ast.Pass,)) or isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            continue
        if isinstance(s, ast.Assign) and isinstance(s.value, ast.Constant) and all(
                isinstance(t, ast.Name) and not t.id.startswith('__') for t in s.targets):
            attrs.update({t.id: ('const', s.value.value) for t in s.targets})
            continue
        if isinstance(s, ast.FunctionDef) and s.name == '__init__' and not s.decorator_list \
                and not s.args.vararg and not s.args.kwarg and not s.args.kwonlyargs and not s.args.posonlyargs \
                and s.args.args and s.args.args[0].arg == 'self' and not init_seen \
                and 'super' not in {a.arg for a in s.args.args} \
                and all(isinstance(d, ast.Constant) for d in s.args.defaults):
            init_seen = True
            ps = [a.arg for a in s.args.args[1:]]
            super_seen = False
            for x in s.body:
                if isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant):
                    continue
                v = x.value if isinstance(x, ast.Expr) else None
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == '__init__' \
                        and isinstance(v.func.value, ast.Call) and isinstance(v.func.value.func, ast.Name) \
                        and v.func.value.func.id == 'super' and not super_seen and not v.func.value.args \
                        and not v.func.value.keywords and not v.keywords and not any(
                            n == 'super' for n, _b in _bound_names_module(tree)) and all(
                            isinstance(a, ast.Constant) or isinstance(a, ast.Name) and a.id in ps for a in v.args):
                    super_seen = True
                    continue
                if isinstance(x, ast.Assign) and len(x.targets) == 1 and isinstance(x.targets[0], ast.Attribute) \
                        and isinstance(x.targets[0].value, ast.Name) and x.targets[0].value.id == 'self' \
                        and not x.targets[0].attr.startswith('__') and (
                            isinstance(x.value, ast.Constant) or isinstance(x.value, ast.Name) and x.value.id in ps):
                    attrs[x.targets[0].attr] = ('const', x.value.value) if isinstance(x.value, ast.Constant) else \
                        ('param', ps.index(x.value.id), x.value.id)
                    continue
                return None, None, (x, 'class %s: __init__ runs %s' % (name, ast.unparse(x).splitlines()[0][:120]))
            continue
        return None, None, (s, 'class %s: %s' % (name, ast.unparse(s).splitlines()[0][:120]))
    return ancestors, attrs, None


def _catches(htype, ancestors, tree, classes):
    """True / False whether an except clause's type catches a class with these ancestors; None when the bytes do not
    show it (a name that is not a built-in exception or a class of the module)."""
    if htype is None:
        return True
    matches = []
    for e in (htype.elts if isinstance(htype, ast.Tuple) else [htype]):
        if not isinstance(e, ast.Name):
            return None
        if e.id in classes:
            _anc, _attrs, bad = _denial_class(e.id, tree, classes)
            if bad:
                return None            # a class statement alone does not establish a valid except type
        elif not _builtin_exception(e.id, tree):
            return None
        matches.append(e.id in ancestors)
    return any(matches)


def _denial_call_binds(raised, name, classes):
    """A constructor arity error raises TypeError instead of the denial whose handler we proved."""
    args = raised.args if isinstance(raised, ast.Call) else []
    keywords = raised.keywords if isinstance(raised, ast.Call) else []
    cls = classes.get(name)
    if cls is None:
        return name in {'Exception', 'RuntimeError', 'ValueError', 'PermissionError', 'KeyError'} and \
            not keywords and len(args) <= 1
    init = next((s for s in cls.body if isinstance(s, ast.FunctionDef) and s.name == '__init__'), None)
    if init is None:
        return not keywords             # direct Exception/RuntimeError/ValueError bases accept positional args
    params = [a.arg for a in init.args.args[1:]]
    if len(args) > len(params):
        return False
    bound = set(params[:len(args)])
    for k in keywords:
        if k.arg not in params or k.arg in bound:
            return False
        bound.add(k.arg)
    required = params[:len(params) - len(init.args.defaults)]
    return all(p in bound for p in required)


def _denial_status(h, cls, raised, attrs):
    """The status the except handler `h` sends for the raise `raised`, when it is one `self.send_error(<status>, ...)`
    or `self.<reply>(<status>, ...)` call (a reply method whose one send_response/send_error sends that parameter),
    optionally then `return`, and the status is a constant or an attribute of the caught exception the raise sets from
    a constant; else None."""
    body = [s for s in h.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if body and isinstance(body[-1], ast.Return) and body[-1].value is None:
        body = body[:-1]
    if len(body) != 1 or not isinstance(body[0], ast.Expr) or _self_call(body[0].value) is None:
        return None
    call = body[0].value
    if not call.args:
        return None
    name = _self_call(call)
    if name != 'send_error':
        fn = next((b for b in cls.body if isinstance(b, ast.FunctionDef) and b.name == name), None)
        ps = [a.arg for a in fn.args.args[1:]] if fn is not None else []
        if not ps or any(not isinstance(s, (ast.Assign, ast.Expr, ast.Pass)) for s in fn.body) or any(
                isinstance(s, ast.Assign) and any(not isinstance(t, ast.Name) for t in s.targets)
                for s in fn.body) or any(
                isinstance(n, ast.Name) and n.id == ps[0] and isinstance(n.ctx, (ast.Store, ast.Del))
                         for n in ast.walk(fn)):
            return None
        # ast.walk alone credits a send in an unexecuted branch or after return. Require
        # the one status send to be an unconditional, top-level statement of a linear reply.
        sends = [c for c in ast.walk(fn) if _self_call(c) in ('send_response', 'send_error')]
        if len(sends) != 1 or not sends[0].args or not (isinstance(sends[0].args[0], ast.Name)
                and sends[0].args[0].id == ps[0]) or not any(
                    isinstance(s, ast.Expr) and s.value is sends[0] for s in fn.body):
            return None
        for s in fn.body:
            if isinstance(s, ast.Expr) and s.value is sends[0]:
                break
            if any(isinstance(n, ast.Name) and n.id == 'self' for n in ast.walk(s)):
                return None                # no earlier write to the response stream
    st = call.args[0]
    if isinstance(st, ast.Constant):
        return st.value
    if isinstance(st, ast.Attribute) and isinstance(st.value, ast.Name) and h.name and st.value.id == h.name:
        a = attrs.get(st.attr)
        if a is None:
            return None
        if a[0] == 'const':
            return a[1]
        args = raised.args if isinstance(raised, ast.Call) else []
        v = args[a[1]] if a[1] < len(args) else next(
            (k.value for k in getattr(raised, 'keywords', []) if k.arg == a[2]), None)
        return v.value if isinstance(v, ast.Constant) else None
    return None


def _denial_binding_fault(files, name, hfile):
    """A denial class cannot escape or acquire a replacement constructor/status in any read file."""
    for path, data in files.items():
        if not path.endswith('.py'):
            continue
        try:
            tree = ast.parse(bytes(data).decode('utf-8'))
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            return (None, 'an unparsed file cannot establish the denial class binding')
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del))) or (
                    isinstance(n, ast.arg) and n.arg == name) or (
                    isinstance(n, ast.ExceptHandler) and n.name == name) or (
                    isinstance(n, (ast.Import, ast.ImportFrom)) and any(
                        (a.asname or a.name).split('.')[0] == name for a in n.names)) or (
                    isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name and
                    not (path == hfile and isinstance(n, ast.ClassDef) and n in tree.body)):
                return (n if path == hfile else None, 'the denial class name %s is rebound at %s:%d' %
                        (name, path, n.lineno))
            if not ((isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)) or
                    (isinstance(n, ast.Attribute) and n.attr == name)):
                continue
            par = parents.get(n)
            if path == hfile and isinstance(n, ast.Name):
                if isinstance(par, ast.ExceptHandler) and par.type is n:
                    continue
                if isinstance(par, ast.Tuple) and isinstance(parents.get(par), ast.ExceptHandler):
                    continue
                if isinstance(par, ast.Call) and par.func is n and isinstance(parents.get(par), ast.Raise):
                    continue
                if isinstance(par, ast.Raise) and par.exc is n:
                    continue
            return (n if path == hfile else None, 'the denial class %s escapes or is modified at %s:%d' %
                    (name, path, n.lineno))
    return None


def _guard_order_faults(files, tree, cls, gfn, header, check_line, guard_tries, hfile, faults):
    """The guard is exactly: header tests that raise the denial, then the credential compare that raises the denial;
    nothing else runs before the compare (a call, a non-header test, a raise value built by code). The denial is a
    raise of an exception class whose construction runs nothing and which the except clause catching it in every
    do_<METHOD> that runs the guard answers with 401 or 403 (review of #5285 at 7f4c3c7c, HIGH-1)."""
    loc = lambda n: '%s:%d' % (hfile, n.lineno)
    params = {a.arg for a in gfn.args.args + gfn.args.kwonlyargs + gfn.args.posonlyargs} - {'self'}
    params |= {a.arg for a in (gfn.args.vararg, gfn.args.kwarg) if a}
    classes = _module_classes(tree)
    own = []
    body = [s for s in gfn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    for s in body:
        if not isinstance(s, ast.If):
            continue
        if s.lineno < check_line and not _header_test(s.test, params, tree):
            _fault(own, 'guard_before_compare', 'before the %s compare, only `if <header read> <compare> '
                   '<self.server.<attr> | module name | constant>: raise <denial>` tests (anything else runs code '
                   'before the compare)' % header, ast.unparse(s.test)[:160], path=loc(s))
        if s.lineno > check_line:
            continue
        for r in s.body:
            if not isinstance(r, ast.Raise):
                continue
            exc = r.exc
            target = exc.func if isinstance(exc, ast.Call) else exc
            ok = isinstance(target, ast.Name) and target.id not in params and r.cause is None and (
                not isinstance(exc, ast.Call) or all(isinstance(a, ast.Constant) for a in exc.args)
                and all(k.arg and isinstance(k.value, ast.Constant) for k in exc.keywords))
            ancestors, attrs, bad = _denial_class(target.id, tree, classes) if ok else (None, None, None)
            if ok and not bad:
                bad = _denial_binding_fault(files, target.id, hfile)
            if ok and not bad and not _denial_call_binds(exc, target.id, classes):
                bad = (r, 'the constructor arguments do not establish an instance of the denial class')
            if not ok or bad:
                _fault(own, 'guard_raise', 'raise <exception class>(<constants>) of a class whose construction '
                       'runs nothing (the raise value runs before the compare decides)',
                       bad[1] if bad else ast.unparse(r)[:160], path=loc(bad[0] if bad and bad[0] else r))
                continue
            for m, t in sorted(guard_tries.items()):
                status, what = None, 'no try around self.%s() in do_%s' % (gfn.name, m)
                if t is not None:
                    what = 'no except clause of do_%s catches it' % m
                    for h in t.handlers:
                        c = _catches(h.type, ancestors, tree, classes)
                        if c is False:
                            continue
                        if c is True:
                            status = _denial_status(h, cls, exc, attrs)
                        what = 'the except clause at line %d sends %s' % (
                            h.lineno, status if status is not None else 'no status the bytes show')
                        break
                if status not in _DENIAL_STATUS:
                    _fault(own, 'guard_denial', 'the raise answered with 401 or 403 by the except clause that '
                           'catches it in every do_<METHOD> that runs the guard', '%s: %s' % (
                               ast.unparse(r)[:100], what), path=loc(r))
    for f in own:                      # one fault per rule and line (a class read once for each raise of it)
        if not any((g['rule'], g['path']) == (f['rule'], f['path']) for g in faults):
            faults.append(f)


# ---------------------------------------------------------------------------------------------- the template
def template(files: dict) -> dict:
    """A pre-filled bridge from the code: the first BaseHTTPRequestHandler subclass, its first `self.<x>()` statement
    after the public blocks as the guard, the public block's literal paths, and one route per do_<METHOD> left for you
    to complete. Every field is a proposal: run `check` after editing."""
    for path in sorted(files):
        if not path.endswith('.py'):
            continue
        try:
            tree = ast.parse(bytes(files[path]).decode('utf-8'))
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            continue
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef) or not any(
                    (b.id if isinstance(b, ast.Name) else getattr(b, 'attr', None)) in BASES for b in cls.bases):
                continue
            public, guard, routes = [], None, []
            for fn in cls.body:
                if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith('do_')):
                    continue
                m = fn.name[3:]
                body = fn.body[0].body if len(fn.body) == 1 and isinstance(fn.body[0], ast.Try) else fn.body
                for s in body:
                    lits = _path_literals(s.test) if isinstance(s, ast.If) else None
                    if lits is not None:
                        public += [{'method': m, 'path': p} for p in sorted(lits)]
                        continue
                    if isinstance(s, ast.Expr) and _self_call(s.value):
                        guard = guard or _self_call(s.value)
                    break
                routes.append({'method': m, 'path': '/TODO', 'match': 'TODO: the literal do_%s selects this route by' % m})
            return {'contract': CONTRACT, 'onto': ONTO, 'handler': {'file': path, 'class': cls.name},
                    'guard': {'method': guard or 'TODO', 'credential': 'TODO: the credentials[].id the guard checks'},
                    'public': public, 'routes': routes}
    return {}


def template_credential(files: dict, bridge: dict) -> dict:
    """The credentials[] entry a bridge's guard needs, pre-filled with the header the guard's compare reads (the first
    `self.headers.get("<h>"...)` or `self.headers["<h>"]` inside a compare_digest or `!=` test of the guard)."""
    out = {'id': 'TODO: a short id, also written in bridge.guard.credential', 'kind': 'api_key', 'carrier': 'header',
           'carrier_name': 'TODO: the header the guard compares'}
    h, g = bridge.get('handler') or {}, (bridge.get('guard') or {}).get('method')
    try:
        tree = ast.parse(bytes(files.get(h.get('file'), b'')).decode('utf-8'))
    except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
        return out
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == h.get('class')), None)
    fn = next((n for n in getattr(cls, 'body', []) if isinstance(n, ast.FunctionDef) and n.name == g), None)
    for s in getattr(fn, 'body', []):
        t = s.test if isinstance(s, ast.If) else None
        if t is None or not ('compare_digest' in ast.unparse(t) or isinstance(t, ast.Compare) and
                             isinstance(t.ops[0], ast.NotEq)):
            continue
        for n in ast.walk(t):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get' and n.args \
                    and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == 'headers' \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str) \
                    and n.args[0].value.lower() not in ('host', 'origin', 'sec-fetch-site'):
                out['carrier_name'] = n.args[0].value
                return out
    return out


# ---------------------------------------------------------------------------------------------- command line
def _read_files(root: Path, declaration: dict) -> dict:
    roots = [r for r in declaration.get('app_roots') or [] if isinstance(r, str)] or ['.']
    files = {}
    for r in roots:
        base = (root / r).resolve()
        if not base.is_relative_to(root.resolve()):
            continue
        for p in sorted(base.rglob('*.py')):
            if p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_SOURCE:
                files[p.resolve().relative_to(root.resolve()).as_posix()] = p.read_bytes()
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='adapter_bridge', description=__doc__.split('\n\n')[0])
    ap.add_argument('command', choices=('check', 'template'))
    ap.add_argument('--declaration', default=DECLARATION_PATH)
    ap.add_argument('--root', default='.')
    a = ap.parse_args(argv)
    root = Path(a.root)
    try:
        declaration = json.loads((root / a.declaration).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        if a.command == 'template':
            declaration = {}
        else:
            print('adapter bridge: cannot read %s: %s' % (a.declaration, e))
            return 2
    files = _read_files(root, declaration if isinstance(declaration, dict) else {})
    if a.command == 'template':
        t = template(files)
        print(json.dumps({'credentials': [template_credential(files, t)], 'bridge': t}, indent=2))
        print('Merge both into %s: the credential entry carries the header the guard reads.' % a.declaration)
        return 0
    res = verify(files, declaration)
    if res['faults']:
        print('adapter bridge: %d fault(s); Assure refuses this bridge until each is fixed (%s)' % (len(res['faults']), DOC))
        for f in res['faults']:
            print('- %s at %s: expected %s; found %s' % (f['rule'], f['path'] or f['pointer'], f['expected'], f['actual']))
        return 2
    g = res['guard']
    print('adapter bridge: matches the code. Assure will read %d route(s) onto %s:' % (len(res['routes']), ONTO))
    for r in res['routes']:
        print('- %s %s: %s' % (r['method'], r['path'], 'public (answered before the guard)' if r['public'] else
                               'behind %s at line %s' % (g['method'], r['guard_line'])))
    print('guard %s reads header %s and raises on a mismatch at %s:%d%s' % (
        g['method'], g['header'], res['handler']['file'], g['check_line'],
        ' (compare_digest)' if g['constant_time'] else ' (not a constant-time compare)'))
    print('the verdict will state these premises as yours:')
    for p in res['premises']:
        print('- assuming ' + p['text'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
