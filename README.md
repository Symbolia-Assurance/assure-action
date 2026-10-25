# Assure GitHub Action

Assure checks the software your code runs on. From your own GitHub Actions workflow it reads your PostgreSQL server or your site's HTTP responses and tells you, obligation by obligation, what holds, what is disproven, and what it could not establish and why. The check reads green only when nothing it examined is disproven, and the first line of every result says how much it could see.

The Action collects facts in your runner. The check runs on Symbolia's server at `api.symbolia.ai`. The verdict comes back into your runner and, on a pull request, onto the pull request as annotations.

**Install.** Give this to your agent: `skills/assure/SKILL.md`. It knows the supported routes, what the Action needs from your repository, and where it stops.

Assure returns information. What to change is your call; your agents can act on the result directly — every reading carries the obligation, the machine, the evidence and the reason.

**Served today:** five profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory (`raw/declaration.json`) or a connection with `.assure/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe. `mysql-declared-model`: a MySQL server, from a mysql:// connection plus your declaration file (`declaration`), or an artefacts directory holding `raw/submission.json`. `python-auth-declared-model`: a Python (Flask) repository, free, from the checkout in one step; the Action proposes a drafted declaration in a pull request the merge accepts; FastAPI, Django and standard-library http.server repositories with your declaration.

Known-vulnerability scanners check your code against a list of what has broken before. Assure checks whether the way your code meets the foundational software it runs on stays inside a regime that can be shown safe and reliable, and says exactly what it could and could not establish.

Assure is the check that reads green only when nothing it examined is disproven. It tells you the bounds of what it has established, and why it matters. In an age where machines generate code at a volume nobody can read, Assure shows that each change maintains its baseline security and reliability, and stays true to any formalised requirements.

- `postgresql-observed-baseline`: your server against what is observed and pinned public baselines; you declare nothing. From a connection, or from an artefacts directory the collector wrote.
- `postgresql-declared-model`: your server against a declaration you write (`raw/declaration.json`). When the check carried your `requirements.md`, the verdict also carries `requirements`: one row per requirement line, with its `id`, its `sentence` as you wrote it, and one of three states.
- `http-observed-baseline`: the response heads you captured for the endpoints you select, offline; the Action produces the scope binding itself.
- `mysql-declared-model`: a MySQL server, from a `mysql://` connection and your declaration file (`declaration`), or an artefacts directory holding `raw/submission.json`. Seven machines read it, M1 to M4, M6, M7 and M8, and the check contacts no server. Its report is written as for every served profile.

PostgreSQL majors 14 to 18 are supported. Real-run evidence exists for PostgreSQL 17 and 18.

## What a check claims

A green check claims this: within the bounds its first line states, nothing the rules Symbolia holds could check was disproven; every obligation that could not be established is named with what would establish it. The claim covers those rules and those observations, and nothing beyond them. It does not say the database is fit for its purpose.

A run that read nothing never goes green: it is yellow and exits 3. When no obligation on the machines read holds, the first line says "nothing could be established". It never means "no issues".

[SCOPE.md](docs/SCOPE.md) states the claim and its limits in full.

## What leaves your runner

