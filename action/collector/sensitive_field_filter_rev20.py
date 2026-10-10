#!/opt/homebrew/bin/python3.14 -B
"""sensitive_field_filter: the one shared data-protection filter for the MySQL corpus tools and the MySQL collector. Revision 20
(round 1: ten findings → Round1Findings; round 2: eleven blocking + three non-blocking → Round2Findings; round 3: six blocking + three
non-blocking → Round3Findings; round 4: six blocking + two non-blocking → Round4Findings; round 5: four blocking + two non-blocking → Round5Findings; round 6: one blocking + four non-blocking → Round6Findings; round 7: one blocking + six non-blocking → Round7Findings; round 8: one blocking + five non-blocking → Round8Findings; round 9: two blocking + five non-blocking → Round9Findings; round 10 accepted, then OPERATOR-RULING-001 (derive and corpus follow-ups hit
false refusals on the input form's own constants) → Round10Findings; round 11: two blocking + two non-blocking → Round11Findings; round 12: one blocking + four non-blocking → Round12Findings; round 13: one blocking + three non-blocking → Round13Findings; round 14: one blocking + two non-blocking → Round14Findings; round 15 accepted; corpus-check round 6 found a leading-separator
miss → Round15Findings; round 16: one blocking + three non-blocking → Round16Findings; round 17: one blocking + four non-blocking → Round17Findings; round 18: one blocking + four non-blocking → Round18Findings;
revision 20 (trial-013, REG-003): a $ between two letters also separates word-like segments, so MySQL's own sys schema names (x$…) read as names → tests/serving/test_collector_sys_names.py;
every finding became a test before the fix). Line ends are LF, CRLF, or the
serialized-newline marker plus LF; serialized text is read de-escaped only. Bytes are decoded before scanning.

A corpus record must never carry a secret. scan() walks a parsed JSON value or a text and returns WHERE a field that must not be
stored was found and WHAT KIND it is; it never records the value (flagged keys are withheld from paths too). redact() replaces detected
spans with a placeholder, including whole PEM blocks, YAML block scalars and high-entropy tokens. Deterministic, total, fails CLOSED (depth
or size beyond the limits is itself a finding), standard library only. Assignment values are located in Python after a cheap zero-width
match, so a line of many assignments scans in linear time. Flags: execution_authorized false; hardware_authorized false;
industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false."""
import json, math, re
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Finding:
    path: str
    kind: str

