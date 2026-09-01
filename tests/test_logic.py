#!/usr/bin/env python3
"""Offline regression tests for scripts/fetch_fpl_draft.py."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_fpl_draft.py"
SPEC = importlib.util.spec_from_file_location("fetch_fpl_draft", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def base_bootstrap(player_count: int = 30) -> dict:
    players = []
    for element_id in range(1, player_count + 1):
        players.append(
            {
                "id": element_id,
                "web_name": "Wirtz" if element_id == 1 else f"Player {element_id}",
                "first_name": "Florian" if element_id == 1 else "Test",
                "second_name": "Wirtz" if element_id == 1 else str(element_id),
                "team": 14 if element_id == 1 else 8,
                "element_type": ((element_id - 1) % 4) + 1,
                "draft_rank": element_id,
                "status": "a",
                "news": "",
            }
        )
    return {
        "elements": players,
        "teams": [
            {"id": 14, "name": "Liverpool", "short_name": "LIV"},
            {"id": 8, "name": "Chelsea", "short_name": "CHE"},
        ],
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 2, "singular_name_short": "DEF"},
            {"id": 3, "singular_name_short": "MID"},
            {"id": 4, "singular_name_short": "FWD"},
        ],
        "events": [],
    }


def base_details(two_teams: bool = True) -> dict:
    entries = [
        {
            "id": 42948,
            "entry_id": 42888,
            "entry_name": "AGFs Førstehold",
            "short_name": "JT",
        }
    ]
    if two_teams:
        entries.append(
            {
                "id": 138641,
                "entry_id": 138032,
                "entry_name": "Hyggemix",
                "short_name": "MB1",
            }
        )
    return {
        "league": {
            "id": 8905,
            "name": "OK Data Liga",
            "start_event": 1,
            "draft_status": "post",
            "drafts": [
                {
                    "id": 9516,
                    "event": 1,
                    "draft_dt": "2026-08-21T10:00:00Z",
                    "draft_started": True,
                    "draft_completed": "2026-08-21T10:35:00Z",
                }
            ],
        },
        "league_entries": entries,
        "matches": [
            {
                "id": 1,
                "event": 1,
                "league_entry_1": 42948,
                "league_entry_1_points": 57,
                "league_entry_2": 138641,
                "league_entry_2_points": 52,
                "finished": True,
            }
        ]
        if two_teams
        else [],
        "standings": [],
    }


class TestCoreLogic(unittest.TestCase):
    def test_sanitize_removes_private_manager_fields_recursively(self) -> None:
        payload = {
            "player_first_name": "Private",
            "entry_name": "Public Team",
            "nested": {"email": "private@example.com", "value": 1},
        }
        self.assertEqual(
            MODULE.sanitize(payload),
            {"entry_name": "Public Team", "nested": {"value": 1}},
        )

    def test_latest_complete_gameweek(self) -> None:
        details = {
            "matches": [
                {"event": 1, "finished": True},
                {"event": 1, "finished": True},
                {"event": 2, "finished": True},
                {"event": 2, "finished": False},
            ]
        }
        self.assertEqual(MODULE.latest_complete_gameweek(details), 1)

    def test_upcoming_event_id_uses_earliest_future_deadline(self) -> None:
        bootstrap = {
            "events": [
                {"id": 1, "deadline_time": "2026-08-20T17:30:00Z"},
                {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
                {"id": 3, "deadline_time": "2026-09-04T17:30:00Z"},
            ]
        }
        now = datetime(2026, 8, 21, tzinfo=timezone.utc)
        self.assertEqual(MODULE.upcoming_event_id(bootstrap, now), 2)

    def test_wirtz_watch_combines_stats_owner_lineup_fixture_and_h2h(self) -> None:
        watched = MODULE.build_watched_players(
            gameweek=1,
            watch_names=("Wirtz",),
            bootstrap=base_bootstrap(),
            details=base_details(),
            element_status={
                "element_status": [
                    {"element": 1, "owner": 42948, "status": "a"}
                ]
            },
            event_live={
                "elements": [
                    {
                        "id": 1,
                        "stats": {
                            "minutes": 84,
                            "total_points": 7,
                            "goals_scored": 0,
                            "assists": 1,
                            "bonus": 1,
                            "yellow_cards": 0,
                            "red_cards": 0,
                        },
                        "explain": [{"fixture": 99, "stats": []}],
                    }
                ]
            },
            entry_events={
                "42888": {
                    "picks": [
                        {"element": 1, "position": 6, "multiplier": 1}
                    ]
                }
            },
            pl_fixtures=[
                {
                    "id": 99,
                    "team_h": 14,
                    "team_a": 8,
                    "team_h_score": 2,
                    "team_a_score": 1,
                    "finished": True,
                }
            ],
        )
        self.assertEqual(watched["gameweek"], 1)
        self.assertEqual(len(watched["players"]), 1)
        wirtz = watched["players"][0]
        self.assertEqual(wirtz["web_name"], "Wirtz")
        self.assertEqual(wirtz["owner"]["entry_name"], "AGFs Førstehold")
        self.assertEqual(wirtz["squad_status"], "starter")
        self.assertEqual(wirtz["points_counted"], 7)
        self.assertEqual(wirtz["stats"]["assists"], 1)
        self.assertEqual(wirtz["fixtures"][0]["opponent_club_short_name"], "CHE")
        self.assertEqual(wirtz["h2h"]["opponent_entry_name"], "Hyggemix")
        self.assertEqual(wirtz["h2h"]["result"], "win")
        self.assertTrue(wirtz["h2h"]["points_exceeded_final_margin"])

    def test_wirtz_watch_reports_bench_points_without_guessing(self) -> None:
        watched = MODULE.build_watched_players(
            gameweek=1,
            watch_names=("Wirtz",),
            bootstrap=base_bootstrap(),
            details=base_details(),
            element_status={"element_status": [{"element": 1, "owner": 42948}]},
            event_live={"elements": [{"id": 1, "stats": {"total_points": 5}}]},
            entry_events={
                "42888": {
                    "picks": [{"element": 1, "position": 13, "multiplier": 0}]
                }
            },
            pl_fixtures=[],
        )
        wirtz = watched["players"][0]
        self.assertEqual(wirtz["squad_status"], "bench")
        self.assertEqual(wirtz["points_counted"], 0)
        self.assertEqual(wirtz["bench_points"], 5)

    def test_draft_recap_uses_true_choice_order_and_builds_complete_teams(self) -> None:
        details = base_details()
        bootstrap = base_bootstrap(30)
        choices = {"choices": []}
        statuses = []
        for overall_pick in range(1, 31):
            round_number = (overall_pick - 1) // 2 + 1
            pick_in_round = (overall_pick - 1) % 2
            if round_number % 2 == 1:
                owner = 42948 if pick_in_round == 0 else 138641
            else:
                owner = 138641 if pick_in_round == 0 else 42948
            choices["choices"].append(
                {
                    "choice": overall_pick,
                    "element": overall_pick,
                    "league_entry": owner,
                }
            )
            statuses.append({"element": overall_pick, "owner": owner})

        recap = MODULE.build_draft_recap(
            league_id=8905,
            details=details,
            bootstrap=bootstrap,
            element_status={"element_status": statuses},
            choices=choices,
            transactions={"transactions": []},
            watch_names=("Wirtz",),
        )
        self.assertTrue(recap["recap_ready"])
        self.assertIsNotNone(recap["draft_fingerprint"])
        self.assertEqual(recap["data_quality"]["resolved_picks"], 30)
        self.assertTrue(recap["data_quality"]["pick_order_available"])
        self.assertEqual(recap["picks"][0]["web_name"], "Wirtz")
        self.assertEqual(recap["watched_players"][0]["overall_pick"], 1)
        self.assertEqual(len(recap["teams"]), 2)
        self.assertTrue(all(team["squad_size"] == 15 for team in recap["teams"]))
        self.assertEqual(
            [item["entry_name"] for item in recap["draft_order"]],
            ["AGFs Førstehold", "Hyggemix"],
        )

    def test_wirtz_watch_prefers_historical_lineup_owner_over_current_owner(self) -> None:
        watched = MODULE.build_watched_players(
            gameweek=1,
            watch_names=("Wirtz",),
            bootstrap=base_bootstrap(),
            details=base_details(),
            element_status={
                "element_status": [{"element": 1, "owner": 138641}]
            },
            event_live={
                "elements": [{"id": 1, "stats": {"total_points": 7}}]
            },
            entry_events={
                "42888": {
                    "picks": [{"element": 1, "position": 6, "multiplier": 1}]
                },
                "138032": {"picks": []},
            },
            pl_fixtures=[],
        )
        wirtz = watched["players"][0]
        self.assertEqual(wirtz["owner_source"], "entry-events")
        self.assertEqual(wirtz["owner"]["entry_name"], "AGFs Førstehold")
        self.assertEqual(wirtz["current_owner"]["entry_name"], "Hyggemix")

    def test_draft_recap_falls_back_to_owner_rosters_when_choices_unavailable(self) -> None:
        details = base_details()
        bootstrap = base_bootstrap(30)
        statuses = [
            {"element": element_id, "owner": 42948 if element_id <= 15 else 138641}
            for element_id in range(1, 31)
        ]
        recap = MODULE.build_draft_recap(
            league_id=8905,
            details=details,
            bootstrap=bootstrap,
            element_status={"element_status": statuses},
            choices=None,
            transactions=None,
            watch_names=("Wirtz",),
        )
        self.assertTrue(recap["recap_ready"])
        self.assertEqual(recap["data_quality"]["squad_source"], "element-status")
        self.assertFalse(recap["data_quality"]["pick_order_available"])
        self.assertEqual(recap["watched_players"][0]["entry_name"], "AGFs Førstehold")
        self.assertIsNone(recap["watched_players"][0]["overall_pick"])

    def test_live_choices_shape_uses_index_and_ignores_vacant_entry_shell(self) -> None:
        details = base_details()
        details["league_entries"].append(
            {
                "id": 420622,
                "entry_id": None,
                "entry_name": None,
                "short_name": "AV",
            }
        )
        bootstrap = base_bootstrap(30)
        choices = {"choices": []}
        statuses = []
        for overall_pick in range(1, 31):
            round_number = (overall_pick - 1) // 2 + 1
            pick_in_round = (overall_pick - 1) % 2 + 1
            if round_number % 2 == 1:
                owner = 42888 if pick_in_round == 1 else 138032
            else:
                owner = 138032 if pick_in_round == 1 else 42888
            choices["choices"].append(
                {
                    "index": overall_pick,
                    "pick": pick_in_round,
                    "round": round_number,
                    "element": overall_pick,
                    "entry": owner,
                }
            )
            league_entry_owner = 42948 if owner == 42888 else 138641
            statuses.append({"element": overall_pick, "owner": league_entry_owner})

        recap = MODULE.build_draft_recap(
            league_id=8905,
            details=details,
            bootstrap=bootstrap,
            element_status={"element_status": statuses},
            choices=choices,
            transactions={"transactions": []},
            watch_names=("Wirtz",),
        )

        self.assertTrue(recap["recap_ready"])
        self.assertEqual(recap["data_quality"]["expected_picks"], 30)
        self.assertEqual(recap["data_quality"]["resolved_picks"], 30)
        self.assertTrue(recap["data_quality"]["pick_order_available"])
        self.assertEqual(recap["data_quality"]["pick_order_source"], "explicit_choice_field")
        self.assertEqual(recap["picks"][2]["overall_pick"], 3)
        self.assertEqual(recap["picks"][2]["pick_in_round"], 1)
        self.assertEqual(len(recap["teams"]), 2)
        self.assertNotIn(420622, {team["league_entry_id"] for team in recap["teams"]})


    def test_transactions_are_separated_from_post_gameweek_activity(self) -> None:
        details = base_details()
        details["league"]["drafts"][0]["draft_completed"] = "2026-08-21T10:35:00Z"
        details["matches"] = [
            {"event": 1, "finished": True, "league_entry_1": 42948, "league_entry_2": 138641, "league_entry_1_points": 10, "league_entry_2_points": 9},
        ]
        transactions = {"transactions": [
            {"id": 1, "entry": 42948, "element_in": 2, "element_out": 3, "kind": "f", "result": "a", "event": 1, "added": "2026-08-21T11:00:00Z"},
            {"id": 2, "entry": 42948, "element_in": 4, "element_out": 5, "kind": "w", "result": "p", "event": 2, "added": "2026-08-27T18:00:00Z"},
        ]}
        enriched = MODULE.enrich_transactions(transactions, details, base_bootstrap())
        phases = {tx["transaction_id"]: tx["phase"] for tx in enriched["transactions"]}
        self.assertEqual(phases[1], "gw1")
        self.assertEqual(phases[2], "current_transfer_window")
        post = MODULE.post_gameweek_transactions(enriched)
        self.assertEqual(post["transfer_window_gameweek"], 2)
        self.assertEqual(post["transaction_count"], 1)
        self.assertEqual(post["transactions"][0]["transaction_id"], 2)


    def test_transfer_window_advances_with_latest_complete_gameweek(self) -> None:
        details = base_details()
        details["league"]["drafts"][0]["draft_completed"] = "2026-08-21T10:35:00Z"
        details["matches"] = [
            {"event": 3, "finished": True, "league_entry_1": 42948, "league_entry_2": 138641, "league_entry_1_points": 10, "league_entry_2_points": 9},
        ]
        transactions = {"transactions": [
            {"id": 2, "entry": 42948, "kind": "w", "result": "p", "event": 4, "added": "2026-09-03T18:00:00Z"},
            {"id": 3, "entry": 42948, "kind": "w", "result": "p", "event": 3, "added": "2026-08-29T18:00:00Z"},
        ]}
        enriched = MODULE.enrich_transactions(transactions, details, base_bootstrap())
        window = MODULE.current_transfer_window(enriched)
        self.assertEqual(window["latest_complete_gameweek"], 3)
        self.assertEqual(window["transfer_window_gameweek"], 4)
        self.assertEqual([tx["transaction_id"] for tx in window["transactions"]], [2])

    def test_transactions_are_typed_only_from_explicit_kind(self) -> None:
        transactions = {
            "transactions": [
                {
                    "id": 1,
                    "entry": 42948,
                    "element_in": 2,
                    "element_out": 3,
                    "kind": "w",
                    "result": "a",
                    "event": 2,
                },
                {
                    "id": 2,
                    "entry": 138641,
                    "element_in": 4,
                    "element_out": 5,
                },
            ]
        }
        enriched = MODULE.enrich_transactions(
            transactions, base_details(), base_bootstrap()
        )
        first, second = enriched["transactions"]
        self.assertEqual(first["transaction_type"], "waiver")
        self.assertEqual(first["result"], "accepted")
        self.assertEqual(first["entry_name"], "AGFs Førstehold")
        self.assertEqual(first["element_in"]["web_name"], "Player 2")
        self.assertIsNone(second["transaction_type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

    def test_current_rosters_and_free_agents_separates_owned_and_unowned(self) -> None:
        details = base_details()
        bootstrap = base_bootstrap(20)
        statuses = [
            *[{'element': i, 'owner': 42948} for i in range(1, 16)],
            *[{'element': i, 'owner': None} for i in range(16, 21)],
        ]
        state = MODULE.current_rosters_and_free_agents(
            {'element_status': statuses}, details, bootstrap
        )
        self.assertEqual(state['owned_player_count'], 15)
        self.assertEqual(state['free_agent_count'], 5)
        jt = next(r for r in state['rosters'] if r['league_entry_id'] == 42948)
        self.assertEqual(jt['player_count'], 15)
        self.assertEqual({p['element_id'] for p in state['free_agents']}, set(range(16, 21)))

    def test_proposed_waivers_extracts_pending_waivers_only(self) -> None:
        enriched = {
            'data_quality': {'source_available': True},
            'transactions': [
                {'transaction_type': 'waiver', 'result': 'pending', 'transaction_id': 1},
                {'transaction_type': 'waiver', 'result': 'accepted', 'transaction_id': 2},
                {'transaction_type': 'free_agent', 'result': 'accepted', 'transaction_id': 3},
            ],
        }
        result = MODULE.proposed_waivers(enriched)
        self.assertEqual(result['pending_waiver_count'], 1)
        self.assertEqual(result['waivers'][0]['transaction_id'], 1)
