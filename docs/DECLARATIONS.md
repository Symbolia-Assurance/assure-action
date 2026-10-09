# Declarations

A declaration is to your database's access rules what a Playwright test is to your UI — a file in your repo, run on every PR.

Keep it at `raw/declaration.json`, beside the files collected from the database. You write the intended access rules; the collector supplies the observed configuration. Keep the declaration under version control and review its changes with the database changes.

Assure is built for machine-generated changes at a volume nobody reads. Within the stated bounds of its served PostgreSQL and HTTP profiles, a check helps detect regressions in the rules those methods cover. A scanner can flag a known pattern; a declared-model check compares the supplied configuration with your stated intent under a bounded model. It cannot establish every software requirement or establish arbitrary software behavior.

## Validate locally

From the public Action distribution checkout, with Python 3.14:

```sh
python3.14 -B -m action.declare validate /path/to/repo/raw/declaration.json
```

This free command needs only Python: no package install, API key, network or model call. It reads the bundled versioned schema at `action/schemas/postgresql-declaration-v1.schema.json`. Exit 0 means valid structure; exit 2 means invalid input. Its JSON output names structure errors, operator confirmations and coverage gaps. Valid structure is not a database verdict.

The version is `"schema": "assure.postgresql.declaration/v1"`. The required fields are `schema`, `id` and `major`; unlisted fields are rejected. Keep `id` stable when revising the same declaration. It is a 1 to 128 character identifier starting with a letter or digit and then using letters, digits, underscores, dots or hyphens. `major` must be an integer encoded as, for example, `17`, from 14 through 18. JSON Schema's integer type also permits `17.0`; this validator rejects that encoding for compatibility with the derive step.

Declarations are UTF-8 JSON objects with distinct keys and finite numbers, at most 1,048,576 bytes. A role or object identifier starts with a letter or underscore, then uses letters, digits, underscores, dots or hyphens, at most 64 characters. Read the bundled schema for every optional field and nested shape. Existing legacy runtime declarations remain supported; add `schema` and `id` to use this public validation version.

## Describe your intent

These five groups explain the existing flat fields. They are not new nested keys:

| Group | Fields and meaning |
|---|---|
| Administrators | `database_owner`, `administrators`, `applications`, `collection_role`, `sensitive_roles`, `permitted` and privilege declarations identify owners, application roles and intended authority. A role's name alone does not establish its actual privileges. |
| Permitted connections | `intended_flows` specifies transport (`local`, `plain`, `tls` or `gss`), database, user, address, method and rule id. `forbidden_methods`, `trusted_addresses`, `loaded_identity`, `tls_floor`, `key_file_mode`, `key_owner`, `certificate_roles` and `ca_bindings` describe authentication and transport intent. Optional `raw/clients.json` supplies client channels. |
| Sensitive objects | `sensitive_objects`, `permitted`, `privilege_queries`, `disjoint_duties`, `default_acl_expectations` and `declared_revokes` name objects and intended grants or revokes. The versioned privilege fields accept `SELECT`, `INSERT`, `UPDATE` or `DELETE`. |
| Tenant boundaries | `protected_tables`, `declared_predicate`, `access_paths_complete`, `required_policies`, `rls_exempt_logins` and `view_exemptions` state the protected domain and intentional exceptions. Supplying `protected_tables` requires `declared_predicate` and `access_paths_complete`, even if the table list is empty. |
| Recovery requirements | `standbys`, `standby_addresses`, `replication_roles`, `no_loss_required`, `unbounded_retention_declared`, `slot_creation_actor` and `slot_creation_authority_declared` describe replication assumptions. A requirement that a backup can be restored has no method in this served declaration profile; it remains not established. |

Do not infer purpose from the observed settings. An operator must confirm that declaration and collection describe the same database and major, that declared authentication works, that loaded HBA rules match supplied files, and that TLS, function authority and replication assumptions apply where declared. The validator names the confirmations relevant to your fields.

For tenant boundaries, confirm the predicate means each user can read only their own tenant rows, that identities map to the model, that all direct and view access routes are supplied, and that exemptions are intentional. The derive step compares normalized SQL text with `declared_predicate`; it does not parse or prove the meaning of arbitrary SQL, `auth.uid()`, joins or functions. A literal `true` does not describe tenant isolation, and a literal `false` denies every row.

