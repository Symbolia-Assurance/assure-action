# Route 1: a connection to the server

## Managed PostgreSQL and connection poolers (section 6)

On Supabase, the `postgres` role cannot grant `pg_read_all_settings` or `pg_read_all_stats`. It can grant `pg_monitor`, and the collector this Action ships refuses `pg_monitor` as broader than it needs (section 2). So this Action version cannot collect from a Supabase database.

If the database is on Supabase, tell the operator so before any grant; do not grant `pg_monitor` and do not set it in `collection-privileges`.

## What the runner needs

- Outbound HTTPS to `api.symbolia.ai` (port 443).
- A network path to your database, for a check with `connection`.
- Python 3.14 and, for `connection`, the PostgreSQL client (`psql`).

## 1. Get an API key

Ask Symbolia for a key. It starts with `asr_`, and you receive it once.

In your repository, open **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `ASSURE_API_KEY`
- Value: the key.

The Action masks the key in the job log before it prints anything. It sends the key only in the `Authorization` header to the API, over TLS, and never follows a redirect.

## 2. Create a collection role

The Action connects as a role you create for it. Give that role read access to settings and statistics, and nothing more.

Run this as a superuser or a role that can create roles:

```sql
CREATE ROLE assure_collector LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD '<choose a long random password>';
GRANT pg_read_all_settings, pg_read_all_stats TO assure_collector;
GRANT CONNECT ON DATABASE <your database> TO assure_collector;
```

In these statements `<your database>` is the name of the database to check, or `postgres` for a local server that holds no other database.

The `CONNECT` grant matters when your database revokes `CONNECT` from `PUBLIC` (for example `REVOKE ALL ON DATABASE <your database> FROM PUBLIC`). Without it, the first run stops with `collector_cannot_connect` and the reason `permission denied for database`. Where `PUBLIC` still has `CONNECT`, the grant changes nothing.

Then allow the role to log in from the runner. Add a line to `pg_hba.conf` and reload the server:

```
host  <your database>  assure_collector  <the runner's address>/32  scram-sha-256
```

Rules for this role:

- Create a new role. Use it for nothing else. The checker leaves the collection role out of every reading, so a role your site also uses would hide its own results.
- Grant it only these two roles. The collector refuses a broader role: `pg_monitor` or `pg_stat_scan_tables` in `collection-privileges` stops the Action with exit 2 (`bad_input`) before anything runs, and a role that belongs to either stops it with exit 3 (`collector_refused`). The collector also refuses to run if the role is a superuser, has `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`, or belongs to any other role.
- Allow it to log in through `pg_hba.conf` from the runner's address.

The collector runs a fixed, published set of `SELECT` queries. It writes nothing to your database. The collector asks for a read-only session. A pooler may not pass the request on. The collector runs only fixed SELECT statements either way. The collector records whether the session was read-only, and the job summary says so (section 8).

## 3. Store the connection as a secret

Add a second repository secret:

- Name: `ASSURE_PG_CONNECTION`
- Value: a libpq connection string or URI, for example:

```
host=db.example.internal port=5432 dbname=app user=assure_collector password=<the password> sslmode=require
```

`sslmode=require` encrypts the connection but does not check the server's certificate. It works with the self-signed certificate that the Debian and Ubuntu packages set up. `sslmode=verify-full` also checks that the certificate is signed by an authority the runner trusts and names the host you connect to. It is the stronger choice. It needs a certificate the runner trusts: a self-signed server certificate fails it. Give the authority's certificate with `sslrootcert`:

```
host=db.example.internal port=5432 dbname=app user=assure_collector password=<the password> sslmode=verify-full sslrootcert=/path/to/root.crt
```

Test the string from the runner before the first run. Leave the password out and type it at the prompt, so it stays out of your shell history:

```
psql 'host=db.example.internal port=5432 dbname=app user=assure_collector sslmode=require' -c 'SELECT current_user'
```

It prints `assure_collector`. If it does not, the Action cannot connect either.

The Action passes the connection to `psql` through environment variables. The connection stays in your runner: it is never sent to the API, put on a command line or logged.

## 4. Add the workflow

Create `.github/workflows/assure.yml`:

