# Quickstart: the Assure GitHub Action

> **First run checklist.** Tick all five before the first run.
>
> - [ ] The collection role exists, with `CONNECT` on your database (section 2).
> - [ ] The runner can read the server's configuration files, or has copies it can read (section 6). Managed PostgreSQL: skip this line.
> - [ ] The connection string works from the runner: `psql '<the connection string>' -c 'SELECT current_user'` prints `assure_collector` (section 3).
> - [ ] The API key is stored as the repository secret `ASSURE_API_KEY` (section 1).
> - [ ] `profile` is left at its default, `postgresql-observed-baseline`.

**Served today:** three profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory with your declaration in `raw/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe.

Known-vulnerability scanners check your code against a list of what has broken before. Assure checks whether the way your code meets the foundational software it runs on stays inside a regime that can be shown safe and reliable, and says exactly what it could and could not establish.

Assure is the check that reads green only when nothing it examined is disproven. It tells you the bounds of what it has established, and why it matters. In an age where machines generate code at a volume nobody can read, Assure shows that each change maintains its baseline security and reliability, and stays true to any formalised requirements.

The Action collects facts in your GitHub Actions runner and sends them to `api.symbolia.ai` over TLS with your API key. The check runs on Symbolia's server; the Action writes the verdict, job summary and annotations in your runner.

Supported PostgreSQL majors: 14 to 18. Real-run evidence: 17 and 18.

**Rules the collector keeps, and rules it withholds.** The collector this Action ships keeps a `pg_hba.conf` rule with a quoted name, an `@file` list or a regular-expression user (`/^...`) as written, and the check reads it. A rule or setting it still has to withhold, such as a rule with an unclosed quote, becomes a marker line that names its own line number and reason. The check reads that rule or setting as not observed, and the summary lists it as `not observed: <file> line N (<the reason in plain words>)`.

Files collected earlier with the earlier collector, given as `artefacts`, still stop at such a rule with exit 3 (`collector_refused`): that collector withheld it whole, and Assure cannot read it. The message names the file and the line. Collect again with this Action. If you cannot: remove quotes a name does not need; write an `@file` list's names inline; use a `+group` role in place of a list; list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted.

## What is sent, and what is never read

The Action sends the collector's output: catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. What leaves the runner:

- settings and rules as written, without comment text: every comment in your configuration files, including commented-out settings, is replaced in the runner with `# <withheld comment>`, and every line keeps its place. A line PostgreSQL cannot parse (an unclosed quote) becomes `<withheld: a line PostgreSQL cannot parse>`, which the check still counts as a broken line; if the check would read it as a working setting or rule, the Action stops, exits 2 (`bad_input`) and names the file and the line, and you fix the line and run again. A `pg_hba.conf` rule or `postgresql.conf` setting the collector had to withhold whole is a marker line the check reads as not observed, and the summary lists it as `not observed: <file> line N (<reason>)`. A marker whose line number is not its own, or whose reason is not one the collector writes, stops the upload with exit 2 (`bad_input`), and a collection that mixes this collector's output with the earlier collector's stops with exit 3 (`collector_refused`). In files from the earlier collector, a rule or setting that collector withheld whole stops the upload with exit 3 (`collector_refused`) (section 9). The collector's record of which lines it withheld (`COLLECTION-SIDECAR.json`) must come with its output, with the `REDACTION-MANIFEST.json` from the same run: without them, a file that holds a withheld line cannot be checked, and the upload stops the same way;
- policy expressions with every string literal withheld: each quoted literal becomes `'<withheld literal N>'` in the runner, and so does each literal in your declaration's `declared_predicate`;
- no secret-bearing value: the collector withholds every one whole before anything is written, and checks its own output for those values.

The job log and the job summary state how many comments and literals were withheld. For a profile whose inputs name no PostgreSQL configuration or `pg_hba.conf` file, such as the HTTP profile, nothing is withheld: the files are sent as read, and the line says "nothing to withhold — the withholding pass covers PostgreSQL configuration and pg_hba files and the SQL literals in the catalog snapshot and the declaration, and this profile's inputs name none of them". [DATA.md](DATA.md) lists every item, including what is still sent as written, such as role names and client addresses.

The collector never reads table contents, password hashes, key material or other sessions' statements. It reads the connection string of a subscription and withholds it whole before anything is written.

The Action sends only files the profile reads. It fetches each profile's list of file names and size limits from the API first, and checks every file against that list in the runner. A file with another name, or over its limit, stays in the runner.

The server deletes the collected facts when the check ends. It keeps the verdict for 30 days.

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

## Reading your first result

The first line of the job summary, and the Action's last log line, starts with a colour, then says how much was read, "N of 8 machines read, M refused", and the bounds of the result. A machine is one part of the check, such as client authentication or row-level security. A refused machine was not read, and the summary lists it under "Machines not read" with its reason.

