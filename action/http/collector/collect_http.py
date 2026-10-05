"""Bounded HTTP fixture collector candidate. No live adapter or product verdict.

Flags: execution_authorized false; hardware_authorized false;
industrial_release_authorized false; release_allowed false;
physical_validation false; simulation true; self_approved false.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import stat
import tempfile
import time

_binding_spec = importlib.util.spec_from_file_location(
    'http_collector_scope_binding', Path(__file__).resolve().parents[1]/'scope_binding.py')
scope_binding = importlib.util.module_from_spec(_binding_spec)
_binding_spec.loader.exec_module(scope_binding)


FLAGS = dict(execution_authorized=False, hardware_authorized=False,
             industrial_release_authorized=False, release_allowed=False,
             physical_validation=False, simulation=True, self_approved=False)
UA = 'Symbolia-Assure-HTTP/1'
HEAD_CAP, LINE_CAP, FIELD_CAP, ENDPOINT_CAP = 65536, 8192, 100, 16
TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
TOKEN_RE = re.compile(TOKEN + r'\Z')
SAFE_ID = re.compile(r'[a-z][a-z0-9-]{0,62}\Z')
ENDPOINT_ID = re.compile(r'endpoint-[0-9]{3}\Z')
ALLOW = frozenset(('content-length', 'transfer-encoding', 'location',
                  'strict-transport-security', 'content-security-policy',
                  'content-security-policy-report-only', 'x-content-type-options',
                  'referrer-policy', 'set-cookie'))
REASONS = frozenset(('HEADER-SENSITIVE', 'HEADER-NOT-ALLOWLISTED',
                     'HEADER-CONTINUATION', 'HEADER-MALFORMED', 'CONTROL-CHARACTER',
                     'FIELD-OVER-BOUND', 'MARKER-COLLISION'))
MARKER = re.compile(r'!collect_http-withheld line ([1-9][0-9]{0,8}) reason ([A-Z][A-Z0-9-]+)\Z')
REFERRERS = frozenset(('no-referrer', 'no-referrer-when-downgrade', 'origin',
                      'origin-when-cross-origin', 'same-origin', 'strict-origin',
                      'strict-origin-when-cross-origin', 'unsafe-url'))
TLS_VERSIONS = frozenset(('TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3'))
TLS_FAILURES = frozenset(('CERT-EXPIRED', 'CERT-NOT-YET-VALID', 'CERT-UNTRUSTED',
                          'CERT-NAME-MISMATCH', 'CERT-VERIFY-FAILED', 'HANDSHAKE-FAILED'))


class CollectionError(Exception):
    """Only fixed safe codes survive exceptional paths."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def typed(value=None, status='observed'):
    return dict(status=status, value=value)


def unknown():
    return typed(None, 'not_observed')


def _controlled(value):
    return any(ord(c) < 32 and c != '\t' or ord(c) >= 127 for c in value)


def request_policy(status):
    return dict(policy_status='not_observed', reason='HEAD-NOT-SERVED') if status in (405, 501) else dict(policy_status='observed', reason=None)


def _endpoint(endpoint):
    allowed = {'id', 'scheme', 'host', 'port', 'path', 'response_file', 'complete', 'scope_token'}
    if not isinstance(endpoint, dict) or set(endpoint) != allowed:
        raise CollectionError('MANIFEST-INVALID')
    if not isinstance(endpoint.get('id'), str) or not ENDPOINT_ID.fullmatch(endpoint['id']):
        raise CollectionError('MANIFEST-INVALID')
    if not isinstance(endpoint['scope_token'], str) or not SAFE_ID.fullmatch(endpoint['scope_token']):
        raise CollectionError('MANIFEST-INVALID')
    if endpoint['scheme'] not in ('http', 'https') or type(endpoint['port']) is not int or not 1 <= endpoint['port'] <= 65535:
        raise CollectionError('MANIFEST-INVALID')
    host, path = endpoint['host'], endpoint['path']
    if (not isinstance(host, str) or not 1 <= len(host) <= 253 or
            any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.'))):
        raise CollectionError('URL-FORBIDDEN-COMPONENT')
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or len(path) > 2048:
        raise CollectionError('URL-FORBIDDEN-COMPONENT')
    # The manifest permits only explicitly public paths. This is a lexical
    # boundary, not a detector of secrets encoded in an operator-selected path.
    if any(ord(c) < 33 or ord(c) > 126 for c in path) or any(c in path for c in ('?', '#', '\\')):
        raise CollectionError('URL-FORBIDDEN-COMPONENT')
    decoded = re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m[1], 16)), path)
    if (re.search(r'%(?![0-9A-Fa-f]{2})', path) or any(c in decoded for c in ('?', '#', '\\')) or
            any(ord(c) <= 32 or ord(c) >= 127 for c in decoded) or '%' in decoded):
        raise CollectionError('URL-FORBIDDEN-COMPONENT')
    if type(endpoint['complete']) is not bool or not isinstance(endpoint['response_file'], str):
        raise CollectionError('MANIFEST-INVALID')


def build_request(endpoint):
    _endpoint(endpoint)
    default = 443 if endpoint['scheme'] == 'https' else 80
    host = endpoint['host'] + (':' + str(endpoint['port']) if endpoint['port'] != default else '')
    return ('HEAD ' + endpoint['path'] + ' HTTP/1.1\r\nHost: ' + host +
            '\r\nUser-Agent: ' + UA + '\r\n\r\n').encode('ascii')


