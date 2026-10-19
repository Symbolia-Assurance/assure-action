# Assure GitHub Action: first run on one page

This page gets a first run to a verdict. The full reference is [QUICKSTART-ACTION.md](QUICKSTART-ACTION.md).

## 1. Get an API key

The Action can get one for each run itself, and you store nothing. The workflow in step 4 gives the job `id-token: write` under `permissions:`, with `contents: read` beside it. The Action then signs in with the workflow's GitHub identity and gets a key for that run only.

### Or store a key from Symbolia

Ask Symbolia for a key. It starts with `asr_`, and you receive it once. In your repository, open **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `ASSURE_API_KEY`
- Value: the key.

Then add `api-key: ${{ secrets.ASSURE_API_KEY }}` under `with:` in step 4. A key you pass is used, and the Action does not ask GitHub for an identity token.

## 2. Create the collection role

The Action connects as a role you create for it. Run this as a superuser or a role that can create roles:

```sql
CREATE ROLE assure_collector LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD '<choose a long random password>';
GRANT pg_read_all_settings, pg_read_all_stats TO assure_collector;
GRANT CONNECT ON DATABASE <your database> TO assure_collector;
```

`<your database>` is the name of the database to check, or `postgres` for a local server that holds no other database. Use the role for nothing else, and grant it only those two roles. The collector refuses a broader role.

Then allow the role to log in from the runner. Add a line to `pg_hba.conf` and reload the server:

```
host  <your database>  assure_collector  <the runner's address>/32  scram-sha-256
```

## 3. Store the connection as a secret

Add a second repository secret, `ASSURE_PG_CONNECTION`, holding a libpq connection string, for example:

```
host=db.example.internal port=5432 dbname=app user=assure_collector password=<the password> sslmode=require
```

Test it from the runner first. It must print `assure_collector`:

```
psql 'host=db.example.internal port=5432 dbname=app user=assure_collector sslmode=require' -c 'SELECT current_user'
```

The connection stays in your runner. It is never sent to the API, put on a command line or logged.

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

permissions:
  contents: read
  id-token: write

jobs:
  assure:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Install the PostgreSQL client
        run: command -v psql || (sudo apt-get update && sudo apt-get install -y postgresql-client)

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@beta
        with:
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

Use `@beta` on the `Symbolia-Assurance/assure-action` line. It moves to each new release when Symbolia publishes, so you get fixes without editing your workflow. To freeze, pin a full 40-character commit SHA of `Symbolia-Assurance/assure-action` in place of `@beta`; in a clone, `git -C assure-action rev-parse HEAD` prints it. If your repository requires SHA pins, pin the commit that `@beta` resolves to; `gh api repos/Symbolia-Assurance/assure-action/branches/beta -q .commit.sha` prints it. Pin every third-party action to the full commit SHA of the release you trust.

The `source:` line of `skills/assure/VERSION` names another commit: the Assure source commit the Action was built from. It is not a commit of the Action repository, so it never goes in a `uses:` line.

Change `main` if your default branch has another name. A pull request from a fork gets no identity token and no repository secrets from GitHub, so the Action stops there with exit 2.

## 5. Read the verdict

The first line of the job summary, and the Action's last log line, starts with a colour, then says how much was read ("N of 8 machines read, M refused") and the bounds of the result.

- **green** (exit 0): within these bounds, nothing disproven. Green never means more than this.
- **red** (exit 1): something is disproven, and your `fail-on` names it (`fails` by default). Exit 2 is also red: bad input, or an API key that is missing, unknown or revoked. Fix the inputs, the files or the key.
- **yellow** (exit 3): nothing could be read at all, or a typed outcome stopped the check. The failure file holds the reason and what to do.

The summary lists every reading under its status, with its text. The verdict file holds the same readings with their premises, and the workflow uploads it as the `assure-verdict` artifact.

## What is sent

The Action sends the collector's output: catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. Comments in those files and string literals in policy expressions are withheld in the runner, except a setting name written as a standard-quoted `'name'` directly after `current_setting(`, which is sent as written. The collector never reads table contents, password hashes, key material or other sessions' statements. The server deletes the collected facts when the check ends and keeps the verdict for 30 days; on the Premium tier a sealed copy of the collected facts is kept for the formal shadow (see [DATA.md](DATA.md)).

Both data-sending inputs are opt-in: with no inputs the Action asks for no report, so no verdict record goes to a third-party model, and uploads no `requirements.md`; set `report: true` to ask for the report, and name the file in the `requirements` input (for example `requirements: requirements.md`) to send its text. To turn either on, add it under `with:` in step 4:

```yaml
          report: true
          requirements: requirements.md
```

In `mode: api` the Action also sends your repository name and the commit; the server keeps them, and any requirements text you send, with the check for 30 days.

For more detail, see [QUICKSTART-ACTION.md](QUICKSTART-ACTION.md), "What is sent, and what is never read", "6. Managed PostgreSQL and configuration files" (for managed servers, poolers and configuration files) and "7. The fail-on policy and exit codes".