- **green** (exit 0): within these bounds, nothing disproven. For example "green: 7 of 8 machines read, 1 refused; declared premises: none (observed profile); version pins: major 18; nothing disproven; established: 4 of 40; deviations: 2; not established: 18 — top action: state it in requirements.md". A deviation is counted on its own. When no obligation on the machines read holds, the line says so in words: "nothing could be established (0 of N obligations hold); not established: n — top action: \<action>". One line follows for each obligation that could not be established, "\<id>: \<reason> — \<owner>: \<what it needs>". Green never means more than this.
- **red**: something is disproven, for example "red: ...; disproven: \<obligation> — \<object>, \<access path>, \<locator>". It exits 1 when your `fail-on` names the status (`fails` by default). A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. When your `fail-on` leaves a disproven status out, the exit is 0 and the line ends "(exit 0 by your fail-on: ...)". A status you chose to stop on that is not a verdict (for example `fail-on: not_observed`) is red with exit 1 and reads "stopped by your choice: not observed — \<obligation>", never "disproven".
- **yellow** (exit 3): nothing could be read at all, "yellow: could not look: \<reason>; \<action>", for example "yellow: could not look: the input could not be represented; re-collect with the pinned collector". The summary prints the reason and the file it names under it. A typed outcome that stopped the check before any reading also exits 3. Yellow is a check run's `action_required` where a check run is published with `checks: write`; this Action publishes none, so it falls back to exit 3, which fails the job.

Under the first line, one sentence says what it means in plain words. For a green PostgreSQL run: "Nothing in your database configuration contradicts what is known about safe PostgreSQL setups. 21 of 40 checks could not be completed, mostly because they depend on what the system is for, which has not been stated. That is a gap in what we could see; your database configuration is unchanged by it." For red, the consequence of what was disproven and where; for yellow, that nothing below is a finding and what to do. Each disproven or deviating obligation is listed under "Why it matters" with its statement and its consequence ("Consequence not yet stated for \<obligation>." until the profile states one).

[FIRST-LINE-SAMPLES.md](FIRST-LINE-SAMPLES.md) shows one first line for each colour, word for word, with the meaning sentence for each colour and profile.

A refused machine bounds the result and is named; a status you name in `fail-on` on its rows stops the job as on a read machine, and a reading the checker kept on it is read as not observed. `allow-partial` is still accepted and no longer changes anything.

Under the first line, the summary lists every reading under its status, each with its text: why it holds, why it fails, or what could not be read. The verdict file holds the same readings with their premises ([VERDICTS.md](VERDICTS.md)). The Action keeps it at the `output` path; the workflow above uploads it as the `assure-verdict` artifact.

If a reading looks wrong, send Symbolia, through your Symbolia contact, the check id (the line under the heading: "Profile ..., check \<id>."), the first line, and the summary text of that reading. Never send your configuration files or your connection string.

## 5. Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-key` | none | Your Assure API key. Pass it from a secret. Required. |
| `api-url` | `https://api.symbolia.ai` | The API address. The published API is `https://` only. Plain `http://` is accepted only for a loopback host (`127.0.0.1`, `::1` or `localhost`), for a local test server. |
| `mode` | `api` | `api`: the check runs on the Assure API. |
| `profile` | `postgresql-observed-baseline` | The checker profile to run. |
| `connection` | none | libpq connection string or URI. Pass it from a secret. |
| `artefacts` | none | A directory of collected files. Use this or `connection`, never both. For `http-observed-baseline` with `scope-binding` empty, the directory holding your endpoint manifest (`manifest.json` and the response heads it names): the Action binds the endpoints and collects them itself. |
| `collection-role` | the user in `connection` | The role's name inside the database. The collector checks it against `current_user`. Set it when a connection pooler's login name differs (section 6). |
| `collection-privileges` | `pg_read_all_settings,pg_read_all_stats` | The roles you granted to the collection role: one or both of these two. |
| `data-dir` | none | A path where the runner can read the server's data directory. Used with `connection`. |
| `config-dirs` | none | Directories that hold the server's configuration files outside the data directory, one per line or separated by colons. Used with `connection`. |
| `fail-on` | `fails` | Which statuses fail the job (section 7). The API checks it against the profile and applies it. `unresolved-security` adds strict (section 7). |
| `allow-partial` | `false` | Accepted for compatibility; it no longer changes the exit (section 7). Any other word is `bad_input`. |
| `scope` | none | A JSON file of selected ids, for a profile whose scope you select. Both PostgreSQL profiles take none. |
| `scope-binding` | none | A JSON file holding the whole `scope_binding` object, for a profile that binds its scope: the token map under the profile's map name, and any record the profile lists. The Action checks its keys before collecting. Both PostgreSQL profiles take none. For `http-observed-baseline`, leave it empty and the Action makes it. |
| `identity-key` | `pipe` | For `http-observed-baseline`: how the endpoint identity key reaches the identity producer. Only `pipe`. The Action makes a fresh key for each job, passes it to the producer and then the collector on a pipe, and keeps nothing, so no key is an input, an environment variable or a file and nothing persists between runs; that is fine while no accepted scope exists, since a later comparison with an accepted scope will need a key kept across runs. Any other value is masked and refused before anything is read. |
| `accepted-scope-ref` | none | Refused for now, before anything is collected or sent: no accepted scope record can be resolved yet. Leave it empty. |
| `report` | `false` | `true` asks the API for the plain-language report of the check's claim tree after a verdict ("The report"). `mode: api` only. Any other word is `bad_input`. |
| `allow-overage` | `false` | With `report: true`, `true` lets a report beyond your account's monthly report allowance run, and its overage is charged at cost x 1.2 ("The report"). Any other word is `bad_input`. |
| `fresh-check` | `false` | `true` sends a random `Idempotency-Key`, so the same bundle is checked, and charged, again (section 9). By default the key comes from the content of the request, and a repeat of the same request gets the stored verdict back. Any other word is `bad_input`. |
| `output` | `assure-verdict.json` | Where to write the verdict file. |
| `python` | `python3` | The Python 3.14 interpreter to use. |

## 6. Managed PostgreSQL and configuration files

