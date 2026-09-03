# OK Data Liga - consolidated public JSON

The active fetcher now publishes one consolidated public artifact:

`data/fpl-draft.json`

The document contains current data, draft data and historical completed gameweek snapshots. Legacy per-file JSON outputs are folded into the aggregate and removed after a successful write.

The GitHub Pages job publishes only `data/fpl-draft.json`.

Run locally:

`python scripts/fetch_fpl_draft.py --league-id 8905 --watch-player Wirtz`

Run tests:

`python tests/test_logic.py`