The Action sends catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. Before anything is sent, the collector withholds every secret-bearing value whole, every comment in your configuration files is replaced with `# <withheld comment>`, and every string literal in a policy expression is replaced with `'<withheld literal N>'` (except a setting name written as a standard-quoted `'name'` directly after `current_setting(`, which is sent as written). The collector never reads table contents, password hashes, key material or other sessions' statements. Your connection string and password stay in your runner. The Action sends only the files the profile reads, each within its size limit. The server deletes the collected facts when the check ends and keeps the verdict for 30 days; on Premium, Pro and usage plans a sealed copy of the collected facts is kept for the formal shadow (see [DATA.md](docs/DATA.md)). The report is on by default in `mode: api`: after a verdict the Action asks for it, which sends the verdict record (never your files) through OpenRouter to a model, asking for zero data retention, and `report: false` turns it off; the Action reads the repository-root `requirements.md` by default and sends its text, your own promises; name another file in the `requirements` input, or set `requirements: none` to send none in that separate request field; by default, on every plan, a line of that text that does not match one of the profile's statements word for word also goes to Claude Haiku through OpenRouter, unless an earlier reading of it is kept, drawn from your account's `formalisation` line (with no balance left there, none is sent), and `compile-requirements: false` keeps those lines from it. In `mode: api` the Action sends that text (within 65536 bytes, 256 lines and 8192 bytes per line, from a regular file; a root file that is a symbolic link or beyond them is not sent, and one notice says why), your repository name and the commit (on a pull request, its head commit); the server keeps them with the check for 30 days. Setting `requirements` to `none` stops the separate requirements text and goal-map fields only: the repository and the commit are still sent and kept with the check for 30 days. On the Python profile it does not remove a tracked root `requirements.md` from `raw/repository/requirements.md`; that raw file is still sent to the first declaration proposal and to lint/check submissions under the Python file-selection rules. Naming a different requirements input does not remove that root copy either. [DATA.md](docs/DATA.md) lists every item.

## Quickstart

You need:

- the permission `id-token: write` on the job that runs Assure, so the Action signs in with your workflow's GitHub identity and you store no key; or, instead,
- an Assure API key from Symbolia (it starts with `asr_`), stored as the repository secret `ASSURE_API_KEY`;
- outbound HTTPS from the runner to `api.symbolia.ai` (port 443);
- Python 3.14 on the runner and, to collect over a connection, the PostgreSQL client (`psql`);
- a collection role with read access to settings and statistics only, if you collect over a connection.

Rotate a stored key with `POST /v1/keys/rotate` during its rotation window; a GitHub sign-in key lasts at most an hour and never rotates, and your Symbolia contact revokes stored keys.

The smallest job, for files you collected and committed in `collected/`; put it under `jobs:` in your workflow:

```yaml
  assure:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      pull-requests: write
    steps:
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Assure check
        uses: Symbolia-Assurance/assure-action@v0
        with:
          artefacts: collected
```

Keep `contents: read` beside `id-token: write`: naming one permission sets the others to none. Your Assure account is your GitHub owner, on the free plan the first time it signs in, and each run gets a key that lives for that run only.