Some facts live in configuration files: `postgresql.conf` and the files it includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. The collector finds them through the server's own settings and reads them from the runner's filesystem.

With a connection and no data directory, the runner cannot read those files. This is the usual case for managed PostgreSQL. A reading that needs a fact from a file then reads **not observed**. Where the checker cannot represent the input without the file, as with a missing `pg_hba.conf` or `postgresql.conf`, the readings that use it read **representation**. The client-authentication and TLS obligations are the ones most affected.

To read the files, run the Action on a self-hosted runner that can read them:

- `data-dir`: the server's data directory, as the runner sees it.
- `config-dirs`: directories that hold configuration files outside the data directory. The Debian and Ubuntu packages keep them in `/etc/postgresql/<major>/<cluster>`:

```yaml
data-dir: /var/lib/postgresql/18/main
config-dirs: /etc/postgresql/18/main
```

Give one directory per line, or separate them with colons. A path that holds a colon cannot be given here.

The collector reads files only inside `data-dir` and `config-dirs`.

The collector does not copy some include targets. It records each one as "not copied", and the readings that need it read **not observed** or **representation**. These are an absolute `include_dir` in `postgresql.conf`, any absolute include in `pg_hba.conf` or `pg_ident.conf` (an `include`, `include_if_exists` or `include_dir` line on PostgreSQL 16 and later, or an `@file` name), and a relative include that leads above the directory of the main file (`postgresql.conf`, `pg_hba.conf` or `pg_ident.conf`). An absolute `include` or `include_if_exists` in `postgresql.conf` is copied.

### Letting the runner read the server's configuration files

The collector asks the server where each file is (`config_file`, `hba_file`, `ident_file`, `data_directory`) and reads each file at that path. One path is moved: a file inside the server's data directory is read from `data-dir` instead. A file outside the data directory, such as Debian's `/etc/postgresql/18/main/pg_hba.conf`, is read at the server's own path, which must lie inside `config-dirs`.

By default the runner cannot read these files. The data directory is mode 0700, and `pg_hba.conf` and `pg_ident.conf` are 0640, owned by `postgres`. There are three ways forward. The examples use Debian or Ubuntu, PostgreSQL 18 and a runner user named `runner`.

**(a) Run on the database host, with the runner in the `postgres` group.** Put the data directory in PostgreSQL's group-access mode (the same as `initdb --allow-group-access`), with the server stopped, and add the runner user to the group:

```
sudo systemctl stop postgresql@18-main
sudo chmod 0750 /var/lib/postgresql/18/main
sudo chmod -R g+rX /var/lib/postgresql/18/main
sudo systemctl start postgresql@18-main
sudo usermod -aG postgres runner
```

Restart the runner service so the new group applies. With the data directory at 0750 when the server starts, PostgreSQL writes `postgresql.auto.conf` and `postmaster.opts` group-readable (0640) from then on; `pg_hba.conf` and `pg_ident.conf` are already 0640 `postgres:postgres`. Inputs: `data-dir: /var/lib/postgresql/18/main` and `config-dirs: /etc/postgresql/18/main`. This gives every file, always current. The cost: the group also reads every table file in the data directory. Prefer (b).

**(b) Give the runner copies, or read access to these files only.** Copy the files inside the data directory to a directory the runner reads, and pass it as `data-dir`. Leave the files under `/etc` where they are, and give the runner read access to the two that it cannot read:

```
sudo install -d -m 0750 -o root -g runner /srv/assure-pgdata
sudo install -p -m 0640 -o root -g runner /var/lib/postgresql/18/main/postgresql.auto.conf /var/lib/postgresql/18/main/postmaster.opts /srv/assure-pgdata/
sudo setfacl -m u:runner:r /etc/postgresql/18/main/pg_hba.conf /etc/postgresql/18/main/pg_ident.conf
```

Inputs: `data-dir: /srv/assure-pgdata` and `config-dirs: /etc/postgresql/18/main`. In the Debian layout, `postgresql.conf` and the `conf.d` include directory are usually readable by every user; check with `ls -l`. `-p` keeps each copy's modification time. The runner reads these configuration files and nothing else. The cost: the copies go stale. Copy again after `ALTER SYSTEM` (which rewrites `postgresql.auto.conf`) and after a server restart (which rewrites `postmaster.opts`), and set the ACL again if an editor replaces `pg_hba.conf`. Copying the files to some other directory and naming it in `config-dirs` does not work: the collector looks for each file at the path the server reports.

For a runner on another host, put the copies at the same paths the server uses, and the data-directory files in the `data-dir` copy. Run this on the runner host, in a directory that holds copies of the server's files:

```
sudo install -d -m 0750 -o root -g runner /etc/postgresql/18/main /etc/postgresql/18/main/conf.d /srv/assure-pgdata
sudo install -p -m 0640 -o root -g runner postgresql.conf pg_hba.conf pg_ident.conf /etc/postgresql/18/main/
sudo install -p -m 0640 -o root -g runner conf.d/*.conf /etc/postgresql/18/main/conf.d/
sudo install -p -m 0640 -o root -g runner postgresql.auto.conf postmaster.opts /srv/assure-pgdata/
```

When the server keeps every configuration file in its data directory (the layout `initdb` writes), copy all of them, with any include directory at its relative path, into the `data-dir` copy, and leave out `config-dirs`.

**(c) Managed PostgreSQL.** The runner has no access to the server's files. Leave out `data-dir` and `config-dirs`. Every reading that needs a file reads **not observed** or **representation**, with the file named. The readings from the catalog still come back.

