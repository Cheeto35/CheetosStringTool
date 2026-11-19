"""The attributes window: an item's saved settings (a potion's liquid and effects, a dynamite fuse, durability, ...)
as checkboxes, number boxes and lists, built from the game's own layouts. Changes go into the string as they're made.
"""
import tkinter as tk
from tkinter import colorchooser, ttk

from tavern_shared.theme import AMBER, BG, BORDER, GREEN, MUTED, PARCH, RED, SURF, SURF2, _btn, _mk_scrollbar
from tavern_shared.window_chrome import _finish_dark_window

from . import attributes as A
from . import components as C
from .dialogs import _label, _window

NUMBER = ("int", "uint", "float", "long", "ulong", "timespan", "datetime")
LIMITS = {"int": (-2 ** 31, 2 ** 31 - 1), "uint": (0, 2 ** 32 - 1), "long": (-2 ** 63, 2 ** 63 - 1),
          "ulong": (0, 2 ** 64 - 1), "timespan": (-2 ** 63, 2 ** 63 - 1), "datetime": (0, 2 ** 64 - 1)}
STATUS = {"default": ("normal values", MUTED), "set": ("changed in this string", GREEN),
          "old": ("saved by an older game version, so it can't be changed here", RED),
          "unreadable": ("couldn't be read, so it's left as it is", RED)}


def parse_number(kind, text):
    """The typed value for a number box, or None when it isn't a number that fits."""
    text = (text or "").strip()
    try:
        if kind == "float":
            v = float(text)
            return v if v == v and abs(v) < 3.4e38 else None
        v = int(float(text)) if "." in text or "e" in text.lower() else int(text)
    except ValueError:
        return None
    lo, hi = LIMITS[kind]
    return v if lo <= v <= hi else None


def _fmt(kind, v):
    if kind == "float":
        return ("%.6g" % v) if v is not None else "0"
    return str(v)


def _hex(c):
    def ch(x):
        x = float(x or 0)
        x = x / 255.0 if x > 1.0 else x  # some old strings used 0-255
        return max(0, min(255, int(round(x * 255))))
    return "#%02x%02x%02x" % (ch(c.get("r")), ch(c.get("g")), ch(c.get("b")))


