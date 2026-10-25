---
name: assure
description: Set up Assure on GitHub: every pull request checked. One workflow, no key to store.
---

# Assure

Assure checks the software your code runs on.

BASE is `https://api.symbolia.ai` unless the person or env variable `ASSURE_API` names another.

## 1. Detect the stack

Pick one check:

- **A Flask, FastAPI or Django app:** the sign-in check, `python-auth-declared-model`. Free; it never runs your code.
- **A PostgreSQL database the app uses:** `postgresql-observed-baseline`, from a connection or a CI database. Committed `.assure/postgresql-declared-model.json` (the merged proposal) or `.assure/declaration.json` adds `postgresql-declared-model`: in `mode: api`, two checks charged. One check: `profile: postgresql-declared-model`, or commit neither. Skip to step 5.
- **Both:** Flask first, then the database.

Standard-library http.server: the same check with a declaration you write (references/python.md). Supabase cannot grant the collector's role. So this Action version cannot collect from a Supabase database.

## 2. Ask, then send the setup draft request

Select Python files, except tests (tests/ and test/ folders, test_x.py, x_test.py, conftest.py), docs/, migrations/, virtual environments and vendored code; dependency files (requirements*.txt at root, files under requirements/, pyproject.toml, lock files, and -r/-c includes from sent requirements files: dependency files only); requirements.md if there is one. Count files and bytes. If the request would pass 6 MiB (base64 adds a third), send nothing; after consent below, use the fallback.

LIST: routes with no sign-in guard (method, path). Ask the person once:

```text
Send N files (X KB) to BASE? This includes dependency files, including nested requirements files. Later sends follow DATA.md: source, intent, records, default report, and whole Django/FastAPI lock files, only where your versions are pinned (names, versions, hashes). Public: LIST; other routes need sign-in. One yes covers sending, setup and its pull request. Yes, or edit LIST?
```

No: send nothing; leave an unsent local draft and push no sending workflow. Yes: POST this JSON to BASE/v1/setup, with no key. Tool asks to approve? [Approving](references/agent.md#approving-a-request-in-your-tool). For FastAPI or Django, add the key stack, python/fastapi or python/django. At most 10 calls a minute from one address.

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

If setup.requirements is null, keep existing requirements.md. Add `report: true` (default on; `report: false` opts out), and `api-url` with BASE if BASE is not the default. `requirements: none` stops the separate field, not tracked root requirements.md in the Python bundle ([DATA.md](DATA.md)). Change `main` for another default branch. Never give the Assure job the name of a required status check.

## 4. Open the pull request

Ask nothing more. Set declaration.public_routes to the union of LIST, with the person's edits, and the draft's public_routes minus routes the person removed from LIST; in the pull request body, list each route that only one of the two names, and which, and name each removed drafted route as not applied. Each to_confirm row is applied by default (CONFIG: keep as drafted); list its method, path and note in the pull request body. Do not ask about requirements.md: the Action reads the repository-root `requirements.md` by default; one notice names a root file it cannot send.

Commit on a new branch; open a pull request with your own GitHub access. No repository setting changes. Fix confirm fields at sources' file:line. After the first Assure comment, return its first line and pull request link; stop. Never merge: the person reviews and merges.

| Omitted | Default |
|---|---|
| `app_roots` | repo root |
| `guards` | none: yellow |
| `session_identity_key` | AUTH-3/4/5 not established |

## 5. PostgreSQL: ask for the connection

- **PostgreSQL only: the connection.** Show the read-only role and `ASSURE_PG_CONNECTION` commands (references/postgres.md, sections 2 and 3); they run them. Yes: read settings, roles and policies, never table contents. No: use CI or skip it.

Use references/postgres.md, section 4; open its pull request (step 4). For a private database, prefer the one migrations build in CI or collect it and pass the folder as `artefacts` in place of `connection` (references/postgres-local.md).

Ask nothing else. Use GitHub identity: no key. For SHA pins, pin the commit `@v0` resolves to (references/running.md).

## 6. Every pull request gets a comment

Success: the next pull request gets a comment from Assure, headed "Assure: N rules broken by this change".

If a run stops, read the first line of its job summary.

- **Red:** a rule this change breaks.
- **Yellow:** fix an unread setup and push again. Unread app code is Assure's gap: do not rewrite working code or silence the job. At most one more question: every gap of that run in one message, with the coverage note (references/agent.md). Send the summary's first line as feedback (references/feedback.md) on a yes, and tell the person.

Never commit `mode: lint`: a lint run checks nothing. Never store a key or guess a commit.

## Fallback: the setup draft is not served

Use it after a 404 (`not_found`) from POST /v1/setup or files over its limit, only after the data yes in step 2. Without app_roots, the first run sends all tracked Python, root requirements.md, records, Django/FastAPI pins and Flask's non-lock dependency files (DATA.md). Keep LIST. After data yes, ask about workflow permission:

- **Let GitHub Actions open pull requests?** Ask only when Settings, Actions, General: "Allow GitHub Actions to create and approve pull requests" is off, read with `gh api repos/{owner}/{repo}/actions/permissions/workflow`. Yes: turn it on with `gh api -X PUT repos/{owner}/{repo}/actions/permissions/workflow -F can_approve_pull_request_reviews=true`; Assure opens it. No: the job summary carries the drafts and a Commit this draft link instead, and checks still run.

This is GitHub permission, not data consent. A data no permits no sending workflow. After a data yes, push this workflow; once merged, set `contents: read`.

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
      - uses: Symbolia-Assurance/assure-action@v0
        with:
          profile: python-auth-declared-model
          report: true
          # requirements: requirements.md   # the default
```

If permitted, the first run opens `Assure: proposed intent — review and merge to accept`; else the summary draft. Name **Approve and run** (Conversation tab) as a human action. After the first Assure comment, return the pull request link and first line, then stop. Never merge: they review and merge.

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
- [feedback.md](references/feedback.md): one JSON object, or a JSON list of up to 10 objects
- [references/coverage.md](references/coverage.md)
- [agent.md](references/agent.md)