### Managed PostgreSQL and connection poolers

Some managed services put a connection pooler in front of the server, and the pooler routes on the login name. Supabase's pooler, for example, takes the login name `assure_collector.<project-ref>`; inside the database the role is `assure_collector`.

- The `user` in `connection` is the login name. Keep it as the service gives it.
- `collection-role` is the role's name inside the database. The collector checks it against `current_user` and `session_user`. When it is not set, it is the user in `connection`.

When the two differ, the Action logs in with the login name and the collector checks the role. If you leave `collection-role` unset behind such a pooler, the collector refuses with `collection_role_mismatch` (`collector_refused`, exit 3), and the reason says which name to set.

On Supabase, the `postgres` role cannot grant `pg_read_all_settings` or `pg_read_all_stats`. It can grant `pg_monitor`, and the collector this Action ships refuses `pg_monitor` as broader than it needs (section 2). So this Action version cannot collect from a Supabase database.

Use the session pooler. Assure has run through Supabase's session pooler on port 5432. The collector runs each query in its own `psql` process, one short session per query; a transaction pooler has not been tested.

The collector asks for a read-only session. A pooler may not pass the request on: through Supabase's session pooler the session was not read-only. The collector runs only fixed SELECT statements either way. The job summary states whether the session was read-only (section 8).

The runner cannot read a managed server's configuration files, so the readings that need them read **not observed** or **representation**, as above.

## 7. The fail-on policy and exit codes

`fail-on` is a comma list of words, or the single word `never`. The Action sends it as you wrote it. The API checks every word against the profile and applies it. A word the profile cannot emit is `bad_input`, and the reason lists the words that profile accepts. `GET /v1/profiles` lists them too.

The words a profile accepts:

- any status the profile can emit except `holds` and `vacuous`;
- `not_collected`: every status the profile uses for a fact it could not read or represent;
- `never`, on its own: readings never fail the job, except a prove-class obligation that is not proven (exit 1, `not_proven`).

| Profile | Statuses you can name | `not_collected` stands for |
|---|---|---|
| `postgresql-declared-model` | `fails`, `representation`, `missing_method`, `missing_premise`, `not_evaluated` | `representation`, `missing_method`, `missing_premise`, `not_evaluated` |
| `postgresql-observed-baseline` | `fails`, `deviates`, `representation`, `missing_method`, `not_observed`, `missing_baseline`, `needs_intent` | `representation`, `missing_method`, `not_observed`, `missing_baseline` |

`needs_intent` is outside `not_collected`: it marks a norm that depends on what the system is for, which is out of scope by design. Name it on its own to fail on it.

Examples:

- `fails` (the default): the job fails when any obligation reads fails.
- `fails,deviates`: the job also fails on a deviation from vendor guidance or from the Assure baseline (observed profile).
- `fails,not_collected`: the job also fails when a needed fact was not collected or could not be represented.
- `never`: readings never fail the job, except a prove-class obligation that is not proven, which exits 1 (`not_proven`). A typed outcome still does.
- `unresolved-security` (strict, never the default): `fails`, and also every obligation the checker marks `security: true` that is not resolved, that is, has no verdict on a machine that was read. Such an obligation turns the run red with "unresolved by your choice (strict): \<id> — \<reason>; \<action>", and each obligation that could not be established is also a notice annotation. The observed PostgreSQL profile marks 36 of its 40 obligations `security: true` (authentication, authorisation, privilege, definer context, replication and transport); there strict stops the job on any of them that has no verdict, and the first line says "strict: n of m security obligations observable at this pin". The HTTP and declared profiles mark none, so there strict is a no-op and the first line says "strict: no obligations marked". Only the security obligations the pinned collector can observe count in n and m: an obligation the profile marks `observable_at_pin: false` is listed as not established, "not observable at collector pin \<pin>", and the first line says "strict: n of m security obligations observable at this pin". An intent-bound obligation (`class: intent_bound`) depends on what the system is for, which no collector observes. All security obligations without a verdict bind under strict, including one the pin cannot observe; the report names each and why. An intent-bound one is named "unresolved by your choice (strict)", reads "depends on what the system is for" and has the action "state it in requirements.md". n and m count observability only: an intent-bound obligation never counts in them and is never listed as not observable at the collector pin; m counts the intent-free security obligations.

Each obligation has a class its profile declares, never settable per run, and `GET /v1/profiles` lists it: `refute` (green unless disproven) or `prove` (red unless proven). A prove-class obligation that does not read holds on a machine that was read turns the run red, "not proven: \<id> — input not observed" when its input could not be read, else "not proven: \<id> — \<reason>; \<action>", and the first line states "prove-class obligations: p (unproven: u)". Every obligation of today's profiles is refute-class.

The Action exits with the verdict's own policy exit, `policy.exit` in the verdict file. `policy.reason` says why, in one word. The job summary states the policy and this run's exit in plain words.

