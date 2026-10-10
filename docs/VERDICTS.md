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
| `outcome` | `verdict` when at least one obligation reads holds, fails or deviates (holds or fails for the declared profile). `no_verdict` otherwise. A vacuous reading alone is not a verdict: it says only that a domain was empty. |
| `readings` | The checker's full output, unchanged. This is the proof tree (section 3). |
| `counts` | The number of obligation readings in each status. Every status appears, including those at zero. A refused machine's own line is not an obligation reading and is not counted here: the sum of `counts` equals `completion.usable_readings.of`. |
| `machines_refused` | `count`: how many machines the checker refused; `by_status`: that count by the refused machine's status, for example `{"not_evaluated": 1, "missing_premise": 1}`. `{count: 0, by_status: {}}` when no machine was refused. |
| `a0` | Null, or the reason the input failed its integrity gate (section 7). |
| `machines` | `read`: the machines that gave readings of their own. `refused`: each machine that could not be read, with the checker's `reason` and its `status`: the status of that machine's own refusal line in `rows` where it has one, so the multiset of these statuses is `machines_refused.by_status`; where it has none, the status its reason names (`representation: pg_hba.conf absent from raw` is `representation`), else the profile's not-collected status for a machine with no readings at all (`not_observed` on the observed profiles, `not_evaluated` on the declared ones). You never have to guess it. `total`: every machine the profile checks (8). `source`: `reported` when the checker said which machines it refused, `inferred` when Assure worked it out from the readings (section 7). |
| `rows` | One line per obligation: `machine`, `id`, `status`, `status_text`, `authority` and `reason`. A refused machine keeps its own line in place, with `id` null, `kind: machine_refusal`, its `status`, its `reason` as the checker wrote it, and `needs`: `{kind, key, action}`, where `kind` is `declaration` (something to declare), `input` (something to collect) or `method` (no input admits it yet), `key` names what, and `action` says it in one sentence; `needs` is null when what admits that reason is not tabled yet, and the reason text is kept. `rows` and `counts` keep the checker's raw statuses. A row the checker kept on a machine it refused is coverage: every rendered surface (the first line, the summary, the annotations, the not-established list, the report) reads it as not observed. |
| `policy` | `fail_on`: the statuses that fail the job (`not_collected` already expanded; `unresolved-security` as written). `exit` and `reason`: see section 9. `allow_partial`: as you sent it; it changes nothing. |
| `colour`, `bounds`, `not_established`, `bias`, `completion` | The first line's colour, bounds and not-established list, the obligation classes, and the three completion answers: see section 9. |
| `observed_facts` | An object, `{}` unless the profile is `http-observed-baseline`. For each endpoint that was observed it holds `{endpoint id: the facts the readings used}` (the status code and the HSTS, CSP and cookie attributes), read from your uploaded `raw/HTTP-FACTS.json`, the file each reading's premise names. Its keys match each reading's `observations[].endpoint_id`. It is `{}` when that file is not the one the readings name. Cookie values and redirect URLs are never kept. |
| `scope_notes` | Limits that bound every reading in this check. See [SCOPE.md](SCOPE.md). |
| `warnings` | A list, empty when there is nothing to warn about. Each entry is `{kind, text, ...}`: `text` is one sentence, and `kind` names the entry's other fields; new kinds can be added later, so read `kind` before you read the rest. The kinds today are `endpoint_non_success` and `known_limit`. `endpoint_non_success` is on `http-observed-baseline`: an endpoint answered 4xx or 5xx, so the checker did not observe some policy checks for the whole run. Its entry is `{kind, endpoint_id, response_class, hidden_obligations, text}`, one per such endpoint, with `hidden_obligations` the sorted ids of the obligations left not observed on it. The summary shows each warning under the first line, and each is an annotation. A warning changes no status, count, colour or exit. Choose endpoints that answer HEAD with 2xx or 3xx. `known_limit`, on `postgresql-observed-baseline`, is `{kind, limit_id, obligation, machine, status, limits, text}`, one per served `RLS-1-OB` row of any status, with `limit_id` `OB-RLS1-ROUTE-KEYS-001`: a known limit of a served reading is disclosed beside the reading, and the reading stands as observed. |
| seven flags | Fixed record flags: `execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation`, `simulation`, `self_approved`. A verdict authorises no change, release or action. |

