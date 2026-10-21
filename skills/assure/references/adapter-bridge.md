# The adapter bridge

The adapter bridge (contract `assure.adapter-bridge/v1`) lets a standard-library `http.server` app that Assure does not read natively get the sign-in check. You, or your coding agent, write a short map from your app onto the `python/stdlib-http` adapter Assure serves. Assure reads that map against your code on every run.

## When to use it

Assure reads one standard-library shape natively: a module-level literal route table and one dispatcher that calls one guard before it answers, the shape of Assure's own API. Use the bridge when your repository serves HTTP with `http.server` and has any other shape, for example routes chosen inside `do_GET` and `do_POST`, assets answered before the guard, and a guard method that raises.

The bridge lives in your repository, in `.assure/declaration.json`, under the key `bridge`. The Action sends that file with the check after you choose to submit it.

Use an unmodified `http.server.HTTPServer` or `ThreadingHTTPServer`. When the files read construct the server, Assure resolves that constructor by import and checks that your handler is its handler argument. Server subclasses, dispatch replacements and unknown factories refuse the bridge. When startup is outside the files read, the verdict states that the server is the standard library's, unmodified, as your premise.

A visible constructor must receive the unshadowed declared class in the handler file. Its instance stays local and uses the standard server methods. Direct access to `socketserver` or `threading`, server-socket replacement and local copies of those modules refuse the bridge. The verdict retains an explicit premise that dispatch dependencies outside the files read are unmodified.

