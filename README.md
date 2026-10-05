# Assure GitHub Action

This Action checks a PostgreSQL server against an Assure profile from your own GitHub Actions workflow. It is for teams that run PostgreSQL and want a repeatable record of which reliability and safety obligations hold, which are broken and which could not be observed.

The Action collects facts in your runner. The check runs on Symbolia's server at `api.symbolia.ai`. The Action writes the verdict back into your runner.

**Served today:** both PostgreSQL profiles. The intent-free profile, `postgresql-observed-baseline`, needs no declaration. `postgresql-declared-model` reads your server against a declaration you write and needs a directory of collected files. Supported PostgreSQL majors are 14 to 18. Real-run evidence exists for PostgreSQL 18.

## What a check claims

A check that meets your policy claims this: every rule Symbolia holds for the system was checked against what was observed and none is violated, and what could not be observed or judged is named. The claim covers those rules and those observations, and nothing beyond them. It does not say the database is fit for its purpose.

A run that read nothing never passes. When no obligation reaches a verdict, the job summary reads "No verdicts" and the job exits 3. That means nothing could be checked. It never means "no issues".

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
| `api-url` | `https://api.symbolia.ai` | The API address. It must use `https://`. |
| `mode` | `api` | `api`: the check runs on the Assure API. |
| `profile` | `postgresql-observed-baseline` | The checker profile to run. |
| `connection` | none | A libpq connection string or URI. Pass it from a secret. |
| `artefacts` | none | A directory of collected files. Use this or `connection`, never both. |
| `collection-role` | none | The name of the collection role. It must match the user in `connection`. |
| `collection-privileges` | `pg_read_all_settings,pg_read_all_stats` | The roles you granted to the collection role. |
| `data-dir` | none | Where the runner can read the server's data directory. Used with `connection`. |
| `config-dirs` | none | Directories outside the data directory that hold configuration files. Used with `connection`. |
| `fail-on` | `fails` | Which statuses fail the job, or `never`. |
| `output` | `assure-verdict.json` | Where to write the verdict file. |
| `python` | `python3` | The Python 3.14 interpreter to use. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | A verdict was written, and no reading has a status you fail on (or `fail-on` is `never`). |
| 1 | A reading has a status you fail on. |
| 2 | Bad input. Fix the inputs or files. |
| 3 | Nothing was checked, or a typed outcome stopped the check. The failure file holds the reason and what to do. |

The Action sets three outputs: `verdict-path`, `outcome` and `exit-code`.

## Where the verdict goes

- **The verdict file:** JSON at the `output` path, schema `assure.serve.verdict/v1`, with every reading and its premises. [VERDICTS.md](docs/VERDICTS.md) explains how to read it.
- **The job summary:** counts by status, then one line per obligation, on the run page.
- **Annotations:** each `fails` reading is an error and each `deviates` reading is a warning, up to 50.

When the Action cannot produce a verdict, it writes a failure file at the `output` path instead, with the outcome, the reason and what to do.

## Read more

- [Full quickstart](docs/QUICKSTART-ACTION.md)
- [What a verdict claims](docs/SCOPE.md)
- [Reading a verdict](docs/VERDICTS.md)
- [What is collected and where it goes](docs/DATA.md)

## Licence

Elastic License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