def capture_head(sock):
    """Reads raw recv bytes; never unfolds/joins fields or retains a body.

    The caller owns socket timeout configuration. Only a single head is
    supported; sanitize_response marks interim responses unsupported.
    """
    buffer = bytearray()
    try:
        while len(buffer) <= HEAD_CAP:
            part = sock.recv(min(4096, HEAD_CAP + 1 - len(buffer)))
            if not part:
                return dict(head=bytes(buffer), complete=False, gap='SOURCE-INCOMPLETE')
            if not isinstance(part, bytes):
                return dict(head=b'', complete=False, gap='FRAMING-UNSUPPORTED')
            buffer.extend(part)
            end = buffer.find(b'\r\n\r\n')
            if end >= 0:
                head = bytes(buffer[:end + 4])
                if len(head) > HEAD_CAP:
                    return dict(head=b'', complete=False, gap='LIMIT-EXCEEDED')
                return dict(head=head, complete=True, gap=None)
            if len(buffer) >= HEAD_CAP:
                return dict(head=b'', complete=False, gap='LIMIT-EXCEEDED')
    except TimeoutError:
        return dict(head=bytes(buffer), complete=False, gap='TIMEOUT')
    except OSError:
        return dict(head=bytes(buffer), complete=False, gap='TRANSPORT-ERROR')
    return dict(head=b'', complete=False, gap='LIMIT-EXCEEDED')


def _length(value):
    if re.fullmatch(r'[0-9]+', value):
        if len(value) > 19 or int(value) > 2**63 - 1:
            return dict(status='representation', syntax='unknown', value=None)
        return dict(status='observed', syntax='valid', value=int(value))
    # Full observed bytes establish invalid supported scalar syntax, but no
    # arbitrary invalid text survives into the result.
    return dict(status='observed', syntax='invalid', value=None)


def _encoding(value):
    parts = [p.strip().lower() for p in value.split(',')]
    known = ('chunked', 'gzip', 'compress', 'deflate')
    if not parts or any(not TOKEN_RE.fullmatch(p) for p in parts):
        return dict(status='representation', syntax='unknown', codings=[])
    if any(p not in known for p in parts):
        return dict(status='representation', syntax='unknown', codings=[])
    return dict(status='observed', syntax='valid', codings=parts)


def _hsts(value):
    result = dict(status='observed', syntax='valid', max_age=None,
                  include_subdomains=False, preload=False)
    directives = []
    # Semicolons within quoted extension values are data. Preserve neither
    # extension text nor a digest of it; tokenizer state stays in memory.
    chunks, start, quoted, escaped = [], 0, False, False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quoted and character == '\\':
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == ';' and not quoted:
            chunks.append(value[start:index])
            start = index + 1
    if quoted or escaped:
        return dict(result, syntax='invalid')
    chunks.append(value[start:])
    for raw in chunks:
        raw = raw.strip()
        if not raw:
            continue
        match = re.fullmatch('(' + TOKEN + r')(?:\s*=\s*(' + TOKEN + r'|"(?:[^"\\\x00-\x1f\x7f]|\\[\x20-\x7e])*"))?', raw)
        if not match:
            return dict(result, syntax='invalid')
        name, val = match[1].lower(), match[2]
        directives.append(name)
        if name == 'max-age':
            val = val[1:-1] if val and val.startswith('"') else val
            # quoted-pair decodes the escaped CHAR before the digit grammar.
            val = re.sub(r'\\([\x20-\x7e])', r'\1', val) if val is not None else None
            if val is None or not re.fullmatch(r'[0-9]+', val):
                result['syntax'] = 'invalid'
            elif len(val) > 19 or int(val) > 2**63 - 1:
                result.update(status='representation', syntax='unknown')
            else:
                result['max_age'] = int(val)
        elif name == 'includesubdomains':
            if val is not None:
                result['syntax'] = 'invalid'
            result['include_subdomains'] = True
        elif name == 'preload':
            # RFC 6797 does not standardise preload semantics: it is an
            # extension whose optional value is withheld, never rejected.
            result['preload'] = True
        # Unknown extension contents are never returned, even when legal.
    if directives.count('max-age') != 1 or len(set(directives)) != len(directives):
        result['syntax'] = 'invalid'
    return result


def _location(value, endpoint):
    result = dict(status='observed', syntax='valid', form='relative', scheme=endpoint['scheme'],
                  origin_relation='same_origin', secure_to_insecure=False)
    if not value or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or '\\' in value or re.search(r'%(?![a-fA-F0-9]{2})', value):
        return dict(result, syntax='invalid', scheme='other', origin_relation='unknown', secure_to_insecure=None)
    absolute = re.match(r'^([A-Za-z][A-Za-z0-9+.-]*):', value)
    if absolute or value.startswith('//'):
        scheme = absolute[1].lower() if absolute else endpoint['scheme']
        result.update(form='absolute' if absolute else 'network_relative', scheme=scheme if scheme in ('http', 'https') else 'other')
        rest = value[len(absolute[0]):] if absolute else value
        if not rest.startswith('//'):
            return dict(result, status='representation', origin_relation='unknown', secure_to_insecure=None)
        authority = re.split(r'[/?#]', rest[2:], maxsplit=1)[0]
        # Refuse to derive a relation from userinfo, ambiguous authority, IPv6
        # (not in this candidate grammar), or unsupported schemes.
        if '@' in authority or scheme not in ('http','https'):
            return dict(result, status='not_observed', origin_relation='unknown', secure_to_insecure=None)
        match = re.fullmatch(r'([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?', authority)
        if not match:
            return dict(result, syntax='invalid', origin_relation='unknown', secure_to_insecure=None)
        port = int(match[2]) if match[2] else (443 if scheme == 'https' else 80)
        if not 1 <= port <= 65535:
            return dict(result, syntax='invalid', origin_relation='unknown', secure_to_insecure=None)
        same = (scheme == endpoint['scheme'] and match[1].lower() == endpoint['host'].lower() and port == endpoint['port'])
        result.update(origin_relation='same_origin' if same else 'different_origin',
                      secure_to_insecure=endpoint['scheme'] == 'https' and scheme == 'http')
    return result


