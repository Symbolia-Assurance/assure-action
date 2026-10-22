## Instructions of this skill, not from the documents

- Choose the route from the repository and stated task; ask for the one data consent and only on an already-consented fallback for the separate GitHub-setting permission, each with its tradeoff.
- A section number in this skill names a numbered heading of the skill file the sentence names, or of the file the sentence is in; the skill folder carries every section it names.
- If the database is on Supabase, tell the operator so before any grant; do not grant `pg_monitor` and do not set it in `collection-privileges`.
- Show the operator `docs/DATA.md` before the first run, and ask before committing collected files to the repository.
- Never guess a data directory or a configuration directory: ask the server with `psql -c 'SHOW data_directory'`, `psql -c 'SHOW config_file'` and `psql -c 'SHOW hba_file'`.
- If this folder was copied without its checkout, install the Action at `@v0`; never guess a commit.
- Replace the example endpoint values with the operator's own; keep the top-level keys and the seven flags as shown.
- Before the run, check that the first line of each captured head begins with `HTTP/1.1`.
- Set up the Assure GitHub Action on a repository and read its result.
- On the Python route, release checks are a separately requested feature outside initial setup, adding one run per release and needing `contents: write` to write the report into the release notes (references/python.md, "Check each release").
- The commands for (a) and (b), the two ways to let the runner read the configuration files, are in references/postgres.md, section 6, with paths for Debian or Ubuntu; show them to the operator and let the operator choose and run one.

## Rules for an agent

When an agent sets up or runs the Action for you, these rules hold for it, as they do for you.

- Before it submits a contribution (an adapter bridge, a proposed formal model, or a coverage request that carries code locations) it asks "Would you like to submit this data to improve Assure's coverage of your requirements?", naming the files, lines or model it would send.
- It sends only on yes; on no it sends nothing and the run continues.
- It asks nothing about the report or the requirements text: they are defaults with opt-outs.
- Do not fabricate facts, edit redacted evidence, change database permissions to accommodate the checker, or change the pins to conceal a gap.
- Report the first line and each reading as the summary states it: a missing fact is reported as missing, with the place it was looked for.
- It shows you every command that changes your server, its files or its roles, and you run it.
- During normal served setup it uses its own GitHub access to open the setup pull request and changes no repository setting. Only on the fallback, after the initial data yes and a 404 or oversized setup request, it asks whether to turn on "Allow GitHub Actions to create and approve pull requests" when that setting is off. This is permission to change a repository setting, separate from the one data consent; it does not ask again to send the files. It reads the setting with `gh api repos/{owner}/{repo}/actions/permissions/workflow` and changes it only on that permission yes, with existing access, using `gh api -X PUT repos/{owner}/{repo}/actions/permissions/workflow -F can_approve_pull_request_reviews=true`. A setting no keeps it off: the job summary carries the drafts and a Commit this draft link instead. Release checks are a separately requested feature, outside initial setup. A contribution question is separate, only for an actual coverage gap, and names what would be sent.
- A run that read nothing never goes green: it is yellow and exits 3. When no obligation on the machines read holds, the first line says "nothing could be established". It never means "no issues".
- Outside the files and sends covered by your DATA.md consent, this rule holds: Never send your configuration files, your connection string or your API key.
- Create a new role. Use it for nothing else. The checker leaves the collection role out of every reading, so a role your site also uses would hide its own results.
- Grant it only these two roles. The collector refuses a broader role: `pg_monitor` or `pg_stat_scan_tables` in `collection-privileges` stops the Action with exit 2 (`bad_input`) before anything runs, and a role that belongs to either stops it with exit 3 (`collector_refused`). The collector also refuses to run if the role is a superuser, has `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`, or belongs to any other role.
