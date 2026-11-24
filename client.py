"""Cheetos String Tool: a TavernKeeper tab for building, labelling, drawing, previewing and saving spawn strings.

Made By Cheeto. Registers itself after the Macros tab; delete this addon folder and the tab disappears.
"""
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from tavern_shared.theme import AMBER, AMBERDIM, BG, BORDER, GREEN, MONO, MUTED, PARCH, RED, SURF, SURF2, _btn, _mk_scrollbar
from tavern_shared.window_chrome import _finish_dark_window, _set_window_icon, _start_hidden

from . import attributes, components, dialogs, edits, layout2d, library, liveinfo, render2d
from . import catalog as catalog_module
from .catalog import Catalog
from .preview import PreviewTracker
from .visuals import Visuals

try:
    from PIL import ImageTk
except ImportError:  # no Pillow: the 2D view falls back to outlines
    ImageTk = None
from .stringcodec import SpawnString, StringFormatError, decode, encode

WHOLE, ALL = "Whole part", "All pieces"  # Piece choices besides the named pieces
NO_MATERIAL = "(this item has no material)"

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(HERE, "data", "items.json")
VISUALS = os.path.join(HERE, "data", "visuals.json")
LIBRARY = os.path.join(HERE, "data", "library.json")
COMPONENTS = os.path.join(HERE, "data", "components.json")
REFS = os.path.join(HERE, "data", "refs.json")
CREDIT = "Made By Cheeto"
# Strings longer than this are spawned without TavernKeeper printing them whole (Tk freezes on very long lines).
LONG_STRING = 5000


def _data_dir():
    try:
        from tavern_shared.paths import _tavern_data_dir
        return _tavern_data_dir()
    except Exception:
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TheModdingTavern")


def user_library_path():
    return os.path.join(_data_dir(), "string_builder_library.json")


def named_materials_path():
    return os.path.join(_data_dir(), "string_builder_materials.json")


def _info(title, text, parent=None):
    messagebox.showinfo(title, text, parent=parent)


def _ask(title, text, parent=None):
    return messagebox.askyesno(title, text, parent=parent)


_catalog = None


def fresh_catalog():
    """The shipped item data plus the materials this player has named."""
    try:
        cat = Catalog.load(ITEMS)
    except Exception:
        cat = Catalog.empty()
    for h, n in liveinfo.load_named_materials(named_materials_path()).items():
        cat.learn_material(n, h)
    return cat


def get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = fresh_catalog()
    return _catalog


_visuals = None


def get_visuals():
    global _visuals
    if _visuals is None:
        _visuals = Visuals.load(VISUALS)
        get_catalog().alias_swatches(_visuals)
    return _visuals


_schema = None
_refs = None


def get_schema():
    """The game's saved layouts for item components (shipped data); empty if the file is missing."""
    global _schema
    if _schema is None:
        try:
            _schema = components.Schema.load(COMPONENTS)
        except (OSError, ValueError):
            _schema = components.Schema({})
    return _schema


def get_refs():
    """Names of game assets by kind (liquids, effects, stats, ...) for the attributes window."""
    global _refs
    if _refs is None:
        try:
            with open(REFS, encoding="utf-8") as f:
                _refs = json.load(f)
        except (OSError, ValueError):
            _refs = {}
    return _refs


def _data_warning(cat):
    if not cat.prefabs:
        return "Item data is missing, so items show as numbers and can't be drawn. Reinstall the addon."
    try:  # TavernKeeper caches this server's prefab list here after Browse Prefabs
        with open(os.path.join(_data_dir(), "prefabs.json"), encoding="utf-8") as f:
            raw = json.load(f)
        server = set()
        for p in raw if isinstance(raw, list) else []:
            if isinstance(p, (list, tuple)) and p:
                server.add(int(p[0]))  # TavernKeeper saves [hash, name] pairs
            elif isinstance(p, dict) and "Hash" in p:
                server.add(int(p["Hash"]))
    except Exception:
        return None
    missing = len(server - set(cat.prefabs))
    if missing:
        return ("This server has %d item(s) the String Tool doesn't know (its data is from game build %s). "
                "Those show as 'Unknown item'." % (missing, cat.build))
    return None


def _style():
    st = ttk.Style()
    st.configure("SB.Treeview", background=SURF, fieldbackground=SURF, foreground=PARCH, rowheight=22, borderwidth=0)
    st.map("SB.Treeview", background=[("selected", AMBERDIM)], foreground=[("selected", "#ffd080")])
    st.configure("SB.TCombobox", fieldbackground=SURF, background=SURF2, foreground=PARCH, arrowcolor=AMBERDIM)
    st.map("SB.TCombobox", fieldbackground=[("disabled", BG), ("readonly", SURF)],
           foreground=[("disabled", MUTED), ("readonly", PARCH)])


def _label(parent, text, fg=PARCH, font=("Segoe UI", 9), **kw):
    return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=fg, font=font, **kw)


