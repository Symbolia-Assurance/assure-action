# Reading a verdict

A check writes one JSON file. The Action writes it at its `output` path. The API returns it as the response body.

There is no overall pass or fail. Each obligation has its own reading. The only summary is the policy exit, which follows the `fail-on` setting you chose.

## 1. The verdict envelope

Schema `assure.serve.verdict/v1`.

| Field | Meaning |
|---|---|
| `schema` | Always `assure.serve.verdict/v1`. |
| `check_id` | A random 32-character hex id for this check. |
| `profile` | The profile that ran, for example `postgresql-observed-baseline`. |
| `profile_version` | The version of that profile's checker entry. |
| `engine` | `commit`, `release_sha256` and `checkers_sha256`: the exact engine that produced the readings. |
| `input` | `files`: each file's `path`, `bytes` and `sha256`. `bundle_sha256`: one digest over that list. |
| `outcome` | `verdict` when at least one obligation reads holds, fails, deviates or vacuous. `no_verdict` when none does. |
| `readings` | The checker's full output, unchanged. This is the proof tree (section 3). |
| `counts` | The number of obligations in each status. Every status appears, including those at zero. |
| `a0` | Null, or the reason the input failed its integrity gate (section 7). |
| `rows` | One line per obligation: `machine`, `id`, `status`, `status_text`, `authority` and `reason`. |
| `policy` | `fail_on`: the statuses that fail the job (`not_collected` already expanded). `exit` and `reason`: see section 9. |
| `scope_notes` | Limits that bound every reading in this check. See [SCOPE.md](SCOPE.md). |
| seven flags | Fixed record flags: `execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation`, `simulation`, `self_approved`. A verdict authorises no change, release or action. |

When no verdict can be made, the file is a failure envelope instead, schema `assure.serve.failure/v1`: `check_id`, `outcome`, `reason`, `action`, `detail` and the same flags. The quickstarts list every failure outcome.

## 2. The nine statuses

Four statuses are verdicts. Five are not.

| Status | Verdict | Meaning | How it is written |
|---|---|---|---|
| `holds` | yes | The observed system meets the obligation over a non-empty observed domain. | "holds", or "holds in database <db>". It is bounded by its qualifiers. |
| `fails` | yes | An unconditional vendor requirement, or an unconditional safety property computed from observation, is broken. | "fails: <row id>" |
| `deviates` | yes | A recommendation is not followed. `authority` says whose recommendation. | "deviates from vendor guidance <row id>" or "deviates from the Assure baseline <row id>" |
| `vacuous` | yes | The observed domain is empty. There is nothing to check. | "vacuous: observed empty domain", sometimes with " in database <db>". It always carries `domain_locator`. |
| `needs_intent` | no | The rule depends on what the system is for. | "needs intent", or "needs intent in database <db>"; its reason reads "needs intent: out of scope for Assure", with the observations listed |
| `not_observed` | no | A fact the reading needs was not collected or could not be read. | "not observed: <what> (<locator>)" |
| `missing_baseline` | no | A baseline row the reading needs is absent or not documented for this major. | "missing baseline: <row id> not pinned for major <n>" |
| `missing_method` | no | The checker has no method for this input shape. | "missing method: <gap id>" |
| `representation` | no | The input could not be represented faithfully, or a typed internal failure occurred. | "representation: <reason>" |

How to read them:

- **vacuous** means the domain was empty. It is a statement about emptiness. It is a different result from holds.
- **deviates** is a departure from a recommendation. It is a different result from fails. `authority: "vendor"` means the PostgreSQL documentation recommends it. `authority: "assure"` means the Assure baseline recommends it.
- **not observed** means the fact was missing. Nothing was checked for that reading.
- **needs intent** means the answer depends on your purpose, which Assure does not ask for. The observations are listed so you can judge.
- **missing baseline**, **missing method** and **representation** are limits of the checker or its input. They say nothing about your system.

### Precedence

When cases or parts of an obligation combine, the first status present in this list wins:

fails > deviates > representation > missing_method > not_observed > missing_baseline > needs_intent > holds > vacuous

All parts vacuous gives vacuous. Holds plus vacuous gives holds.

## 3. One reading

Readings sit at `readings.M<n>.obligations.<id>`. `readings.order` lists the 40 ids in profile order.

