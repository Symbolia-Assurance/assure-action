"""Deterministic PostgreSQL intent instructions shared by the Action and its renderer.

These name declaration inputs, never infer customer intent or change a checker reading.
The catalog drafter supplies observed candidates; absent intent remains for the customer.
"""
PROFILE = 'postgresql-observed-baseline'
DECLARATION_PATH = '.assure/postgresql-declared-model.json'
STARTER_FILE = 'assure-postgresql-declaration-draft.json'
STARTER_LINE = ('Starter declaration: `%s`, in the `assure-postgresql-declaration` run artifact (beside the verdict locally); review its observed values and fill the fields '
                'named above. Merge Assure\'s proposal pull request if it opened one, or save the reviewed draft '
                'as `%s` and rerun. The starter is drafted from the withheld bundle: before saving it, replace each '
                '`\'<withheld literal N>\'` with the literal at that place in your own catalog, or the row-security '
                'machine (M5) is refused. Unstated intent stays undecided.' % (STARTER_FILE, DECLARATION_PATH))
# Said once under the comment's intent rows (remodel 37423 R1): the observed reading lists its fields on every run;
# the committed declaration is read by the declared reading, in the job summary's section of that name. Remodel 37535
# M2: the job summary prints the same sections (`_pr_sections`), so the words hold on both surfaces.
COMMITTED_LINE = ('Once the declaration is committed, the job summary\'s "Declared reading" section reads it and '
                  'decides these rows from the fields it states; this list still shows them.')

# Each value is (declaration fields, the decision the customer supplies). All intent-bound
# rows and the observed rows whose conjuncts can be graded needs_intent are covered.
STEPS = {
    'PRIV-1': ('privilege_queries', 'which roles should hold which table privileges'),
    'PRIV-2-OB': ('administrators, untrusted_roles', 'which roles may reach privileged roles'),
    'PRIV-3': ('disjoint_duties', 'which duties must stay separate'),
    'PRIV-4': ('sensitive_objects', 'which tables must exclude PUBLIC access'),
    'PRIV-5': ('default_acl_expectations', 'the expected privileges for future objects'),
    'PRIV-6': ('declared_revokes', 'which grants should be revoked'),
    'GRANT-OPTION-POLICY': ('sensitive_objects, administrators', 'which tables and roles may carry grant options'),
    'HBA-1-OB': ('trusted_addresses, forbidden_methods', 'which local connections and methods are intended'),
    'HBA-2': ('intended_flows', 'the intended user, database, address and connection rule'),
    'HBA-3-OB': ('shadow_allowed', 'which shadowed connection rules are intentional'),
    'HBA-4': ('replication_roles, standby_addresses', 'the intended replication roles and standby addresses'),
    'TLS-1-OB': ('ca_bindings', 'which CA and server identity each outgoing channel should trust'),
    'TLS-3': ('certificate_roles', 'which roles must present a client certificate'),
    'REP-1-OB': ('replication_roles, trusted_addresses', 'which roles and addresses are dedicated to replication'),
    'REP-3': ('no_loss_required', 'whether committed transactions must never be lost (true) or loss is allowed (false)'),
    'REP-3-CONFIG': ('no_loss_required', 'whether committed transactions must never be lost (true) or loss is allowed (false)'),
    'RLS-2': ('required_policies, declared_predicate, protected_tables', 'the required policies and tenant filter'),
    'RLS-3': ('declared_predicate, protected_tables', 'the allowed filter on inserted and changed rows'),
    'RLS-4-OB': ('view_exemptions, protected_tables', 'which owner-run view paths are intentional'),
    'SD-1-OB': ('untrusted_roles, caller, authority_complete', 'the callers and writers on the function search path'),
    'SD-2-OB': ('untrusted_roles, caller, authority_complete', 'which callers may run the owner-run functions'),
    'SD-3-OB': ('untrusted_roles, caller, authority_complete', 'which schema writers are trusted on the caller path'),
    'SU-1': ('administrators', 'which roles may hold superuser'),
    'SU-2-OB': ('administrators, untrusted_roles', 'which roles may reach server-file and program roles'),
    'SU-3-OB': ('administrators, untrusted_roles', 'which roles may reach broad data roles'),
    'SU-4-OB': ('administrators, untrusted_roles', 'which predefined-role memberships are intentional'),
    'LR-1': ('exclusive_reader', 'which role alone should read the replication stream'),
    'LR-1-SCOPE': ('intended_tables', 'which tables should be published'),
    'LR-2-OB': ('trusted_owners', 'which target-table owners the subscription may trust'),
    'LR-3-OB': ('ca_bindings', 'which CA and publisher identity the subscription should trust'),
    'LR-4-OB': ('allow_publisher_superuser, allow_publisher_bypassrls', 'whether the publisher may bypass row filters'),
}


def step(ob_id):
    """Plain next-step text, or None for a row outside the published intent contract."""
    if ob_id == 'RLS-5-OB':
        # remodel 37535 R2: only the observed check reads row_security_intent, from raw/declaration.json in its own
        # bundle; a connection run puts no declaration there and the declared reading ignores the key, so this step
        # never names DECLARATION_PATH (nor, alone, carries COMMITTED_LINE)
        return ('state row_security_intent for each table named by the reading in raw/declaration.json, beside the '
                'collected files in an artefacts directory: deny_all or readable; rerun the observed profile. '
                'A run that connects to the database does not read this field')
    spec = STEPS.get(ob_id)
    if spec is None:
        return None
    fields, intent = spec
    return 'state %s in %s at %s; review the starter and rerun' % (intent, fields, DECLARATION_PATH)


def proposal_steps(verdict):
    """A fixed-words checklist for the proposal PR, including fields the catalog cannot draft."""
    if not isinstance(verdict, dict) or verdict.get('profile') != PROFILE:
        return ''
    rows = [r for r in verdict.get('rows') or () if isinstance(r, dict) and r.get('status') == 'needs_intent']
    lines = ['- `%s`: %s.' % (r['id'], text) for r in rows for text in [step(r.get('id'))] if text]
    return ('\n\nFields to review for this reading (an absent value needs your intent):\n\n' + '\n'.join(lines)) if lines else ''