KINDS = {
    "sql_authentication": "an SQL clause that sets an account's authentication (IDENTIFIED BY / WITH … BY / … AS followed by a quoted, hexadecimal (0x… or X'…') or charset-introduced literal, including N'…', _binary 0x… and _binary X'…'; the REPLACE '…' current-password clause; SET PASSWORD assignment; PASSWORD(...) function; the PASSWORD keyword followed by a literal, as in CREATE SERVER … OPTIONS (PASSWORD '…') or mysqladmin password '…'; the server's temporary-password log line); statements may span lines; doubled and backslash-escaped quotes stay inside the literal; RANDOM PASSWORD carries no value and is not flagged",
    "replication_credential": "a replication source credential option inside CHANGE REPLICATION SOURCE TO or CHANGE MASTER TO (the password option, any quoting, spaces inside the quotes included)",
    "client_credential": "a client-side password: the short flag joined to a value (quoted or not, whatever follows, through escaped or glued quotes; a port mapping such as 3306:3306 or ip:port:port, with or without /tcp, is not a password), the long option --password, --password1, --password2 or --password3 with = or a space (quoted or not), the client password environment variable (quoted values may contain spaces), or the mysqladmin password subcommand with a value; a bare short flag with no value is not flagged",
    "stored_authentication_string": "a stored authentication-string shape: asterisk + 40 hex; the caching plugin shape ($A$ + three digits + $ …); crypt shapes beginning $digit$ or $2x$; argon2 shapes",
    "named_assignment": "a password-like name (password, passwd, pass, pwd, secret, secret_id, token, api_key, secret_key, secret_access_key, private_key, passphrase, authentication_string; any prefixed, dotted, hyphenated, camel-cased (also after an acronym: DBPassword, MySQLPassword), padded, numbered or trailing-separator form such as source_password, dbPassword, MasterUserPassword, password1, password_2, password_, dbpassword, DBPASSWORD (a short prefix with no separator counts for password/passwd/pwd/secret/token, for the bare word pass only after a database-ish prefix such as db, root, admin, master: bypass, compass stay words), authentication_ldap_simple_bind_root_pwd, also with leading . _ or - as in .password or _password; bare, quoted or backslash-escaped-quoted as in serialized JSON) followed by = or : and a non-empty value, in these forms: a long command-line option --name=value or --name value (the name judged like any other, so --validate-password and --skip-password are excluded), a Java system property -Dname=value, a glued docker -eNAME=value; at line start (after indentation, a YAML list dash, `export`, or an option-file section) with = or :, where the value may also stand on the next indented line or be a YAML block scalar (| or >, with a tag such as !vault or a trailing comment) spanning the indented lines below — block handling applies to line-start, string-start, quoted and name/value forms; quoted anywhere (JSON snippets, quoted dict literals) with = or :; inside a YAML flow mapping after { or , with :; bare mid-line with = (shell and DSN forms); at the start of a quoted string with = or : (a serialized record field such as \"password=…\" or a quoted header 'X-Api-Key: …'); an XML element <name>value</name> (text may span lines), <property name=\"…\" value=\"…\"/> or <name>…</name><value>…</value>; a subscript assignment ['password'] = …; a name/value pair in JSON or YAML text (name: <password-like>, value: …), also inside serialized text; a PHP define('NAME', 'value'). A null, false or None value is no value. The value runs to the end of the line (or block), so a value of any length is withheld whole. MySQL option and plugin names that merely end in the word (validate_password, mysql_native_password, caching_sha2_password, sha256_password, password_history …, in underscore, hyphen or loose_ spelling) are excluded; an empty quoted value is no value",
    "named_key": "a JSON key of a password-like name (any prefix segments, camel case, surrounding or inner whitespace — also inside a quoted name in text — slashes, or a trailing digit) with a non-empty value of any type except a boolean (a boolean carries no credential bytes); also a name/value pair object whose name is password-like and whose value is non-empty (name/value, Name/Value, Key/Value, ParameterKey/ParameterValue, Variable_name/Value and VARIABLE_NAME/VARIABLE_VALUE as MySQL exports SHOW VARIABLES and performance_schema.global_variables)",
    "pem_block": "a PEM or PGP private-key or certificate block (header to footer)",
    "bearer_token": "an authorization header value: any non-empty value under an Authorization or Proxy-Authorization key, any value after `Authorization:` in a text (with or without a scheme word), or a Bearer token of 16 characters or more elsewhere",
    "provider_key": "a provider access-key identifier (a known prefix followed by a long token, including sk_live_ and github_pat_ shapes)",
    "connection_string": "a connection string carrying user:secret@host (or :secret@host with an empty user): a URL with a scheme, or the scheme-less MySQL Shell / Go DSN forms user:secret@host.domain, user:secret@host:port, user:secret@tcp(host:port), and after mysqlsh or --uri any host",
    "high_entropy_string": "a whitespace-free token of 32 or more characters, anywhere in a string, with Shannon entropy of 4.0 bits per character or more (a token that parses as JSON is judged by its string leaves, not as one run; a token made only of word-like segments split on , _ . - / : ; ( ) or on a $ between two letters is a name; base64 padding stripped before judging; a name=value token is judged on its value side, and on its name side when the name is not made of word-like segments; a URL's userinfo is judged as a token), that is neither a 32-, 40- or 64-character hex digest, nor a GTID set (UUID:ranges or UUID:tag:ranges joined by commas), nor a dotted identifier of short word labels (a schema name, a Java class, a reverse-DNS id), nor a bare name or JSON key made of word-like segments (letters, or at most 24 characters with at most two digit runs, split on _ - .), nor a filesystem path of ordinary segments (POSIX or Windows), nor a host name (dot-separated labels of letters, digits and hyphens whose last label is letters only and none of which is a base64-looking run of 16 or more mixed-case letters and digits without a hyphen; also as the host part of a user@host account or of a credential-free URL, whose path and query segments are judged one by one)",
    "unscannable_depth": "the value nests deeper than the filter scans (64 levels): refused rather than passed",
    "unscannable_size": "a container or text larger than the filter scans (100000 items or lines, 10000 whitespace-free tokens in one text, 4000000 characters) or a pattern failure: refused rather than passed",
}
_INTRO = r"(?:_[A-Za-z0-9]+\s*|[NnBb])?"  # charset introducer (_utf8mb4, _binary), national or bit-string prefix
_SQ = r"'(?:[^'\\]|\\.|'')*'"             # single-quoted literal with doubled or backslash-escaped quotes inside
_DQ = r"\"(?:[^\"\\]|\\.|\"\")*\""
_ESQ = r"\\'(?:[^'\\]|\\[^'])*\\'"          # the same literals with backslash-escaped delimiters, as inside serialized JSON text
_EDQ = r"\\\"(?:[^\"\\]|\\[^\"])*\\\""
_LIT = r"(?:" + _INTRO + r"0x[0-9A-Fa-f]+|" + _INTRO + r"[Xx]'[0-9A-Fa-f]*'|" + _INTRO + _ESQ + r"|" + _INTRO + _EDQ + r"|" + _INTRO + _SQ + r"|" + _INTRO + _DQ + r")"
_QVAL = r"(?:" + _SQ + r"[^\s]*|" + _DQ + r"[^\s]*|[^\s'\"][^\s]*)"  # a shell value: quoted (with anything glued after the closing quote) or bare
_NAMES = r"(?:password|passwd|pass|pwd|secret|secret[_-]?id|token|api[_-]?key|secret[_-]?(?:access[_-]?)?key|private[_-]?key|passphrase|authentication_string)"
_OPTION_FALSE = re.compile(r"(?i)^(?:(?:[a-z0-9]+[_.-])*validate[_.-]password(?:[._-][a-z0-9_.-]+)?|mysql_native_password|caching_sha2_password|sha256_password|authentication_(?![a-z_]*_(?:pwd|passwd|password)$)(?:policy|plugin|windows_[a-z_]+|ldap_[a-z_]+|kerberos_[a-z_]+|fido_[a-z_]+)|default_authentication_plugin|skip_password|(?:ask|no)_(?:[a-z_]+_)?(?:pass|password|pwd)|password_(?:require_current|lock_time|lifetime|history|reuse_interval|expire|policy|length|number_count|mixed_case_count|special_char_count|dictionary_file|check_user_name)|default_password_lifetime|disconnect_on_expired_password|[a-z0-9_]*_(?:lifetime|time|history|policy|count|plugin|interval))$")
_RX = [
    ("sql_authentication", re.compile(r"\bIDENTIFIED\b(?:\s+WITH\s+\S+)?\s+(?:BY|AS)\s+" + _LIT + r"(?:\s+REPLACE\s+" + _LIT + r")?", re.I | re.S)),
    ("sql_authentication", re.compile(r"\bREPLACE\s+" + _LIT, re.I | re.S)),
    ("sql_authentication", re.compile(r"\bSET\s+PASSWORD\b[^=;]{0,200}=\s*(?:PASSWORD\s*\(\s*" + _LIT + r"\s*\)|" + _LIT + r")(?:\s+REPLACE\s+" + _LIT + r")?", re.I | re.S)),
    ("sql_authentication", re.compile(r"\bPASSWORD\s*\(\s*" + _LIT + r"\s*\)", re.I | re.S)),
    ("sql_authentication", re.compile(r"\bPASSWORD\s+" + _LIT, re.I | re.S)),
    ("sql_authentication", re.compile(r"\btemporary password is generated for \S+:[ \t]*\S+", re.I)),
    ("replication_credential", re.compile(r"\b(?:SOURCE|MASTER)_PASSWORD\s*=\s*(?:" + _LIT + r"|[^\s,;]{1,512})", re.I)),
    ("client_credential", re.compile(r"(?<![\w-])-p(?!assword[_\-][a-z])(?!\d{1,5}:\d{1,5}(?:/(?:tcp|udp|sctp))?(?![^\s]))(?!(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}:\d{1,5}(?:/(?:tcp|udp|sctp))?(?![^\s]))(?!-)" + _QVAL)),
    ("client_credential", re.compile(r"(?<![\w-])--password[123]?(?:=|[ \t]+)(?!-)" + _QVAL, re.I)),
    ("client_credential", re.compile(r"\bMYSQL_PWD\s*=\s*" + _QVAL, re.I)),
    ("client_credential", re.compile(r"\bmysqladmin\b[^\n;|&]{0,200}?\s(?:password|old-password)\s+(?!-)" + _QVAL, re.I)),
    ("stored_authentication_string", re.compile(r"(?<![0-9A-Za-z])\*[0-9A-Fa-f]{40}(?![0-9A-Za-z])")),
    ("stored_authentication_string", re.compile(r"\$A\$\d{3}\$[^\s'\"]{20,512}")),
    ("stored_authentication_string", re.compile(r"\$(?:[1-9]|2[abxy]|5|6|y|gy|argon2id?)\$[^\s'\"]{16,512}")),
    ("pem_block", re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}(?:PRIVATE KEY|CERTIFICATE)[A-Z0-9 ]{0,20}-----.{0,20000}?-----END [A-Z0-9 ]{0,40}(?:PRIVATE KEY|CERTIFICATE)[A-Z0-9 ]{0,20}-----|-----BEGIN [A-Z0-9 ]{0,40}(?:PRIVATE KEY|CERTIFICATE)[A-Z0-9 ]{0,20}-----.{0,20000}", re.S)),
    ("bearer_token", re.compile(r"\b(?:Proxy-)?Authorization\\*[\"']?\s*[:=]\s*\\*[\"']?(?:(?:Bearer|Basic|Token|Digest|Negotiate|NTLM|ApiKey)\s+)?[^\s\"'}\\]{1,4096}|\bBearer\s+[A-Za-z0-9._~+/=-]{16,4096}", re.I)),
    ("provider_key", re.compile(r"(?<![A-Za-z0-9])(?:AKIA[0-9A-Z]{16}|sk-(?:or-)?[A-Za-z0-9_-]{20,256}|sk_(?:live|test)_[A-Za-z0-9]{16,256}|github_pat_[A-Za-z0-9_]{20,256}|ghp_[A-Za-z0-9]{30,256}|xox[baprs]-[A-Za-z0-9-]{10,256}|AIza[0-9A-Za-z_-]{30,256})")),
    ("connection_string", re.compile(r"\b[a-z][a-z0-9+.-]{0,20}://[^\s/:@]{0,128}:[^\s/@]{1,256}@[^\s/@]{1,256}", re.I)),
    ("connection_string", re.compile(r"(?<![\w@:/.\-])[A-Za-z0-9_.\-]{1,64}:[^\s@/:]{1,256}@(?:(?:tcp|unix)\(|\[[0-9A-Fa-f:]+\]|localhost\b|[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+|[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?=:\d{1,5}))(?::\d{1,5})?", re.I)),
    ("connection_string", re.compile(r"(?:(?<=mysqlsh )|(?<=--uri ))[A-Za-z0-9_.\-]{1,64}:[^\s@/:]{1,256}@[A-Za-z0-9][A-Za-z0-9.\-]*", re.I)),
]
_AUTH_KEYS = {"authorization", "proxy-authorization", "proxy_authorization"}
_AUTH_SCHEME = re.compile(r"(?i)^\s*(?:Bearer|Basic|Token|Digest|Negotiate|NTLM|ApiKey)\s+\S")
# four assignment forms; each match is zero-width after the separator, and the value span is located in Python (see _value_span),
# so a line of many assignments is scanned in linear time
_NAMETOK = r"(?P<n>[A-Za-z0-9][A-Za-z0-9_.\-]{0,128})"
_ASSIGN_FORMS = [
    ("opt", re.compile(r"(?<!\S)(?:--|-D|-e)" + _NAMETOK + r"[ \t]*=")),  # long option, Java system property, glued docker -e
    ("optspace", re.compile(r"(?<!\S)--" + _NAMETOK + r"[ \t]+(?![-\s])")),  # --admin-password value (the value is the next token)
    ("xml", re.compile(r"<" + _NAMETOK + r"\s*>")),
    ("xml2", re.compile(r"<\w+\s+name\s*=\s*[\"']" + _NAMETOK + r"[\"']\s*>")),  # <property name="…">value</property>
    ("strstart", re.compile(r"(?<=[\"'])[._\-]*" + _NAMETOK + r"[ \t]*[:=]")),  # an assignment at the start of a quoted string (serialized field, quoted header)
    ("pair", re.compile(r"(?i)(?:\\*[\"'])?(?:parameter|variable_)?(?:name|key)(?:\\*[\"'])?\s*[:=]\s*(?:\\*[\"'])?(?P<n>[A-Za-z0-9_./ \-]{1,128}?)(?:\\*[\"'])?\s*,?\s*(?:\\*[\"'])?(?:parameter|variable_)?value(?:\\*[\"'])?\s*[:=]")),  # name/value pair in JSON, YAML or XML-attribute text
    ("define", re.compile(r"\bdefine\s*\(\s*[\"'](?P<n>[A-Za-z0-9_.\-]{1,128})[\"']\s*,\s*")),  # PHP define('NAME', 'value')
    ("line", re.compile(r"(?m)^(?P<ind>[ \t]*)(?:-[ \t]+|export[ \t]+|\[[^\]\n]*\][ \t]*)?(?P<q>[\"']?)[ \t]*[._\-]*" + _NAMETOK + r"[ \t]*(?P=q)[ \t]*[:=]")),  # leading . _ - before the name are allowed
    ("quoted", re.compile(r"(?<![A-Za-z0-9_.\-\\])(?P<q>(?:\\)*[\"'])[ \t]*(?P<n>[._\-]*[A-Za-z0-9][A-Za-z0-9_.\- ]{0,128})[ \t]*(?P=q)[ \t]*[:=]")),  # a quoted name may hold spaces and lead with . _ -  # any escape depth, as in JSON inside JSON
    ("flow", re.compile(r"(?<=[{,])[ \t]*[._\-]*" + _NAMETOK + r"[ \t]*:")),
    ("bare", re.compile(r"(?<![A-Za-z0-9_.\-\"'\\])[._\-]*" + _NAMETOK + r"[ \t]*=")),  # .password=, _password=
    ("subscript", re.compile(r"\[\s*[\"'](?P<n>[A-Za-z0-9_.\- ]{1,128})[\"']\s*\]\s*=")),  # $cfg[...]['password'] = …, os.environ["X"] = …
    ("xmlpair", re.compile(r"<name>\s*(?P<n>[A-Za-z0-9_.\-]{1,128})\s*</name>\s*<value>\s*")),  # Hadoop/Hive property
]
_BLOCK = re.compile(r"(?:![^\s]*[ \t]+)?[|>][-+0-9]*[ \t]*(?:#[^\n]*)?$")  # block indicator, optionally tagged (!vault, !!binary) or commented
_EMPTYV = re.compile(r"(?:\\*\"\\*\"|\\*'\\*'|null|false|true|None|False|True|~)[ \t]*(?:[;,}\])#\\]|$)")  # empty quoted (also escaped), null, booleans  # empty quoted (also escaped), null, false, None
_ESCAPES = (("\\n", "\x0c\n"), ("\\t", "\t"), ("\\r", "\r"))  # JSON-escaped line structure; the newline carries a reversible whitespace marker (form feed, which serialized text never holds raw)
_NAME_TAIL = re.compile(r"(?i)(?:(?:^|[_.-])" + _NAMES + r"|^[a-z0-9]{1,12}(?:password|passwd|pwd|secret|token)|^(?:db|root|admin|user|mysql|sql|rds|master|repl|replica|app|api)pass)(?:[_.\-]?[0-9]{1,2})?[_.\-]*$")  # trailing separators and a numbered form allowed; a short prefix with no separator counts for the strong words (dbpassword), never for bare pass
_CAMEL = re.compile(r"([a-z0-9])([A-Z])|([A-Z]+)([A-Z][a-z])")  # dbPassword → db_Password; DBPassword → DB_Password
_GTID = re.compile(r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?::[A-Za-z_][A-Za-z0-9_]{0,31})?:\d+(?:-\d+)?(?::\d+(?:-\d+)?)*,?)+$")  # 8.4 tagged sets allowed
_HEX = re.compile(r"^[0-9a-fA-F]+$")
_HOST = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?\.){1,}[A-Za-z]{2,24}\.?$")
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_TOKEN = re.compile(r"\S{32,4096}")
_SEP = re.compile(r"[,_.\-/:;()]|(?<=[A-Za-z])\$(?=[A-Za-z])")  # rev 20: a $ between two letters separates (MySQL x$ names); any other $ stays inside its segment
_MAX_DEPTH, _MAX_ITEMS, _MAX_TOKENS, _MAX_TEXT = 64, 100000, 10000, 4_000_000

