from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "fetch_fpl_draft.py"
spec = importlib.util.spec_from_file_location("fetcher", MODULE_PATH)
fetcher = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fetcher)


def test_latest_complete_gameweek():
    details = {
        "matches": [
            {"event": 1, "finished": True},
            {"event": 1, "finished": True},
            {"event": 2, "finished": True},
            {"event": 2, "finished": False},
        ]
    }
    assert fetcher.latest_complete_gameweek(details) == 1


def test_sanitize_manager_names():
    data = {
        "player_first_name": "Private",
        "player_last_name": "Person",
        "entry_name": "Draft FC",
        "nested": [{"email": "private@example.com", "id": 5}],
    }
    cleaned = fetcher.sanitize(data)
    assert "player_first_name" not in cleaned
    assert "player_last_name" not in cleaned
    assert cleaned["entry_name"] == "Draft FC"
    assert "email" not in cleaned["nested"][0]
    assert cleaned["nested"][0]["id"] == 5


if __name__ == "__main__":
    test_latest_complete_gameweek()
    test_sanitize_manager_names()
    print("Tests passed")
