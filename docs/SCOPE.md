# What a verdict claims

**Rules the collector keeps, and rules it withholds:** the collector the Action ships keeps a `pg_hba.conf` rule with a quoted name, an `@file` list or a regular-expression user (`/^...`) as written, and the check reads it. A kept rule the check cannot classify reads `representation` or `missing method` (the members of an `@file` list it does not resolve read `not observed`), not a failure, so under the default `fail-on: fails` such a run can still exit 0; choose `fails,not_collected` to make such readings stop the job. A rule or setting it still has to withhold becomes a marker line that names its own line number and reason; the check reads that rule or setting as not observed, and the summary lists it as `not observed: <file> line N (<reason>)`. Files collected earlier with the earlier collector still stop at such a rule (`collector_refused`, exit 3 in the Action, HTTP 422 from the API): that collector withheld it whole, and Assure cannot read it. The message names the file and the line. Collect again with the Action. If you cannot: remove quotes a name does not need; write an `@file` list's names inline; use a `+group` role in place of a list; list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted.

**Served today:** three profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory with your declaration in `raw/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe.

This page describes the claims of `postgresql-observed-baseline`; the declared profile is below, and the HTTP profile's scope notes are in [the Action quick start](QUICKSTART-ACTION.md).

The check runs on Symbolia's server. The Action collects in your runner and sends the collected facts to the API; [DATA.md](DATA.md) says what is sent and how long it is kept. Before anything is sent, the Action replaces the text of every configuration comment with `# <withheld comment>` and every string literal in a policy expression with `'<withheld literal N>'`; secret-bearing values are withheld whole by the collector. The check reads every file as it would have read it before the comments were withheld: a line PostgreSQL cannot parse is kept as the non-comment marker `<withheld: a line PostgreSQL cannot parse>`, which the check still counts as unparseable, or, when the check would read it as a working setting or rule, the Action stops before sending and names the file and the line. A rule or setting the collector had to withhold whole is a marker line that the check reads as not observed, never as absent or as broken; in files from the earlier collector it stops the upload (`collector_refused`) instead (see [DATA.md](DATA.md)). So does a file holding a line the earlier collector withheld whole when the collector's record, `COLLECTION-SIDECAR.json`, is not sent with it: a collector output without its sidecar cannot be checked. The Action also needs the collector's `REDACTION-MANIFEST.json` from the same run beside `raw/`, to check in your runner that the sidecar belongs to these files; the manifest is never sent. Records from another run are caught only when a file that holds a withheld line differs, byte for byte, from that run's file, so always use the sidecar and manifest written by the same collector run as `raw/` ([DATA.md](DATA.md) states the limit). A direct API caller is responsible for sending the collector's own output from one run. The file digests a verdict records are those of the files as sent. A reading that compares a policy expression with your declared predicate still compares them exactly: equal literals get the same marker within one check.

Assure reads a PostgreSQL deployment and gives a reading for each of 40 reliability and safety obligations. Every premise comes from your observed system or from a pinned public baseline row, and each one names its source. You declare nothing.

The design treats a wrong "holds" as the worst possible outcome. When a fact is missing, the reading says so.

## What a check that meets the policy claims

Under the default policy (`fail-on: fails`), a check exits 0 only when every machine was read, at least one obligation reads holds or deviates, and none reads fails. Such a check claims this: every rule Symbolia holds for the system was checked against what was observed and none is violated; what could not be observed or judged is named. Deviations from a recommendation are listed beside it. The claim covers these rules and these observations, and nothing beyond them. Uptime and behaviour under load are outside it, because no rule for them exists yet.

A run in which some machines could not be read exits 3 by default, because the claim is about the whole system; the first line of the summary says how many machines were read and how many were refused. A run that checked nothing, or whose only verdicts are vacuous, also exits 3, and so does a run in which no machine could be read, even with allow-partial set.

## What a verdict claims