def _entropy(s: str) -> float:
    if not s: return 0.0
    counts = {}
    for ch in s: counts[ch] = counts.get(ch, 0) + 1
    n = len(s); return -sum(c / n * math.log2(c / n) for c in counts.values())

def _is_pw_name(name: str) -> bool:
    n = _CAMEL.sub(lambda m: (m.group(1) + "_" + m.group(2)) if m.group(1) else (m.group(3) + "_" + m.group(4)), str(name).strip()).lower().replace("-", "_").replace("/", "_").replace(" ", "_").strip("_.")  # dbPassword → db_password; DBPassword → db_password; leading and trailing . _ - dropped
    if n.startswith("loose_"): n = n[6:]  # mysqld's loose- prefix
    if _OPTION_FALSE.match(n): return False
    if n.startswith("d") and _OPTION_FALSE.match(n[1:].lstrip("_.")): return False  # -Dvalidate_password=ON read through a leading separator: the D is the Java flag, not part of the name
    return bool(_NAME_TAIL.search(n))

def _is_host(t: str) -> bool:
    t = t.strip("\"'`")
    if _IPV4.match(t): return True
    if not _HOST.match(t) or len(t) > 253: return False
    return not any(_b64_like(label) for label in t.rstrip(".").split("."))  # a base64-looking label is not a host label

