# Quickstart: the Assure GitHub Action

**Served today:** both PostgreSQL profiles. The intent-free profile, `postgresql-observed-baseline`, needs no declaration. `postgresql-declared-model` needs a declaration file in an artefacts directory (section 9).

The Action collects facts about your PostgreSQL server in your own GitHub Actions runner. It sends the collected facts to `api.symbolia.ai` over TLS, with your API key. The check runs on Symbolia's server. The Action writes the verdict the server returns, the job summary and the annotations in your runner.

Supported PostgreSQL majors: 14 to 18. Real-run evidence exists for PostgreSQL 18.

**Not yet checkable with the collector this Action ships:** a `pg_hba.conf` rule with a quoted name, an `@file` list or a regular-expression user (`/^...`) stops the check today with exit 3 (`collector_refused`). PostgreSQL needs quotes around a role or database name with a hyphen or an upper-case letter, so this is not rare. The collector withholds such a rule whole, and Assure cannot read it. The message names the file and the line. What you can do today: remove quotes a name does not need; write an `@file` list's names inline; use a `+group` role in place of a list; list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted.

These refusals go away once you collect with the next collector (RF-28). It keeps such rules as written, and writes any rule or setting it still has to withhold as a marker line that names its own line number and reason. The check then reads that rule or setting as not observed, and the summary lists it as `not observed: <file> line N (<the reason in plain words>)`. This Action version still ships the earlier collector, until the next one is accepted, so today these refusals still happen.

## What is sent, and what is never read

The Action sends the collector's output: catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. What leaves the runner:

- settings and rules as written, without comment text: every comment in your configuration files, including commented-out settings, is replaced in the runner with `# <withheld comment>`, and every line keeps its place. A line PostgreSQL cannot parse (an unclosed quote) becomes `<withheld: a line PostgreSQL cannot parse>`, which the check still counts as a broken line; if the check would read it as a working setting or rule, the Action stops, exits 2 (`bad_input`) and names the file and the line, and you fix the line and run again. A `pg_hba.conf` rule or `postgresql.conf` setting the collector had to withhold whole, such as a rule with a quoted or `@file` name, stops the upload with exit 3 (`collector_refused`): that shape cannot be checked yet with the collector this Action ships. With the next collector (RF-28), such a line is a marker the check reads as not observed, and the summary lists it as `not observed: <file> line N (<reason>)`; a marker whose line number is not its own, or whose reason is not one the collector writes, stops the upload with exit 2 (`bad_input`), and a collection that mixes the two collectors' output stops with exit 3 (`collector_refused`). The collector's record of which lines it withheld (`COLLECTION-SIDECAR.json`) must come with its output, with the `REDACTION-MANIFEST.json` from the same run: without them, a file that holds a withheld line cannot be checked, and the upload stops the same way;
- policy expressions with every string literal withheld: each quoted literal becomes `'<withheld literal N>'` in the runner, and so does each literal in your declaration's `declared_predicate`;
- no secret-bearing value: the collector withholds every one whole before anything is written, and checks its own output for those values.

The job log and the job summary state how many comments and literals were withheld. [DATA.md](DATA.md) lists every item, including what is still sent as written, such as role names and client addresses.

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
```

Rules for this role:

- Create a new role. Use it for nothing else. The checker leaves the collection role out of every reading, so a role your site also uses would hide its own results.
- Grant it only these two roles, or `pg_monitor` alone where they cannot be granted (section 6). The collector refuses to run if the role is a superuser, has `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`, or belongs to any other role.
- Allow it to log in through `pg_hba.conf` from the runner's address.

The collector runs a fixed, published set of `SELECT` queries. It writes nothing to your database. The collector asks for a read-only session. A pooler may not pass the request on. The collector runs only fixed SELECT statements either way.

## 3. Store the connection as a secret

Add a second repository secret:

- Name: `ASSURE_PG_CONNECTION`
- Value: a libpq connection string or URI, for example:

  ```
  host=db.example.internal port=5432 dbname=app user=assure_collector password=<the password> sslmode=verify-full
  ```

The Action passes the connection to `psql` through environment variables. The connection stays in your runner: it is never sent to the API, put on a command line or logged.

## 4. Add the workflow

Create `.github/workflows/assure.yml`:

```yaml
name: Assure

