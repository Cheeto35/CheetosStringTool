"""The String Builder's pop-up windows: the piece editor (an item drawn large, its pieces and a material palette) and
the dock picker (a searchable list of what a dock can hold, with an amount)."""
import tkinter as tk
from tkinter import simpledialog

from tavern_shared.theme import AMBER, AMBERDIM, BG, BORDER, MUTED, PARCH, SURF, SURF2, _btn, _mk_scrollbar
from tavern_shared.window_chrome import _finish_dark_window, _set_window_icon, _start_hidden

from . import edits, render2d
from .stringcodec import Prefab

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

WHOLE_ITEM = 0  # stands for the item itself (its own material) in the piece editor's selection


def _label(parent, text, fg=PARCH, font=("Segoe UI", 9), **kw):
    return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=fg, font=font, **kw)


def _entry(parent, var, **kw):
    return tk.Entry(parent, textvariable=var, bg=SURF2, fg=PARCH, insertbackground=AMBER, relief="flat",
                    font=kw.pop("font", ("Segoe UI", 10)), bd=5, **kw)


def _window(tab, title, size):
    top = tk.Toplevel(tab.frame)
    _start_hidden(top)
    top.title(title)
    top.configure(bg=BG)
    top.geometry(size)
    _set_window_icon(top)
    top.transient(tab.frame.winfo_toplevel())
    return top