Before an agent submits a bridge, it asks once: "Would you like to submit this data to improve Assure's coverage of your requirements?" It names what will be sent: the declaration (including the bridge's route map and header names), the selected application source files and the requirements included in the check. It waits for yes before committing or pushing a change that submits those files. If you decline, it keeps the bridge local and can still run the self-check. On paid tiers, use of this data for product improvement stays off unless you say yes.

## Four steps for an agent

The self-check ships in the public Action repository as `action/adapter_bridge.py`. It needs Python 3.14 and nothing else: no key, no network, no package install. It parses your code and never runs it.

1. Print a pre-filled bridge from your code. It names the first `BaseHTTPRequestHandler` subclass, the first `self.<method>(...)` statement after the public blocks as the guard, and the public paths, and leaves one `TODO` route per `do_<METHOD>`, beside a `credentials` entry pre-filled with the header the guard compares.
2. Edit it into `.assure/declaration.json` under `bridge`: one route per route behind the guard, with the literal the code selects it by, and `guard.credential` set to the `id` of a `credentials` entry for the header the guard reads. Fill in the rest of the declaration as in the worked example.
3. Run the check. Exit 0: the bridge matches your code, and the lines it prints are what the verdict will state as premises. Exit 2: each fault is printed with its rule, its place, what was expected and what was found; fix each one and run it again.
4. Ask for the submission consent above and wait for yes. Commit `.assure/declaration.json` and push. The Action sends it with every check.

From a checkout of the public Action repository, with your repository at `/path/to/repo`:

```sh
git clone https://github.com/Symbolia-Assurance/assure-action assure-action
cd assure-action
python3.14 -B -m action.adapter_bridge template --root /path/to/repo
python3.14 -B -m action.adapter_bridge check --root /path/to/repo
```

`--declaration` names another declaration path, relative to `--root`; the default is `.assure/declaration.json`. The server runs the same verification on every check, so a bridge that passes the self-check reads the same way there, and a change to your code that breaks the map refuses the next check until the bridge matches again.

## The fields

The declaration is schema `assure.identity.declaration/v1` with `stack` `python/stdlib-http`. Its `bridge` object has this shape:

```json
{
  "contract": "assure.adapter-bridge/v1",
  "onto": "python/stdlib-http",
  "handler": {"file": "src/devicectl/service.py", "class": "Handler"},
  "guard": {"method": "check", "credential": "device-token"},
  "public": [{"method": "GET", "path": "/"}],
  "routes": [{"method": "GET", "path": "/api/{device}/status", "match": "status"}],
  "stated": ["Requests reach the service only through the local proxy."]
}
```

| Field | What you write | What Assure checks against your code |
|---|---|---|
| `contract` | `assure.adapter-bridge/v1` | That it is this contract. |
| `onto` | `python/stdlib-http` | That it is the served adapter. |
| `handler.file` | The repository-relative path of the `.py` file that holds your request handler. | That the file is among the files read, under `app_roots`, and parses. |
| `handler.class` | The name of your `BaseHTTPRequestHandler` subclass. | That the file holds one module-level class of that name, whose only base is `BaseHTTPRequestHandler`, with no decorator or metaclass, and whose body holds only plain `def` methods and `NAME = <constant>` lines. |
| `guard.method` | The method of that class that checks the credential and raises when it does not match. | That the method exists, is called with constant arguments only, never returns early, and raises on a mismatch on every path. |
| `guard.credential` | The `id` of an entry in the declaration's `credentials`. | That the entry has `"carrier": "header"`, and that the guard reads the header its `carrier_name` names. |
| `public` | Every route the code answers before the guard runs, as `method` and `path`. | That the code answers exactly these paths before the guard, no more and no fewer. |
| `routes` | Every route behind the guard, as `method`, `path` and `match`: the string literal the code selects that route by. | That each `do_<METHOD>` you name exists and runs the guard first, and that each `match` literal is in that method, a method it calls, or a module constant it names (followed through `*OTHER` elements and dict keys). |
| `stated` | Optional: up to 16 short sentences you want the verdict to carry as your own statements. | Nothing: each one is printed as a premise stated by you. |

`public` and `routes` hold at most 256 routes each, `routes` at least one, and no route appears twice across the two. The methods are `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD` and `OPTIONS`. A path starts with `/` and holds no space; write a path parameter as `{name}`. List the same public routes in the declaration's `public_routes`.

## What Assure reads on every run

The bridge names things. It never says that a route is protected: Assure reads that from the bytes, every run, with the same code as the self-check. These are the limits your code must keep:

- The handler class body holds only plain `def` methods, with no decorator, and `NAME = <constant>` lines. No method is defined twice, and none takes the name of a request attribute such as `headers`, `path` or `server`.
- Every `do_<METHOD>` of the class runs the guard as its first statement, after only blocks of the form `if self.path in ("/", "/app.js"): ... return` that answer the public paths. The guard is called with constant arguments only, as in `self.check()` or `self.check(mutation=True)`.
- A hook the server runs on every request before the guard (`setup`, `handle`, `parse_request`, `log_message`, `end_headers`, `send_header` and the like) is left to `BaseHTTPRequestHandler`, or its body only calls its own `super()` method, sends constant headers with `self.send_header`, or sets a timeout with `self.connection.settimeout`.
- The guard is top-level `if` statements that each only raise. The one that reads the credential compares it as `if not hmac.compare_digest(self.headers.get("<header>"), <expected>): raise ...` (or `secrets.compare_digest`, or a bare `compare_digest` from `from hmac import compare_digest`) or `if self.headers.get("<header>") != <expected>: raise ...`, with no `else`. The compare is the standard library's, found by its import: `import hmac` or `import secrets` with no alias, and no other binding of that name; a method, a class attribute or a module of yours named like it is refused. The header read may carry a constant default, as in `self.headers.get("<header>", "")`. The expected side is a stored value: an attribute of the server, such as `self.server.token`, or a module-level name that no function rebinds. It is never a request attribute such as `self.command` or `self.client_address`, a local variable or a guard parameter, and no method of the handler writes to `self.server` or to module state. Read the header inside the compare: a header first read into a local variable is refused today.
- Before the credential compare, other tests may only read headers against stored values or constants, optionally gated by a guard parameter. Move every non-header test after the compare. Every raise up to and including that compare must construct a bounded exception class from constants. The first matching `except` clause in every `do_<METHOD>` must answer that exception with HTTP 401 or 403 through an unconditional reply path. Unknown construction, a swallowed exception, a success reply or an unproved status refuses the bridge.
- A `do_<METHOD>` may wrap its body in one `try` whose `except` handlers only deny: `pass`, `raise`, `self.send_error(...)`, or one call to a reply method of the class that only writes the reply (`send_response`, `send_header`, `end_headers`, `wfile`), with arguments that read only the caught exception.
- Nothing in the files read replaces what the bridge names: no assignment to the guard, a `do_<METHOD>` or a hook, no `setattr` or `delattr` of them, no subclass of the handler, no other request-handler class, and no `exec`, `eval`, `globals`, `vars`, `__dict__`, `__class__` or similar. The handler class name is bound once, by its `class` statement, and used only as the handler argument of the server call; `secrets`, `hmac` and `compare_digest` are bound only by import.
- Every stated route's `match` literal is in the code.

Any disagreement is a fault. A fault refuses the check: the run reads yellow, names the rule and the place, and never reads as holding.

## Worked example

`devicectl` is an invented device-control service.

Its `.assure/declaration.json`:

```json
{
  "schema": "assure.identity.declaration/v1",
  "stack": "python/stdlib-http",
  "id": "devicectl",
  "adapter": {"id": "codeauth.python.stdlib-http-identity", "version": "1"},
  "app_roots": ["src/devicectl"],
  "credentials": [
    {"id": "device-token", "kind": "api_key", "carrier": "header", "carrier_name": "X-Device-Token"}
  ],
  "public_routes": [
    {"method": "GET", "path": "/"},
    {"method": "GET", "path": "/app.js"}
  ],
  "bridge": {
    "contract": "assure.adapter-bridge/v1",
    "onto": "python/stdlib-http",
    "handler": {"file": "src/devicectl/service.py", "class": "Handler"},
    "guard": {"method": "check", "credential": "device-token"},
    "public": [
      {"method": "GET", "path": "/"},
      {"method": "GET", "path": "/app.js"}
    ],
    "routes": [
      {"method": "GET", "path": "/api/{device}/status", "match": "status"},
      {"method": "POST", "path": "/api/{device}/reboot", "match": "reboot"},
      {"method": "POST", "path": "/api/{device}/lock", "match": "lock"}
    ]
  },
  "registrations_complete": false,
  "execution_authorized": false,
  "hardware_authorized": false,
  "industrial_release_authorized": false,
  "release_allowed": false,
  "physical_validation": false,
  "simulation": true,
  "self_approved": false
}
```

## Faults

Each fault names its rule, the file and line or the field, what Assure expected and what it found.

| Rule | What it means | How to fix it |
|---|---|---|
| `bridge_shape` | The `bridge` object breaks the contract: an unknown field, another `contract` or `onto`, a malformed `handler`, `guard` or route, a route listed twice, or more than 16 `stated` sentences. | Correct the field the pointer names, as in "The fields". |
| `bridge_credential` | `guard.credential` names no `credentials` entry with `"carrier": "header"` and a `carrier_name`. | Add or correct that entry. The bridge reads header credentials only. |
| `handler_absent` | `handler.file` is not among the files read, or it holds no module-level class named `handler.class`, or more than one. | Correct the path or the class name, or widen `app_roots` to include the file. |
| `handler_unparsed` | `handler.file` does not parse as Python. | Fix the syntax error at the line named. |
| `handler_base` | The class has another base, a decorator, a metaclass or a class keyword. | Subclass `BaseHTTPRequestHandler` only. Another base can answer requests the bridge does not see. |
| `handler_alias` | A `do_<METHOD>`, a server hook or the guard is assigned in the class body, as in `do_HEAD = do_GET`. | Define it once, with `def`. |
| `handler_shape` | The class body holds a statement other than a plain `def` or `NAME = <constant>`, defines a method twice, or defines a method named after a request attribute such as `headers`, `path` or `server`, or a double-underscore method other than `__init__`. | Keep the class body to plain `def` methods and constants. |
| `handler_override` | Something in the files read assigns or deletes the guard, a `do_<METHOD>`, a hook or `compare_digest` on any object, or calls `setattr` or `delattr` with such a name or a name that is not a constant. | Remove the assignment. The guard Assure reads must be the one that runs. |
| `handler_rebound` | The handler module binds the handler class name again after its `class` statement. | Bind the name once, by the `class` statement. |
| `handler_escapes` | The handler class name is used other than as an argument of a call, such as the server call `ThreadingHTTPServer(address, Handler)`, or is passed to `type`, `getattr`, `setattr` or `delattr`. | Use the class only as the handler argument of the server call. |
| `escape_hatch` | The files read use `exec`, `eval`, `compile`, `globals`, `locals`, `vars`, `__import__`, `getattr`, or an attribute such as `__dict__`, `__class__`, `__setattr__` or `__getattr__`, any of which can rebind the guard or a method. | Remove it from the files read, or narrow `app_roots` so the bridge reads only the server's files. |
| `compare_rebound` | The handler module binds `secrets`, `hmac` or `compare_digest` other than by import, or a module named `hmac` or `secrets` is among the files read, or a read file accesses mutable import tables or import machinery. | Import them from the standard library, bind nothing else to those names, rename your own module, and remove access to `sys.modules`, import hooks and dynamic import machinery. |
| `handler_subclassed` | A class in the files read subclasses the handler. The server may run that class instead. | Remove the subclass, or map the class the server runs. |
| `handler_other` | Another request-handler class is in the files read, or a request-handler base such as `BaseHTTPRequestHandler` is named anywhere but as the handler's base. It answers routes the bridge does not map. | Keep one request-handler class in the files read, or narrow `app_roots`. |
| `server_dispatch` | A server subclass, an unresolved constructor, a replaced dispatch hook or a local server module can answer before the handler. | Pass the handler to an unmodified `http.server.HTTPServer` or `ThreadingHTTPServer`, imported from the standard library, and remove dispatch replacements. |
| `server_hook` | The class overrides `handle`, `handle_one_request`, `parse_request` or `send_head` without calling its `super()`, or defines `__getattr__` or `__getattribute__`. | Remove the override, or call `super()` from it. |
| `pre_guard_hook` | A hook the server runs before the guard on every request, such as `setup`, `log_message` or `end_headers`, does more than call its own `super()` method, send constant headers or set a timeout. | Leave the hook to `BaseHTTPRequestHandler`, or reduce its body to those calls. |
| `guard_absent` | The class has no method named `guard.method`. | Name the method that checks the credential. |
| `guard_returns` | The guard has a `return`, so it can let a request through without the compare. | Deny by raising. |
| `guard_shape` | The guard holds a `try`, `with` or `yield`, or a statement other than `if <test>: raise ...`. | Write the guard as top-level `if` statements that each only raise. |
| `guard_reads_no_credential` | No top-level `if` in the guard compares the stated header and raises, with no `else`. | Compare `self.headers.get("<header>", ...)` with the expected value in its own top-level `if`, or correct `carrier_name`. |
| `guard_compare` | A guard test that reads the header is not the standard library's `compare_digest(<header read>, <expected>)` resolved by import, or `<header read> != <expected>`; or its expected side is a request attribute, a header, a local variable or a guard parameter. | Read the header inside the compare, use `hmac.compare_digest` or `secrets.compare_digest` imported with no alias, and compare with `self.server.<attr>` or a module-level constant. |
| `handler_shared_write` | A method of the handler class writes to `self.server` or to module state, so a request could set the value the guard compares. | Set the expected value at start, in the server or the module, and never from the handler. |
| `guard_before_compare` | A test before the credential compare does more than read headers against stored values or constants. | Move non-header tests after the compare; remove serving calls from header tests. |
| `guard_raise` | A raise before or at the compare constructs a value the reader cannot prove is a bounded exception class. | Raise a built-in exception or a module class with one direct built-in exception base and a plain constructor that only stores constant arguments. Keep its binding unchanged. |
| `guard_denial` | The first matching handler does not provably send 401 or 403 for the guard exception. | Catch the denial in every dispatcher and send 401 or 403 through one unconditional reply path. |
| `guard_call_args` | A `do_<METHOD>` calls the guard with an argument that is not a constant. Arguments run before the guard. | Pass constants only, as in `self.check(mutation=True)`. |
| `method_unmapped` | A `do_<METHOD>` answers requests, and no stated or public route has that method. | List its routes in `routes` or `public`. |
| `method_absent` | A route names a method the class has no `do_<METHOD>` for. | Correct the route's method, or remove the route. |
| `method_shape` | A `do_<METHOD>` is async or decorated, or its `try` has an `else` or a `finally`, which runs after the guard's outcome and can answer. | Use a plain `def` and a `try` with `except` handlers only. |
| `pre_guard_statement` | A statement other than a public-path block runs before the guard call. | Move it after the guard call, or make it an `if self.path in (...): ... return` block for public paths. |
| `guard_not_first` | A `do_<METHOD>` with stated routes does not call the guard as a statement after its public blocks. | Call `self.<guard>(...)` as that method's first statement after the public blocks. |
| `denial_handler` | An `except` handler does more than deny, or the reply method it calls does more than write the reply. | Keep each handler to `pass`, `raise`, `self.send_error(...)`, or one call to a reply method that only uses `send_response`, `send_header`, `end_headers` and `wfile`, with arguments that read only the caught exception. |
| `public_unstated` | The code answers a path before the guard that `public` does not list. | List the route in `public` and `public_routes`, or move it behind the guard. |
| `public_not_in_code` | A `public` route is not answered before the guard. | Remove it from `public`; if it is behind the guard, list it in `routes`. |
| `route_is_public` | A stated route is answered before the guard. | Move it to `public`. |
| `route_not_found` | A route's `match` literal is not in that `do_<METHOD>`, a method it calls, or a module constant it names (followed through `*OTHER` elements and dict keys). | Set `match` to the literal the code selects that route by. |

## What is stated by you

Some facts cannot be read from the bytes. The bridge states them, and the verdict prints each one as a premise with source `declared`:

- The routes your adapter lists are the routes you mean. Every request the unmodified standard-library server dispatches to the handler that is not on the public list reaches the guard first, read from the code.
- The value the guard compares the header against is a secret set at start and never empty.
- The reply your `except` handlers send on a denial carries only the error.
- Each sentence in `stated`.

Each premise ends "(stated by you)" and is counted in the bounds line as "declared premises: n". Each requirement row's reason ends "assuming your adapter's mapping (stated by you)", and the verdict's scope notes carry one line per premise beginning "Adapter bridge (assure.adapter-bridge/v1, re-read against your code on this run)". The pull request comment and the job summary list the same premises under the heading "Assuming your adapter (stated by you)". One premise is read from your code: whether the guard compares with `compare_digest`, a constant-time compare.