on:
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

This workflow uses the intent-free profile, which needs no declaration. To check against a declaration you write, use `postgresql-declared-model` with collected files (section 9).

The runner must reach your database and `api.symbolia.ai`. For a database on a private network, use a self-hosted runner inside that network with outbound HTTPS.

## 5. Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-key` | none | Your Assure API key. Pass it from a secret. Required. |
| `api-url` | `https://api.symbolia.ai` | The API address. It must use `https://`. |
| `mode` | `api` | `api`: the check runs on the Assure API. |
| `profile` | `postgresql-observed-baseline` | The checker profile to run. |
| `connection` | none | libpq connection string or URI. Pass it from a secret. |
| `artefacts` | none | A directory of collected files. Use this or `connection`, never both. |
| `collection-role` | the user in `connection` | The role's name inside the database. The collector checks it against `current_user`. Set it when a connection pooler's login name differs (section 6). |
| `collection-privileges` | `pg_read_all_settings,pg_read_all_stats` | The roles you granted to the collection role. |
| `data-dir` | none | A path where the runner can read the server's data directory. Used with `connection`. |
| `config-dirs` | none | Directories that hold the server's configuration files outside the data directory, one per line or separated by colons. Used with `connection`. |
| `fail-on` | `fails` | Which statuses fail the job (section 7). The API checks it against the profile and applies it. |
| `allow-partial` | `false` | `true` accepts a run in which some machines could not be read (section 7). Any other word is `bad_input`. |
| `output` | `assure-verdict.json` | Where to write the verdict file. |
| `python` | `python3` | The Python 3.14 interpreter to use. |

## 6. Managed PostgreSQL and configuration files

Some facts live in configuration files: `postgresql.conf` and the files it includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`. The collector finds them through the server's own settings and reads them from the runner's filesystem.

With a connection and no data directory, the runner cannot read those files. This is the usual case for managed PostgreSQL. A reading that needs a fact from a file then reads **not observed**. Where the checker cannot represent the input without the file, as with a missing `pg_hba.conf` or `postgresql.conf`, the readings that use it read **representation**. The client-authentication and TLS obligations are the ones most affected.

To read the files, run the Action on a self-hosted runner that can read them:

- `data-dir`: the server's data directory, as the runner sees it.
- `config-dirs`: directories that hold configuration files outside the data directory. The Debian and Ubuntu packages keep them in `/etc/postgresql/<major>/<cluster>`:

  ```yaml
          data-dir: /var/lib/postgresql/16/main
          config-dirs: /etc/postgresql/16/main
  ```

  Give one directory per line, or separate them with colons. A path that holds a colon cannot be given here.

The collector reads files only inside `data-dir` and `config-dirs`.

### Managed PostgreSQL and connection poolers

Some managed services put a connection pooler in front of the server, and the pooler routes on the login name. Supabase's pooler, for example, takes the login name `assure_collector.<project-ref>`; inside the database the role is `assure_collector`.

- The `user` in `connection` is the login name. Keep it as the service gives it.
- `collection-role` is the role's name inside the database. The collector checks it against `current_user` and `session_user`. When it is not set, it is the user in `connection`.

When the two differ, the Action logs in with the login name and the collector checks the role. If you leave `collection-role` unset behind such a pooler, the collector refuses with `collection_role_mismatch` (`collector_refused`, exit 3), and the reason says which name to set.

On Supabase, the `postgres` role cannot grant `pg_read_all_settings` or `pg_read_all_stats`. Create the role as in section 2, grant `pg_monitor` in their place, and say so in `collection-privileges`:

```sql
GRANT pg_monitor TO assure_collector;
```

```yaml
          connection: ${{ secrets.ASSURE_PG_CONNECTION }}
          collection-role: assure_collector
          collection-privileges: pg_monitor
