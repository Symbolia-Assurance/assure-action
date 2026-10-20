---
name: assure
description: Set up Assure on a GitHub repository so every pull request is checked. Assure checks the software your code runs on. One workflow file, no key to store.
---

# Assure

Assure checks the software your code runs on. Set it up once and every pull request gets a comment: what the change breaks, what still holds, and what was not checked yet.

Five steps, in order.

## 1. Detect the stack

Read the repository and pick one check:

- **A Flask, FastAPI or Django app:** the sign-in check, `python-auth-declared-model`. Free. It reads your code as text and never runs it.
- **A PostgreSQL database the app uses:** `postgresql-observed-baseline`, from a connection or a CI database.
- **Both:** start with Flask. Add the database once the first check is in.

MySQL and HTTP heads: see the references. Standard-library http.server: the same check with a declaration you write (references/python.md). On Supabase, the role the collector needs cannot be granted (references/postgres.md, section 2). So this Action version cannot collect from a Supabase database.

## 2. Ask the person only what only they can answer

One question each, with its tradeoff. With no answer, leave that part out.

- **Let GitHub Actions open pull requests?** Settings, Actions, General: "Allow GitHub Actions to create and approve pull requests". Yes: Assure opens one pull request with the rules it drafted, and merging it accepts them. No: Assure pushes its proposal to a branch and prints a link; one click opens the pull request (once #3238 ships), and checks still run.
- **PostgreSQL only: the connection.** They create a read-only role and store the connection as the secret `ASSURE_PG_CONNECTION` (references/postgres.md, sections 2 and 3). Show each command; they run it. Yes: Assure reads settings, roles and policies, never table contents. No: check the CI database, or skip the database.
- **The report (on by default on the free plan while the free balance lasts).** Yes: leave `report` unset on the free plan, or add `report: true` on a paid plan; a model writes a plain-language report from each verdict, paid from the free report balance, and it leads the pull request comment. `report: false` turns it off. No: no report is written; unmatched requirement lines still go to Claude Haiku (`compile-requirements`, see DATA.md).
- **Check your own rules?** Yes: add `requirements: requirements.md`; Assure sends the file's text with each check and reports on each rule by name (kept 30 days). No: only Assure's built-in checks run.

Ask nothing else. Sign-in uses the workflow's GitHub identity, so there is no key, and the account is free.

## 3. Write `.github/workflows/assure.yml`

Use the block for your stack. Change `main` if the default branch has another name. Never give the Assure job the name of a required status check: a green Assure job would stand in for that check.

Flask. The job proposes Assure's first pull request, so it needs `contents: write`; once that is merged, set `contents: read`.

```yaml
name: Assure

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  assure:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
      pull-requests: write
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0

      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.14"

      - uses: Symbolia-Assurance/assure-action@beta
        with:
          profile: python-auth-declared-model
          # requirements: requirements.md   # if they said yes
```

PostgreSQL, from a connection. It proposes nothing, so `contents: read`:

```yaml
name: Assure

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  assure:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      pull-requests: write
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0

      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.14"

      - name: Install the PostgreSQL client
        run: command -v psql || (sudo apt-get update && sudo apt-get install -y postgresql-client)

      - uses: Symbolia-Assurance/assure-action@beta
        with:
          profile: postgresql-observed-baseline
          connection: ${{ secrets.ASSURE_PG_CONNECTION }}
          collection-role: assure_collector
          # requirements: requirements.md   # if they said yes
```

The runner must reach the database. A private database: by default, the one your migrations build in CI (references/postgres.md, section 4), or collect it and pass the folder as `artefacts` in place of `connection` (references/postgres-local.md).

If the repository requires SHA pins, pin the commit `@beta` resolves to. This prints it:

```sh
gh api repos/Symbolia-Assurance/assure-action/branches/beta -q .commit.sha
```

Today that line reads:

```yaml
      - uses: Symbolia-Assurance/assure-action@384f83abeaf5a1daf17465d9c0b871ef09388ed9 # v0.1.0-beta.41
```

## 4. Push it, then merge Assure's pull request

Push the file to the default branch, or open a pull request with it if the branch is protected.

For a proposal, the job needs `actions/checkout` before the Assure step. The Flask job's first run opens `Assure: proposed intent — review and merge to accept`. GitHub may hold its check until someone clicks **Approve and run** on it; ask the person to. Go through the draft with them, fix what is wrong on its branch, and merge it.

| Omitted | Default |
|---|---|
| `app_roots` | repo root |
| `guards` | none: yellow |
| `session_identity_key` | AUTH-3/4/5 not established |

## 5. Every pull request gets a comment

Success: the next pull request gets a comment from Assure, headed "Assure: N rules broken by this change".

If a run stops, read the first line of its job summary.

- **Red:** a rule this change breaks.
- **Yellow:** Assure could not read part of the app or the setup. If the line names the setup (a permission, the connection, the role), fix that and push again. If it names your code, that is Assure's gap: do not rewrite working code or silence the job. Send the summary's first line as feedback (references/feedback.md) and tell the person.

Never commit `mode: lint`: a lint run checks nothing. Never store a key or guess a commit.

## References

- [references/flask.md](references/flask.md): Flask.
- [references/postgres.md](references/postgres.md): PostgreSQL from a connection.
- [references/postgres-local.md](references/postgres-local.md): PostgreSQL from collected files.
- [references/http.md](references/http.md): HTTP heads.
- [references/mysql.md](references/mysql.md): MySQL.
- [references/python.md](references/python.md): Python and declaration review.
- [references/running.md](references/running.md): pins, keys, inputs.
- [references/results.md](references/results.md): results and exit codes.
- [references/feedback.md](references/feedback.md): feedback.
- [references/agent.md](references/agent.md): rules for an agent.