_NAMEISH = re.compile(r"^[\"'`]*[A-Za-z_][A-Za-z0-9_.\-]*[\"'`]*$")
_DIGIT_RUNS = re.compile(r"\d+")

def _wordy(seg: str) -> bool:
    """a word-like segment: letters only (any length up to 64), or at most 24 characters with at most two digit runs; never a base64-looking run"""
    if not seg or len(seg) > 64 or not seg.isalnum() or _b64_like(seg): return False  # letters and digits only: '+' or '=' inside a segment is never word-like
    return seg.isalpha() or (len(seg) <= 24 and len(_DIGIT_RUNS.findall(seg)) <= 2)

def _is_wordy_name(name: str) -> bool:
    name = name.strip("\"'`")
    return bool(_NAMEISH.match(name)) and all(_wordy(x) for x in re.split(r"[_.\-]", name) if x)

def _is_wordy_token(t: str) -> bool:
    """a comma-joined column list, a dotted class name, a hyphenated slug: every segment word-like, at least two segments"""
    segs = [x for x in _SEP.split(t) if x]
    return len(segs) >= 2 and all(_wordy(x) for x in segs)
_IDENT_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]{0,63}$")
_PATH_SEG = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

def _b64_like(label: str) -> bool:  # defined before _wordy uses it at call time
    """a standard-base64-looking run: 16+ letters and digits only, mixed case with digits (a hyphen, underscore or dot marks a name)"""
    return len(label) >= 16 and label.isalnum() and any(c.isdigit() for c in label) and any(c.islower() for c in label) and any(c.isupper() for c in label)

