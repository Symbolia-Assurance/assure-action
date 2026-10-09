# Route 4: a MySQL submission

## 13. Checking MySQL from a submission

`mysql-declared-model` checks a MySQL server against a submission you produce. The Action has no MySQL collector, so you collect the file yourself and give the Action its folder with `artefacts`.

Give the Action an artefacts folder that holds one file, `raw/submission.json`. Its schema is `symbolia.mysql-declared-input.v0`. It carries `collection`, `declared_policy`, `grant_tables`, `mysql_user`, `system_variables`, `replication_channels`, `version` and `configuration_sha256`, with `material` set to `mysql` and the seven flags at their standing values (`execution_authorized`, `hardware_authorized`, `industrial_release_authorized`, `release_allowed`, `physical_validation` and `self_approved` false; `simulation` true).

The check reads the file and contacts no server. Seven machines read it: M1, M2, M3, M4, M6, M7 and M8. A machine whose section the submission lacks reads `representation`, with the machine's own reason. A submission that holds a secret, such as a password or a key, is refused before anything is read, and the refusal names the path and the kind, never the value.

A report for this profile is withheld with `profile_unqualified` until the report writer is qualified for MySQL. The obligation listing, requirements and formalisation for this profile arrive in a later release.
