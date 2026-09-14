#!/usr/bin/env python3
"""Offline regression tests for scripts/fetch_fpl_draft.py."""
from __future__ import annotations

import importlib.util
import sys
import json
import tempfile
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

    def test_aggregate_document_uses_top_level_current_payload(self) -> None:
        summary = {
            "schema_version": 6,
            "generated_at": "2026-09-03T12:00:00Z",
            "league_id": 8905,
            "league_name": "OK Data Liga",
        }
        initial_draft = {"draft_recap": {"recap_ready": True, "draft_fingerprint": "abc"}}
        document = MODULE.build_aggregate_document(
            summary=summary,
            bootstrap={"elements": []},
            fpl_calendar={"events": []},
            details={"standings": []},
            optional_data={"element_status": {"element_status": []}},
            entry_public={},
            transactions_enriched={"transactions": []},
            current_state={"owned_player_count": 105},
            proposed_waivers_data={"pending_waiver_count": 0},
            draft_recap=initial_draft["draft_recap"],
            round_context={"next_deadline": None},
            pl_fixtures={2: []},
            event_live={"elements": []},
            entry_events={},
            watched_payload={"players": []},
            history={"gw-01": {"summary": {"latest_complete_gameweek": 1}}},
            initial_draft=initial_draft,
        )

        self.assertEqual(document["schema_version"], 6)
        self.assertEqual(document["league_id"], 8905)
        self.assertIn("summary", document)
        self.assertIn("league_details", document)
        self.assertIn("draft_recap", document)
        self.assertIn("history", document)
        self.assertIn("initial_draft", document)
        self.assertNotIn("current", document)
        self.assertNotIn("draft", document)

    def test_aggregate_document_preserves_history_and_draft_at_top_level(self) -> None:
        document = MODULE.build_aggregate_document(
            summary={"generated_at": "now", "league_id": 8905, "league_name": "OK Data Liga"},
            bootstrap={},
            fpl_calendar={},
            details={},
            optional_data={},
            entry_public={},
            transactions_enriched={},
            current_state={},
            proposed_waivers_data={},
            draft_recap={"recap_ready": True},
            round_context={},
            pl_fixtures={},
            event_live={},
            entry_events={},
            watched_payload=None,
            history={"gw-02": {"summary": {"latest_complete_gameweek": 2}}},
            initial_draft={"draft_recap": {"draft_fingerprint": "xyz"}},
        )

        self.assertEqual(document["history"]["gw-02"]["summary"]["latest_complete_gameweek"], 2)
        self.assertEqual(document["initial_draft"]["draft_recap"]["draft_fingerprint"], "xyz")
        self.assertEqual(document["draft_recap"]["recap_ready"], True)

    def test_aggregate_document_is_json_serializable(self) -> None:
        document = MODULE.build_aggregate_document(
            summary={"league_id": 8905},
            bootstrap={},
            fpl_calendar={},
            details={},
            optional_data={},
            entry_public={},
            transactions_enriched={},
            current_state={},
            proposed_waivers_data={},
            draft_recap={},
            round_context={},
            pl_fixtures={2: [{"fixture": 1}]},
            event_live={},
            entry_events={},
            watched_payload=None,
            history={"gw-02": {}},
            initial_draft=None,
        )
        encoded = json.dumps(document, ensure_ascii=False)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["schema_version"], 6)
        self.assertEqual(decoded["pl_fixtures"]["2"][0]["fixture"], 1)




    def test_live_gameweek_builds_scores_remaining_players_and_key_matchups(self) -> None:
        details = base_details()
        details["league_entries"].extend([
            {"id": 321694, "entry_id": 318564, "entry_name": "La Liga es la mejor", "short_name": "AK"},
            {"id": 138748, "entry_id": 138139, "entry_name": "Jyllands Rubin", "short_name": "NH"},
        ])
        details["matches"] = [
            {
                "id": 77, "event": 2, "finished": False,
                "league_entry_1": 42948, "league_entry_2": 138641,
                "league_entry_1_points": 0, "league_entry_2_points": 0,
            },
            {
                "id": 78, "event": 2, "finished": False,
                "league_entry_1": 138641, "league_entry_2": 138748,
                "league_entry_1_points": 0, "league_entry_2_points": 0,
            },
        ]
        bootstrap = base_bootstrap()
        bootstrap["events"] = [{"id": 2, "name": "Gameweek 2", "deadline_time": "2026-08-28T17:30:00Z", "is_current": True}]
        bootstrap["teams"] = [
            {"id": 1, "name": "Club A", "short_name": "A"},
            {"id": 2, "name": "Club B", "short_name": "B"},
            {"id": 3, "name": "Club C", "short_name": "C"},
            {"id": 4, "name": "Club D", "short_name": "D"},
        ]
        bootstrap["elements"] = [
            {"id": 1, "web_name": "Player 1", "first_name": "Player", "second_name": "One", "team": 1, "element_type": 3, "draft_rank": 10, "total_points": 20, "status": "a", "news": ""},
            {"id": 2, "web_name": "Player 2", "first_name": "Player", "second_name": "Two", "team": 2, "element_type": 3, "draft_rank": 20, "total_points": 15, "status": "a", "news": ""},
            {"id": 3, "web_name": "Player 3", "first_name": "Player", "second_name": "Three", "team": 3, "element_type": 3, "draft_rank": 30, "total_points": 12, "status": "a", "news": ""},
            {"id": 4, "web_name": "Player 4", "first_name": "Player", "second_name": "Four", "team": 4, "element_type": 3, "draft_rank": 40, "total_points": 8, "status": "a", "news": ""},
        ]
        event_live = {
            "elements": [
                {"id": 1, "stats": {"total_points": 8}},
                {"id": 2, "stats": {"total_points": 6}},
                {"id": 3, "stats": {"total_points": 4}},
                {"id": 4, "stats": {"total_points": 2}},
            ]
        }
        entry_events = {
            "42888": {"entry_history": {"points": 14}, "picks": [{"element": 1, "position": 1, "multiplier": 1}]},
            "138032": {"entry_history": {"points": 11}, "picks": [{"element": 2, "position": 1, "multiplier": 1}]},
            "138139": {"entry_history": {"points": 7}, "picks": [{"element": 3, "position": 1, "multiplier": 1}]},
            "138748": {"entry_history": {"points": 6}, "picks": [{"element": 4, "position": 1, "multiplier": 1}]},
            "137879": {"entry_history": {"points": 0}, "picks": []},
            "137912": {"entry_history": {"points": 0}, "picks": []},
            "318564": {"entry_history": {"points": 0}, "picks": []},
        }
        fixtures = [
            {"id": 1, "event": 2, "team_h": 1, "team_a": 4, "finished": True, "finished_provisional": True, "started": True, "kickoff_time": "2026-08-28T19:00:00Z"},
            {"id": 2, "event": 2, "team_h": 2, "team_a": 3, "finished": False, "finished_provisional": False, "started": False, "kickoff_time": "2026-08-29T15:00:00Z"},
        ]
        snapshot = MODULE.build_live_gameweek_snapshot(
            gameweek=2,
            bootstrap=bootstrap,
            details=details,
            event_live=event_live,
            entry_events=entry_events,
            pl_fixtures=fixtures,
        )
        manager = next(item for item in snapshot["managers"] if item["league_entry_id"] == 42948)
        self.assertEqual(manager["live_score"], 14)
        self.assertEqual(manager["remaining_player_count"], 0)
        manager2 = next(item for item in snapshot["managers"] if item["league_entry_id"] == 138641)
        self.assertEqual(manager2["live_score"], 11)
        self.assertEqual(manager2["remaining_player_count"], 1)
        self.assertEqual(manager2["remaining_players"][0]["player_name"], "Player 2")
        self.assertEqual(snapshot["h2h_matches"][0]["entry_1_score"], 14)
        self.assertEqual(snapshot["h2h_matches"][0]["entry_2_score"], 11)
        self.assertTrue(snapshot["h2h_matches"][0]["key_match"])
        self.assertEqual(snapshot["key_matchups"][0]["match_id"], 77)

    def test_live_gameweek_has_no_predictive_probability_fields(self) -> None:
        snapshot = MODULE.build_live_gameweek_snapshot(
            gameweek=1,
            bootstrap=base_bootstrap(),
            details=base_details(),
            event_live={"elements": []},
            entry_events={"42888": {"entry_history": {"points": 0}, "picks": []}, "138032": {"entry_history": {"points": 0}, "picks": []}},
            pl_fixtures=[],
        )
        self.assertNotIn("win_probability", snapshot)
        self.assertNotIn("expected_points", snapshot)

    def test_recap_snapshot_builds_top_level_h2h_standings_transfers_and_wirtz(self) -> None:
        details = base_details()
        details["standings"] = [
            {
                "league_entry": 42948,
                "rank": 1,
                "total": 3,
                "matches_played": 1,
                "matches_won": 1,
                "matches_drawn": 0,
                "matches_lost": 0,
                "points_for": 57,
            },
            {
                "league_entry": 138641,
                "rank": 2,
                "total": 0,
                "matches_played": 1,
                "matches_won": 0,
                "matches_drawn": 0,
                "matches_lost": 1,
                "points_for": 52,
            },
        ]
        entry_events = {
            "42888": {
                "picks": [
                    {"element": 1, "position": 1, "multiplier": 1},
                    {"element": 2, "position": 2, "multiplier": 0},
                ]
            },
            "138032": {
                "picks": [
                    {"element": 3, "position": 1, "multiplier": 1},
                ]
            },
        }
        event_live = {
            "elements": [
                {"id": 1, "stats": {"minutes": 90, "total_points": 7, "goals_scored": 1, "assists": 0, "bonus": 1, "expected_goals": 0.2, "expected_assists": 0.1}},
                {"id": 2, "stats": {"minutes": 10, "total_points": 2}},
                {"id": 3, "stats": {"minutes": 90, "total_points": 9}},
            ]
        }
        transactions = {
            "transactions": [
                {"id": 10, "event": 1, "entry": 42888, "element_in": 2, "element_out": 3, "kind": "w", "result": "a"}
            ]
        }
        enriched = MODULE.enrich_transactions(transactions, details, base_bootstrap())
        watched = MODULE.build_watched_players(
            gameweek=1, watch_names=("Wirtz",), bootstrap=base_bootstrap(), details=details,
            element_status={"element_status": [{"element": 1, "owner": 42948}]},
            event_live=event_live, entry_events=entry_events, pl_fixtures=[],
        )
        recap = MODULE.build_recap_snapshot(
            gameweek=1, bootstrap=base_bootstrap(), details=details, event_live=event_live,
            entry_events=entry_events, element_status={"element_status": [{"element": 1, "owner": 42948}, {"element": 3, "owner": 138641}]},
            transactions_enriched=enriched, trades={"trades": []}, watched_payload=watched, pl_fixtures=[], generated_at="now"
        )
        self.assertTrue(recap["metadata"]["recap_ready"])
        self.assertEqual(recap["h2h_matches"][0]["entry_1_name"], "AGFs Førstehold")
        self.assertEqual(recap["standings"][0]["rank"], 1)
        self.assertEqual(recap["transactions"][0]["transaction_type"], "waiver")
        self.assertEqual(recap["wirtz"]["owner_entry_name"], "AGFs Førstehold")
        self.assertEqual(recap["wirtz"]["points_counted"], 7)

    def test_liga_average_uses_other_active_gw_scores(self) -> None:
        details = base_details()
        details["league_entries"].append({
            "id": 321694,
            "entry_id": 318564,
            "entry_name": "La Liga es la mejor",
            "short_name": "AK",
        })
        details["matches"] = [{
            "event": 1,
            "finished": True,
            "league_entry_1": 42948,
            "league_entry_1_points": 50,
            "league_entry_2": 138641,
            "league_entry_2_points": 40,
        }]
        entries = MODULE.active_league_entries(details)
        matches, contexts = MODULE.normalize_h2h_matches(details, 1, entries)
        average = next(item for item in matches if not item["is_real_opponent"])
        self.assertEqual(average["entry_1_id"], 321694)
        self.assertEqual(average["entry_2_name"], "Liga Average")
        self.assertEqual(average["entry_2_score"], 45)
        self.assertEqual(average["entry_1_score"], None)

    def test_recap_snapshot_marks_missing_wirtz_as_not_ready(self) -> None:
        details = base_details()
        recap = MODULE.build_recap_snapshot(
            gameweek=1, bootstrap=base_bootstrap(), details=details, event_live={"elements": []},
            entry_events={"42888": {"picks": []}, "138032": {"picks": []}},
            element_status={"element_status": []},
            transactions_enriched={"transactions": []}, trades={"trades": []},
            watched_payload={"players": []}, pl_fixtures=[], generated_at="now"
        )
        self.assertFalse(recap["metadata"]["recap_ready"])
        self.assertIn("Wirtz record unavailable", recap["metadata"]["validation_errors"])

    def test_remove_legacy_outputs_removes_all_legacy_public_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            for directory_name in ("current", "history", "draft"):
                directory = data_dir / directory_name
                directory.mkdir(parents=True)
                (directory / "legacy.json").write_text("{}", encoding="utf-8")

            MODULE.remove_legacy_outputs(data_dir)

            for directory_name in ("current", "history", "draft"):
                self.assertFalse((data_dir / directory_name).exists())

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
