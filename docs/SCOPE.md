# What a verdict claims

**Served today:** `postgresql-declared-model`, which needs a declaration file in an artefacts directory (see "The declared profile" below). The intent-free profile, `postgresql-observed-baseline`, is not yet served; a check with it returns `profile_not_servable`. This page describes the intent-free profile's claims, which apply once it is served.

The check runs on Symbolia's server. The Action collects in your runner and sends the collected facts to the API; [DATA.md](DATA.md) says what is sent and how long it is kept. Before anything is sent, the Action replaces the text of every configuration comment with `# <withheld comment>` and every string literal in a policy expression with `'<withheld literal N>'`; secret-bearing values are withheld whole by the collector. No reading's status depends on comment text; the file digests a verdict records are those of the files as sent. A reading that compares a policy expression with your declared predicate still compares them exactly: equal literals get the same marker within one check.

Assure reads a PostgreSQL deployment and gives a reading for each of 40 reliability and safety obligations. Every premise comes from your observed system or from a pinned public baseline row, and each one names its source. You declare nothing.

The design treats a wrong "holds" as the worst possible outcome. When a fact is missing, the reading says so.

## What a verdict claims

- **holds**: the obligation is met over the observed, non-empty domain, within the reading's qualifiers.
- **fails**: an unconditional vendor requirement, or an unconditional safety property computed from observation, is broken. The witness shows where.
- **deviates**: a recommendation from the vendor or from the Assure baseline is not followed. The `authority` field says whose.
- **vacuous**: the observed domain is empty. The `domain_locator` shows where it was looked for.

Every verdict is tied to the exact engine (`engine.commit`) and the exact input files (`input.files`, by sha256). The same input and engine give the same readings.

## What a verdict leaves open

- Whether the database is secure or fit for its purpose. Readings cover the 40 obligations only.
- Anything about obligations that read needs intent, not observed, missing baseline, missing method or representation.
- Other databases in the cluster. Database-scoped obligations read only the database you connected to. Their text names it ("in database <db>"). Other connectable databases appear as the qualifier "other connectable databases not collected: <names>". On a default server this includes `template1`. While another connectable database exists, PRIV-2-OB reads not observed.
- The rules the server has loaded. Client-authentication readings use the configured `pg_hba.conf` file. They carry the qualifier "configured rules; loaded identity not observed". HBA-6 reads not observed.
- Password presence and stored-hash type. Readings on scram or md5 rules carry "password presence not observed".
- The collection role. It is left out of every domain. Facts about it appear as observations and are never counted. Use a new role for collection, so it hides none of your site's results.
- Remote access on a server with only local listeners. Host-local means Unix socket, `127.0.0.0/8` and `::1/128`. With no other listener, the remote obligations read vacuous.
- A populated production deployment. Qualification evidence today comes from the official PostgreSQL 18 image. A populated deployment has not yet been run.

## PostgreSQL versions

The collector and checker accept majors 14 to 18. The major comes from the observed `server_version_num`. Most baseline rows are documented for PostgreSQL 18. At another major, a reading that needs such a row reads missing baseline. Real-run evidence exists for PostgreSQL 18 only.

## Managed PostgreSQL

Some facts live in configuration files: `postgresql.conf` and its includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. With a connection and no data directory, those files cannot be read. This is the usual case for managed PostgreSQL services. Then:

- a reading that needs a fact from a file reads **not observed**;
- where the checker cannot represent the input without the file, as with a missing `pg_hba.conf` or `postgresql.conf`, the readings that use it read **representation**.

To fail a job when a needed fact was not collected, set `fail-on` to `fails,not_collected`.

A self-hosted runner, or a collection machine, that can read the files lifts this limit. Set `data-dir` to the data directory. Set `config-dirs` to any directory outside it that holds configuration files, such as `/etc/postgresql/<major>/<cluster>` on Debian and Ubuntu. The collector reads files only inside those directories.

## The declared profile

`postgresql-declared-model` reads against a declaration you write, `raw/declaration.json`. The collector does not write one, so this profile needs an artefacts directory: collect, add your declaration under `raw/`, then check with `artefacts`. With a connection alone it reads `bad_input` for the missing declaration.

## An empty database

A new, default database reads mostly needs intent and vacuous. That means there is little to check. The 16 intent-bound obligations always need intent, and an empty database has few roles, tables or functions to look at.

## Checker status

The `postgresql-observed-baseline` checker is not yet qualified. Until it is, a check with that profile returns the typed outcome `profile_not_servable`. Qualification means: on the official PostgreSQL 18 image the readings equal the expected readings, every planted defect is caught, there are zero wrong holds, one independent review found no blocking defect, and two hosted runs give identical bytes.
