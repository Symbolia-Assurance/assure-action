# Known issues

Answers Assure is known to give wrongly, as far as they are written up on this page. It is not a complete list; release notes name known issues too. Each entry names the profile and the requirement ids, what is read wrongly and which way an answer can be wrong, and the release that mends it once that is known. An entry leaves this page in the release that mends it, and that release's notes say so.

Declared PostgreSQL, row security (RLS-3, RLS-4): a restrictive policy written with no USING clause is read as hiding every row, where PostgreSQL applies no restriction for it. With such a policy RLS-4 can read holds for a view that runs with its owner's rights, and RLS-3 can read holds for an update, where neither should. Until this is mended, read RLS-3 and RLS-4 as not established on a table that has a restrictive policy without USING.

Mended in: not yet known.

Declared PostgreSQL, privileges (PRIV-1, PRIV-3, PRIV-4, GRANT-OPTION-POLICY): privileges granted on single columns of a table are not read. These answers are about privileges granted on the whole table; a column granted to a role, or to every role, does not change them. Where a table is sensitive, check its column grants yourself until Assure reads them.

Mended in: not yet known.

Declared PostgreSQL, search path (SD-1, SD-3): a schema name written in a search path setting without quotes and with a capital letter (for example search_path = 'Public, app'), in the settings file, set for a role or a database, or set on a function, is read as a name that matches no schema, where PostgreSQL folds it to lower case and searches that schema. With such a setting SD-3 can read holds while a schema on the session's path can be written to by an untrusted role, and SD-1 can read holds for a function that runs with its owner's rights while a schema on the function's own path can. Until this is mended, read SD-1 and SD-3 as not established where a search path setting holds an unquoted name with a capital letter, or write the names in lower case and check again.

Mended in: not yet known.
