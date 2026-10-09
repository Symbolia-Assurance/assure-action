# Route 4: a MySQL submission

## 13. Checking MySQL from a submission

`mysql-declared-model` checks a MySQL server against a `mysql://` connection and your declaration file, or against an artefacts directory holding `raw/submission.json`.

**With a connection (the collector runs in your runner):** set `connection` to a `mysql://user:pw@host:port/` URI or a keyword/value string (`mysql host=… port=… user=… password=…`), `profile` to `mysql-declared-model`, and `declaration` to the path of your declaration file (`symbolia.mysql-declaration.v0`). The password reaches the collector by environment only (`MYSQL_PWD`), never on a command line. `collection-role` defaults to the user in the connection.

**With artefacts (you collect yourself):** give the Action an artefacts folder that holds one file, `raw/submission.json`. Its schema is `symbolia.mysql-declared-input.v0`. It carries `collection`, `declared_policy`, `grant_tables`, `mysql_user`, `system_variables`, `replication_channels`, `version` and `configuration_sha256`, with `material` set to `mysql` and the seven flags at their standing values (`execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation` and `self_approved` false; `simulation` true).

The check reads the file and contacts no server. Seven machines read it: M1, M2, M3, M4, M6, M7 and M8. A machine whose section the submission lacks reads `representation`, with the machine's own reason. A submission that holds a secret, such as a password or a key, is refused before anything is read, and the refusal names the path and the kind, never the value.

A report for this profile is withheld with `profile_unqualified` until the report writer is qualified for MySQL. `/v1/profiles` lists the profile's 50 obligations with the states each can take (`holds`, `not_established`, `disproven`, from what its machine can produce), a `requirements.md` line that quotes an obligation binds to it, and the report page names the MySQL areas. The report stays withheld until the writer qualifies for MySQL. Formalisation is not offered for this profile.