| Field | Meaning |
|---|---|
| `status` | One of the nine statuses. |
| `status_text` | The short text from the table above. Show it as given. |
| `reason` | The full reason. For not observed it names what is missing and where it was looked for. |
| `authority` | Present on deviates: `vendor` or `assure`. |
| `witness` | For fails, deviates and needs intent: the example that shows it. Null otherwise. |
| `qualifiers` | Strings that bound the reading, such as the database it covers. |
| `observations` | Observed facts that bear on the reading. |
| `premises` | Every input the reading used, each with its source (section 4). |
| `domain_locator` | For vacuous: where the empty domain was looked for. Null otherwise. |
| `statement` | The obligation, in words. |

## 4. Premises and their sources

Each premise has a `field`, a `source` and a `role` (`reads` or `informational`). The sources you will see:

| Source | Meaning |
|---|---|
| `observed` | Read from your system. It names the file (`artefact`), its `artefact_sha256` and a `locator` inside it. |
| `baseline` | A pinned public baseline row. It names the `row`, its digest and its `authority_class`: `vendor_documentation` or `assure_baseline`. |
| `declared` | A value you supplied in `raw/declaration.json`. It can only tighten a baseline. |
| `intent_required` | An input only you can give. The reading is "needs intent: out of scope for Assure". |
| `not_observed` | A fact that was missing. It names the gap. |

A few premises carry method tags such as `model_constant` or `domain_restriction`. These are internal to the checker's method.

A verdict never reads a premise that is not observed or that needs intent.

## 5. The 40 obligations

24 are intent-free and 16 are intent-bound. Scope `db` means the connected database only. Scope `cl` means the whole cluster.

| Id | Machine | Class | Scope | Statement |
|---|---|---|---|---|
| PRIV-1 | M1 | intent-bound | db | Declared ordinary-ACL privilege queries are answered as expected. |
| PRIV-2-OB | M1 | intent-free | cl | No login other than an observed superuser or the collection role can become superuser or reach the server-file/program roles. |
| PRIV-3 | M1 | intent-bound | db | Roles declared disjoint share no ordinary ACL privilege. |
| PRIV-4 | M1 | intent-bound | db | No sensitive object has a PUBLIC ACL entry. |
| PRIV-5 | M1 | intent-bound | db | Default ACLs equal the expected ACLs. |
| PRIV-6 | M1 | intent-bound | db | Declared revokes leave no dependent grant. |
| GRANT-OPTION-POLICY | M1 | intent-bound | db | No sensitive-object grant option is held outside the administrators. |
| HBA-1-OB | M2 | intent-free | cl | No non-host-local TCP tuple is decided by trust, or by password on a non-hostssl record. |
| HBA-2 | M2 | intent-bound | cl | Every intended connection is accepted by its expected method and record. |
| HBA-3-OB | M2 | intent-free | cl | No configured pg_hba record is fully shadowed over the configured tuple domain. |
| HBA-4 | M2 | intent-bound | cl | Physical replication is admitted only for the operator's roles and standby addresses. |
| HBA-5-OB | M2 | intent-free | cl | Every record admitting a BL-ASSURE-TLS-PRIV-1 login from a non-host-local address is hostssl. |
| HBA-6 | M2 | intent-free | cl | The server's own pg_hba parse has no error rows and loaded rules equal the file (not observable in this version). |
| TLS-1-OB | M3 | intent-free | cl | Every server-originated channel uses verify-full. |
| TLS-2-OB | M3 | intent-free | cl | Every non-host-local record admitting a privileged login is hostssl and ssl is on. |
| TLS-3 | M3 | intent-bound | cl | Records required to use client certificates use cert or verify-full with ssl_ca_file set. |
| TLS-4-OB | M3 | intent-free | cl | With ssl on, ssl_min_protocol_version is at or above PG-BL-TLS-MIN-1. |
| TLS-5-OB | M3 | intent-free | cl | With ssl on, the key file is 0600, or 0640 root-owned (not observed while the mode is not collected). |
| REP-1-OB | M4 | intent-free | cl | Every admissible physical replication path uses non-trust auth off-host, an explicit role and a non-wide address off-host. |
| REP-2-OB | M4 | intent-free | cl | Every physical slot has a matching standby consumer with bounded retention. |
| REP-3-CONFIG | M4 | intent-bound | cl | Required no-loss durability selects a reachable synchronous standby. |
| REP-3 | M4 | intent-bound | cl | No committed transaction is lost on primary failure, when required. |
| RLS-1-OB | M5 | intent-free | db | No protected relation is read or written unfiltered by a non-superuser, non-BYPASSRLS, non-owner path. |
| RLS-2 | M5 | intent-bound | db | Required policies exist and imply the operator's tenant predicate. |
| RLS-3 | M5 | intent-bound | db | INSERT/UPDATE admission implies the operator's new-row predicate. |
| RLS-4-OB | M5 | intent-free | db | Owner-mode views over protected relations are listed. |
| SD-1-OB | M6 | intent-free | db | Every privileged SECURITY DEFINER function sets its own search_path, pg_temp last, no PUBLIC-writable schema. |
| SD-2-OB | M6 | intent-free | db | Privileged SECURITY DEFINER functions with PUBLIC EXECUTE are listed. |
| SD-3-OB | M6 | intent-free | db | No schema on a login's session search_path is CREATE-able by PUBLIC. |
| SD-4-OB | M6 | intent-free | db | The public schema has no PUBLIC CREATE. |
| SU-1 | M7 | intent-bound | cl | Observed superusers are exactly the operator's administrators. |
| SU-2-OB | M7 | intent-free | cl | Transitive memberships in the server-file/program roles are listed. |
| SU-3-OB | M7 | intent-free | cl | Transitive memberships in pg_read_all_data / pg_write_all_data are listed. |
| SU-4-OB | M7 | intent-free | cl | Every membership in the remaining predefined roles is a vendor-default edge. |
| LR-1 | M8 | intent-bound | db | A publication cannot be read by a replication login other than the exclusive reader. |
| LR-1-SCOPE | M8 | intent-bound | db | Published tables stay within the intended tables. |
| LR-2-OB | M8 | intent-free | db | run_as_owner is false unless each target owner equals the subscription owner. |
| LR-2-APPLY-OB | M8 | intent-free | db | Each subscription target can be applied as its owner. |
| LR-3-OB | M8 | intent-free | cl | Each subscription uses verify-full, password_required true, a non-superuser owner. |
| LR-4-OB | M8 | intent-free | db | Publisher roles with SUPERUSER or BYPASSRLS are listed. |