| Code | `policy.reason` | Meaning |
|---|---|---|
| 0 | `nothing_disproven` | Green: nothing is disproven within the bounds the first line states. Machines or endpoints that could not be read, and a run with no verdict, are named there and do not change the exit. |
| 0 | `never` | `fail-on` is `never`. The first line keeps the colour the readings give. A prove-class obligation that is not proven still exits 1 (`not_proven`). |
| 1 | `disproven` | Red: a reading on a machine that was read has a status you fail on. A disproof your `fail-on` leaves out stays red with exit 0 and the same reason. |
| 1 | `not_proven` | Red: a prove-class obligation is not proven. |
| 1 | `unresolved_strict` | Red: under strict, an obligation marked `security: true` is unresolved. |
| 1 | `stopped_by_choice` | Red: a reading has a status that is not a verdict and that your `fail-on` names (`not_observed`, or a status `not_collected` stands for). The job stopped on a status you named in fail-on; the colour above says whether anything is disproven. |
| 2 | | Bad input, or an API key that is missing, unknown or revoked (`unauthenticated`). Red. Fix the inputs, the files or the key. |
| 3 | `could_not_look` | Yellow: nothing could be read at all: the input-integrity gate stopped the check, no machine was read, or no selected endpoint was observed. |
| 3 | | A typed outcome. The failure file holds the reason and what to do. |

A reading with a status you fail on gives exit 1 whatever could not be read. A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. `allow-partial` no longer changes the exit. The input-integrity gate gives 3 under every policy except `never`.

A vacuous reading only says that a domain was empty. A run whose only verdicts are vacuous reads "No verdicts" in the summary, and its first line says "nothing could be established".

