# What a verdict claims

**Rules the collector keeps, and rules it withholds:** the collector the Action ships keeps a `pg_hba.conf` rule with a quoted name, an `@file` list or a regular-expression user (`/^...`) as written, and the check reads it. A kept rule the check cannot classify reads `representation` or `missing method` (the members of an `@file` list it does not resolve read `not observed`), not a failure, so under the default `fail-on: fails` such a run can still exit 0; choose `fails,not_collected` to make such readings stop the job. A rule or setting it still has to withhold becomes a marker line that names its own line number and reason; the check reads that rule or setting as not observed, and the summary lists it as `not observed: <file> line N (<reason>)`. Files collected earlier with the earlier collector still stop at such a rule (`collector_refused`, exit 3 in the Action, HTTP 422 from the API): that collector withheld it whole, and Assure cannot read it. The message names the file and the line. Collect again with the Action. If you cannot: remove quotes a name does not need; write an `@file` list's names inline; use a `+group` role in place of a list; list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted.

**Served today:** five profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory (`raw/declaration.json`) or a connection with `.assure/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe. `mysql-declared-model`: a MySQL server, from a mysql:// connection plus your declaration file (`declaration`), or an artefacts directory holding `raw/submission.json`; reports are withheld (`profile_unqualified`) until the writer is qualified for MySQL. `python-auth-declared-model`: a Python (Flask) repository, free, from the checkout in one step; the Action proposes a drafted declaration in a pull request the merge accepts.

**Progress:** no served profile reports progress while a check runs; a 202 to the poll is the only signal until the verdict is ready, and every `GET /v1/profiles` row says so as `progress_notes: false` (the row flips when a derive gains notes).

This page describes the claims of `postgresql-observed-baseline`; the declared profile is below, the HTTP profile's scope notes are in [the Action quick start](QUICKSTART-ACTION.md), and what each served profile never detects is listed per profile at the end of this page.

The check runs on Symbolia's server. The Action collects in your runner and sends the collected facts to the API; [DATA.md](DATA.md) says what is sent and how long it is kept. Before anything is sent, the Action replaces the text of every configuration comment with `# <withheld comment>` and every string literal in a policy expression with `'<withheld literal N>'` (except a setting name written as a standard-quoted `'name'` directly after `current_setting(`, which is sent as written); secret-bearing values are withheld whole by the collector. The check reads every file as it would have read it before the comments were withheld: a line PostgreSQL cannot parse is kept as the non-comment marker `<withheld: a line PostgreSQL cannot parse>`, which the check still counts as unparseable, or, when the check would read it as a working setting or rule, the Action stops before sending and names the file and the line. A rule or setting the collector had to withhold whole is a marker line that the check reads as not observed, never as absent or as broken; in files from the earlier collector it stops the upload (`collector_refused`) instead (see [DATA.md](DATA.md)). So does a file holding a line the earlier collector withheld whole when the collector's record, `COLLECTION-SIDECAR.json`, is not sent with it: a collector output without its sidecar cannot be checked. The Action also needs the collector's `REDACTION-MANIFEST.json` from the same run beside `raw/`, to check in your runner that the sidecar belongs to these files; the manifest is never sent. Records from another run are caught only when a file that holds a withheld line differs, byte for byte, from that run's file, so always use the sidecar and manifest written by the same collector run as `raw/` ([DATA.md](DATA.md) states the limit). A direct API caller is responsible for sending the collector's own output from one run. The file digests a verdict records are those of the files as sent. A reading that compares a policy expression with your declared predicate still compares them exactly: equal literals get the same marker within one check.

Assure reads a PostgreSQL deployment and gives a reading for each of 40 reliability and safety obligations. Every premise comes from your observed system or from a pinned public baseline row, and each one names its source. You declare nothing.

The design treats a wrong "holds" as the worst possible outcome. When a fact is missing, the reading says so.

## What a check that meets the policy claims

Under the default policy (`fail-on: fails`), a check is green and exits 0 when nothing is disproven. A green check claims only this: within the bounds its first line states, nothing the rules Symbolia holds could check was disproven; every obligation that could not be established is named with what would establish it. Its first line states those bounds: the machines read and refused, the declared premises and the version pins. Deviations from a recommendation are listed beside it. The claim covers these rules and these observations, and nothing beyond them. Uptime and behaviour under load are outside it, because no rule for them exists yet.

