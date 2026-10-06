# Route 3: HTTP endpoints

## 12. Checking HTTP endpoints

`http-observed-baseline` checks one HEAD response per endpoint you select against the HTTP obligations Assure holds (response framing, transport policy, cookies and similar). Live collection against real endpoints is not in this release: the Action reads response heads you captured, offline. `connection` is refused for this profile, before anything is read.

Give the Action an artefacts folder that holds:

- `manifest.json`, with these ten keys exactly: `"schema_version": "http-fixture-001"`, `"mode": "offline_fixture"`, `endpoints`, and the seven flags at the values shown below (`execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation` and `self_approved` false; `simulation` true). Any other key, a missing key or another value makes the Action stop before anything is sent (`MANIFEST-INVALID`). `endpoints` is a list of 1 to 16 objects with exactly these keys: `id` (`endpoint-NNN`, three digits), `scope_token` (a lower-case name you choose, distinct per endpoint), `scheme`, `host`, `port`, `path`, `response_file` (the head file's name in the folder) and `complete` (`true` when you captured the whole head);
- one file per endpoint holding the raw response head as received: the status line and every header line, each ending in CRLF, and the empty line that ends the head.

A complete `manifest.json` for two endpoints:

```json
{
  "schema_version": "http-fixture-001",
  "mode": "offline_fixture",
  "endpoints": [
    {"id": "endpoint-001", "scope_token": "checkout", "scheme": "https", "host": "shop.example.test", "port": 443,
     "path": "/checkout", "response_file": "head-001.txt", "complete": true},
    {"id": "endpoint-002", "scope_token": "login", "scheme": "https", "host": "shop.example.test", "port": 443,
     "path": "/login", "response_file": "head-002.txt", "complete": true}
  ],
  "execution_authorized": false,
  "hardware_authorized": false,
  "industrial_release_authorized": false,
  "release_allowed": false,
  "physical_validation": false,
  "simulation": true,
  "self_approved": false
}
```

```yaml
      - name: Assure check
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: http-observed-baseline
          artefacts: http-fixture
```

The inputs: `profile: http-observed-baseline`; `artefacts`, the folder above. `scope` is optional: a JSON file listing the endpoint ids to check, which must name exactly the manifest's ids (the Action stops before collecting otherwise). Leave `scope-binding` unset so the Action produces it: before collection it runs the identity producer and then the collector over your manifest, and sends their record as the scope binding with the endpoint tokens. `identity-key` stays `pipe`, its default: the Action makes a fresh key for each job and passes it on a pipe, so no key is an input, an environment variable or a file.

A `scope` file, when you give one, is a JSON list of the manifest's ids, for example `["endpoint-001", "endpoint-002"]`.

Replace the example endpoint values with the operator's own; keep the top-level keys and the seven flags as shown.

## Capturing the response heads (section 12)

Capture each head with `curl`, one HEAD request over HTTP/1.1, and write it to the file the manifest names:

```sh
mkdir -p http-fixture
curl -sS --http1.1 -I https://shop.example.test/checkout > http-fixture/head-001.txt
curl -sS --http1.1 -I https://shop.example.test/login > http-fixture/head-002.txt
head -n 1 http-fixture/head-001.txt
```

`-I` sends a HEAD request and writes the head as received, every line ending in CRLF, with the empty line that ends it. `--http1.1` matters: the first line of each head must be an HTTP/1.1 status line, such as `HTTP/1.1 200 OK`. A head whose first line is another version, such as `HTTP/2 200` from a capture without `--http1.1`, or `HTTP/1.0 200 OK` from a server that answers in HTTP/1.0, is recorded as not observed. Without `-L`, `curl` does not follow a redirect, so a `3xx` head is the endpoint's own answer.

Set `complete` to `true` for each head you captured this way. Commit `http-fixture/` with the manifest; the workflow below checks it out.

A complete workflow for the HTTP profile:

```yaml
name: Assure HTTP

on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

jobs:
  http:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@<full commit sha of the release you trust>

      - name: Set up Python 3.14
        uses: actions/setup-python@<full commit sha of the release you trust>
        with:
          python-version: "3.14"

      - name: Assure check
        id: assure
        uses: Symbolia-Assurance/assure-action@<full commit sha>
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: http-observed-baseline
          artefacts: http-fixture
          fail-on: fails
          output: assure-verdict.json

      - name: Keep the verdict
        if: always()
        uses: actions/upload-artifact@<full commit sha of the release you trust>
        with:
          name: assure-verdict
          path: ${{ steps.assure.outputs.verdict-path }}
```

Every reading summary carries the profile's three scope notes:

- Readings cover one HEAD request per operator-selected endpoint.
- Evidence freshness and response authenticity are unverified; same-selection replay is not excluded.
- Per-endpoint coverage qualifications are not displayed in this report.

A full read of the two `https` endpoints above has the first line "green: 2 of 2 endpoints observed; 4 of 5 machines read, 1 refused; declared premises: 12; version pins: none; nothing disproven; established: 3 of 12; not established: 6 — top action: collect the facts HTTP-TLS10-NEGOTIATION reads": the TLS machine (M2) is refused with "no usable observed machine premise", because a captured head carries no TLS session. That is a bound of the result, so the run exits 0. For `http://` endpoints M2 reads vacuous and the first line is "green: 2 of 2 endpoints observed; 5 of 5 machines read; declared premises: 12; version pins: none; nothing disproven; established: 3 of 12; not established: 3 — top action: state it in requirements.md". A head that carries both `Content-Length` and `Transfer-Encoding` fails `HTTP-FRAMING-CL-TE`, and under the default `fail-on: fails` the job exits 1, red.

The policy exits are those of section 7: `nothing_disproven` (0, green) when nothing is disproven, whatever endpoints or machines could not be read; `disproven` (1, red) when a reading has a status you fail on; `could_not_look` (3, yellow) when no endpoint was observed or no machine could be read.

Before the run, check that the first line of each captured head begins with `HTTP/1.1`.

## What is sent, and what is never read

For a profile whose inputs name no PostgreSQL configuration or `pg_hba.conf` file, such as the HTTP profile, nothing is withheld: the files are sent as read, and the line says "nothing to withhold — the withholding pass covers PostgreSQL configuration and pg_hba files and the SQL literals in the catalog snapshot and the declaration, and this profile's inputs name none of them".