class AttributeEditor:
    def __init__(self, tab, prefab):
        self.tab, self.prefab = tab, prefab
        self.cat, self.schema, self.refs = tab.cat, tab.schema, tab.refs
        top = self.top = _window(tab, "Attributes", "600x680")
        _label(top, self.cat.prefab_name(prefab.hash), fg=AMBER, font=("Georgia", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        _label(top, "Settings the item saves. Untouched ones keep the item's normal values; changes go straight into "
               "the string.", fg=MUTED, font=("Segoe UI", 8), wraplength=560, justify="left").pack(anchor="w", padx=12)
        bar = tk.Frame(top, bg=BG)
        bar.pack(fill="x", padx=12, pady=(6, 4))
        self.more = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Show every setting (advanced)", variable=self.more, command=self.rebuild, bg=BG, fg=MUTED,
                       selectcolor=SURF2, activebackground=BG, activeforeground=PARCH, font=("Segoe UI", 8)).pack(side="left")
        _btn(bar, "Done", self.close, "primary", font=("Segoe UI", 9, "bold"), pady=3, padx=14).pack(side="right")
        box = tk.Frame(top, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.canvas = tk.Canvas(box, bg=SURF, highlightthickness=0)
        sb = _mk_scrollbar(box, self.canvas.yview)
        sb.pack(side="right", fill="y")
        self.canvas.config(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=SURF)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        top.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
        top.protocol("WM_DELETE_WINDOW", self.close)
        self.attrs = []
        self.sections = {}
        self._refresh_job = None
        self.rebuild()
        _finish_dark_window(top)

    # ---- sections -------------------------------------------------------------------------------
    def rebuild(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.attrs = A.list_attrs(self.tab.ss, self.prefab, self.cat, self.schema, fresh=self.tab.fresh)
        self.sections = {}
        shown = [a for a in self.attrs if a.friendly or self.more.get()]
        if not shown:
            _label(self.inner, "This item has no settings that can be changed here." if not self.attrs else
                   "Nothing common to change. Tick 'Show every setting' to see the rest.", fg=MUTED, bg=SURF,
                   wraplength=520, justify="left").pack(anchor="w", padx=10, pady=10)
        for a in shown:
            frame = tk.Frame(self.inner, bg=SURF)
            frame.pack(fill="x", padx=8, pady=(8, 2))
            self.sections[(a.embed_h, a.component)] = frame
            self._section(frame, a)

    def _section(self, frame, a):
        for w in frame.winfo_children():
            w.destroy()
        head = tk.Frame(frame, bg=SURF)
        head.pack(fill="x")
        _label(head, A.title(a.component), fg=AMBER, bg=SURF, font=("Georgia", 10, "bold")).pack(side="left")
        if a.part_name != self.cat.prefab_name(self.prefab.hash):
            _label(head, "  on " + a.part_name, fg=MUTED, bg=SURF, font=("Segoe UI", 8)).pack(side="left")
        text, colour = STATUS[a.status]
        if a.status == "default":
            _btn(head, "Change", lambda: self.start(a), font=("Segoe UI", 8), pady=1, padx=8).pack(side="right")
        elif a.status == "set":
            _btn(head, "↺ Normal values", lambda: self.reset(a), font=("Segoe UI", 8), pady=1, padx=8).pack(side="right")
        _label(frame, text, fg=colour, bg=SURF, font=("Segoe UI", 8)).pack(anchor="w")
        if a.status == "set":
            body = tk.Frame(frame, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
            body.pack(fill="x", pady=(2, 0))
            fields = self.schema.fields(a.component) or []
            for f in fields:
                if A.hidden_field(a.component, f["name"]):
                    continue
                self._field(body, a, f["name"], f["type"], a.value, f["name"])
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))

    # ---- changes --------------------------------------------------------------------------------
    def _redraw(self, a):
        frame = self.sections.get((a.embed_h, a.component))
        if frame is None:
            self.rebuild()
        else:
            self._section(frame, a)

    def start(self, a):
        value = A.starting_value(self.schema, a.component)
        if A.set_values(self.tab.ss, self.prefab, a, value, self.cat, self.schema):
            self._changed()
            self._redraw(a)

    def reset(self, a):
        A.reset(self.tab.ss, self.prefab, a, self.cat)
        self._changed()
        self._redraw(a)

    def commit(self, a, redraw=False):
        if a.component == "LiquidContainer" and a.value.get("isCustom") and a.value.get("customData") is None:
            a.value["customData"] = A.starting_mix(self.schema, self.refs)
            redraw = True
        ok = A.set_values(self.tab.ss, self.prefab, a, a.value, self.cat, self.schema)
        self._changed()
        if redraw or not ok:
            self._redraw(a)
        return ok

    def _changed(self):
        self.tab.dirty = True
        if self._refresh_job is None:
            self._refresh_job = self.top.after(150, self._refresh_tab)

    def _refresh_tab(self):
        self._refresh_job = None
        try:
            self.tab.refresh()
        except tk.TclError:
            pass

    def close(self):
        if self._refresh_job is not None:
            self.top.after_cancel(self._refresh_job)
            self._refresh_job = None
        self.top.destroy()
        self.tab.refresh()

    # ---- one field ------------------------------------------------------------------------------
    def _row(self, parent, text):
        row = tk.Frame(parent, bg=SURF)
        row.pack(fill="x", padx=6, pady=1)
        _label(row, text, fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=24, anchor="w").pack(side="left")
        return row

    def _field(self, parent, a, path, t, holder, key):
        """An editor for holder[key] (a dict field or a list slot) of type t."""
        k = t["k"]
        text = A.label(a.component, path)

        def put(v, redraw=False):
            holder[key] = v
            return self.commit(a, redraw)

        if k == "bool":
            var = tk.BooleanVar(value=bool(holder[key]))
            row = self._row(parent, text)
            tk.Checkbutton(row, variable=var, command=lambda: put(var.get()), bg=SURF, selectcolor=SURF2,
                           activebackground=SURF).pack(side="left")
        elif k in NUMBER:
            row = self._row(parent, text)
            var = tk.StringVar(value=_fmt(k, holder[key]))
            e = tk.Entry(row, textvariable=var, width=14, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                         font=("Segoe UI", 9), bd=3)
            e.pack(side="left")

            def done(_ev=None, e=e, var=var):
                v = parse_number(k, var.get())
                try:
                    e.config(bg="#5a2020" if v is None else SURF2)
                except tk.TclError:
                    return  # the section was rebuilt
                if v is not None and v != holder[key]:
                    put(v)
            e.bind("<Return>", done)
            e.bind("<FocusOut>", done)
            if path in ("contentLevel",):
                for n in (1, 100, 99999999):
                    _btn(row, "∞" if n == 99999999 else str(n), lambda n=n: (var.set(str(n)), done()),
                         font=("Segoe UI", 7), pady=0, padx=4).pack(side="left", padx=1)
        elif k == "string":
            row = self._row(parent, text)
            var = tk.StringVar(value=holder[key] or "")
            e = tk.Entry(row, textvariable=var, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                         font=("Segoe UI", 9), bd=3)
            e.pack(side="left", fill="x", expand=True)
            e.bind("<Return>", lambda _e: put(var.get()))
            e.bind("<FocusOut>", lambda _e: put(var.get()) if var.get() != (holder[key] or "") else None)
        elif k == "ref":
            row = self._row(parent, text)
            names = A.ref_names(self.refs, t["name"])
            options = [(0, "(none)")] + names
            cur = int(holder[key] or 0)
            if cur not in dict(options):
                options.append((cur, "#%d" % cur))
            var = tk.StringVar(value=dict(options)[cur])
            box = ttk.Combobox(row, textvariable=var, values=[n for _h, n in options], state="readonly",
                               style="SB.TCombobox", font=("Segoe UI", 9))
            box.pack(side="left", fill="x", expand=True)
            box.bind("<<ComboboxSelected>>", lambda _e: put(next(h for h, n in options if n == var.get())))
        elif k == "enum":
            row = self._row(parent, text)
            values = t.get("values") or []
            cur = int(holder[key] or 0)
            labels = [A.pretty(v) for v in values] or [str(cur)]
            var = tk.StringVar(value=labels[cur] if 0 <= cur < len(labels) else str(cur))
            box = ttk.Combobox(row, textvariable=var, values=labels, state="readonly", style="SB.TCombobox",
                               font=("Segoe UI", 9))
            box.pack(side="left", fill="x", expand=True)
            box.bind("<<ComboboxSelected>>", lambda _e: put(labels.index(var.get())))
        elif k == "struct" and t["name"] == "UnityEngine.Color":
            row = self._row(parent, text)
            c = holder[key] or {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}
            sw = tk.Label(row, text="      ", bg=_hex(c), relief="flat", cursor="hand2")
            sw.pack(side="left", padx=(0, 6))

            def pick(_e=None):
                got = colorchooser.askcolor(color=_hex(c), parent=self.top, title=text)
                if got and got[0]:
                    r, g, b = got[0]
                    put({"r": r / 255.0, "g": g / 255.0, "b": b / 255.0, "a": float(c.get("a") or 1.0) or 1.0}, True)
            sw.bind("<Button-1>", pick)
            _btn(row, "Pick…", pick, font=("Segoe UI", 8), pady=0, padx=6).pack(side="left")
        elif k == "struct":
            row = self._row(parent, text)
            d = self.schema.types.get(t["name"]) or {}
            v = holder[key] if isinstance(holder[key], dict) else C.blank(self.schema, t)
            holder[key] = v
            for f in d.get("fields") or []:
                if f["type"]["k"] not in NUMBER:
                    continue
                _label(row, f["name"], fg=MUTED, bg=SURF, font=("Segoe UI", 8)).pack(side="left")
                var = tk.StringVar(value=_fmt(f["type"]["k"], v.get(f["name"])))
                e = tk.Entry(row, textvariable=var, width=7, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                             font=("Segoe UI", 9), bd=2)
                e.pack(side="left", padx=(1, 4))

                def done(_ev=None, e=e, var=var, f=f):
                    n = parse_number(f["type"]["k"], var.get())
                    try:
                        e.config(bg="#5a2020" if n is None else SURF2)
                    except tk.TclError:
                        return
                    if n is not None and n != v.get(f["name"]):
                        v[f["name"]] = n
                        self.commit(a)
                e.bind("<Return>", done)
                e.bind("<FocusOut>", done)
        elif k == "class":
            d = self.schema.types.get(t["name"]) or {}
            on = holder[key] is not None
            var = tk.BooleanVar(value=on)
            row = self._row(parent, text)

            def toggle():
                fresh = (A.starting_mix(self.schema, self.refs) if t["name"] == A.CUSTOM_MIX
                         else C.blank_class(self.schema, t["name"]))
                put(fresh if var.get() else None, True)
            tk.Checkbutton(row, variable=var, command=toggle, bg=SURF, selectcolor=SURF2, activebackground=SURF).pack(side="left")
            if on:
                sub = tk.Frame(parent, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
                sub.pack(fill="x", padx=(18, 6), pady=2)
                for f in d.get("fields") or []:
                    self._field(sub, a, path + "." + f["name"], f["type"], holder[key], f["name"])
        elif k in ("array", "list"):
            items = holder[key] if isinstance(holder[key], list) else []
            holder[key] = items
            head = self._row(parent, "%s (%d)" % (text, len(items)))
            of = t["of"]

            def add():
                if of["k"] == "class":
                    items.append(C.blank_class(self.schema, of["name"]))
                else:
                    items.append(C.blank(self.schema, of))
                self.commit(a, True)
            _btn(head, "＋ Add", add, font=("Segoe UI", 8), pady=0, padx=6).pack(side="left")
            sub = tk.Frame(parent, bg=SURF)
            sub.pack(fill="x", padx=(18, 6))
            for i in range(len(items)):
                cell = tk.Frame(sub, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
                cell.pack(fill="x", pady=1)
                bar = tk.Frame(cell, bg=SURF)
                bar.pack(fill="x")
                _label(bar, "#%d" % (i + 1), fg=MUTED, bg=SURF, font=("Segoe UI", 7)).pack(side="left", padx=4)

                def remove(i=i):
                    del items[i]
                    self.commit(a, True)
                _btn(bar, "✕", remove, "danger", font=("Segoe UI", 7), pady=0, padx=4).pack(side="right")
                if of["k"] == "class":
                    if items[i] is None:
                        items[i] = C.blank_class(self.schema, of["name"])
                    for f in (self.schema.types.get(of["name"]) or {}).get("fields") or []:
                        self._field(cell, a, path + "." + f["name"], f["type"], items[i], f["name"])
                else:
                    self._field(cell, a, path, of, items, i)
        else:
            self._row(parent, text + " (can't be changed here)")