def _is_identifier(t: str) -> bool:
    """a dotted identifier of short word labels: a schema name, a Java class, a reverse-DNS id (never a base64-looking label)"""
    parts = t.split(".")
    return len(parts) >= 2 and all(_IDENT_LABEL.match(x) and all(_wordy(y) for y in re.split(r"[_\-]", x) if y) for x in parts)

def _is_path(t: str) -> bool:
    """a filesystem path of ordinary segments (POSIX or Windows); a base64-looking segment is not ordinary"""
    if re.match(r"^[A-Za-z]:\\", t): segs = t[3:].split("\\")
    elif "\\" in t: segs = t.split("\\")  # a Windows path fragment after a space in the path
    elif t.startswith("/"): segs = t[1:].split("/")
    else: return False
    return len(segs) >= 2 and all(_PATH_SEG.match(x) and all(_wordy(y) for y in re.split(r"[_.\-]", x) if y) for x in segs if x)

def _judge(t: str, key: str) -> bool:
    """the entropy rule on one cleaned token"""
    if len(t) < 32 or _entropy(t) < 4.0: return False
    if _is_identifier(t) or _is_path(t) or _is_wordy_token(t) or _GTID.match(t.rstrip(";")): return False
    if _HEX.match(t) and len(t) in (32, 40, 64): return False  # a hex digest shape is a digest (scan and redact agree; a hex secret under a password-like key is the named_key rule's)
    if _is_host(t): return False
    return True

