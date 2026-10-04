"""The Assure GitHub Action: `entry.py` runs in the customer's own runner; `collect.py` runs the frozen read-only
collector by digest; `serve/bundle.py` bounds what may be sent; `client.py` sends the collected facts to the hosted API and
reads back the verdict; `local_mode.py` (private repository only) runs the check in the runner; `build_dist.py`
assembles the public Action tree and the server tree. Standard library only."""

# execution_authorized false; hardware_authorized false; industrial_release_authorized false; release_allowed false; physical_validation false; simulation true; self_approved false.
