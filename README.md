# Assure GitHub Action

Assure checks the software your code runs on. From your own GitHub Actions workflow it reads your PostgreSQL server or your site's HTTP responses and tells you, obligation by obligation, what holds, what is disproven, and what it could not establish and why. The check reads green only when nothing it examined is disproven, and the first line of every result says how much it could see.

The Action collects facts in your runner. The check runs on Symbolia's server at `api.symbolia.ai`. The verdict comes back into your runner and, on a pull request, onto the pull request as annotations.

**Install.** Give this to your agent: `skills/assure/SKILL.md`. It knows the supported routes, what the Action needs from your repository, and where it stops. Pin the Action at the commit you fetched this file from. If you prefer to do it by hand, the quickstart below is the same path.

Assure returns information. What to change is your call; your agents can act on the result directly — every reading carries the obligation, the machine, the evidence and the reason.

**Served today:** three profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory with your declaration in `raw/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe.

Known-vulnerability scanners check your code against a list of what has broken before. Assure checks whether the way your code meets the foundational software it runs on stays inside a regime that can be shown safe and reliable, and says exactly what it could and could not establish.

Assure is the check that reads green only when nothing it examined is disproven. It tells you the bounds of what it has established, and why it matters. In an age where machines generate code at a volume nobody can read, Assure shows that each change maintains its baseline security and reliability, and stays true to any formalised requirements.

- `postgresql-observed-baseline`: your server against what is observed and pinned public baselines; you declare nothing. From a connection, or from an artefacts directory the collector wrote.
- `postgresql-declared-model`: your server against a declaration you write (`raw/declaration.json`). When the check carried your `requirements.md`, the verdict also carries `requirements`: one row per requirement line, with its `id`, its `sentence` as you wrote it, and one of three states.
- `http-observed-baseline`: the response heads you captured for the endpoints you select, offline; the Action produces the scope binding itself.

PostgreSQL majors 14 to 18 are supported. Real-run evidence exists for PostgreSQL 17 and 18.

## What a check claims

A green check claims this: within the bounds its first line states, nothing the rules Symbolia holds could check was disproven; every obligation that could not be established is named with what would establish it. The claim covers those rules and those observations, and nothing beyond them. It does not say the database is fit for its purpose.

A run that read nothing never goes green: it is yellow and exits 3. When no obligation on the machines read holds, the first line says "nothing could be established". It never means "no issues".

[SCOPE.md](docs/SCOPE.md) states the claim and its limits in full.

## What leaves your runner

The Action sends catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. Before anything is sent, the collector withholds every secret-bearing value whole, every comment in your configuration files is replaced with `# <withheld comment>`, and every string literal in a policy expression is replaced with `'<withheld literal N>'`. The collector never reads table contents, password hashes, key material or other sessions' statements. Your connection string and password stay in your runner. The Action sends only the files the profile reads, each within its size limit. The server deletes the collected facts when the check ends and keeps the verdict for 30 days. In `mode: api` the Action also sends, by default, the text of the `requirements.md` at your repository root (when it is there and within 65536 bytes, 256 lines and 8192 bytes per line), your repository name and the commit (on a pull request, its head commit); the server keeps them with the check for 30 days. Set the `requirements` input to `none` to send no requirements text. Setting `requirements` to `none` stops the requirements text only: the repository and the commit are still sent and kept with the check for 30 days. [DATA.md](docs/DATA.md) lists every item.

## Quickstart

You need:

- an Assure API key from Symbolia (it starts with `asr_`), stored as the repository secret `ASSURE_API_KEY`;
- outbound HTTPS from the runner to `api.symbolia.ai` (port 443);
- Python 3.14 on the runner and, to collect over a connection, the PostgreSQL client (`psql`);
- a collection role with read access to settings and statistics only, if you collect over a connection.

The declared profile reads collected files. Put the collector's output in a directory that holds `raw/`, add your declaration as `raw/declaration.json`, commit the directory, then add these steps. The checkout step puts the directory on the runner; for a directory made by an earlier job, fetch it with `actions/download-artifact` instead.

```yaml
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-declared-model
          artefacts: collected
          fail-on: fails
```