def _json_leaves(v):
    if isinstance(v, dict):
        for k, x in v.items(): yield str(k); yield from _json_leaves(x)
    elif isinstance(v, list):
        for x in v: yield from _json_leaves(x)
    elif isinstance(v, str): yield v

def _token_is_secret(tok: str, key: str) -> bool:
    if tok[:1] in "{[" and tok[-1:] in "}]" and len(tok) <= 2_000_000:  # a compact JSON record is judged by its string leaves, not as one run
        try: parsed = json.loads(tok)
        except Exception: parsed = None
        if isinstance(parsed, (dict, list)):
            return any(_token_is_secret(leaf_tok, key) for leaf in _json_leaves(parsed) for leaf_tok in _TOKEN.findall(leaf))
    t = tok.strip("\"',;()[]{}<>`")
    if "<" in t and ">" in t: return any(_judge(seg, key) for seg in re.split(r"[<>/]", t) if seg)  # XML markup glued to its text: judge the pieces
    if "://" in t:  # a URL: the host is a host; the path and query segments are judged one by one
        rest = t.split("://", 1)[1]
        authority, _, tail = rest.partition("/")
        if "@" in authority:  # userinfo: a token (no colon) or user:secret; the secret side is judged as a token
            userinfo = authority.rsplit("@", 1)[0]
            return _judge(userinfo.split(":", 1)[1] if ":" in userinfo else userinfo, key)
        host = authority.rsplit(":", 1)[0] if re.search(r":\d{1,5}$", authority) else authority
        if host and not _is_host(host) and _judge(host, key): return True
        return any(_judge(seg, key) for seg in re.split(r"[/?&=#;]", tail) if seg)
    if "@" in t:  # user@host account form (the part after @ is a host name): judge the user part alone
        user, host = t.rsplit("@", 1)
        if _is_host(host): return _judge(user.strip("\"'`"), key)
    if _is_path(t): return False  # a Windows path carries a drive colon; judge it as a path before any assignment split
    if _GTID.match(t.rstrip(";")): return False  # a GTID set (UUID:ranges, comma-joined) is a replication value; judge it whole, before any split at its colons
    core = t.rstrip("=")  # base64 padding is not an assignment
    if "=" in core[1:] or ":" in core[1:]:  # an assignment token: judge the value side only (option names and keywords are not secrets)
        name, value = re.split(r"[=:]", core, maxsplit=1)
        value = value.strip("\"',;()[]{}<>`")
        if value: return _judge(value, key) or (not _is_wordy_name(name) and _judge(name.strip("\"'`"), key))  # a secret on the name side is judged too
        if _is_wordy_name(name): return False  # a bare name or JSON key with its punctuation attached is a name
    return _judge(core, key)

def _json_text(text: str):
    """the parsed value when the whole text is a JSON object or array (a serialized record), else None"""
    ts = text.strip()
    if ts[:1] in "{[" and ts[-1:] in "}]" and len(ts) <= 4_000_000:
        try:
            v = json.loads(ts)
            if isinstance(v, (dict, list)): return v
        except Exception: return None
    return None

def _secret_leaf_tokens(parsed, key: str):
    for leaf in _json_leaves(parsed):
        for tok in _TOKEN.findall(leaf):
            if _token_is_secret(tok, key): yield tok