def _cookie(value, index, parse=True):
    names = ('secure', 'httponly', 'samesite', 'domain_present', 'path_present',
             'expires_present', 'max_age_present', 'unknown_attribute_present')
    result = dict(id=f'cookie-{index:03d}', capture_status='observed' if parse else 'not_observed',
                  syntax_status='valid' if parse else 'unknown', pair_syntax='valid' if parse else 'unknown',
                  attribute_status='observed' if parse else 'not_observed', violations=[])
    result.update({n: unknown() for n in names})
    if not parse:
        return result
    parts = [p.strip() for p in value.split(';')]
    pair = parts[0].split('=', 1)
    if len(pair) != 2 or not TOKEN_RE.fullmatch(pair[0]):
        result.update(syntax_status='invalid', pair_syntax='invalid', violations=['COOKIE-PAIR-SYNTAX'])
        return result
    cookie_value = pair[1]
    if cookie_value.startswith('"') and cookie_value.endswith('"'):
        cookie_value = cookie_value[1:-1]
    if any(ord(c) not in (0x21,) and not (0x23 <= ord(c) <= 0x2b or 0x2d <= ord(c) <= 0x3a or 0x3c <= ord(c) <= 0x5b or 0x5d <= ord(c) <= 0x7e) for c in cookie_value):
        result.update(syntax_status='invalid', pair_syntax='invalid', violations=['COOKIE-PAIR-SYNTAX'])
        return result
    result.update({n: typed(False) for n in names if n != 'samesite'})
    result['samesite'] = typed(None)
    seen = set()
    for part in parts[1:]:
        if not part:
            continue
        attribute = part.split('=', 1)
        name = attribute[0].strip().lower()
        val = attribute[1].strip() if len(attribute) == 2 else None
        key = {'secure':'secure', 'httponly':'httponly', 'samesite':'samesite',
               'domain':'domain_present', 'path':'path_present', 'expires':'expires_present',
               'max-age':'max_age_present'}.get(name)
        if key is None:
            result['unknown_attribute_present'] = typed(True)
            continue
        duplicate = name in seen
        seen.add(name)
        invalid = duplicate or (name in ('secure','httponly') and val is not None)
        if invalid:
            result[key] = unknown()
            result['violations'].append('COOKIE-ATTRIBUTE-DUPLICATE' if duplicate else 'COOKIE-ATTRIBUTE-SYNTAX')
            result['attribute_status'] = 'not_observed'
            continue
        if name == 'samesite':
            result[key] = typed(val.lower()) if val and val.lower() in ('strict','lax','none') else unknown()
        else:
            result[key] = typed(True)
    result['violations'] = sorted(set(result['violations']))
    return result


