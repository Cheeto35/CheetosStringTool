"""Keeps track of what Spawn preview put in the world, so Clear removes exactly that.

Destroying a spawned item's root also removes everything attached to it and everything inside it (checked on a
58-piece food bag), so only root ids are kept.
"""
from typing import Callable, List


class PreviewTracker:
    def __init__(self):
        self.ids: List[int] = []

    @staticmethod
    def spawn_command(target_q: str, string_q: str) -> str:
        return "spawn string %s %s" % (target_q, string_q)

    def record(self, result_data) -> int:
        items = result_data if isinstance(result_data, list) else [result_data]
        n = 0
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("Identifier"), int):
                self.ids.append(item["Identifier"])
                n += 1
        return n

    def clear_commands(self) -> List[str]:
        cmds = ["wacky destroy %d" % i for i in self.ids]
        self.ids = []
        return cmds

    def clear(self, send: Callable[[str], None]) -> int:
        cmds = self.clear_commands()
        for c in cmds:
            try:
                send(c)
            except Exception:
                pass  # already gone, or the connection dropped; nothing else to do
        return len(cmds)
