from __future__ import annotations
import json
import os
import time
import uuid
from copy import deepcopy

SAVES_DIR = "/saves"

_COLORS = ["#c4902a", "#4a9eff", "#7dff7d", "#ff7d7d", "#ffcc7d", "#c47aff"]


def _path(session_id: str) -> str:
    return os.path.join(SAVES_DIR, f"mp_{session_id}.json")


def _read(session_id: str) -> dict | None:
    p = _path(session_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write(session_id: str, state: dict) -> None:
    os.makedirs(SAVES_DIR, exist_ok=True)
    with open(_path(session_id), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def create_session(game_state: dict, host_name: str) -> tuple[str, str, dict]:
    """Create a new multiplayer session. Returns (session_id, player_id, state)."""
    session_id = str(uuid.uuid4())[:6].upper()
    player_id = str(uuid.uuid4())[:8]

    state = deepcopy(game_state)
    state["multiplayer"] = {
        "enabled": True,
        "session_id": session_id,
        "players": [{"id": player_id, "name": host_name, "color": _COLORS[0]}],
        "last_updated": time.time(),
    }
    _write(session_id, state)
    return session_id, player_id, state


def join_session(session_id: str, player_name: str) -> tuple[str | None, dict | None]:
    """Join an existing session. Returns (player_id, state) or (None, None) if not found."""
    state = _read(session_id)
    if state is None:
        return None, None

    player_id = str(uuid.uuid4())[:8]
    idx = len(state["multiplayer"]["players"])
    color = _COLORS[idx % len(_COLORS)]
    state["multiplayer"]["players"].append({"id": player_id, "name": player_name, "color": color})
    state["multiplayer"]["last_updated"] = time.time()
    _write(session_id, state)
    return player_id, state


def sync(session_id: str) -> dict | None:
    """Pull the latest state from disk."""
    return _read(session_id)


def push(session_id: str, state: dict) -> None:
    """Write updated state back to the shared session file."""
    s = deepcopy(state)
    s["multiplayer"]["last_updated"] = time.time()
    _write(session_id, s)


def get_player(state: dict, player_id: str) -> dict:
    for p in state.get("multiplayer", {}).get("players", []):
        if p["id"] == player_id:
            return p
    return {"id": player_id, "name": "Unknown", "color": "#ffffff"}


def list_sessions() -> list[dict]:
    os.makedirs(SAVES_DIR, exist_ok=True)
    out = []
    for fname in os.listdir(SAVES_DIR):
        if fname.startswith("mp_") and fname.endswith(".json"):
            try:
                with open(os.path.join(SAVES_DIR, fname), "r", encoding="utf-8") as f:
                    s = json.load(f)
                mp = s.get("multiplayer", {})
                out.append({
                    "session_id": mp.get("session_id", "?"),
                    "players": [p["name"] for p in mp.get("players", [])],
                    "setting": s.get("world", {}).get("setting", "?"),
                    "location": s.get("world", {}).get("current_location", "?"),
                })
            except Exception:
                pass
    return out