When no verdict can be made, the file is a failure envelope instead, schema `assure.serve.failure/v1`: `check_id`, `outcome`, `reason`, `action`, `detail` and the same flags. The quickstarts list every failure outcome. When the Action writes it, `detail.answered` names the request the API refused: `profiles` (the profile list, before anything is collected: a wrong or revoked key or a rate limit refused there sends nothing from your system), `check` (the upload) or `poll` (the request for a sent check's result).

## 2. The nine statuses

Four statuses are verdicts. Five are not. A vacuous reading alone does not make a check's outcome a verdict, because it says only that a domain was empty.

| Status | Verdict | Meaning | How it is written |
|---|---|---|---|
| `holds` | yes | The observed system meets the obligation over a non-empty observed domain. | "holds", or "holds in database \<db>". It is bounded by its qualifiers. |
| `fails` | yes | An unconditional vendor requirement, or an unconditional safety property computed from observation, is broken. | "fails: \<id>", where the id is a baseline row or a safety property (such as OSP-AUTH-1), with " in database \<db>" on a database-scoped obligation |
| `deviates` | yes | A recommendation is not followed. `authority` says whose recommendation. | "deviates from vendor guidance \<row id>" or "deviates from the Assure baseline \<row id>" |
| `vacuous` | yes | The observed domain is empty. There is nothing to check. | "vacuous: observed empty domain", sometimes with " in database \<db>". It always carries `domain_locator`. |
| `needs_intent` | no | The rule depends on what the system is for. | "needs intent", or "needs intent in database \<db>"; its reason reads "needs intent: out of scope for Assure", with the observations listed |
| `not_observed` | no | A fact the reading needs was not collected or could not be read. | "not observed: \<what> (\<locator>)" |
| `missing_baseline` | no | A baseline row the reading needs is absent or not documented for this major. | "missing baseline: \<row id> not pinned for major \<n>" |
| `missing_method` | no | The checker has no method for this input shape. | "missing method: \<gap id>" |
| `representation` | no | The input could not be represented faithfully. | "representation: \<reason>" |

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
| `witnesses` | A list. For fails, deviates and needs intent: every example that shows it. Empty otherwise. |
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

A separate list, `internal_premises`, holds method tags such as `model_constant` or `domain_restriction`. These are internal to the checker's method. They are neither observations nor baselines.

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

On the official PostgreSQL 18 image the checker reads: needs intent 17, vacuous 13, holds 4, not observed 4, deviates 2, missing baseline 0, fails 0.

## 7. "No verdicts" and input integrity

- **No verdicts.** `outcome` is `no_verdict` when no obligation on a machine that was read reads holds, fails or deviates. A vacuous reading alone does not count, and neither does a reading on a machine that could not be read. No verdict is a coverage fact, never an exit of its own: the summary says "No verdicts", and when no obligation on the machines read holds, the first line says "nothing could be established (0 of N obligations hold)". Such a run is green unless something is disproven (section 9). Look at the not-established lines to see what was missing and what would establish it.
- **Machines not read.** The first line counts the machines read and refused, for example "5 of 8 machines read, 3 refused". The count is out of every machine the profile checks (eight for both profiles) less any a scope limit names, which read "n out of scope" and leave both counts (section 9); a machine with no reading at all is refused with the reason "no readings for this machine". Each refused machine is listed with the checker's reason. The envelope counts them in `machines_refused` (`count`, `by_status`); the refused machine's own row in `rows` carries `kind: machine_refusal` and `needs`, what would admit it (section 1), and the summary adds one line under the status table, "Machines refused: n (\<status> k, ...). A refused machine is not an obligation reading and is not in the table above.", then under "Machines not read" each machine's status and what it needs. When that reason lists bound comparisons, for example `M2 domain bound exceeded (users 5 > 6 or databases 7 > 6)`, the summary keeps it as written and adds, in plain words, only the bounds that were exceeded: `in plain words: domain bound exceeded: databases 7 (cap 6)`. A refused machine bounds the result; a status you name in `fail-on` on its rows stops the job as on a read machine, and a reading the checker kept on it is read as not observed: a named `fails` or `deviates` does not stop the job on such a row, a named `not_observed` (or `not_collected`) does. When no machine could be read at all the run is yellow, "could not look", exit 3. When `machines.source` is `inferred`, the checker did not say which machines it refused, the machine count on the first line ends "(inferred)" and the summary says so, whether or not a machine was refused, and the list was worked out from the readings: a machine counts as refused when every reading of it is representation or not observed with one same reason.
- **The selected scope.** A profile can check a set you select that is not a set of machines, for example a list of endpoints. Its verdict then carries `scope_observed` beside `machines`: `unit` and `label` (for example `endpoint` and `endpoints`), `expected` (every unit you asked to be checked), `observed` (the units that were observed), `refused` (each unit that was not, with its `reason`) and `source` (`bound` when the set came with your request, `row` when the profile fixes it, `reported` when only the checker named it). The set you send is fixed before the checker runs, so the checker's output can add to it but never remove from it. The first line starts with this scope, for example "1 of 2 endpoints observed; 5 of 5 machines read", and adds "(accepted scope reduced)" when a unit was removed from the scope you accepted. Each unit that was not observed is listed with its reason. An unobserved unit bounds the result like a refused machine and does not change the exit, unless no unit was observed at all: then the run is yellow, "could not look". Both PostgreSQL profiles check machines: their verdicts carry `machines` alone.
- **No reading: input integrity.** When `a0` is set, the input failed its integrity gate. Every reading is representation, with the gate's reason. The run is yellow: `policy.exit` is 3 with `policy.reason` `could_not_look` under every policy except `never`, and the summary says "No reading: input integrity". Fix the collection and run again.

## 8. The declared profile

`postgresql-declared-model` reads per machine against a declaration you supply. Its statuses are holds, fails, vacuous, missing method, missing premise, representation and not evaluated. Holds, fails and vacuous are its verdicts. **Missing premise** means the declaration lacks a value the model needs. **Not evaluated** means the machine was not run; the reason says why. Both profiles are served. A holds on a tenant filter that reads a session setting (such as `current_setting(...)` or `auth.uid()`) means isolation holds given the application sets the setting from an authenticated identity before any query; a direct database login can set it. The observed profile prints this condition in the reason; the declared profile applies it without printing it. In the job summary, each fails line shows its witness from `readings`, such as `witness: path postgres:direct, command SELECT, outcome allowed, ...` (at most 5 witnesses per line); the verdict file holds them all.

## 9. The policy exit

`policy.exit` is the one number a CI job reads, and `colour` the one word. `policy.reason` names why, and the job summary says it in plain words. The product reads green unless something is disproven. A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. `policy.reason` names the cause of the exit and nothing else. One order:

| Order | `policy.reason` | `policy.exit` | Colour | When |
|---|---|---|---|---|
| 1 | `never` | 0 | as the readings give | `fail-on` is `never`. A prove-class obligation that is not proven still exits 1 (`not_proven`, row 5). |
| 2 | `bad_input`, `unauthenticated` | 2 | red | The request or input was refused (`bad_input`), or the API key is missing, unknown or revoked (`unauthenticated`): a failure envelope, never a verdict. |
| 3 | `could_not_look` | 3 | yellow | Nothing could be read at all: the input-integrity gate stopped the check (`a0` is set), no machine was read, or a profile with a selected scope observed none of its units. A prove-class obligation that is not proven keeps the colour red even then. |
| 4 | `disproven` | 1 | red | Something is disproven and your `fail-on` stops on it: a reading on a machine that was read has a status you fail on (`fails` by default; `deviates` when you name it). |
| 5 | `not_proven` | 1 | red | A prove-class obligation is not proven: no holds on a machine that was read. It exits 1 whatever its reading and under every `fail-on`, `never` included; when it reads fails and your `fail-on` names fails, the reason is `disproven`. |
| 6 | `unresolved_strict` | 1 | red | Under `fail-on: unresolved-security`, an obligation marked `security: true` is unresolved. Only the security obligations the pinned collector can observe count in n and m: an obligation the profile marks `observable_at_pin: false` is listed as not established, "not observable at collector pin \<pin>", and the first line says "strict: n of m security obligations observable at this pin". An intent-bound obligation (`class: intent_bound`) depends on what the system is for, which no collector observes. All security obligations without a verdict bind under strict, including one the pin cannot observe; the report names each and why. An intent-bound one is named "unresolved by your choice (strict)", reads "depends on what the system is for" and has the action "state it in requirements.md". n and m count observability only: an intent-bound obligation never counts in them and is never listed as not observable at the collector pin; m counts the intent-free security obligations. |
| 7 | `stopped_by_choice` | 1 | red | A reading has a status that is not a verdict and that your `fail-on` names (`not_observed`, or a status `not_collected` stands for). The job stopped on a status you named in fail-on; the colour above says whether anything is disproven. |
| 8 | `platform_owned` | 0 | red | Every disproof your `fail-on` names is platform-owned: a `fails` reading whose `findings` all carry `owner_class` `platform` or `extension` is excluded from the exit as someone else's to fix, the colour stays red, and the first line ends "(exit 0: platform-owned)". |
| 9 | `nothing_disproven` | 0 | green | Otherwise, refused machines, unobserved units and a run with no verdict included: within these bounds, nothing disproven. |

A `fails` reading sets exit 1 only when at least one of its `findings` has `owner_class` `app` or `unknown`, or it carries no `findings` at all; a `fails` reading whose findings are all `platform` or `extension` is platform-owned and excluded from the exit, `policy.reason` `platform_owned`, and the summary lists it under "Platform-owned, someone else's to fix". A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. A reading of any verdict status (fails, deviates, holds, vacuous) the checker kept on a machine it reports refused is a gap in coverage, never a disproof or a holds: every surface reads it as not observed. The refusal is on the first line; the row is listed as not established on that machine; a `not_observed` (or `not_collected`) you name in `fail-on` stops the job on it as on any not-observed reading; the summary shows it under its refused machine, "M6 refused — SD-4-OB kept by the checker, read as not observed", never under its status, and adds one line under the status table, "Readings the checker kept on refused machines and read as not observed: n.", while the table keeps the raw counts; the paid report reads it the same way. When your `fail-on` leaves a disproven status out (for example `fail-on: deviates`), the colour stays red, the exit is 0 with `policy.reason` `disproven`, and the first line ends "(exit 0 by your fail-on: deviates)". `fail-on: never` does the same, "(exit 0 by your fail-on: never)". `never` keeps exit 0, with one exception: a prove-class obligation that is not proven exits 1 with `policy.reason` `not_proven`, because a prove-class obligation is red unless proven and no run can set that aside. When the line leads with a refute-class disproof and the exit 1 comes from such an obligation, it ends "(exit 1: not proven — \<obligation>)". When the line leads with a disproof your `fail-on` leaves out and the exit 1 comes from a status you named, it ends "(exit 1 by your fail-on: \<status> — \<obligation>)". `allow_partial` is still accepted and changes nothing.

The first line of the job summary, the Action's first notice and its last log line carry the same words, in this order: the colour, the coverage, the bounds, then the finding.

- Coverage: "E of F \<units> observed; " for a selected scope, then "N of M machines read", with ", K refused" when a machine was refused.
- Bounds: "declared premises: n; version pins: \<pins or none>". An observed profile that declares nothing reads "declared premises: none (observed profile)". Pins are named: "major 18", and the baseline set when the readings name one. Then "prove-class obligations: p (unproven: u)" when the profile has any, and "strict: no obligations marked" when you chose strict and the profile marks none.
- Red: "deviations: d" when any reading deviates, then the finding. A disproof reads "disproven: \<obligation> — \<object>, \<access path>, \<locator>", from the reading's first witness. A status you chose to stop on reads "stopped by your choice: \<status> — \<obligation>", never "disproven". A prove-class obligation whose input could not be read reads "not proven: \<obligation> — input not observed"; one read without a holds reads "not proven: \<obligation> — \<reason>; \<action>". Strict reads "unresolved by your choice (strict): \<obligation> — \<reason>; \<action>". With more than one, it reads "unresolved by your choice (strict): k, first \<obligation> — \<reason>; \<action>", where k counts them and the first is in reading order.
- Green, when at least one obligation on the machines read holds: "nothing disproven; established: h of N; [deviations: d; ][\<status>: k; …]not established: n — top action: \<action>". When none holds: "nothing could be established (0 of N obligations hold); [deviations: d; ][\<status>: k; …]not established: n — top action: \<action>". Every other reading class on the machines read, such as `vacuous`, is named with its count, in alphabetical order, so the parts account for every reading. N counts every obligation reading; h the holds on machines that were read. The top action is the action of the most frequent reason class, leaving out `representation` when any other class is present; a free quote follows it when the action is a paid run. A deviation is counted on its own and is never a not-established obligation.
- Yellow: "yellow: could not look: \<reason>; \<action>", for example "yellow: could not look: the input could not be represented; re-collect with the pinned collector". Under it, the summary prints the input gate's reason and the file it names, when it names one.

For example: "green: 8 of 8 machines read; declared premises: none (observed profile); version pins: major 18; nothing disproven; established: 4 of 40; deviations: 2; vacuous: 13; not established: 21 — top action: state it in requirements.md". [FIRST-LINE-SAMPLES.md](FIRST-LINE-SAMPLES.md) gives one line for each case, word for word, with the meaning sentence for each colour.

Under the first line, one sentence says what it means in plain words, from a fixed template per colour:

- green: "Nothing in your \<subject> contradicts what is known about safe \<family> setups. \<n> of \<N> checks could not be completed, mostly because \<the top reason>. That is a gap in what we could see; your \<subject> is unchanged by it." ("are" for a plural subject.) The subject and family are "database configuration" and "PostgreSQL" for the PostgreSQL profiles, "HTTP responses" and "HTTP" for the HTTP profile.
- red: the consequence of what the first line names, then for a disproof "The finding is at \<locator> (\<object>, \<access path>)." when the reading's witness names a locator, or "The reading \<obligation> fails; the record carries no witness to point at." when it carries none. Until a profile states an obligation's consequence, it reads "Consequence not yet stated for \<obligation>."; nothing is invented.
- yellow: "We could not read the collected files, so nothing below is a finding about your \<subject>. \<Action>."

"Why it matters" lists each disproven or deviating obligation once: its plain statement and its consequence, both from the profile (the observed PostgreSQL profile states both for every obligation); a profile that states no plain statement falls back to the reading's own statement.

Under a green line the summary names each obligation that could not be established, "\<obligation>: \<reason> — \<owner>: \<what it needs>". The reasons, their owners and what they need:

| `reason_class` | Reason | `owner` | `needs` | `action` |
|---|---|---|---|---|
| `not_observed` | a fact was not collected: \<locator> | agent | collect \<locator> | collect \<locator> |
| `missing_method` | no method for this shape | symbolia | a method for this input shape | a method is a later profile version |
| `missing_baseline` | no pinned baseline for major \<n> | symbolia | a pinned baseline for major \<n> | pin the baseline (Symbolia) |
| `needs_intent` | depends on what the system is for | operator | a requirements.md sentence | state it in requirements.md |
| `representation` | the input could not be represented | agent | a faithful input: \<reason> | re-collect with the pinned collector |
| `not_observable_at_pin` | not observable at collector pin \<pin> | symbolia | a collector successor that observes it | collect with the collector successor (Symbolia) |

On `http-observed-baseline` a `needs_intent` entry has the action and the need "no HTTP requirement can be stated in this release; the reading informs and asks nothing of you", because no requirements.md sentence can hold on that profile yet; the coverage phrase the report keeps as `first_line` then ends "; no HTTP requirement can hold in this release".

A vacuous reading means there was nothing to check in its domain: it is counted, never listed. The declared profile's missing premise reads `not_observed` and its not evaluated `representation`. `quote` is null until a profile names a priced action. Obligations of class `representation` and `missing_method` are the profile version's own limits: the summary lists them under "Unsupported by this profile version: n", apart from the rest.

The verdict also carries `colour`, `bounds` (`declared_premises`, `observed`, `version_pins`, `coverage`), `not_established`, `bias` (`default`, `declared`, `prove_total`, `prove_unproven`, `prove`, `security`), `why` (each disproven or deviating obligation with its statement), `consequences` (the consequence sentences the profile states) and `completion`: `usable_readings` {`count`, `of`}, `coverage_complete`, `policy_passes`, `unsupported` {`count`, `ids`} and `snapshot` {`collected_at`, `freshness_s`, `loaded_state`}. The summary answers the three questions in three short sentences under the meaning sentence: "Usable readings: u of n. Coverage complete: yes. Job stops: no (exit 0 by your fail-on)." (or "Job stops: yes (exit 1)"; "Job stops: no (exit 0: platform-owned)" when every disproof your `fail-on` names is platform-owned). When the collector's sidecar names them, the collection time and its age, and the loaded state, follow on the same line: "Collected at \<time>, \<s> s before this summary. Loaded state: \<state>." The envelope keeps them in `completion.snapshot`.

## 10. Your requirements

When the check carried your `requirements.md`, the verdict also carries `requirements`: one row per requirement line, with its `id`, its `sentence` as you wrote it, and one of three states. **holds**: the methods it matches hold within the bounds the first line states. **not_established**: nothing establishes it yet; `reason_class` says why and `establishing_action` what would establish it. **disproven**: a reading with a witness contradicts it. A row that matches a prove-class obligation that is not proven keeps the state `not_established` with `display_state` `not_proven` and `blocking` true. A requirement holds only when the check ran to its end: a check the input gate stopped, or one whose effort is not accounted, never yields holds.

The first line adds "requirements: h hold, n not established", with ", d disproven" when any is, after the not-established count (before the finding on a red line). Under the not-established list, the summary lists every requirement with its sentence as you wrote it, "R3 — "\<sentence>" — not established — missing method — \<action>": the sentence is cut at 160 characters with …, the line names the locator after the reason class when the row's evidence carries one (for a disproof, where the counterexample is), and it ends with the quote's USD range when the row carries a free quote. The meaning sentence ends "\<u> of \<N> requirements in requirements.md could be read." A disproven requirement is red, as its disproof is; one that reads not proven exits 1 under every `fail-on`. Each requirement that does not hold is also one annotation in the same words. A check sent without requirements carries no `requirements` field, and every other field is as before. A requirement checked with `http-observed-baseline` cannot hold today: the HTTP check does not yet carry a verified method and path for each endpoint, so a matched HTTP requirement reads not established with the reason class `missing_identity_binding`. `mode: local` does not read `requirements.md`: requirements are checked in `mode: api` only, and a local run that finds one says so in one notice.

Exit 2 is bad input, and a failure envelope gives its outcome's own exit, 3 for every outcome that has none. A failure of the checker itself is the failure envelope `checker_error`, under every policy. A check is charged once the checker has started, whatever its result, `checker_error` and `checker_timeout` included. One failure is not charged: the checker's own internal error, a `checker_error` whose `detail.rule` is `internal_error`. A request refused before the checker starts is never charged, and neither is a check cut short by a server restart; it still counts against your rate limits.

A result is returned whenever one can be produced. When the checker's output for one machine is malformed, that machine is refused and named under "Machines not read" with its reason, `malformed_output: ...` (or `server_fault: ...` when the server could not write that machine's readings), and the other machines keep their readings; a refused machine never contributes a verdict, so the policy reads it as any refused machine. When no result can be produced, the typed failure says what was malformed in `detail.malformation`: a kind from a fixed list, the file, the line, the field and the expected form, never the text of your input. A rule or setting the collector withheld as a marker line is listed in `not_observed_lines` and in the summary as `not observed: <file> line N (<reason>)`; the check reads it as not observed.