Every intent-bound obligation reads needs intent. The "listed" obligations read needs intent with the list when something is found, and vacuous when nothing is.

## 6. An empty database

A new, default database reads mostly **needs intent** and **vacuous**. That means there is little to check. The 16 intent-bound obligations always need intent. An empty database has no ordinary logins, tables, definer functions or subscriptions, so many domains are empty.

On the official PostgreSQL 18 image the expected counts are about: needs intent 16, vacuous 13, holds 4, deviates 2, not observed 3, missing baseline 2, fails 0. These counts may shift as baseline rows are pinned.

## 7. "No verdicts" and input integrity

- **No verdicts.** `outcome` is `no_verdict` when no obligation reads holds, fails, deviates or vacuous. Nothing could be checked, so `policy.exit` is 3 with `policy.reason` `no_verdict`, unless a reading has a status you fail on (then 1) or `fail-on` is `never` (then 0). Look at the not observed readings to see what was missing.
- **No reading: input integrity.** When `a0` is set, the input failed its integrity gate. Every reading is representation, with the gate's reason. `policy.exit` is 3 with `policy.reason` `input_integrity` under every policy except `never`. Fix the collection and run again.

## 8. The declared profile

`postgresql-declared-model` reads per machine against a declaration you supply. Its statuses are holds, fails, vacuous, missing method, missing premise, representation and not evaluated. Holds, fails and vacuous are its verdicts. **Missing premise** means the declaration lacks a value the model needs. **Not evaluated** means the machine was not run; the reason says why. It is the profile served today.

## 9. The policy exit

`policy.exit` is the one number a CI job reads. `policy.reason` names why, and the job summary says it in plain words. The order:

| Order | `policy.reason` | `policy.exit` | When |
|---|---|---|---|
| 1 | `never` | 0 | `fail-on` is `never`. |
| 2 | `input_integrity` | 3 | The input-integrity gate stopped the check (`a0` is set). |
| 3 | `policy_failed` | 1 | A reading has a status you fail on. |
| 4 | `no_verdict` | 3 | No reading is a verdict: nothing was checked. |
| 5 | `policy_met` | 0 | Otherwise. |

Exit 2 is bad input, and a failure envelope gives its outcome's own exit, 3 for every outcome that has none. `fail-on` takes, for each profile, the statuses it can emit except holds and vacuous, the group word `not_collected`, or `never` alone; the quickstarts list them.