The current RLS model represents one protected table, at most four access paths and four policies, and two non-NULL tenants. Each derived path is assigned the `tenant_a` abstraction; actual session/JWT mapping needs operator confirmation. Additional protected tables, incomplete paths, NULL tenants, arbitrary SQL, joins, functions, triggers, `RETURNING` and integrity-check side channels remain outside those bounds. The validator reports gaps rather than changing your declaration. Standbys are bounded to two; privilege queries, disjoint duties, default ACL expectations and declared revokes are each bounded to 32 entries by derivation.

## Place the declaration beside collected files

Follow [the collection quickstart](QUICKSTART-ACTION.md#9-using-collected-files-instead-of-a-connection), retaining the collector's sidecar, timing and redaction manifest from the same run. Add your reviewed declaration:

```text
collected/
  raw/
    catalog_snapshot.json
    declaration.json
    ... other files from this collection ...
  COLLECTION-SIDECAR.json
  TIMING.json
  REDACTION-MANIFEST.json
```

`postgresql-declared-model` requires `raw/catalog_snapshot.json` (at most 4 MiB) and `raw/declaration.json` (at most 1 MiB). Optional `raw/clients.json` is at most 1 MiB. The Action's bundle limits are 64 files and 8 MiB total; consult [DATA.md](DATA.md) for collected data and [SCOPE.md](SCOPE.md) for the claim boundaries. Use `artefacts`, since the connection collector does not author a declaration:

```yaml
      - name: Check declared database intent
        uses: Symbolia-Assurance/assure-action@beta
        with:
          api-key: ${{ secrets.ASSURE_API_KEY }}
          profile: postgresql-declared-model
          artefacts: collected
          fail-on: fails
```

The checker performs no SQL of its own. Its readings describe what the declared configuration satisfies under a declared model over pinned documentation; they prove nothing about the database software and give no deployment approval. An empty declared domain reads vacuous, which is not holds. See [VERDICTS.md](VERDICTS.md) for the current Action policy.

## Requirements as reviewable sentences

The requirement matcher accepts `requirements.md`: one sentence per line, optionally a Markdown bullet, a stable id and a scope tag. Tags are `[postgres]` or `[http METHOD /path]`; an unscoped sentence is also accepted. Explicit requirement ids must start with an ASCII letter, use only ASCII letters, digits, underscores, dots or hyphens, be at most 64 characters and contain at least one ASCII digit. Examples include `R1`, `own_rows2`, `Requirement7`, `false-positive1` and `NO1`. A word-shaped candidate label recognized by the ASCII label grammar before a colon or scope tag without a digit is ambiguous: `Not`, `Untrue`, `Disproven`, `Not-true`, `Requirement` and `own_rows` retain the complete source line and read not understood. The same rule refuses `not`, `never`, `no`, `false`, `none` and `without`, regardless of casing or digitless punctuation variants. In requirement matching, such a recognized ambiguous line cannot match a method or request a formalisation quote. Labels outside the candidate grammar remain part of the whole-line sentence and may request a no-method formalisation quote. Anonymous sentences without a candidate label remain accepted. For example:

```text
- R1 [postgres]: A backup can be restored.
- R2 [http HEAD /]: No response carries both Content-Length and Transfer-Encoding.
- R3 [http GET /]: No response carries both Content-Length and Transfer-Encoding.
```

Preserve each original sentence in the result. Matching uses existing method statements and the reviewed HTTP framing alias above; writing a sentence does not create a method or infer a predicate for a declaration. The backup restoration sentence therefore remains a no-method requirement. Keep tenant intent in the declaration; exact canonical statements bind existing methods, while the generic tenant sentence is not an alias.

A matched coverage gap whose trusted obligation metadata declares `observable_at_pin: false` and whose class is not `intent_bound` asks for the collector successor (Symbolia), with no formalisation quote; admitted holds or witnessed disproof and preceding scope, identity or incomplete-effort gaps keep their precedence.
An `intent_bound` obligation retains its original cause and action, including `needs_intent` and the operator action to supply and confirm purpose and assumptions. For other classes, this redirect also covers intent or premise gaps, refused-machine observations and HTTP endpoint gaps. The original cause remains in the details; the collector action belongs to Symbolia.
Only an exact plain dictionary whose top-level keys are all exact strings supplies effort completion and provenance; every other carrier counts as absent effort before any lookup. Accepted provenance keys are snapshotted once per match call after semantic evaluation, directly from plain source trees without caller copy hooks. Supported exact types are dictionaries with exact UTF-8 string keys, lists and null/bool/UTF-8 string/int/float values; tuples and subclasses are refused. Numbers must be finite and within the finite signed binary64 transport range, preserving their sign. Each key admits at most 4096 value nodes with root depth 0 and maximum depth 64; keys do not count as value nodes, and repeated container identities are refused. These are structure bounds, not a total byte or wall-time bound. Independent row copies preserve admitted values. When effort provenance cannot be admitted, `bounds.effort_copy_errors` names the omitted accepted key with closed `source`/`kind` labels; usable evidence is preserved, semantic completion checks still apply and no completed work is fabricated. Other trusted result fields remain outside this provenance boundary.

The requirement matcher is free. The numerical formalisation quote is free on every tier, including a zero formalisation allowance and an empty top-up. An eligible `missing_method` row carries `formalisation_quote.quote_usd`, a numerical low/high estimate from the pinned price of `anthropic/claude-opus-5.5`; its `basis` names the price table hash, price date, source and token assumption. When pricing is unavailable, the quote is null and `needs_formalisation_quote` remains true. The quote itself has no charge, reserves no allowance, writes no usage and calls no model or provider. Formalisation itself is a paid future run and is unavailable in this API.

The estimate reuses the shared report-token proxy, with 2000..12000 output tokens, and is unmeasured for formalisation. It excludes future context, retries, verification and proof search. The numbers estimate model cost; they are not a payable charge, approved cap or promise that a method can be produced. Malformed lines, missing identity and incomplete effort name their own next actions rather than requesting that quote.

## Get a quote without a check

`POST /v1/formalisation/quote` accepts exactly `profile` and `sentence`, for example:

```json
{"profile":"postgresql-declared-model","sentence":"A backup can be restored."}
```

Authentication is required on every tier, including an account with zero check credit. The route applies only the minute request-rate limit: no check admission, ledger probe or ledger write. It creates no check, calls no check runner, report worker, model or provider, and reserves no allowance. An exhausted check credit balance blocks a new check with `credit_exhausted`, but does not block the standalone quote route.

Use one of the served profiles with a reviewed quote namespace: `postgresql-declared-model`, `postgresql-observed-baseline` or `http-observed-baseline`. The sentence must be nonblank UTF-8 text of at most 8192 UTF-8 bytes, without control characters. Whitespace, Unicode and punctuation remain exact in its sentence/domain content key. The body accepts no caller model, price, schema, repository or commit overrides. Malformed quote body shape or sentence is `400 bad_input` with malformation kind `quote_body`; an unknown profile is `404 unknown_profile`, and a body beyond 65536 UTF-8 bytes is `413 oversize_input`. A missing or invalid key is `401 unauthenticated`. Unavailable model pricing is `503 profile_not_servable` with `detail.rule: price_owed`, rather than a zero estimate. Failed profile-metadata verification is `503 profile_not_servable` with `detail.rule: checker_metadata`; nothing is owed by the caller, and Symbolia repairs it. Quote bounds retain their numeric values and types within the finite binary64 transport ceiling (`sys.float_info.max`); this is a transport limit, not a business price cap.

The direct response is the quote object: `line`, `quote_usd`, `idempotency_key`, `quote_fee_usd: 0`, `calibrated: false`, `execution_available: false` and `basis`, plus read-only account terms `allowance_remaining` and `allow_overage_needed`. Those terms describe whether a later paid run would need overage permission; they do not admit that run. It assigns no requirement state and does not attest a missing method or authorize spending. The estimate and its limits above apply; no formaliser is available.

Each requirement has three states:

| State | Meaning |
|---|---|
| Holds | Every applicable matched method establishes the sentence within its stated bounds, on a nonempty domain. |
| Disproven | An applicable witnessed result contradicts the sentence. Review the counterexample, repair its cause and rerun the obligation. |
| Not established | A method, premise, observation, verified scope binding or representation is missing, or applicable work stopped early. The result must name the gap and the next action. |

Bias belongs to each obligation's trusted profile metadata, not to a run-wide switch. `refute` permits software green after all available applicable methods complete without a witnessed contradiction, while named not-established gaps remain visible. `prove` makes an unestablished matched obligation blocking and presents it as **not proven**. A critical not-proven presentation leaves the three states unchanged: there is no fourth state or proof. Legacy profiles have no explicit bias metadata and retain undeclared `refute` provenance; their gaps must still be shown. Software green concerns completed methods and policy, and does not mean that every requirement holds.

HTTP evidence here covers one captured HEAD response per operator-selected endpoint. A HEAD result for `/` cannot establish a requirement scoped to GET `/`, a different path or a different endpoint. Verified method/path identity is required for scoped matching. The current public HTTP collection omits an inspectable method/path map: its identity carrier holds digests and opaque endpoint tokens. Until the serving adapter supplies a reviewed verified map, even a `[http HEAD /]` requirement has an identity-binding gap; unit-test bindings are interface examples rather than collected evidence. Captured heads do not establish response authenticity, freshness or a TLS session, and same-selection replay is not excluded. See [the HTTP quickstart](QUICKSTART-ACTION.md#12-checking-http-endpoints).

## Send requirements and read history

`POST /v1/checks` accepts `requirements` as one UTF-8 JSON string beside `profile` and `files`. This text is metadata, never a file under `raw/`, and the uploaded collected files remain unchanged. It is at most 65536 UTF-8 bytes, 256 physical lines and 8192 UTF-8 bytes per content line. Physical lines are split on LF; a final LF or CRLF ends the last line rather than adding one. After splitting on LF, the byte limit includes a CR before LF and any bullet, id or tag; it is checked before the matcher removes line terminators. The source hash covers the exact original upload, including its final line ending. Invalid UTF-8 or an exceeded limit is `bad_input` with malformation kind `requirements`, before the checker runs.

Send `repository` (`owner/name`) and `commit` (40 lowercase hex digits) together or neither. A direct API call defaults to `provenance: caller`, but can supply `provenance: runner` itself; the Action sends `GITHUB_REPOSITORY` and the pull request head SHA from a valid event file bounded to 16 MiB, otherwise `GITHUB_SHA`, with `provenance: runner`. This pair is checked for shape, not a GitHub attestation or permission to read another account. A check without repository and commit has no history. Reusing an `Idempotency-Key` with different requirements text is refused as `bad_input` with rule `idempotency_body_mismatch`.

The Action sends the repository root's `requirements.md` by default when present, and sends no requirements text when absent; an unsendable default root file is skipped with a notice explaining why. An explicit `requirements` input selects a file path; a selected missing, unreadable, linked, non-UTF-8 or over-limit file gives `bad_input` and exit 2 before collection or upload. For example, add `requirements: review/requirements.md` to the Action's `with` inputs. Requirements matching runs in API mode; when local mode finds a file or explicit input it says "requirements are read in api mode only: local mode did not read or send requirements.md".

Set `requirements: none` to send no requirements text or skipped-file notice in API mode and suppress the local requirements notice. Use `./none` to select a literal file named `none`. When both are present, repository and commit metadata are sent independently of requirements text, including with `requirements: none`. The server keeps this metadata with the check for 30 days; see [DATA.md](DATA.md#on-the-server).

The requirements text comes from the checked-out workspace, not fetched from the named commit. A pull request workflow may read a merge tree, and `pull_request_target` may read the base branch, while the metadata names the pull request head. Align the checkout with the commit you intend to check; caller/runner provenance is not a GitHub attestation.

The verdict's `requirements` list preserves each original sentence, id, state, reason class, next action, available evidence and quote. The first line counts requirements that hold, are not established or are disproven; the Action summary and annotations carry requirement lines, and its outputs include `requirements-not-established` and `requirements-disproven`. A matched prove-class requirement that is not proven remains `not_established`, with `display_state: not_proven` and `blocking: true`. Those human lines show the sentence in at most 160 characters, with an ellipsis when truncated, plus an available evidence locator, id, state, reason class, action and quote. The literal row `reason` remains in JSON and is not rendered on these human lines. Unicode categories Cf, Zl and Zp are shown as spaces on human requirement lines; JSON and quote identity retain the exact original characters. The original JSON sentence and available source details remain unchanged.

`GET /v1/profiles` exposes the declared `canonical_statements`: each full statement has its machine, obligation ID and source MACHINE digest. Copy that exact statement into requirements.md to match the existing declared obligation. The listing's `checker_entry_sha256` identifies the current verified metadata snapshot. The verdict's `checker.entry_sha256` binds matching to the actual loaded checker entry captured before execution; metadata verification or entry-binding failure reads `not_established/checker_contract`, with no quote, while the original checker reading remains. It retains the legacy refute default and per-obligation source facts without inventing policy metadata, aliases or authenticated identity assumptions. A genuine unknown sentence or absent obligation statement still reads `missing_method` and may receive a free quote. Canonical matching carries the actual obligation result, including typed method or premise gaps, rather than promoting a whole-machine result. The HTTP identity-binding gap above remains.

The authenticated routes `GET /v1/requirements/{id}/history?repository=owner/name` and `GET /v1/declarations/{id}/history?repository=owner/name` return JSON lists, newest check first, from stored finished checks. `repository` is required and matched exactly within the authenticated account; missing it is `bad_input`. A foreign or absent history returns an empty list. Two checks on one commit remain two entries. Use `limit` from 1 to 200 (default 50) and the last entry's `check_id` as `cursor` for the next page; listing history runs no check.

Requirement history records commit, check id, actual requirement state, declaration id, `sentence_sha256` and the matcher schema `assure.requirements/v1`. Declaration history also works for a handwritten `raw/declaration.json` without requirements text: it records the declaration's own schema, `source_sha256` of the exact uploaded declaration bytes and `requirement_ids` (`[]` when none were sent). Collection time is the recorded collector time or null, never upload time. These routes list recorded results within their bounds; they do not establish new evidence.

## Synthetic Supabase tenant example

The public distribution includes `examples/supabase-tenant/setup.sql` and three authored declaration examples: `examples/supabase-tenant/restricted/raw/declaration.json`, `examples/supabase-tenant/rls-off/raw/declaration.json` and `examples/supabase-tenant/using-true/raw/declaration.json`. All keep the same tenant intent and stable declaration id. Only those declarations and SQL are exported; synthetic test catalogs are not database captures.

`setup.sql` describes a disposable Supabase database that already provides `auth.uid()`. It uses two synthetic PostgreSQL login paths (`user_a`, `user_b`), two UUID identities, and `public.cpd_records(owner_id, note)`. The declared object is the unqualified `cpd_records`, because the current derive step reads `relname`; duplicate names in different schemas are outside this example. This bounded identity mapping is not a complete Supabase role/JWT simulation. No SQL in this example has been executed or presented as observed evidence.

When item 8 lands (not yet served on any release): treating `auth.uid()` as session identity requires collected function-owner or definition evidence that the auth schema is Supabase's; its name alone does not establish that provenance.

When item 8 lands (not yet served): the declaration/example has this scoped applicability condition: "isolation holds given the application sets the setting from an authenticated identity before any query; a direct database login can set it." The normalized `tenant_eq` value alone does not establish that condition or attest an authenticated identity.

Copy the restricted declaration into your own collected `raw/declaration.json`, review it for your database, and run the free validator. Keep it beside that database's collected artifacts; do not substitute a test catalog for collection. The predicate is `owner_id = auth.uid()`, the required policy is `cpd_own_rows`, both logins are application roles, and no login or view exemption is declared. Confirm the identity and route assumptions before checking.

The intended restricted policy is `FOR SELECT TO PUBLIC USING (owner_id = auth.uid())`, with RLS enabled and forced. The two mutations in `setup.sql` leave the declaration unchanged: disable RLS, or replace the policy with `USING (true)`. Re-enable RLS or restore the original predicate respectively to repair them. In disposable sessions with the matching synthetic role and UUID claim, the restricted and repaired cases are expected to return only that user's row; either mutation is expected to expose both rows. These are expectations, not SQL observations.

The command-specific SELECT method is still missing in this slice. The three existing decisive acceptance tests remain genuinely failing: restricted SELECT should establish the tenant boundary, while RLS-off and SELECT USING(true) should disprove it with cross-tenant witnesses; after repair they should establish it. Shape validation alone cannot produce those results. The current RLS method accepts ALL policies, and replacing SELECT with ALL would change the example rather than resolve this gap.
