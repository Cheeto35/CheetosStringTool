"""Item knowledge read from the connected server's own console, so modded items, parts and dock contents work.

Two vanilla commands give it:
  spawn infodump          every spawnable item, its parts in the game's order, and what each part saves
  repair-box list-items   the item types a dock can hold
The game has no command that lists material numbers, so a third one comes from the String Tool's helper mod:
  stringtool materials    every material on the server, mods included, with its number and the look it copies
Servers without the helper answer "Command not found"; then mod materials are named by the player instead
(named_materials). parse() turns the replies into the dict Catalog.apply_live() takes; it is cached per server.
"""
import json
import os
from typing import List, Optional

COMMANDS = ("spawn infodump", "repair-box list-items", "stringtool materials")


def parse(infodump, list_items, materials=None) -> dict:
    prefabs = []
    for p in infodump or []:
        try:
            embeds = [[int(e["Hash"]), str(e.get("Name") or ""), [str(s.get("Name")) for s in e.get("Savables") or []]]
                      for e in p.get("Embedded") or []]
            prefabs.append([int(p["Hash"]), str(p.get("Name") or ""), embeds])
        except (KeyError, TypeError, ValueError):
            continue  # one odd entry shouldn't lose the rest
    types = []
    for i in list_items or []:
        try:
            types.append([int(i["Hash"]), str(i["Name"])])
        except (KeyError, TypeError, ValueError):
            continue
    mats = []
    for m in materials if isinstance(materials, list) else []:
        try:
            mats.append([int(m["Hash"]), str(m["Name"]), str(m.get("Looks") or "")])
        except (KeyError, TypeError, ValueError):
            continue
    return {"prefabs": prefabs, "item_types": types, "materials": mats}


def cache_path(data_dir: str, host: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-." else "_" for c in (host or "server"))
    return os.path.join(data_dir, "string_builder_live_%s.json" % safe)


def save_cache(path: str, live: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(live, f, separators=(",", ":"))
    os.replace(tmp, path)


def load_cache(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and "prefabs" in data else None
    except (OSError, ValueError):
        return None


def load_named_materials(path: str) -> dict:
    """{material hash: name} the player gave to materials the addon didn't know."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {int(h): str(n) for h, n in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_named_materials(path: str, names: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({str(h): n for h, n in names.items()}, f, indent=1)
    os.replace(tmp, path)
