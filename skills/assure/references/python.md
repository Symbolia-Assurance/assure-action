# Route 5: a Python (Flask) repository

## 14. Checking a Python (Flask) repository

`python-auth-declared-model` checks how a Flask app signs people in and guards its routes. It reads your code as text and never runs it. The check is free and contacts no server of yours.

A whole workflow. It grants `id-token: write` so the Action signs in with your workflow's GitHub identity and you store no key, and `contents: write` and `pull-requests: write` so the Action can open its proposal (below). Set `profile`; leave `artefacts` and `connection` empty:

```yaml
name: Assure

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: write
  id-token: write
  pull-requests: write

jobs:
  assure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@beta
        with:
          profile: python-auth-declared-model

      - name: Keep the verdict
        if: always()
        uses: actions/upload-artifact@<full commit sha of the release you trust>
        with:
          name: assure-verdict
          path: ${{ steps.assure.outputs.verdict-path }}
```

The Action reads the checked-out repository: its tracked Python files and `requirements.md`, at most 2000 Python files of 512 KiB each, within 2048 upload entries including manifests and an 8 MiB encoded request body. It writes `raw/REPOSITORY.json` (each file's bytes, sha256 and git mode, the commit and the tree id) itself.

**The declaration arrives as a proposal.** The check reads your app against a declaration at `.assure/declaration.json`: your app objects, the session key that means "signed in", your guard decorators, the views that sign people in, raise privilege and sign out, and the routes that are public on purpose. On the first run there is none, so the Action sends the bounded repository bytes to the free declaration proposal route, whose drafter uses the checker's own readers, and runs the check on the returned draft. When the repository's Python files import FastAPI or Django and no other web framework, the Action asks the route for that stack's draft (`stack: python/fastapi` or `python/django`) and the pull request says which stack it was drafted for; any other repository is drafted as Flask, except one whose Python files import none of these frameworks and serve HTTP with the standard library's `http.server`: Assure drafts nothing for it, and the run stops with `bad_input` naming the declaration to write, schema assure.identity.declaration/v1 with `stack` set to `python/stdlib-http` at `.assure/declaration.json` (the API quick start's python-auth-declared-model section lists its fields). A field the bytes do not give remains unread in the proposal for you to review. When your Flask app loads its configuration by name (`from_pyfile`, `from_object`, `from_envvar`) from a file or module the check reads as outside the repository (flaskr's `app.config.from_pyfile("config.py")` with no `instance/config.py`, or `from_envvar`; a `from_pyfile` or `from_object` name that is not a literal is not read, and drafts nothing), the draft proposes `instance_config: "constants-only"` as a field to confirm, read at that call: keep it only if that configuration assigns constants.

Assure never commits to your branches; it opens one pull request proposing each profile's draft at its own path under .assure/; merging it is the acceptance. The pull request, `Assure: proposed intent — review and merge to accept`, comes from Assure's own branch `assure/declaration-proposal` into your base branch (the pull request's base, or your default branch on a push), and changes only the drafts' files: python-auth's `.assure/declaration.json` and `postgresql-declared-model`'s `.assure/postgresql-declared-model.json`, side by side when both profiles run on one repository, its description holding one section per file. Its description and the job summary list each field to confirm with the file and line it was read from. A later run updates the same pull request, keeping the other profile's file, in the shallow checkout `actions/checkout` leaves too; it never opens a second one. Its description opens by naming the file this run is proposing. A branch on an older base tip, or one holding a file its description does not name (a proposal opened before one pull request carried both profiles), is rebuilt from the base branch's tip, carrying over each draft under `.assure/` whose section its description holds (with that section); a file it does not name is left behind.

Which profiles draft intent: `python-auth-declared-model` drafts `.assure/declaration.json`; `postgresql-declared-model` reads the declaration supplied with the run, and drafts one only on its own connection run with no `.assure/declaration.json` in the checkout, proposing it in Assure's pull request (the job summary of a run not bounded by a draft says so in an "Intent" section); `postgresql-observed-baseline` writes its proposal beside the verdict (`assure-declaration-proposal.json`) and, inside a git checkout with a workflow token, proposes it at `.assure/postgresql-declared-model.json` in Assure's pull request; `http-observed-baseline` and `mysql-declared-model` have no intent drafter yet, and the job summary of a run of either that reaches a verdict says so in an "Intent" section: an `http-observed-baseline` check reads only what was observed, a `mysql-declared-model` check reads the declaration supplied with the run.

Read the draft in that pull request. Edit any field that is wrong on its branch. Merge it to accept.

Until the declaration is on your base branch, the result is bounded by the draft. The log says "bounded by an unaccepted declaration draft", the job summary says where the draft is, and the step output `declaration` is `unaccepted-draft`. After the merge, every run reads the accepted file and the bound goes.

GitHub lets the workflow token open a pull request only when the repository allows it: in Settings, Actions, General, tick "Allow GitHub Actions to create and approve pull requests". When the workflow lacks `contents: write` or `pull-requests: write`, that setting is off, or the run is on a pull request from a fork, the check still runs, bounded, and the job summary carries the draft in full with one sentence naming the two permission lines. The summary also carries a **Commit this draft** link: GitHub's prefilled new-file form (`https://github.com/<owner>/<repo>/new/<branch>` with the path and the draft filled in, on the branch the proposal targets: the pull request's base branch, else the repository's default branch), so accepting the draft stays one click with no setting changed. When that branch cannot be read (a push run with no workflow token, or the repository could not be read) or the link would pass 8000 characters, the summary instead names the path at which to commit the draft shown below it. The observed PostgreSQL profile's summary carries such a link only when withholding left its draft unchanged; a draft holding your policy literals gets none, since the summary never shows them.