def sanitize_response(head, endpoint, complete=True):
    """Return safe text plus independently extracted bounded observations."""
    _endpoint(endpoint)
    if not isinstance(head, bytes) or type(complete) is not bool:
        raise CollectionError('MANIFEST-INVALID')
    over = len(head) > HEAD_CAP
    # Never retain body bytes. Multiple interim heads are not implemented.
    terminator = head.find(b'\r\n\r\n')
    lf_terminator = head.find(b'\n\n')
    if terminator >= 0:
        head = head[:terminator + 4]
    elif lf_terminator >= 0:
        head = head[:lf_terminator + 2]
    head = head[:HEAD_CAP]
    lines = head.split(b'\n')
    if lines and lines[-1] == b'':
        lines.pop()
    physical = [line[:-1] if line.endswith(b'\r') else line for line in lines]
    proper_boundary = terminator >= 0 and all(line.endswith(b'\r') for line in lines)
    closed = complete and terminator >= 0 and proper_boundary and not over
    status_match = re.fullmatch(rb'HTTP/1\.1 ([0-9]{3})(?: [\x20-\x7e]*)?', physical[0]) if physical else None
    code = int(status_match[1]) if status_match and 100 <= int(status_match[1]) <= 599 else None
    if code is None:
        closed = False
    interim = code is not None and code < 200
    if interim:
        closed = False
    units = []
    for n, data in enumerate(physical[1:], 2):
        if data == b'':
            continue
        if data.startswith((b' ', b'\t')) and units:
            units[-1]['lines'].append((n, data))
        else:
            units.append(dict(lines=[(n, data)]))
    over = over or any(len(line) > LINE_CAP for line in physical) or len(units) > FIELD_CAP
    if over:
        closed = False
    facts = dict(capture_status='observed' if closed else 'not_observed',
                 status_code=code, protocol_version='HTTP/1.1' if status_match else None,
                 content_length=[], transfer_encoding=[], content_length_relation='unknown',
                 content_length_and_transfer_encoding=None, locations=[], hsts=[], cookies=[],
                 cookie_count=None, cookie_coverage='unknown', header_coverage='unknown',
                 csp=dict(enforcing_count=0, report_only_count=0, status='observed'),
                 nosniff=[], referrer_policy=[], policy=request_policy(code), gaps=[])
    if over:
        facts['gaps'].append('LIMIT-EXCEEDED')
    if interim:
        facts['gaps'].append('INTERIM-HEAD-UNSUPPORTED')
    if not closed and not facts['gaps']:
        facts['gaps'].append('SOURCE-INCOMPLETE' if not complete or terminator < 0 else 'FRAMING-UNSUPPORTED')
    rows, fields, safe = [], [], [''] * len(physical)
    if safe:
        # The arbitrary reason phrase is withheld, so the whole physical
        # status unit is a marker, with independently parsed numeric facts.
        # known_not_allowlisted at line1/status-line denotes a known non-header
        # status unit and therefore does not taint header-name absence.
        status_reason = 'HEADER-SENSITIVE' if code is not None else 'HEADER-MALFORMED'
        safe[0] = '!collect_http-withheld line 1 reason ' + status_reason
        rows.append(dict(file='response-head.txt', line=1, logical_unit_id='status-line', reason=status_reason,
                         identity_status='known_not_allowlisted' if code is not None else 'unknown'))
    identity_complete = True
    cookie_complete = closed
    cookie_index = 0
    for index, unit in enumerate(units, 1):
        number, raw = unit['lines'][0]
        logical_id = f'field-{index:03d}'
        name, value = None, None
        try:
            decoded = raw.decode('ascii')
            match = re.match('^(' + TOKEN + r'):(.*)$', decoded)
            if match:
                name, value = match[1].lower(), match[2].strip(' \t')
        except UnicodeError:
            decoded = ''
        identity = 'allowlisted:' + name if name in ALLOW else ('known_not_allowlisted' if name else 'unknown')
        folded = len(unit['lines']) > 1
        control = any(any(byte < 32 and byte != 9 or byte >= 127 for byte in content) for _, content in unit['lines'])
        # A bare CR may conceal a different field boundary for another recipient.
        # A corrupted nonallowlisted unit must never certify framing absence.
        # Other controls in a known allowlisted value do not erase its independently
        # observed field name: CL+TE presence remains usable without retaining value.
        if any(b'\r' in content for _, content in unit['lines']) or (control and name not in ALLOW):
            identity = 'unknown'
        if identity == 'unknown':
            identity_complete, cookie_complete = False, False
        bounded = all(len(content) <= LINE_CAP for _, content in unit['lines']) and index <= FIELD_CAP and not over
        parse = name is not None and not folded and not control and bounded
        syntax = 'valid' if parse else 'unknown'
        violations = ['OBS-FOLD'] if folded else []
        if control:
            violations.append('FIELD-CONTROL-CHARACTER')
        f = dict(occurrence_id=logical_id, physical_lines=[n for n, _ in unit['lines']],
                 name_class=name if name in ALLOW else 'unknown', identity_status=identity,
                 capture_status='observed' if bounded and closed else 'not_observed',
                 syntax_status=syntax, violations=violations, facts={})
        source = dict(file='response-head.txt', occurrence_id=logical_id, physical_lines=f['physical_lines'])
        extracted, retained = None, None
        if name == 'set-cookie':
            cookie_index += 1
            extracted = _cookie(value or '', cookie_index, parse and closed)
            facts['cookies'].append(dict(extracted, source=source))
            if not parse:
                cookie_complete = False
        elif name in ALLOW and parse:
            if name == 'content-length':
                extracted = _length(value)
                facts['content_length'].append(dict(extracted, source=source))
                if extracted['value'] is not None:
                    retained = 'Content-Length: ' + str(extracted['value'])
            elif name == 'transfer-encoding':
                extracted = _encoding(value)
                facts['transfer_encoding'].append(dict(extracted, source=source))
                if extracted['status'] == 'observed':
                    retained = 'Transfer-Encoding: ' + ', '.join(extracted['codings'])
            elif name == 'location':
                extracted = _location(value, endpoint)
                facts['locations'].append(dict(extracted, source=source))
            elif name == 'strict-transport-security':
                extracted = _hsts(value)
                facts['hsts'].append(dict(extracted, source=source))
            elif name.startswith('content-security-policy'):
                key = 'report_only_count' if name.endswith('report-only') else 'enforcing_count'
                facts['csp'][key] += 1
                extracted = dict(status='observed', presence=True, mode='report_only' if name.endswith('report-only') else 'enforcing')
            elif name == 'x-content-type-options':
                extracted = dict(status='observed' if value.lower() == 'nosniff' else 'representation', value='nosniff' if value.lower() == 'nosniff' else None)
                facts['nosniff'].append(dict(extracted, source=source))
                if extracted['value']:
                    retained = 'X-Content-Type-Options: nosniff'
            elif name == 'referrer-policy':
                policies = [v.strip().lower() for v in value.split(',')]
                extracted = dict(status='observed' if all(v in REFERRERS for v in policies) else 'representation', values=[v for v in policies if v in REFERRERS])
                facts['referrer_policy'].append(dict(extracted, source=source))
        elif name in ALLOW:
            extracted = dict(status='not_observed', syntax='unknown', value=None)
            target = {'content-length':'content_length', 'transfer-encoding':'transfer_encoding',
                      'location':'locations', 'strict-transport-security':'hsts'}.get(name)
            if target:
                facts[target].append(dict(extracted, source=source))
            if name.startswith('content-security-policy'):
                facts['csp']['status'] = 'not_observed'
        if extracted is not None:
            extraction = extracted.get('status', extracted.get('capture_status', 'not_observed'))
            f['facts'] = dict(source=source, extraction_status=extraction, value=extracted)
            f['syntax_status'] = extracted.get('syntax', extracted.get('syntax_status', f['syntax_status']))
            f['violations'] += extracted.get('violations', [])
        fields.append(f)
        if retained is not None and parse:
            safe[number - 1] = retained
        else:
            if raw.startswith(b'!collect_http-withheld'):
                reason = 'MARKER-COLLISION'
            elif not bounded:
                reason = 'FIELD-OVER-BOUND'
            elif control:
                reason = 'CONTROL-CHARACTER'
            elif folded:
                reason = 'HEADER-CONTINUATION'
            elif name is None:
                reason = 'HEADER-MALFORMED'
            elif name not in ALLOW:
                reason = 'HEADER-NOT-ALLOWLISTED'
            else:
                reason = 'HEADER-SENSITIVE'
            for line_number, _ in unit['lines']:
                safe[line_number - 1] = f'!collect_http-withheld line {line_number} reason {reason}'
                rows.append(dict(file='response-head.txt', line=line_number, logical_unit_id=logical_id,
                                 reason=reason, identity_status=identity))
    facts['header_coverage'] = 'complete' if closed and identity_complete else 'unknown'
    facts['cookie_coverage'] = 'complete' if cookie_complete and identity_complete else 'unknown'
    if facts['cookie_coverage'] == 'complete':
        facts['cookie_count'] = cookie_index
    cl = facts['content_length']
    if facts['header_coverage'] == 'complete':
        values = [entry.get('value') for entry in cl]
        if not cl:
            facts['content_length_relation'] = 'absent'
        elif any(v is None for v in values):
            facts['content_length_relation'] = 'unknown'
        else:
            facts['content_length_relation'] = 'equal' if len(set(values)) == 1 else 'conflicting'
        known_names = {field['identity_status'] for field in fields}
        facts['content_length_and_transfer_encoding'] = (
            'allowlisted:content-length' in known_names and 'allowlisted:transfer-encoding' in known_names)
    # No partial response can prove a policy field count or absence.
    if not closed or not identity_complete:
        facts['csp']['status'] = 'not_observed'
    metadata = dict(complete_head=closed, physical_boundary_status='observed' if proper_boundary else 'not_observed',
                    field_identity_coverage='complete' if identity_complete else 'unknown',
                    header_count_status='observed' if closed and identity_complete else 'not_observed',
                    cookie_count_status='observed' if facts['cookie_count'] is not None else 'not_observed')
    text = '\n'.join(safe) + ('\n' if safe else '')
    validate_marker_accounting(text, rows, 'response-head.txt')
    return dict(sanitized_head=text, facts=facts, redaction_withheld=rows, fields=fields, metadata=metadata)


