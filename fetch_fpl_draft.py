#!/usr/bin/env python3
"""Fetch public FPL Draft data and persist a compact, public-safe snapshot.

Designed for GitHub Actions. No login, password, cookie or API key is required.
Endpoints that are unavailable before/after the draft are treated as optional.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://draft.premierleague.com/api"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)

# Manager personal-name fields are removed before anything is committed to a
# public repository. Team names / entry names are intentionally retained.
PRIVATE_KEYS = {
    "player_first_name",
    "player_last_name",
    "player_email",
    "email",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize(val)
            for key, val in value.items()
            if key not in PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def fetch_json(path: str, *, required: bool = False, attempts: int = 4) -> tuple[Any | None, dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://draft.premierleague.com/",
        "Origin": "https://draft.premierleague.com",
        "Cache-Control": "no-cache",
    }

    last_error = None
    for attempt in range(1, attempts + 1):
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw)
                return payload, {"ok": True, "status": response.status, "path": path}
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            # 404/401/403 are usually endpoint state/auth issues, not transient.
            if exc.code in {401, 403, 404}:
                break
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(min(2 ** attempt, 10))
                continue
            break
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2 ** attempt, 10))

    status = {"ok": False, "error": last_error or "unknown error", "path": path}
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
        "id",
        "web_name",
        "team",
        "element_type",
        "status",
        "news",
        "total_points",
        "minutes",
    )
    team_fields = ("id", "name", "short_name")
    event_fields = ("id", "name", "deadline_time", "finished", "is_current", "is_next")
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
    keep = (
        "id",          # league-entry id
        "entry_id",    # team id used by entry/transaction endpoints
        "entry_name",  # fantasy team name
        "short_name",
    )
    return {key: entry.get(key) for key in keep if key in entry}


def endpoint_slug(path: str) -> str:
    return path.strip("/").replace("/", "_") or "root"


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

    bootstrap, status = fetch_json("/bootstrap-static", required=True)
    endpoint_status["bootstrap_static"] = status
    assert isinstance(bootstrap, dict)
    write_json(current_dir / "bootstrap-compact.json", compact_bootstrap(bootstrap))

    details, status = fetch_json(f"/league/{league_id}/details", required=True)
    endpoint_status["league_details"] = status
    assert isinstance(details, dict)
    write_json(current_dir / "league-details.json", details)

    optional_paths = {
        "bootstrap_dynamic": "/bootstrap-dynamic",
        "game": "/game",
        "element_status": f"/league/{league_id}/element-status",
        "trades": f"/draft/league/{league_id}/trades",
        "choices": f"/draft/league/{league_id}/choices",
        "pl_event_status": "/pl/event-status",
    }
    optional_data: dict[str, Any] = {}
    for key, path in optional_paths.items():
        payload, status = fetch_json(path)
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

        payload, status = fetch_json(f"/entry/{entry_id}/public")
        endpoint_status[f"entry_{entry_id}_public"] = status
        if payload is not None:
            entry_public[str(entry_id)] = payload

        payload, status = fetch_json(f"/draft/entry/{entry_id}/transactions")
        endpoint_status[f"entry_{entry_id}_transactions"] = status
        if payload is not None:
            transactions[str(entry_id)] = payload

    if entry_public:
        write_json(current_dir / "entries-public.json", entry_public)
    if transactions:
        write_json(current_dir / "transactions.json", transactions)

    latest_gw = latest_complete_gameweek(details)
    entry_events: dict[str, Any] = {}
    live_payload = None

    if latest_gw is not None:
        live_payload, status = fetch_json(f"/event/{latest_gw}/live")
        endpoint_status[f"event_{latest_gw}_live"] = status
        if live_payload is not None:
            write_json(current_dir / "latest-event-live.json", live_payload)

        for entry in entries:
            entry_id = entry.get("entry_id")
            if not isinstance(entry_id, int):
                continue
            payload, status = fetch_json(f"/entry/{entry_id}/event/{latest_gw}")
            endpoint_status[f"entry_{entry_id}_event_{latest_gw}"] = status
            if payload is not None:
                entry_events[str(entry_id)] = payload

        if entry_events:
            write_json(current_dir / "latest-entry-events.json", entry_events)

    summary = {
        "schema_version": 1,
        "league_id": league_id,
        "league_name": league_name(details),
        "number_of_entries": len(entries),
        "entries": [entry_summary(entry) for entry in entries],
        "latest_complete_gameweek": latest_gw,
        "endpoint_status": endpoint_status,
    }
    write_json(data_dir / "summary.json", summary)

    # A completed-GW snapshot is immutable after first creation. This makes it
    # easy for a recap bot to compare weeks without keeping noisy 3-hour dumps.
    if latest_gw is not None:
        gw_dir = history_dir / f"gw-{latest_gw:02d}"
        if not gw_dir.exists():
            gw_dir.mkdir(parents=True)
            write_json(gw_dir / "summary.json", summary)
            write_json(gw_dir / "league-details.json", details)
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
        f"latest completed GW={latest_gw if latest_gw is not None else 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