`fail-on` takes, for each profile, the statuses it can emit except holds and vacuous, the group word `not_collected`, or `never` alone; the quickstarts list them.

## 11. The lint record

`POST /v1/lint` and the Action's `mode: lint` answer with a lint record, schema `assure.serve.lint/v1`. It is not a verdict: no check ran and nothing was charged.

```json
{"schema": "assure.serve.lint/v1", "ok": false, "profile": "postgresql-declared-model",
 "findings": [{"stage": "files", "outcome": "bad_input", "kind": "file_missing",
               "text": "Missing required file raw/declaration.json.", "file": "raw/declaration.json"}],
 "requirements": {"rows": 3, "problems": 1}}
```

The record also carries the seven flags. `ok` is true exactly when `findings` is empty. `profile` is the profile id, or null when none could be read. `requirements` counts the rows read and the rows with a problem, or is null when no requirements text could be read.

Each finding has `stage`, `outcome`, `kind` and `text` (one sentence saying what to change), and `file`, `line`, `field` and `endpoint_id` when they apply. The stages run in this order: `body`, `query`, `profile`, `fail_on`, `scope`, `files`, `collector`, `requirements`, `http`; an unknown profile is listed first, because no other fix can matter until the profile exists. A stage that cannot run because an earlier one failed is left out. Each stage up to `collector` reports its first problem. `requirements` gives one finding for each row that is not understood (`not_understood`), repeats an id (`duplicate_id`) or carries a tag for another profile family (`scope_mismatch`), with its `line`; a row that is understood and states no method is a normal answer and not a finding. `http` applies to `http-observed-baseline`: one finding for each endpoint whose response will not be observed, and one for each endpoint that answered 4xx or 5xx.
