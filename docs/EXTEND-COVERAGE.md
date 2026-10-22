# Extend Assure's coverage

When Assure says it cannot read something, choose the path below that fits the gap. A missing reading stays not established until the check can establish it.

Use matching Action and API releases that include these extensibility features.

## 1. Request a library or rule

Use this when Assure does not read a library, extension call or requirement. For a refused extension, copy `detail.coverage.template` from the result into `coverage-request.json`. Check its pinned library version, calls and file locations. Complete the source evidence for routes, request hooks, identity reads and writes, and the setting that activates the extension. The [request instructions](QUICKSTART-ACTION.md#extension-adapter) name each slot.

You may add a proposed model in `coverage.formal_model`: it shares a 4,096-byte limit with `text` and is data Symbolia reviews. Show the request and obtain the consent below before sending it:

```sh
curl --request POST https://api.symbolia.ai/v1/feedback \
  --header "Authorization: Bearer $ASSURE_API_KEY" \
  --header 'Content-Type: application/json' \
  --data-binary @coverage-request.json
```

Keep the returned `id`; `GET /v1/feedback/{id}` with the same header reports its status. For a gap without a template, send a `coverage_gap` note with `text` describing the missing reading. [Deliberate feedback](QUICKSTART-ACTION.md#deliberate-feedback) gives its fields.

The comment keeps the refusal and its coverage-request next step. Sending a request changes no reading. Symbolia must ship a reader for that version; a proposed model alone establishes nothing.

## 2. Map a standard-library HTTP app

Use the adapter bridge when your app uses `http.server` but has a shape the native reader does not read. This maps your handler, guard, public paths and private routes onto `python/stdlib-http`.

```sh
git -C /path/to/work clone https://github.com/Symbolia-Assurance/assure-action assure-action
python3.14 -B /path/to/work/assure-action/action/adapter_bridge.py template --root /path/to/app
python3.14 -B /path/to/work/assure-action/action/adapter_bridge.py check --root /path/to/app
```

Between template and check, merge the printed `credentials` entry and `bridge` map into your existing `.assure/declaration.json`, completing every route. Follow the [bridge contract](ADAPTER-BRIDGE.md); the self-check parses source without running your app or sending it. Fix every printed fault. After consent, commit the declaration and rerun your existing Action check; in API mode it reads `requirements.md` by default.

The comment says **"Assuming your adapter (stated by you)"** and names its premises. Assure rechecks the map against source on every run. A mismatched map is refused. Keep readings that depend on those premises apart from unconditional holds; the summary's holds total is not an unconditional-hold count.

## 3. State an external configuration fact

Use this for a supported configuration decision whose production value Assure cannot observe. Confirm and monitor that value yourself. For example, when DebugToolbar is disabled in production, add this item to `config_surfaces` in an `assure.identity.declaration/v1` declaration, keeping the other entries:

```json
{"kind":"property","locator":"DEBUG_TB_ENABLED","assertion":"false in production"}
```

For the native `assure.python-auth.declaration/v1` form, the same item is `{"key":"DEBUG_TB_ENABLED","value":false,"where":"production"}`. Use the form matching your declaration's `schema`.

Commit the reviewed declaration and rerun the same check:

```sh
git -C /path/to/app add .assure/declaration.json
git -C /path/to/app commit -m "State the production configuration premise"
git -C /path/to/app push
```

The comment says `holds, assuming DEBUG_TB_ENABLED = false in production (stated by you, not observed)`. This is a stated assumption, not an observed production value; do not count it as an unconditional hold. This path covers the supported disabled-DebugToolbar and built-in Flask-Caching decisions; it cannot waive an unknown extension, a contradiction in code, a computed loader or a constructor's configuration. An unused fact changes no reading.

### Declared hand-offs and config values

A `python-auth` declaration (`.assure/declaration.json`) can state two kinds of fact that Assure cannot read from your code. Both are stated by you.

`config_surfaces` gives the value of a configuration key. Assure reads a stated value only for the keys it interprets: `DEBUG_TB_ENABLED` and `CACHE_TYPE`. A binding in your code that contradicts it reads disproven.

```json
{"key": "CACHE_TYPE", "value": "SimpleCache", "where": "production"}
```

`declared_handoffs` says what a call Assure cannot follow does with your app object or a blueprint, such as `db.init_app(app)` or `UserManager(app, db, User)`. Name the call as `<file>:<line>`, the library by its PyPI name, and the effect. `no_routes` means the call registers no route. `routes` lists every route it registers, each with a method, a path and a guard: a guard your declaration defines under `guards`, or `public`. AUTH-1 judges each listed route like any other.

```json
[
  {"call": "app/__init__.py:37", "library": "Flask-SQLAlchemy", "effect": "no_routes"},
  {"call": "app/__init__.py:68", "library": "Flask-User", "effect": {"routes": [{"method": "GET", "path": "/user/sign-in", "guard": "public"}, {"method": "GET", "path": "/user/change-password", "guard": "login_required"}]}}
]
```

Every row that rests on one of these facts reads "premised: stated by you (file:line)". A `no_routes` entry whose call registers a route in code Assure can read reads disproven. An entry that names a call that does not exist is refused as a stale declaration. The setup consent lists these facts.

## Before sending an adapter or model

The agent shows exactly what will be sent and asks once: **"Would you like to submit this data to improve Assure's coverage of your requirements?"** For a bridge, name the declaration and route/header map, selected application files and requirements; for a request, name the note and any proposed model. Wait for yes before a POST or a commit/push that submits them. If declined, keep the work local; the bridge self-check still works.

Product-improvement settings are separate: Free defaults on with an opt-out through Symbolia; paid plans default off and require an opt-in; Enterprise data is excluded. A submission approval does not change that setting. `consent_follow_up` only permits follow-up about a feedback note. See [DATA.md](DATA.md#using-your-data-to-improve-the-product-product_data).