The first line counts the machines read out of every machine the profile checks, "5 of 8 machines read, 3 refused" (", K refused" only when a machine was refused): a machine that gave no reading at all is listed as refused with the reason "no readings for this machine". When Assure worked the list out from the readings because the checker did not report it, the count ends "(inferred)". The bounds follow: "declared premises: n" (premises you declared; "none (observed profile)" for an observed profile that has none) and "version pins: major 18" (the server's observed major; "none" when the readings name none). Under the meaning sentence, the summary answers three questions in three short sentences, "Usable readings: u of n. Coverage complete: yes or no. Job stops: no (exit 0 by your fail-on), or yes (exit 1).", followed by the collection time and the loaded state when the collector records them, and lists the obligations the profile version cannot yet check (representation, missing method) under their own heading, "Unsupported by this profile version: n".

If the checker itself fails, the result is the typed outcome `checker_error` (exit 3) under every policy, `never` included. A check is charged once the checker has started, whatever its result, `checker_error` and `checker_timeout` included. One failure is not charged: the checker's own internal error, a `checker_error` whose `detail.rule` is `internal_error`. A request refused before the checker starts is never charged, and neither is a check cut short by a server restart; it still counts against your rate limits. A result is returned whenever one can be produced: when the checker's output for one machine is malformed, that machine is listed under "Machines not read" with its reason (`malformed_output: ...`, or `server_fault: ...` when the server could not write it) and the other machines keep their readings. When no result can be produced, the failure's `detail.malformation` says what was malformed: a fixed kind, the file, the line, the field and the expected form, never your text.

The Action sets five outputs: `verdict-path`, `outcome`, `exit-code`, `colour` (`green`, `red` or `yellow`; a failure is `red` for bad input or a bad key, exit 2, and `yellow` otherwise) and `not-established` (how many obligations could not be established; empty for a failure).

## 8. Where the results appear

- **The verdict file.** JSON at the `output` path, schema `assure.serve.verdict/v1`. It holds every reading with its premises. See [VERDICTS.md](VERDICTS.md).
- **The job summary.** A table of counts by status, then one line per obligation. It appears on the run page. When the collector recorded the collection session, the summary ends with two lines, as the server reported them for that session:
  - `The collection session was read-only: yes`, `no` or `not recorded`;
  - `TLS to the server: yes (<protocol>, <cipher>, <bits> bits)`, `no` or `not recorded`.

  Behind a connection pooler they describe the pooler's session to the server, not your runner's connection to the pooler. The job log carries the same two lines.
- **Annotations.** The first line is the first notice annotation. Each `fails` reading is an error annotation. Each `deviates` reading is a warning annotation. Under strict, each obligation that could not be established is a notice annotation. At most 50 of each appear.

When no obligation reaches a verdict, the summary says "No verdicts" and the first line says "nothing could be established". It never means "no issues".

Text from the checker or your files is shown as plain text. A web address in it appears as code, never as a link.

## The report

Set `report: true` to get a plain-language report of the claim tree behind a verdict: what was checked, what holds, what fails and why, and what the check could not decide. It needs `mode: api` and an account whose tier includes the report; otherwise the API refuses it with `tier_excludes`. A language model writes it from the verdict's record alone, never from your files. A deterministic check then reads it against the record, and a report that fails that check is withheld. Reports are written for `postgresql-declared-model` verdicts today; for other profiles the report is withheld and says so.

- **Written.** The job summary carries the first line, then the report, then a line naming the report page. The page shows the claim tree with each rule's check id, status, reason and evidence. Open it with your API key in the `Authorization` header. The `report-url` output holds its address.
- **Withheld or refused.** The job summary carries the usual summary and one more line: "The report was withheld: \<reason>." A refused report adds one warning annotation, never an error.

The report never changes the verdict, the verdict file or the exit code. The first line and the verdict file stay the record. The `report-status` output reads `written`, `withheld`, `refused`, or `running` when the report was still being written as the Action stopped waiting; the summary and `report-url` then name its page, to open later. [DATA.md](DATA.md) says what is sent to the writer and how long a report is kept.

**What a report costs.** Each paid plan has a monthly report allowance, counted in USD at the model's price. No paid plan's allowance is set yet, so today every paid report is overage. The free plan has a report balance of USD 1, granted once per verified email; it does not renew, a report is paid from it at its real cost, and reports stop while the balance is below zero. A recharge clears what is owed, and the rest goes to your account's top-up. A report within the allowance or the balance is not charged. The part of a report's cost beyond it is charged at cost x 1.2. Before a report runs, the API holds its expected cost (the high end of its quote) against your allowance and top-up, so two reports never share the same cover. A report that would go beyond the allowance runs only when you set `allow-overage: true`, or when your account's top-up covers the hold. Otherwise the API refuses it with `allowance_exhausted`: nothing runs and nothing is charged, and the summary reads "Report: allowance exhausted: USD q needed; set allow-overage or top up". Without `allow-overage`, a report is never charged more than its hold, even when the model cost more. A free report beyond what is left of the balance is refused `allowance_exhausted` whatever `allow-overage` says. One job's quote can be at most USD 50 unless you ask Symbolia to raise your account's job ceiling; the quote comes first. A report whose quote is above it is refused `job_ceiling`, even with `allow-overage`. Each plan also has a daily report cap (`daily_report_cap`), which counts the reports that ran. While Assure is in beta a withheld report is not charged. Asking again for a report you already have returns the same record at no cost. The summary adds one line, "Report: cost USD x.xxx, charged USD y.yyy, allowance remaining USD z.zz", and the outputs `report-cost-usd`, `report-charge-usd` and `report-allowance-remaining` hold the same figures.

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

### Bringing the folder to the runner

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

### Running the collector yourself

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

It prints one line of JSON and exits with one of four codes:

| Exit | Meaning |
|---|---|
| 0 | Collected; every input was observed. |
| 1 | Collected with gaps. `COLLECTION-SIDECAR.json` lists each one under `entries` with its status (`unreadable`, `missing` or `unsupported`), and `gap_count` counts them. Give the output as `artefacts`: each gap reads **not observed** with the place it was looked for. |
| 2 | Invalid arguments. Nothing was read and nothing was written. The printed line, or the usage text before it, names the argument. |
| 3 | A typed refusal. The printed line gives its `type` and its `reason`. A refusal during the collection removes everything the run wrote and leaves `REFUSAL.json`, with the same type and reason, as the only file in `--out`. A refusal before the collection, such as a `--out` that is not new or empty, writes no `REFUSAL.json`. |

With the two roles of section 2, a collection usually ends with exit 1: the role cannot read some catalog views, such as `pg_hba_file_rules` and `pg_file_settings`, and each view it cannot read is a gap with the status `unreadable`. The collector still reads the configuration files themselves inside `--data-dir` and `--extra-root`.

The refusals name the reason in their `type`: for example `collection_role_superuser`, `collection_role_not_read_only` or `collection_role_not_least_privilege` for a role section 2 does not allow, `collection_role_mismatch` when the role you connect as is not `--role`, `unsupported_major` outside PostgreSQL 14 to 18, and `redaction_selfcheck_failed` when its own check found a withheld value in its output. Recreate the role as in section 2, or fix what the reason names, and run it again into an empty directory.

### A server on your own machine

For a PostgreSQL server on the machine you collect on, ask the server where its files are, as the user you normally connect as:

```sh
psql -c 'SHOW data_directory'
psql -c 'SHOW config_file'
psql -c 'SHOW hba_file'
```

Give the data directory as `--data-dir`. When `config_file` or `hba_file` lies outside it, give that file's directory as `--extra-root`. Homebrew on Apple silicon keeps the data directory at `/opt/homebrew/var/postgresql@<major>`, and Postgres.app at `~/Library/Application Support/Postgres/var-<major>`; check with `SHOW` all the same.

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

### Collecting again after a change

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

## 10. Typed outcomes

When the Action cannot produce a verdict, it writes a failure file at the `output` path (schema `assure.serve.failure/v1`) with `outcome`, `reason` and `action`. It also writes the reason to the job summary and one error annotation. When the API gave a check id, the failure file carries it.

The last line of the summary says what left your runner:

- "No check was sent." The Action stopped in your runner. Nothing was sent.
- "The API refused the request for the profile list before anything was collected; nothing from your system was sent." The Action asks the API for the profile list first. A wrong or revoked key, or a rate limit, is refused there, before the Action collects or sends anything.
- "The API refused the request before a check started; the collected files were sent and not kept."
- "Check \<id>. The check was sent; the API refused the poll for its result."
- "Check \<id>." The check reached the server. Report this id to Symbolia.
- "No check id came back from the API." The request may have left your runner; no check id came back.

| Outcome | Exit | What it means | What to do |
|---|---|---|---|
| `bad_input` | 2 | An input is missing or malformed, a required file is absent, both `connection` and `artefacts` were set, `api-key` is missing, or `api-url` is not `https://` (plain `http://` only for a loopback host). | Read the reason and fix the input. |
| `oversize_input` | 2 | A file, the file count or the total size is over the limit. | Remove files the profile does not read. Limits: 4 MiB per file, 64 files, 8 MiB in total. |
| `unknown_profile` | 2 | The API serves no profile with that name. | Use a profile the API lists. |
| `unauthenticated` | 2 | The API key is missing, unknown or revoked. | Check the `ASSURE_API_KEY` secret, or ask Symbolia for a new key. |
| `rate_limited` | 3 | Too many checks in a minute or a day. The Action waits once for a wait of up to 60 seconds. | Run again later. |
| `credit_exhausted` | 3 | The account's free credit is spent. | Contact Symbolia. |
| `server_busy` | 3 | The API's queue stayed full after three attempts. | Run again in a minute. |
| `api_unreachable` | 3 | The runner could not reach the API after three attempts. | Check outbound HTTPS from the runner to `api.symbolia.ai`. |
| `api_error` | 3 | The API answered in a way the Action does not accept, after three attempts where a retry applies. | Run again later. If it repeats, report the check id to Symbolia. |
| `engine_digest_mismatch` | 3 | The server's engine does not match its pin, so it runs no check. | Report it to Symbolia. |
| `not_found` | 3 | The API holds no check with that id for this account. | Run the check again. |
| `collector_cannot_connect` | 3 | The first query could not reach the database, or `psql` is missing. | Check the secret, the network path from the runner and `pg_hba.conf`. Install `postgresql-client`. |
| `collector_refused` | 3 | The collector refused the collection. Some refusals come before it reads anything: the role is too broad (a superuser, or a member of `pg_monitor` or `pg_stat_scan_tables`; the reason says what to grant), the major is outside 14 to 18, or the role name does not match (behind a connection pooler, the reason says which name to set as `collection-role`; section 6). Others come after it has read: its self-check found a withheld secret value in its own output. The Action also refuses in the runner when a collection mixes this collector's output with the earlier collector's; when files from the earlier collector hold a whole `pg_hba.conf` rule (a quoted name, an `@file` list or a regular-expression user) or `postgresql.conf` setting line that collector withheld; and when a file holds a line the collector withheld but its `COLLECTION-SIDECAR.json` is missing or has no record of that file, or its `REDACTION-MANIFEST.json` is missing, records a different digest for that file, or disagrees with the sidecar. The reason names the file, the lines and the collector's reason, never a line's text. In every refusal it keeps no collected data, and nothing is sent. | Read the reason. For a role refusal, recreate the collection role as in section 2. For a missing or mismatched `COLLECTION-SIDECAR.json` or `REDACTION-MANIFEST.json`, give `raw/`, the sidecar and the manifest from one collector run as it wrote them (section 9). For a withheld `pg_hba.conf` rule in the earlier collector's files: collect again with this Action. If you cannot: remove quotes a name does not need, write an `@file` list's names inline, use a `+group` role in place of a list, or list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted. |
| `profile_not_servable` | 3 | The server holds no qualified checker for this profile. | Use a served profile. |
| `profile_refused` | 3 | The checker refused the collected input with a stated reason, for example because the major version was not observed. | Read the reason. Check that collection completed. |
| `checker_error` | 3 | The checker failed in an unexpected way, for example a crash. A check the server restarted during also reads `checker_error`; its reason says to submit it again. | Report the check id to Symbolia, or submit the check again when the reason says so. |
| `checker_timeout` | 3 | The check ran longer than its time cap, or did not finish within 300 seconds of waiting. | Run again. If it repeats, report the check id to Symbolia. |

A collection with gaps is still a verdict. Each gap reads **not observed** with the place it was looked for.

`tier_excludes` never ends a job. With `report: true`, it means your account's tier does not include the report: the verdict, its summary and its exit stand, and the summary says the report was withheld. Leave `report` off, or ask Symbolia about a tier that includes the report.

`allowance_exhausted` never ends a job either. With `report: true`, it means your plan's report allowance is not set or is spent for the month, and nothing pays for the report: the verdict, its summary and its exit stand, and the summary names the USD needed. Set `allow-overage: true`, or ask Symbolia to top up your account. On the free plan, it means your report balance is spent, and the summary says so.

`overage_ceiling` never ends a job: this month's report overage would pass a monthly overage limit set on your account, so the report does not run, even with `allow-overage`. `job_ceiling` never ends a job: the report's quote is above your account's job ceiling, so the report does not run, even with `allow-overage`; the summary names the quote and the ceiling. `daily_report_cap` never ends a job: your account has had its reports for the day (UTC). Nothing runs and nothing is charged for any of them.

## 11. Profiles

- `postgresql-declared-model` checks your server against a declaration you supply in `raw/declaration.json` (and optionally `raw/clients.json`). It needs `artefacts`: the collector does not write a declaration, so with `connection` this profile reads `bad_input` for the missing `raw/declaration.json`. Collect first, add your declaration under `raw/`, then run with `artefacts`.
- `postgresql-observed-baseline` reads your server and compares it with observed facts and pinned public baselines. You declare nothing.
- `http-observed-baseline` reads the response heads you captured for the HTTP endpoints you select (section 12).

What each profile claims, and what it does not, is in [SCOPE.md](SCOPE.md) and, for `http-observed-baseline`, in section 12. What is collected and where it goes is in [DATA.md](DATA.md).

## 12. Checking HTTP endpoints

`http-observed-baseline` checks one HEAD response per endpoint you select against the HTTP obligations Assure holds (response framing, transport policy, cookies and similar). Live collection against real endpoints is not in this release: the Action reads response heads you captured, offline. `connection` is refused for this profile, before anything is read.

Give the Action an artefacts folder that holds:

- `manifest.json`, with these ten keys exactly: `"schema_version": "http-fixture-001"`, `"mode": "offline_fixture"`, `endpoints`, and the seven flags at the values shown below (`execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation` and `self_approved` false; `simulation` true). Any other key, a missing key or another value makes the Action stop before anything is sent (`MANIFEST-INVALID`). `endpoints` is a list of 1 to 16 objects with exactly these keys: `id` (`endpoint-NNN`, three digits), `scope_token` (a lower-case name you choose, distinct per endpoint), `scheme`, `host`, `port`, `path`, `response_file` (the head file's name in the folder) and `complete` (`true` when you captured the whole head);
- one file per endpoint holding the raw response head as received: the status line and every header line, each ending in CRLF, and the empty line that ends the head.

A complete `manifest.json` for two endpoints:

```json
{
  "schema_version": "http-fixture-001",
  "mode": "offline_fixture",
  "endpoints": [
    {"id": "endpoint-001", "scope_token": "checkout", "scheme": "https", "host": "shop.example.test", "port": 443,
     "path": "/checkout", "response_file": "head-001.txt", "complete": true},
    {"id": "endpoint-002", "scope_token": "login", "scheme": "https", "host": "shop.example.test", "port": 443,
     "path": "/login", "response_file": "head-002.txt", "complete": true}
  ],
  "execution_authorized": false,
  "hardware_authorized": false,
  "industrial_release_authorized": false,
  "release_allowed": false,
  "physical_validation": false,
  "simulation": true,
  "self_approved": false
}
```

```yaml
      - name: Assure check
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: http-observed-baseline
          artefacts: http-fixture
```

The inputs: `profile: http-observed-baseline`; `artefacts`, the folder above. `scope` is optional: a JSON file listing the endpoint ids to check, which must name exactly the manifest's ids (the Action stops before collecting otherwise). Leave `scope-binding` unset so the Action produces it: before collection it runs the identity producer and then the collector over your manifest, and sends their record as the scope binding with the endpoint tokens. `identity-key` stays `pipe`, its default: the Action makes a fresh key for each job and passes it on a pipe, so no key is an input, an environment variable or a file.

A `scope` file, when you give one, is a JSON list of the manifest's ids, for example `["endpoint-001", "endpoint-002"]`.

### Capturing the response heads

Capture each head with `curl`, one HEAD request over HTTP/1.1, and write it to the file the manifest names:

```sh
mkdir -p http-fixture
curl -sS --http1.1 -I https://shop.example.test/checkout > http-fixture/head-001.txt
curl -sS --http1.1 -I https://shop.example.test/login > http-fixture/head-002.txt
head -n 1 http-fixture/head-001.txt
```

`-I` sends a HEAD request and writes the head as received, every line ending in CRLF, with the empty line that ends it. `--http1.1` matters: the first line of each head must be an HTTP/1.1 status line, such as `HTTP/1.1 200 OK`. A head whose first line is another version, such as `HTTP/2 200` from a capture without `--http1.1`, or `HTTP/1.0 200 OK` from a server that answers in HTTP/1.0, is recorded as not observed. Without `-L`, `curl` does not follow a redirect, so a `3xx` head is the endpoint's own answer.

Set `complete` to `true` for each head you captured this way.

A complete workflow for the HTTP profile captures the heads in the job. Commit `http-fixture/manifest.json` alone; one step per endpoint runs `curl` and writes that endpoint's head beside it. Every run then checks fresh heads, and no captured head is committed to your repository.

```yaml
name: Assure HTTP

on:
  pull_request:
  push:
    branches:
      - main
  schedule:
    - cron: "17 3 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  http:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Capture the head of /checkout
        run: curl -sS --http1.1 -I https://shop.example.test/checkout > http-fixture/head-001.txt

      - name: Capture the head of /login
        run: curl -sS --http1.1 -I https://shop.example.test/login > http-fixture/head-002.txt

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: http-observed-baseline
          artefacts: http-fixture
          fail-on: fails
          output: assure-verdict.json

      - name: Keep the verdict
        if: always()
        uses: actions/upload-artifact@<full commit sha of the release you trust>
        with:
          name: assure-verdict
          path: ${{ steps.assure.outputs.verdict-path }}
```

Each run is a new check, even when the heads are the same as the last run's, byte for byte: the Action makes a fresh identity key for each job, so the endpoint tokens it sends differ from run to run (section 9).

You can instead commit the captured heads with the manifest and leave out the capture steps. Use this offline route when you must reproduce a check on a fixture that does not change, for example heads you captured once to keep as a record.

Every reading summary carries the profile's three scope notes:

- Readings cover one HEAD request per operator-selected endpoint.
- Evidence freshness and response authenticity are unverified; same-selection replay is not excluded.
- Per-endpoint coverage qualifications are not displayed in this report.

A full read of the two `https` endpoints above has the first line "green: 2 of 2 endpoints observed; 4 of 5 machines read, 1 refused; declared premises: 12; version pins: none; nothing disproven; established: 3 of 12; not established: 6 — top action: collect the facts HTTP-TLS10-NEGOTIATION reads": the TLS machine (M2) is refused with "no usable observed machine premise", because a captured head carries no TLS session. That is a bound of the result, so the run exits 0. For `http://` endpoints M2 reads vacuous and the first line is "green: 2 of 2 endpoints observed; 5 of 5 machines read; declared premises: 12; version pins: none; nothing disproven; established: 3 of 12; not established: 3 — top action: state it in requirements.md". A head that carries both `Content-Length` and `Transfer-Encoding` fails `HTTP-FRAMING-CL-TE`, and under the default `fail-on: fails` the job exits 1, red.

The policy exits are those of section 7: `nothing_disproven` (0, green) when nothing is disproven, whatever endpoints or machines could not be read; `disproven` (1, red) when a reading has a status you fail on; `could_not_look` (3, yellow) when no endpoint was observed or no machine could be read.

## Rules for an agent

When an agent sets up or runs the Action for you, these rules hold for it, as they do for you. Do not fabricate facts, edit redacted evidence, change database permissions to accommodate the checker, or change the pins to conceal a gap. Report the first line and each reading as the summary states it: a missing fact is reported as missing, with the place it was looked for. It shows you every command that changes your server, its files or its roles, and you run it.