```

Use the session pooler. Assure has run through Supabase's session pooler on port 5432. The collector runs each query in its own `psql` process, one short session per query; a transaction pooler has not been tested.

The collector asks for a read-only session. A pooler may not pass the request on: through Supabase's session pooler the session was not read-only. The collector runs only fixed SELECT statements either way.

The runner cannot read a managed server's configuration files, so the readings that need them read **not observed** or **representation**, as above.

## 7. The fail-on policy and exit codes

`fail-on` is a comma list of words, or the single word `never`. The Action sends it as you wrote it. The API checks every word against the profile and applies it. A word the profile cannot emit is `bad_input`, and the reason lists the words that profile accepts. `GET /v1/profiles` lists them too.

The words a profile accepts:

- any status the profile can emit except `holds` and `vacuous`;
- `not_collected`: every status the profile uses for a fact it could not read or represent;
- `never`, on its own: readings never fail the job.

| Profile | Statuses you can name | `not_collected` stands for |
|---|---|---|
| `postgresql-declared-model` | `fails`, `representation`, `missing_method`, `missing_premise`, `not_evaluated` | `representation`, `missing_method`, `missing_premise`, `not_evaluated` |
| `postgresql-observed-baseline` | `fails`, `deviates`, `representation`, `missing_method`, `not_observed`, `missing_baseline`, `needs_intent` | `representation`, `missing_method`, `not_observed`, `missing_baseline` |

`needs_intent` is outside `not_collected`: it marks a norm that depends on what the system is for, which is out of scope by design. Name it on its own to fail on it.

Examples:

- `fails` (the default): the job fails when any obligation reads fails.
- `fails,deviates`: the job also fails on a deviation from vendor guidance or from the Assure baseline (observed profile).
- `fails,not_collected`: the job also fails when a needed fact was not collected or could not be represented.
- `never`: readings never fail the job. A typed outcome still does.

The Action exits with the verdict's own policy exit, `policy.exit` in the verdict file. `policy.reason` says why, in one word. The job summary states the policy and this run's exit in plain words.

| Code | `policy.reason` | Meaning |
|---|---|---|
| 0 | `policy_met` | A verdict was written, and no reading has a status you fail on. |
| 0 | `never` | A verdict was written, and `fail-on` is `never`. |
| 1 | `policy_failed` | A reading has a status you fail on. |
| 2 | | Bad input. Fix the inputs or files. |
| 3 | `no_verdict` | Nothing was checked: no reading is a verdict, and no reading has a status you fail on. |
| 3 | `input_integrity` | Nothing was checked: the input-integrity gate stopped the check. |
| 3 | `machines_refused` | Some machines could not be read, and `allow-partial` is not `true`. The readings cover only the machines that were read. |
| 3 | `scope_refused` | Part of the selected scope (for example an endpoint) was not observed, and `allow-partial` is not `true`. Both PostgreSQL profiles check machines, so they never give this reason. |
| 3 | | A typed outcome. The failure file holds the reason and what to do. |

A failed policy wins over no verdict: when a reading has a status you fail on, the exit is 1 even if no reading is a verdict, and even if some machines could not be read. The input-integrity gate gives 3 under every policy except `never`.

A vacuous reading only says that a domain was empty. A run whose only verdicts are vacuous reads "No verdicts" and the job stops with exit 3.

The first line of the job summary, and the Action's last log line, say how many machines were read and how many could not be read, for example "5 of 8 machines read, 3 refused", or "No machine could be read". The count is out of every machine the profile checks: a machine that gave no reading at all is listed as refused with the reason "no readings for this machine". When Assure worked the list out from the readings because the checker did not report it, the line ends "(inferred)", for example "8 of 8 machines read, none refused (inferred)". The summary lists each machine that could not be read with the checker's reason. The claim of a check is about the whole system, so by default a run in which machines were refused exits 3. If you accept a partial read, set `allow-partial: true`: such a run then exits 0 when no reading has a status you fail on.

If the checker itself fails, the result is the typed outcome `checker_error` (exit 3) under every policy, `never` included. A check is charged once the checker has started, whatever its result, `checker_error` and `checker_timeout` included. One failure is not charged: the checker's own internal error, a `checker_error` whose `detail.rule` is `internal_error`. A request refused before the checker starts is never charged, and neither is a check cut short by a server restart; it still counts against your rate limits. A result is returned whenever one can be produced: when the checker's output for one machine is malformed, that machine is listed under "Machines not read" with its reason (`malformed_output: ...`, or `server_fault: ...` when the server could not write it) and the other machines keep their readings. When no result can be produced, the failure's `detail.malformation` says what was malformed: a fixed kind, the file, the line, the field and the expected form, never your text.

The Action sets three outputs: `verdict-path`, `outcome` and `exit-code`.

## 8. Where the results appear

- **The verdict file.** JSON at the `output` path, schema `assure.serve.verdict/v1`. It holds every reading with its premises. See [VERDICTS.md](VERDICTS.md).
- **The job summary.** A table of counts by status, then one line per obligation. It appears on the run page.
- **Annotations.** Each `fails` reading is an error annotation. Each `deviates` reading is a warning annotation. At most 50 appear.

When no obligation reaches a verdict, the summary headline reads "No verdicts" and the job stops with exit 3. That means nothing could be checked. It never means "no issues".

Text from the checker or your files is shown as plain text. A web address in it appears as code, never as a link.

## 9. Using collected files instead of a connection

You can collect on one machine and check from another. Set `artefacts` to a directory that holds a `raw/` folder (or to the `raw/` folder itself). Leave `connection` empty.

The directory must hold files under the names the profile reads. The API lists them for each profile (`GET /v1/profiles`). Files with other names stay in the runner and are listed in a notice. A symbolic link at an expected name is refused.

Give the collector's output directory as it wrote it. The collector writes `raw/` and, beside it, `COLLECTION-SIDECAR.json` and `TIMING.json`. The Action takes those two files from beside `raw/` (or from inside `raw/`, if you moved them there) and sends them as `raw/COLLECTION-SIDECAR.json` and `raw/TIMING.json`. If both places hold a copy and the copies differ, the Action stops with `bad_input`. Do not leave out `COLLECTION-SIDECAR.json`: it is the collector's record of which lines it withheld whole and why. A configuration file that holds a line the collector withheld (`# [collect_pg: line withheld, ...]`) cannot be checked without it, so the Action stops with `collector_refused` and sends nothing: a collector output without its sidecar cannot be checked.

