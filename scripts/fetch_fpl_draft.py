#!/usr/bin/env python3
"""Fetch and enrich public FPL Draft data for league recaps.

Designed for GitHub Actions. No login, password, cookie or API key is required.

In addition to the raw league/gameweek data, the script creates two recap-ready
artifacts:

* ``data/current/draft-recap.json`` and an immutable initial-draft snapshot.
* ``data/current/watched-players.json`` plus one file in every completed GW
  snapshot. Florian Wirtz is watched by default.

The code deliberately keeps uncertain facts explicit. It never labels a player
movement as a waiver or free-agent transfer unless the transaction payload does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DRAFT_BASE_URL = "https://draft.premierleague.com/api"
FPL_BASE_URL = "https://fantasy.premierleague.com/api"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)

PRIVATE_KEYS = {
    "player_first_name",
    "player_last_name",
    "player_email",
    "email",
}

POSITION_LABELS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
DEFAULT_WATCH_PLAYERS = ("Wirtz",)
EXPECTED_SQUAD_SIZE = 15
WATCH_STAT_FIELDS = (
    "minutes",
    "starts",
    "total_points",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "saves",
    "bonus",
    "bps",
    "defensive_contribution",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
)
TRANSACTION_KIND_LABELS = {
    "w": "waiver",
    "waiver": "waiver",
    "f": "free_agent",
    "fa": "free_agent",
    "free_agent": "free_agent",
    "free agent": "free_agent",
    "t": "trade",
    "trade": "trade",
    "d": "draft",
    "draft": "draft",
}
TRANSACTION_RESULT_LABELS = {
    "a": "accepted",
    "accepted": "accepted",
    "s": "successful",
    "successful": "successful",
    "p": "pending",
    "pending": "pending",
    "r": "rejected",
    "rejected": "rejected",
    "i": "invalid",
    "invalid": "invalid",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize(value: Any) -> Any:
    """Recursively remove private manager fields before writing public JSON."""
    if isinstance(value, dict):
        return {
            key: sanitize(val)
            for key, val in value.items()
            if key not in PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def fetch_json(
    base_url: str,
    path: str,
    *,
    required: bool = False,
    attempts: int = 4,
) -> tuple[Any | None, dict[str, Any]]:
    """Fetch JSON with small retries and a machine-readable status block."""
    url = f"{base_url}{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://draft.premierleague.com/",
        "Cache-Control": "no-cache",
    }
    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw)
                return payload, {
                    "ok": True,
                    "status": response.status,
                    "path": path,
                    "host": base_url,
                }
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code in {401, 403, 404}:
                break
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(min(2**attempt, 10))
                continue
            break
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 10))

    status = {
        "ok": False,
        "error": last_error or "unknown error",
        "path": path,
        "host": base_url,
    }
    if required:
        raise RuntimeError(f"Required endpoint failed: {url} ({status['error']})")
    print(f"Optional endpoint unavailable: {url} ({status['error']})", file=sys.stderr)
    return None, status


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(sanitize(payload), ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        sanitize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def first_int(mapping: dict[str, Any], keys: Iterable[str]) -> int | None:
    return as_int(first_present(mapping, keys))


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def extract_records(payload: Any, preferred_keys: Iterable[str]) -> list[dict[str, Any]]:
    """Return a list of dictionaries from common API envelope shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def compact_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    player_fields = (
        "id",
        "web_name",
        "first_name",
        "second_name",
        "team",
        "element_type",
        "status",
        "news",
        "chance_of_playing_this_round",
        "chance_of_playing_next_round",
        "draft_rank",
        "total_points",
        "minutes",
    )
    team_fields = ("id", "name", "short_name")
    event_fields = (
        "id",
        "name",
        "deadline_time",
        "deadline_time_epoch",
        "finished",
        "data_checked",
        "is_previous",
        "is_current",
        "is_next",
    )
    type_fields = (
        "id",
        "singular_name",
        "singular_name_short",
        "plural_name",
        "squad_select",
    )
    return {
        "elements": [
            {key: item.get(key) for key in player_fields if key in item}
            for item in payload.get("elements", [])
            if isinstance(item, dict)
        ],
        "teams": [
            {key: item.get(key) for key in team_fields if key in item}
            for item in payload.get("teams", [])
            if isinstance(item, dict)
        ],
        "events": [
            {key: item.get(key) for key in event_fields if key in item}
            for item in payload.get("events", [])
            if isinstance(item, dict)
        ],
        "element_types": [
            {key: item.get(key) for key in type_fields if key in item}
            for item in payload.get("element_types", [])
            if isinstance(item, dict)
        ],
    }


def latest_complete_gameweek(details: dict[str, Any]) -> int | None:
    matches = details.get("matches") or []
    by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        if not isinstance(match, dict):
            continue
        event = as_int(match.get("event"))
        if event is not None:
            by_event[event].append(match)
    completed = [
        event
        for event, event_matches in by_event.items()
        if event_matches and all(bool(match.get("finished")) for match in event_matches)
    ]
    return max(completed) if completed else None


def league_name(details: dict[str, Any]) -> str | None:
    league = details.get("league")
    if isinstance(league, dict):
        return league.get("name")
    return details.get("name")


def entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "entry_id", "entry_name", "short_name", "waiver_pick")
    return {key: entry.get(key) for key in keep if key in entry}


