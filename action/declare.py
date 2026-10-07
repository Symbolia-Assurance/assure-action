"""A declaration is a file in your repo at raw/declaration.json.

In a private source checkout: ``python3.14 -B -m assure.declare validate raw/declaration.json``.
In the public Action distribution: ``python3.14 -B -m action.declare validate raw/declaration.json``.
Both run free local shape validation from the same published bytes.
Exit 0 means valid structure; exit 2 means invalid input. Operator confirmations and coverage gaps remain named.
Legacy runtime declarations stay supported; add schema and id to pass the new public version. This module adds
no runtime gate, no SQL parser, no model call and no verdict. The bundled schema is the validation source.
Its annotated runtime integer encoding rule additionally rejects 17.0, which standard JSON Schema permits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = 'assure.postgresql.declaration/v1'
MAX_BYTES = 1048576
SCHEMA_PATH = Path(__file__).with_name('schemas') / 'postgresql-declaration-v1.schema.json'


def schema_document():
    """Read the published, bundled Draft 2020-12 declaration schema."""
    return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))


def _pointer(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _validate(value, rule, path, errors):
    """Interpret only the keywords used by our bundled schema, with strict JSON Python types.

    This is a declaration validator, not a general JSON Schema implementation. It never fetches external schemas.
    Unknown validation keywords in the bundled contract fail as a programming error instead of being ignored.
    """
    known = {'$schema', '$id', 'title', 'description', 'type', 'const', 'enum', 'pattern', 'minLength',
             'minimum', 'maximum', 'properties', 'propertyNames', 'required', 'additionalProperties',
             'dependentRequired', 'items', 'prefixItems', 'minItems', 'maxItems', 'uniqueItems',
             'x-runtime-integer-encoding',
             'execution_authorized', 'hardware_authorized', 'industrial_release_authorized',
             'release_allowed', 'physical_validation', 'simulation', 'self_approved'}
    if rule.keys() - known:
        raise ValueError('Unsupported validation keyword in bundled schema')
    def error(code, message):
        errors.append({'path': path, 'code': code, 'message': message})
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    expected = rule.get('type')
    if expected is not None:
        expected = expected if type(expected) is list else [expected]
        if not any((type(value) is int or type(value) is float and value.is_integer())
                   if name == 'integer' else type(value) is types[name] for name in expected):
            error('type', 'Expected ' + ' or '.join(expected) + '.'); return
    if rule.get('x-runtime-integer-encoding') and type(value) is not int:
        error('runtime_integer_encoding', 'The frozen derive step requires integer JSON encoding, such as 17; JSON Schema alone also permits 17.0.')
    if 'const' in rule and (type(value) is not type(rule['const']) or value != rule['const']):
        error('const', 'Expected the value fixed by the schema.')
    if 'enum' in rule and not any(type(value) is type(item) and value == item for item in rule['enum']):
        error('enum', 'Expected one of the values listed in the schema.')
    if type(value) is str:
        if len(value) < rule.get('minLength', 0): error('minLength', 'Expected a nonempty string.')
        if 'pattern' in rule:
            pattern = rule['pattern']
            # Python's $ accepts a position before a final newline. Published
            # whole-string identifier/mode patterns must cover every character;
            # unanchored patterns such as \\S retain JSON Schema search semantics.
            matcher = re.fullmatch if pattern.startswith('^') and pattern.endswith('$') else re.search
            if matcher(pattern, value) is None:
                error('pattern', 'Expected the string form listed in the schema.')
    if type(value) is int:
        if 'minimum' in rule and value < rule['minimum']: error('minimum', 'Below the schema minimum.')
        if 'maximum' in rule and value > rule['maximum']: error('maximum', 'Above the schema maximum.')
    if type(value) is dict:
        props = rule.get('properties', {})
        required = set(rule.get('required', []))
        for key, needed in rule.get('dependentRequired', {}).items():
            if key in value: required.update(needed)
        for key in sorted(required - value.keys()):
            errors.append({'path':_pointer(path,key),'code':'required','message':'Required field is missing.'})
        for key, item in value.items():
            if 'propertyNames' in rule: _validate(key, rule['propertyNames'], _pointer(path,key), errors)
            if key in props: _validate(item, props[key], _pointer(path,key), errors)
            elif rule.get('additionalProperties') is False:
                errors.append({'path':_pointer(path,key),'code':'unknown_field','message':'Field is absent from this schema version.'})
            elif type(rule.get('additionalProperties')) is dict:
                _validate(item, rule['additionalProperties'], _pointer(path,key), errors)
    if type(value) is list:
        if len(value) < rule.get('minItems',0): error('minItems', 'Too few array entries.')
        if len(value) > rule.get('maxItems', len(value)): error('maxItems', 'Too many array entries.')
        if rule.get('uniqueItems') and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            error('uniqueItems', 'Array entries must be distinct.')
        prefix = rule.get('prefixItems', [])
        for index, item in enumerate(value):
            item_rule = prefix[index] if index < len(prefix) else rule.get('items', {})
            if item_rule is False:
                errors.append({'path':_pointer(path,index),'code':'items','message':'Extra array entry is absent from the schema.'})
            else: _validate(item, item_rule, _pointer(path,index), errors)


def _notice(code, path, message):
    return {'code':code, 'path':path, 'message':message}


def _notes(value):
    confirmations = [_notice('declared_model', '',
        'Confirm the declaration and collected files describe the same database and PostgreSQL major. '
        'The checker reasons over a bounded declared model; catalog conformance remains a separate question.')]
    gaps = []
    if 'protected_tables' in value:
        if value['declared_predicate'].strip().lower() in ('true', 'false'):
            gaps.append(_notice('literal_predicate_boundary', '/declared_predicate',
                'A literal true or false boundary does not describe tenant isolation. '
                'True admits every row and cannot expose an overbroad USING(true) policy against this boundary; '
                'false denies every row. Confirm the intended boundary before claiming tenant isolation.'))
        confirmations.extend([
            _notice('predicate_semantics', '/declared_predicate',
                'Confirm this predicate means each user may read only their own tenant rows. Tenant semantics are an operator assumption.'),
            _notice('sql_text_equality', '/declared_predicate',
                'The derive step recognizes normalized SQL-text equality with this predicate as tenant equality. '
                'It does not parse or prove the meaning of arbitrary SQL, auth.uid(), joins or functions.'),
            _notice('session_tenant', '/protected_tables',
                'Confirm each login/session identity is represented by the finite tenant_a abstraction. '
                'The model uses two non-NULL tenants and assigns tenant_a to every derived path; JWT and connection identity are not observed.'),
            _notice('access_paths_complete', '/access_paths_complete',
                'Confirm the supplied catalog includes every relevant direct and view route. The checker derives at most four paths for one protected table. '
                'SET ROLE routes and real session tenant mapping require separate evidence.'),
            _notice('exemptions', '/rls_exempt_logins',
                'Confirm all named exempt logins and view exemptions are intentional. Exempt access reduces the isolation domain.')])
        if not value['protected_tables']:
            gaps.append(_notice('empty_protected_domain','/protected_tables','No protected table is declared; tenant isolation has an empty domain.'))
        if len(value['protected_tables']) > 1:
            gaps.append(_notice('protected_table_bound','/protected_tables','The current RLS model represents only the first matching protected table.'))
        if value['access_paths_complete'] is False:
            gaps.append(_notice('access_paths_incomplete','/access_paths_complete','Access paths are declared incomplete; provide the missing routes to establish complete coverage.'))
        gaps.extend([
            _notice('catalog_bounds','/protected_tables','Path and policy counts are checked after derivation: one table, at most four paths and four policies. This declaration alone cannot establish those counts.'),
            _notice('command_specific_policy','/protected_tables','The current RLS method accepts ALL policies. SELECT-only policy decisiveness depends on the command-specific RLS method; shape validation cannot establish it.'),
            _notice('finite_tenant_scope','/declared_predicate','NULL tenants, arbitrary SQL, joins, functions, triggers, RETURNING and integrity-check side channels are outside the finite tenant model.')])
    else:
        gaps.append(_notice('tenant_intent_absent','/protected_tables','No tenant-isolation intent is declared. Add protected_tables, declared_predicate and access_paths_complete.'))
    for field, code, text in [
        ('database_owner','role_intent_absent','M1/M7 need a database owner present in the snapshot; role and privilege intent is read from the declaration.'),
        ('loaded_identity','loaded_identity_absent','M2 needs confirmation that loaded HBA rules match supplied files.'),
        ('tls_floor','tls_intent_absent','M3 needs a TLS floor, key mode/owner and optional client channels; server build and certificate presence are assumptions.'),
        ('caller','function_intent_absent','M6 needs caller, schema and authority intent; absent function declarations do not establish function safety.'),
        ('intended_tables','replication_intent_absent','M8 needs intended replication tables and exclusive reader intent when replication is present.')]:
        if field not in value: gaps.append(_notice(code,'/'+field,text))
    for field, code, text in [
        ('intended_flows','intended_authentication','Confirm intended connection credentials work; normalized intended flows assume successful authentication.'),
        ('loaded_identity','loaded_hba_identity','Confirm loaded HBA identity against the server; supplied disk rules stand in for loaded rules.'),
        ('tls_floor','tls_environment','Confirm server TLS support, certificate/key presence and configured key mode/owner. '
         'Optional clients.json channels assume certificate chain, hostname, client identity and credential validity; GSS availability is modeled false.'),
        ('ca_bindings','ca_identity','Confirm every declared channel CA is bound to the intended single server identity.'),
        ('standbys','standby_authentication','Confirm standby roles, addresses, credentials, slot creation authority and retention/no-loss declarations.'),
        ('authority_complete','function_authority','Confirm function caller, owner-only login, untrusted roles and complete schema authority are represented.'),
        ('intended_tables','replication_authority','Confirm intended tables, trusted owners, exclusive reader and publisher superuser/BYPASSRLS exceptions.')]:
        if field in value: confirmations.append(_notice(code,'/'+field,text))
    for field, limit in [('standbys',2),('privilege_queries',32),('disjoint_duties',32),('default_acl_expectations',32),('declared_revokes',32)]:
        if len(value.get(field,[])) > limit:
            gaps.append(_notice('declaration_bound','/'+field, f'The derive step represents at most {limit} entries in this field.'))
    return confirmations, gaps


def validate(value):
    """Return structure errors, operator confirmations and coverage gaps; never a database verdict."""
    errors = []
    _validate(value, schema_document(), '', errors)
    confirmations, gaps = _notes(value) if not errors else ([], [])
    return {'schema':'assure.declaration.validation/v1','declaration_schema':SCHEMA,
            'id':value.get('id') if not errors else None, 'valid':not errors,
            'meaning':'Valid structure. Confirm the named assumptions and run the declared-model checker.' if not errors else 'Invalid declaration structure.',
            'errors':errors, 'operator_confirmations':confirmations, 'coverage_gaps':gaps}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


def _reject_constant(_):
    raise ValueError('Non-finite JSON number')


def validate_file(path):
    """Read at most the profile's declaration byte limit. Input failures carry no supplied values."""
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES: raise ValueError('Declaration exceeds byte limit')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, RecursionError):
        result = validate({})
        result['errors'] = [_notice('input_unreadable','', 'Expected a readable UTF-8 JSON object within 1048576 bytes, with distinct keys and finite numbers.')]
        return result
    return validate(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('validate', help='Check declaration structure and name operator confirmations.')
    command.add_argument('path')
    args = parser.parse_args(argv)
    result = validate_file(args.path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false;
# physical_validation false; simulation true; self_approved false.
