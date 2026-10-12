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
  no basis for is ``unread`` and is left out of ``declaration``: the drafter never invents an intent.
- ``confirm`` lists the keys whose value is a judgement the customer confirms before committing (every proposed key
  except the four observed facts: schema, major, collection_role, database_owner).

Each rule below drafts the strict reading of what the snapshot shows (access_paths_complete excepted: it is drafted
true beside protected_tables, always confirmed, since without it the row-security machine is refused). A value that would only widen what the checker
accepts (an empty untrusted-role list, an empty administrator list) is never drafted from an absence: that key stays
unread. A snapshot section the collector did not read (absent from the snapshot) is never read as empty.

Standard library only. No network, no database, no model call, no verdict.
execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
"""
from __future__ import annotations

import argparse
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
    # tie) is drafted, since the declaration states one predicate
    if objects_sec is None or policies_sec is None:
        for key in ("protected_tables", "declared_predicate", "required_policies"):
            d.unread(key, "objects or policies were not collected")
    else:
        by_table = {}
        for index, row in enumerate(policies_sec):
            if isinstance(row, dict) and type(row.get("polrelid")) is str:
                by_table.setdefault(row["polrelid"], []).append((index, row))
        groups = {}
        for index, row in rls_tables:
            quals = {}
            for pindex, policy in by_table.get(row["relname"], []):
                qual = policy.get("polqual")
                if type(qual) is str and not _trivial(qual):
                    quals.setdefault(strip_outer_parens(qual), pindex)
            if len(quals) == 1:
                (predicate, pindex), = quals.items()
                groups.setdefault(predicate, []).append((index, row, pindex))
            else:
                d.notes.append({"key": "protected_tables", "note": "table %s has %d distinct row filters; not drafted"
                                % (row["relname"], len(quals))})
        if not groups:
            for key in ("protected_tables", "declared_predicate", "required_policies"):
                d.unread(key, "no row-security table with a single row filter was observed")
        else:
            predicate = max(groups, key=lambda p: (len(groups[p]), -groups[p][0][0]))
            chosen = groups[predicate]
            d.put("protected_tables", [row["relname"] for _, row, _ in chosen],
                  _list_sources([SNAP + "/objects/%d/relrowsecurity" % index for index, _, _ in chosen]))
            d.put("declared_predicate", predicate, SNAP + "/policies/%d/polqual" % chosen[0][2])
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


#: one plain sentence per proposed key, for the draft requirements.md
SENTENCES = {
    "administrators": "Only {v} may hold superuser.",
    "applications": "The application connects as {v}.",
    "privilege_queries": "These table privileges are intended: {v}.",
    "sensitive_objects": "These tables hold sensitive data: {v}.",
    "default_acl_expectations": "New tables get exactly these default privileges: {v}.",
    "replication_roles": "Only {v} may replicate.",
    "protected_tables": "Row security protects {v}.",
    "declared_predicate": "Each tenant sees only the rows where {v}.",
    "required_policies": "These row-security policies must exist: {v}.",
    "access_paths_complete": "Every way to reach the protected tables is a grant, membership or view in the catalog.",
    "rls_exempt_logins": "No login is exempt from row security.",
    "view_exemptions": "No view is exempt from row security.",
    "intended_tables": "Logical replication publishes only {v}.",
    "untrusted_roles": "These roles are untrusted and must not control a SECURITY DEFINER function's search path: {v}.",
    "id": "This declaration is named {v}.",
}


def _phrase(value):
    if isinstance(value, list):
        if not value:
            return "nothing"
        parts = []
        for item in value:
            if isinstance(item, dict) and "privilege" in item:
                parts.append("%s %s on %s" % (item["role"], item["privilege"], item["object"]))
            elif isinstance(item, dict) and "creator" in item:
                parts.append("tables %s creates in %s grant %s" % (item["creator"], item["schema"],
                             ", ".join("%s %s" % (g, p) for g, p in item["expected_acl"]) or "nothing"))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def requirements_draft(record, notes=()):
    """A draft requirements.md: one sentence per proposed key, each marked for confirmation."""
    lines = ["# Requirements (draft)", "",
             "Proposed from the catalog snapshot. Each line is proposed — confirm before committing. "
             "Only the committed raw/declaration.json is authority.", ""]
    decl = record["declaration"]
    for key in sorted(k for k in decl if "/" + _esc(k) in record["confirm"]):
        sentence = SENTENCES.get(key, "%s: {v}." % key).format(v=_phrase(decl[key]))
        lines.append("- %s (proposed — confirm before committing)" % sentence)
    unread = sorted(p[1:] for p, v in record["sources"].items() if v == "unread")
    if unread:
        lines += ["", "Not proposed (the snapshot gives no basis; state these yourself): " + ", ".join(unread) + "."]
    left = [n["note"] for n in notes if "note" in n]
    if left:
        lines += ["", "Notes:"] + ["- " + n for n in left]
    lines += ["", "execution_authorized false; hardware_authorized false; industrial_release_authorized false; "
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
        Path(args.requirements).write_text(requirements_draft(record, notes), encoding="utf-8")
    print("declare_proposal: %d keys proposed, %d to confirm, %d unread; written to %s" % (
        len(record["declaration"]) - len(FLAGS) - 1, len(record["confirm"]),
        sum(1 for v in record["sources"].values() if v == "unread"), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