def _entropy_kinds(text: str, key: str) -> set:
    parsed = _json_text(text)
    if parsed is not None:  # a serialized record is judged by its string leaves, never as whitespace-split runs of JSON
        return {"high_entropy_string"} if any(True for _ in _secret_leaf_tokens(parsed, key)) else set()
    toks = _TOKEN.findall(text); out = set()
    if len(toks) > _MAX_TOKENS: out.add("unscannable_size")  # beyond the token cap the text is refused, never passed
    for tok in toks[:_MAX_TOKENS]:
        if _token_is_secret(tok, key): out.add("high_entropy_string"); break
    return out

def _value_span(text: str, form: str, m):
    sp = _value_span_raw(text, form, m)
    if sp:  # a newline marker from de-escaped serialized text is structure, not value
        a, b = sp
        while b > a and text[b - 1] in "\x0c\r \t": b -= 1
        return (a, b) if b > a else None
    return sp

def _value_span_raw(text: str, form: str, m):
    """(start, end) of the value that follows an assignment match: the end of the line, or for the line form a next-line scalar or a
    YAML block scalar spanning the lines indented deeper than the key; None when there is no value"""
    i = m.end()
    while i < len(text) and text[i] in " \t": i += 1
    eol = text.find("\n", i); eol = len(text) if eol < 0 else eol
    eolc = eol  # the line's content end: a CR or the serialized-newline marker before the LF is structure, not value
    while eolc > i and text[eolc - 1] in "\r\x0c": eolc -= 1
    if form == "optspace":
        end = i
        while end < len(text) and not text[end].isspace(): end += 1
        return (i, end) if end > i else None
    if form == "define":
        end = text.find(")", i); end = eol if end < 0 or end > eol else end
        return (i, end) if i < end and text[i:end].strip() else None
    if form in ("xml", "xml2", "xmlpair"):
        end = text.find("</", i, i + 4096); end = eolc if end < 0 else end
        return (i, end) if i < end and text[i:end].strip() else None
    if form not in ("line", "strstart", "quoted", "pair"): return (i, eolc) if i < eolc and not _EMPTYV.match(text, i, eolc) else None
    if form == "line": ind = len(m.group("ind"))
    elif form == "strstart": ind = 0  # a quoted string start counts as indentation 0
    else:  # indentation of the key's own line
        ls = text.rfind("\n", 0, m.start()) + 1; head = text[ls:m.start()]; ind = len(head) - len(head.lstrip(" \t"))
    def deeper_block(start):  # the run of following lines indented more than the key (blank lines allowed inside the run)
        end = start - 1; j = start
        while j < len(text):
            nl = text.find("\n", j); nl = len(text) if nl < 0 else nl
            line = text[j:nl]
            if line.strip() == "": j = nl + 1; continue
            if len(line) - len(line.lstrip(" \t")) <= ind: break
            end = nl; j = nl + 1
        return end
    if i < eolc and _EMPTYV.match(text, i, eolc): return None  # an empty quoted value (whatever trails it) is no value
    if i >= eolc:  # nothing on the key line: a plain scalar may stand on the next, deeper-indented line(s)
        if eol >= len(text): return None
        end = deeper_block(eol + 1)
        return (i, end) if end > eol else None
    if _BLOCK.match(text, i, eolc):  # block scalar: the indicator and the indented block below
        end = deeper_block(eol + 1) if eol < len(text) else eol
        return (i, max(end, eol))
    return (i, eolc)

def _assignments(text: str):
    """yield (name, form, match) for every assignment form at every position"""
    for form, rx in _ASSIGN_FORMS:
        for m in rx.finditer(text): yield m.group("n"), form, m

def _deescape(text: str) -> str:
    for a, b in _ESCAPES: text = text.replace(a, b)
    return text

def _reescape(text: str) -> str:
    for a, b in _ESCAPES: text = text.replace(b, a)
    return text

def _text_kinds(text: str, key: str) -> set:
    if not isinstance(text, str) or not text: return set()
    if "\\n" in text or "\\t" in text or "\\r" in text: return _text_kinds_core(_deescape(text), key)  # serialized text is read with its line structure restored, and only so (a raw reading glues the escape letter onto the next name)
    return _text_kinds_core(text, key)

def _text_kinds_core(text: str, key: str) -> set:
    seen = set()
    for kind, rx in _RX:
        try:
            if rx.search(text): seen.add(kind)
        except Exception: seen.add("unscannable_size")
    try:
        if (key or "").strip().lower() in _AUTH_KEYS and text.strip(): seen.add("bearer_token")
    except Exception: seen.add("unscannable_size")
    try:
        for name, form, m in _assignments(text):
            if _is_pw_name(name) and _value_span(text, form, m): seen.add("named_assignment"); break
    except Exception: seen.add("unscannable_size")
    try: seen |= _entropy_kinds(text, key)
    except Exception: seen.add("unscannable_size")
    return seen

def _withheld(key: str) -> str:
    k = _text_kinds(key, "")
    return f"<withheld:{sorted(k)[0]}>" if k else key