A run in which some machines could not be read is green unless something is disproven, and its first line says how many machines were read and how many were refused. When no obligation on the machines read holds, the first line says "nothing could be established". Only a run in which nothing could be read at all is yellow and exits 3.

## What a verdict claims

- **holds**: the obligation is met over the observed, non-empty domain, within the reading's qualifiers.
- **fails**: an unconditional vendor requirement, or an unconditional safety property computed from observation, is broken. The `witnesses` list shows where.
- **deviates**: a recommendation from the vendor or from the Assure baseline is not followed. The `authority` field says whose.
- **vacuous**: the observed domain is empty. The `domain_locator` shows where it was looked for.

Every verdict is tied to the exact engine (`engine.commit`) and the exact input files (`input.files`, by sha256). The same input and engine give the same readings.

## What a verdict leaves open

- Anything beyond the rules Symbolia holds today, including whether the database is fit for its purpose. Readings cover the 40 obligations and the CVE exposure rows (VERDICTS.md section 5) only.
- Anything about obligations that read needs intent, not observed, missing baseline, missing method or representation.
- Other databases in the cluster. Database-scoped obligations read only the database you connected to. Their text names it ("in database \<db>"). Other connectable databases appear as the qualifier "other connectable databases not collected: \<names>". On a default server this includes `template1`. While another connectable database exists, PRIV-2-OB reads not observed.
- The rules the server has loaded. Client-authentication readings use the configured `pg_hba.conf` file. They carry the qualifier "configured rules; loaded identity not observed". HBA-6 reads not observed.
- Password presence and stored-hash type. Readings on scram or md5 rules carry "password presence not observed".
- The collection role. It is left out of every domain. Facts about it appear as observations and are never counted. Use a new role for collection, so it hides none of your site's results.
- Remote access on a server with only local listeners. Host-local means Unix socket, `127.0.0.0/8`, `::1/128` and the IPv4-mapped loopback `::ffff:127.0.0.0/104`. With no other listener, the remote obligations read vacuous.
- A populated production deployment. Qualification evidence today comes from the official PostgreSQL 18 image. A populated deployment has not yet been run.

## PostgreSQL versions

The collector and checker accept majors 14 to 18. The major comes from the observed `server_version_num`. Most baseline rows are documented for PostgreSQL 18. At another major, a reading that needs such a row reads missing baseline. Real-run evidence exists for PostgreSQL 17 and 18.

## Managed PostgreSQL

Some facts live in configuration files: `postgresql.conf` and its includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. With a connection and no data directory, those files cannot be read. This is the usual case for managed PostgreSQL services. Then every reading that could not be made is named with its status and its reason, such as not observed or representation; the reason says which fact or file was missing. A machine the checker could not read at all is listed with its reason under "Machines not read" in the job summary, and in the verdict's `machines` field. A run in which machines were refused is green unless something is disproven, and its first line names what was not read.

To fail a job when a needed fact was not collected, set `fail-on` to `fails,not_collected`.

The collector asks for a read-only session. A pooler may not pass the request on. The collector runs only fixed SELECT statements either way. The collector records whether the session was read-only, and the job summary says so: `The collection session was read-only: yes`, `no` or `not recorded`. It also states `TLS to the server:` as the server reported it for that session. Behind a connection pooler both describe the pooler's session to the server. Neither changes a reading.

A self-hosted runner, or a collection machine, that can read the files lifts this limit. Set `data-dir` to the data directory. Set `config-dirs` to any directory outside it that holds configuration files, such as `/etc/postgresql/<major>/<cluster>` on Debian and Ubuntu. The collector reads files only inside those directories.

## The declared profile