def validate_marker_accounting(text, rows, file='response-head.txt'):
    found = {}
    for ordinal, line in enumerate(text.splitlines(), 1):
        if line.startswith('!collect_http-withheld'):
            match = MARKER.fullmatch(line)
            if not match or int(match[1]) != ordinal or match[2] not in REASONS:
                raise CollectionError('OUTPUT-BINDING-INVALID')
            found[ordinal] = match[2]
        if line.rstrip().endswith('\\'):
            raise CollectionError('OUTPUT-BINDING-INVALID')
    observed = {}
    if not isinstance(rows, list):
        raise CollectionError('OUTPUT-BINDING-INVALID')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'file','line','logical_unit_id','reason','identity_status'}:
            raise CollectionError('OUTPUT-BINDING-INVALID')
        identity = row['identity_status']
        allowed_identity = identity in ('known_not_allowlisted','unknown') or identity in {'allowlisted:' + name for name in ALLOW}
        if (row['file'] != file or type(row['line']) is not int or row['line'] in observed or
                not allowed_identity or row['reason'] not in REASONS or
                row['reason'] == 'HEADER-NOT-ALLOWLISTED' and identity != 'known_not_allowlisted' or
                not isinstance(row['logical_unit_id'], str) or not SAFE_ID.fullmatch(row['logical_unit_id'])):
            raise CollectionError('OUTPUT-BINDING-INVALID')
        observed[row['line']] = row['reason']
    if observed != found:
        raise CollectionError('OUTPUT-BINDING-INVALID')