Keep `REDACTION-MANIFEST.json` too. The collector writes it beside `raw/` in the same run as the sidecar. It records the digest of each file as the collector wrote it, and what the collector withheld. When a file holds a withheld line, the Action uses it in the runner to check that the sidecar belongs to these files: the file must be unchanged since collection, and the manifest and the sidecar must record the same withheld lines. If the manifest is missing, records a different digest for such a file, or disagrees with the sidecar, the Action stops with `collector_refused` and sends nothing. Records from another run are caught only when a file that holds a withheld line differs, byte for byte, from that run's file. Records kept from an earlier run of the same server pass if the withheld lines sit at the same places with the same marker, even where a line that was a comment is now a rule. So always use the sidecar and manifest written by the same collector run as `raw/`. The manifest stays in your runner; it is never sent. With the next collector (RF-28), a withheld rule or setting is a marker line that names its own line number and reason, so records from another run cannot hide it: the check reads that line as not observed whatever the records say. That collector's sidecar is recognised by its own fields; a collection that mixes its output with the earlier collector's stops with `collector_refused`.

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

## 10. Typed outcomes

When the Action cannot produce a verdict, it writes a failure file at the `output` path (schema `assure.serve.failure/v1`) with `outcome`, `reason` and `action`. It also writes the reason to the job summary and one error annotation. When the API gave a check id, the failure file carries it.

