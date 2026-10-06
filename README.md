# Assure GitHub Action

This Action checks a PostgreSQL server or a set of HTTP endpoints against an Assure profile from your own GitHub Actions workflow. It is for teams that run PostgreSQL and want a repeatable record of which reliability and safety obligations hold, which are broken and which could not be observed.

The Action collects facts in your runner. The check runs on Symbolia's server at `api.symbolia.ai`. The Action writes the verdict back into your runner.

**Served today:** three profiles. `postgresql-observed-baseline`: intent-free, from a connection or an artefacts directory. `postgresql-declared-model`: an artefacts directory with your declaration in `raw/declaration.json`. `http-observed-baseline`: an artefacts folder holding an endpoint manifest and captured response heads; the Action produces the scope binding and passes the identity key by pipe.

Known-vulnerability scanners check your code against a list of what has broken before. Assure checks whether the way your code meets the foundational software it runs on stays inside a regime that can be shown safe and reliable, and says exactly what it could and could not establish.

Assure is the check that reads green only when nothing it examined is disproven. It tells you the bounds of what it has established, and why it matters. In an age where machines generate code at a volume nobody can read, Assure shows that each change maintains its baseline security and reliability, and stays true to any formalised requirements.

Supported PostgreSQL majors are 14 to 18. Real-run evidence exists for PostgreSQL 18.

**Checking HTTP endpoints.** `http-observed-baseline` reads the response heads you captured for the endpoints you select, offline: give the Action an artefacts folder holding an endpoint manifest and the heads, and it produces the scope binding itself.

## What a check claims

A green check claims this: within the bounds its first line states, nothing the rules Symbolia holds could check was disproven; every obligation that could not be established is named with what would establish it. The claim covers those rules and those observations, and nothing beyond them. It does not say the database is fit for its purpose.

A run that read nothing never goes green: it is yellow and exits 3. When no obligation on the machines read holds, the first line says "nothing could be established". It never means "no issues".

[SCOPE.md](docs/SCOPE.md) states the claim and its limits in full.

## What leaves your runner

The Action sends catalog facts (roles, memberships, object ACLs, policies, functions, schemas, settings and similar) and, when the runner can read them, your configuration files. Before anything is sent, the collector withholds every secret-bearing value whole, every comment in your configuration files is replaced with `# <withheld comment>`, and every string literal in a policy expression is replaced with `'<withheld literal N>'`. The collector never reads table contents, password hashes, key material or other sessions' statements. Your connection string and password stay in your runner. The Action sends only the files the profile reads, each within its size limit. The server deletes the collected facts when the check ends and keeps the verdict for 30 days. [DATA.md](docs/DATA.md) lists every item.

## Quickstart

You need:

- an Assure API key from Symbolia (it starts with `asr_`), stored as the repository secret `ASSURE_API_KEY`;
- outbound HTTPS from the runner to `api.symbolia.ai` (port 443);
- Python 3.14 on the runner and, to collect over a connection, the PostgreSQL client (`psql`);
- a collection role with read access to settings and statistics only, if you collect over a connection.

The declared profile reads collected files. Put the collector's output in a directory that holds `raw/`, add your declaration as `raw/declaration.json`, then add this step:

```yaml
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

The [full quickstart](docs/QUICKSTART-ACTION.md) covers the collection role, collecting over a connection, managed PostgreSQL, the complete workflow file and every typed outcome.

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
