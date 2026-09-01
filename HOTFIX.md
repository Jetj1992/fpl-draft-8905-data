# Draft recap hotfix

Replace these two files in the repository:

- `scripts/fetch_fpl_draft.py`
- `tests/test_logic.py`

The hotfix:

1. ignores vacant/removed league-entry shells with a null `entry_id`;
2. uses `choices[].index` as the overall draft pick;
3. uses `choices[].pick` as the pick inside the round;
4. validates the real seven-team draft as 105 picks;
5. allows `recap_ready`, `draft_fingerprint` and the immutable initial snapshot to be created.

After committing, manually run the GitHub Action once. The expected result is:

- `number_of_entries: 7`
- `draft.recap_ready: true`
- `draft.pick_order_available: true`
- `draft.resolved_picks: 105`
- a non-null `draft.recap_fingerprint`
- `data/draft/initial/draft-recap.json` exists


## Current-state / transfer fix

The current sync now classifies transactions into phases so draft and GW1 setup activity is not confused with activity after the latest completed gameweek. It writes `data/current/post-gameweek-transactions.json` for transfer reporting. Pending waivers are limited to the `post_complete_gw` phase.
