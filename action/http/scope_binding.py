"""Caller-keyed endpoint selection binding, never response/server authentication.

Keys enter memory explicitly; no key persistence, key fingerprint or key recovery.
The checker consumes only public records and independently supplied authority.
"""
import hashlib
import hmac
import json
import re

FLAGS = dict(execution_authorized=False, hardware_authorized=False,
             industrial_release_authorized=False, release_allowed=False,
             physical_validation=False, simulation=True, self_approved=False)
SAFE_ID = re.compile(r'[a-z][a-z0-9-]{0,62}\Z')
ENDPOINT_ID = re.compile(r'endpoint-[0-9]{3}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
SCHEMA = 'assure.http.endpoint-identity.v1'
PROFILE = dict(method='HEAD', http_version='HTTP/1.1', user_agent='Symbolia-Assure-HTTP/1')
DOMAIN = b'assure.http.endpoint-identity.v1\x00'


class BindingError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(value, code):
    if not value:
        raise BindingError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _tokens(scope):
    require(isinstance(scope, dict) and isinstance(scope.get('endpoint_tokens'), dict), 'IDENTITY-BINDING-INVALID')
    tokens = dict(scope['endpoint_tokens'])
    require(1 <= len(tokens) <= 16 and all(isinstance(k, str) and ENDPOINT_ID.fullmatch(k) and
        isinstance(v, str) and SAFE_ID.fullmatch(v) for k,v in tokens.items()) and
        len(set(tokens.values())) == len(tokens), 'IDENTITY-BINDING-INVALID')
    return tokens


def _routes(endpoints):
    require(isinstance(endpoints, (list, tuple)) and 1 <= len(endpoints) <= 16, 'IDENTITY-BINDING-INVALID')
    routes = []
    for endpoint in endpoints:
        require(isinstance(endpoint, dict), 'IDENTITY-BINDING-INVALID')
        # Copy scalar inputs before validation or hashing; retain no routing reference.
        route = {key:endpoint.get(key) for key in ('id','scope_token','scheme','host','port','path')}
        require(isinstance(route['id'],str) and ENDPOINT_ID.fullmatch(route['id']) and
                isinstance(route['scope_token'],str) and SAFE_ID.fullmatch(route['scope_token']), 'IDENTITY-BINDING-INVALID')
        require(route['scheme'] in ('http','https') and type(route['port']) is int and 1 <= route['port'] <= 65535, 'IDENTITY-BINDING-INVALID')
        host, path = route['host'], route['path']
        require(isinstance(host,str) and 1 <= len(host) <= 253 and
            all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.')), 'IDENTITY-BINDING-INVALID')
        require(isinstance(path,str) and path.startswith('/') and not path.startswith('//') and len(path) <= 2048 and
            not any(ord(c) < 33 or ord(c) > 126 or c in '?#\\' for c in path), 'IDENTITY-BINDING-INVALID')
        decoded = re.sub(r'%([0-9A-Fa-f]{2})', lambda m:chr(int(m[1],16)), path)
        require(not re.search(r'%(?![0-9A-Fa-f]{2})',path) and
            not any(ord(c) <= 32 or ord(c) >= 127 or c in '?#\\%' for c in decoded), 'IDENTITY-BINDING-INVALID')
        routes.append(route)
    require(len({r['id'] for r in routes}) == len(routes) and
            len({r['scope_token'] for r in routes}) == len(routes), 'IDENTITY-BINDING-INVALID')
    return routes


def create_identity_binding(endpoints, identity_key, identity_key_id):
    require(type(identity_key) is bytes and len(identity_key) == 32, 'IDENTITY-KEY-INVALID')
    require(isinstance(identity_key_id,str) and SAFE_ID.fullmatch(identity_key_id), 'IDENTITY-KEY-ID-INVALID')
    digests = {}
    for route in _routes(endpoints):
        payload = dict(endpoint_id=route['id'], scope_token=route['scope_token'], scheme=route['scheme'],
                       host=route['host'], port=route['port'], path=route['path'], **PROFILE)
        digests[route['id']] = hmac.new(identity_key, DOMAIN+canonical(payload), hashlib.sha256).hexdigest()
    return dict(schema=SCHEMA, algorithm='hmac-sha256', key_id=identity_key_id, endpoint_digests=digests)


def caller_scope(endpoints, identity_key=None, identity_key_id=None):
    routes = _routes(endpoints)
    scope = dict(endpoint_tokens={r['id']:r['scope_token'] for r in routes})
    if identity_key is None and identity_key_id is None:
        return scope
    scope['identity_binding'] = create_identity_binding(routes, identity_key, identity_key_id)
    return scope


def validate_identity_binding(scope, tokens):
    require(isinstance(scope,dict) and isinstance(tokens,dict), 'IDENTITY-BINDING-INVALID')
    _tokens({'endpoint_tokens':tokens})
    if 'identity_binding' not in scope:
        return None
    binding = scope['identity_binding']
    require(isinstance(binding,dict) and set(binding) == {'schema','algorithm','key_id','endpoint_digests'} and
            binding['schema'] == SCHEMA and binding['algorithm'] == 'hmac-sha256' and
            isinstance(binding['key_id'],str) and SAFE_ID.fullmatch(binding['key_id']), 'IDENTITY-BINDING-INVALID')
    values = binding['endpoint_digests']
    require(isinstance(values,dict) and set(values) == set(tokens) and
            all(isinstance(value,str) and DIGEST.fullmatch(value) for value in values.values()), 'IDENTITY-BINDING-INVALID')
    return dict(schema=SCHEMA, algorithm='hmac-sha256', key_id=binding['key_id'], endpoint_digests=dict(values))


def compare_scopes(current_scope, expected_scope, accepted_scope=None):
    current_tokens, expected_tokens = _tokens(current_scope), _tokens(expected_scope)
    require(current_tokens == expected_tokens, 'SCOPE-SELECTION-MISMATCH')
    current = validate_identity_binding(current_scope, current_tokens)
    expected = validate_identity_binding(expected_scope, expected_tokens)
    require((current is None) == (expected is None), 'EXPECTED-IDENTITY-BINDING-MISMATCH')
    if current is not None:
        require(current['key_id'] == expected['key_id'], 'EXPECTED-IDENTITY-BINDING-MISMATCH')
        matches = [hmac.compare_digest(current['endpoint_digests'][eid], expected['endpoint_digests'][eid])
                   for eid in sorted(current_tokens)]
        require(all(matches), 'EXPECTED-IDENTITY-BINDING-MISMATCH')
    status = 'verified' if current is not None else 'unverified'
    reason = 'CALLER-KEYED-ENDPOINT-DIGEST-MATCH' if current is not None else 'TOKEN-SET-ONLY-NOT-ENDPOINT-AUTHENTICITY'
    removed, changed, added = [], [], []
    comparison = 'first_selected_scope' if status == 'verified' else 'scope_binding_unverified'
    if accepted_scope is not None:
        old_tokens = _tokens(accepted_scope)
        old = validate_identity_binding(accepted_scope, old_tokens)
        removed = sorted(set(old_tokens)-set(current_tokens))
        added = sorted(set(current_tokens)-set(old_tokens))
        changed = sorted(eid for eid in set(current_tokens)&set(old_tokens) if current_tokens[eid] != old_tokens[eid])
        if current is not None and old is not None and current['key_id'] == old['key_id']:
            changed = sorted(set(changed) | {eid for eid in set(current_tokens)&set(old_tokens)
                if not hmac.compare_digest(current['endpoint_digests'][eid], old['endpoint_digests'][eid])})
            comparison = 'same_selected_scope'
        else:
            status = 'unverified'
            if current is not None:
                reason = 'PREDECESSOR-IDENTITY-NOT-BOUND' if old is None else 'IDENTITY-KEY-CONTEXT-CHANGED'
            comparison = 'scope_binding_unverified'
        if removed or changed:
            comparison = 'coverage_reduced'
        elif added:
            comparison = 'scope_expanded'
    return dict(comparison=comparison, removed_endpoint_ids=removed, changed_endpoint_ids=changed,
                added_endpoint_ids=added, scope_binding_status=status, scope_binding_reason=reason,
                scope_authority='caller_bound_keyed_endpoint_selection' if status == 'verified' else 'caller_bound_token_selection')