def scan(value: Any, path=()) -> list:
    out: list = []
    try: _walk(value, tuple(path) if isinstance(path, (list, tuple)) else (str(path),), out, 0, "")
    except Exception: out.append(Finding("$", "unscannable_size"))
    seen = set(); res = []  # dedupe, stable order
    for f in out:
        if (f.path, f.kind) not in seen: seen.add((f.path, f.kind)); res.append(f)
    return res

def _walk(v, path, out, depth, key):
    p = "/".join(str(x) for x in path) or "$"
    if depth > _MAX_DEPTH: out.append(Finding(p, "unscannable_depth")); return
    if isinstance(v, dict):
        items = list(v.items())
        if len(items) > _MAX_ITEMS: out.append(Finding(p, "unscannable_size")); items = items[:_MAX_ITEMS]
        low = {str(k).strip().lower(): k for k in v}
        for nk, vk in (("name", "value"), ("key", "value"), ("parameterkey", "parametervalue"), ("variable_name", "value"), ("variable_name", "variable_value")):
            if nk in low and vk in low and _is_pw_name(str(v[low[nk]])) and v[low[vk]] not in (None, "", [], {}) and not isinstance(v[low[vk]], bool):
                out.append(Finding(p + "/" + str(low[vk]), "named_key"))  # name/value pair (Kubernetes env, CloudFormation Name/Value, Key/Value, ParameterKey/ParameterValue)
        for k, x in items:
            ks = str(k); safe = _withheld(ks)
            if _is_pw_name(ks) and x not in (None, "", [], {}) and not isinstance(x, bool): out.append(Finding(p + "/" + safe, "named_key"))
            for kind in sorted(_text_kinds(ks, "")): out.append(Finding(p + "/<key>", kind))
            _walk(x, path + (safe,), out, depth + 1, ks)
    elif isinstance(v, (list, tuple)):
        if len(v) > _MAX_ITEMS: out.append(Finding(p, "unscannable_size"))
        for i, x in enumerate(v[:_MAX_ITEMS]): _walk(x, path + (i,), out, depth + 1, key)
    elif isinstance(v, (bytes, bytearray)):
        _walk(bytes(v).decode("utf-8", "replace"), path, out, depth, key)
    elif isinstance(v, str):
        if len(v) > _MAX_TEXT: out.append(Finding(p, "unscannable_size")); v = v[:_MAX_TEXT]
        for kind in sorted(_text_kinds(v, key)): out.append(Finding(p, kind))
        if "\n" in v:  # line-level paths for texts, in addition to the whole-text match above
            lines = v.split("\n")
            if len(lines) > _MAX_ITEMS: out.append(Finding(p, "unscannable_size"))
            for n, line in enumerate(lines[:_MAX_ITEMS], 1):
                for kind in sorted(_text_kinds(line, key)): out.append(Finding(f"{p}:line{n}", kind))

def redact(text) -> str:
    try: s = bytes(text).decode("utf-8", "replace") if isinstance(text, (bytes, bytearray)) else str(text)
    except Exception: return "<withheld:unrepresentable>"
    esc = "\\n" in s or "\\t" in s or "\\r" in s
    if esc: s = _deescape(s)  # serialized text: redact with its line structure restored, then restore the escapes
    s = _redact_text(s)
    return _reescape(s) if esc else s

def _redact_text(s: str) -> str:
    try:  # assignments first (their values may hold shapes the other rules would cut short); spans merged, replaced right to left
        spans = []
        for name, form, m in _assignments(s):
            if _is_pw_name(name):
                sp = _value_span(s, form, m)
                if sp: spans.append(sp)
        merged = []
        for a, b in sorted(spans):
            if merged and a <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else: merged.append((a, b))
        for a, b in reversed(merged): s = s[:a] + "<withheld:named_assignment>" + s[b:]
    except Exception: return "<withheld:unscannable_size>"
    for kind, rx in _RX:
        try: s = rx.sub(f"<withheld:{kind}>", s)
        except Exception: return "<withheld:unscannable_size>"
    try:
        parsed = _json_text(s)
        if parsed is not None:  # serialized record: withhold each secret leaf token where it stands, in every form json.dumps may have written it
            for tok in sorted(set(_secret_leaf_tokens(parsed, "")), key=len, reverse=True):
                for form in {tok, json.dumps(tok, ensure_ascii=True)[1:-1], json.dumps(tok, ensure_ascii=False)[1:-1]}: s = s.replace(form, "<withheld:high_entropy_string>")
            left = _json_text(s)
            if left is not None and any(True for _ in _secret_leaf_tokens(left, "")): s = "<withheld:high_entropy_string>"  # fail closed: a leaf escaped in a form not covered
        else:
            s = _TOKEN.sub(lambda m: "<withheld:high_entropy_string>" if _token_is_secret(m.group(0), "") else m.group(0), s)
    except Exception: return "<withheld:unscannable_size>"
    return s

__all__ = ["Finding", "KINDS", "scan", "redact"]