```yaml
name: Assure

on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * 1"

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Install the PostgreSQL client
        run: command -v psql || (sudo apt-get update && sudo apt-get install -y postgresql-client)

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-observed-baseline
          connection: ${{ secrets.ASSURE_PG_CONNECTION }}
          collection-role: assure_collector
          collection-privileges: pg_read_all_settings,pg_read_all_stats
          fail-on: fails
          output: assure-verdict.json

      - name: Keep the verdict
        if: always()
        uses: actions/upload-artifact@<full commit sha of the release you trust>
        with:
          name: assure-verdict
          path: ${{ steps.assure.outputs.verdict-path }}
```

Pin every `uses:` line to a full 40-character commit SHA. A tag can move; a commit cannot.

Pin the Action at the commit you fetched this file from. Put that commit of `Symbolia-Assurance/assure-action`, in full, in place of `<full commit sha>`. In a clone, `git -C assure-action rev-parse HEAD` prints it. The `source:` line of `skills/assure/VERSION` names another commit: the Assure source commit the Action was built from. It is not a commit of the Action repository, so it never goes in a `uses:` line. The `pin:` line of `skills/assure/VERSION` says the same: the build cannot know the commit you fetched, so it names none.

This workflow runs on every pull request, on every push to `main`, when you start it by hand, and once a week. Change `main` if your default branch has another name. A pull request from a fork gets no repository secrets from GitHub, so `api-key` is empty there and the Action stops with `bad_input` (exit 2).

This workflow uses the intent-free profile, which needs no declaration. To check against a declaration you write, use `postgresql-declared-model` with collected files (section 9).

The runner must reach your database and `api.symbolia.ai`. For a database on a private network, use a self-hosted runner inside that network with outbound HTTPS.

## 6. Managed PostgreSQL and configuration files

> - [ ] The runner can read the server's configuration files, or has copies it can read (section 6). Managed PostgreSQL: skip this line.

Some facts live in configuration files: `postgresql.conf` and the files it includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. The collector finds them through the server's own settings and reads them from the runner's filesystem.

With a connection and no data directory, the runner cannot read those files. This is the usual case for managed PostgreSQL. A reading that needs a fact from a file then reads **not observed**. Where the checker cannot represent the input without the file, as with a missing `pg_hba.conf` or `postgresql.conf`, the readings that use it read **representation**. The client-authentication and TLS obligations are the ones most affected.

To read the files, run the Action on a self-hosted runner that can read them:

- `data-dir`: the server's data directory, as the runner sees it.
- `config-dirs`: directories that hold configuration files outside the data directory.
  Give one directory per line, or separate them with colons. A path that holds a colon cannot be given here.

The collector reads files only inside `data-dir` and `config-dirs`.

The collector does not copy some include targets. It records each one as "not copied", and the readings that need it read **not observed** or **representation**. These are an absolute `include_dir` in `postgresql.conf`, any absolute include in `pg_hba.conf` or `pg_ident.conf` (an `include`, `include_if_exists` or `include_dir` line on PostgreSQL 16 and later, or an `@file` name), and a relative include that leads above the directory of the main file (`postgresql.conf`, `pg_hba.conf` or `pg_ident.conf`). An absolute `include` or `include_if_exists` in `postgresql.conf` is copied.

Never guess a data directory or a configuration directory: ask the server with `psql -c 'SHOW data_directory'`, `psql -c 'SHOW config_file'` and `psql -c 'SHOW hba_file'`.

The collector asks the server where each file is (`config_file`, `hba_file`, `ident_file`, `data_directory`) and reads each file at that path. One path is moved: a file inside the server's data directory is read from `data-dir` instead. A file outside the data directory, such as Debian's `/etc/postgresql/18/main/pg_hba.conf`, is read at the server's own path, which must lie inside `config-dirs`.

By default the runner cannot read these files. The data directory is mode 0700, and `pg_hba.conf` and `pg_ident.conf` are 0640, owned by `postgres`. There are three ways forward. The examples use Debian or Ubuntu, PostgreSQL 18 and a runner user named `runner`.

The commands for (a) and (b), the two ways to let the runner read the configuration files, are in the quick start's section 6, with paths for Debian or Ubuntu; show them to the operator and let the operator choose and run one.

**(a) Run on the database host, with the runner in the `postgres` group.**

With the data directory at 0750 when the server starts, PostgreSQL writes `postgresql.auto.conf` and `postmaster.opts` group-readable (0640) from then on; `pg_hba.conf` and `pg_ident.conf` are already 0640 `postgres:postgres`. This gives every file, always current. The cost: the group also reads every table file in the data directory. Prefer (b).