`postgresql-declared-model` reads against a declaration you write, `raw/declaration.json`. The collector does not write one: with an artefacts directory, add your declaration under `raw/`; with a connection in `mode: api`, commit it at `.assure/declaration.json` in the checkout (a link, or a file that is not a regular readable file, is refused `bad_input`; its `declared_predicate` literals are withheld like an artefacts directory's), and with none there (and a server major from 14 to 18) the Action checks on a declaration drafted from your database before withholding, bounded by that unaccepted draft (`declaration=unaccepted-draft`), and proposes it only in a pull request of its own on `assure/declaration-proposal`; merging it is the acceptance. In `mode: local` a connection alone reads `bad_input` for the missing declaration.

## An empty database

A new, default database reads mostly needs intent and vacuous. That means there is little to check. The 16 intent-bound obligations always need intent, and an empty database has few roles, tables or functions to look at.

## Checker status

The `postgresql-observed-baseline` checker is served. It was qualified before it was served. Qualification means: on the official PostgreSQL 18 image the readings equal the expected readings, every planted defect is caught, there are zero wrong holds, one independent review found no blocking defect, and two hosted runs give identical bytes.

## What each profile never detects

A check reads only what its checker opens, and the checker opens only files the row's `inputs` admits: `GET /v1/profiles` lists every served profile's input allow-list. A file the allow-list admits is not therefore read: the two PostgreSQL rows admit any non-JSON file under `raw/` for configuration includes, and a file the checker never opens is not a reading. So each profile has fault classes no reading of it can detect, whatever the verdict says. They are listed here per profile, from what the checker reads, so that a fault you found can be matched to a documented exclusion rather than to a gap. Each bullet names the artefact that would have to be collected for the class to be checkable, then the next step: a requirement sentence in your declaration, a different served profile, or "not a check Assure sells".

### What `postgresql-observed-baseline` never detects

The checker reads the collected catalog snapshot (`raw/catalog_snapshot.json`) and, when collected, the settings and configuration files the allow-list names. A present `raw/declaration.json` it takes only to tighten a baseline (`tls_floor`, `sensitive_roles`, `forbidden_methods`; any other key is dropped with a `declared_ignored` warning, [VERDICTS.md](VERDICTS.md)). It runs no SQL of its own and watches no server.

- Anything not in the collected snapshot or configuration files: the state of the server after collection, the rules the server has loaded (as opposed to the configured `pg_hba.conf`), password presence and stored-hash type, other databases in the cluster. Artefact: a fact the collector does not write into the snapshot or the configuration files; until the collector writes it, a reading that needs it reads not observed and names it. Next: not a check Assure sells today.
- Runtime behaviour: queries, uptime, behaviour under load, crashes, client or application errors and process exit codes. Artefact: a server log, a query trace or a load run; the input allow-list (`GET /v1/profiles`) admits non-JSON files under `raw/`, but the checker does not read them as runtime evidence. Next: not a check Assure sells.
- Anything outside the files the allow-list names: application code, deployment manifests, operating-system configuration, backups. Artefact: those files, which the checker never opens; the row's catch-all pattern admits any non-JSON file under `raw/` for configuration includes, and a file it does not read is not a reading. Next: `python-auth-declared-model` reads a Flask repository's registered routes and guards; for the rest, not a check Assure sells.
- Whether the configuration is the one you intended: the 16 intent-bound obligations read needs intent. Artefact: your declaration, `raw/declaration.json`, which this profile takes only to tighten a baseline; it does not read your intent from it. Next: `postgresql-declared-model`.

### What `postgresql-declared-model` never detects

The checker reads the collected snapshot (`raw/catalog_snapshot.json`) against your declaration (`raw/declaration.json`), both from the artefacts directory. It runs no SQL of its own, proves nothing about the database software and certifies no deployment.

- Anything your declaration does not state and the snapshot does not hold: an obligation no method states reads missing method, and a shape the declaration does not admit reads representation. Artefact: a sentence in `raw/declaration.json` stating the obligation ([DECLARATIONS.md](DECLARATIONS.md)). Next: a requirement sentence in your declaration.
- Runtime behaviour: queries, uptime, behaviour under load, crashes, client or application errors and process exit codes. Artefact: a server log, a query trace or a load run; the input allow-list (`GET /v1/profiles`) admits non-JSON files under `raw/`, but the checker does not read them as runtime evidence. Next: not a check Assure sells.
- Anything outside the files the allow-list names: application code, deployment manifests, operating-system configuration, backups. Artefact: those files, which the checker never opens; the row's catch-all pattern admits any non-JSON file under `raw/` for configuration includes, and a file it does not read is not a reading. Next: `python-auth-declared-model` reads a Flask repository's registered routes and guards; for the rest, not a check Assure sells.

### What `http-observed-baseline` never detects

The checker reads the endpoint manifest (`raw/HTTP-FACTS.json`), the collector's sidecar (`raw/COLLECTION-SIDECAR.json`) and one captured HEAD response per selected endpoint (`raw/response-heads/endpoint-NNN.txt`). It sends no request of its own.

- Anything not in the collected heads: response bodies, the answer to GET, POST or any method but HEAD, an endpoint you did not select, a state change the request causes, and the server's behaviour after the capture. Artefact: a captured response for that endpoint and method under `raw/response-heads/`; the collector captures one HEAD per selected endpoint, and the allow-list (`GET /v1/profiles`) admits no body. Next: select the endpoint and collect again; for a body, another method or a state change, not a check Assure sells.
- Evidence freshness, response authenticity and same-selection replay: the heads are read as collected. Artefact: a server-side signature or timestamp over the response; the identity binding signs the runner's digests, not the server's answer. Next: not a check Assure sells.
- Runtime behaviour of the server behind the endpoint: application exceptions, handler exit codes, logs, the processes that answer. Artefact: the server's logs or its source, which this profile's `inputs` does not admit (its only pattern is `raw/response-heads/`). Next: `python-auth-declared-model` reads a Flask repository's registered routes and guards from source; for the rest, not a check Assure sells.

### What `mysql-declared-model` never detects

The checker reads your submission (`raw/submission.json`), the collector's statement of the server state, under your declaration. It performs no SQL of its own and reads no server.

- Anything not in the submission: a machine whose section the submission lacks refuses typed, and the refusal is noted with the section's name; a fact no section carries is not observed. Artefact: the missing section of `raw/submission.json`, written by the Action's MySQL collector ([DECLARATIONS.md](DECLARATIONS.md), MySQL submissions). Next: collect again with that section; for a fact no section carries, not a check Assure sells.
- Anything your declaration does not state: an obligation no method states reads missing method. Artefact: a sentence in your declaration file stating the obligation. Next: a requirement sentence in your declaration.
- Runtime behaviour: queries, uptime, behaviour under load, crashes, client or application errors and process exit codes. Artefact: a server log, a query trace or a load run; none is in the input allow-list (`GET /v1/profiles`). Next: not a check Assure sells.
- Anything outside the files the allow-list names: application code, deployment manifests, operating-system configuration, backups. Artefact: those files, which this profile's `inputs` does not admit. Next: `python-auth-declared-model` reads a Flask repository's registered routes and guards; for the rest, not a check Assure sells.

### What `python-auth-declared-model` never detects

The checker reads the repository listing (`raw/REPOSITORY.json`), your declaration (`raw/declaration.json`) and the source files under `raw/repository/`. It reads registration and imports statically (`extract_registration.py` reads `route`, `add_url_rule` and `register_blueprint` calls; `extract_imports.py` reads imports) and runs no code of yours.

- Runtime behaviour of a handler: an exception a view raises, a `SystemExit` raised inside a handler, the process's exit code, what a request returns, and what the application does when started. Artefact: a request trace or a run of your application; neither is an input of this profile, and no served profile reads one. Next: not a check Assure sells.
- A route the source does not register literally: a path built from a string the checker cannot resolve, a route the framework registers for you (static files, framework error responses), an error-handler body. A use the checker cannot resolve refuses, on the sound side. Artefact: the registration written as a literal `route` decorator or `add_url_rule` call in the repository. Next: a requirement sentence stating the route, or not a check Assure sells for framework responses and error-handler bodies.
- Deployment and runtime configuration: the WSGI server, the database, the browser and deployment manifests. Artefact: deployment settings or a run of those systems; the input allow-list (`GET /v1/profiles`) admits a submitted manifest such as `raw/repository/deploy.yaml`, but the checker does not evaluate it as deployment evidence. A repository path sent directly as `raw/deploy.yaml` is one this profile's `inputs` does not admit. Next: `postgresql-observed-baseline` or `mysql-declared-model` for the database, `http-observed-baseline` for the endpoints as served; for the rest, not a check Assure sells.
- Whether the guards and session keys you declared are the right ones: the model is your declaration. Artefact: a sentence in `raw/declaration.json` stating the guard or key. Next: a requirement sentence in your declaration.