- **holds**: the obligation is met over the observed, non-empty domain, within the reading's qualifiers.
- **fails**: an unconditional vendor requirement, or an unconditional safety property computed from observation, is broken. The `witnesses` list shows where.
- **deviates**: a recommendation from the vendor or from the Assure baseline is not followed. The `authority` field says whose.
- **vacuous**: the observed domain is empty. The `domain_locator` shows where it was looked for.

Every verdict is tied to the exact engine (`engine.commit`) and the exact input files (`input.files`, by sha256). The same input and engine give the same readings.

## What a verdict leaves open

- Anything beyond the rules Symbolia holds today, including whether the database is fit for its purpose. Readings cover the 40 obligations only.
- Anything about obligations that read needs intent, not observed, missing baseline, missing method or representation.
- Other databases in the cluster. Database-scoped obligations read only the database you connected to. Their text names it ("in database <db>"). Other connectable databases appear as the qualifier "other connectable databases not collected: <names>". On a default server this includes `template1`. While another connectable database exists, PRIV-2-OB reads not observed.
- The rules the server has loaded. Client-authentication readings use the configured `pg_hba.conf` file. They carry the qualifier "configured rules; loaded identity not observed". HBA-6 reads not observed.
- Password presence and stored-hash type. Readings on scram or md5 rules carry "password presence not observed".
- The collection role. It is left out of every domain. Facts about it appear as observations and are never counted. Use a new role for collection, so it hides none of your site's results.
- Remote access on a server with only local listeners. Host-local means Unix socket, `127.0.0.0/8`, `::1/128` and the IPv4-mapped loopback `::ffff:127.0.0.0/104`. With no other listener, the remote obligations read vacuous.
- A populated production deployment. Qualification evidence today comes from the official PostgreSQL 18 image. A populated deployment has not yet been run.

## PostgreSQL versions

The collector and checker accept majors 14 to 18. The major comes from the observed `server_version_num`. Most baseline rows are documented for PostgreSQL 18. At another major, a reading that needs such a row reads missing baseline. Real-run evidence exists for PostgreSQL 18 only.

## Managed PostgreSQL

Some facts live in configuration files: `postgresql.conf` and its includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. With a connection and no data directory, those files cannot be read. This is the usual case for managed PostgreSQL services. Then every reading that could not be made is named with its status and its reason, such as not observed or representation; the reason says which fact or file was missing. A machine the checker could not read at all is listed with its reason under "Machines not read" in the job summary, and in the verdict's `machines` field. A run in which machines were refused does not meet the policy by default: it exits 3. Set `allow-partial: true` to accept a partial read.

To fail a job when a needed fact was not collected, set `fail-on` to `fails,not_collected`.

The collector asks for a read-only session. A pooler may not pass the request on. The collector runs only fixed SELECT statements either way. The collector records whether the session was read-only, and the job summary says so: `The collection session was read-only: yes`, `no` or `not recorded`. It also states `TLS to the server:` as the server reported it for that session. Behind a connection pooler both describe the pooler's session to the server. Neither changes a reading.

A self-hosted runner, or a collection machine, that can read the files lifts this limit. Set `data-dir` to the data directory. Set `config-dirs` to any directory outside it that holds configuration files, such as `/etc/postgresql/<major>/<cluster>` on Debian and Ubuntu. The collector reads files only inside those directories.

## The declared profile

`postgresql-declared-model` reads against a declaration you write, `raw/declaration.json`. The collector does not write one, so this profile needs an artefacts directory: collect, add your declaration under `raw/`, then check with `artefacts`. With a connection alone it reads `bad_input` for the missing declaration.

## An empty database

A new, default database reads mostly needs intent and vacuous. That means there is little to check. The 16 intent-bound obligations always need intent, and an empty database has few roles, tables or functions to look at.

## Checker status

The `postgresql-observed-baseline` checker is served. It was qualified before it was served. Qualification means: on the official PostgreSQL 18 image the readings equal the expected readings, every planted defect is caught, there are zero wrong holds, one independent review found no blocking defect, and two hosted runs give identical bytes.
