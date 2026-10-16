"""A proposed PostgreSQL declaration, drafted from the collector's catalog snapshot (DD-150, DD-156; issue #1186).

``python3.14 -B -m assure.declare_proposal raw/catalog_snapshot.json --out proposal.json [--requirements draft.md]``

The postgresql-declared-model profile reads raw/declaration.json (schema assure.postgresql.declaration/v1). Most of
its keys state what the operator intends, and the observed baseline answers those rows needs_intent. This module
drafts a declaration from the same catalog snapshot the collector wrote, so the customer reviews a filled draft in
place of typing each value. Only the committed raw/declaration.json is authority: a proposal alone changes no reading.

The record is ``{schema, stack, declaration, sources, confirm}``, the shape of the identity declaration proposal:

- ``declaration`` validates against assure/schemas/postgresql-declaration-v1.schema.json (assure.declare.validate).
- ``sources`` maps a JSON pointer to where its value came from: ``catalog_snapshot.json#<pointer>`` (the snapshot
  row the value was read from), ``COLLECTION-SIDECAR.json#<pointer>`` or ``argument:major`` (the major), or
  ``default:<reason>`` (a strict value that grants nothing, needed beside a proposed key). A key the snapshot gives
  no basis for is ``unread`` and is left out of ``declaration``: the drafter never invents an intent. The server key
  file's mode and owner (key_file_mode 0600, key_owner postgres; issue #2925) are file facts the snapshot cannot show:
  they are drafted as ``default:`` server defaults the customer confirms (the Director's ruling, 16 Oct 2026).
- ``confirm`` lists the keys whose value is a judgement the customer confirms before committing (every proposed key
  except the four observed facts: schema, major, collection_role, database_owner).

Each rule below drafts the strict reading of what the snapshot shows (access_paths_complete excepted: it is drafted
true beside protected_tables, always confirmed, since without it the row-security machine is refused). A value that would only widen what the checker
accepts (an empty untrusted-role list, an empty administrator list) is never drafted from an absence: that key stays
unread. A snapshot section the collector did not read (absent from the snapshot) is never read as empty.

The draft requirements.md (``requirements_draft``) holds the goals a person would write (``GOALS``), one plain
sentence each, for the obligation families the drafted declaration decides; the header is a Markdown heading, so the
matcher reads only the goals. Its companion (``typed_companion``, assure-requirements-typed.json) is a tree: each goal
pinned by its sentence's sha256 to its child typed rows (``ROWS``: the canonical statement the matcher establishes,
with its waypoint sentence and provenance). ``typed_text`` sends each unchanged goal as its children's typed rows
(issue #1186; coordination 7570, 7588).

Standard library only. No network, no database, no model call, no verdict.
execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PROPOSAL_SCHEMA = "assure.postgresql.declaration-proposal/v1"
STACK = "postgresql"
DECLARATION_SCHEMA = "assure.postgresql.declaration/v1"
FLAGS = {"execution_authorized": False, "hardware_authorized": False, "industrial_release_authorized": False,
         "release_allowed": False, "physical_validation": False, "simulation": True, "self_approved": False}
SNAP = "catalog_snapshot.json#"
#: the schema's role/object name pattern (postgresql-declaration-v1.schema.json); a name outside it is never proposed
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
ID_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
#: table privilege letters the declaration speaks of (aclitem letters r, a, w, d)
TABLE_PRIVS = {"r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE"}
TABLE_KINDS = ("r", "p")
#: the tls_floor values the declaration schema and the M3 explorer represent (postgresql-declaration-v1.schema.json)
TLS_VERSIONS = ("TLSv1", "TLSv1.1", "TLSv1.2", "TLSv1.3")
#: the derive step reads at most 32 privilege_queries rows (derive_lifted.py m1_acl scoped(...)[:32])
QUERY_CAP = 32
#: keys the snapshot gives no basis for: every one is reported unread, never drafted (observed needs_intent ids)
ALWAYS_UNREAD = (
    "disjoint_duties",      # PRIV-3: which duties must stay apart is the operator's division of work
    "declared_revokes",     # PRIV-6: which grants the operator means to revoke
    "intended_flows",       # HBA-2: pg_hba.conf is not in the catalog snapshot, and the flows are the operator's
    "standby_addresses",    # HBA-4: standby addresses are not in the catalog snapshot
    "certificate_roles",    # TLS-3: which roles must present a client certificate
    "no_loss_required",     # REP-3, REP-3-CONFIG: whether a committed transaction may be lost is the operator's
    "exclusive_reader",     # LR-1: which role alone may read the replication stream
    "authority_complete",   # SD-2: whether every authority over the caller's path is listed
    "owner_only_login",     # SD-2: whether only the owner logs in
    "caller",               # SD-2: which role calls the SECURITY DEFINER function
)
#: the observed facts drafted without confirmation (the observed baseline's overlay reads the same values)
OBSERVED_FACTS = ("schema", "major", "collection_role", "database_owner")


def _esc(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def parse_aclitem(item):
    """`grantee=privs/grantor` -> (grantee, [(letter, grant_option)], grantor); grantee '' is PUBLIC. None if unread."""
    if type(item) is not str:
        return None
    i, n = 0, len(item)

    def name(stop):
        nonlocal i
        if i < n and item[i] == '"':
            out, i = [], i + 1
            while i < n:
                if item[i] == '"':
                    if i + 1 < n and item[i + 1] == '"':
                        out.append('"')
                        i += 2
                        continue
                    i += 1
                    return "".join(out)
                out.append(item[i])
                i += 1
            return None
        start = i
        while i < n and item[i] not in stop:
            i += 1
        return item[start:i]
    grantee = name("=")
    if grantee is None or i >= n or item[i] != "=":
        return None
    i += 1
    privs = []
    while i < n and item[i] != "/":
        letter = item[i]
        if not letter.isalpha():
            return None
        option = i + 1 < n and item[i + 1] == "*"
        privs.append((letter, option))
        i += 2 if option else 1
    if i >= n or item[i] != "/":
        return None
    i += 1
    grantor = name("")
    if grantor is None or i != n or grantor == "":
        return None
    return (grantee or "PUBLIC"), privs, grantor


def strip_outer_parens(text):
    """`(a = b)` -> `a = b` when the outer pair encloses the whole expression (pg_get_expr wraps a top-level operator
    expression in one pair; a declaration states the predicate without it, and the derive step compares both forms
    equal after normalising)."""
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth, quote, closes_at_end = 0, None, True
        for index, ch in enumerate(text):
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and index != len(text) - 1:
                    closes_at_end = False
                    break
        if not closes_at_end or depth != 0:
            break
        text = text[1:-1].strip()
    return text


def _trivial(sql):
    return re.sub(r"\s+", " ", strip_outer_parens(str(sql))).strip().lower() in ("true", "false")


#: what a `true` clause opens, by command (pg_policy.polcmd): USING lets every row be read, changed or deleted, WITH
#: CHECK lets any row be added or written
_OPENS = {("polqual", "r"): "read every row of %s", ("polqual", "*"): "read and change every row of %s",
          ("polqual", "w"): "change every row of %s", ("polqual", "d"): "delete every row of %s",
          ("polwithcheck", "a"): "add rows to %s", ("polwithcheck", "*"): "add rows to %s",
          ("polwithcheck", "w"): "change rows of %s to any value"}


def _open_line(table, policies):
    """The heading line requirements.md carries for a table its own permissive `true` policies open (issue #1186):
    who can do what to its rows, which policies allow it, and the goal to add if it is not intended. Headings are
    never read as requirements."""
    acts, names = [], []
    for _index, policy in policies:
        if policy.get("polpermissive", True) is False:
            continue
        roles = policy.get("polroles")
        who = ("everyone" if not isinstance(roles, list) or not roles
               or "public" in [str(r).lower() for r in roles]
               or not all(type(r) is str and NAME.match(r) for r in roles) else "the roles " + _and(roles))
        for field in ("polqual", "polwithcheck"):
            what = _OPENS.get((field, policy.get("polcmd")))
            if what and type(policy.get(field)) is str and _is_true(policy[field]):
                act = "%s can %s" % (who, what % table)
                if act not in acts:
                    acts.append(act)
                name = policy.get("polname")
                if type(name) is str and '"' not in name and name not in names \
                        and not re.search(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", name) and len(name) <= 200:
                    names.append(name)
    if not acts:
        return None
    allows = (" (its polic%s %s allow%s it)" % ("y" if len(names) == 1 else "ies",
                                                 _and(['"%s"' % n for n in names]), "s" if len(names) == 1 else "")
              if names else "")
    goal = ("Each user sees only their own rows in %s." % table if any("read" in a for a in acts)
            else "Each user writes only their own rows in %s." % table)
    return ('## To confirm: %s%s. If that is not intended, add a goal such as "%s"'
            % (_and(acts), allows, goal))


def _is_true(sql):
    return re.sub(r"\s+", " ", strip_outer_parens(str(sql))).strip().lower() == "true"


#: issue #2573: the declared derive step (declared-derive derive_lifted.build_m5 term) reads a policy expression as
#: absent, `true`, `false` or the declared predicate by this normalised text; any other expression on the protected
#: table refuses the whole M5 machine (SQL-GRAMMAR), so a table carrying one is never drafted
GRAMMAR_REASON = "outside the declared model's tenant grammar (neither absent, true, false nor the row filter)"


def _norm_sql(text):
    return re.sub(r"\s+", " ", str(text).strip().strip("()")).strip().lower()


def _outside_grammar(predicate, policies):
    """The policy expressions on a table the declared derive step cannot read with `predicate` declared."""
    out = []
    for _index, policy in policies:
        for field, clause in (("polqual", "USING"), ("polwithcheck", "WITH CHECK")):
            sql = policy.get(field)
            if sql is not None and _norm_sql(sql) not in ("true", "false", _norm_sql(predicate)):
                out.append("policy %s %s" % (policy.get("polname"), clause))
    return out


#: issue #2551: the placeholder the withholding pass (action/withhold.py LITERAL_MARK) writes for a string literal
_PLACEHOLDER = re.compile(r"'<withheld literal [0-9]+>'")
_QUOTED = re.compile(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'')


def _placeholders(predicate, source):
    """Issue #2551: [{placeholder, source, literals}] for each withheld-literal placeholder a drafted predicate holds,
    `literals` the 1-based places among the expression's string literals where it stands, so the customer restores each
    from their own catalog; [] for a predicate drafted from an unwithheld snapshot."""
    places = {}
    quoted = [q for q in _QUOTED.findall(str(predicate)) if q.startswith("'")]
    for place, literal in enumerate(quoted, 1):
        if _PLACEHOLDER.fullmatch(literal):
            places.setdefault(literal, []).append(place)
    return [{"placeholder": k, "source": source, "literals": v} for k, v in places.items()]


class _Draft:
    def __init__(self):
        self.decl, self.sources, self.confirm, self.notes = {}, {}, [], []

    def put(self, key, value, source, confirm=True):
        """Draft `key`; `source` is one string for the key (every leaf under it) or {sub-pointer: string}."""
        self.decl[key] = value
        if isinstance(source, dict):
            for sub, where in source.items():
                self.sources["/" + _esc(key) + sub] = where
        else:
            self.sources["/" + _esc(key)] = source
        if confirm:
            self.confirm.append("/" + _esc(key))

    def unread(self, key, why):
        self.decl.pop(key, None)
        for pointer in [p for p in self.sources if p == "/" + _esc(key) or p.startswith("/" + _esc(key) + "/")]:
            del self.sources[pointer]
        if "/" + _esc(key) in self.confirm:
            self.confirm.remove("/" + _esc(key))
        self.sources["/" + _esc(key)] = "unread"
        self.notes.append({"key": key, "unread": why})


def _list_sources(pointers):
    return {"/%d" % i: where for i, where in enumerate(pointers)}


def _member_sources(rows):
    """[(member dict, source)] -> {"/i/field": source} for every scalar or list field of each member."""
    out = {}
    for i, (member, where) in enumerate(rows):
        for field, value in member.items():
            if isinstance(value, list):
                if not value:
                    out["/%d/%s" % (i, field)] = where
                for j, inner in enumerate(value):
                    if isinstance(inner, list):
                        for k in range(len(inner)):
                            out["/%d/%s/%d/%d" % (i, field, j, k)] = where
                    else:
                        out["/%d/%s/%d" % (i, field, j)] = where
            else:
                out["/%d/%s" % (i, field)] = where
    return out


def propose_with_notes(snapshot, *, major, major_source="argument:major"):
    """(record, notes): the proposal and the drafter's plain notes (what it left out and why), for the draft text."""
    if not isinstance(snapshot, dict):
        raise ValueError("catalog snapshot must be a JSON object")
    if type(major) is not int or major not in range(14, 19):
        raise ValueError("major must be an integer 14..18")
    d = _Draft()
    d.decl["schema"] = DECLARATION_SCHEMA
    d.put("major", major, major_source, confirm=False)

    def section(name):
        value = snapshot.get(name)
        return value if isinstance(value, list) else None

    roles_sec, members_sec = section("roles"), section("memberships")
    objects_sec, policies_sec = section("objects"), section("policies")
    databases_sec, default_sec = section("databases"), section("default_acl")
    pubs_sec, pubrels_sec = section("publications"), section("publication_rels")

    # collection_role: the account the collector ran as (collection.role), an observed fact
    block = snapshot.get("collection") if isinstance(snapshot.get("collection"), dict) else {}
    collector = block.get("role") if type(block.get("role")) is str and NAME.match(block.get("role")) else None
    if collector is not None and not collector.startswith("pg_") and collector != "PUBLIC":
        d.put("collection_role", collector, SNAP + "/collection/role", confirm=False)
    else:
        collector = None
        d.unread("collection_role", "the snapshot names no collection role (collection.role)")

    roles = {}
    for index, row in enumerate(roles_sec or []):
        if isinstance(row, dict) and type(row.get("rolname")) is str and row["rolname"] not in roles:
            roles[row["rolname"]] = (index, row)

    def customer(name):
        """A role the customer made: named within the schema pattern, not predefined, not the collection account."""
        return type(name) is str and bool(NAME.match(name)) and not name.startswith("pg_") and name != collector

    # database_owner: the connected database's owner (databases[is_current].owner), an observed fact
    current = [(i, row) for i, row in enumerate(databases_sec or []) if isinstance(row, dict) and row.get("is_current") is True]
    datname = None
    if len(current) == 1 and type(current[0][1].get("owner")) is str and NAME.match(current[0][1]["owner"]):
        d.put("database_owner", current[0][1]["owner"], SNAP + "/databases/%d/owner" % current[0][0], confirm=False)
        datname = current[0][1].get("datname") if type(current[0][1].get("datname")) is str else None
    else:
        d.unread("database_owner", "the snapshot has no single connected database row with an owner")
    owner = d.decl.get("database_owner")

    # id: a name for the declaration, from the connected database's name; the customer names it
    if datname:
        ident = (ID_CHARS.sub("-", datname).lstrip("-_.") or "database")[:118] + "-declared"
        d.put("id", ident, SNAP + "/databases/%d/datname" % current[0][0])
    else:
        d.put("id", "postgresql-declared", "default:the snapshot names no connected database; the customer names the declaration")

    # administrators (SU-1): the observed superusers other than the collection account
    if roles_sec is None:
        d.unread("administrators", "roles were not collected")
    else:
        admins = [(name, SNAP + "/roles/%d/rolsuper" % index) for name, (index, row) in roles.items()
                  if row.get("rolsuper") is True and customer(name)]
        if admins:
            d.put("administrators", [a for a, _ in admins], _list_sources([s for _, s in admins]))
        else:
            d.unread("administrators", "no superuser other than the collection account was observed")

    # table ACLs, read once: [(object index, row, [(grantee, letters, grantor)] or None)]
    tables, seen_names = [], set()
    for index, row in enumerate(objects_sec or []):
        if not isinstance(row, dict) or type(row.get("relname")) is not str or row.get("relkind") not in TABLE_KINDS:
            continue
        if row["relname"] in seen_names:  # the derive step keys objects by relname: the first row stands
            d.notes.append({"key": "objects", "note": "a second relation named %s was not read" % row["relname"]})
            continue
        seen_names.add(row["relname"])
        acl = row.get("relacl")
        items = None
        if isinstance(acl, list):
            items = [(j, parse_aclitem(item)) for j, item in enumerate(acl)]
        tables.append((index, row, items))

    # applications: customer logins that are not superusers, and customer roles that hold a table privilege; a role
    # that bypasses row security or is a superuser is never drafted as an application (the customer says so)
    apps = []
    if roles_sec is not None:
        for name, (index, row) in roles.items():
            if customer(name) and row.get("rolcanlogin") is True and row.get("rolsuper") is not True \
                    and row.get("rolbypassrls") is not True:
                apps.append((name, SNAP + "/roles/%d/rolcanlogin" % index))
        for index, row, items in tables:
            for j, parsed in items or []:
                if parsed is None:
                    continue
                grantee = parsed[0]
                if grantee in roles and customer(grantee) and grantee != row.get("owner") \
                        and roles[grantee][1].get("rolsuper") is not True and roles[grantee][1].get("rolbypassrls") is not True \
                        and any(letter in TABLE_PRIVS for letter, _ in parsed[1]) and grantee not in [a for a, _ in apps]:
                    apps.append((grantee, SNAP + "/objects/%d/relacl/%d" % (index, j)))
    if apps:
        d.put("applications", [a for a, _ in apps], _list_sources([s for _, s in apps]))
    else:
        d.unread("applications", "roles were not collected" if roles_sec is None else
                 "no customer login and no customer role holding a table privilege was observed")

    # privilege_queries (PRIV-1): the observed table grants to customer roles other than the owner
    if objects_sec is None or roles_sec is None:
        d.unread("privilege_queries", "objects or roles were not collected")
    else:
        queries = []
        for index, row, items in tables:
            if not NAME.match(row["relname"]):
                continue
            for j, parsed in items or []:
                if parsed is None or parsed[0] not in roles or not customer(parsed[0]) or parsed[0] == row.get("owner"):
                    continue
                for letter in ("r", "a", "w", "d"):
                    if letter in [l for l, _ in parsed[1]]:
                        member = {"object": row["relname"], "privilege": TABLE_PRIVS[letter], "role": parsed[0]}
                        if member not in [m for m, _ in queries]:
                            queries.append((member, SNAP + "/objects/%d/relacl/%d" % (index, j)))
        if len(queries) > QUERY_CAP:
            d.notes.append({"key": "privilege_queries", "note": "%d observed grants; the first %d are drafted (the "
                            "derive step reads at most %d)" % (len(queries), QUERY_CAP, QUERY_CAP)})
            queries = queries[:QUERY_CAP]
        if queries:
            d.put("privilege_queries", [m for m, _ in queries], _member_sources(queries))
        else:
            d.unread("privilege_queries", "no table grant to a customer role other than the owner was observed")

    # sensitive_objects (PRIV-4, GRANT-OPTION-POLICY) and the row-security keys: the customer's own signal is row
    # security switched on for a table
    rls_tables = [(index, row) for index, row, _items in tables if row.get("relrowsecurity") is True and NAME.match(row["relname"])]
    if objects_sec is None:
        d.unread("sensitive_objects", "objects were not collected")
    elif rls_tables:
        d.put("sensitive_objects", [row["relname"] for _, row in rls_tables],
              _list_sources([SNAP + "/objects/%d/relrowsecurity" % index for index, _ in rls_tables]))
    else:
        d.unread("sensitive_objects", "no table with row security switched on was observed")

    # default_acl_expectations (PRIV-5): each schema-scoped table default as observed (global defaults name no schema)
    if default_sec is None:
        d.unread("default_acl_expectations", "default privileges were not collected")
    else:
        expectations = []
        for index, row in enumerate(default_sec):
            if not isinstance(row, dict) or row.get("defaclobjtype", "r") not in ("r",):
                continue
            creator, schema = row.get("defaclrole"), row.get("defaclnamespace")
            if type(schema) is not str or not NAME.match(schema) or type(creator) is not str or not NAME.match(creator):
                if schema in (None, ""):
                    d.notes.append({"key": "default_acl_expectations",
                                    "note": "a global default for %s names no schema and was not drafted" % creator})
                continue
            pairs = []
            for item in row.get("defaclacl") or []:
                parsed = parse_aclitem(item)
                if parsed is None or not (parsed[0] == "PUBLIC" or NAME.match(parsed[0])):
                    continue
                for letter in ("r", "a", "w", "d"):
                    if letter in [l for l, _ in parsed[1]] and [parsed[0], TABLE_PRIVS[letter]] not in pairs:
                        pairs.append([parsed[0], TABLE_PRIVS[letter]])
            expectations.append(({"creator": creator, "expected_acl": pairs, "kind": "table", "schema": schema},
                                 SNAP + "/default_acl/%d" % index))
        if expectations:
            d.put("default_acl_expectations", [m for m, _ in expectations], _member_sources(expectations))
        else:
            d.unread("default_acl_expectations", "no schema-scoped table default privilege was observed")

    # replication_roles (HBA-4): customer logins with the replication attribute (never drafted empty)
    if roles_sec is None:
        d.unread("replication_roles", "roles were not collected")
    else:
        repl = [(name, SNAP + "/roles/%d/rolreplication" % index) for name, (index, row) in roles.items()
                if customer(name) and row.get("rolreplication") is True and row.get("rolsuper") is not True]
        if repl:
            d.put("replication_roles", [a for a, _ in repl], _list_sources([s for _, s in repl]))
        else:
            d.unread("replication_roles", "no customer role with the replication attribute was observed")

    # protected_tables, declared_predicate, required_policies (RLS-2, RLS-3): the row-security tables whose policies
    # carry exactly one non-trivial USING expression, grouped by it; the largest group (first in snapshot order on a
    # tie) is drafted, since the declaration states one predicate. Issue #1186: a table with a permissive policy whose
    # USING or WITH CHECK is `true` admits every row by its own policy (Supabase's "viewable by everyone"): the
    # snapshot shows no tenant boundary there, so it is never drafted as protected (the customer says so)
    if objects_sec is None or policies_sec is None:
        for key in ("protected_tables", "declared_predicate", "required_policies"):
            d.unread(key, "objects or policies were not collected")
    else:
        by_table = {}
        for index, row in enumerate(policies_sec):
            if isinstance(row, dict) and type(row.get("polrelid")) is str:
                by_table.setdefault(row["polrelid"], []).append((index, row))
        groups, off_grammar = {}, []
        for index, row in rls_tables:
            open_to_all = [str(policy.get("polname")) for _pindex, policy in by_table.get(row["relname"], [])
                           if policy.get("polpermissive", True) is not False
                           and any(type(policy.get(f)) is str and _is_true(policy[f])
                                   for f in ("polqual", "polwithcheck"))]
            if open_to_all:
                d.notes.append({"key": "protected_tables", "note": "table %s has a policy that admits every row (%s); "
                                "its rows are open by its own policy, so it was not drafted as protected"
                                % (row["relname"], "; ".join(open_to_all)), "table": row["relname"],
                                "open": _open_line(row["relname"], by_table.get(row["relname"], []))})
                continue
            quals = {}
            for pindex, policy in by_table.get(row["relname"], []):
                qual = policy.get("polqual")
                if type(qual) is str and not _trivial(qual):
                    quals.setdefault(strip_outer_parens(qual), pindex)
            if len(quals) == 1:
                (predicate, pindex), = quals.items()
                outside = _outside_grammar(predicate, by_table.get(row["relname"], []))
                if outside:
                    off_grammar.append(row["relname"])
                    d.notes.append({"key": "protected_tables", "note": "table %s has a policy expression %s (%s); "
                                    "not drafted" % (row["relname"], GRAMMAR_REASON, "; ".join(outside))})
                    continue
                groups.setdefault(predicate, []).append((index, row, pindex))
            else:
                d.notes.append({"key": "protected_tables", "note": "table %s has %d distinct row filters; not drafted"
                                % (row["relname"], len(quals))})
        if not groups:
            for key in ("protected_tables", "declared_predicate", "required_policies"):
                d.unread(key, "the row filter of %s is %s" % (_and(off_grammar), GRAMMAR_REASON) if off_grammar
                         else "no row-security table with a single row filter was observed")
        else:
            predicate = max(groups, key=lambda p: (len(groups[p]), -groups[p][0][0]))
            chosen = groups[predicate]
            d.put("protected_tables", [row["relname"] for _, row, _ in chosen],
                  _list_sources([SNAP + "/objects/%d/relrowsecurity" % index for index, _, _ in chosen]))
            d.put("declared_predicate", predicate, SNAP + "/policies/%d/polqual" % chosen[0][2])
            restore = _placeholders(predicate, SNAP + "/policies/%d/polqual" % chosen[0][2])
            if restore:
                d.notes.append({"key": "declared_predicate", "restore": restore, "note": (
                    "declared_predicate holds %s, string literals the withholding pass replaced in policy %s USING (%s); "
                    "before committing, replace %s with the string literal at that place in your own catalog (counting "
                    "the expression's string literals from 1), or the upload withholds the placeholder as a new literal, "
                    "the policy no longer equals the declared predicate and the row-security machine (M5) is refused"
                    % (_and([e["placeholder"] for e in restore]),
                       policies_sec[chosen[0][2]].get("polname"), restore[0]["source"],
                       "; ".join("%s with literal %s" % (e["placeholder"], ", ".join(map(str, e["literals"])))
                                 for e in restore)))})
            # access_paths_complete: the snapshot's grants, memberships and views are every route the derive step
            # reads; true states that no route outside them reaches the tables (the M5 machine is refused, A-G02,
            # until it is declared). It is the customer's judgement, so it is always confirmed; the derive step still
            # reads it false when an ACL item, a view's base tables or a relation kind is unreadable.
            d.put("access_paths_complete", True,
                  SNAP + "/objects/%d/relacl" % chosen[0][0] if "relacl" in chosen[0][1] else SNAP + "/objects/%d" % chosen[0][0])
            names, skipped = [], []
            for _, row, _ in chosen:
                for pindex, policy in by_table.get(row["relname"], []):
                    name = policy.get("polname")
                    if type(name) is str and NAME.match(name):
                        if name not in [n for n, _ in names]:
                            names.append((name, SNAP + "/policies/%d/polname" % pindex))
                    else:
                        skipped.append(str(name))
            if skipped:
                d.notes.append({"key": "required_policies", "note": "%d policies have names the declaration format "
                                "cannot hold: %s" % (len(skipped), "; ".join(skipped))})
            if names:
                d.put("required_policies", [n for n, _ in names], _list_sources([s for _, s in names]))
            else:
                d.unread("required_policies", "no policy on the drafted tables has a name the declaration format holds")
            # rls_exempt_logins (RLS-1, RLS-3; issue #1186): the drafted administrators that can log in. A superuser
            # bypasses row security whatever is declared, and SU-1 holds the superuser set to the administrators
            exempt = [(name, SNAP + "/roles/%d/rolsuper" % roles[name][0]) for name in d.decl.get("administrators", [])
                      if name in roles and roles[name][1].get("rolcanlogin") is True]
            if exempt:
                d.put("rls_exempt_logins", [n for n, _ in exempt], _list_sources([w for _, w in exempt]))
            else:
                d.put("rls_exempt_logins", [], "default:[] exempts no login from row security")
            d.put("view_exemptions", [], "default:[] exempts no view from row security")

    # intended_tables (LR-1-SCOPE): the tables the observed publications name (none when no publication exists)
    if pubs_sec is None or pubrels_sec is None:
        d.unread("intended_tables", "publications were not collected")
    else:
        published = []
        for index, row in enumerate(pubrels_sec):
            if isinstance(row, dict) and type(row.get("relname")) is str and NAME.match(row["relname"]) \
                    and row["relname"] not in [n for n, _ in published]:
                published.append((row["relname"], SNAP + "/publication_rels/%d/relname" % index))
        if published:
            d.put("intended_tables", [n for n, _ in published], _list_sources([s for _, s in published]))
        elif not pubs_sec:
            d.put("intended_tables", [], SNAP + "/publications")
        else:
            d.unread("intended_tables", "publications exist but name no table (FOR ALL TABLES or by schema)")

    # untrusted_roles (SD-2): the drafted applications that neither own the database nor hold superuser or
    # createrole (never drafted empty: an empty list would make no schema writable)
    untrusted = []
    for i, name in enumerate(d.decl.get("applications", [])):
        row = roles.get(name, (None, {}))[1]
        if name != owner and row.get("rolsuper") is not True and row.get("rolcreaterole") is not True:
            untrusted.append((name, d.sources["/applications/%d" % i]))
    if untrusted:
        d.put("untrusted_roles", [n for n, _ in untrusted], _list_sources([s for _, s in untrusted]))
    else:
        d.unread("untrusted_roles", "no application role outside the owner and the administrators was drafted")

    # tls_floor (TLS-1..TLS-5; issue #2555): the floor the server enforces today (pg_settings ssl_min_protocol_version),
    # confirmed, since raising it is the operator's choice; a value the declared model cannot represent stays unread
    floor = [(i, row) for i, row in enumerate(section("pg_settings") or [])
             if isinstance(row, dict) and row.get("name") == "ssl_min_protocol_version"]
    if not floor:
        d.unread("tls_floor", "ssl_min_protocol_version was not collected (pg_settings)")
    elif floor[0][1].get("setting") in TLS_VERSIONS:
        d.put("tls_floor", floor[0][1]["setting"], SNAP + "/pg_settings/%d/setting" % floor[0][0])
    else:
        d.unread("tls_floor", "the observed ssl_min_protocol_version is not a TLS version name (%s)"
                 % ", ".join(TLS_VERSIONS))
    # key_file_mode, key_owner (TLS-1..TLS-5 after the floor; issue #2925): file facts the snapshot cannot show, so the
    # server defaults are drafted for the customer to confirm (the Director's ruling, 16 Oct 2026)
    d.put("key_file_mode", "0600",
          "default:0600, owner read-write only, the mode PostgreSQL accepts for a key its own user owns")
    d.put("key_owner", "postgres", "default:postgres, the server's own operating-system user owns the key file")

    for key in ALWAYS_UNREAD:
        d.unread(key, "the catalog snapshot gives no basis for it; the customer states it")

    declaration = dict(sorted(d.decl.items()))
    declaration.update(FLAGS)
    declaration = dict(sorted(declaration.items()))
    record = {"schema": PROPOSAL_SCHEMA, "stack": STACK, "declaration": declaration,
              "sources": dict(sorted(d.sources.items())), "confirm": sorted(d.confirm)}
    return record, d.notes


def propose(snapshot, *, major, major_source="argument:major"):
    """Draft the declaration proposal for `snapshot` (a catalog_snapshot.json object) at server `major`."""
    return propose_with_notes(snapshot, major=major, major_source=major_source)[0]


#: the requirement rows the draft can carry (issue #1186; coordination 7570, 7588): (obligation id, the declaration keys
#: it rests on, the obligation's canonical statement in the postgresql-declared-model profile, package-model-003
#: models/M*/MACHINE.json). The requirements matcher (serve/requirements.py) establishes a line only when its sentence is
#: that statement. An obligation is drafted only when every key it rests on is drafted; a key marked `?` is named when
#: drafted, and the obligation is decided without it (measured on D-g with the declared profile).
#: tests/serving/test_issue_1186_typed_rows_accept.py pins each statement to the profile.
ROWS = (
    ("PRIV-1", ("privilege_queries",),
     "Compute declared ordinary ACL queries as direct/inherited/after_set/not_held with derived path; explicit "
     "broad-role/RLS uncertainty is missing_method."),
    ("PRIV-4", ("sensitive_objects",),
     "No sensitive object in the supplied finite object list has an explicit/effective PUBLIC ACL entry."),
    ("PRIV-5", ("default_acl_expectations",),
     "For each declared future creator/schema query, resolved global ACL union additive schema ACL equals declared "
     "expected ACL; existing objects remain separate."),
    ("GRANT-OPTION-POLICY", ("sensitive_objects", "administrators"),
     "Additional declared policy: no sensitive-object grant option outside administrators, including owner implicit "
     "grant options independent of ordinary ACL contents. Not a vendor policy."),
    ("SU-1", ("administrators", "applications?"),
     "Direct rolsuper set equals declared administrator set and includes no application login."),
    ("RLS-1", ("protected_tables", "rls_exempt_logins", "access_paths_complete"),
     "Each protected table/non-exempt login path is RLS enabled, owner only with FORCE, no superuser/BYPASSRLS reach."),
    ("RLS-2", ("protected_tables", "required_policies?", "declared_predicate", "access_paths_complete"),
     "Required policies exist; every applicable permissive predicate implies the declared tenant predicate."),
    ("RLS-3", ("protected_tables", "declared_predicate", "access_paths_complete"),
     "INSERT/UPDATE admission implies the declared new-row predicate through explicit CHECK or implicit USING."),
    ("RLS-4", ("protected_tables", "view_exemptions", "access_paths_complete"),
     "No non-exempt view-owner read path over protected tables."),
    ("LR-1-SCOPE", ("intended_tables",),
     "Published tables, including modeled future FOR ALL TABLES members, stay within declared intent."),
)
_PATHS = ", and every way to reach them is a grant, membership or view in the catalog."
#: the plain-English face of each row: (template, values the template fixes) in the order tried; a {key} is the
#: drafted value in words (`_phrase`), read back by `_unphrase`
ENGLISH = {
    "PRIV-1": (("These table privileges are held as declared: {privilege_queries}.", {}),),
    "PRIV-4": (("PUBLIC holds no privilege on the sensitive tables {sensitive_objects}.", {}),),
    "PRIV-5": (("New tables get exactly these default privileges: {default_acl_expectations}.", {}),),
    "GRANT-OPTION-POLICY": (("Only {administrators} may hold a grant option on the sensitive tables "
                             "{sensitive_objects}.", {}),),
    "SU-1": (("Only {administrators} may hold superuser, and the application logins {applications} are not "
              "superusers.", {}),
             ("Only {administrators} may hold superuser.", {})),
    "RLS-1": (("Row security covers every login that reaches {protected_tables}" + _PATHS,
               {"rls_exempt_logins": [], "access_paths_complete": True}),
              ("Row security covers every login that reaches {protected_tables}, except {rls_exempt_logins}" + _PATHS,
               {"access_paths_complete": True})),
    "RLS-2": (("Each tenant reads only the rows of {protected_tables} where {declared_predicate}, through the policies "
               "{required_policies}" + _PATHS, {"access_paths_complete": True}),
              ("Each tenant reads only the rows of {protected_tables} where {declared_predicate}" + _PATHS,
               {"access_paths_complete": True})),
    "RLS-3": (("Each tenant inserts or updates only rows of {protected_tables} where {declared_predicate}" + _PATHS,
               {"access_paths_complete": True}),),
    "RLS-4": (("No view reads {protected_tables} past row security" + _PATHS,
               {"view_exemptions": [], "access_paths_complete": True}),
              ("No view except {view_exemptions} reads {protected_tables} past row security" + _PATHS,
               {"access_paths_complete": True})),
    "LR-1-SCOPE": (("Logical replication publishes no table.", {"intended_tables": []}),
                   ("Logical replication publishes only {intended_tables}.", {})),
}
#: issue #2893: the fill-in lines the draft offers when no table was drafted as protected or one was left out as open,
#: each the ENGLISH forms of its obligations joined by a space: RLS-1 + RLS-2 (row security on each user-data table,
#: with a policy keyed on the caller) and RLS-3 (the ownership check). The snapshot carries no column names, so the
#: tables and the caller predicate are the user's to fill in
TEMPLATES = (("RLS-1", "RLS-2"), ("RLS-3",))
_FILL = {"protected_tables": "<tables>", "declared_predicate": "`<caller predicate>`"}
#: the goals a person would write, each over the obligation family it rolls up (key, sentence, obligations): a goal
#: is drafted when at least one of its obligations is; its sentence names no role, table or obligation
GOALS = (
    ("access", "Only the people who run the database can change who has access to it.",
     ("SU-1", "GRANT-OPTION-POLICY", "PRIV-1", "PRIV-4", "PRIV-5")),
    ("tenant", "Each user sees only their own data.", ("RLS-1", "RLS-2", "RLS-3", "RLS-4")),
    ("replication", "Only the data meant to be shared leaves the database through replication.", ("LR-1-SCOPE",)),
)
#: drafted keys no requirement row rests on, and why (the draft's notes name them)
NO_ROW = {
    "id": "it names the declaration; no obligation reads it",
    "tls_floor": "TLS-1 to TLS-5 rest on it with key_file_mode and key_owner; the draft carries no TLS goal",
    "key_file_mode": "a drafted server default: TLS-1 to TLS-5 rest on it with tls_floor and key_owner; the draft "
                     "carries no TLS goal",
    "key_owner": "a drafted server default: TLS-1 to TLS-5 rest on it with tls_floor and key_file_mode; the draft "
                 "carries no TLS goal",
    "replication_roles": "HBA-4 also needs standby_addresses, which the catalog snapshot does not give",
    "untrusted_roles": "SD-1 and SD-3 also need the authority closure (authority_complete, caller), which the catalog "
                       "snapshot does not give",
}
#: the companion of the draft: each goal line, keyed by its sha256, with its child typed rows (`typed_companion`)
TYPED_SCHEMA = "assure.requirements-typed/v1"
TYPED_PROFILE = "postgresql-declared-model"
#: the longest waypoint sentence drafted (serve/requirements.py reads lines of at most 8 KiB)
LINE_CAP = 3072
#: the most open-table lines requirements.md carries (the rest are counted; the companion's notes name each)
OPEN_CAP = 20
_N = NAME.pattern[1:-2]     # the name pattern without its anchors
_PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE")
_PLACE = re.compile(r"\{([a-z_]+)\}")
_GID = re.compile(r"G[1-9][0-9]{0,5}\Z")
_MARKER = re.compile(r"(?:[-*+]\s+|\d+[.)]\s+)")


def _and(words):
    """a | a and b | a, b and c"""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _unand(text):
    parts = text.split(", ")
    last = parts[-1].split(" and ")
    if len(last) > 2 or (len(parts) > 1 and len(last) != 2):
        return None
    return parts[:-1] + last


def _runs(pairs):
    """[(head, privilege)] -> [(head, [privileges])], consecutive equal heads joined (order kept)."""
    out = []
    for head, privilege in pairs:
        if out and out[-1][0] == head:
            out[-1][1].append(privilege)
        else:
            out.append((head, [privilege]))
    return out


def _phrase(key, value):
    """The plain words for one drafted value, or None when it has none (an empty list, an unknown shape)."""
    if key == "declared_predicate":
        return "`%s`" % value if isinstance(value, str) else None
    if not isinstance(value, list) or not value:
        return None
    if key == "privilege_queries":
        return "; ".join("%s %s on %s" % (role, _and(privs), obj) for (role, obj), privs in
                         _runs([((m["role"], m["object"]), m["privilege"]) for m in value]))
    if key == "default_acl_expectations":
        if any(m.get("kind") != "table" for m in value):
            return None
        return ", while ".join("tables %s creates in %s grant %s" % (m["creator"], m["schema"], "; ".join(
            "%s %s" % (g, _and(privs)) for g, privs in _runs(m["expected_acl"])) or "nothing") for m in value)
    return _and([str(name) for name in value])


def _privs(text):
    privs = _unand(text)
    return privs if privs and all(p in _PRIVS for p in privs) else None


def _unphrase(key, text):
    """`_phrase` read back: the drafted value, or None when the words are not its phrase."""
    if key == "declared_predicate":
        return text[1:-1] if len(text) > 1 and text[0] == text[-1] == "`" else None
    if key == "privilege_queries":
        out = []
        for part in text.split("; "):
            m = re.fullmatch(r"(%s) (.+) on (%s)" % (_N, _N), part)
            privs = _privs(m.group(2)) if m else None
            if privs is None:
                return None
            out += [{"object": m.group(3), "privilege": p, "role": m.group(1)} for p in privs]
        return out
    if key == "default_acl_expectations":
        out = []
        for part in text.split(", while "):
            m = re.fullmatch(r"tables (%s) creates in (%s) grant (.+)" % (_N, _N), part)
            if m is None:
                return None
            pairs = []
            for group in ([] if m.group(3) == "nothing" else m.group(3).split("; ")):
                g = re.fullmatch(r"(%s) (.+)" % _N, group)
                privs = _privs(g.group(2)) if g else None
                if privs is None:
                    return None
                pairs += [[g.group(1), p] for p in privs]
            out.append({"creator": m.group(1), "expected_acl": pairs, "kind": "table", "schema": m.group(2)})
        return out
    names = _unand(text)
    return names if names and all(NAME.match(n) for n in names) else None


def english(row):
    """The plain-English sentence of a typed row ({obligation, statement, values}), built from the drafted values; None
    when no template of the obligation says them."""
    for template, fixed in ENGLISH.get(row["obligation"], ()):
        named = _PLACE.findall(template)
        if set(named) | set(fixed) != set(row["values"]) or any(row["values"][k] != v for k, v in fixed.items()):
            continue
        words = {key: _phrase(key, row["values"][key]) for key in named}
        if None not in words.values():
            return template.format(**words)
    return None


def parse_english(sentence):
    """`english` read back to its typed row, or None when the sentence is not one."""
    for obligation, _keys, statement in ROWS:
        for template, fixed in ENGLISH[obligation]:
            named = _PLACE.findall(template)
            pattern = "".join(re.escape(piece) if i % 2 == 0 else "(.*?)"
                              for i, piece in enumerate(_PLACE.split(template)))
            m = re.fullmatch(pattern, sentence, re.S)
            if m is None:
                continue
            values = dict(fixed, **{key: _unphrase(key, text) for key, text in zip(named, m.groups())})
            if any(value is None for value in values.values()):
                continue
            order = [k.rstrip("?") for k in _keys if k.rstrip("?") in values]
            row = {"obligation": obligation, "statement": statement, "values": {k: values[k] for k in order}}
            if english(row) == sentence:
                return row
    return None


def template_line(obligations):
    """The fill-in line of a TEMPLATES entry: per obligation the first ENGLISH form that names only the protected
    tables and the predicate, `<tables>` and `<caller predicate>` in place of the values."""
    return " ".join(next(template.format(**_FILL) for template, _fixed in ENGLISH[o]
                         if set(_PLACE.findall(template)) <= set(_FILL)) for o in obligations)


def parse_template(sentence):
    """Issue #2893: a filled TEMPLATES line read back (`parse_english`, one sentence per obligation) to its typed rows,
    all over the same protected tables; None when the sentence is not one."""
    for obligations in TEMPLATES:
        cuts = [m.end() for m in re.finditer(r"\. ", sentence)] if len(obligations) == 2 else []
        for parts in ([[sentence]] if len(obligations) == 1 else
                      [[sentence[:cut - 1], sentence[cut:]] for cut in cuts]):
            rows = [parse_english(part) for part in parts]
            if None not in rows and [r["obligation"] for r in rows] == list(obligations) \
                    and len({json.dumps(r["values"]["protected_tables"]) for r in rows}) == 1:
                return rows
    return None


def _one_line(text, cap=LINE_CAP):
    return (isinstance(text, str) and len(text.encode("utf-8")) <= cap
            and not re.search(r"[\x00-\x1f\x7f-\x9f  ]", text))


def _drafted(record):
    """(rows, left): the typed rows the drafted declaration decides, in ROWS order, and a note for each obligation left
    out because its English is not one line that reads back to the same row."""
    decl, rows, left = record["declaration"], [], []
    for obligation, keys, statement in ROWS:
        if not all(key in decl for key in keys if not key.endswith("?")):
            continue
        row = {"obligation": obligation, "statement": statement,
               "values": {key.rstrip("?"): decl[key.rstrip("?")] for key in keys if key.rstrip("?") in decl}}
        face = english(row)
        if not _one_line(face) or parse_english(face) != row:
            left.append("%s has no row: its value does not read back from one plain line" % obligation)
            continue
        rows.append(row)
    return rows, left


def typed_rows(record):
    """The typed requirement rows the drafted declaration decides: [{obligation, statement, values}], in ROWS order.
    `values` holds each key the row rests on, as drafted. Every row's `english` reads back to it."""
    return _drafted(record)[0]


def row_line(rid, row):
    """The typed requirements line of a row: the matcher's `ID [postgres]: sentence` with the canonical statement."""
    return "- %s [postgres]: %s" % (rid, row["statement"])


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def goal_sentence(key):
    """The goal sentence of a goal key, or None."""
    return next((sentence for k, sentence, _obligations in GOALS if k == key), None)


def parse_goal(sentence):
    """The goal key of a goal sentence, or None."""
    return next((k for k, s, _obligations in GOALS if s == sentence), None)


def drafted_goals(record):
    """[{key, english, rows}]: each goal (GOALS order) with at least one typed row the drafted declaration decides,
    its rows in the goal's order."""
    rows = {row["obligation"]: row for row in typed_rows(record)}
    return [{"key": key, "english": sentence, "rows": [rows[o] for o in obligations if o in rows]}
            for key, sentence, obligations in GOALS if any(o in rows for o in obligations)]


def _left(record, notes):
    """The drafter's notes: obligations with no row and why, drafted keys no row rests on, and `notes`."""
    decl = record["declaration"]
    rows, left = _drafted(record)
    used = {key for row in rows for key in row["values"]}
    for obligation, keys, _statement in ROWS:
        required = [key for key in keys if not key.endswith("?")]
        missing = [key for key in required if key not in decl]
        if missing and len(missing) < len(required):
            left.append("%s has no row: it also needs %s, which is not drafted" % (obligation, ", ".join(missing)))
    for key in sorted(k for k in decl if "/" + _esc(k) in record["confirm"] and k not in used):
        left.append("%s is drafted with no row: %s" % (key, NO_ROW.get(key, "no obligation rests on it alone")))
    return left + [n["note"] for n in notes if "note" in n]


def typed_companion(record, text, drafted_from=None, notes=()):
    """The companion of the draft `text` (assure-requirements-typed.json beside it), a tree: the sha256 of `text`
    (`source_sha256`), what the proposal was drafted from (`drafted_from`), the drafter's notes, and per goal its id
    (G1..), key, sentence, the sentence's sha256 and 1-based `line` in `text`, `status` (proposed: committing the file
    is the acceptance, DD-150) and its child rows: id (G1.1..), obligation, canonical statement (the typed row the
    matcher establishes), waypoint sentence (`english`), declaration keys and values, and the snapshot rows each key
    was drafted from. The customer never edits it; `typed_text` reads it."""
    lines = text.split("\n")
    goals = []
    for g, goal in enumerate(drafted_goals(record), 1):
        children = []
        for c, row in enumerate(goal["rows"], 1):
            provenance = {key: sorted({source for pointer, source in record["sources"].items()
                                       if pointer == "/" + _esc(key) or pointer.startswith("/" + _esc(key) + "/")})
                          for key in row["values"]}
            children.append({"id": "G%d.%d" % (g, c), "obligation": row["obligation"], "statement": row["statement"],
                             "english": english(row), "keys": list(row["values"]), "values": row["values"],
                             "provenance": provenance})
        goals.append({"id": "G%d" % g, "key": goal["key"], "english": goal["english"], "sha256": _sha(goal["english"]),
                      "line": lines.index("- " + goal["english"]) + 1 if "- " + goal["english"] in lines else None,
                      "status": "proposed", "rows": children})
    return dict({"schema": TYPED_SCHEMA, "profile": TYPED_PROFILE, "source_sha256": _sha(text),
                 "drafted_from": drafted_from, "notes": _left(record, notes), "goals": goals}, **FLAGS)


def _companion(companion):
    """Whether `companion` is a typed companion: its schema and profile, and a list of goals (which may be empty)."""
    return (isinstance(companion, dict) and companion.get("schema") == TYPED_SCHEMA
            and companion.get("profile") == TYPED_PROFILE and isinstance(companion.get("goals"), list))


def _goals(companion):
    """{sha256: {id, english, line, rows: [(id, statement, waypoint)]}} of the companion goals that check: the goal
    sentence is its key's, its sha256 is that sentence's, and every child is one of the goal's obligations with its
    obligation's statement, the waypoint its own values render, and the id G<n>.<k> in order. A goal with any child
    that does not check is ignored whole."""
    if not _companion(companion):
        return {}
    statements = {obligation: statement for obligation, _keys, statement in ROWS}
    family = {key: obligations for key, _sentence, obligations in GOALS}
    out, ids = {}, set()
    for goal in companion["goals"]:
        try:
            line, children = goal.get("line"), []
            ok = (type(goal["id"]) is str and _GID.match(goal["id"]) and goal["id"] not in ids
                  and goal_sentence(goal["key"]) == goal["english"] and goal["sha256"] == _sha(goal["english"])
                  and (line is None or type(line) is int and line > 0)
                  and isinstance(goal["rows"], list) and goal["rows"])
            seen = set()
            for k, child in enumerate(goal["rows"] if ok else (), 1):
                row = {"obligation": child["obligation"], "statement": child["statement"], "values": child["values"]}
                ok = ok and (child["id"] == "%s.%d" % (goal["id"], k) and row["obligation"] in family[goal["key"]]
                             and row["obligation"] not in seen and statements[row["obligation"]] == row["statement"]
                             and isinstance(row["values"], dict) and child["english"] == english(row))
                seen.add(row["obligation"])
                children.append((child["id"], child["statement"], child["english"]))
        except (KeyError, TypeError, AttributeError, ValueError):
            ok = False
        if ok and goal["sha256"] not in out:
            ids.add(goal["id"])
            out[goal["sha256"]] = {"id": goal["id"], "english": goal["english"], "line": line, "rows": children}
    return out


def compile_line(sentence, goals):
    """The checked companion goal for one English requirement sentence, by its sha256; None when there is none (a line
    the customer wrote or edited), and the line is sent as written. The hook where issue #2252 compiles such a line."""
    return goals.get(_sha(sentence))


def typed_text(text, companion):
    """(text the matcher reads, changed lines, expanded goals). Each English line whose sha256 a checked companion
    goal names becomes its children's typed lines (`- G1.1 [postgres]: <statement>`, one per line); every other line,
    and every line inside a code fence, is sent as written. `changed` lists the requirement lines with no match where a
    checked goal was compiled (its `line`): lines changed since they were compiled, checked as written. `expanded`
    lists each goal sent as {id, english, rows: [(id, statement, waypoint)]}. A filled TEMPLATES line is sent as its
    obligations' typed lines under a G<n> id after the companion goals', also when the companion drafted no goal
    (REFUTATION-r3 MEDIUM-1). A companion that is not one (`_companion`) changes nothing."""
    goals = _goals(companion)
    if not goals and not _companion(companion):
        return text, [], []
    compiled_at = {goal["line"] for goal in goals.values() if goal["line"] is not None}
    top = max((int(goal["id"][1:]) for goal in goals.values()), default=0)
    out, fenced, expanded, changed = [], False, [], []
    for n, line in enumerate(text.split("\n"), 1):
        end = "\r" if line.endswith("\r") else ""
        stripped = (line[:-1] if end else line).strip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and stripped and not re.match(r"#{1,6}(?:\s|$)", stripped):
            marker = _MARKER.match(stripped)
            sentence = stripped[marker.end():] if marker else stripped
            goal = compile_line(sentence, goals)
            rows = parse_template(sentence) if goal is None else None
            if rows:                       # REFUTATION-r2 HIGH-1: a G<n> id after every companion goal's, as check_goals reads
                tid = "G%d" % (top + sum(1 for g in expanded if "values" in g) + 1)
                goal = {"id": tid, "english": sentence, "line": n,
                        "rows": [("%s.%d" % (tid, k), row["statement"], english(row)) for k, row in enumerate(rows, 1)],
                        "values": {key: value for row in rows for key, value in row["values"].items()}}
            if goal is not None and goal not in expanded:
                expanded.append(goal)
                out += ["- %s [postgres]: %s%s" % (rid, statement, end) for rid, statement, _w in goal["rows"]]
                continue
            if goal is None and n in compiled_at:
                changed.append(n)
        out.append(line)
    return "\n".join(out), changed, expanded


def apply_typed(text, companion):
    """The requirements text the matcher reads (`typed_text`)."""
    return typed_text(text, companion)[0]


def changed_sentence(changed):
    """The one sentence naming the requirement lines changed since they were compiled, or None."""
    if not changed:
        return None
    if len(changed) == 1:
        return ("1 requirement line changed since it was compiled; it is checked as written (line %d)." % changed[0])
    return ("%d requirement lines changed since they were compiled; they are checked as written (lines %s)."
            % (len(changed), ", ".join(str(n) for n in changed)))


def rollup(goal, states):
    """One goal's reading from its children's requirement states ({id: holds | disproven | not_established}):
    `broken: <waypoints of the disproven children>`, else `holds for N of M checks[; K not decided yet]`."""
    broken = [waypoint for rid, _statement, waypoint in goal["rows"] if states.get(rid) == "disproven"]
    if broken:
        return "broken: " + " ".join(broken)
    held = sum(1 for rid, _statement, _w in goal["rows"] if states.get(rid) == "holds")
    total = len(goal["rows"])
    return "holds for %d of %d checks" % (held, total) + ("; %d not decided yet" % (total - held) if held < total else "")


def requirements_draft(record, notes=()):
    """A draft requirements.md (issue #1186; coordination 7588 and its qualification): the goals a person would write,
    one plain sentence each, for each goal with at least one obligation the drafted declaration decides; no role,
    table or obligation names. The header and the flags line are Markdown headings, so the matcher reads only the
    goals as requirements. The checks under each goal, the drafter's notes and provenance are in the companion
    (`typed_companion`)."""
    lines = ["# Requirements (draft)", "",
             "## Proposed from the catalog snapshot: confirm each goal before committing. Only the committed "
             "raw/declaration.json is authority. The checks under each goal, and where each came from, are in "
             "assure-requirements-typed.json: commit it beside this file unchanged.", ""]
    goals = drafted_goals(record)
    lines += ["- " + goal["english"] for goal in goals] + ([""] if goals else [])
    opened = [n["open"] for n in notes if isinstance(n.get("open"), str)]
    if opened:
        lines += opened[:OPEN_CAP] + ([] if len(opened) <= OPEN_CAP else [
            "## To confirm: %d more tables are open to every row by their own policies; "
            "assure-requirements-typed.json names them." % (len(opened) - OPEN_CAP)]) + [""]
    if "protected_tables" not in record["declaration"] or opened:
        tables = [n["table"] for n in notes if isinstance(n.get("open"), str) and isinstance(n.get("table"), str)]
        lines += ["## Templates: fill in <tables>%s and <caller predicate> (the predicate that keys a row on its user, "
                  "such as `auth.uid() = id`), then keep the line as a goal (\"- \" and the filled sentence) and "
                  "state the same tables and predicate as `protected_tables` and `declared_predicate` in the "
                  "declaration: without them the line's checks are not established."
                  % (" (suggested: %s)" % _and(tables[:OPEN_CAP]) if tables else "")]
        lines += ["## Template: " + template_line(obligations) for obligations in TEMPLATES] + [""]
    unread = sorted(p[1:] for p, v in record["sources"].items() if v == "unread")
    if unread:
        lines += ["## Not proposed (the snapshot gives no basis; state these yourself): " + ", ".join(unread) + ".", ""]
    if _left(record, notes):
        lines += ["## Some of the proposal has no check here; assure-requirements-typed.json says what and why.", ""]
    lines += ["###### execution_authorized false; hardware_authorized false; industrial_release_authorized false; "
              "release_allowed false; physical_validation false; simulation true; self_approved false.", ""]
    return "\n".join(lines)


def _major_from_sidecar(snapshot_path):
    """(major, source) from COLLECTION-SIDECAR.json#/server/server_version_num beside raw/ or inside it, else None."""
    for candidate in (snapshot_path.parent / "COLLECTION-SIDECAR.json", snapshot_path.parent.parent / "COLLECTION-SIDECAR.json"):
        try:
            sidecar = json.loads(candidate.read_text(encoding="utf-8"))
            num = int(str(sidecar["server"]["server_version_num"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        return num // 10000, "COLLECTION-SIDECAR.json#/server/server_version_num"
    return None


def dump(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draft a PostgreSQL declaration proposal from a catalog snapshot.")
    parser.add_argument("snapshot", help="raw/catalog_snapshot.json as the collector wrote it")
    parser.add_argument("--out", required=True, help="where to write the proposal record (JSON)")
    parser.add_argument("--major", type=int, help="server major (default: COLLECTION-SIDECAR.json beside raw/)")
    parser.add_argument("--requirements", help="also write a draft requirements.md here")
    parser.add_argument("--typed", help="with --requirements: also write its typed companion here")
    args = parser.parse_args(argv)
    path = Path(args.snapshot)
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("declare_proposal: cannot read %s: %s" % (path, error), file=sys.stderr)
        return 2
    if args.major is not None:
        major, source = args.major, "argument:major"
    else:
        found = _major_from_sidecar(path)
        if found is None:
            print("declare_proposal: the server major is not observed; pass --major", file=sys.stderr)
            return 2
        major, source = found
    try:
        record, notes = propose_with_notes(snapshot, major=major, major_source=source)
    except ValueError as error:
        print("declare_proposal: %s" % error, file=sys.stderr)
        return 2
    Path(args.out).write_text(dump(record), encoding="utf-8")
    if args.requirements:
        text = requirements_draft(record, notes)
        Path(args.requirements).write_text(text, encoding="utf-8")
        if args.typed:
            Path(args.typed).write_text(dump(typed_companion(
                record, text, "catalog_snapshot.json sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), notes)),
                encoding="utf-8")
    print("declare_proposal: %d keys proposed, %d to confirm, %d unread; written to %s" % (
        len(record["declaration"]) - len(FLAGS) - 1, len(record["confirm"]),
        sum(1 for v in record["sources"].values() if v == "unread"), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