def tls_observation(session):
    """Closed safe session facts; never server-wide support or certificate data."""
    if not isinstance(session, dict):
        return dict(status='not_observed', verification_failure='CERT-VERIFY-FAILED',
                    prohibition_observability=typed(None, 'not_observed'))
    if session.get('verification') == 'failed':
        failure = session.get('error_code')
        return dict(status='not_observed', verification_failure=failure if failure in TLS_FAILURES else 'CERT-VERIFY-FAILED',
                    prohibition_observability=typed(None, 'not_observed'))
    offered = session.get('offered_versions')
    offer_known = isinstance(offered, list) and bool(offered) and all(v in TLS_VERSIONS for v in offered)
    cipher_shape = lambda v: isinstance(v, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,127}', v) is not None
    ciphers = session.get('offered_ciphers')
    ciphers_known = isinstance(ciphers, list) and bool(ciphers) and len(ciphers) <= 256 and all(cipher_shape(c) for c in ciphers)
    version, cipher = session.get('negotiated_version'), session.get('negotiated_cipher')
    result = dict(status='observed' if session.get('status') == 'observed' else 'not_observed',
                  offered_versions=offered if offer_known else None,
                  offered_ciphers=ciphers if ciphers_known else None,
                  negotiated_version=version if version in TLS_VERSIONS else None,
                  negotiated_cipher=cipher if cipher_shape(cipher) else None,
                  verification='verified' if session.get('verification') == 'verified' else 'not_observed',
                  library=session.get('library') if session.get('library') in ('OpenSSL','LibreSSL','BoringSSL','AWS-LC') else None,
                  library_version=session.get('library_version') if isinstance(session.get('library_version'), str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+[a-z]?', session['library_version']) else None)
    premise = offer_known and ciphers_known and result['library'] is not None and result['library_version'] is not None
    result['prohibition_observability'] = dict(status='observed' if premise and any(v in ('TLSv1','TLSv1.1') for v in offered) else 'not_observed',
                                             reason=None if premise and any(v in ('TLSv1','TLSv1.1') for v in offered) else 'CLIENT-OFFER-NOT-DISCRIMINATING')
    return result


def _read_regular(root, relative, maximum, missing_ok=False):
    """Descriptor-relative no-follow opens, including each parent component."""
    if not isinstance(relative, str) or not relative or len(relative) > 1024:
        raise CollectionError('PATH-ESCAPE')
    parts = relative.split('/')
    if relative.startswith('/') or any(p in ('','..','.') or '\\' in p for p in parts):
        raise CollectionError('PATH-ESCAPE')
    descriptors = []
    try:
        descriptors.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts[:-1]:
            descriptors.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptors[-1]))
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptors[-1])
        descriptors.append(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CollectionError('PATH-ESCAPE')
        # Read at most bound+1; the parser decides response truncation.
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(8192, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        return bytes(data)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise CollectionError('SOURCE-MISSING') from None
    except OSError:
        raise CollectionError('PATH-ESCAPE') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise CollectionError('MANIFEST-INVALID')
        obj[key] = value
    return obj


def _scope(endpoints, accepted_scope, *, identity_key=None, identity_key_id=None):
    endpoints = [dict(endpoint) for endpoint in endpoints]
    if accepted_scope is not None and (not isinstance(accepted_scope,dict) or
            not set(accepted_scope) <= {'endpoint_tokens','identity_binding'}):
        raise CollectionError('MANIFEST-INVALID')
    try:
        authority = scope_binding.caller_scope(endpoints, identity_key, identity_key_id)
        decision = scope_binding.compare_scopes(authority, authority, accepted_scope)
    except scope_binding.BindingError as error:
        raise CollectionError(error.code) from None
    mapping = authority['endpoint_tokens']
    digest_input = dict(endpoint_tokens=mapping, method='HEAD', http_version='HTTP/1.1', user_agent=UA)
    if 'identity_binding' in authority:
        digest_input['identity_binding'] = authority['identity_binding']
    comparison = dict(status=decision['comparison'], **{name:decision[name] for name in
        ('removed_endpoint_ids','changed_endpoint_ids','added_endpoint_ids')})
    result = dict(status='declared', endpoint_tokens=mapping, digest_input=digest_input,
                sanitized_sha256=hashlib.sha256(canonical(digest_input)).hexdigest(), comparison=comparison,
                **{name:decision[name] for name in ('scope_binding_status','scope_binding_reason','scope_authority')})
    if 'identity_binding' in authority:
        result['identity_binding'] = authority['identity_binding']
    return result


def _rebind(value, file):
    if isinstance(value, dict):
        return {key:(file if key == 'file' and val == 'response-head.txt' else _rebind(val,file)) for key,val in value.items()}
    if isinstance(value, list):
        return [_rebind(item,file) for item in value]
    return value


def _fixture_endpoints(fixture_dir):
    root = Path(fixture_dir)
    try:
        raw_manifest = _read_regular(root, 'manifest.json', 65536)
        if len(raw_manifest) > 65536:
            raise CollectionError('MANIFEST-INVALID')
        manifest = json.loads(raw_manifest.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError):
        raise CollectionError('MANIFEST-INVALID') from None
    keys = set(FLAGS) | {'schema_version','mode','endpoints'}
    if not isinstance(manifest, dict) or set(manifest) != keys or manifest['schema_version'] != 'http-fixture-001' or manifest['mode'] != 'offline_fixture':
        raise CollectionError('MANIFEST-INVALID')
    if any(manifest[k] is not v for k,v in FLAGS.items()):
        raise CollectionError('MANIFEST-INVALID')
    endpoints = manifest['endpoints']
    if not isinstance(endpoints, list) or not 1 <= len(endpoints) <= ENDPOINT_CAP:
        raise CollectionError('MANIFEST-INVALID')
    for endpoint in endpoints:
        _endpoint(endpoint)
    if len({e['id'] for e in endpoints}) != len(endpoints) or len({e['scope_token'] for e in endpoints}) != len(endpoints):
        raise CollectionError('SCOPE-INTEGRITY-FAULT')
    return [dict(endpoint) for endpoint in endpoints]


def collect_fixture(fixture_dir, out, accepted_scope=None, *, identity_key=None, identity_key_id=None):
    root, target = Path(fixture_dir), Path(out)
    if target.exists() or target.is_symlink():
        raise CollectionError('OUTPUT-EXISTS')
    endpoints = _fixture_endpoints(root)
    scope = _scope(endpoints, accepted_scope, identity_key=identity_key, identity_key_id=identity_key_id)
    cases = []
    for endpoint in endpoints:
        data = _read_regular(root, endpoint['response_file'], HEAD_CAP, missing_ok=True)
        public = dict(endpoint_id=endpoint['id'], scope_token=endpoint['scope_token'], scheme=endpoint['scheme'],
                      source_kind='synthetic', method='HEAD', http_version='HTTP/1.1', user_agent=UA,
                      observation_time=None, collector_location_id=None, address_family=None,
                      address_class=None, domain_status='declared')
        if data is None:
            cases.append(dict(public, capture_status='not_observed', gap='SOURCE-MISSING',
                              facts=None, metadata=None, fields=[], status_class=None,
                              policy_status='not_observed', sanitized_head=None, redaction_withheld=[]))
            continue
        result = sanitize_response(data, endpoint, endpoint['complete'])
        cases.append(dict(public, capture_status=result['facts']['capture_status'],
                          gap=result['facts']['gaps'][0] if result['facts']['gaps'] else None,
                          status_class=result['facts']['status_code'] // 100 if result['facts']['status_code'] else None,
                          policy_status=result['facts']['policy']['policy_status'],
                          facts=result['facts'], metadata=result['metadata'], fields=result['fields'],
                          sanitized_head=result['sanitized_head'], redaction_withheld=result['redaction_withheld']))
    publish_observations(cases, target, selected_scope=scope, mode='offline_fixture')


def publish_observations(observations, out, *, selected_scope, mode='offline_fixture'):
    """Internal emitter for already-sanitised observations, never raw inputs.

    This is a trusted collector boundary, not an external JSON ingest API.
    Caller must use sanitize_response and closed metadata/TLS extraction;
    arbitrary external dictionaries are not authorised emitter inputs.
    """
    target = Path(out)
    if mode not in ('offline_fixture', 'live') or target.exists() or target.is_symlink():
        raise CollectionError('OUTPUT-EXISTS')
    if not isinstance(observations, list) or not isinstance(selected_scope, dict):
        raise CollectionError('OUTPUT-BINDING-INVALID')
    expected = selected_scope.get('endpoint_tokens')
    if not isinstance(expected, dict) or len(observations) != len(expected):
        raise CollectionError('OUTPUT-BINDING-INVALID')
    actual = [case.get('endpoint_id') for case in observations if isinstance(case,dict)]
    if len(actual) != len(observations) or len(set(actual)) != len(actual) or set(actual) != set(expected):
        raise CollectionError('OUTPUT-BINDING-INVALID')
    artefacts, cases, rows = {}, [], []
    public_keys = {'endpoint_id','scope_token','scheme','source_kind','method','http_version','user_agent',
                   'observation_time','collector_location_id','address_family','address_class','domain_status',
                   'capture_status','gap','status_class','facts','metadata','fields','policy_status','tls','transport','qualifiers'}
    for observation in observations:
        if observation.get('scope_token') != expected[observation['endpoint_id']] or not ENDPOINT_ID.fullmatch(observation['endpoint_id']):
            raise CollectionError('OUTPUT-BINDING-INVALID')
        case = {key:value for key,value in observation.items() if key in public_keys}
        text = observation.get('sanitized_head')
        withheld = observation.get('redaction_withheld', [])
        file = 'raw/response-heads/' + case['endpoint_id'] + '.txt'
        case = _rebind(case,file)
        withheld = _rebind(withheld,file)
        if text is not None:
            if not isinstance(text,str):
                raise CollectionError('OUTPUT-BINDING-INVALID')
            validate_marker_accounting(text,withheld,file)
            artefacts[file] = text.encode('ascii')
            rows.extend(withheld)
        elif withheld or case.get('capture_status') == 'observed':
            raise CollectionError('OUTPUT-BINDING-INVALID')
        case.setdefault('tls', dict(status='not_observed', source_kind=case['source_kind'],
                                    prohibition_observability=dict(status='not_observed', reason='TLS-NOT-CAPTURED')))
        case.setdefault('transport', dict(status='not_observed' if mode == 'offline_fixture' else 'observed', mode=mode))
        request_profile = dict(method='HEAD', http_version='HTTP/1.1', user_agent=UA)
        case.setdefault('qualifiers', dict(endpoint_id=case['endpoint_id'], **request_profile,
                        address_family=case.get('address_family'), address_class=case.get('address_class'),
                        status_class=case.get('status_class'), observation_utc=case.get('observation_time'),
                        collector_location_id=case.get('collector_location_id'),
                        request_profile_sha256=hashlib.sha256(canonical(request_profile)).hexdigest()))
        cases.append(case)
    fact_record = dict(FLAGS, schema='assure.http.facts.v1', mode='offline_fixture',
                       selected_scope=selected_scope, endpoints=cases)
    fact_record['mode'] = mode
    artefacts['raw/HTTP-FACTS.json'] = canonical(fact_record) + b'\n'
    sidecar = dict(FLAGS, schema='assure.http.collection-sidecar.v1', mode=mode, source_kind='synthetic' if mode == 'offline_fixture' else 'live',
                   selected_scope=selected_scope, redaction_withheld=rows,
                   sanitized_sha256={file:hashlib.sha256(data).hexdigest() for file,data in sorted(artefacts.items())},
                   audit=dict(sockets='not_executed_fixture' if mode == 'offline_fixture' else 'caller_audit_required',
                              subprocesses='not_executed_fixture' if mode == 'offline_fixture' else 'caller_audit_required',
                              live_identity='not_observed', file_reads='explicit_manifest_regular_files_only' if mode == 'offline_fixture' else 'caller_audit_required'),
                   bounds=dict(endpoints=ENDPOINT_CAP, header_bytes=HEAD_CAP, fields=FIELD_CAP, physical_line_bytes=LINE_CAP))
    artefacts['raw/COLLECTION-SIDECAR.json'] = canonical(sidecar) + b'\n'
    # First output byte is already sanitised. No source or arbitrary error
    # string has been written or hashed. Output is a fresh caller-selected dir.
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix='.http-sanitized-', dir=target.parent))
        for file,data in sorted(artefacts.items()):
            destination = stage / file
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(data)
        if target.exists() or target.is_symlink():
            raise CollectionError('OUTPUT-EXISTS')
        os.replace(stage, target)
        stage = None
    except OSError:
        raise CollectionError('OUTPUT-WRITE-ERROR') from None
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def _read_identity_key_fd(fd):
    """Explicit caller-owned nonblocking pipe; exact32 bytes plus EOF, <=1s."""
    try:
        if type(fd) is not int or fd <= 2 or not stat.S_ISFIFO(os.fstat(fd).st_mode) or os.get_blocking(fd):
            raise CollectionError('IDENTITY-KEY-FD-INVALID')
        deadline = time.monotonic()+1.0
        value = bytearray()
        while True:
            left = deadline-time.monotonic()
            if left <= 0 or not select.select([fd], [], [], max(0.0,left))[0]:
                raise CollectionError('IDENTITY-KEY-FD-TIMEOUT')
            try:
                part = os.read(fd, 33-len(value))
            except BlockingIOError:
                continue
            if not part:
                if len(value) != 32:
                    raise CollectionError('IDENTITY-KEY-FD-LENGTH')
                return bytes(value)
            value.extend(part)
            if len(value) > 32:
                raise CollectionError('IDENTITY-KEY-FD-LENGTH')
    except CollectionError:
        raise
    except (OSError, ValueError, TypeError):
        raise CollectionError('IDENTITY-KEY-FD-INVALID') from None


