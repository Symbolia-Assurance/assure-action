"""The secret-pattern registry (issue #1819): the one place serve/ and action/ compile a pattern for Assure's own API
key. Standard library only, so the public Action tree ships it (action/client.py imports it; action/build_dist.py
follows the import).

- `KEY_RE`: an Assure API key, `asr_<8 hex key id>_<43 url-safe base64 characters>`; group 1 is the key id, group 2 the
  secret. serve/keys.py authenticates with it and action/client.py checks the key a token exchange returns with it.
- `KEY_PREFIX_RE`: the key-shaped prefix `asr_<8 hex>_` alone; action/source_contract.py refuses a contract value that
  holds it.
- `PATTERNS`: name -> compiled pattern for the secrets `screen` looks for in free text.
- `screen(text)`: the names of the `PATTERNS` that occur in `text`, in `PATTERNS` order; `()` for none. A name, never
  the matched value.

The module is named after what it holds; it imports the standard library's `secrets` nowhere, and the modules that
need both read this one as `serve.secrets` (an absolute `import secrets` still names the standard library's).
"""
from __future__ import annotations

import re

KEY_RE = re.compile(r'asr_([0-9a-f]{8})_([A-Za-z0-9_-]{43})')
KEY_PREFIX_RE = re.compile(r'asr_[0-9a-f]{8}_')
PATTERNS = {'assure_key': KEY_RE}


def screen(text):
    """The names of the PATTERNS found in `text` (a str; anything else is the TypeError `re` raises), in PATTERNS order;
    `()` when none is found."""
    return tuple(name for name, rx in PATTERNS.items() if rx.search(text))
