# Route 2: collected files

## Managed PostgreSQL and connection poolers (section 6)

On Supabase, the `postgres` role cannot grant `pg_read_all_settings` or `pg_read_all_stats`. It can grant `pg_monitor`, and the collector this Action ships refuses `pg_monitor` as broader than it needs (section 2). So this Action version cannot collect from a Supabase database.

If the database is on Supabase, tell the operator so before any grant; do not grant `pg_monitor` and do not set it in `collection-privileges`.

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

## Running the collector yourself (section 9)

The collector is `action/collector/collect_pg.py` in the `Symbolia-Assurance/assure-action` repository. Use it at the same commit as your `uses:` line. Fetch it on a machine that can reach the server and has Python 3.14 and `psql`:

```sh
git clone https://github.com/Symbolia-Assurance/assure-action assure-action
git -C assure-action checkout <full commit sha>
```

Set the standard libpq variables for the server (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGPASSWORD`, `PGSSLMODE`). Find the data directory first: ask the server with `psql -c 'SHOW data_directory'` ("A server on your own machine", below), and give that directory, as this machine sees it, in place of `<data directory>`. Then run:

```sh
python3.14 -B assure-action/action/collector/collect_pg.py --out collected \
  --role assure_collector \
  --privileges pg_read_all_settings,pg_read_all_stats \
  --data-dir '<data directory>' \
  --role-created-for-run yes
```

It prints one line of JSON and exits with one of four codes:

| Exit | Meaning |
|---|---|
| 0 | Collected; every input was observed. |
| 1 | Collected with gaps. `COLLECTION-SIDECAR.json` lists each one under `entries` with its status (`unreadable`, `missing` or `unsupported`), and `gap_count` counts them. Give the output as `artefacts`: each gap reads **not observed** with the place it was looked for. |
| 2 | Invalid arguments. Nothing was read and nothing was written. The printed line, or the usage text before it, names the argument. |
| 3 | A typed refusal. The printed line gives its `type` and its `reason`. A refusal during the collection removes everything the run wrote and leaves `REFUSAL.json`, with the same type and reason, as the only file in `--out`. A refusal before the collection, such as a `--out` that is not new or empty, writes no `REFUSAL.json`. |

With the two roles of section 2, a collection usually ends with exit 1: the role cannot read some catalog views, such as `pg_hba_file_rules` and `pg_file_settings`, and each view it cannot read is a gap with the status `unreadable`. The collector still reads the configuration files themselves inside `--data-dir` and `--extra-root`.

The refusals name the reason in their `type`: for example `collection_role_superuser`, `collection_role_not_read_only` or `collection_role_not_least_privilege` for a role section 2 does not allow, `collection_role_mismatch` when the role you connect as is not `--role`, `unsupported_major` outside PostgreSQL 14 to 18, and `redaction_selfcheck_failed` when its own check found a withheld value in its output. Recreate the role as in section 2, or fix what the reason names, and run it again into an empty directory.

| Flag | Meaning |
|---|---|
| `--out` | A new or empty directory for the output. Required. Any other directory is refused with exit 3 before anything is read. |
| `--role` | The collection role's name inside the database (section 2). Required. |
| `--privileges` | The roles granted to it, comma separated: `pg_read_all_settings`, `pg_read_all_stats` or both. Required. `pg_monitor` or `pg_stat_scan_tables` here is refused with exit 2. |
| `--data-dir` | The server's data directory, as this machine sees it. Required, and it must be a directory that exists. When this machine cannot read the server's files, give an empty directory: every configuration file then reads as a recorded gap, as it does for the Action without `data-dir`. |
| `--extra-root` | A directory outside the data directory that holds configuration files, such as `/etc/postgresql/18/main`. Once per directory. The collector reads configuration files only inside `--data-dir` and these directories. |
| `--psql` | The `psql` command to run, when it is not `psql` on the path. |
| `--role-created-for-run` | `yes` or `no`: whether you created the role for this run. The collector records your answer in `COLLECTION-SIDECAR.json`; left out, it records that you did not say. The collector itself creates, alters and grants nothing. |
| `--login-user` | The login name, when a connection pooler's login name differs from the role (section 6). Left out, it is `--role`. |

The collector logs in as `--login-user`, or as `--role` when that is not given. The collector never asks for a password: give it in `PGPASSWORD`, or in a password file `psql` reads.

## A server on your own machine (section 9)

For a PostgreSQL server on the machine you collect on, ask the server where its files are, as the user you normally connect as:

```sh
psql -c 'SHOW data_directory'
psql -c 'SHOW config_file'
psql -c 'SHOW hba_file'
```

Give the data directory as `--data-dir`. When `config_file` or `hba_file` lies outside it, give that file's directory as `--extra-root`.

Read the `pg_hba.conf` that `SHOW hba_file` names. Where its `local` lines say `trust`, the role needs no password; create it without one:

```sql
CREATE ROLE assure_collector LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT pg_read_all_settings, pg_read_all_stats TO assure_collector;
GRANT CONNECT ON DATABASE <your database> TO assure_collector;
```

In these statements `<your database>` is the name of the database to check, or `postgres` for a local server that holds no other database.

Otherwise create it with a password as in section 2. The collector never asks for a password, so set `PGPASSWORD` for the collector's run only, and `unset PGPASSWORD` afterwards. Test the role first; it prints `assure_collector`:

```sh
psql -U assure_collector -d <your database> -c 'SELECT current_user'
```

When `psql` is not on the path, as with a Homebrew server whose client is not linked, tell the collector where it is: `--psql /opt/homebrew/opt/postgresql@<major>/bin/psql`.

When you have finished collecting, drop the role, as the user that created it:

```sql
REVOKE CONNECT ON DATABASE <your database> FROM assure_collector;
DROP ROLE assure_collector;
```

To collect again later, create it again.

## 9. Using collected files instead of a connection

You can collect on one machine and check from another. Set `artefacts` to a directory that holds a `raw/` folder (or to the `raw/` folder itself). Leave `connection` empty.

The directory must hold files under the names the profile reads. The API lists them for each profile (`GET /v1/profiles`). Files with other names stay in the runner and are listed in a notice. A symbolic link at an expected name is refused.

Give the collector's output directory as it wrote it. The collector writes `raw/` and, beside it, `COLLECTION-SIDECAR.json` and `TIMING.json`. The Action takes those two files from beside `raw/` (or from inside `raw/`, if you moved them there) and sends them as `raw/COLLECTION-SIDECAR.json` and `raw/TIMING.json`. If both places hold a copy and the copies differ, the Action stops with `bad_input`. Do not leave out `COLLECTION-SIDECAR.json`: it is the collector's record of which lines it withheld whole and why. A configuration file that holds a line the earlier collector withheld (`# [collect_pg: line withheld, ...]`) cannot be checked without it, so the Action stops with `collector_refused` and sends nothing: a collector output without its sidecar cannot be checked.

Keep `REDACTION-MANIFEST.json` too. The collector writes it beside `raw/` in the same run as the sidecar. It records the digest of each file as the collector wrote it, and what the collector withheld. When a file holds a withheld line, the Action uses it in the runner to check that the sidecar belongs to these files: the file must be unchanged since collection, and the manifest and the sidecar must record the same withheld lines. If the manifest is missing, records a different digest for such a file, or disagrees with the sidecar, the Action stops with `collector_refused` and sends nothing. Records from another run are caught only when a file that holds a withheld line differs, byte for byte, from that run's file. Records kept from an earlier run of the same server pass if the withheld lines sit at the same places with the same marker, even where a line that was a comment is now a rule. So always use the sidecar and manifest written by the same collector run as `raw/`. The manifest stays in your runner; it is never sent. With the collector this Action ships, a withheld rule or setting is a marker line that names its own line number and reason, so records from another run cannot hide it: the check reads that line as not observed whatever the records say. That collector's sidecar is recognised by its own fields; a collection that mixes its output with the earlier collector's stops with `collector_refused`. The earlier collector withheld a `pg_hba.conf` rule with a quoted name, an `@file` list or a regular-expression user whole, so its files stop there with `collector_refused`; collect again with this Action.

Line continuation in `pg_hba.conf` (a line ending in `\`) depends on the server's major version. If `raw/declaration.json` gives a major on the other side of 16 from the one the sidecar records, and a `pg_hba.conf` line ends in `\`, the Action stops with `bad_input`. Set the declaration's `major` to the server's major.

The declared profile, `postgresql-declared-model`, reads your declaration from `raw/declaration.json` (and optionally `raw/clients.json`) beside the collected files:

```yaml
      - name: Assure check from collected files
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-declared-model
          artefacts: collected
          fail-on: fails
```

## Bringing the folder to the runner (section 9)

Show the operator `docs/DATA.md` before the first run, and ask before committing collected files to the repository.

The Action reads `artefacts` from the runner's working directory. Put the folder there before the Assure step, in one of three ways:

- **Committed to your repository.** Add a step with `actions/checkout`, pinned to a full commit SHA. The complete workflow is below.
- **Made by an earlier job.** That job uploads the folder with `actions/upload-artifact`; the job that runs the Action fetches it with `actions/download-artifact` in place of the checkout step.
- **Collected in the same job.** Fetch the collector and run it in a step before the Assure step, as in "Running the collector yourself". The runner must then reach your database.

Committing the folder puts what it holds into your repository's history: role names, ACLs, `pg_hba.conf` rules with client addresses, and the other items `DATA.md` lists as sent as written. Commit it only where everyone who can read the repository may read those.

A complete workflow for the intent-free profile, with the collector's output committed as `collected/`:

```yaml
name: Assure

on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Assure check from collected files
        id: assure
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-observed-baseline
          artefacts: collected
          fail-on: fails
          output: assure-verdict.json

      - name: Keep the verdict
        if: always()
        uses: actions/upload-artifact@<full commit sha of the release you trust>
        with:
          name: assure-verdict
          path: ${{ steps.assure.outputs.verdict-path }}
```

For the declared profile, set `profile: postgresql-declared-model` and commit your declaration as `collected/raw/declaration.json`.

For a folder made by an earlier job, this step takes the place of the checkout step:

```yaml
      - name: Fetch the collected files
        uses: actions/download-artifact@<full commit sha of the release you trust>
        with:
          name: collected
          path: collected
```

The earlier job uploads the whole folder as the collector wrote it, under the name `collected`. The job that runs the Action names the collecting job in `needs:`, so it starts only after the upload; without it the two jobs run at the same time and the download finds nothing:

```yaml
  check:
    needs: collect
    runs-on: ubuntu-latest
```

## Collecting again after a change (section 9)

A check on collected files reads the server as it was when you collected. After you change the server (a setting, a `pg_hba.conf` rule, a role or a grant), collect again. `--out` must be a new or empty directory, so remove the old output first, then run the collector as above and commit the new folder:

```sh
rm -rf collected
python3.14 -B assure-action/action/collector/collect_pg.py --out collected \
  --role assure_collector \
  --privileges pg_read_all_settings,pg_read_all_stats \
  --data-dir '<data directory>' \
  --role-created-for-run yes
```

Keep `raw/`, `COLLECTION-SIDECAR.json` and `REDACTION-MANIFEST.json` from the one new run together. Running the workflow again without collecting again sends the same files: it gets the stored verdict of the first run back, and it says nothing about the change.

The Action makes one check per distinct bundle. It derives its `Idempotency-Key` from the content of the request: a digest of the bundle's files, the profile, the selected scope and its binding, and the `fail-on` and `allow-partial` words as sent. A later run whose request is the same, byte for byte, gets the stored verdict of the first run back, and it is not charged again. A changed byte in any file is a new check. A changed `fail-on` is a new check too, because the stored verdict carries the policy it was checked under.

A collection from a connection is never the same twice: the collector records when it collected and how long each query took. An HTTP check is never the same twice either: the Action makes a fresh identity key for each job, so the endpoint tokens differ from run to run. A stored verdict comes back when `artefacts` holds a collected bundle with the same files as an earlier run, for example when you run a job again.

A stored failure comes back the same way. To check the same bundle again on purpose, set `fresh-check: true`: the Action then sends a random key, and the check runs and is charged again. The server keeps a key for as long as the verdict it points to (30 days).
