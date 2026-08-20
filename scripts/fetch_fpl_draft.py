#!/usr/bin/env python3
"""Fetch public FPL Draft data for league analysis and gameweek previews.

Designed for GitHub Actions. No login, password, cookie or API key is required.
The script stores:
- league state and standings
- Draft H2H matchups for previous/current/next gameweek
- Premier League fixtures/results for previous/current/next gameweek
- gameweek deadlines
- live player points and entry event data for the latest completed Draft gameweek
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(val) for key, val in value.items() if key not in PRIVATE_KEYS}
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
    url = f"{base_url}{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://draft.premierleague.com/",
        "Cache-Control": "no-cache",
    }

    last_error = None
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
                time.sleep(min(2 ** attempt, 10))
                continue
            break
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2 ** attempt, 10))

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


def compact_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    player_fields = (
        "id", "web_name", "team", "element_type", "status", "news",
        "total_points", "minutes",
    )
    team_fields = ("id", "name", "short_name")
    event_fields = (
        "id", "name", "deadline_time", "deadline_time_epoch",
        "finished", "data_checked", "is_previous", "is_current", "is_next",
    )
    type_fields = ("id", "singular_name", "singular_name_short", "plural_name")

    return {
        "elements": [
            {key: item.get(key) for key in player_fields if key in item}
            for item in payload.get("elements", [])
        ],
        "teams": [
            {key: item.get(key) for key in team_fields if key in item}
            for item in payload.get("teams", [])
        ],
        "events": [
            {key: item.get(key) for key in event_fields if key in item}
            for item in payload.get("events", [])
        ],
        "element_types": [
            {key: item.get(key) for key in type_fields if key in item}
            for item in payload.get("element_types", [])
        ],
    }


def latest_complete_gameweek(details: dict[str, Any]) -> int | None:
    matches = details.get("matches") or []
    by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        event = match.get("event")
        if isinstance(event, int):
            by_event[event].append(match)

    completed = []
    for event, event_matches in by_event.items():
        if event_matches and all(bool(match.get("finished")) for match in event_matches):
            completed.append(event)
    return max(completed) if completed else None


def league_name(details: dict[str, Any]) -> str | None:
    league = details.get("league")
    if isinstance(league, dict):
        return league.get("name")
    return details.get("name")


def entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "entry_id", "entry_name", "short_name")
    return {key: entry.get(key) for key in keep if key in entry}


def event_map(bootstrap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        event["id"]: event
        for event in bootstrap.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("id"), int)
    }


def find_event_id(events: dict[int, dict[str, Any]], flag: str) -> int | None:
    for event_id, event in events.items():
        if event.get(flag) is True:
            return event_id
    return None


def gameweek_ids(bootstrap: dict[str, Any], details: dict[str, Any]) -> dict[str, int | None]:
    events = event_map(bootstrap)
    completed = latest_complete_gameweek(details)
    previous = find_event_id(events, "is_previous") or completed
    current = find_event_id(events, "is_current")
    nxt = find_event_id(events, "is_next")

    # Before GW1, FPL sometimes exposes only is_next. After a GW is data-checked,
    # is_current can advance while Draft H2H completion follows shortly after.
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




def upcoming_event_id(bootstrap: dict[str, Any], now: datetime | None = None) -> int | None:
    """Return the gameweek with the earliest deadline still in the future."""
    now = now or datetime.now(timezone.utc)
    candidates: list[tuple[datetime, int]] = []
    for event in bootstrap.get("events", []):
        if not isinstance(event, dict) or not isinstance(event.get("id"), int):
            continue
        raw = event.get("deadline_time")
        if not isinstance(raw, str):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt > now:
            candidates.append((dt, event["id"]))
    return min(candidates)[1] if candidates else None

def deadline_block(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    raw = event.get("deadline_time")
    result = {
        "gameweek": event.get("id"),
        "name": event.get("name"),
        "deadline_time_utc": raw,
    }
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            result["deadline_time_copenhagen"] = dt.astimezone(
                ZoneInfo("Europe/Copenhagen")
            ).isoformat()
        except ValueError:
            pass
    return result


def draft_matches_for_event(details: dict[str, Any], event_id: int | None) -> list[dict[str, Any]]:
    if event_id is None:
        return []
    return [
        match for match in (details.get("matches") or [])
        if match.get("event") == event_id
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

    return {
        "gameweeks": ids,
        "next_deadline": deadline_block(events.get(ids["upcoming"])) if ids["upcoming"] else None,
        "rounds": rounds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    league_id = args.league_id
    data_dir = Path(args.data_dir)
    current_dir = data_dir / "current"
    history_dir = data_dir / "history"
    current_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    endpoint_status: dict[str, Any] = {}

    bootstrap, status = fetch_json(DRAFT_BASE_URL, "/bootstrap-static", required=True)
    endpoint_status["bootstrap_static"] = status
    assert isinstance(bootstrap, dict)
    write_json(current_dir / "bootstrap-compact.json", compact_bootstrap(bootstrap))

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
        "choices": f"/draft/league/{league_id}/choices",
    }
    optional_data: dict[str, Any] = {}
    for key, path in optional_paths.items():
        payload, status = fetch_json(DRAFT_BASE_URL, path)
        endpoint_status[key] = status
        optional_data[key] = payload
        if payload is not None:
            write_json(current_dir / f"{key.replace('_', '-')}.json", payload)

    entries = details.get("league_entries") or []
    entry_public: dict[str, Any] = {}
    transactions: dict[str, Any] = {}

    for entry in entries:
        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, int):
            continue

        payload, status = fetch_json(DRAFT_BASE_URL, f"/entry/{entry_id}/public")
        endpoint_status[f"entry_{entry_id}_public"] = status
        if payload is not None:
            entry_public[str(entry_id)] = payload

        payload, status = fetch_json(
            DRAFT_BASE_URL, f"/draft/entry/{entry_id}/transactions"
        )
        endpoint_status[f"entry_{entry_id}_transactions"] = status
        if payload is not None:
            transactions[str(entry_id)] = payload

    if entry_public:
        write_json(current_dir / "entries-public.json", entry_public)
    if transactions:
        write_json(current_dir / "transactions.json", transactions)

    # Pull PL fixture lists for the adjacent rounds. This gives the recap actual
    # PL results and the preview kickoff schedule/opponents.
    ids = gameweek_ids(bootstrap, details)
    fixture_events = sorted({gw for gw in ids.values() if isinstance(gw, int)})
    pl_fixtures: dict[int, Any] = {}
    for gw in fixture_events:
        payload, status = fetch_json(FPL_BASE_URL, f"/fixtures/?event={gw}")
        endpoint_status[f"pl_fixtures_gw_{gw}"] = status
        if payload is not None:
            pl_fixtures[gw] = payload
            write_json(current_dir / f"pl-fixtures-gw-{gw:02d}.json", payload)

    round_context = build_round_context(bootstrap, details, pl_fixtures)
    write_json(current_dir / "round-context.json", round_context)

    latest_gw = ids["latest_complete"]
    entry_events: dict[str, Any] = {}
    live_payload = None

    if latest_gw is not None:
        live_payload, status = fetch_json(DRAFT_BASE_URL, f"/event/{latest_gw}/live")
        endpoint_status[f"event_{latest_gw}_live"] = status
        if live_payload is not None:
            write_json(current_dir / "latest-event-live.json", live_payload)

        for entry in entries:
            entry_id = entry.get("entry_id")
            if not isinstance(entry_id, int):
                continue
            payload, status = fetch_json(
                DRAFT_BASE_URL, f"/entry/{entry_id}/event/{latest_gw}"
            )
            endpoint_status[f"entry_{entry_id}_event_{latest_gw}"] = status
            if payload is not None:
                entry_events[str(entry_id)] = payload

        if entry_events:
            write_json(current_dir / "latest-entry-events.json", entry_events)

    summary = {
        "schema_version": 2,
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
        "endpoint_status": endpoint_status,
    }
    write_json(data_dir / "summary.json", summary)

    # Completed GW snapshots are written once. They preserve the recap inputs.
    if latest_gw is not None:
        gw_dir = history_dir / f"gw-{latest_gw:02d}"
        if not gw_dir.exists():
            gw_dir.mkdir(parents=True)
            write_json(gw_dir / "summary.json", summary)
            write_json(gw_dir / "league-details.json", details)
            write_json(gw_dir / "round-context.json", round_context)
            if latest_gw in pl_fixtures:
                write_json(gw_dir / "pl-fixtures.json", pl_fixtures[latest_gw])
            if optional_data.get("element_status") is not None:
                write_json(gw_dir / "element-status.json", optional_data["element_status"])
            if optional_data.get("trades") is not None:
                write_json(gw_dir / "trades.json", optional_data["trades"])
            if optional_data.get("choices") is not None:
                write_json(gw_dir / "choices.json", optional_data["choices"])
            if transactions:
                write_json(gw_dir / "transactions.json", transactions)
            if live_payload is not None:
                write_json(gw_dir / "event-live.json", live_payload)
            if entry_events:
                write_json(gw_dir / "entry-events.json", entry_events)

    print(
        f"League {league_id}: {len(entries)} entries; "
        f"latest completed GW={latest_gw if latest_gw is not None else 'none'}; "
        f"next deadline={summary['next_deadline']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
