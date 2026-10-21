---
name: assure
description: Set up Assure on a GitHub repository so every pull request is checked. Assure checks the software your code runs on. One workflow file, no key to store.
---

# Assure

Assure checks the software your code runs on. Every pull request gets a comment: what the change breaks, what holds, what was not checked.

BASE is `https://api.symbolia.ai` unless the person or the environment (`ASSURE_API`) names another.

## 1. Detect the stack

Read the repository and pick one check:

- **A Flask, FastAPI or Django app:** the sign-in check, `python-auth-declared-model`. Free; it never runs your code. Steps 2 to 4.
- **A PostgreSQL database the app uses:** `postgresql-observed-baseline`, from a connection or a CI database. Skip to step 5.
- **Both:** Flask first, then the database.

Standard-library http.server: the same check with a declaration you write (references/python.md). On Supabase, the collector's role cannot be granted. So this Action version cannot collect from a Supabase database.

## 2. Ask, then send the setup draft request

Pick the files the drafter reads: Python files, except tests (tests/ and test/ folders, test_x.py, x_test.py, conftest.py), docs/, migrations/, virtual environments and vendored code; the dependency files (requirements.txt, pyproject.toml, lock files); requirements.md if there is one. Count them and their bytes. If the request would pass 6 MiB (base64 adds a third), send nothing: use the fallback.

Ask the person once:

```text
Assure drafts your setup from your app's Python files. Send N files (X KB) to BASE? Nothing else leaves the repo. (DATA.md)
```

No: send nothing; offer the fallback (its first run sends these files from the runner). Yes: POST this JSON to BASE/v1/setup, with no key. For FastAPI or Django, add the key stack, python/fastapi or python/django. At most 10 calls a minute from one address.

```json
{"profile": "python-auth-declared-model",
 "files": {"raw/repository/<path>": "<base64 of the file>"}}
```

A 404 (`not_found`): this server does not serve it; use the fallback at the end.

## 3. Write what comes back

```text
declaration             -> .assure/declaration.json (as JSON)
setup.requirements.text -> setup.requirements.path (requirements.md)
setup.workflow.text     -> setup.workflow.path (.github/workflows/assure.yml)
```

If setup.requirements is null, keep the repository's own requirements.md. Under the Assure step's `with:`, add `report: true` (a plain report of each verdict, DATA.md; on by default in api mode, `report: false` turns it off; requirements.md is read by default, `requirements: none` turns that off), and `api-url` with BASE if BASE is not the default. Change `main` if the default branch has another name. Never give the Assure job the name of a required status check: it would stand in for that check.

## 4. Confirm the public routes, then open the pull request

Show the person one list: declaration.public_routes, each to_confirm row (method, path, note), and every other route you find with no sign-in guard. Ask once:

```text
These routes are public; every other route needs sign-in. Yes, or edit the list?
```

Write their edits into public_routes. Do not ask about requirements.md: the workflow names it.

Commit the three files on a new branch and open a pull request with your own GitHub access (gh pr create). No repository setting changes. Fix any other field confirm lists, at the file and line sources gives. Then merge.

| Omitted | Default |
|---|---|
| `app_roots` | repo root |
| `guards` | none: yellow |
| `session_identity_key` | AUTH-3/4/5 not established |

## 5. PostgreSQL: ask for the connection

- **PostgreSQL only: the connection.** They create a read-only role and store the connection as the secret `ASSURE_PG_CONNECTION` (references/postgres.md, sections 2 and 3). Show each command; they run it. Yes: Assure reads settings, roles and policies, never table contents. No: check the CI database, or skip the database.

Then write the workflow in references/postgres.md, section 4, pinned as the workflow at the end, and open its pull request as in step 4. The runner must reach the database. A private database: by default, the one your migrations build in CI (references/postgres.md, section 4), or collect it and pass the folder as `artefacts` in place of `connection` (references/postgres-local.md).

Ask nothing else. Sign-in uses the workflow's GitHub identity: no key. If the repository requires SHA pins, pin the commit `@beta` resolves to (references/running.md).

## 6. Every pull request gets a comment

Success: the next pull request gets a comment from Assure, headed "Assure: N rules broken by this change".

If a run stops, read the first line of its job summary.

- **Red:** a rule this change breaks.
- **Yellow:** Assure could not read part of the app or the setup. If it names the setup, fix that and push again. If it names your code, that is Assure's gap: do not rewrite working code or silence the job. Ask the contribution question (references/agent.md). Send the summary's first line as feedback (references/feedback.md) on a yes, and tell the person.

Never commit `mode: lint`: a lint run checks nothing. Never store a key or guess a commit.

## Fallback: the setup draft is not served

Use it after a 404 (`not_found`) from POST /v1/setup, a no in step 2, or files over the limit. The job proposes the first pull request (references/python.md, section 14). Ask one more question:

- **Let GitHub Actions open pull requests?** Settings, Actions, General: "Allow GitHub Actions to create and approve pull requests". Yes: Assure opens it. No: the job summary carries the drafts and a Commit this draft link instead, and checks still run.

Push this workflow. It needs `contents: write` to propose; once merged, set `contents: read`.

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
          report: true
          # requirements: requirements.md   # once you have one
```

Its first run opens `Assure: proposed intent — review and merge to accept`. GitHub may hold its check until someone clicks **Approve and run**; ask the person to. Review and merge it as in step 4.

## References

- [flask.md](references/flask.md)
- [postgres.md](references/postgres.md)
- [postgres-local.md](references/postgres-local.md)
- [http.md](references/http.md)
- [mysql.md](references/mysql.md)
- [python.md](references/python.md)
- [adapter-bridge.md](references/adapter-bridge.md)
- [running.md](references/running.md)
- [results.md](references/results.md)
- [feedback.md](references/feedback.md)
- [references/coverage.md](references/coverage.md)
- [agent.md](references/agent.md)
