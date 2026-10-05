# Beta tester brief

## Who this is for

You administer one self-hosted PostgreSQL server, major 14 to 18, and you can run a GitHub Actions workflow that reaches it.

**Served today:** three profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory with your declaration in `raw/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe.

**Checking HTTP endpoints.** `http-observed-baseline` reads the response heads you captured for the endpoints you select, offline: give the Action an artefacts folder holding an endpoint manifest and the heads, and it produces the scope binding itself. The steps below are for PostgreSQL.

## What you get

A reading for each obligation Assure checks: holds, fails, deviates, vacuous, or why it could not be read. A run that meets your policy claims this: every rule Symbolia holds for the system was checked against what was observed and none is violated; what could not be observed or judged is named. It is a record of what was checked, never a seal of approval. [SCOPE.md](SCOPE.md) states the limits.

## Your first run

1. Create the collection role, grant it `CONNECT` on your database, and allow it in `pg_hba.conf` ([quick start](QUICKSTART-ACTION.md), section 2).
2. Let the runner read the server's configuration files, preferably copies (section 6, option b).
3. From the runner, test the connection string with `psql` and `sslmode=require` (section 3). Store it as the secret `ASSURE_PG_CONNECTION`, and your key as `ASSURE_API_KEY`.
4. Add the workflow from section 4. Leave `profile` at its default.
5. Run it, and read the first line of the job summary.

If the key is wrong or revoked, or you hit a rate limit, the API refuses the first request, for the profile list, before anything is collected or sent; the summary's last line says so.

## What the first line means

"7 of 8 machines read, 1 refused" means seven parts of the check were read and one was not. Exit 3 means nothing was checked, or a machine was refused: the claim is about the whole system. Set `allow-partial: true` to accept a partial read.

## Three things that will look odd today

- **A refused machine (M2, client authentication) when the server has more than six databases or more than six users, as the checker counts them.** It counts the databases that allow connections, plus each one a `pg_hba.conf` rule names, and the login roles, plus each `+group`. The summary names the bound exceeded, for example "databases 7 (cap 6)" or "users 7 (cap 6)". The other machines still read; set `allow-partial: true` to accept them. M2 also reads "missing method" today when any `pg_hba.conf` line uses `peer`, `ident` or another external authentication method (the Debian and Ubuntu default `local all postgres peer` included), until the checker bounds those methods.
- **A `pg_hba.conf` rule with a quoted role name, an `@file` list or a regular-expression user reads `representation` or `missing method`, not a verdict.** Under the default `fail-on: fails` such a run can still pass; choose `fail-on: fails,not_collected` to make those readings stop the job. A rule the collector has to withhold (an unclosed quote, for example) appears as `not observed: pg_hba.conf line N (<reason>)`.
- **Readings that read not observed or representation where you might expect a verdict.** On PostgreSQL 18 the collection role cannot read `pg_hba_file_rules`, `pg_file_settings` or `pg_subscription`, so the readings that need them read not observed. With more than one `SECURITY DEFINER` function, the search-path readings (SD-1, SD-2) read representation.

## What to send back

Through your Symbolia contact:

- the check id (the line under the summary heading: "Profile ..., check <id>.");
- the first line;
- the summary text of any reading that looks wrong, or the failure reason;
- your PostgreSQL major, and where setup took longest.

Never send your configuration files, your connection string or your API key.

## What is kept

Per [DATA.md](DATA.md): the collected facts are deleted when the check ends. The verdict is kept 30 days. Checker telemetry, with counts and statuses and no names or values from your system, is kept 12 months. On the free tier, using your facts to improve the checks is opt-in: nothing of yours is kept for it unless you opt in.

## Contact

Your Symbolia contact.