**(b) Give the runner copies, or read access to these files only.** Copy the files inside the data directory to a directory the runner reads, and pass it as `data-dir`.

Inputs: `data-dir: /srv/assure-pgdata` and `config-dirs: /etc/postgresql/18/main`. In the Debian layout, `postgresql.conf` and the `conf.d` include directory are usually readable by every user; check with `ls -l`. The runner reads these configuration files and nothing else. The cost: the copies go stale. Copying the files to some other directory and naming it in `config-dirs` does not work: the collector looks for each file at the path the server reports.

For a runner on another host, put the copies at the same paths the server uses, and the data-directory files in the `data-dir` copy. Run this on the runner host, in a directory that holds copies of the server's files:

```
sudo install -d -m 0750 -o root -g runner /etc/postgresql/18/main /etc/postgresql/18/main/conf.d /srv/assure-pgdata
sudo install -p -m 0640 -o root -g runner postgresql.conf pg_hba.conf pg_ident.conf /etc/postgresql/18/main/
sudo install -p -m 0640 -o root -g runner conf.d/*.conf /etc/postgresql/18/main/conf.d/
sudo install -p -m 0640 -o root -g runner postgresql.auto.conf postmaster.opts /srv/assure-pgdata/
```

When the server keeps every configuration file in its data directory (the layout `initdb` writes), copy all of them, with any include directory at its relative path, into the `data-dir` copy, and leave out `config-dirs`.

**(c) Managed PostgreSQL.** The runner has no access to the server's files. Leave out `data-dir` and `config-dirs`. Every reading that needs a file reads **not observed** or **representation**, with the file named. The readings from the catalog still come back.

## Managed PostgreSQL and connection poolers (section 6)

Some managed services put a connection pooler in front of the server, and the pooler routes on the login name. Supabase's pooler, for example, takes the login name `assure_collector.<project-ref>`; inside the database the role is `assure_collector`.

- The `user` in `connection` is the login name. Keep it as the service gives it.
- `collection-role` is the role's name inside the database. The collector checks it against `current_user` and `session_user`. When it is not set, it is the user in `connection`.

When the two differ, the Action logs in with the login name and the collector checks the role. If you leave `collection-role` unset behind such a pooler, the collector refuses with `collection_role_mismatch` (`collector_refused`, exit 3), and the reason says which name to set.

On Supabase, the `postgres` role cannot grant `pg_read_all_settings` or `pg_read_all_stats`. It can grant `pg_monitor`, and the collector this Action ships refuses `pg_monitor` as broader than it needs (section 2). So this Action version cannot collect from a Supabase database.

Use the session pooler. Assure has run through Supabase's session pooler on port 5432. The collector runs each query in its own `psql` process, one short session per query; a transaction pooler has not been tested.

The collector asks for a read-only session. A pooler may not pass the request on: through Supabase's session pooler the session was not read-only. The collector runs only fixed SELECT statements either way. The job summary states whether the session was read-only (section 8).

The runner cannot read a managed server's configuration files, so the readings that need them read **not observed** or **representation**, as above.

## Three things that will look odd today

- **A refused machine (M2, client authentication) when the server has more than six databases or more than six users, as the checker counts them.** It counts the databases that allow connections, plus each one a `pg_hba.conf` rule names, and the login roles, plus each `+group`. The summary names the bound exceeded, for example "databases 7 (cap 6)" or "users 7 (cap 6)". The other machines still read, and the run stays green unless something is disproven. M2 also reads "missing method" today when any `pg_hba.conf` line uses `peer`, `ident` or another external authentication method (the Debian and Ubuntu default `local all postgres peer` included), until the checker bounds those methods.
- **A `pg_hba.conf` rule with a quoted role name, an `@file` list or a regular-expression user reads `representation` or `missing method`, not a verdict.** Under the default `fail-on: fails` such a run can still pass; choose `fail-on: fails,not_collected` to make those readings stop the job. A rule the collector has to withhold (an unclosed quote, for example) appears as `not observed: pg_hba.conf line N (<reason>)`.
- **Readings that read not observed or representation where you might expect a verdict.** On PostgreSQL 17 and 18 the collection role cannot read `pg_hba_file_rules` or `pg_file_settings` (nor, on 17, `pg_ident_file_mappings`, and on 18 `pg_subscription`), so the readings that need them read not observed. With more than one `SECURITY DEFINER` function, the search-path readings (SD-1, SD-2) read representation.
