"""The built-in string library (read-only, ships with the addon) and the player's own saved strings."""
import json
import os
from typing import List


def default_data(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"note": "", "entries": []}
    except Exception:
        return {"note": "", "entries": []}


def default_entries(path: str) -> List[dict]:
    return list(default_data(path).get("entries", []))


def load_user(path: str) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [{"name": str(e.get("name", "")), "string": str(e.get("string", "")), "credit": str(e.get("credit", ""))}
            for e in data if isinstance(e, dict) and e.get("name") and e.get("string")]


def save_user(path: str, entries: List[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def add_user(path: str, name: str, string: str) -> bool:
    entries = [e for e in load_user(path) if e["name"] != name]
    entries.append({"name": name, "string": string, "credit": ""})
    return save_user(path, entries)


def delete_user(path: str, name: str) -> bool:
    return save_user(path, [e for e in load_user(path) if e["name"] != name])