Pin every `uses:` line to a full 40-character commit SHA. A tag can move; a commit cannot.

Put the commit of `Symbolia-Assurance/assure-action` you fetched this file from, in full, in place of `<full commit sha>`. In a clone, `git -C assure-action rev-parse HEAD` prints it. The `source:` line of `skills/assure/VERSION` names another commit: the Assure source commit the Action was built from. It is not a commit of the Action repository, so it never goes in a `uses:` line. The `pin:` line of `skills/assure/VERSION` says the same: the build cannot know the commit you fetched, so it names none.

`SOURCE-CONTRACT.json` at the top of this repository records the digest of the Assure source the tree was built from, the files that built it and the digest of every file it ships, with its details in `SOURCE-CONTRACT-DETAIL.json`; `DIST-MANIFEST.json` lists each shipped file with its digest and the reason it ships.

The [full quickstart](docs/QUICKSTART-ACTION.md) covers the collection role, collecting over a connection, managed PostgreSQL, running the collector yourself, complete workflow files that run on pull requests and on pushes to your default branch, the HTTP captures, and every typed outcome.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-key` | none | Your Assure API key. Pass it from a secret. Required. |
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
| `requirements` | `requirements.md` at the repository root | A requirements file to send with the check, `mode: api` only. Empty sends the repository root's `requirements.md` when it can be sent; when it cannot (over 65536 bytes, 256 lines or 8192 bytes per line, a symbolic link, not a regular file or not UTF-8), nothing is sent and one notice says why. A file you name that cannot be sent stops the run with exit 2. `none` sends no requirements text and prints no notice (a file named `none` is then reached as `./none`). Only `none` in lower case is the sentinel: `NONE` names a file, and on a file system that ignores case, such as the default on macOS, a file named `none` answers to it. `mode: local` does not read requirements. The repository and the commit (on a pull request, its head commit) are sent on every `mode: api` run, with `none` too. |
| `output` | `assure-verdict.json` | Where to write the verdict file. |
| `python` | `python3` | The Python 3.14 interpreter to use. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Green: nothing disproven within the bounds the first line states; or red with exit 0 because your `fail-on` leaves the disproven status out (or is `never`, which still exits 1 on a prove-class obligation that is not proven), and the first line says so. |
| 1 | Red: something is disproven and your `fail-on` stops on it, a prove-class obligation is not proven, a status you chose to stop on was read, or under strict (`fail-on: unresolved-security`) an obligation marked `security: true` is unresolved. |
| 2 | Red: bad input, or an API key that is missing, unknown or revoked. Fix the inputs, the files or the key. |
| 3 | Yellow: nothing could be read at all, or a typed outcome stopped the check. The failure file holds the reason and what to do. |

The colour is green, red or yellow. A `fails` reading on a read machine is red whatever `fail-on` says. A status you name in `fail-on` also turns the reading red and sets the exit. `fail-on: unresolved-security` is the strict preset; it is never the default, and while a profile marks no obligation it changes nothing ("strict: no obligations marked").

The Action sets these outputs: `verdict-path`, `outcome`, `exit-code`, `colour`, `not-established` (how many obligations could not be established), and with `report: true` also `report-status`, `report-url`, `report-cost-usd`, `report-charge-usd` and `report-allowance-remaining`.

## Where the verdict goes

- **The verdict file:** JSON at the `output` path, schema `assure.serve.verdict/v1`, with every reading and its premises. [VERDICTS.md](docs/VERDICTS.md) explains how to read it.
- **The job summary:** the first line (colour, coverage, bounds, finding), one sentence on what it means, then counts by status and one line per obligation, on the run page.
- **Annotations:** the first line is the first notice; each `fails` reading is an error and each `deviates` reading is a warning, up to 50.

When the Action cannot produce a verdict, it writes a failure file at the `output` path instead, with the outcome, the reason and what to do.

## Read more

- [Beta tester brief: one page for your first run](docs/BETA-TESTER-BRIEF.md)
- [Full quickstart](docs/QUICKSTART-ACTION.md)
- [What a verdict claims](docs/SCOPE.md)
- [Reading a verdict](docs/VERDICTS.md)
- [What is collected and where it goes](docs/DATA.md)

## Licence

Elastic License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
