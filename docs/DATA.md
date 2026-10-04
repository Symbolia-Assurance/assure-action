# Your data

## What is collected

The collector runs in your runner. It connects as your collection role and runs a fixed, published set of `SELECT` queries in a read-only session. It reads:

- catalog views: roles, role memberships, objects and their ACLs, default ACLs, row-level security policies, functions, schemas, replication slots, publications and their tables, subscriptions and their tables, settings, the database list and its ACLs, and server times;
- configuration files, when it can read them: `postgresql.conf` and its includes, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and `postmaster.opts`.

It reads files only inside the data directory you give it (`data-dir`) and the configuration directories you name (`config-dirs`).

## What is never read

- Table contents.
- Password hashes (`pg_authid`) and whether a role has a password.
- Key material and key file contents.
- Other sessions' statements and the process list.

Secret-bearing values are withheld whole before anything is written. This covers passwords in connection strings, secret-named settings, and structured setting values such as `primary_conninfo` and `archive_command`. The subscription connection string (`subconninfo` in `pg_subscription`) is read by the collector's subscriptions query and withheld whole before anything is written. The collector then searches its own output for every value it withheld. If one is found, it deletes its output and stops, and nothing is sent.

## What leaves the runner

After the collector finishes, and before anything is checked or sent, the Action withholds free text in the runner:

- **Configuration comments.** In `postgresql.conf`, `postgresql.auto.conf`, `pg_hba.conf`, `pg_ident.conf` and every file they include, the text of every comment is replaced with `# <withheld comment>`. This covers whole-line comments, comments after a setting or a rule, and commented-out settings such as `#shared_buffers = 128MB`. Every line keeps its place and its line number, and the settings and rules themselves are sent as written. A `#` inside a quoted value is part of the value, not a comment. A line the Action cannot parse safely, such as one with an unclosed quote, is replaced with the same marker.
- **String literals in SQL expressions.** In row-level security policy expressions (`polqual` and `polwithcheck`), and in the `declared_predicate` of your declaration, every quoted string literal is replaced with `'<withheld literal N>'`. N numbers the different literals of one upload, so two equal literals get the same N. The rest of the expression, such as column names, operators and casts, is sent as written. An expression the Action cannot parse safely is withheld whole as one marker. No other SQL expression is collected: no view definitions, function bodies or column defaults.
- **Structured secret values** stay withheld whole by the collector, as above.

The Action does the same to an `artefacts` directory you made yourself. It works on the bytes it read, so your directory is not changed. The job log and the job summary state how many comments and literals were withheld. They show the counts only.

What still leaves the runner, as written:

- role names, and the names of databases, schemas, tables, views, functions, policies, publications and replication slots;
- ACLs, role memberships and role attributes;
- setting names and setting values that are not secret-bearing, such as `listen_addresses`, `port`, `ssl` and file paths;
- `pg_hba.conf` and `pg_ident.conf` rules as written: connection types, database and user names, client addresses and masks, authentication methods and options that are not secret-bearing, and identity-map names;
- policy expressions apart from their literals;
- the server version, the paths of the data and configuration directories, and the collector's record of what it read.

## What the Action sends

The Action sends the collected facts, after the withholding above, to `api.symbolia.ai` over HTTPS, with your API key, and the check runs on Symbolia's server. It sends only the files the profile reads, each within its size limit; it checks this in your runner before sending. Your database connection string and password stay in your runner.

The Action writes the verdict file, the job summary and the annotations in your runner. The job summary stays in your workflow run, under your own GitHub retention settings. The verdict file stays on the runner unless you upload it as a workflow artifact.

## On the server

The server is in Sydney, Australia.

| Data | Where it goes | How long it is kept |
|---|---|---|
| The collected facts you send | A scratch folder made for this one check, readable only by the service | Deleted when the check ends, whatever the result |
| The verdict | `store/<your account>/<check id>.json` | 30 days, then deleted |
| An `Idempotency-Key` you send | A small record beside the verdict: the check id and a SHA-256 of the request | Deleted with the verdict |
| Request log | One line per request on the server | 90 days |
| Charges | One ledger row per check the checker started: time, account, check id, bytes, tokens, cost, outcome | Kept to compute your credit |
| Your key | Stored only as a SHA-256 hash, with its key id and account | Kept after revocation, marked revoked |
| Backups | A daily copy of the key file (key hashes, key ids, accounts) and the charges ledger, readable only by the operator (mode 0600). Verdicts and collected facts are not backed up | 30 days, then deleted |
| Proxy log | The front proxy's own messages in the system journal: start-up, certificate renewal and errors. An error line can hold the client's IP address, the request method and path with its query, and the request headers with the `Authorization` header redacted. It never holds a request body. There is no access log | 90 days |

The scratch folder is removed when the check ends. If the server is stopped during a check, a daily cleanup job removes any scratch folder older than 30 minutes. When the server starts again, that check reads `checker_error` with the reason "the server restarted while this check was running; submit it again", and it is not charged.

The verdict holds the readings, which include facts observed from your files, such as role names and settings. It also holds each file's name, size and sha256. It holds no file contents.

The request log holds ids, sizes, outcomes and timings only: time, request id, key id, account, method, route, status, outcome, bytes in and out, file count, check id and duration. When a charge cannot be recorded, one more line says so (`event: charge`, `outcome: charge_failed`), with the account, check id, byte count and the check's outcome. The log never holds a request body, a file name, file contents, a key or a header value.

Each check runs in its own process, separate from the server process. Two things keep that process off the network:

- The serving code it runs imports no network client and no model client. A test enforces this: it reads every source file of the serving code and the Action and fails if one imports a network or model client module. The one exception is the Action's own client of the API, which runs in your runner.
- The server's systemd service configuration denies the service, the check process included, every outbound network address except the machine's own loopback.

## Tenant separation

- Each check gets its own scratch folder, created for that check alone and removed when it ends.
- Verdicts are stored per account. Check ids are random 128-bit values.
- Every read checks the account. Another account's check id reads `not_found`, the same as an id that does not exist.
- Idempotency keys are per account. The same key from two accounts names two separate checks.
- Nothing is cached across accounts.

## Questions

For a question about your data, or to ask for a key to be revoked, contact Symbolia.