class StringBuilderTab:
    VIEW_NAMES = ["Side", "Front", "Top", "Back"]

    def __init__(self, parent, window):
        self.frame = parent
        self.window = window
        self.cat = get_catalog()
        self.vis = get_visuals()
        self.schema = get_schema()
        self.refs = get_refs()
        self.ss = None
        self.sel_prefab = None
        self.sel_slot = None  # (prefab, slot hash) that a double-clicked item will fill
        self.view = None  # None = pick the view that shows the item largest
        self.fresh = False  # built with New: gets the current versioning tail; loaded strings keep their own
        self.dirty = False  # unsaved edits
        self._hits = []  # parts and slot markers from the last draw, for click picking
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0  # right-drag offset of the 2D view, in pixels
        self._pan_from = None
        self._row_map = {}
        self._shape_map = {}
        self._polys = []  # canvas polygons from the last draw, nearest last, for click picking
        self._photo = None
        self._synced_host = None
        if not hasattr(window, "_string_builder_preview"):
            window._string_builder_preview = PreviewTracker()  # survives tab rebuilds
        self.preview = window._string_builder_preview
        _style()
        self._build()
        self.refresh_search()
        self.refresh()
        self._sync_job = self.frame.after(1500, self._auto_sync)
        self.frame.bind("<Destroy>", lambda e: self._stop_sync() if e.widget is self.frame else None, add="+")

    # ---- layout ------------------------------------------------------------------------------
    def _build(self):
        f = self.frame
        # Footer first, packed to the bottom, so it is always visible.
        foot = tk.Frame(f, bg=BG)
        foot.pack(side="bottom", fill="x")
        tk.Frame(foot, bg=BORDER, height=1).pack(fill="x")
        _label(foot, CREDIT, fg=AMBER, font=("Georgia", 9, "bold")).pack(side="right", padx=10, pady=3)
        self.string_var = tk.StringVar(value="")
        _label(foot, "", textvariable=self.string_var, fg=MUTED, font=MONO, anchor="w").pack(side="left", fill="x", expand=True, padx=8)

        bar = tk.Frame(f, bg=BG)
        bar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        _btn(bar, "Paste string", self.paste, font=("Segoe UI", 9), pady=4, padx=8).pack(side="left")
        _btn(bar, "My strings", self.open_library, font=("Segoe UI", 9), pady=4, padx=8).pack(side="left", padx=4)
        _btn(bar, "New", self.new, font=("Segoe UI", 9), pady=4, padx=8).pack(side="left")
        _btn(bar, "Copy string", self.copy, "primary", font=("Segoe UI", 9, "bold"), pady=4, padx=8).pack(side="right")
        _btn(bar, "Clear preview", self.clear_preview, font=("Segoe UI", 9), pady=4, padx=8).pack(side="right", padx=4)
        _btn(bar, "Spawn preview", self.spawn_preview, "success", font=("Segoe UI", 9, "bold"), pady=4, padx=8).pack(side="right")
        _btn(bar, "Refresh", self.sync_server, font=("Segoe UI", 9), pady=4, padx=6).pack(side="left", padx=(10, 2))
        self.sync_label = _label(bar, "Items: the addon's list", fg=MUTED, font=("Segoe UI", 8))
        self.sync_label.pack(side="left")
        tgt = tk.Frame(bar, bg=BG)
        tgt.pack(side="right", padx=8)
        _label(tgt, "Target:", fg=MUTED).pack(side="left")
        tv = getattr(self.window, "v_target", None)
        _label(tgt, "", textvariable=tv, fg=PARCH, font=("Segoe UI", 9, "bold")).pack(side="left") if tv is not None else None

        warn = _data_warning(self.cat)
        if warn:
            _label(f, "Warning: " + warn, fg=RED, wraplength=820, justify="left", anchor="w").pack(side="top", fill="x", padx=8)

        body = tk.Frame(f, bg=BG)
        body.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 6))
        body.columnconfigure(0, weight=0, minsize=185)
        body.columnconfigure(1, weight=3, minsize=290)
        body.columnconfigure(2, weight=4, minsize=280)
        body.rowconfigure(0, weight=1)
        self._build_items(self._pane(body, 0, "Items"))
        self._build_parts(self._pane(body, 1, "Parts"))
        self._build_view(self._pane(body, 2, "2D view"))

    def _pane(self, body, col, title):
        p = tk.Frame(body, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        p.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0))
        head = tk.Frame(p, bg=SURF)
        head.pack(fill="x", padx=6, pady=(6, 2))
        _label(head, title, fg=AMBER, font=("Georgia", 10, "bold"), bg=SURF).pack(side="left")
        p.head = head
        return p

    def _build_items(self, p):
        self.search_var = tk.StringVar()
        e = tk.Entry(p, textvariable=self.search_var, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                     font=("Segoe UI", 10), bd=5)
        e.pack(fill="x", padx=6, pady=(0, 4))
        self.search_var.trace_add("write", lambda *_: self.refresh_search())
        self.fits_var = tk.BooleanVar(value=False)
        self.fits_check = tk.Checkbutton(p, text="Only items that fit the slot", variable=self.fits_var,
                                         command=self.refresh_search, bg=SURF, fg=MUTED, selectcolor=SURF2,
                                         activebackground=SURF, activeforeground=PARCH, font=("Segoe UI", 8),
                                         anchor="w", wraplength=190, justify="left")
        self.fits_check.pack(fill="x", padx=4)
        box = tk.Frame(p, bg=SURF)
        box.pack(fill="both", expand=True, padx=6, pady=4)
        self.results = tk.Listbox(box, bg=SURF, fg=PARCH, selectbackground=AMBERDIM, selectforeground="#ffd080",
                                  relief="flat", highlightthickness=0, font=("Segoe UI", 9), activestyle="none")
        sb = _mk_scrollbar(box, self.results.yview)
        sb.pack(side="right", fill="y")
        self.results.config(yscrollcommand=sb.set)
        self.results.pack(side="left", fill="both", expand=True)
        self.results.bind("<Double-Button-1>", lambda e: self._on_result_double())
        self.results.bind("<Return>", lambda e: self._on_result_double())
        self.items_hint = _label(p, "Double-click to start a new string, or to fill the selected slot.", fg=MUTED,
                                 bg=SURF, font=("Segoe UI", 8), wraplength=190, justify="left")
        self.items_hint.pack(fill="x", padx=6, pady=(0, 6))
        self._result_hashes = []

    def _build_parts(self, p):
        box = tk.Frame(p, bg=SURF)
        box.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.tree = ttk.Treeview(box, show="tree", selectmode="browse", style="SB.Treeview")
        sb = _mk_scrollbar(box, self.tree.yview)
        sb.pack(side="right", fill="y")
        xsb = _mk_scrollbar(box, self.tree.xview, orient="horizontal")
        xsb.pack(side="bottom", fill="x")
        self.tree.config(yscrollcommand=sb.set, xscrollcommand=xsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("slot", foreground="#7fa7c9")
        self.tree.tag_configure("unknown", foreground=RED)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select())
        self.tree.bind("<Double-Button-1>", lambda e: self._on_tree_double())

        props = tk.Frame(p, bg=SURF)
        props.pack(fill="x", padx=6, pady=(0, 6))
        tk.Frame(props, bg=BORDER, height=1).pack(fill="x", pady=(0, 4))
        self.sel_title = _label(props, "Nothing selected", fg=AMBER, bg=SURF, font=("Georgia", 9, "bold"), anchor="w")
        self.sel_title.pack(fill="x")
        rowp = tk.Frame(props, bg=SURF)
        rowp.pack(fill="x", pady=2)
        _label(rowp, "Piece", fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
        self.piece_var = tk.StringVar(value=WHOLE)
        self.piece_box = ttk.Combobox(rowp, textvariable=self.piece_var, values=[WHOLE], state="readonly",
                                      style="SB.TCombobox", font=("Segoe UI", 9))
        self.piece_box.pack(side="left", fill="x", expand=True)
        self.piece_box.bind("<<ComboboxSelected>>", lambda e: (self._show_material(), self.draw()))
        self.pieces_btn = _btn(rowp, "Materials…", self.open_piece_editor, font=("Segoe UI", 8), pady=1, padx=6)
        self.pieces_btn.pack(side="left", padx=(4, 0))
        row = tk.Frame(props, bg=SURF)
        row.pack(fill="x", pady=2)
        _label(row, "Material", fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
        self.mat_var = tk.StringVar()
        self._materials = [(None, "(none)")] + self.cat.materials()
        self.mat_box = ttk.Combobox(row, textvariable=self.mat_var, values=[n for _, n in self._materials],
                                    state="readonly", style="SB.TCombobox", font=("Segoe UI", 9))
        self.mat_box.pack(side="left", fill="x", expand=True)
        self.mat_box.bind("<<ComboboxSelected>>", lambda e: self._apply_material())
        _btn(row, "Add…", self.add_material, font=("Segoe UI", 8), pady=1, padx=6).pack(side="left", padx=(4, 0))
        row2 = tk.Frame(props, bg=SURF)
        row2.pack(fill="x", pady=2)
        _label(row2, "Item scale", fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
        self.scale_var = tk.StringVar()
        se = tk.Entry(row2, textvariable=self.scale_var, width=8, bg=SURF2, fg=PARCH, insertbackground=AMBER,
                      relief="flat", font=("Segoe UI", 9), bd=3)
        se.pack(side="left")
        se.bind("<Return>", lambda e: self._apply_scale())
        _btn(row2, "Set", self._apply_scale, font=("Segoe UI", 8), pady=1, padx=6).pack(side="left", padx=4)
        self.remove_btn = _btn(row2, "Remove part", self._remove_selected, "danger", font=("Segoe UI", 8), pady=1, padx=6)
        self.remove_btn.pack(side="right")
        row3 = tk.Frame(props, bg=SURF)
        row3.pack(fill="x", pady=2)
        _label(row3, "Holds", fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
        self.dock_type_var = tk.StringVar()
        self.dock_qty_var = tk.StringVar(value="1")
        self.dock_btn = _btn(row3, "Select a dock to fill it", self._holds_clicked, font=("Segoe UI", 8),
                             pady=2, padx=8, anchor="w")
        self.dock_btn.pack(side="left", fill="x", expand=True)
        row5 = tk.Frame(props, bg=SURF)
        row5.pack(fill="x", pady=2)
        _label(row5, "Settings", fg=MUTED, bg=SURF, font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
        self.attr_btn = _btn(row5, "Select a part to change its settings", self.open_attributes, font=("Segoe UI", 8),
                             pady=2, padx=8, anchor="w")
        self.attr_btn.pack(side="left", fill="x", expand=True)
        row4 = tk.Frame(props, bg=SURF)
        row4.pack(fill="x", pady=(4, 0))
        _btn(row4, "Attach a string to this slot…", self._attach_string_dialog, font=("Segoe UI", 8),
             pady=2, padx=6).pack(side="left")

    def _build_view(self, p):
        self.view_var = tk.StringVar(value="Auto")
        for name in ["Auto"] + self.VIEW_NAMES:
            tk.Radiobutton(p.head, text=name, value=name, variable=self.view_var, command=self._on_view, indicatoron=False,
                           bg=SURF2, fg=PARCH, selectcolor=AMBERDIM, activebackground=SURF2, relief="flat",
                           font=("Segoe UI", 8), padx=5, bd=0).pack(side="left", padx=1)
        self.canvas = tk.Canvas(p, bg="#16120e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", lambda e: self.click_at(e.x, e.y))
        self.canvas.bind("<Double-Button-1>", lambda e: self.double_click_at(e.x, e.y))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<Button-4>", lambda e: self._zoom(1.15))
        self.canvas.bind("<Button-5>", lambda e: self._zoom(1 / 1.15))

    # ---- string state ------------------------------------------------------------------------
    def current_string(self):
        if self.ss is None:
            return ""
        v = self.cat.versioning() if self.fresh else None
        return encode(self.ss, versioning=v or None)

    def _confirm_discard(self):
        return not self.dirty or _ask("Unsaved changes", "Your current string has changes that aren't saved. "
                                      "Replace it anyway?", parent=self.frame)

    def load_string(self, text):
        try:
            ss = decode(text)
        except Exception as e:  # malformed, truncated, or nested too deep to read
            _info("Not a spawn string", "That doesn't look like a spawn string.\n\n%s" % e, parent=self.frame)
            return False
        if not self._confirm_discard():
            return False
        self.ss, self.fresh, self.dirty = ss, False, False
        self.sel_prefab, self.sel_slot = ss.root, None
        self.view, self.zoom = None, 1.0
        self.pan_x = self.pan_y = 0
        self.view_var.set("Auto")
        self.refresh()
        return True

    def new(self):
        if not self._confirm_discard():
            return
        self.ss, self.sel_prefab, self.sel_slot, self.dirty = None, None, None, False
        self.refresh()

    def new_from(self, prefab_h):
        self.ss, self.fresh, self.dirty = edits.new_string(prefab_h), True, True
        self.sel_prefab, self.sel_slot = self.ss.root, None
        first = self.cat.slots(prefab_h)
        if first:
            self.sel_slot = (self.ss.root, first[0][0])
        self.view, self.zoom = None, 1.0
        self.pan_x = self.pan_y = 0
        self.refresh()

    def select_slot(self, prefab, slot_h):
        self.sel_prefab, self.sel_slot = prefab, (prefab, slot_h)
        self.refresh()

    def attach_item(self, prefab_h):
        if self.ss is None:
            self.new_from(prefab_h)
            return
        if not self.sel_slot:
            _info("Pick a slot", "Select an empty slot in Parts (or on the drawing) first, then double-click an item.",
                  parent=self.frame)
            return
        parent, slot_h = self.sel_slot
        child = edits.attach(self.ss, parent, slot_h, prefab_h)
        self.dirty = True
        self.sel_prefab = child
        free = [h for h, _l, _k in self.cat.slots(prefab_h)]
        self.sel_slot = (child, free[0]) if free else self._next_empty_slot()
        self.refresh()

    def _next_empty_slot(self):
        for r in edits.tree(self.ss, self.cat):
            if r.empty_slots:
                return (r.prefab, r.empty_slots[0][0])
        return None

    # ---- actions -----------------------------------------------------------------------------
    def paste(self):
        try:
            text = self.frame.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            _info("Clipboard empty", "Copy a spawn string first, then press Paste string.", parent=self.frame)
            return
        self.load_string(text)

    def copy(self):
        s = self.current_string()
        if not s:
            _info("Nothing to copy", "Build or load a string first.", parent=self.frame)
            return
        self.frame.clipboard_clear()
        self.frame.clipboard_append(s)
        self._log("[String Tool] Copied the string (%d characters).\n" % len(s), "ok")

    def spawn_preview(self):
        if self.ss is None:
            _info("Nothing to spawn", "Build or load a string first.", parent=self.frame)
            return
        if not getattr(self.window, "_connected", False):
            _info("Not connected", "Connect to a server first.", parent=self.frame)
            return
        target = self.window._current_target()
        if not target:
            return
        s = self.current_string()
        cmd = self.preview.spawn_command(self.window._q(target), self.window._q(s))

        def done(_rs, rd):
            n = self.preview.record(rd)
            self._log("[String Tool] Spawned %d preview item(s) for %s.\n" % (n, target) if n else
                      "[String Tool] The server didn't spawn it. Check the console output above.\n", "ok" if n else "err")
        ws = getattr(self.window, "_ws_client", None)
        if len(s) > LONG_STRING and hasattr(ws, "send_capture"):
            # TavernKeeper prints every command whole in its console box, and Tk freezes for a long time laying out
            # one line hundreds of thousands of characters long. Send it ourselves and log a short line instead.
            short = self.preview.spawn_command(self.window._q(target), "<%s-character string>" % format(len(s), ","))
            self._log("> %s\n" % short, "cyan")

            reply = []

            def worker():
                rs, rd, _err = ws.send_capture(cmd, timeout=60.0)
                reply.append((rs, rd))

            def check():  # Tk is only touched from the window's own thread
                if reply:
                    done(*reply[0])
                    return
                try:
                    self.frame.after(100, check)
                except tk.TclError:
                    pass  # the window closed meanwhile
            threading.Thread(target=worker, daemon=True).start()
            self.frame.after(100, check)
            return
        self.window._send_and_capture(cmd, done, max_wait=60.0)  # big strings can take a while to spawn

    def clear_preview(self):
        if not self.preview.ids:
            _info("Nothing to clear", "No preview items are out right now.", parent=self.frame)
            return
        if not getattr(self.window, "_connected", False):
            _info("Not connected", "Connect to the server again to clear the preview.", parent=self.frame)
            return
        n = self.preview.clear(self.window._send)
        self._log("[String Tool] Cleared %d preview item(s).\n" % n, "ok")

    def save_user_string(self, name):
        if self.ss is None or not name:
            return False
        ok = library.add_user(user_library_path(), name, self.current_string())
        if ok:
            self.dirty = False
        return ok

    def _log(self, text, tag=""):
        try:
            self.window._append_log(text, tag)
        except Exception:
            pass

    # ---- search ------------------------------------------------------------------------------
    def refresh_search(self):
        fits = None
        if self.sel_slot:
            p, h = self.sel_slot
            self.fits_check.config(text="Only items that fit %s" % self.cat.embed_name(p.hash, h), state="normal")
            if self.fits_var.get():
                fits = (p.hash, h)
        else:
            self.fits_check.config(text="Only items that fit the slot (select a slot first)", state="disabled")
        found = self.cat.search(self.search_var.get(), fits=fits, limit=400)
        self.items_hint.config(text="Showing the first 400 matches. Type more to narrow it down." if len(found) >= 400
                               else "Double-click to start a new string, or to fill the selected slot.")
        self._result_hashes = [h for h, _ in found]
        self.results.delete(0, "end")
        for _h, name in found:
            self.results.insert("end", name)

    def _on_result_double(self):
        sel = self.results.curselection()
        if sel:
            self.attach_item(self._result_hashes[sel[0]])

    # ---- tree --------------------------------------------------------------------------------
    def tree_rows(self):
        out = []

        def walk(iid):
            for c in self.tree.get_children(iid):
                out.append(c)
                walk(c)
        walk("")
        return out

    def refresh(self):
        self._refill_tree()
        self._refresh_props()
        self.refresh_search()
        s = self.current_string()
        self.string_var.set(("String: " + (s[:110] + "…" if len(s) > 110 else s)) if s else
                            "No string yet: double-click an item on the left, or paste a string.")
        self.draw()

    def _refill_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._row_map = {}
        if self.ss is None:
            return
        parents = {}
        select = None
        for r in edits.tree(self.ss, self.cat):
            m = edits.get_material(r.prefab, self.cat)
            text = r.label + ("  ·  " + self.cat.material_short(m) if m is not None else "")
            if r.slot_label:
                text = r.slot_label + " → " + text
            parent_iid = parents.get(id(r.parent), "")
            iid = self.tree.insert(parent_iid, "end", text=text, open=True,
                                   tags=("unknown",) if r.label.startswith("Unknown") else ())
            parents[id(r.prefab)] = iid
            self._row_map[iid] = ("part", r.prefab, None)
            if r.prefab is self.sel_prefab and not self.sel_slot:
                select = iid
            if self.cat.is_gift_box(r.prefab.hash):
                gid = self.tree.insert(iid, "end", text="Gift: " + self._gift_summary(r.prefab), tags=("slot",), open=False)
                self._row_map[gid] = ("part", r.prefab, None)
                for n, it in edits.gift_groups(edits.get_gift(r.prefab)):
                    cid = self.tree.insert(gid, "end", text=dialogs.gift_item_label(self.cat, n, it), tags=("slot",))
                    self._row_map[cid] = ("part", r.prefab, None)
            for h, label in r.empty_slots:
                held = edits.get_dock(r.prefab, h, self.cat)
                text = ("◆ %s: %d × %s" % (label, held[1], self.cat.item_type_name(held[0])) if held
                        else "○ " + label + " (empty)")
                sid = self.tree.insert(iid, "end", text=text, tags=("slot",))
                self._row_map[sid] = ("slot", r.prefab, h)
                if self.sel_slot and self.sel_slot[0] is r.prefab and self.sel_slot[1] == h:
                    select = sid
        self._fit_tree_width()
        if select:
            self._suppress = True
            self.tree.selection_set(select)
            self.tree.see(select)
            self._suppress = False

    def _fit_tree_width(self):
        """Makes the column as wide as the longest row (text plus indent) so long builds scroll sideways."""
        # Tk's own "font measure": tkinter.font isn't bundled in the released TavernLauncher Client exe
        measure = lambda text: int(self.tree.tk.call("font", "measure", "TkDefaultFont", text))
        widest = 0
        def walk(iid, depth):
            nonlocal widest
            for c in self.tree.get_children(iid):
                widest = max(widest, measure(self.tree.item(c, "text")) + 20 * (depth + 1))
                walk(c, depth + 1)
        walk("", 0)
        self.tree.column("#0", minwidth=widest + 8, width=widest + 8, stretch=True)

    def _on_tree_double(self):
        sel = self.tree.selection()
        if sel and sel[0] in self._row_map and self._row_map[sel[0]][0] == "part":
            p = self._row_map[sel[0]][1]
            self.open_gift_editor(p) if self.cat.is_gift_box(p.hash) else self.open_piece_editor(p)

    def _on_tree_select(self):
        if getattr(self, "_suppress", False):
            return
        sel = self.tree.selection()
        if not sel or sel[0] not in self._row_map:
            return
        kind, prefab, slot_h = self._row_map[sel[0]]
        self.sel_prefab = prefab
        self.sel_slot = (prefab, slot_h) if kind == "slot" else None
        self._refresh_props()
        self.refresh_search()
        self.draw()

    def _refresh_props(self):
        p = self.sel_prefab
        if self.ss is None or p is None:
            self.sel_title.config(text="Nothing selected")
            self.mat_var.set("")
            self.scale_var.set("")
            self.piece_box.config(values=[WHOLE], state="disabled")
            self.piece_var.set(WHOLE)
            self.pieces_btn.config(state="disabled")
            self._refresh_dock()
            self._refresh_attrs()
            return
        title = self.cat.prefab_name(p.hash)
        if self.sel_slot:
            title += "  ·  filling " + self.cat.embed_name(p.hash, self.sel_slot[1])
        self.sel_title.config(text=title)
        names = [n for _, n in self.cat.pieces(p.hash)]
        options = ([WHOLE] if self.cat.has_own_material(p.hash) else []) + ([ALL] + names if names else [])
        self.piece_box.config(values=options or [NO_MATERIAL], state="readonly" if len(options) > 1 else "disabled")
        self.mat_box.config(state="readonly" if options else "disabled")
        if self.piece_var.get() not in options:
            self.piece_var.set(options[0] if options else NO_MATERIAL)
        self._show_material()
        self._refresh_dock()
        self._refresh_attrs()
        self.pieces_btn.config(state="normal" if options else "disabled")
        self.scale_var.set(("%g" % self.ss.root.scale))  # only the base item's scale counts; it sizes the whole build

    def _piece_hash(self):
        """The selected piece's embed hash, or WHOLE / ALL."""
        name = self.piece_var.get()
        if name in (WHOLE, ALL, NO_MATERIAL, ""):
            return name or WHOLE
        return next((h for h, n in self.cat.pieces(self.sel_prefab.hash) if n == name), WHOLE)

    def _show_material(self):
        p = self.sel_prefab
        if self.ss is None or p is None:
            return
        piece = self._piece_hash()
        if piece in (ALL, NO_MATERIAL):
            self.mat_var.set("")
            return
        m = edits.get_material(p, self.cat) if piece == WHOLE else edits.get_piece_material(p, piece, self.cat)
        self.mat_var.set(self.cat.material_name(m) if m is not None else "(none)")

    def _apply_material(self):
        if self.ss is None or self.sel_prefab is None:
            return
        name = self.mat_var.get()
        mat = next((h for h, n in self._materials if n == name and h is not None), None)
        if mat is None:
            return
        p, piece = self.sel_prefab, self._piece_hash()
        if piece == NO_MATERIAL:
            return
        if piece == WHOLE:
            edits.set_material(self.ss, p, mat, self.cat)
        elif piece == ALL:
            for h, _n in self.cat.pieces(p.hash):
                edits.set_piece_material(self.ss, p, h, mat, self.cat)
        elif not edits.set_piece_material(self.ss, p, piece, mat, self.cat):
            _info("Piece removed", "That piece was removed from this item in the string, so it has no material.",
                  parent=self.frame)
            return
        self.dirty = True
        self.refresh()

    # ---- docks and string on string ------------------------------------------------------------
    def _selected_dock(self):
        """(prefab, dock hash) when the selected slot is a dock, else None."""
        if self.ss is None or not self.sel_slot:
            return None
        p, h = self.sel_slot
        e = self.cat.embed(p.hash, h)
        return (p, h) if e and e["kind"] == "dock" else None

    def _attrs(self, p=None):
        if p is None:
            if self.sel_slot:
                return []
            p = self.sel_prefab
        if self.ss is None or p is None:
            return []
        return attributes.list_attrs(self.ss, p, self.cat, self.schema, fresh=self.fresh)

    def _refresh_attrs(self):
        attrs = self._attrs()
        if not attrs:
            self.attr_btn.config(text="Nothing to change on this part" if self.sel_prefab and not self.sel_slot
                                 else "Select a part to change its settings", state="disabled")
            return
        changed = sum(1 for a in attrs if a.status == "set")
        text = attributes.summary(attrs) or "%d setting%s" % (len(attrs), "" if len(attrs) == 1 else "s")
        self.attr_btn.config(text=text + ("  ·  %d changed" % changed if changed else "") + "   ▾", state="normal")

    def open_attributes(self, prefab=None):
        """The attributes window for a part with saved settings (potion liquid, fuse, durability, ...)."""
        from .attr_dialog import AttributeEditor
        p = prefab or self.sel_prefab
        if self.ss is None or p is None or not self._attrs(p):
            return None
        return AttributeEditor(self, p)

    def _gift_box(self):
        """The selected part when it's a gift mail box (names and contents), else None."""
        p = self.sel_prefab
        return p if self.ss is not None and p is not None and not self.sel_slot and self.cat.is_gift_box(p.hash) else None

    def _holds_clicked(self):
        return self.open_gift_editor() if self._gift_box() else self.open_dock_picker()

    def open_gift_editor(self, prefab=None):
        p = prefab or self._gift_box()
        if self.ss is None or p is None or not self.cat.is_gift_box(p.hash):
            return None
        return dialogs.GiftEditor(self, p)

    def _gift_summary(self, p):
        g = edits.get_gift(p)
        if g is None:
            return "Empty · add names and contents"
        bits = [("To: " + g.to) if g.to else "", ("From: " + g.sender) if g.sender else "",
                "%d inside" % len(g.items) if g.items else "empty"]
        return " · ".join(b for b in bits if b)

    def _refresh_dock(self):
        d = self._selected_dock()
        held = edits.get_dock(d[0], d[1], self.cat) if d else None
        self.dock_type_var.set(self.cat.item_type_name(held[0]) if held else "")
        self.dock_qty_var.set(str(held[1]) if held else "1")
        box = self._gift_box()
        if box is not None:
            self.dock_btn.config(text="Gift: " + self._gift_summary(box) + "   ▾", state="normal")
        elif not d:
            self.dock_btn.config(text="Select a dock to fill it", state="disabled")
        else:
            self.dock_btn.config(text=("◆ %d × %s   ▾" % (held[1], self.cat.item_type_name(held[0])) if held
                                       else "Empty · choose what it holds   ▾"), state="normal")

    def open_dock_picker(self):
        d = self._selected_dock()
        return dialogs.DockPicker(self, d[0], d[1]) if d else None

    def open_piece_editor(self, prefab=None):
        """The materials window for an item that has a material or pieces; None for anything else."""
        p = prefab or self.sel_prefab
        if self.ss is None or p is None or not (self.cat.pieces(p.hash) or self.cat.has_own_material(p.hash)):
            return None
        return dialogs.PieceEditor(self, p)

    def name_material(self, h, name):
        """Names a material the addon doesn't know; kept on this PC for every string."""
        names = liveinfo.load_named_materials(named_materials_path())
        names[int(h)] = name
        try:
            liveinfo.save_named_materials(named_materials_path(), names)
        except OSError:
            pass
        self.cat.learn_material(name, h)
        self._materials = [(None, "(none)")] + self.cat.materials()
        self.mat_box.config(values=[n for _, n in self._materials])
        self.refresh()

    def add_material_by_number(self, text, name):
        """Adds a material (from a mod) by its number and a name; the number, or None if it isn't one."""
        h = catalog_module.parse_material_number(text)
        if h is None or not (name or "").strip():
            return None
        self.name_material(h, name.strip())
        return h

    def add_material(self, parent=None):
        """Asks for a mod material's number and name, so it can be picked like any other material."""
        parent = parent or self.frame
        text = simpledialog.askstring(
            "Add a material", "The material's number (from the mod, or from a string that uses it).\n"
            "Servers with the String Tool helper mod list their mod materials by themselves.", parent=parent)
        if text is None:
            return None
        h = catalog_module.parse_material_number(text)
        if h is None:
            _info("Not a material number", "That isn't a material number. It's a whole number, like 1276475934.",
                  parent=parent)
            return None
        known = self.cat.knows_material(h)
        name = simpledialog.askstring("Add a material", "What is material #%d called?" % h, parent=parent,
                                      initialvalue=self.cat.material_short(h) if known else "")
        return self.add_material_by_number(str(h), name) if name else None

    # ---- the connected server's own lists ------------------------------------------------------
    def _host(self):
        v = getattr(self.window, "v_host", None)
        try:
            return v.get() if v is not None else "server"
        except Exception:
            return "server"

    def _stop_sync(self):
        try:
            self.frame.after_cancel(self._sync_job)
        except (tk.TclError, ValueError):
            pass

    def _auto_sync(self):
        try:
            if getattr(self.window, "_connected", False) and self._synced_host != self._host():
                self.sync_server()
            self._sync_job = self.frame.after(3000, self._auto_sync)
        except tk.TclError:
            pass  # the tab was closed

    def sync_server(self):
        """Reads items, parts and dock item types from the connected server, so modded ones work too."""
        if not getattr(self.window, "_connected", False):
            _info("Not connected", "Connect TavernKeeper to a server first.", parent=self.frame)
            return
        host = self._host()
        self._synced_host = host
        self.sync_label.config(text="Items: reading the server…", fg=MUTED)
        replies = {}

        def step(i):
            if i == len(liveinfo.COMMANDS):
                return self._finish_sync(host, replies)
            cmd = liveinfo.COMMANDS[i]

            def got(_rs, rd):
                replies[cmd] = rd
                step(i + 1)
            self.window._send_and_capture(cmd, got, max_wait=30.0)
        step(0)

    def _finish_sync(self, host, replies):
        live = liveinfo.parse(replies.get("spawn infodump"), replies.get("repair-box list-items"),
                              replies.get("stringtool materials"))
        if not live["prefabs"]:
            cached = liveinfo.load_cache(liveinfo.cache_path(_data_dir(), host))
            if not cached:
                self.sync_label.config(text="Items: the addon's list (server didn't answer)", fg=RED)
                return
            live, note = cached, " (saved copy)"
        else:
            note = ""
            try:
                liveinfo.save_cache(liveinfo.cache_path(_data_dir(), host), live)
            except OSError:
                pass
        global _catalog
        cat = fresh_catalog()
        cat.apply_live(live)
        cat.alias_swatches(self.vis)
        _catalog = self.cat = cat
        self._materials = [(None, "(none)")] + cat.materials()
        self.mat_box.config(values=[n for _, n in self._materials])
        new = sum(1 for p in cat.prefabs.values() if p.get("live_only"))
        mods = sum(1 for h, _n in cat.materials() if cat.material_mod(h) == catalog_module.SERVER_MOD)
        self.sync_label.config(text="Items: from %s, %d items%s%s%s" % (
            host, len(live["prefabs"]), (", %d new" % new) if new else "",
            (", %d mod material%s" % (mods, "" if mods == 1 else "s")) if mods else "", note), fg=GREEN)
        self.refresh()

    def _apply_dock(self):
        d = self._selected_dock()
        if not d:
            return
        name = self.dock_type_var.get().strip().lower()
        t = next((h for h, n in self.cat.item_types() if n.lower() == name), None)
        if t is None:
            _info("Dock holds", "Pick an item type from the list.", parent=self.frame)
            return
        try:
            q = int(self.dock_qty_var.get())
            if not 1 <= q <= 2000000000:
                raise ValueError
        except ValueError:
            _info("Dock holds", "The amount must be a whole number from 1 up.", parent=self.frame)
            return
        edits.set_dock(self.ss, d[0], d[1], t, q, self.cat)
        self.dirty = True
        self.refresh()
        return True

    def _empty_dock(self):
        d = self._selected_dock()
        if not d:
            return
        edits.clear_dock(self.ss, d[0], d[1], self.cat)
        self.dirty = True
        self.refresh()

    def attach_string_text(self, text):
        """Puts a whole string (with everything on it) into the selected empty slot or dock."""
        if self.ss is None or not self.sel_slot:
            _info("Pick a slot", "Select an empty slot or dock in Parts first, then attach a string to it.",
                  parent=self.frame)
            return False
        try:
            inner = decode(text)
        except Exception as e:
            _info("Not a spawn string", "That doesn't look like a spawn string.\n\n%s" % e, parent=self.frame)
            return False
        parent, slot_h = self.sel_slot
        child = edits.attach_string(self.ss, parent, slot_h, inner)
        self.dirty = True
        self.sel_prefab, self.sel_slot = child, None
        self.refresh()
        return True

    def pick_string(self, use, title, parent=None):
        """A saved or clipboard string handed to `use(text)`; the window closes when it returns True."""
        return LibraryDialog(self, attach=True, use=use, title=title)

    def _attach_string_dialog(self):
        if self.ss is None or not self.sel_slot:
            _info("Pick a slot", "Select an empty slot or dock in Parts first, then attach a string to it.",
                  parent=self.frame)
            return
        LibraryDialog(self, attach=True)

    def _apply_scale(self):
        if self.ss is None or self.sel_prefab is None:
            return
        try:
            v = float(self.scale_var.get())
            if not 0.01 <= v <= 100:
                raise ValueError
        except ValueError:
            _info("Scale", "Scale must be a number between 0.01 and 100.", parent=self.frame)
            return
        edits.set_scale(self.ss, self.ss.root, v)
        self.dirty = True
        self.refresh()

    def _remove_selected(self):
        if self.ss is None or self.sel_prefab is None:
            return
        if self.sel_slot:
            _info("Remove part", "That's an empty slot. Select the part itself to remove it.", parent=self.frame)
            return
        found = edits.find_parent(self.ss, self.sel_prefab)
        if not found:
            _info("Remove part", "That's the base item. Use New to start over instead.", parent=self.frame)
            return
        parent, slot_h = found
        n = len(edits.tree(SpawnString(self.sel_prefab), self.cat)) - 1
        if n and not _ask("Remove part", "Remove %s and the %d part(s) attached to it?"
                          % (self.cat.prefab_name(self.sel_prefab.hash), n), parent=self.frame):
            return
        edits.detach(self.ss, parent, self.sel_prefab)
        self.dirty = True
        self.sel_prefab, self.sel_slot = parent, (parent, slot_h)
        self.refresh()

    # ---- 2D view -----------------------------------------------------------------------------
    def _on_view(self):
        v = self.view_var.get()
        self.view = None if v == "Auto" else v.lower()
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0
        self.draw()

    def _pan_start(self, e):
        self._pan_from = (e.x, e.y)

    def _pan_move(self, e):
        if self._pan_from is None:
            return
        self.pan_x += e.x - self._pan_from[0]
        self.pan_y += e.y - self._pan_from[1]
        self._pan_from = (e.x, e.y)
        self.draw()

    def _on_wheel(self, e):
        self._zoom(1.15 if e.delta > 0 else 1 / 1.15)

    def _zoom(self, f):
        self.zoom = max(0.2, min(20.0, self.zoom * f))
        self.draw()

    def _pick_view(self):
        if self.view:
            return self.view
        best, area = "side", -1.0
        for v in ("side", "front", "top"):
            shapes = layout2d.layout(self.ss.root, self.cat, v)
            x0 = min(s.rect[0] for s in shapes); x1 = max(s.rect[2] for s in shapes)
            y0 = min(s.rect[1] for s in shapes); y1 = max(s.rect[3] for s in shapes)
            a = (x1 - x0) * (y1 - y0)
            if a > area + 1e-9:
                best, area = v, a
        return best

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        for x in range(0, w, 20):
            c.create_line(x, 0, x, h, fill="#221c15")
        for y in range(0, h, 20):
            c.create_line(0, y, w, y, fill="#221c15")
        self._shape_map = {}
        self._hits = []
        if self.ss is None:
            c.create_text(w / 2, h / 2, text="Double-click an item on the left to start,\nor paste one of your strings.",
                          fill=MUTED, font=("Segoe UI", 10), justify="center")
            return
        view = self._pick_view()
        shapes = layout2d.layout(self.ss.root, self.cat, view)
        world = render2d.polygons(self.ss.root, self.cat, self.vis, view)
        scale, ox, oy = render2d.fit_points(world, w, h, 24) if world else layout2d.fit(shapes, w, h, 24)
        scale *= self.zoom
        ox = w / 2 + (ox - w / 2) * self.zoom
        oy = h / 2 + (oy - h / 2) * self.zoom
        ox += self.pan_x
        oy += self.pan_y
        piece = self._piece_hash() if self.sel_prefab is not None else None
        hl = {piece} if isinstance(piece, int) else set()
        img, self._polys = render2d.render(self.ss.root, self.cat, self.vis, view, w, h, (scale, ox, oy),
                                           selected=self.sel_prefab, highlight=hl, grid=True)
        textured = img is not None and ImageTk is not None
        if textured:
            self._photo = ImageTk.PhotoImage(img)
            c.create_image(0, 0, anchor="nw", image=self._photo)
        self._depth = {id(s.prefab): s.depth for s in shapes}
        colours = [AMBER, "#7fa7c9", "#c9a0dc", GREEN, "#d98a6a"]
        for i, s in enumerate(shapes):
            x0, y0, x1, y1 = layout2d.to_canvas(s.rect, scale, ox, oy)
            sel = s.prefab is self.sel_prefab
            col = colours[s.depth % len(colours)]
            tag = "shape%d" % i
            c.create_rectangle(x0, y0, x1, y1, outline="#ffd080" if sel else col, width=2.5 if sel else 1.2,
                               fill="#3d311d" if sel else "", tags=("part", tag),
                               state="hidden" if textured else "normal")  # the picture shows the parts
            self._shape_map[tag] = s
            self._hits.append(("part", (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), s))
        for s in shapes:  # labels and slot markers on top
            x0, y0, x1, y1 = layout2d.to_canvas(s.rect, scale, ox, oy)
            if s.prefab is self.sel_prefab or len(shapes) <= 6:
                c.create_text(x0 + 2, y0 - 2, text=s.label, anchor="sw", fill=PARCH if s.prefab is self.sel_prefab else MUTED,
                              font=("Segoe UI", 8))
            for h_, x, y, filled in s.slot_points:
                if filled:
                    continue
                px, py = layout2d.point_to_canvas(x, y, scale, ox, oy)
                sel = self.sel_slot and self.sel_slot[0] is s.prefab and self.sel_slot[1] == h_
                tag = "slot%d_%d" % (id(s.prefab), h_)
                c.create_oval(px - 4, py - 4, px + 4, py + 4, outline="#ffd080" if sel else "#7fa7c9",
                              dash=() if sel else (2, 2), width=2 if sel else 1, tags=("slotpoint", tag))
                self._hits.append(("slot", (px, py), (s.prefab, h_)))
        c.create_text(6, h - 6, text=view.title() + " view", anchor="sw", fill=MUTED, font=("Segoe UI", 8))
        c.create_text(w - 6, h - 6, text="scroll: zoom · right-drag: move · double-click: materials", anchor="se", fill=MUTED,
                      font=("Segoe UI", 8))

    def _part_under(self, x, y):
        """The polygon under the point: attached parts win over what they're attached to, then the nearest."""
        under = [q for q in self._polys if render2d._inside(q.points, x, y)]
        return max(under, key=lambda q: (self._depth.get(id(q.prefab), 0), q.depth)) if under else None

    def double_click_at(self, x, y):
        """Opens the piece editor for the crafted item under the pointer."""
        q = self._part_under(x, y)
        if q is None:
            return None
        self.sel_prefab, self.sel_slot = q.prefab, None
        self.refresh()
        if self.cat.is_gift_box(q.prefab.hash):
            return self.open_gift_editor(q.prefab)
        return self.open_piece_editor(q.prefab)

    def click_at(self, x, y):
        """Empty-slot markers win within 8 px; otherwise the most deeply attached (then smallest) part under the pointer."""
        for kind, where, what in self._hits:
            if kind == "slot" and (where[0] - x) ** 2 + (where[1] - y) ** 2 <= 64:
                self.select_slot(*what)
                return
        q = self._part_under(x, y)
        if q is not None:
            self.sel_prefab, self.sel_slot = q.prefab, None
            if q.piece and q.entity in dict(self.cat.pieces(q.prefab.hash)):
                self.piece_var.set(dict(self.cat.pieces(q.prefab.hash))[q.entity])
            self.refresh()
            return
        best = None
        for kind, where, what in self._hits:
            if kind == "part" and where[0] - 2 <= x <= where[2] + 2 and where[1] - 2 <= y <= where[3] + 2:
                key = (-what.depth, (where[2] - where[0]) * (where[3] - where[1]))  # attached parts sit on top
                if best is None or key < best[0]:
                    best = (key, what)
        if best:
            self._click_shape(best[1])

    def _click_shape(self, s):
        self.sel_prefab, self.sel_slot = s.prefab, None
        self.refresh()

    # ---- library dialog ----------------------------------------------------------------------
    def open_library(self):
        LibraryDialog(self)


class LibraryDialog:
    def __init__(self, tab, attach=False, use=None, title=None):
        self.tab = tab
        self.attach = attach  # pick a string to put into the selected slot instead of loading it
        self.use = use or (tab.attach_string_text if attach else tab.load_string)
        top = self.top = tk.Toplevel(tab.frame)
        _start_hidden(top)
        top.title(title or ("Attach a string" if attach else "My strings"))
        top.configure(bg=BG)
        top.geometry("560x620")
        _set_window_icon(top)
        top.transient(tab.frame.winfo_toplevel())
        data = library.default_data(LIBRARY)
        _label(top, "Strings", fg=AMBER, font=("Georgia", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        if data.get("note"):
            _label(top, data["note"], fg=MUTED, font=("Segoe UI", 8), wraplength=530, justify="left").pack(anchor="w", padx=12, pady=(2, 6))
        self.q = tk.StringVar()
        e = tk.Entry(top, textvariable=self.q, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                     font=("Segoe UI", 10), bd=5)
        e.pack(fill="x", padx=12, pady=(0, 6))
        self.q.trace_add("write", lambda *_: self.fill())
        box = tk.Frame(top, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True, padx=12)
        self.tree = ttk.Treeview(box, show="tree", selectmode="browse", style="SB.Treeview")
        sb = _mk_scrollbar(box, self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", lambda e: self.load())
        btns = tk.Frame(top, bg=BG)
        btns.pack(fill="x", padx=12, pady=10)
        if attach:
            _btn(btns, "Use" if use else "Attach", self.load, "primary", font=("Segoe UI", 9, "bold"), pady=5, padx=12).pack(side="left")
            _btn(btns, "From clipboard", self.from_clipboard, font=("Segoe UI", 9), pady=5, padx=10).pack(
                side="left", padx=6)
        else:
            _btn(btns, "Load", self.load, "primary", font=("Segoe UI", 9, "bold"), pady=5, padx=12).pack(side="left")
            _btn(btns, "Save current as…", self.save, font=("Segoe UI", 9), pady=5, padx=10).pack(side="left", padx=6)
            _btn(btns, "Delete", self.delete, "danger", font=("Segoe UI", 9), pady=5, padx=10).pack(side="left")
        _label(btns, CREDIT, fg=AMBER, font=("Georgia", 9, "bold")).pack(side="right")
        self.defaults = data.get("entries", [])
        self.items = {}
        self.fill()
        e.focus_set()
        _finish_dark_window(top)

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        words = self.q.get().lower().split()
        groups = {}
        for e in self.defaults:
            groups.setdefault(e.get("folder") or "Strings", []).append((e, False))
        groups["My saved strings"] = [(e, True) for e in library.load_user(user_library_path())]
        for g, entries in groups.items():
            shown = [(e, mine) for e, mine in entries if all(w in e["name"].lower() for w in words)]
            gid = self.tree.insert("", "end", text="%s (%d)" % (g, len(shown)), open=bool(words) or g == "My saved strings")
            for e, mine in shown:
                iid = self.tree.insert(gid, "end", text=e["name"] + ("" if mine else "   · by " + e.get("credit", "")))
                self.items[iid] = (e, mine)

    def _selected(self):
        sel = self.tree.selection()
        return self.items.get(sel[0]) if sel else None

    def load(self):
        it = self._selected()
        if not it:
            return
        if self.use(it[0]["string"]):
            self.top.destroy()

    def from_clipboard(self):
        try:
            text = self.top.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            _info("Clipboard empty", "Copy a spawn string first.", parent=self.top)
            return
        if self.use(text):
            self.top.destroy()

    def save(self):
        if self.tab.ss is None:
            _info("Nothing to save", "Build or load a string first.", parent=self.top)
            return
        name = simpledialog.askstring("Save string", "Name for this string:", parent=self.top)
        if not name or not name.strip():
            return
        name = name.strip()
        if any(e["name"] == name for e in library.load_user(user_library_path())) and not _ask(
                "Replace", "You already have a string called '%s'. Replace it?" % name, parent=self.top):
            return
        if not self.tab.save_user_string(name):
            _info("Couldn't save", "Your saved-strings file couldn't be read or written, so nothing was changed. "
                  "A copy of it was kept next to it as .bak.\n\n%s" % user_library_path(), parent=self.top)
            return
        self.fill()

    def delete(self):
        it = self._selected()
        if not it:
            return
        e, mine = it
        if not mine:
            _info("Built-in string", "Built-in strings can't be deleted. Only your saved strings can.", parent=self.top)
            return
        if _ask("Delete", "Delete '%s'?" % e["name"], parent=self.top):
            if not library.delete_user(user_library_path(), e["name"]):
                _info("Couldn't delete", "Your saved-strings file couldn't be read or written, so nothing was changed.",
                      parent=self.top)
            self.fill()


def build_tab(parent, window):
    return StringBuilderTab(parent, window)


try:
    from client.core.tavernkeeper.registry import register_tab
    register_tab("string_builder", "String Tool", build_tab, after="macros")
except ImportError:
    pass  # imported outside the launcher (tests)
