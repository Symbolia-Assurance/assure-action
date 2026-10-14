# First-line samples

The first line of the job summary, word for word, as the serving path writes it for each case, and the sentence under it that says what it means. Each line comes from recorded readings, or from recorded readings changed as each section says; a test rebuilds every line and checks it against this page. [VERDICTS.md](VERDICTS.md) section 9 gives the words and their order.

## Green: nothing disproven

The observed profile on the official PostgreSQL 18 image (the successor build's recorded readings), `fail-on: fails`. Every machine was read; four obligations hold; two readings deviate from vendor guidance and are counted on their own; 21 obligations could not be established, and the top action names what would establish most of them.

```text
green: 8 of 8 machines read; declared premises: none (observed profile); version pins: major 18; nothing disproven; established: 4 of 40; deviations: 2; vacuous: 13; not established: 21 — top action: state it in requirements.md
```

The top action stays "state it in requirements.md". In the summary under the line, each row that depends on what the system is for gives a second way: "operator: commit the proposed declaration (assure-declaration-proposal.json) as .assure/declaration.json (with a connection; raw/declaration.json in an artefacts directory) and run postgresql-declared-model, or state it in requirements.md". On this profile the Action writes `assure-declaration-proposal.json` beside the verdict file, a declaration drafted from the same catalog snapshot, with `assure-requirements-draft.md`, the goals that proposal lets Assure check, as plain sentences to confirm, and `assure-requirements-typed.json`, which pins each goal to the checks under it. The summary's section "Declaration proposal" counts the leaves it proposes, the keys to confirm and the rows a committed declaration would decide.

## Red: something disproven

The same readings with `fail-on: fails,deviates`. A deviation is now a status you fail on, so both are disproven: the line counts them and the first one in reading order is the witness: its object, its access path and its locator. With one disproof the count is left out: "disproven: HBA-5-OB — …".

```text
red: 8 of 8 machines read; declared premises: none (observed profile); version pins: major 18; deviations: 2; disproven: 2, first HBA-5-OB — postgres, hba-128, raw/pg_hba.conf:128 'host all all all scram-sha-256'
```

## Yellow: could not look

The same readings with the input-integrity gate set. Nothing could be read, so the line gives the reason and what to do; the summary under it prints the gate's reason and the file it names.

```text
yellow: could not look: the input could not be represented; re-collect with the pinned collector
```

## Strict

The successor build's readings with `fail-on: unresolved-security`. The observed profile marks 36 of its 40 obligations `security: true`. Fourteen of them are intent-bound: they depend on what the system is for, which no collector can observe, so the count "19 of 22" leaves them out; it counts observability only. Of the other 22, the collector pin observes 19; HBA-6, TLS-1-OB and LR-3-OB are listed as not observable at the collector pin. All security obligations without a verdict bind under strict, including one the pin cannot observe; the report names each and why: 19 here, the 14 intent-bound ones, HBA-1-OB, REP-1-OB and the three the pin cannot observe. The job stops (exit 1, `unresolved_strict`), and the line gives the count and names the first in reading order, PRIV-1, with what would resolve it.

```text
red: 8 of 8 machines read; declared premises: none (observed profile); version pins: major 18; strict: 19 of 22 security obligations observable at this pin; deviations: 2; unresolved by your choice (strict): 19, first PRIV-1 — depends on what the system is for; state it in requirements.md
```

## Every obligation not established

The declared profile on the same image (the proof fixture's recorded readings), `fail-on: fails`. Three of eight machines were read and none of their 15 obligations holds, so the line says in words that nothing could be established, then the action that would establish the most frequent kind of gap.

```text
green: 3 of 8 machines read, 5 refused; declared premises: 0; version pins: none; nothing could be established (0 of 15 obligations hold); not established: 15 — top action: collect the facts REP-1 reads
```

## What each colour means, per profile

The sentence under the first line comes from a fixed template for each colour. A consequence the profile does not state yet reads "Consequence not yet stated for \<obligation>."; nothing is invented.

### PostgreSQL observed

The successor build's recorded readings: green with `fail-on: fails`, red with `fail-on: fails,deviates`, yellow with the input-integrity gate set. The observed profile states each obligation's consequence, so the red sentence opens with HBA-5-OB's own.

Green:

```text
Nothing in your database configuration contradicts what is known about safe PostgreSQL setups. 21 of 40 checks could not be completed, mostly because they depend on what the system is for, which has not been stated. That is a gap in what we could see; your database configuration is unchanged by it.
```

Red:

```text
A superuser or replication login and its data can cross the network unencrypted. The finding is at raw/pg_hba.conf:128 'host all all all scram-sha-256' (postgres, hba-128).
```

Yellow:

```text
We could not read the collected files, so nothing below is a finding about your database configuration. Re-collect with the pinned collector.
```

### PostgreSQL declared

The proof fixture's recorded readings: green as recorded; red with TLS-1 changed to fails; yellow with every machine not evaluated.

Green:

```text
Nothing in your database configuration contradicts what is known about safe PostgreSQL setups. 15 of 15 checks could not be completed, mostly because some facts were not collected. That is a gap in what we could see; your database configuration is unchanged by it.
```

Red:

```text
Consequence not yet stated for TLS-1. The reading TLS-1 fails; the record carries no witness to point at.
```

Yellow:

```text
We could not read the collected files, so nothing below is a finding about your database configuration. Re-collect with the pinned collector.
```

### HTTP

An HTTP endpoint check of two endpoints, with readings made for this page: green with both endpoints observed and holding; red with one reading changed to fails; yellow with no endpoint observed.

Green:

```text
Nothing in your HTTP responses contradicts what is known about safe HTTP setups. 4 of 5 checks could not be completed, mostly because they depend on what the system is for, which has not been stated. That is a gap in what we could see; your HTTP responses are unchanged by it.
```

Red:

```text
Consequence not yet stated for HTTP-1. The reading HTTP-1 fails; the record carries no witness to point at.
```

Yellow:

```text
We could not read the collected files, so nothing below is a finding about your HTTP responses. Collect the selected endpoints.
```

### Python auth

`python-auth-declared-model` on the checker's own Flask fixtures, bundled as the Action bundles them, with the six catalogue phrases as the repository's requirements.md and as the check's requirements: green on `flask-session-b` (every reading holds but AUTH-6, which has no method yet); red on `flask-session-a` with no elevation key in its declaration.json, so AUTH-5 has nothing to elevate (the checker reads it `missing_premise`, because requirements.md claims it) and reads as an empty domain. The declared premises count the premises the checker confirms. AUTH-1 states its consequence.

Green, the first line and the sentence under it:

```text
green: 1 of 1 machines read; declared premises: 7; version pins: none; nothing disproven; established: 5 of 6; not established: 1 — top action: a method is a later profile version; requirements: 5 hold, 1 not established
```

```text
Every route in your Flask app is guarded as your declaration says. 1 of 6 checks could not be completed, mostly because Assure has no method yet for some of these shapes. That is a gap in what we could see; your Flask app is unchanged by it. 6 of 6 requirements in requirements.md could be read.
```

Red, the first line and the sentence under it:

```text
red: 1 of 1 machines read; declared premises: 6; version pins: none; requirements: 2 hold, 2 not established, 2 disproven; disproven: 2, first AUTH-1 — app/__init__.py:49
```

```text
Anyone who can reach your Flask app can call a route outside your declared public routes without signing in. The finding is at app/__init__.py:49. 6 of 6 requirements in requirements.md could be read.
```