def _write_caller_scope(path, scope):
    path = Path(path).absolute()
    if not re.fullmatch(r'[A-Za-z0-9_-]*scope[A-Za-z0-9_-]*\.json', path.name):
        raise CollectionError('SCOPE-AUTHORITY-FILENAME')
    opened, stream, created = [], None, False
    try:
        content = canonical(scope)+b'\n'
        opened.append(os.open('/', os.O_RDONLY|os.O_DIRECTORY))
        for part in path.parts[1:-1]:
            opened.append(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=opened[-1]))
        stream = os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=opened[-1])
        created = True
        offset = 0
        while offset < len(content):
            written = os.write(stream,content[offset:])
            if written <= 0:
                raise OSError()
            offset += written
    except OSError:
        if created:
            try: os.unlink(path.name,dir_fd=opened[-1])
            except OSError: pass
        raise CollectionError('OUTPUT-WRITE-ERROR') from None
    finally:
        if stream is not None: os.close(stream)
        for fd in reversed(opened): os.close(fd)


def main(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            raise CollectionError('CLI-INVALID')
    parser = SafeParser(description='Offline synthetic HTTP fixture collector candidate')
    parser.add_argument('--fixture-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--scope-only', action='store_true')
    parser.add_argument('--identity-key-fd', type=int)
    parser.add_argument('--identity-key-id')
    # No --endpoints live mode until separate implementation and review.
    try:
        args = parser.parse_args(argv)
        if (args.identity_key_fd is None) != (args.identity_key_id is None):
            raise CollectionError('IDENTITY-KEY-INVALID')
        identity_key = _read_identity_key_fd(args.identity_key_fd) if args.identity_key_fd is not None else None
        if args.scope_only:
            endpoints = _fixture_endpoints(args.fixture_dir)
            try:
                authority = scope_binding.caller_scope(endpoints,identity_key,args.identity_key_id)
            except scope_binding.BindingError as error:
                raise CollectionError(error.code) from None
            _write_caller_scope(args.out,authority)
        else:
            collect_fixture(args.fixture_dir, args.out, identity_key=identity_key, identity_key_id=args.identity_key_id)
    except CollectionError as error:
        print(json.dumps(dict(FLAGS, status='collection_error', code=error.code), sort_keys=True))
        return 2
    except Exception:
        print(json.dumps(dict(FLAGS, status='collection_error', code='INTERNAL-ERROR'), sort_keys=True))
        return 2
    print(json.dumps(dict(FLAGS, status='scope_generated' if args.scope_only else 'collected', mode='offline_fixture'), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