| Outcome | Exit | What it means | What to do |
|---|---|---|---|
| `bad_input` | 2 | An input is missing or malformed, a required file is absent, both `connection` and `artefacts` were set, `api-key` is missing, or `api-url` is not `https://`. | Read the reason and fix the input. |
| `oversize_input` | 2 | A file, the file count or the total size is over the limit. | Remove files the profile does not read. Limits: 4 MiB per file, 64 files, 8 MiB in total. |
| `unknown_profile` | 2 | The API serves no profile with that name. | Use a profile the API lists. |
| `unauthenticated` | 3 | The API key is missing, unknown or revoked. | Check the `ASSURE_API_KEY` secret, or ask Symbolia for a new key. |
| `rate_limited` | 3 | Too many checks in a minute or a day. The Action waits once for a wait of up to 60 seconds. | Run again later. |
| `credit_exhausted` | 3 | The account's free credit is spent. | Contact Symbolia. |
| `server_busy` | 3 | The API's queue stayed full after three attempts. | Run again in a minute. |
| `api_unreachable` | 3 | The runner could not reach the API after three attempts. | Check outbound HTTPS from the runner to `api.symbolia.ai`. |
| `api_error` | 3 | The API answered in a way the Action does not accept, after three attempts where a retry applies. | Run again later. If it repeats, report the check id to Symbolia. |
| `engine_digest_mismatch` | 3 | The server's engine does not match its pin, so it runs no check. | Report it to Symbolia. |
| `not_found` | 3 | The API holds no check with that id for this account. | Run the check again. |
| `collector_cannot_connect` | 3 | The first query could not reach the database, or `psql` is missing. | Check the secret, the network path from the runner and `pg_hba.conf`. Install `postgresql-client`. |
| `collector_refused` | 3 | The collector refused the collection. Some refusals come before it reads anything: the role is too broad, the major is outside 14 to 18, or the role name does not match (behind a connection pooler, the reason says which name to set as `collection-role`; section 6). Others come after it has read: its self-check found a withheld secret value in its own output. The Action also refuses in the runner when the collector withheld a whole `pg_hba.conf` rule (a quoted name, an `@file` list or a regular-expression user) or `postgresql.conf` setting line, which cannot be checked yet, and when a file holds a line the collector withheld but its `COLLECTION-SIDECAR.json` is missing or has no record of that file, or its `REDACTION-MANIFEST.json` is missing, records a different digest for that file, or disagrees with the sidecar; the reason names the file, the lines and the collector's reason, never a line's text. In every refusal it keeps no collected data, and nothing is sent. With the next collector (RF-28) the withheld-rule refusals go away (the line reads as not observed), and a collection that mixes the two collectors' output is refused instead. | Read the reason. For a role refusal, recreate the collection role as in section 2. For a missing or mismatched `COLLECTION-SIDECAR.json` or `REDACTION-MANIFEST.json`, give `raw/`, the sidecar and the manifest from one collector run as it wrote them (section 9). For a withheld `pg_hba.conf` rule: remove quotes a name does not need, write an `@file` list's names inline, use a `+group` role in place of a list, or list a regular-expression user's roles by name. Otherwise, send Symbolia the file name and the line number through your Symbolia contact, so the shape is counted. |
| `profile_not_servable` | 3 | The server holds no qualified checker for this profile. | Use a served profile. |
| `profile_refused` | 3 | The checker refused the collected input with a stated reason, for example because the major version was not observed. | Read the reason. Check that collection completed. |
| `checker_error` | 3 | The checker failed in an unexpected way, for example a crash. A check the server restarted during also reads `checker_error`; its reason says to submit it again. | Report the check id to Symbolia, or submit the check again when the reason says so. |
| `checker_timeout` | 3 | The check ran longer than its time cap, or did not finish within 300 seconds of waiting. | Run again. If it repeats, report the check id to Symbolia. |

A collection with gaps is still a verdict. Each gap reads **not observed** with the place it was looked for.

## 11. Profiles

- `postgresql-declared-model` checks your server against a declaration you supply in `raw/declaration.json` (and optionally `raw/clients.json`). It needs `artefacts`: the collector does not write a declaration, so with `connection` this profile reads `bad_input` for the missing `raw/declaration.json`. Collect first, add your declaration under `raw/`, then run with `artefacts`.
- `postgresql-observed-baseline` reads your server and compares it with observed facts and pinned public baselines. You declare nothing.

What either profile claims, and what it does not, is in [SCOPE.md](SCOPE.md). What is collected and where it goes is in [DATA.md](DATA.md).
