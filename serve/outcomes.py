"""Typed failure outcomes (DD-054; DESIGN-001 section 5). A failure is a named outcome, never a silent pass and never an
unexplained stop. Each carries an HTTP status (API), an exit code (Action) and one plain sentence telling the customer
what to do next.

The database's outcome list (db/migrations/0001_foundation.sql) holds every name here. `lease_lost` and the other
job-internal names (lease_expired, attempts_exhausted, ...) stay in the database and hosted/jobs.py: a customer never
receives them."""
from __future__ import annotations

from types import MappingProxyType

_TABLE = {
    'bad_input': (400, 2, 'Fix the request so every file is allow-listed for the profile and well formed, then send it again.'),
    'oversize_input': (413, 2, 'Send fewer or smaller files, within the published size and count limits.'),
    'unknown_profile': (404, 2, 'Choose a profile from the list of served profiles.'),
    'unauthenticated': (401, None, 'Send a valid, unrevoked API key in the Authorization header.'),
    'rate_limited': (429, None, 'Wait for the time given in Retry-After, then send the request again.'),
    'credit_exhausted': (402, None, 'Your free credit is spent; contact Symbolia to continue.'),
    'engine_digest_mismatch': (503, 3, 'Report it to Symbolia (or reinstall the pinned release when you run the engine yourself), because the engine files differ from their pin and no check ran.'),
    'collector_cannot_connect': (None, 3, 'Check the connection settings and that the server accepts the collection role.'),
    'collector_refused': (422, 3, 'Fix the condition the reason names and run again, or, for a rule or setting shape that cannot be checked yet, send Symbolia the file name and line number it gives.'),
    'profile_not_servable': (503, 3, 'Use another profile, because this one is not yet qualified to serve readings.'),
    'profile_refused': (422, 3, 'Fix the collection or declaration fault the reason names, then run again.'),
    'checker_error': (500, 3, 'Report the check id to Symbolia, because the checker failed in a way it should not.'),
    'checker_timeout': (504, 3, 'Send a smaller input or try again later, because the check ran past its time limit.'),
    'server_busy': (503, None, 'Try again in a minute, because the queue is full.'),
    'not_found': (404, None, 'Check the check id, because no check with that id exists for this account.'),
    'secret_in_input': (422, 2, 'Remove the secret the reason names from the input, then send it again; nothing was stored.'),
    'store_unavailable': (503, None, 'Try again in a minute, because the result store cannot be reached just now.'),
    # The Action's own outcomes when it reaches the hosted API: never sent by the server, so they carry no HTTP status.
    'api_unreachable': (None, 3, 'Check that the runner can reach the API over HTTPS, then run the job again.'),
    'api_error': (None, 3, 'Run the job again later, and report the check id to Symbolia if it happens again.'),
}

OUTCOMES = MappingProxyType({name: MappingProxyType({'http': http, 'exit': code, 'action': action})
                             for name, (http, code, action) in _TABLE.items()})


class Refusal(Exception):
    """A typed outcome: `Refusal(outcome, reason, **detail)`. An unknown outcome name is a ValueError at construction."""

    def __init__(self, outcome, reason='', **detail):
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise ValueError('unknown outcome: %r' % (outcome,))
        self.outcome = outcome
        self.reason = str(reason)
        self.detail = dict(detail)
        super().__init__('%s: %s' % (outcome, self.reason))

    @property
    def http(self):
        return OUTCOMES[self.outcome]['http']

    @property
    def exit(self):
        return OUTCOMES[self.outcome]['exit']

    @property
    def action(self):
        return OUTCOMES[self.outcome]['action']

    def to_dict(self):
        return {'outcome': self.outcome, 'reason': self.reason, 'action': self.action, 'detail': dict(self.detail)}

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