def event_map(bootstrap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for event in bootstrap.get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = as_int(event.get("id"))
        if event_id is not None:
            result[event_id] = event
    return result


def find_event_id(events: dict[int, dict[str, Any]], flag: str) -> int | None:
    for event_id, event in events.items():
        if event.get(flag) is True:
            return event_id
    return None


def upcoming_event_id(
    bootstrap: dict[str, Any], now: datetime | None = None
) -> int | None:
    """Return the gameweek with the earliest deadline still in the future."""
    now = now or datetime.now(timezone.utc)
    candidates: list[tuple[datetime, int]] = []
    for event in bootstrap.get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = as_int(event.get("id"))
        raw = event.get("deadline_time")
        if event_id is None or not isinstance(raw, str):
            continue
        try:
            deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if deadline > now:
            candidates.append((deadline, event_id))
    return min(candidates)[1] if candidates else None


def gameweek_ids(
    bootstrap: dict[str, Any], details: dict[str, Any]
) -> dict[str, int | None]:
    events = event_map(bootstrap)
    completed = latest_complete_gameweek(details)
    previous = find_event_id(events, "is_previous") or completed
    current = find_event_id(events, "is_current")
    nxt = find_event_id(events, "is_next")

    if current is None and nxt is not None and previous is not None and nxt == previous + 2:
        current = previous + 1
    if nxt is None and current is not None and current < max(events or {38: {}}):
        nxt = current + 1
    if previous is None and current is not None and current > 1:
        previous = current - 1

    return {
        "previous": previous,
        "current": current,
        "next": nxt,
        "upcoming": upcoming_event_id(bootstrap),
        "latest_complete": completed,
    }


def deadline_block(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    raw = event.get("deadline_time")
    result: dict[str, Any] = {
        "gameweek": event.get("id"),
        "name": event.get("name"),
        "deadline_time_utc": raw,
    }
    if isinstance(raw, str):
        try:
            deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            result["deadline_time_copenhagen"] = deadline.astimezone(
                ZoneInfo("Europe/Copenhagen")
            ).isoformat()
        except ValueError:
            pass
    return result


def draft_matches_for_event(
    details: dict[str, Any], event_id: int | None
) -> list[dict[str, Any]]:
    if event_id is None:
        return []
    return [
        match
        for match in (details.get("matches") or [])
        if isinstance(match, dict) and as_int(match.get("event")) == event_id
    ]


def build_round_context(
    bootstrap: dict[str, Any],
    details: dict[str, Any],
    pl_fixtures: dict[int, Any],
) -> dict[str, Any]:
    ids = gameweek_ids(bootstrap, details)
    events = event_map(bootstrap)
    rounds: dict[str, Any] = {}
    for label in ("previous", "current", "next", "upcoming"):
        gw = ids[label]
        if gw is None:
            rounds[label] = None
            continue
        rounds[label] = {
            "gameweek": gw,
            "event": events.get(gw),
            "deadline": deadline_block(events.get(gw)),
            "draft_h2h_matches": draft_matches_for_event(details, gw),
            "premier_league_fixtures": pl_fixtures.get(gw, []),
        }
    upcoming = ids["upcoming"]
    return {
        "gameweeks": ids,
        "next_deadline": deadline_block(events.get(upcoming)) if upcoming else None,
        "rounds": rounds,
    }


def entry_indexes(
    details: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_league_entry: dict[int, dict[str, Any]] = {}
    by_entry: dict[int, dict[str, Any]] = {}
    for item in details.get("league_entries") or []:
        if not isinstance(item, dict):
            continue
        league_entry_id = as_int(item.get("id"))
        entry_id = as_int(item.get("entry_id"))
        if league_entry_id is not None:
            by_league_entry[league_entry_id] = item
        if entry_id is not None:
            by_entry[entry_id] = item
    return by_league_entry, by_entry


def resolve_entry_reference(
    value: Any,
    by_league_entry: dict[int, dict[str, Any]],
    by_entry: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("league_entry_id", "league_entry", "id", "entry_id", "entry"):
            if key in value:
                resolved = resolve_entry_reference(
                    value[key], by_league_entry, by_entry
                )
                if resolved is not None:
                    return resolved
        return None
    identifier = as_int(value)
    if identifier is None:
        return None
    return by_league_entry.get(identifier) or by_entry.get(identifier)


def bootstrap_indexes(
    bootstrap: dict[str, Any],
) -> tuple[
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
]:
    players: dict[int, dict[str, Any]] = {}
    teams: dict[int, dict[str, Any]] = {}
    positions: dict[int, dict[str, Any]] = {}
    for item in bootstrap.get("elements", []):
        if isinstance(item, dict) and as_int(item.get("id")) is not None:
            players[int(item["id"])] = item
    for item in bootstrap.get("teams", []):
        if isinstance(item, dict) and as_int(item.get("id")) is not None:
            teams[int(item["id"])] = item
    for item in bootstrap.get("element_types", []):
        if isinstance(item, dict) and as_int(item.get("id")) is not None:
            positions[int(item["id"])] = item
    return players, teams, positions


def enrich_player(
    element_id: int,
    players: dict[int, dict[str, Any]],
    teams: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    player = players.get(element_id, {})
    team_id = as_int(player.get("team"))
    team = teams.get(team_id or -1, {})
    position_id = as_int(player.get("element_type"))
    return {
        "element_id": element_id,
        "web_name": player.get("web_name"),
        "first_name": player.get("first_name"),
        "second_name": player.get("second_name"),
        "club_id": team_id,
        "club_name": team.get("name"),
        "club_short_name": team.get("short_name"),
        "position_id": position_id,
        "position": POSITION_LABELS.get(position_id),
        "official_draft_rank": as_int(player.get("draft_rank")),
        "availability_status": player.get("status"),
        "news": player.get("news"),
    }


def resolve_watched_players(
    bootstrap: dict[str, Any], names: Iterable[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    players, teams, _ = bootstrap_indexes(bootstrap)
    result: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[int] = set()

    for requested in names:
        wanted = normalize_text(requested)
        exact: list[int] = []
        partial: list[int] = []
        for element_id, player in players.items():
            candidates = {
                normalize_text(player.get("web_name")),
                normalize_text(
                    f"{player.get('first_name', '')} {player.get('second_name', '')}"
                ),
                normalize_text(player.get("second_name")),
            }
            if wanted in candidates:
                exact.append(element_id)
            elif wanted and any(wanted in candidate for candidate in candidates if candidate):
                partial.append(element_id)

        matches = exact or partial
        if len(matches) == 1:
            element_id = matches[0]
            if element_id not in seen:
                item = enrich_player(element_id, players, teams)
                item["requested_name"] = requested
                result.append(item)
                seen.add(element_id)
        elif not matches:
            warnings.append(f"Watched player not found: {requested}")
        else:
            warnings.append(
                f"Watched player name is ambiguous: {requested} ({len(matches)} matches)"
            )
    return result, warnings


def owner_by_element(element_status: Any) -> dict[int, Any]:
    result: dict[int, Any] = {}
    for item in extract_records(element_status, ("element_status", "elements", "results")):
        element_id = first_int(item, ("element", "element_id", "id"))
        if element_id is not None:
            result[element_id] = item.get("owner")
    return result


def live_by_element(event_live: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in extract_records(event_live, ("elements", "element_live", "results")):
        element_id = first_int(item, ("id", "element", "element_id"))
        if element_id is not None:
            result[element_id] = item
    return result


def owner_from_entry_events(
    element_id: int,
    entry_events: dict[str, Any],
    by_entry: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve the historical GW owner by scanning every saved squad.

    This is preferred over current element-status because a player can change
    owner after a gameweek finishes but before the snapshot job runs.
    """
    for entry_key, entry_event in entry_events.items():
        if not isinstance(entry_event, dict):
            continue
        pick = find_pick(entry_event, element_id)
        if pick is None:
            continue
        entry_id = as_int(entry_key)
        owner = by_entry.get(entry_id) if entry_id is not None else None
        if owner is None:
            payload_entry = first_int(entry_event, ("entry", "entry_id", "id"))
            owner = by_entry.get(payload_entry or -1)
        return owner, pick
    return None, None


def lineup_status(position: int | None, multiplier: int | None) -> str:
    if position is None:
        return "not_in_squad_data"
    multiplier = multiplier if multiplier is not None else 0
    if position <= 11 and multiplier > 0:
        return "starter"
    if position > 11 and multiplier > 0:
        return "substituted_in"
    if position > 11 and multiplier == 0:
        return "bench"
    if position <= 11 and multiplier == 0:
        return "starter_not_counted"
    return "unknown"


def find_pick(entry_event: Any, element_id: int) -> dict[str, Any] | None:
    if not isinstance(entry_event, dict):
        return None
    for pick in entry_event.get("picks") or []:
        if isinstance(pick, dict) and first_int(
            pick, ("element", "element_id", "id")
        ) == element_id:
            return pick
    return None


def match_for_league_entry(
    details: dict[str, Any], gameweek: int, league_entry_id: int
) -> tuple[dict[str, Any] | None, int | None]:
    for match in details.get("matches") or []:
        if not isinstance(match, dict) or as_int(match.get("event")) != gameweek:
            continue
        side_1 = first_int(
            match,
            ("league_entry_1", "league_entry_1_id", "entry_1", "entry_1_id"),
        )
        side_2 = first_int(
            match,
            ("league_entry_2", "league_entry_2_id", "entry_2", "entry_2_id"),
        )
        if league_entry_id == side_1:
            return match, 1
        if league_entry_id == side_2:
            return match, 2
    return None, None


def h2h_context(
    details: dict[str, Any],
    gameweek: int,
    owner: dict[str, Any],
    counted_points: int | float | None,
) -> dict[str, Any] | None:
    league_entry_id = as_int(owner.get("id"))
    if league_entry_id is None:
        return None
    match, side = match_for_league_entry(details, gameweek, league_entry_id)
    if match is None or side is None:
        return None

    opponent_side = 2 if side == 1 else 1
    opponent_ref = first_int(
        match,
        (
            f"league_entry_{opponent_side}",
            f"league_entry_{opponent_side}_id",
            f"entry_{opponent_side}",
            f"entry_{opponent_side}_id",
        ),
    )
    by_league_entry, by_entry = entry_indexes(details)
    opponent = resolve_entry_reference(opponent_ref, by_league_entry, by_entry)
    owner_score = first_present(
        match,
        (
            f"league_entry_{side}_points",
            f"entry_{side}_points",
            f"score_{side}",
            f"points_{side}",
        ),
    )
    opponent_score = first_present(
        match,
        (
            f"league_entry_{opponent_side}_points",
            f"entry_{opponent_side}_points",
            f"score_{opponent_side}",
            f"points_{opponent_side}",
        ),
    )
    owner_score_num = as_int(owner_score)
    opponent_score_num = as_int(opponent_score)
    finished = bool(match.get("finished"))
    result: str | None = None
    margin: int | None = None
    if finished and owner_score_num is not None and opponent_score_num is not None:
        margin = abs(owner_score_num - opponent_score_num)
        if owner_score_num > opponent_score_num:
            result = "win"
        elif owner_score_num < opponent_score_num:
            result = "loss"
        else:
            result = "draw"

    points_exceeded_margin = None
    if margin is not None and isinstance(counted_points, (int, float)):
        points_exceeded_margin = counted_points > margin

    return {
        "match_id": match.get("id"),
        "finished": finished,
        "owner_score": owner_score,
        "opponent_league_entry_id": opponent.get("id") if opponent else opponent_ref,
        "opponent_entry_id": opponent.get("entry_id") if opponent else None,
        "opponent_entry_name": opponent.get("entry_name") if opponent else None,
        "opponent_score": opponent_score,
        "result": result,
        "margin": margin,
        "watched_player_points_counted": counted_points,
        "points_exceeded_final_margin": points_exceeded_margin,
        "interpretation_note": (
            "points_exceeded_final_margin is mathematical only and does not prove causality"
            if points_exceeded_margin is not None
            else None
        ),
    }


def player_fixture_context(
    player: dict[str, Any],
    pl_fixtures: Any,
    teams: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    club_id = as_int(player.get("club_id"))
    if club_id is None or not isinstance(pl_fixtures, list):
        return []
    result: list[dict[str, Any]] = []
    for fixture in pl_fixtures:
        if not isinstance(fixture, dict):
            continue
        home = as_int(fixture.get("team_h"))
        away = as_int(fixture.get("team_a"))
        if club_id not in {home, away}:
            continue
        is_home = club_id == home
        opponent_id = away if is_home else home
        opponent = teams.get(opponent_id or -1, {})
        result.append(
            {
                "fixture_id": fixture.get("id"),
                "home_or_away": "home" if is_home else "away",
                "opponent_club_id": opponent_id,
                "opponent_club_name": opponent.get("name"),
                "opponent_club_short_name": opponent.get("short_name"),
                "finished": fixture.get("finished"),
                "kickoff_time": fixture.get("kickoff_time"),
                "team_score": fixture.get("team_h_score")
                if is_home
                else fixture.get("team_a_score"),
                "opponent_score": fixture.get("team_a_score")
                if is_home
                else fixture.get("team_h_score"),
            }
        )
    return result


def build_watched_players(
    *,
    gameweek: int,
    watch_names: Iterable[str],
    bootstrap: dict[str, Any],
    details: dict[str, Any],
    element_status: Any,
    event_live: Any,
    entry_events: dict[str, Any],
    pl_fixtures: Any,
) -> dict[str, Any]:
    watched, warnings = resolve_watched_players(bootstrap, watch_names)
    owners = owner_by_element(element_status)
    live = live_by_element(event_live)
    players, teams, _ = bootstrap_indexes(bootstrap)
    by_league_entry, by_entry = entry_indexes(details)
    output_players: list[dict[str, Any]] = []

    if element_status is None:
        warnings.append("element-status data unavailable")
    if event_live is None:
        warnings.append("event-live data unavailable")
    if not entry_events:
        warnings.append("entry-event data unavailable")

    for configured in watched:
        element_id = int(configured["element_id"])
        owner_ref = owners.get(element_id)
        current_owner = resolve_entry_reference(
            owner_ref, by_league_entry, by_entry
        )
        historical_owner, pick = owner_from_entry_events(
            element_id, entry_events, by_entry
        )
        owner = historical_owner or current_owner
        owner_source = (
            "entry-events"
            if historical_owner is not None
            else "element-status"
            if current_owner is not None
            else None
        )

        live_item = live.get(element_id, {})
        stats = live_item.get("stats") if isinstance(live_item.get("stats"), dict) else {}
        selected_stats = {
            field: stats.get(field)
            for field in WATCH_STAT_FIELDS
            if field in stats
        }
        total_points = stats.get("total_points")
        total_points_num = as_int(total_points)

        if pick is None and owner is not None:
            entry_id = as_int(owner.get("entry_id"))
            if entry_id is not None:
                entry_event = entry_events.get(str(entry_id)) or entry_events.get(entry_id)
                pick = find_pick(entry_event, element_id)

        position = first_int(pick or {}, ("position", "pick_position"))
        multiplier = first_int(pick or {}, ("multiplier",))
        status = (
            "unowned"
            if owner is None
            else lineup_status(position, multiplier)
        )
        counted_points: int | None = None
        bench_points: int | None = None
        if total_points_num is not None and multiplier is not None:
            counted_points = total_points_num * multiplier
            if status == "bench":
                bench_points = total_points_num

        player = dict(configured)
        player.update(
            {
                "owner": {
                    "league_entry_id": owner.get("id") if owner else None,
                    "entry_id": owner.get("entry_id") if owner else None,
                    "entry_name": owner.get("entry_name") if owner else None,
                    "short_name": owner.get("short_name") if owner else None,
                }
                if owner is not None
                else None,
                "owner_source": owner_source,
                "current_owner": {
                    "league_entry_id": current_owner.get("id"),
                    "entry_id": current_owner.get("entry_id"),
                    "entry_name": current_owner.get("entry_name"),
                    "short_name": current_owner.get("short_name"),
                }
                if current_owner is not None
                else None,
                "squad_status": status,
                "squad_position": position,
                "multiplier": multiplier,
                "points_counted": counted_points,
                "bench_points": bench_points,
                "stats": selected_stats,
                "fixtures": player_fixture_context(configured, pl_fixtures, teams),
                "h2h": h2h_context(details, gameweek, owner, counted_points)
                if owner is not None
                else None,
                "raw_point_explain": live_item.get("explain")
                if isinstance(live_item, dict)
                else None,
            }
        )
        output_players.append(player)

    return {
        "schema_version": 1,
        "gameweek": gameweek,
        "generated_at": utc_now_iso(),
        "players": output_players,
        "data_quality": {
            "watched_players_requested": list(watch_names),
            "watched_players_resolved": len(output_players),
            "element_status_available": element_status is not None,
            "event_live_available": event_live is not None,
            "entry_events_available": bool(entry_events),
            "pl_fixtures_available": isinstance(pl_fixtures, list),
            "warnings": sorted(set(warnings)),
        },
    }


def draft_record(details: dict[str, Any]) -> dict[str, Any] | None:
    league = details.get("league") if isinstance(details.get("league"), dict) else {}
    start_event = as_int(league.get("start_event")) or 1
    drafts = league.get("drafts") or details.get("drafts") or []
    candidates = [item for item in drafts if isinstance(item, dict)]
    for item in candidates:
        if as_int(item.get("event")) == start_event:
            return item
    return candidates[0] if candidates else None


def draft_completion_state(
    details: dict[str, Any], owned_count: int, expected_picks: int
) -> tuple[bool, str | None, dict[str, Any] | None]:
    league = details.get("league") if isinstance(details.get("league"), dict) else {}
    status = str(league.get("draft_status") or "").casefold() or None
    record = draft_record(details)
    completed_at = record.get("draft_completed") if record else None
    complete_statuses = {"post", "complete", "completed", "drafted"}
    completed = bool(completed_at) or status in complete_statuses
    if expected_picks > 0 and owned_count >= expected_picks:
        completed = True
    return completed, status, record


def normalize_choice_records(
    choices: Any,
    details: dict[str, Any],
    bootstrap: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = extract_records(choices, ("choices", "picks", "results", "transactions"))
    by_league_entry, by_entry = entry_indexes(details)
    players, teams, _ = bootstrap_indexes(bootstrap)
    number_of_entries = len(by_league_entry)
    normalized: list[dict[str, Any]] = []
    explicit_order_count = 0
    unresolved: list[int] = []

    for source_index, raw in enumerate(records, start=1):
        element_id = first_int(raw, ("element", "element_id", "player", "player_id"))
        if element_id is None:
            unresolved.append(source_index)
            continue

        owner_ref = first_present(
            raw,
            (
                "league_entry",
                "league_entry_id",
                "leagueEntryId",
                "entry",
                "entry_id",
                "entryId",
                "owner",
            ),
        )
        owner = resolve_entry_reference(owner_ref, by_league_entry, by_entry)
        if owner is None:
            unresolved.append(source_index)
            continue

        explicit_pick = first_int(
            raw,
            (
                "overall_pick",
                "overallPick",
                "choice",
                "pick",
                "rank",
                "draft_pick",
                "draftPick",
            ),
        )
        if explicit_pick is not None:
            explicit_order_count += 1
        overall_pick = explicit_pick or source_index
        round_number = first_int(raw, ("round", "round_number", "roundNumber"))
        pick_in_round = first_int(
            raw, ("pick_in_round", "pickInRound", "round_pick", "roundPick")
        )
        if number_of_entries:
            round_number = round_number or ((overall_pick - 1) // number_of_entries + 1)
            pick_in_round = pick_in_round or ((overall_pick - 1) % number_of_entries + 1)

        player = enrich_player(element_id, players, teams)
        official_rank = as_int(player.get("official_draft_rank"))
        player.update(
            {
                "overall_pick": overall_pick,
                "round": round_number,
                "pick_in_round": pick_in_round,
                "league_entry_id": owner.get("id"),
                "entry_id": owner.get("entry_id"),
                "entry_name": owner.get("entry_name"),
                "draft_rank_delta": official_rank - overall_pick
                if official_rank is not None
                else None,
                "source_index": source_index,
            }
        )
        normalized.append(player)

    normalized.sort(key=lambda item: (item.get("overall_pick") or 10**9, item["element_id"]))
    unique_order = len({item.get("overall_pick") for item in normalized}) == len(normalized)
    order_available = bool(normalized) and unique_order
    order_source = None
    if order_available:
        order_source = (
            "explicit_choice_field"
            if explicit_order_count == len(normalized)
            else "choices_array_order"
        )

    return normalized, {
        "choices_available": choices is not None,
        "choice_records_received": len(records),
        "choice_records_resolved": len(normalized),
        "choice_records_unresolved_source_indexes": unresolved,
        "pick_order_available": order_available,
        "pick_order_source": order_source,
    }


def roster_picks_from_element_status(
    element_status: Any,
    details: dict[str, Any],
    bootstrap: dict[str, Any],
) -> list[dict[str, Any]]:
    by_league_entry, by_entry = entry_indexes(details)
    players, teams, _ = bootstrap_indexes(bootstrap)
    output: list[dict[str, Any]] = []
    for item in extract_records(element_status, ("element_status", "elements", "results")):
        element_id = first_int(item, ("element", "element_id", "id"))
        owner_ref = item.get("owner")
        if element_id is None or owner_ref is None:
            continue
        owner = resolve_entry_reference(owner_ref, by_league_entry, by_entry)
        if owner is None:
            continue
        player = enrich_player(element_id, players, teams)
        player.update(
            {
                "overall_pick": None,
                "round": None,
                "pick_in_round": None,
                "league_entry_id": owner.get("id"),
                "entry_id": owner.get("entry_id"),
                "entry_name": owner.get("entry_name"),
                "draft_rank_delta": None,
                "source_index": None,
            }
        )
        output.append(player)
    return sorted(
        output,
        key=lambda item: (
            str(item.get("entry_name") or ""),
            item.get("position_id") or 99,
            str(item.get("web_name") or ""),
        ),
    )


def normalize_transaction_type(raw_kind: Any) -> str | None:
    return TRANSACTION_KIND_LABELS.get(normalize_text(raw_kind))


def normalize_transaction_result(raw_result: Any) -> str | None:
    return TRANSACTION_RESULT_LABELS.get(normalize_text(raw_result))


def enrich_transactions(
    transactions: Any,
    details: dict[str, Any],
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    records = extract_records(transactions, ("transactions", "results", "items"))
    by_league_entry, by_entry = entry_indexes(details)
    players, teams, _ = bootstrap_indexes(bootstrap)
    output: list[dict[str, Any]] = []

    for raw in records:
        owner_ref = first_present(
            raw,
            ("league_entry", "league_entry_id", "entry", "entry_id", "owner"),
        )
        owner = resolve_entry_reference(owner_ref, by_league_entry, by_entry)
        element_in = first_int(
            raw, ("element_in", "elementIn", "in", "player_in", "playerIn")
        )
        element_out = first_int(
            raw, ("element_out", "elementOut", "out", "player_out", "playerOut")
        )
        raw_kind = first_present(raw, ("kind", "type", "transaction_type"))
        raw_result = first_present(raw, ("result", "status", "transaction_result"))
        output.append(
            {
                "transaction_id": first_present(raw, ("id", "transaction_id")),
                "event": first_int(raw, ("event", "gameweek", "gw")),
                "timestamp": first_present(
                    raw,
                    ("created", "created_at", "timestamp", "time", "processed_at"),
                ),
                "priority": first_int(raw, ("index", "priority", "waiver_pick")),
                "raw_kind": raw_kind,
                "transaction_type": normalize_transaction_type(raw_kind),
                "raw_result": raw_result,
                "result": normalize_transaction_result(raw_result),
                "league_entry_id": owner.get("id") if owner else None,
                "entry_id": owner.get("entry_id") if owner else None,
                "entry_name": owner.get("entry_name") if owner else None,
                "element_in": enrich_player(element_in, players, teams)
                if element_in is not None
                else None,
                "element_out": enrich_player(element_out, players, teams)
                if element_out is not None
                else None,
                "raw": raw,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "transactions": output,
        "data_quality": {
            "source_available": transactions is not None,
            "records_received": len(records),
            "records_enriched": len(output),
            "typed_records": sum(
                1 for item in output if item.get("transaction_type") is not None
            ),
            "note": (
                "Only records with an explicit recognized kind are labelled waiver, "
                "free_agent, trade or draft."
            ),
        },
    }


def group_draft_teams(
    details: dict[str, Any], picks: list[dict[str, Any]], draft_order: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for pick in picks:
        league_entry_id = as_int(pick.get("league_entry_id"))
        if league_entry_id is not None:
            by_team[league_entry_id].append(pick)

    draft_slot_by_team = {
        as_int(item.get("league_entry_id")): item.get("draft_slot")
        for item in draft_order
        if as_int(item.get("league_entry_id")) is not None
    }
    teams_output: list[dict[str, Any]] = []
    for entry in details.get("league_entries") or []:
        if not isinstance(entry, dict):
            continue
        league_entry_id = as_int(entry.get("id"))
        if league_entry_id is None:
            continue
        team_picks = sorted(
            by_team.get(league_entry_id, []),
            key=lambda item: (
                item.get("overall_pick") is None,
                item.get("overall_pick") or 10**9,
                item.get("position_id") or 99,
            ),
        )
        squad = {label: [] for label in POSITION_LABELS.values()}
        for pick in team_picks:
            label = pick.get("position")
            if label in squad:
                squad[label].append(pick)
        deltas = [
            item["draft_rank_delta"]
            for item in team_picks
            if isinstance(item.get("draft_rank_delta"), int)
        ]
        teams_output.append(
            {
                "league_entry_id": league_entry_id,
                "entry_id": entry.get("entry_id"),
                "entry_name": entry.get("entry_name"),
                "short_name": entry.get("short_name"),
                "draft_slot": draft_slot_by_team.get(league_entry_id),
                "first_pick": team_picks[0] if team_picks else None,
                "picks": team_picks,
                "squad": squad,
                "position_counts": {
                    label: len(players) for label, players in squad.items()
                },
                "squad_size": len(team_picks),
                "best_draft_rank_value": max(deltas) if deltas else None,
                "biggest_draft_rank_reach": min(deltas) if deltas else None,
            }
        )
    return sorted(
        teams_output,
        key=lambda item: (
            item.get("draft_slot") is None,
            item.get("draft_slot") or 10**9,
            str(item.get("entry_name") or ""),
        ),
    )


def derive_draft_order(
    picks: list[dict[str, Any]], number_of_entries: int
) -> list[dict[str, Any]]:
    if not picks or number_of_entries <= 0:
        return []
    first_round = [
        item
        for item in picks
        if as_int(item.get("round")) == 1
        or (
            as_int(item.get("overall_pick")) is not None
            and int(item["overall_pick"]) <= number_of_entries
        )
    ]
    first_round.sort(key=lambda item: item.get("overall_pick") or 10**9)
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for item in first_round:
        league_entry_id = as_int(item.get("league_entry_id"))
        if league_entry_id is None or league_entry_id in seen:
            continue
        result.append(
            {
                "draft_slot": len(result) + 1,
                "league_entry_id": league_entry_id,
                "entry_id": item.get("entry_id"),
                "entry_name": item.get("entry_name"),
            }
        )
        seen.add(league_entry_id)
    return result if len(result) == number_of_entries else []


def draft_insights(picks: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = [item for item in picks if as_int(item.get("overall_pick")) is not None]
    first_by_position: dict[str, Any] = {}
    for label in POSITION_LABELS.values():
        position_picks = [item for item in ordered if item.get("position") == label]
        first_by_position[label] = (
            min(position_picks, key=lambda item: item["overall_pick"])
            if position_picks
            else None
        )

    with_delta = [
        item for item in ordered if isinstance(item.get("draft_rank_delta"), int)
    ]
    return {
        "first_player_by_position": first_by_position,
        "largest_positive_draft_rank_deltas": sorted(
            with_delta,
            key=lambda item: item["draft_rank_delta"],
            reverse=True,
        )[:10],
        "largest_negative_draft_rank_deltas": sorted(
            with_delta,
            key=lambda item: item["draft_rank_delta"],
        )[:10],
        "draft_rank_note": (
            "Positive delta means a player was selected later than the official FPL "
            "Draft Rank; negative means earlier. This is not an objective grade."
        ),
    }


def build_draft_recap(
    *,
    league_id: int,
    details: dict[str, Any],
    bootstrap: dict[str, Any],
    element_status: Any,
    choices: Any,
    transactions: Any,
    watch_names: Iterable[str],
) -> dict[str, Any]:
    entries = [
        item for item in details.get("league_entries") or [] if isinstance(item, dict)
    ]
    expected_picks = len(entries) * EXPECTED_SQUAD_SIZE
    choices_picks, choices_quality = normalize_choice_records(
        choices, details, bootstrap
    )
    owner_picks = roster_picks_from_element_status(
        element_status, details, bootstrap
    )

    picks = choices_picks if choices_picks else owner_picks
    source = "choices" if choices_picks else "element-status"
    owned_count = len(owner_picks)
    completed, status, record = draft_completion_state(
        details, owned_count, expected_picks
    )
    draft_order = derive_draft_order(picks, len(entries)) if choices_picks else []
    teams = group_draft_teams(details, picks, draft_order)
    complete_rosters = (
        bool(entries)
        and len(teams) == len(entries)
        and all(team.get("squad_size") == EXPECTED_SQUAD_SIZE for team in teams)
    )
    recap_ready = completed and complete_rosters

    watched, watch_warnings = resolve_watched_players(bootstrap, watch_names)
    watched_output: list[dict[str, Any]] = []
    for watched_player in watched:
        element_id = watched_player["element_id"]
        selected = next(
            (item for item in picks if item.get("element_id") == element_id), None
        )
        item = dict(watched_player)
        item.update(
            {
                "drafted": selected is not None,
                "overall_pick": selected.get("overall_pick") if selected else None,
                "round": selected.get("round") if selected else None,
                "league_entry_id": selected.get("league_entry_id") if selected else None,
                "entry_id": selected.get("entry_id") if selected else None,
                "entry_name": selected.get("entry_name") if selected else None,
            }
        )
        watched_output.append(item)

    fingerprint_payload = [
        {
            "element_id": item.get("element_id"),
            "league_entry_id": item.get("league_entry_id"),
            "overall_pick": item.get("overall_pick"),
        }
        for item in picks
    ]
    fingerprint = stable_hash(fingerprint_payload) if recap_ready else None
    enriched_transactions = enrich_transactions(transactions, details, bootstrap)

    warnings = list(watch_warnings)
    if choices is None:
        warnings.append(
            "Draft choices endpoint unavailable; squads are reconstructed from element-status and true pick order is omitted."
        )
    if completed and not complete_rosters:
        warnings.append(
            f"Draft appears complete, but only {len(picks)} of {expected_picks} squad slots were resolved."
        )

    return {
        "schema_version": 1,
        "league_id": league_id,
        "league_name": league_name(details),
        "generated_at": utc_now_iso(),
        "draft": {
            "id": record.get("id") if record else None,
            "event": record.get("event") if record else None,
            "scheduled_at": record.get("draft_dt") if record else None,
            "started": record.get("draft_started") if record else None,
            "completed_at": record.get("draft_completed") if record else None,
            "status": status,
            "is_complete": completed,
        },
        "recap_ready": recap_ready,
        "draft_fingerprint": fingerprint,
        "draft_order": draft_order,
        "picks": picks,
        "teams": teams,
        "watched_players": watched_output,
        "insights": draft_insights(picks),
        "transactions_at_generation": enriched_transactions,
        "data_quality": {
            **choices_quality,
            "squad_source": source,
            "element_status_available": element_status is not None,
            "league_transactions_available": transactions is not None,
            "expected_picks": expected_picks,
            "resolved_picks": len(picks),
            "owned_players_in_element_status": owned_count,
            "complete_rosters": complete_rosters,
            "warnings": sorted(set(warnings)),
        },
    }


def save_draft_snapshot(
    *,
    draft_dir: Path,
    recap: dict[str, Any],
    details: dict[str, Any],
    bootstrap: dict[str, Any],
    element_status: Any,
    choices: Any,
    transactions: Any,
    trades: Any,
) -> bool:
    """Write the initial-draft snapshot once, only after it is recap-ready."""
    if not recap.get("recap_ready"):
        return False
    recap_path = draft_dir / "draft-recap.json"
    if recap_path.exists():
        return True
    draft_dir.mkdir(parents=True, exist_ok=True)
    write_json(recap_path, recap)
    write_json(draft_dir / "league-details.json", details)
    write_json(draft_dir / "bootstrap-compact.json", bootstrap)
    if element_status is not None:
        write_json(draft_dir / "element-status.json", element_status)
    if choices is not None:
        write_json(draft_dir / "choices.json", choices)
    if transactions is not None:
        write_json(draft_dir / "transactions.json", transactions)
    if trades is not None:
        write_json(draft_dir / "trades.json", trades)
    return True


def save_gameweek_snapshot(
    *,
    gw_dir: Path,
    summary: dict[str, Any],
    details: dict[str, Any],
    round_context: dict[str, Any],
    bootstrap: dict[str, Any],
    pl_fixtures: Any,
    element_status: Any,
    trades: Any,
    choices: Any,
    transactions: Any,
    transactions_enriched: dict[str, Any],
    event_live: Any,
    entry_events: dict[str, Any],
    watched_players: dict[str, Any] | None,
) -> None:
    """Create immutable raw GW inputs and safely backfill new derived files."""
    is_new = not gw_dir.exists()
    gw_dir.mkdir(parents=True, exist_ok=True)
    if is_new:
        write_json(gw_dir / "summary.json", summary)
        write_json(gw_dir / "league-details.json", details)
        write_json(gw_dir / "round-context.json", round_context)
        write_json(gw_dir / "bootstrap-compact.json", bootstrap)
        if pl_fixtures is not None:
            write_json(gw_dir / "pl-fixtures.json", pl_fixtures)
        if element_status is not None:
            write_json(gw_dir / "element-status.json", element_status)
        if trades is not None:
            write_json(gw_dir / "trades.json", trades)
        if choices is not None:
            write_json(gw_dir / "choices.json", choices)
        if transactions is not None:
            write_json(gw_dir / "transactions.json", transactions)
        if event_live is not None:
            write_json(gw_dir / "event-live.json", event_live)
        if entry_events:
            write_json(gw_dir / "entry-events.json", entry_events)

    # These files did not exist in schema v3. Backfill only when missing.
    if not (gw_dir / "bootstrap-compact.json").exists():
        write_json(gw_dir / "bootstrap-compact.json", bootstrap)
    if not (gw_dir / "transactions-enriched.json").exists():
        write_json(gw_dir / "transactions-enriched.json", transactions_enriched)
    if watched_players is not None and not (gw_dir / "watched-players.json").exists():
        write_json(gw_dir / "watched-players.json", watched_players)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument(
        "--watch-player",
        action="append",
        dest="watch_players",
        help=(
            "Player web name/full name to include in watched-players.json. "
            "May be repeated. Defaults to Wirtz."
        ),
    )
    args = parser.parse_args()

    league_id = args.league_id
    watch_players = tuple(args.watch_players or DEFAULT_WATCH_PLAYERS)
    data_dir = Path(args.data_dir)
    current_dir = data_dir / "current"
    history_dir = data_dir / "history"
    initial_draft_dir = data_dir / "draft" / "initial"
    current_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    endpoint_status: dict[str, Any] = {}

    draft_bootstrap, status = fetch_json(
        DRAFT_BASE_URL, "/bootstrap-static", required=True
    )
    endpoint_status["bootstrap_static"] = status
    assert isinstance(draft_bootstrap, dict)
    bootstrap = compact_bootstrap(draft_bootstrap)
    write_json(current_dir / "bootstrap-compact.json", bootstrap)

    fpl_calendar_raw, status = fetch_json(
        FPL_BASE_URL, "/bootstrap-static/", required=True
    )
    endpoint_status["fpl_bootstrap_static"] = status
    assert isinstance(fpl_calendar_raw, dict)
    fpl_calendar_compact = compact_bootstrap(fpl_calendar_raw)
    fpl_calendar = {
        "events": fpl_calendar_compact.get("events", []),
        "teams": fpl_calendar_compact.get("teams", []),
    }
    write_json(current_dir / "fpl-calendar.json", fpl_calendar)

    details, status = fetch_json(
        DRAFT_BASE_URL, f"/league/{league_id}/details", required=True
    )
    endpoint_status["league_details"] = status
    assert isinstance(details, dict)
    write_json(current_dir / "league-details.json", details)

    optional_paths = {
        "bootstrap_dynamic": "/bootstrap-dynamic",
        "game": "/game",
        "element_status": f"/league/{league_id}/element-status",
        "trades": f"/draft/league/{league_id}/trades",
        # Correct public endpoint for the initial snake-draft choices.
        "choices": f"/draft/{league_id}/choices",
        # League-wide endpoint includes draft/waiver/free-agent transactions.
        "transactions": f"/draft/league/{league_id}/transactions",
    }
    optional_data: dict[str, Any] = {}
    for key, path in optional_paths.items():
        payload, status = fetch_json(DRAFT_BASE_URL, path)
        endpoint_status[key] = status
        optional_data[key] = payload
        if payload is not None:
            write_json(current_dir / f"{key.replace('_', '-')}.json", payload)

    entries = [
        item for item in details.get("league_entries") or [] if isinstance(item, dict)
    ]
    entry_public: dict[str, Any] = {}
    for entry in entries:
        entry_id = as_int(entry.get("entry_id"))
        if entry_id is None:
            continue
        payload, status = fetch_json(DRAFT_BASE_URL, f"/entry/{entry_id}/public")
        endpoint_status[f"entry_{entry_id}_public"] = status
        if payload is not None:
            entry_public[str(entry_id)] = payload
    if entry_public:
        write_json(current_dir / "entries-public.json", entry_public)

    transactions_enriched = enrich_transactions(
        optional_data.get("transactions"), details, bootstrap
    )
    write_json(current_dir / "transactions-enriched.json", transactions_enriched)

    candidate_draft_recap = build_draft_recap(
        league_id=league_id,
        details=details,
        bootstrap=bootstrap,
        element_status=optional_data.get("element_status"),
        choices=optional_data.get("choices"),
        transactions=optional_data.get("transactions"),
        watch_names=watch_players,
    )
    frozen_draft_recap = read_json(initial_draft_dir / "draft-recap.json")
    if isinstance(frozen_draft_recap, dict) and frozen_draft_recap.get("recap_ready"):
        # Keep the initial draft stable even after waivers or a mid-season redraft.
        draft_recap = frozen_draft_recap
        draft_snapshot_exists = True
    else:
        draft_recap = candidate_draft_recap
        draft_snapshot_exists = save_draft_snapshot(
            draft_dir=initial_draft_dir,
            recap=draft_recap,
            details=details,
            bootstrap=bootstrap,
            element_status=optional_data.get("element_status"),
            choices=optional_data.get("choices"),
            transactions=optional_data.get("transactions"),
            trades=optional_data.get("trades"),
        )
    write_json(current_dir / "draft-recap.json", draft_recap)

    ids = gameweek_ids(fpl_calendar, details)
    fixture_events = sorted({gw for gw in ids.values() if isinstance(gw, int)})
    pl_fixtures: dict[int, Any] = {}
    for gw in fixture_events:
        payload, status = fetch_json(FPL_BASE_URL, f"/fixtures/?event={gw}")
        endpoint_status[f"pl_fixtures_gw_{gw}"] = status
        if payload is not None:
            pl_fixtures[gw] = payload
            write_json(current_dir / f"pl-fixtures-gw-{gw:02d}.json", payload)

    round_context = build_round_context(fpl_calendar, details, pl_fixtures)
    write_json(current_dir / "round-context.json", round_context)

    latest_gw = ids["latest_complete"]
    entry_events: dict[str, Any] = {}
    live_payload: Any = None
    watched_payload: dict[str, Any] | None = None
    if latest_gw is not None:
        live_payload, status = fetch_json(DRAFT_BASE_URL, f"/event/{latest_gw}/live")
        endpoint_status[f"event_{latest_gw}_live"] = status
        if live_payload is not None:
            write_json(current_dir / "latest-event-live.json", live_payload)

        for entry in entries:
            entry_id = as_int(entry.get("entry_id"))
            if entry_id is None:
                continue
            payload, status = fetch_json(
                DRAFT_BASE_URL, f"/entry/{entry_id}/event/{latest_gw}"
            )
            endpoint_status[f"entry_{entry_id}_event_{latest_gw}"] = status
            if payload is not None:
                entry_events[str(entry_id)] = payload
        if entry_events:
            write_json(current_dir / "latest-entry-events.json", entry_events)

        watched_payload = build_watched_players(
            gameweek=latest_gw,
            watch_names=watch_players,
            bootstrap=bootstrap,
            details=details,
            element_status=optional_data.get("element_status"),
            event_live=live_payload,
            entry_events=entry_events,
            pl_fixtures=pl_fixtures.get(latest_gw, []),
        )
        write_json(current_dir / "watched-players.json", watched_payload)

    summary = {
        "schema_version": 4,
        "generated_at": utc_now_iso(),
        "league_id": league_id,
        "league_name": league_name(details),
        "number_of_entries": len(entries),
        "entries": [entry_summary(entry) for entry in entries],
        "latest_complete_gameweek": latest_gw,
        "previous_gameweek": ids["previous"],
        "current_gameweek": ids["current"],
        "next_gameweek": ids["next"],
        "upcoming_gameweek": ids["upcoming"],
        "next_deadline": round_context.get("next_deadline"),
        "draft": {
            "status": draft_recap.get("draft", {}).get("status"),
            "draft_id": draft_recap.get("draft", {}).get("id"),
            "completed_at": draft_recap.get("draft", {}).get("completed_at"),
            "recap_ready": draft_recap.get("recap_ready"),
            "recap_fingerprint": draft_recap.get("draft_fingerprint"),
            "pick_order_available": draft_recap.get("data_quality", {}).get(
                "pick_order_available"
            ),
            "resolved_picks": draft_recap.get("data_quality", {}).get(
                "resolved_picks"
            ),
            "current_recap_path": "data/current/draft-recap.json",
            "snapshot_recap_path": (
                "data/draft/initial/draft-recap.json"
                if draft_snapshot_exists
                else None
            ),
        },
        "watched_players": {
            "configured": list(watch_players),
            "latest_gameweek": latest_gw,
            "current_path": (
                "data/current/watched-players.json"
                if watched_payload is not None
                else None
            ),
        },
        "endpoint_status": endpoint_status,
    }
    write_json(data_dir / "summary.json", summary)

    if latest_gw is not None:
        gw_dir = history_dir / f"gw-{latest_gw:02d}"
        save_gameweek_snapshot(
            gw_dir=gw_dir,
            summary=summary,
            details=details,
            round_context=round_context,
            bootstrap=bootstrap,
            pl_fixtures=pl_fixtures.get(latest_gw),
            element_status=optional_data.get("element_status"),
            trades=optional_data.get("trades"),
            choices=optional_data.get("choices"),
            transactions=optional_data.get("transactions"),
            transactions_enriched=transactions_enriched,
            event_live=live_payload,
            entry_events=entry_events,
            watched_players=watched_payload,
        )

    print(
        f"League {league_id}: {len(entries)} entries; "
        f"draft recap ready={draft_recap.get('recap_ready')}; "
        f"latest completed GW={latest_gw if latest_gw is not None else 'none'}; "
        f"watched={','.join(watch_players)}; "
        f"next deadline={summary['next_deadline']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
