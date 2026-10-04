"""Serving the Assure checker to customers (SERVE-001, DESIGN-001 and BUILD-SPEC-001).

One code path for the Action and the hosted API: bundle -> pin.verify -> profiles.run -> envelope -> render. Nothing
here edits or imports a checker file directly: checkers are reached only through `assure.checkers.load_checker`, which
re-hashes every file before anything runs. Customer bytes are data: never imported, evaluated or passed to a shell.
Standard library only.

Importing this package turns bytecode writing off for the process: `serve.pin.verify` refuses any `__pycache__` or `.pyc`
under assure/, serve/ and action/, so no entry point may leave one behind. Run every entry point with `python3 -B` too, so
the package's own first import writes nothing either.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

FLAGS = {'execution_authorized': False, 'hardware_authorized': False, 'industrial_release_authorized': False,
         'release_allowed': False, 'physical_validation': False, 'simulation': True, 'self_approved': False}


def flags():
    """A fresh copy of the seven flags, for an output document."""
    return dict(FLAGS)

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