class MaterialPalette:
    """A searchable list of materials, each with its texture swatch. Calls on_pick(material hash)."""
    ROW = 28

    def __init__(self, parent, tab, on_pick, on_name=None):
        self.tab, self.on_pick, self.on_name = tab, on_pick, on_name
        self.frame = tk.Frame(parent, bg=SURF)
        self.q = tk.StringVar()
        e = _entry(self.frame, self.q, font=("Segoe UI", 9))
        e.pack(fill="x", padx=4, pady=(4, 2))
        self.q.trace_add("write", lambda *_: self.fill())
        box = tk.Frame(self.frame, bg=SURF)
        box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.canvas = tk.Canvas(box, bg=SURF, highlightthickness=0, height=200)
        sb = _mk_scrollbar(box, self.canvas.yview)
        sb.pack(side="right", fill="y")
        self.canvas.config(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", lambda ev: self.canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units"))
        self._icons, self.rows, self.current = {}, [], None
        self.unknown = []  # material hashes in the string that the addon doesn't know
        self.fill()

    def _icon(self, h):
        if ImageTk is None:
            return None
        if h not in self._icons:
            sw = self.tab.vis.swatch(h) if self.tab.vis else None
            self._icons[h] = ImageTk.PhotoImage(sw.resize((22, 22))) if sw is not None else None
        return self._icons[h]

    def fill(self):
        c = self.canvas
        c.delete("all")
        words = self.q.get().lower().split()
        self.rows = [(h, n) for h, n in self.tab.cat.materials() if all(w in n.lower() for w in words)]
        self.rows += [(h, "Unknown #%d  (click to name it)" % h) for h in self.unknown
                      if not self.tab.cat.knows_material(h)]
        w = max(c.winfo_width(), 220)
        for i, (h, n) in enumerate(self.rows):
            y = i * self.ROW
            sel = h == self.current
            c.create_rectangle(0, y, w, y + self.ROW - 2, fill=AMBERDIM if sel else SURF, outline="")
            icon = self._icon(h)
            if icon is not None:
                c.create_image(4, y + 2, anchor="nw", image=icon)
            else:
                col = (self.tab.vis.material_color(h) if self.tab.vis else None) or "#777777"
                c.create_rectangle(4, y + 2, 26, y + 24, fill=col, outline="")
            c.create_text(34, y + self.ROW / 2 - 1, text=n, anchor="w", fill="#ffd080" if sel else PARCH,
                          font=("Segoe UI", 9))
        c.config(scrollregion=(0, 0, w, len(self.rows) * self.ROW))

    def _click(self, ev):
        i = int(self.canvas.canvasy(ev.y) // self.ROW)
        if 0 <= i < len(self.rows):
            self.pick(self.rows[i][0])

    def pick(self, h):
        if not self.tab.cat.knows_material(h):
            if self.on_name:
                self.on_name(h)
            return
        self.current = h
        self.fill()
        self.on_pick(h)


class PieceEditor:
    """One item drawn large: hover to see a piece's name, click to pick pieces (Ctrl adds), then click a material."""

    def __init__(self, tab, prefab: Prefab):
        self.tab, self.prefab = tab, prefab
        cat = tab.cat
        self.pieces = cat.pieces(prefab.hash)
        self.own = cat.has_own_material(prefab.hash)
        self.names = dict(self.pieces)
        if self.own:
            self.names[WHOLE_ITEM] = "(the item itself)"
        self.selected = set()
        self.hover = None
        self._order = [WHOLE_ITEM] * self.own + [h for h, _ in self.pieces]
        self._polys = []
        self.view = tab._pick_view() if tab.ss is not None else "side"
        top = self.top = _window(tab, "Pieces · " + cat.prefab_name(prefab.hash), "900x600")

        _label(top, cat.prefab_name(prefab.hash), fg=AMBER, font=("Georgia", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        _label(top, "Click a piece on the drawing or in the list (Ctrl-click for more), then click a material.",
               fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=12)
        body = tk.Frame(top, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left = tk.Frame(body, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True)
        head = tk.Frame(left, bg=SURF)
        head.pack(fill="x", padx=6, pady=4)
        self.view_var = tk.StringVar(value=self.view.title())
        for name in ("Side", "Front", "Top", "Back"):
            tk.Radiobutton(head, text=name, value=name, variable=self.view_var, command=self._on_view, indicatoron=False,
                           bg=SURF2, fg=PARCH, selectcolor=AMBERDIM, activebackground=SURF2, relief="flat",
                           font=("Segoe UI", 8), padx=6, bd=0).pack(side="left", padx=1)
        self.hover_label = _label(head, "", fg=PARCH, bg=SURF, font=("Segoe UI", 9, "bold"))
        self.hover_label.pack(side="right")
        self.canvas = tk.Canvas(left, bg=render2d.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(None))
        self.canvas.bind("<Button-1>", lambda e: self.click_at(e.x, e.y, add=bool(e.state & 0x4)))

        right = tk.Frame(body, bg=SURF, highlightbackground=BORDER, highlightthickness=1, width=300)
        right.pack(side="left", fill="both", padx=(8, 0))
        right.pack_propagate(False)
        _label(right, "Pieces", fg=AMBER, bg=SURF, font=("Georgia", 10, "bold")).pack(anchor="w", padx=6, pady=(6, 0))
        lb = tk.Frame(right, bg=SURF)
        lb.pack(fill="both", expand=True, padx=6)
        self.list = tk.Listbox(lb, bg=SURF, fg=PARCH, selectbackground=AMBERDIM, selectforeground="#ffd080",
                               relief="flat", highlightthickness=0, font=("Segoe UI", 9), activestyle="none",
                               selectmode="extended", exportselection=False, height=8)
        sb = _mk_scrollbar(lb, self.list.yview)
        sb.pack(side="right", fill="y")
        self.list.config(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        self.list.bind("<<ListboxSelect>>", lambda e: self._from_list())
        btns = tk.Frame(right, bg=SURF)
        btns.pack(fill="x", padx=6, pady=2)
        _btn(btns, "All pieces", self.select_all, font=("Segoe UI", 8), pady=1, padx=6).pack(side="left")
        _btn(btns, "None", lambda: self.select(set()), font=("Segoe UI", 8), pady=1, padx=6).pack(side="left", padx=4)
        _label(right, "Material", fg=AMBER, bg=SURF, font=("Georgia", 10, "bold")).pack(anchor="w", padx=6, pady=(6, 0))
        self.palette = MaterialPalette(right, tab, self.apply_material, self._name_material)
        self.palette.unknown = self._unknown_materials()
        self.palette.fill()
        self.palette.frame.pack(fill="both", expand=True)
        foot = tk.Frame(top, bg=BG)
        foot.pack(fill="x", padx=12, pady=(0, 10))
        _btn(foot, "Done", top.destroy, "primary", font=("Segoe UI", 9, "bold"), pady=4, padx=14).pack(side="right")
        _label(foot, "Changes go straight into your string.", fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        self._fill_list()
        _finish_dark_window(top)

    # ---- state ---------------------------------------------------------------------------------
    def _material_of(self, entity):
        p = self.prefab
        m = edits.get_material(p, self.tab.cat) if entity == WHOLE_ITEM else edits.get_piece_material(p, entity, self.tab.cat)
        if m is None:
            part = next((q for q in (self.tab.vis.parts(p.hash) if self.tab.vis else []) if q.entity == entity), None)
            m = part.material if part else None
        return m

    def _unknown_materials(self):
        seen = {self._material_of(e) for e in self._order}
        return sorted(m for m in seen if m and not self.tab.cat.knows_material(m))

    def _fill_list(self):
        self.list.delete(0, "end")
        for e in self._order:
            m = self._material_of(e)
            self.list.insert("end", "%s   ·  %s" % (self.names[e], self.tab.cat.material_short(m) if m else "—"))
        for i, e in enumerate(self._order):
            if e in self.selected:
                self.list.selection_set(i)

    def select(self, entities):
        self.selected = set(entities)
        self.list.selection_clear(0, "end")
        for i, e in enumerate(self._order):
            if e in self.selected:
                self.list.selection_set(i)
        ms = {self._material_of(e) for e in self.selected}
        self.palette.current = ms.pop() if len(ms) == 1 else None
        self.palette.fill()
        self.redraw()

    def select_all(self):
        self.select(h for h, _ in self.pieces)

    def _from_list(self):
        self.select(self._order[i] for i in self.list.curselection())

    def _entity_at(self, q):
        if q is None:
            return None
        if q.entity in self.names and q.entity != WHOLE_ITEM:
            return q.entity
        return WHOLE_ITEM if self.own else None

    def click_at(self, x, y, add=False):
        e = self._entity_at(render2d.pick(self._polys, x, y))
        if e is None:
            if not add:
                self.select(set())
            return
        self.select(self.selected ^ {e} if add else {e})

    def apply_material(self, material_h):
        cat, p, ss = self.tab.cat, self.prefab, self.tab.ss
        if not self.selected:
            return
        for e in self.selected:
            if e == WHOLE_ITEM:
                edits.set_material(ss, p, material_h, cat)
            else:
                edits.set_piece_material(ss, p, e, material_h, cat)
        self.tab.dirty = True
        self.tab.refresh()
        self._fill_list()
        self.redraw()

    def _name_material(self, h):
        name = simpledialog.askstring("Name this material", "This string uses material #%d, which the String Builder "
                                      "doesn't know (it may come from a mod). What is it called?" % h, parent=self.top)
        if name and name.strip():
            self.tab.name_material(h, name.strip())
            self.palette.fill()
            self._fill_list()

    # ---- drawing -------------------------------------------------------------------------------
    def _on_view(self):
        self.view = self.view_var.get().lower()
        self.redraw()

    def _alone(self):
        p = self.prefab  # the same lists, so edits show; children left off so the pieces are what you see
        return Prefab(p.hash, p.pos, p.rot, 1.0, p.components, p.embeds, [])

    def redraw(self):
        c = self.canvas
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        hl = set(self.selected) | ({self.hover} if self.hover is not None else set())
        if WHOLE_ITEM in hl:
            hl |= {q.entity for q in (self.tab.vis.parts(self.prefab.hash) if self.tab.vis else [])
                   if q.entity not in dict(self.pieces)}
        alone = self._alone()
        img, self._polys = render2d.render(alone, self.tab.cat, self.tab.vis, self.view, w, h, selected=alone,
                                           highlight=hl or {-1}, margin=30)
        for q in self._polys:
            q.prefab = alone
        c.delete("all")
        if img is not None:
            self._photo = ImageTk.PhotoImage(img)
            c.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            for q in self._polys:
                c.create_polygon(*[v for pt in q.points for v in pt], fill=q.color, outline="#000")

    def _set_hover(self, e):
        if e != self.hover:
            self.hover = e
            self.hover_label.config(text=self.names.get(e, "") if e is not None else "")
            self.redraw()

    def _motion(self, ev):
        self._set_hover(self._entity_at(render2d.pick(self._polys, ev.x, ev.y)))


class DockPicker:
    """What a dock holds: search the item types, pick one and an amount."""
    QUICK = (1, 10, 100, 999)

    def __init__(self, tab, prefab, dock_h):
        self.tab, self.prefab, self.dock_h = tab, prefab, dock_h
        cat = tab.cat
        top = self.top = _window(tab, "Dock contents", "420x520")
        _label(top, cat.embed_name(prefab.hash, dock_h), fg=AMBER, font=("Georgia", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        _label(top, "on " + cat.prefab_name(prefab.hash), fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=12)
        self.q = tk.StringVar()
        e = _entry(top, self.q)
        e.pack(fill="x", padx=12, pady=(8, 4))
        self.q.trace_add("write", lambda *_: self.fill())
        box = tk.Frame(top, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True, padx=12)
        self.list = tk.Listbox(box, bg=SURF, fg=PARCH, selectbackground=AMBERDIM, selectforeground="#ffd080",
                               relief="flat", highlightthickness=0, font=("Segoe UI", 10), activestyle="none",
                               exportselection=False)
        sb = _mk_scrollbar(box, self.list.yview)
        sb.pack(side="right", fill="y")
        self.list.config(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        self.list.bind("<Double-Button-1>", lambda ev: self.apply())
        self.list.bind("<Return>", lambda ev: self.apply())
        e.bind("<Down>", lambda ev: (self.list.focus_set(), self.list.selection_set(0)))
        e.bind("<Return>", lambda ev: self.apply())
        self.count = _label(top, "", fg=MUTED, font=("Segoe UI", 8))
        self.count.pack(anchor="w", padx=12)
        amt = tk.Frame(top, bg=BG)
        amt.pack(fill="x", padx=12, pady=6)
        _label(amt, "Amount", fg=MUTED).pack(side="left")
        held = edits.get_dock(prefab, dock_h, cat)
        self.qty = tk.StringVar(value=str(held[1]) if held else "1")
        _entry(amt, self.qty, width=8).pack(side="left", padx=6)
        for n in self.QUICK:
            _btn(amt, str(n), lambda n=n: self.qty.set(str(n)), font=("Segoe UI", 8), pady=1, padx=6).pack(side="left", padx=1)
        btns = tk.Frame(top, bg=BG)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        _btn(btns, "Fill dock", self.apply, "primary", font=("Segoe UI", 9, "bold"), pady=4, padx=12).pack(side="left")
        _btn(btns, "Empty it", self.empty, font=("Segoe UI", 9), pady=4, padx=10).pack(side="left", padx=6)
        _btn(btns, "Cancel", top.destroy, font=("Segoe UI", 9), pady=4, padx=10).pack(side="right")
        self.shown = []
        self.fill()
        if held:
            self.choose(cat.item_type_name(held[0]))
        e.focus_set()
        _finish_dark_window(top)

    def fill(self):
        words = self.q.get().lower().split()
        self.shown = [(h, n) for h, n in self.tab.cat.item_types() if all(w in n.lower() for w in words)]
        self.list.delete(0, "end")
        for _h, n in self.shown:
            self.list.insert("end", n)
        if self.shown:
            self.list.selection_set(0)
        self.count.config(text="%d item types" % len(self.shown) + ("" if self.tab.cat.live else
                          "  ·  from the addon's list; connect to use the server's own"))

    def choose(self, name):
        for i, (_h, n) in enumerate(self.shown):
            if n == name:
                self.list.selection_clear(0, "end")
                self.list.selection_set(i)
                self.list.see(i)
                return True
        return False

    def apply(self):
        sel = self.list.curselection()
        if not sel:
            return
        self.tab.select_slot(self.prefab, self.dock_h)
        self.tab.dock_type_var.set(self.shown[sel[0]][1])
        self.tab.dock_qty_var.set(self.qty.get())
        if self.tab._apply_dock():
            self.top.destroy()

    def empty(self):
        self.tab.select_slot(self.prefab, self.dock_h)
        self.tab._empty_dock()
        self.top.destroy()