On a `pull_request` event the Action also posts the result as one comment on the pull request, "Assure: N rules broken by this change", with what is broken and the fix, what still holds, and what was not checked yet. Its lines are rendered from the verdict with no model, except the report's: when the report is written, the paragraph under the comment's heading and the full report folded below it are a language model's text, written from the verdict's record ([QUICKSTART-ACTION.md](docs/QUICKSTART-ACTION.md#the-report), "The report"). Each later run on the pull request updates the same comment. The Action posts it with the workflow's own token, so the job needs `pull-requests: write` under `permissions:` (keep `contents: read` beside it); the jobs on this page grant it. Without that permission the comment is not posted, the job log carries one notice naming the line to add, and the verdict, the job summary and the exit code are unchanged.

With an API key instead, pass it from a secret. The declared profile reads collected files. Put the collector's output in a directory that holds `raw/`, add your declaration as `raw/declaration.json`, commit the directory, then add these steps. The checkout step puts the directory on the runner; for a directory made by an earlier job, fetch it with `actions/download-artifact` instead.

```yaml
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@v0
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-declared-model
          artefacts: collected
          fail-on: fails
```

Use `@v0` on the `Symbolia-Assurance/assure-action` line. It moves to each new release when Symbolia publishes, so you get fixes without editing your workflow. A moving ref runs what Symbolia last published; every release is first served by production and reviewed before merge, and each release also has an immutable tag `v0.1.N`.

To freeze, pin a full 40-character commit SHA of `Symbolia-Assurance/assure-action` in place of `@v0`; in a clone, `git -C assure-action rev-parse HEAD` prints it. If your repository requires SHA pins, pin the commit that `@v0` resolves to; `gh api repos/Symbolia-Assurance/assure-action/commits/v0 -q .sha` prints it. Pin every third-party action to the full commit SHA of the release you trust. The `source:` line of `skills/assure/VERSION` names another commit: the Assure source commit the Action was built from. It is not a commit of the Action repository, so it never goes in a `uses:` line. The `pin:` line of `skills/assure/VERSION` says the same: the build cannot know which Action commit you pin, so it names none.

`SOURCE-CONTRACT.json` at the top of this repository records the digest of the Assure source the tree was built from, the files that built it and the digest of every file it ships, with its details in `SOURCE-CONTRACT-DETAIL.json`; `DIST-MANIFEST.json` lists each shipped file with its digest and the reason it ships.

The [full quickstart](docs/QUICKSTART-ACTION.md) covers the collection role, collecting over a connection, managed PostgreSQL, running the collector yourself, complete workflow files that run on pull requests and on pushes to your default branch, the HTTP captures, and every typed outcome.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-key` | none | Your Assure API key. Pass it from a secret. Leave it out when the job has `id-token: write` under `permissions:`: the Action then signs in with the workflow's GitHub identity. |
| `api-url` | `https://api.symbolia.ai` | The API address. The published API is `https://` only. Plain `http://` is accepted only for a loopback host (`127.0.0.1`, `::1` or `localhost`), for a local test server. |
| `mode` | `api` | `api`: the check runs on the Assure API. |
| `profile` | `postgresql-observed-baseline` | The checker profile to run. |
| `connection` | none | A libpq connection string or URI. Pass it from a secret. |
| `artefacts` | none | A directory of collected files. Use this or `connection`, never both. |
| `collection-role` | the user in `connection` | The role's name inside the database. Set it when a connection pooler's login name differs. |
| `collection-privileges` | `pg_read_all_settings,pg_read_all_stats` | The roles you granted to the collection role. |
| `data-dir` | none | Where the runner can read the server's data directory. Used with `connection`. |
| `config-dirs` | none | Directories outside the data directory that hold configuration files. Used with `connection`. |
| `fail-on` | `fails` | Which statuses fail the job, or `never`. |
| `requirements` | unset | A requirements file to send with the check, `mode: api` only. Unset, the Action reads the repository-root `requirements.md` by default and sends its text; with no such file it sends none and says nothing, and a root file it cannot send (a symbolic link, beyond the bounds, not UTF-8 text) is not sent: the check runs and one notice says why. A file you name that cannot be sent stops the run with exit 2. `none` sends no requirements text and prints no notice (a file named `none` is then reached as `./none`). Only `none` in lower case is the sentinel: `NONE` names a file, and on a file system that ignores case, such as the default on macOS, a file named `none` answers to it. `mode: local` does not read requirements. The repository and the commit (on a pull request, its head commit) are sent on every `mode: api` run, with `none` too. |
| `report` | unset | The report is on by default in `mode: api`: unset or `report: true` asks for it; `report: false` turns it off. Local mode never asks for one. Reports are written for every served profile; a report that states anything the verdict's record does not hold is withheld. |
| `feedback` | `''` | A deliberate feedback note: one JSON object, or a JSON list of up to 10 objects, as a string or the path of a JSON file your workflow wrote. `mode: api` only; each note is sent once, in order, after the check. |
| `output` | `assure-verdict.json` | Where to write the verdict file. |
| `python` | `python3` | The Python 3.14 interpreter to use. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Green: nothing disproven within the bounds the first line states; or red with exit 0 because your `fail-on` leaves the disproven status out (or is `never`, which still exits 1 on a prove-class obligation that is not proven), and the first line says so. |
| 1 | Red: something is disproven and your `fail-on` stops on it, a prove-class obligation is not proven, a status you chose to stop on was read, or under strict (`fail-on: unresolved-security`) an obligation marked `security: true` is unresolved. |
| 2 | Red: bad input, or an API key that is missing, unknown or revoked. Fix the inputs, the files or the key. With no key, the job needs `id-token: write` under `permissions:`. |
| 3 | Yellow: nothing could be read at all, or a typed outcome stopped the check. The failure file holds the reason and what to do. |

The colour is green, red or yellow. A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. `fail-on: unresolved-security` is the strict preset; it is never the default, and while a profile marks no obligation it changes nothing ("strict: no obligations marked").

The Action sets these outputs: `verdict-path`, `outcome`, `exit-code`, `colour`, `not-established` (how many obligations could not be established), and with the report on also `report-status`, `report-url`, `report-cost-usd`, `report-charge-usd` and `report-allowance-remaining`. On `postgresql-observed-baseline`, when the Action writes `assure-requirements-draft.md`, it also sets `requirements-draft`, that file's path (empty when nothing was drafted).

## What is never charged

Two modes of the Action charge nothing. `mode: lint` collects and checks your files in the runner, then sends them to `POST /v1/lint`, which lists the problems it finds; nothing is charged, but it counts against your rate limits. `mode: local` runs the checker in the runner and sends nothing; it runs only from the Assure source tree, and this published Action refuses it with `bad_input`. From the source tree it also runs as one command, with no `INPUT_*` variables set: `python3 -m action.entry --mode local --artefacts DIR --profile P [--fail-on ...] [--out FILE]`. Each `--<input> VALUE` (or `--<input>=VALUE`) sets the input of that name (`--out` is `output`); an unknown flag, or one with no value, stops with exit 2 naming its `INPUT_` form, and `api-key`, `connection` and `identity-key` are read from the environment only. Deliberate feedback (the `feedback` input) is free on every plan. A check in `mode: api` and its report can be charged: what a check costs is in [section 7 of the full quickstart](docs/QUICKSTART-ACTION.md#7-the-fail-on-policy-and-exit-codes), and what a report costs in [The report](docs/QUICKSTART-ACTION.md#the-report).

## Where the verdict goes

- **The verdict file:** JSON at the `output` path, schema `assure.serve.verdict/v1`, with every reading and its premises. [VERDICTS.md](docs/VERDICTS.md) explains how to read it.
- **The job summary:** the first line (colour, coverage, bounds, finding), one sentence on what it means, then counts by status and one line per obligation (on `postgresql-observed-baseline`, an M6 `deviates` line is followed by the functions it read, one entry per function with its login roles), on the run page. In `mode: api`, after the check the Action reads `GET /v1/usage` (free) and prints one log line naming your plan, for example "Assure: plan Premium (usd_20)". On a plan other than free the job summary and the pull request comment's footer add the plan line, "Plan: Premium (usd_20).", and a checks line; on Premium and Pro it says what `charged: true` means there: the check is counted in your account's checks, except on a Symbolia internal account, whose checks are not counted there, and the free check credit does not limit checks (it is not topped up, and at zero checks still run). On another agreement (`usage`, `enterprise`, `internal`) the checks line gives the count alone, "Checks: N on this account." On the free plan the log line is followed by "Assure: Checks: N on this account; check credit USD C of USD S left.", the pull request comment's footer adds the plan line, "Plan: Free (free).", and that check credit line, and the job summary is unchanged (a free API run's summary still equals the local one). These lines are not in the verdict file, so an API verdict still equals the local one; a server whose usage document names no `tier` adds none of them.
- **Annotations:** the first line is the first notice; each `fails` reading is an error and each `deviates` reading is a warning, up to 50.
- **The ignored line:** one notice, "N name(s) not read by profile P: ...", lists the names under `artefacts` the profile does not read. A file that matches only an optional input and is over that input's byte cap is left out of the bundle and listed there as "NAME: over CAP bytes (optional input)" (a sidecar beside `raw/` as "NAME beside raw/: ..."); the check then runs on the rest, and what comes back depends on the profile. `postgresql-observed-baseline`: a dropped `raw/pg_hba.conf` (cap 1 MiB) gives a verdict, charged, whose first line counts the refused machines; M2, M3 and M4 read `representation: pg_hba.conf absent from raw`, so nothing about authentication rules is established. `postgresql-declared-model`: after a dropped `raw/pg_hba.conf`, the check still runs on the rest against your declaration with no observed HBA rules; M4 and M8 name the missing source in their `source_not_visible` gaps and read `missing_premise`, while the final `verdict` or `no_verdict` and any charge follow the remaining inputs and normal outcome policy. `http-observed-baseline`: a dropped `raw/response-heads/endpoint-NNN.txt` (cap 64 KiB) that the sidecar still lists is refused as an input fault (`UNEXPECTED-ARTEFACT`), not read around. `python-auth-declared-model`: a supplied `raw/REPOSITORY.json` is kept unchanged. If it still lists a dropped repository file, the step stops with `profile_refused` (`input_pin_differs`: `file_absent`, naming the file; exit 3, not charged), and the ignored line is not printed because no verdict came back. Removing its file row without recomputing that supplied manifest's tree does not repair its pin. When no manifest is supplied in `mode: api`, the generated manifest lists only the retained files, so the checked repository excludes the dropped file; the remaining repository and declaration decide the outcome and exit under normal charge policy, and a returned verdict prints the ignored notice. Keep each repository file under the profile's cap (512 KiB for python-auth) or out of the repository you declare. `mysql-declared-model` has no optional input. A required input over its cap still stops the run with `oversize_input` (exit 2).

When the Action cannot produce a verdict, it writes a failure file at the `output` path instead, with the outcome, the reason and what to do.

## Lines the Action prints

Three lines the Action prints to the job log, with their placeholders, so a workflow step or a test can match them without reading the source. `action/entry.py` exports each format as the constant named in the first column.

| Line | Format | Placeholders |
|---|---|---|
| Names not read (`NOTICE_LINE`) | `::notice title=Assure::<count> name(s) not read by profile <profile>: <names>` | `<count>` is how many collected names the profile does not read; `<profile>` is your `profile` input; `<names>` is the first 20 of them, comma separated, then ` and N more` when there are more. Printed only when at least one name was not read. |
| Lint summary (`LINT_LINE`) | `Assure: lint: <reading>; <findings> finding(s); nothing was charged; policy exit <exit>; <output>` | `<reading>` is `ready for a check` or `fix these before a check`; `<findings>` is the number of findings; `<exit>` is 0 or 2; `<output>` is the `output` path the lint record was written to. The last line of a `mode: lint` run. |
| Withheld (`WITHHELD_LINE`) | `Assure: <withheld>` | `<withheld>` is the sentence of counts starting `Withheld in the runner before anything was sent:`, followed by one more sentence starting ` Also:` when expressions, unparseable lines or not-observed lines were also withheld; the same text as the job summary's "Withheld in the runner" section. Printed before anything is sent. |

The order each mode prints these lines in, as `entry.ORDER` in `action/entry.py` names them (`tests/serving/test_issue_1960_accept.py` pins it against a run in each mode). Each is printed only when its condition above holds; other lines, such as the masks, the annotations and the verdict line, can come before, between and after them.

- `mode: api`: `WITHHELD_LINE`, `NOTICE_LINE`
- `mode: local`: `WITHHELD_LINE`, `NOTICE_LINE`
- `mode: lint`: `WITHHELD_LINE`, `NOTICE_LINE`, `LINT_LINE`

The text after `title=Assure::` in the notice and the `<output>` path in the lint summary are printed as workflow-command data: a `%` in them is printed as `%25` and a newline as `%0A`, and the notice's text is cut to 300 characters ending in `…` when a long name list exceeds that.

## Read more

- [Beta tester brief: one page for your first run](docs/BETA-TESTER-BRIEF.md)
- [One-page first run](docs/FIRST-RUN-ACTION.md)
- [Full quickstart](docs/QUICKSTART-ACTION.md)
- [What a verdict claims](docs/SCOPE.md)
- [Reading a verdict](docs/VERDICTS.md)
- [What is collected and where it goes](docs/DATA.md)

## Licence

Elastic License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
