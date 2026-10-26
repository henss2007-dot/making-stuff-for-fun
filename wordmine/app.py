"""The WordMine desktop window (Tkinter).

Flow: pick a region over the text -> it is read automatically whenever it
changes -> hover a word on screen (or in the window) to see reading, meaning
and grammar -> one key saves it to your word list with the sentence and a
screenshot -> send the list to Anki or export it whenever you like.
"""

from __future__ import annotations

import datetime as dt
import html
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Optional

from PIL import Image

from . import ai
from . import config as cfgmod
from .anki import AnkiConnect, AnkiError
from .capture import RegionSelector, changed, fingerprint, grab, grab_game_and_region
from .dictionary import Dictionary
from .grammar import GrammarHit, analyze
from .hover import HoverMap, Span, describe
from .ocr import WordBox, get_engine, is_vertical
from .store import Store
from .tokenizer import Token, clean_lang, clean_ocr_text, sentences_of, tagger_dictionary, tokenize, unique

LANGS = [
    ("ja", "Japanese"), ("en", "English"), ("zh", "Chinese (simplified)"),
    ("zh-tw", "Chinese (traditional)"), ("ko", "Korean"), ("de", "German"),
    ("fr", "French"), ("es", "Spanish"), ("it", "Italian"), ("pt", "Portuguese"),
    ("ru", "Russian"), ("nl", "Dutch"), ("pl", "Polish"), ("sv", "Swedish"),
    ("tr", "Turkish"), ("vi", "Vietnamese"), ("th", "Thai"), ("other", "Other (type a Tesseract code)…"),
]
MODES = [("game", "Game"), ("vn", "Visual novel"), ("manga", "Manga / comics"), ("book", "Book / article")]
# Presets applied when you switch mode. Any setting can still be changed in Settings.
MODE_PRESETS = {
    "game": {"orientation": "horizontal", "context": "sentence", "screenshot": "full"},
    "vn": {"orientation": "horizontal", "context": "full", "screenshot": "full"},
    "manga": {"orientation": "auto", "context": "sentence", "screenshot": "region"},
    "book": {"orientation": "horizontal", "context": "sentence", "screenshot": "off"},
}
MODE_HINTS = {
    "game": "Game: select the dialogue box once; it is read whenever the text changes. Saved words get a screenshot of the whole game screen.",
    "vn": "Visual novel: the text box is read when it changes; cards keep the full line and a screenshot of the scene. Using Textractor? Turn on Clipboard.",
    "manga": "Manga: press the Snip hotkey and drag over a bubble. Vertical text is handled; cards get the bubble as the screenshot.",
    "book": "Book: select the page area (or copy text with Clipboard on). Cards keep the sentence the word came from.",
}
ORIENTATIONS = [("auto", "Auto"), ("horizontal", "Horizontal"), ("vertical", "Vertical")]
CONTEXTS = [("sentence", "Sentence with the word"), ("full", "Everything captured"), ("none", "No context")]
SCREENSHOTS = [("off", "No screenshot"), ("region", "Text box / bubble only"), ("full", "Whole screen")]
AI_CHECKS = [("off", "Off"), ("ambiguous", "Ambiguous words only"), ("always", "Every word")]
HOVER_MODIFIERS = [("", "Whenever the mouse rests on a word"), ("alt", "Only while holding Alt"), ("ctrl", "Only while holding Ctrl"), ("shift", "Only while holding Shift")]
ENGINES = [("tesseract", "Tesseract (any language)"), ("manga_ocr", "manga-ocr (Japanese, best quality)")]
STATUS_LABELS = {"new": "new", "learning": "learning", "known": "known"}


def strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


class Choice(ttk.Combobox):
    """Read-only combobox backed by (value, label) pairs."""

    def __init__(self, master, pairs, var: tk.StringVar, width=18, **kw):
        self.pairs = pairs
        self.var = var
        self._label = tk.StringVar()
        super().__init__(master, textvariable=self._label, state="readonly", width=width,
                         values=[lbl for _, lbl in pairs], **kw)
        self._sync_from_var()
        self.bind("<<ComboboxSelected>>", self._on_pick)
        var.trace_add("write", lambda *_: self._sync_from_var())

    def _sync_from_var(self):
        for v, lbl in self.pairs:
            if v == self.var.get():
                if self._label.get() != lbl:
                    self._label.set(lbl)
                return
        self._label.set(self.var.get())

    def _on_pick(self, _e=None):
        for v, lbl in self.pairs:
            if lbl == self._label.get():
                if self.var.get() != v:
                    self.var.set(v)
                return


class Hint:
    """Small hover help on a widget."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        try:
            self.tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(self.tip, text=self.text, justify="left", bg="#fff8dc", relief="solid", borderwidth=1,
                 wraplength=360, padx=6, pady=3).pack()
        self.tip.geometry(f"+{x}+{y}")

    def _hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Tooltip:
    """The on-screen word popup: reading, meaning, grammar, and a Save button."""

    def __init__(self, root: tk.Tk, on_save: Callable[[], None], on_edit: Callable[[], None]):
        self.root = root
        self.win: Optional[tk.Toplevel] = None
        self.key = None
        self.on_save, self.on_edit = on_save, on_edit
        self._labels: list[tk.Widget] = []

    def visible(self) -> bool:
        return self.win is not None

    def contains(self, x: int, y: int) -> bool:
        if not self.win:
            return False
        try:
            wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
            return wx <= x <= wx + self.win.winfo_width() and wy <= y <= wy + self.win.winfo_height()
        except tk.TclError:
            return False

    def overlaps(self, region: Optional[dict]) -> bool:
        """Does the popup cover part of the capture region? (It would show up in the OCR.)"""
        if not self.win or not region:
            return False
        try:
            wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
            ww, wh = self.win.winfo_width(), self.win.winfo_height()
        except tk.TclError:
            return False
        return (wx < region["left"] + region["width"] and wx + ww > region["left"]
                and wy < region["top"] + region["height"] and wy + wh > region["top"])

    def show(self, key, lines: list[tuple[str, str]], x: int, y: int, hint: str, avoid: Optional[tuple] = None, can_save: bool = True):
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            try:
                self.win.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.frame = tk.Frame(self.win, bg="#1f2430", padx=10, pady=8, highlightthickness=1, highlightbackground="#555")
            self.frame.pack()
            self.body = tk.Frame(self.frame, bg="#1f2430")
            self.body.pack(anchor="w")
            btns = tk.Frame(self.frame, bg="#1f2430")
            btns.pack(anchor="w", pady=(6, 0))
            self.save_btn = tk.Button(btns, text="+ Save", command=self.on_save, bg="#3c8dbc", fg="white", relief="flat", padx=8, cursor="hand2")
            self.save_btn.pack(side="left")
            tk.Button(btns, text="Edit…", command=self.on_edit, bg="#444", fg="white", relief="flat", padx=8, cursor="hand2").pack(side="left", padx=(6, 0))
            self.hint = tk.Label(btns, text="", bg="#1f2430", fg="#999", font=("TkDefaultFont", 8))
            self.hint.pack(side="left", padx=(10, 0))
        if key != self.key:
            self.key = key
            for w in self._labels:
                w.destroy()
            self._labels = []
            big = ("Yu Gothic UI", 15, "bold") if sys.platform == "win32" else ("TkDefaultFont", 14, "bold")
            for i, (title, body) in enumerate(lines[:4]):
                lt = tk.Label(self.body, text=title, bg="#1f2430", fg="#ffd479" if i == 0 else "#9ecbff",
                              font=big if i == 0 else ("TkDefaultFont", 10, "bold"), justify="left", anchor="w", wraplength=420)
                lt.pack(anchor="w", pady=(6 if i else 0, 0))
                self._labels.append(lt)
                if body:
                    lb = tk.Label(self.body, text=body, bg="#1f2430", fg="white", justify="left", anchor="w", wraplength=420)
                    lb.pack(anchor="w")
                    self._labels.append(lb)
            self.hint.configure(text=hint)
            self.save_btn.configure(state="normal" if can_save else "disabled", text="+ Save" if can_save else "Saved")
            self.win.update_idletasks()
            self._place(x, y, avoid)

    def _place(self, x: int, y: int, avoid: Optional[tuple]):
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        px, py = x + 18, y + 22
        if avoid and px < avoid[2] and px + w > avoid[0] and py < avoid[3] and py + h > avoid[1]:
            py = int(avoid[1]) - h - 8  # above the text region so we don't cover it
            if py < 0:
                py = int(avoid[3]) + 8
        px = max(0, min(px, sw - w))
        py = max(0, min(py, sh - h))
        self.win.geometry(f"+{px}+{py}")

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None
            self.key = None
            self._labels = []


class Capture:
    """Everything we know about the last captured text."""

    def __init__(self, raw: str, lang: str, tokens_all: list[Token], hits: list[GrammarHit], boxes: list[WordBox],
                 origin: Optional[tuple[int, int]], crop: Optional[Image.Image], full: Optional[Image.Image], source: str):
        self.raw = raw
        self.lang = lang
        self.cleaned = clean_ocr_text(raw, clean_lang(lang))
        self.sentences = sentences_of(self.cleaned, lang)
        self.tokens_all = tokens_all
        self.tokens = unique(tokens_all)
        self.hits = hits
        self.boxes = boxes
        self.origin = origin
        self.crop, self.full = crop, full
        self.source = source
        self.hover = HoverMap(self.cleaned, self.sentences, tokens_all, hits, boxes, origin) if boxes and origin else None
        self.window_map = HoverMap(self.cleaned, self.sentences, tokens_all, hits, [], (0, 0))  # offsets only


class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.store = Store()
        self.anki = AnkiConnect(cfg["anki_connect_url"], cfg["deck"], cfg["note_type"],
                                {"grammar": cfg["note_type_grammar"], "sentence": cfg["note_type_sentence"]})
        self.dictionary = Dictionary(cfg, load_jmdict=False)  # the offline index is built in the background below
        self.engine = None
        self.engine_lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.cap: Optional[Capture] = None
        self.saved_count = 0
        self._auto_prev: Optional[bytes] = None
        self._auto_done: Optional[bytes] = None
        self._selecting = False
        self._pending_capture: Optional[tuple] = None
        self._clip_last: Optional[str] = None
        self._preview_photo = None
        self._anki_warned = False
        self._prefetch_stop: Optional[threading.Event] = None
        self._fetching: set[str] = set()
        self.hovered: Optional[Token] = None
        self._hover_seen = 0.0
        self._win_tip_key = None
        self._modifier_down = False
        self._prev_lang = cfg["lang"]

        self.root = tk.Tk()
        self.root.title("WordMine")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        style = ttk.Style(self.root)
        try:
            if sys.platform == "win32":
                style.theme_use("vista")
        except tk.TclError:
            pass
        self.tooltip = Tooltip(self.root, self.save_hovered, self.edit_hovered)
        self._build_vars()
        self._build_ui()
        self._apply_topmost()
        self._setup_hotkeys()
        self.root.after(80, self._pump)
        self.root.after(600, self._auto_tick)
        self.root.after(500, self._clipboard_tick)
        self.root.after(100, self._hover_tick)
        if self.cfg.get("region"):
            self.status(f"Region remembered. Reading starts when the text changes; hover a word to see it. {self.cfg['hotkey_select_region']} picks a new region.")
        else:
            self.status("Step 1: click '1. Select region' and drag a box over the text in your game, manga or book.")
        threading.Thread(target=self._startup_checks, daemon=True).start()
        self._load_jmdict_bg()

    # ------------------------------------------------------------------ setup
    def _build_vars(self):
        c = self.cfg
        self.v_mode = tk.StringVar(value=c["mode"])
        self.v_lang = tk.StringVar(value=c["lang"])
        self.v_hover = tk.BooleanVar(value=c["hover_mode"])
        self.v_auto = tk.BooleanVar(value=c["auto"])
        self.v_clip = tk.BooleanVar(value=c["watch_clipboard"])
        self.v_hide_known = tk.BooleanVar(value=c["hide_known"])
        self.v_topmost = tk.BooleanVar(value=c["stay_on_top"])
        self.v_autosend = tk.BooleanVar(value=c["anki_auto_send"])

        def bind(var, key, after=None):
            def cb(*_):
                val = var.get()
                if self.cfg.get(key) != val:
                    self.cfg[key] = val
                    cfgmod.save(self.cfg)
                    if after:
                        after(val)
            var.trace_add("write", cb)

        bind(self.v_mode, "mode", self._on_mode)
        bind(self.v_lang, "lang", self._on_lang)
        bind(self.v_hover, "hover_mode", lambda v: (self.tooltip.hide() if not v else None))
        bind(self.v_auto, "auto", self._on_auto)
        bind(self.v_clip, "watch_clipboard", self._on_clip)
        bind(self.v_hide_known, "hide_known", lambda _v: self.refresh_words())
        bind(self.v_topmost, "stay_on_top", lambda _v: self._apply_topmost())
        bind(self.v_autosend, "anki_auto_send")

    def _build_ui(self):
        root = self.root
        pad = {"padx": 3, "pady": 3}
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=6, pady=(6, 2))
        b = ttk.Button(bar, text="1. Select region", command=self.select_region)
        b.pack(side="left", **pad)
        Hint(b, f"Drag a box over the game's text box / the page. Remembered between sessions.\nHotkey {self.cfg['hotkey_select_region']}")
        b = ttk.Button(bar, text="Read now", command=self.capture)
        b.pack(side="left", **pad)
        Hint(b, f"Read the region right now.\nHotkey {self.cfg['hotkey_capture']}")
        b = ttk.Button(bar, text="Snip", command=self.snip)
        b.pack(side="left", **pad)
        Hint(b, f"Drag over any text (a manga bubble, a menu) and read it once.\nHotkey {self.cfg['hotkey_snip']}")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        cb = ttk.Checkbutton(bar, text="Hover", variable=self.v_hover)
        cb.pack(side="left", **pad)
        Hint(cb, f"Move the mouse over a word on the game screen to see its reading and meaning.\n{self.cfg['hotkey_add_hovered']} saves the word you are pointing at.")
        cb = ttk.Checkbutton(bar, text="Auto", variable=self.v_auto)
        cb.pack(side="left", **pad)
        Hint(cb, "Read the region again whenever its text changes, so you just play.")
        cb = ttk.Checkbutton(bar, text="Clipboard", variable=self.v_clip)
        cb.pack(side="left", **pad)
        Hint(cb, "Also read any text you copy (Textractor / Agent texthookers, Kindle, browsers).")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(bar, text="Mode").pack(side="left")
        Choice(bar, MODES, self.v_mode, width=14).pack(side="left", **pad)
        ttk.Label(bar, text="Language").pack(side="left")
        Choice(bar, LANGS, self.v_lang, width=18).pack(side="left", **pad)
        b = ttk.Button(bar, text="Settings…", command=self.open_settings)
        b.pack(side="right", **pad)
        Hint(b, "Screenshot and sentence choices, Anki deck, dictionaries, AI, hotkeys.")

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(2, 0))
        self._build_read_tab()
        self._build_words_tab()
        self._build_grammar_tab()
        self._build_list_tab()
        self._build_help_tab()

        self.status_var = tk.StringVar()
        ttk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

    def _build_read_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  Read  ")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(6, 0))
        ttk.Label(top, text="Captured text — hover a word for its meaning, double-click to save it. Fix OCR mistakes here and press Re-parse.").pack(side="left", anchor="w")
        self.preview = ttk.Label(tab, relief="sunken", anchor="center")
        self.preview.pack(fill="x", pady=4)
        font = ("Yu Gothic UI", 14) if sys.platform == "win32" else ("TkDefaultFont", 13)
        self.text = tk.Text(tab, height=6, wrap="word", font=font, padx=8, pady=6, spacing2=4, cursor="arrow")
        self.text.pack(fill="both", expand=True)
        self.text.tag_configure("word", background="#fff3c4")
        self.text.tag_configure("known", background="")
        try:
            self.text.tag_configure("grammar", underline=True, underlinefg="#3c8dbc")
        except tk.TclError:  # older Tk without underlinefg
            self.text.tag_configure("grammar", underline=True)
        self.text.bind("<Motion>", self._text_motion)
        self.text.bind("<Leave>", lambda _e: self._hide_window_tip())
        self.text.bind("<Double-1>", self._text_double_click)
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Re-parse", command=self.reparse).pack(side="left", padx=3)
        b = ttk.Button(row, text="Save sentence", command=self.save_sentence)
        b.pack(side="left", padx=3)
        Hint(b, "Save the whole captured text (or the part you selected) as a sentence card, with screenshot.")
        b = ttk.Button(row, text="Explain with AI", command=self.explain_ai)
        b.pack(side="left", padx=3)
        Hint(b, "Translation and a grammar breakdown of every part of the sentence (needs an API key, see Settings).")
        ttk.Button(row, text="Open image / PDF…", command=self.open_file).pack(side="right", padx=3)

    def _build_words_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  Words  ")
        cols = ("word", "reading", "pos", "note", "sentence")
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for col, title, width in (("word", "Word", 120), ("reading", "Reading", 110), ("pos", "Type", 70),
                                  ("note", "Also possible", 160), ("sentence", "Sentence", 330)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=(col == "sentence"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("known", foreground="#999")
        self.tree.tag_configure("ambiguous", foreground="#b25c00")
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Return>", lambda _e: self.save_selected())
        self.tree.bind("<Delete>", lambda _e: self.mark_known_selected())
        self.tree.bind("<Control-a>", lambda _e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        b = ttk.Button(row, text="Save selected", command=self.save_selected)
        b.pack(side="left", padx=3)
        Hint(b, "Add the selected words to your word list (Enter). Ctrl/Shift-click to select several.")
        ttk.Button(row, text="Edit & save…", command=self.edit_selected).pack(side="left", padx=3)
        b = ttk.Button(row, text="Merge", command=self.merge_selected)
        b.pack(side="left", padx=3)
        Hint(b, "Join neighbouring pieces into one word (魔法 + 少女 -> 魔法少女).")
        b = ttk.Button(row, text="Mark known", command=self.mark_known_selected)
        b.pack(side="left", padx=3)
        Hint(b, "Hide words you already know (Delete key).")
        ttk.Checkbutton(row, text="Hide known words", variable=self.v_hide_known).pack(side="left", padx=12)
        b = ttk.Button(row, text="Import known words from Anki", command=self.sync_known)
        b.pack(side="right", padx=3)
        Hint(b, "Treat every word already in your Anki deck as known.")

    def _build_grammar_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  Grammar  ")
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("pattern", "meaning", "level", "text")
        self.gtree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for col, title, width in (("pattern", "Grammar", 180), ("meaning", "Meaning", 330), ("level", "JLPT", 50), ("text", "In the text", 220)):
            self.gtree.heading(col, text=title)
            self.gtree.column(col, width=width, stretch=(col == "meaning"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.gtree.yview)
        self.gtree.configure(yscrollcommand=sb.set)
        self.gtree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.gtree.tag_configure("form", foreground="#555")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        b = ttk.Button(row, text="Save grammar card", command=self.save_grammar_selected)
        b.pack(side="left", padx=3)
        Hint(b, "Save the selected grammar point with this sentence as the example.")
        b = ttk.Button(row, text="Explain sentence with AI", command=self.explain_ai)
        b.pack(side="left", padx=3)
        Hint(b, "Full breakdown of the sentence by Claude (needs an API key, see Settings).")
        ttk.Label(row, text="Grey rows explain verb/adjective forms; the others are grammar patterns.", foreground="#666").pack(side="right", padx=6)

    def _build_list_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  My words  ")
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("word", "reading", "meaning", "sentence", "source", "status", "anki", "added")
        self.ltree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for col, title, width in (("word", "Word", 130), ("reading", "Reading", 90), ("meaning", "Meaning", 220), ("sentence", "Sentence", 220),
                                  ("source", "Source", 90), ("status", "Status", 60), ("anki", "Anki", 40), ("added", "Added", 110)):
            self.ltree.heading(col, text=title)
            self.ltree.column(col, width=width, stretch=col in ("meaning", "sentence"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.ltree.yview)
        self.ltree.configure(yscrollcommand=sb.set)
        self.ltree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.ltree.tag_configure("known", foreground="#999")
        self.ltree.tag_configure("grammar", foreground="#3c6e9c")
        self.ltree.tag_configure("sentence", foreground="#6a4c93")
        self.ltree.bind("<Double-1>", lambda _e: self.edit_record())
        self.ltree.bind("<Delete>", lambda _e: self.delete_records())
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        b = ttk.Button(row, text="Send to Anki", command=self.send_to_anki)
        b.pack(side="left", padx=3)
        Hint(b, "Create cards in Anki for everything not sent yet (Anki must be open with AnkiConnect).")
        mb = ttk.Menubutton(row, text="Export…")
        menu = tk.Menu(mb, tearoff=0)
        menu.add_command(label="Anki import file (TSV)…", command=lambda: self.export("tsv"))
        menu.add_command(label="Spreadsheet (CSV)…", command=lambda: self.export("csv"))
        menu.add_command(label="Copy as plain list", command=lambda: self.export("copy"))
        menu.add_command(label="Open data folder", command=self.open_folder)
        mb.configure(menu=menu)
        mb.pack(side="left", padx=3)
        Hint(mb, "Get your words out: a TSV Anki imports directly, a CSV for spreadsheets, or plain text for anywhere else.")
        cb = ttk.Checkbutton(row, text="Also send new words to Anki automatically", variable=self.v_autosend)
        cb.pack(side="left", padx=(12, 3))
        Hint(cb, "Off: words collect here until you press 'Send to Anki' (or export). On: each save also creates the card right away when Anki is open.")
        ttk.Label(row, text="Status:").pack(side="left", padx=(12, 2))
        for st in ("new", "learning", "known"):
            ttk.Button(row, text=st, width=8, command=lambda s=st: self.set_status(s)).pack(side="left", padx=1)
        ttk.Button(row, text="Delete", command=self.delete_records).pack(side="right", padx=3)
        b = ttk.Button(row, text="Show screenshot", command=self.show_record_image)
        b.pack(side="right", padx=3)
        self.list_summary = ttk.Label(tab, text="", foreground="#666")
        self.list_summary.pack(anchor="w", padx=3)
        self.refresh_list()

    def _build_help_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  Help  ")
        c = self.cfg
        text = tk.Text(tab, wrap="word", padx=10, pady=8, relief="flat", height=18)
        text.pack(fill="both", expand=True, pady=(6, 0))
        text.insert("end", "How to use WordMine\n\n", ("h",))
        text.insert("end",
            "1.  Start your game / manga reader / book in a window (not exclusive fullscreen).\n"
            "2.  Pick the Mode and Language at the top.\n"
            f"3.  Click '1. Select region' (or press {c['hotkey_select_region']}) and drag over the text box. "
            "With Auto on, the text is read every time it changes.\n"
            "4.  Hover a word on the game screen: its reading and meaning pop up. "
            f"Click '+ Save' or press {c['hotkey_add_hovered']} to keep it, with the sentence and a screenshot.\n"
            "    The Read tab shows the same text with the same hover; the Words tab lists every word; "
            "the Grammar tab explains patterns like 〜ている or 〜なければならない.\n"
            "5.  'My words' is your list. Send it to Anki, export a TSV/CSV, or copy it as text.\n\n")
        text.insert("end", "Hotkeys\n\n", ("h",))
        text.insert("end", f"{c['hotkey_select_region']}   select region        {c['hotkey_capture']}   read now\n"
                           f"{c['hotkey_snip']}   snip (read anything once)        {c['hotkey_toggle_auto']}   toggle Auto\n"
                           f"{c['hotkey_add_hovered']}   save the word under the mouse\n"
                           "Enter = save selected words, Delete = mark known, double-click = edit.  Change hotkeys in Settings → Hotkeys.\n\n")
        text.insert("end", "Manga: use Snip on each bubble. Visual novels: with Textractor, turn on Clipboard.  Books: select the page area, "
                           "or copy text with Clipboard on.\n\n")
        text.tag_configure("h", font=("TkDefaultFont", 12, "bold"))
        text.configure(state="disabled")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Run setup check", command=self.run_checks).pack(side="left", padx=3)
        ttk.Button(row, text="Open data folder", command=self.open_folder).pack(side="left", padx=3)
        ttk.Checkbutton(row, text="Keep this window on top", variable=self.v_topmost).pack(side="right", padx=3)

    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.v_topmost.get()))
        except tk.TclError:
            pass

    def _setup_hotkeys(self):
        try:
            from pynput import keyboard
        except Exception as exc:  # pragma: no cover - platform dependent
            self.status(f"Global hotkeys unavailable ({exc}); use the buttons.")
            return
        mapping = {
            self.cfg["hotkey_capture"]: lambda: self.q.put(("hotkey", "capture")),
            self.cfg["hotkey_select_region"]: lambda: self.q.put(("hotkey", "select")),
            self.cfg["hotkey_toggle_auto"]: lambda: self.q.put(("hotkey", "auto")),
            self.cfg["hotkey_snip"]: lambda: self.q.put(("hotkey", "snip")),
            self.cfg["hotkey_add_hovered"]: lambda: self.q.put(("hotkey", "save_hovered")),
        }
        try:
            self._hotkeys = keyboard.GlobalHotKeys(mapping)
            self._hotkeys.daemon = True
            self._hotkeys.start()
        except Exception as exc:  # pragma: no cover
            self.status(f"Could not register hotkeys: {exc}")
        # Track the hover modifier key (Alt/Ctrl/Shift) so the popup can be
        # limited to "only while holding it".
        try:
            mods = {
                "alt": {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, getattr(keyboard.Key, "alt_gr", keyboard.Key.alt)},
                "ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
                "shift": {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
            }

            def on_press(key):
                if key in mods.get(self.cfg.get("hover_modifier", ""), set()):
                    self._modifier_down = True

            def on_release(key):
                if key in mods.get(self.cfg.get("hover_modifier", ""), set()):
                    self._modifier_down = False

            self._mod_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._mod_listener.daemon = True
            self._mod_listener.start()
        except Exception:  # pragma: no cover
            pass

    def _load_jmdict_bg(self):
        if not self.cfg.get("jmdict_path"):
            return
        self.status("Building the offline dictionary index (one time, can take a minute)… online lookups are used meanwhile.")
        self.dictionary.load_jmdict_async(lambda err: self.q.put(("status", err or "Offline dictionary ready: hover answers are instant now.")))

    def _startup_checks(self):
        notes = []
        if self.cfg["lang"] == "ja":
            try:
                notes.append(f"Japanese analyser: {tagger_dictionary()}")
            except RuntimeError as exc:
                notes.append(str(exc))
            notes.append("offline dictionary configured" if self.cfg.get("jmdict_path") else "online dictionary (jisho.org)")
        notes.append("Anki connected" if self.anki.available() else "Anki not open (words go to your list)")
        self.q.put(("status_append", " | ".join(notes)))

    # --------------------------------------------------------------- settings
    def _on_mode(self, mode: str):
        for key, val in MODE_PRESETS.get(mode, {}).items():
            self.cfg[key] = val
        cfgmod.save(self.cfg)
        self.status(MODE_HINTS.get(mode, ""))

    def _on_lang(self, lang: str):
        if lang == "other":
            code = simpledialog.askstring(
                "Language", "Tesseract language code for the text, e.g. ind (Indonesian), ara (Arabic), hin (Hindi), "
                "ell (Greek), ces (Czech), ukr (Ukrainian).\nThe matching language pack must be installed with Tesseract.",
                parent=self.root)
            code = (code or "").strip() or getattr(self, "_prev_lang", "ja")
            self.cfg["lang"] = code
            if code != getattr(self, "_prev_lang", ""):
                self.cfg["tesseract_lang"] = code if code not in dict(LANGS) else ""
            cfgmod.save(self.cfg)
            # Tk does not fire a variable's trace from inside that trace, so update the box afterwards.
            self.root.after(0, lambda: self.v_lang.set(code))
            lang = code
        elif self.cfg.get("tesseract_lang") == self._prev_lang and self._prev_lang not in dict(LANGS):
            self.cfg["tesseract_lang"] = ""  # leaving a typed code: drop the override it set
            cfgmod.save(self.cfg)
        self._prev_lang = lang
        with self.engine_lock:
            self.engine = None  # rebuilt with the new language on next OCR
        self.refresh_words()

    def _on_clip(self, on: bool):
        if on:
            try:
                self._clip_last = self.root.clipboard_get()  # ignore what is already there
            except tk.TclError:
                self._clip_last = ""
            self.status("Clipboard watching on: copy text in the game, texthooker or reader and it appears here.")

    def _on_auto(self, on: bool):
        if on and not self.cfg.get("region"):
            self.status("Auto is on; select a region and it will be read whenever the text changes.")
        self._auto_prev = self._auto_done = None

    def apply_settings(self):
        """Called after the Settings dialog changes cfg."""
        c = self.cfg
        self.anki.url, self.anki.deck = c["anki_connect_url"], c["deck"]
        self.anki.model_names = {"word": c["note_type"], "grammar": c["note_type_grammar"], "sentence": c["note_type_sentence"]}
        self.anki.reset()
        with self.engine_lock:
            self.engine = None
        self.dictionary.save()
        self.dictionary = Dictionary(c, load_jmdict=False)
        self._load_jmdict_bg()
        self._apply_topmost()
        if self.v_autosend.get() != bool(c["anki_auto_send"]):
            self.v_autosend.set(bool(c["anki_auto_send"]))
        if self.v_topmost.get() != bool(c["stay_on_top"]):
            self.v_topmost.set(bool(c["stay_on_top"]))
        self.refresh_words()

    def open_settings(self):
        SettingsDialog(self)

    # ----------------------------------------------------------------- actions
    def status(self, msg: str):
        self.status_var.set(msg)

    def ui(self, fn: Callable[[], None]) -> None:
        """Run fn on the UI thread (safe to call from worker threads)."""
        self.q.put(("call", fn))

    def select_region(self):
        self.tooltip.hide()
        self._selecting = True
        try:
            region = RegionSelector(self.root).select()
        finally:
            self._selecting = False
        if region:
            self.cfg["region"] = region
            cfgmod.save(self.cfg)
            self._auto_prev = self._auto_done = None
            self.status("Region set. Reading it now; afterwards it is re-read whenever the text changes (Auto)." if self.v_auto.get()
                        else f"Region set. Press 'Read now' ({self.cfg['hotkey_capture']}) whenever new text appears.")
            self.capture()

    def snip(self):
        """Drag over a speech bubble or paragraph and read it right away."""
        self.tooltip.hide()
        self._selecting = True
        try:
            region = RegionSelector(self.root).select()
        finally:
            self._selecting = False
        if region:
            self.capture(region=region, source="snip")

    def capture(self, region: Optional[dict] = None, source: str = "screen"):
        region = region or self.cfg.get("region")
        if not region:
            self.status("No region yet: click '1. Select region' and drag over the text.")
            return
        if self.busy:
            if source != "screen" or self._pending_capture is None:
                self._pending_capture = (region, source)  # read it as soon as the current read finishes
            self.status("Still reading the previous text; this one is queued.")
            return
        try:
            full, crop = grab_game_and_region(region)
        except Exception as exc:
            self.status(f"Screen capture failed: {exc}")
            return
        self._ocr_async(crop, full, source, origin=(region["left"], region["top"]))

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open a page image or PDF",
            filetypes=[("Images / PDF", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".pdf"):
                img = self._pdf_page(path)
                if img is None:
                    return
            else:
                img = Image.open(path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("WordMine", f"Could not open {path}:\n{exc}")
            return
        self._ocr_async(img, img, source=os.path.basename(path), origin=None)

    def _pdf_page(self, path: str) -> Optional[Image.Image]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            messagebox.showinfo("WordMine", "PDF support needs PyMuPDF:  pip install pymupdf")
            return None
        doc = fitz.open(path)
        page_no = simpledialog.askinteger("WordMine", f"Page number (1-{doc.page_count}):", minvalue=1, maxvalue=doc.page_count, parent=self.root)
        if not page_no:
            return None
        pix = doc[page_no - 1].get_pixmap(matrix=fitz.Matrix(2, 2))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def _ocr_async(self, crop: Image.Image, full: Image.Image, source: str, origin: Optional[tuple[int, int]]):
        self.busy = True
        self.status("Reading text…")
        threading.Thread(target=self._ocr_job, args=(crop, full, source, origin), daemon=True).start()

    def _ocr_job(self, crop, full, source, origin):
        try:
            with self.engine_lock:
                if self.engine is None:
                    self.engine = get_engine(self.cfg)
                    for w in getattr(self.engine, "warnings", []):
                        self.q.put(("status", w))
                engine = self.engine
            vertical = is_vertical(crop, self.cfg["orientation"])
            text, boxes = engine.recognize_boxes(crop, vertical=vertical)
            cap = self._analyze(text, boxes, origin, crop, full, source)
            self.q.put(("capture", cap))
        except Exception as exc:
            self.q.put(("error", f"Reading failed: {exc}"))
        finally:
            self.busy = False
            self.q.put(("ocr_done",))

    def _analyze(self, text, boxes, origin, crop, full, source) -> Capture:
        lang = self.cfg["lang"]
        tokens_all = tokenize(text, lang, dedupe=False)
        cleaned = clean_ocr_text(text, clean_lang(lang))
        hits = analyze(cleaned, lang)
        return Capture(text, lang, tokens_all, hits, boxes, origin, crop, full, source)

    def reparse(self):
        text = self.text.get("1.0", "end").strip()
        if not text or self.busy:
            return
        self.busy = True
        cap = self.cap

        def job():
            try:
                new = self._analyze(text, [], None, cap.crop if cap else None, cap.full if cap else None, cap.source if cap else "edited")
                self.q.put(("capture", new))
            except Exception as exc:
                self.q.put(("error", f"Could not parse text: {exc}"))
            finally:
                self.busy = False
        threading.Thread(target=job, daemon=True).start()

    # ------------------------------------------------------------- saving
    def _selected_tokens(self) -> list[Token]:
        if not self.cap:
            return []
        out = []
        for iid in self.tree.selection():
            try:
                out.append(self.cap.tokens[int(iid)])
            except (ValueError, IndexError):
                pass
        return out

    def save_selected(self):
        tokens = self._selected_tokens()
        if not tokens:
            self.status("Select one or more words first (Ctrl/Shift-click for several), then Save.")
            return
        self.save_tokens(tokens)

    def save_hovered(self):
        if self.hovered is not None:
            self.save_tokens([self.hovered])
        else:
            self.status("Point at a word first, then save it.")

    def edit_hovered(self):
        if self.hovered is not None:
            self.tooltip.hide()
            EditDialog(self, self.hovered)

    def save_tokens(self, tokens: list[Token], overrides: Optional[dict] = None):
        fresh = [t for t in tokens if overrides or not self.store.has(t.lemma)]
        if not fresh:
            self.status(f"{tokens[0].lemma} is already in your list (My words tab).")
            return
        self.status(f"Saving {', '.join(t.lemma for t in fresh[:3])}{'…' if len(fresh) > 3 else ''}")
        threading.Thread(target=self._save_job, args=(fresh, overrides), daemon=True).start()

    def _card_context(self, token: Optional[Token]) -> str:
        mode = self.cfg["context"]
        if mode == "none" or not self.cap:
            return ""
        if mode == "full" or token is None:
            return self.cap.cleaned
        return token.sentence

    def _card_image(self) -> Optional[Image.Image]:
        if not self.cap or self.cfg["screenshot"] == "off":
            return None
        return self.cap.crop if self.cfg["screenshot"] == "region" else self.cap.full

    def _save_image(self, img: Optional[Image.Image], label: str) -> str:
        if img is None:
            return ""
        folder = cfgmod.APP_DIR / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w぀-鿿]+", "_", label)[:30] or "shot"
        path = folder / (dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{safe}.png")
        try:
            img.save(path)
        except OSError as exc:
            self.q.put(("status", f"Could not save screenshot: {exc}"))
            return ""
        return str(path)

    def _save_job(self, tokens: list[Token], overrides: Optional[dict]):
        """Look up, optionally AI-check, then save each token. Runs off the UI thread."""
        lang = self.cfg["lang"]
        cap = self.cap
        for token in tokens:
            word, reading, meaning = token.lemma, token.reading, ""
            note_lines: list[str] = []
            if overrides:
                word = overrides.get("word", word)
                reading = overrides.get("reading", reading)
                meaning = overrides.get("meaning", meaning)
            if self.cfg["lookup"] and not meaning:
                entry = self.dictionary.get(word, lang, reading_hint=reading, pos=token.pos)
                meaning = entry.meaning
                if not reading:
                    reading = entry.reading
                if lang == "ja" and not entry.matched_context and entry.readings:
                    note_lines.append("dictionary readings: " + ", ".join(entry.readings))
            ai_mode = self.cfg["ai_check"]
            if ai_mode == "always" or (ai_mode == "ambiguous" and token.ambiguous):
                try:
                    verdict = ai.check(token.sentence, token.surface, reading, token.alt_readings,
                                       token.alt_lemmas, lang, self.cfg["ai_model"], self.cfg["anthropic_api_key"])
                except ai.AIError as exc:
                    self.q.put(("status", str(exc)))
                    verdict = None
                if verdict:
                    if verdict.reading and lang == "ja":
                        reading = verdict.reading
                    if verdict.dictionary_form and not overrides:
                        word = verdict.dictionary_form
                    if verdict.meaning:
                        meaning = f"<b>{html.escape(verdict.meaning)}</b>" + (f"<br>{meaning}" if meaning else "")
                    if verdict.note:
                        note_lines.append(verdict.note)
            if note_lines:
                meaning = (meaning + "<br>" if meaning else "") + "<i>" + html.escape(" · ".join(note_lines)) + "</i>"
            sentence = overrides["sentence"] if overrides and "sentence" in overrides else self._card_context(token)
            source = self.cfg["source_name"] or (cap.source if cap else "")
            image_path = self._save_image(self._card_image(), word)
            rec = self.store.add(word, reading, meaning, sentence, source, image=image_path, lang=lang, surface=token.surface)
            if token.lemma != word:
                self.store.mark_known(token.lemma)
            self._maybe_send(rec)
            self.q.put(("saved", rec))
        self.dictionary.save()

    def _maybe_send(self, rec: dict):
        if not self.cfg["anki_auto_send"]:
            return
        try:
            self.anki.add_record(rec)
            self.store.update(rec["id"], anki=True)
        except AnkiError as exc:
            self.q.put(("anki_error", str(exc)))

    def save_grammar_selected(self):
        if not self.cap:
            return
        sel = self.gtree.selection()
        if not sel:
            self.status("Select a grammar row first.")
            return
        hits = [self.cap.hits[int(i)] for i in sel if int(i) < len(self.cap.hits)]

        def job():
            for h in hits:
                if self.store.has(h.name, kind="grammar", sentence=h.sentence):
                    self.q.put(("status", f"{h.name} with this sentence is already in your list."))
                    continue
                meaning = html.escape(h.meaning) + (f" <i>({h.level})</i>" if h.level else "")
                rec = self.store.add(h.name, "", meaning, h.sentence, self.cfg["source_name"] or self.cap.source,
                                     image=self._save_image(self._card_image(), h.name), lang=self.cfg["lang"], kind="grammar", notes=h.text)
                self._maybe_send(rec)
                self.q.put(("saved", rec))
        threading.Thread(target=job, daemon=True).start()

    def save_sentence(self, translation: str = "", notes: str = ""):
        if not self.cap:
            self.status("Nothing captured yet.")
            return
        try:
            sentence = self.text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            sentence = ""
        sentence = sentence or self.cap.cleaned
        if not notes:
            notes = ", ".join(dict.fromkeys(h.name for h in self.cap.hits if h.category == "pattern" and h.sentence in sentence))

        def job():
            rec = self.store.add(sentence, "", translation, sentence, self.cfg["source_name"] or self.cap.source,
                                 image=self._save_image(self._card_image(), "sentence"), lang=self.cfg["lang"], kind="sentence", notes=notes)
            self._maybe_send(rec)
            self.q.put(("saved", rec))
        threading.Thread(target=job, daemon=True).start()

    def explain_ai(self):
        if not self.cap:
            self.status("Capture some text first.")
            return
        try:
            sentence = self.text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            sentence = ""
        if not sentence:
            sentence = self.cap.sentences[0] if len(self.cap.sentences) == 1 else self.cap.cleaned
        ExplainDialog(self, sentence)

    def edit_selected(self):
        tokens = self._selected_tokens()
        if not tokens:
            self.status("Select a word to edit.")
            return
        EditDialog(self, tokens[0])

    def merge_selected(self):
        """Join adjacent tokens into one word (e.g. 魔法/少女 -> 魔法少女)."""
        if not self.cap:
            return
        iids = sorted((int(i) for i in self.tree.selection()), key=int)
        if len(iids) < 2:
            self.status("Select two or more neighbouring words to merge.")
            return
        parts = [self.cap.tokens[i] for i in iids]
        if len({p.sentence for p in parts}) != 1:
            self.status("Merge only works for words from the same sentence.")
            return
        surface = "".join(p.surface for p in parts)
        if surface not in parts[0].sentence:
            self.status("Those words are not next to each other in the sentence.")
            return
        lemma = "".join(p.surface for p in parts[:-1]) + parts[-1].lemma
        reading = "".join(p.reading or p.surface for p in parts) if self.cfg["lang"] == "ja" else ""
        merged = Token(surface=surface, lemma=lemma, reading=reading, pos=parts[-1].pos, sentence=parts[0].sentence,
                       sent_index=parts[0].sent_index, start=parts[0].start, end=parts[-1].end)
        self.cap.tokens[iids[0]] = merged
        for i in reversed(iids[1:]):
            del self.cap.tokens[i]
        self.refresh_words()
        self.tree.selection_set(str(iids[0]))
        self.status(f"Merged into {lemma}")

    def mark_known_selected(self):
        tokens = self._selected_tokens()
        if tokens:
            self.store.mark_known(*(t.lemma for t in tokens))
            self.refresh_words()
            self.status(f"Marked {len(tokens)} word(s) as known; they stay hidden from now on.")

    def sync_known(self):
        self.status("Reading your Anki deck…")

        def job():
            try:
                words = self.anki.known_words()
                self.store.mark_known(*words)
                self.q.put(("status", f"Imported {len(words)} words from deck '{self.anki.deck}' as known."))
                self.q.put(("refresh",))
            except AnkiError as exc:
                self.q.put(("status", str(exc)))
        threading.Thread(target=job, daemon=True).start()

    # --------------------------------------------------------- word list tab
    def _selected_records(self) -> list[dict]:
        out = []
        for iid in self.ltree.selection():
            rec = self.store.get(int(iid))
            if rec:
                out.append(rec)
        return out

    def send_to_anki(self):
        pending = self.store.unsent()
        if not pending:
            self.status("Everything in your list is already in Anki.")
            return
        self.status(f"Sending {len(pending)} card(s) to Anki…")

        def job():
            sent = 0
            for rec in pending:
                try:
                    self.anki.add_record(rec)
                    self.store.update(rec["id"], anki=True)
                    sent += 1
                except AnkiError as exc:
                    msg = str(exc)
                    if "duplicate" in msg:
                        self.store.update(rec["id"], anki=True)  # already there: fine
                        continue
                    self.q.put(("status", f"Stopped after {sent} card(s): {msg}"))
                    self.q.put(("refresh_list",))
                    return
            self.q.put(("status", f"Sent {sent} card(s) to deck '{self.anki.deck}'."))
            self.q.put(("refresh_list",))
        threading.Thread(target=job, daemon=True).start()

    def export(self, kind: str):
        recs = self._selected_records() or self.store.words
        if not recs:
            self.status("Your list is empty.")
            return
        if kind == "copy":
            text = self.store.export_text(recs)
            self._clip_last = text  # so clipboard watching does not read our own export
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status(f"Copied {len(recs)} word(s) to the clipboard.")
            return
        ext = ".tsv" if kind == "tsv" else ".csv"
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=f"wordmine_words{ext}",
                                            filetypes=[("Anki import (TSV)", "*.tsv")] if kind == "tsv" else [("CSV", "*.csv")])
        if not path:
            return
        if kind == "csv":
            n = self.store.export_csv(path, recs)
            self.status(f"Exported {n} entries to {path}")
            return
        base = os.path.splitext(path)[0]
        media = f"{base}_media"
        done = []
        for k, suffix, note_type in (("word", "", self.cfg["note_type"]), ("grammar", "_grammar", self.cfg["note_type_grammar"]),
                                     ("sentence", "_sentences", self.cfg["note_type_sentence"])):
            if not any(r.get("kind", "word") == k for r in recs):
                continue
            target = path if k == "word" else f"{base}{suffix}.tsv"
            n = self.store.export_tsv(target, recs, kind=k, note_type=note_type, deck=self.cfg["deck"], media_dir=media)
            done.append(f"{n} {k}{'s' if n != 1 else ''} → {os.path.basename(target)}")
        hint = (" In Anki: press 'Send to Anki' once first (it creates the WordMine note types), then File > Import this file;"
                f" copy the images from {os.path.basename(media)} into Anki's collection.media folder." if any(r.get("image") for r in recs)
                else " In Anki: press 'Send to Anki' once first (it creates the WordMine note types), then File > Import this file.")
        self.status("Exported " + ", ".join(done) + "." + hint)

    def set_status(self, status: str):
        for rec in self._selected_records():
            self.store.update(rec["id"], status=status)
        self.refresh_list()

    def delete_records(self):
        recs = self._selected_records()
        if recs and messagebox.askyesno("WordMine", f"Remove {len(recs)} entr{'y' if len(recs) == 1 else 'ies'} from your list?"):
            self.store.remove(*(r["id"] for r in recs))
            self.refresh_list()

    def show_record_image(self):
        recs = self._selected_records()
        if recs and recs[0].get("image") and os.path.exists(recs[0]["image"]):
            self._open_path(recs[0]["image"])
        else:
            self.status("No screenshot stored for this entry.")

    def edit_record(self):
        recs = self._selected_records()
        if recs:
            RecordDialog(self, recs[0])

    def open_folder(self):
        self._open_path(str(cfgmod.APP_DIR))

    def _open_path(self, path: str):
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            self.status(f"{path} ({exc})")

    def run_checks(self):
        from .diagnostics import run_checks
        win = tk.Toplevel(self.root)
        win.title("Setup check")
        win.geometry("760x420")
        txt = tk.Text(win, wrap="word", padx=8, pady=8)
        txt.pack(fill="both", expand=True)
        txt.insert("end", "Checking…\n")
        txt.tag_configure("OK", foreground="#2e7d32")
        txt.tag_configure("FAIL", foreground="#c62828")
        txt.tag_configure("note", foreground="#555")

        def job():
            results = run_checks(self.cfg)
            self.ui(lambda: show(results))

        def show(results):
            if not win.winfo_exists():
                return
            txt.delete("1.0", "end")
            for status, msg in results:
                txt.insert("end", f"{status:5s} ", (status,))
                txt.insert("end", msg + "\n\n")
        threading.Thread(target=job, daemon=True).start()

    # ------------------------------------------------------------------ loops
    def _pump(self):
        try:
            while True:
                self._handle(self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "capture":
            self._show_capture(msg[1])
        elif kind == "saved":
            rec = msg[1]
            self.saved_count += 1
            self.refresh_words()
            self.refresh_list()
            self._refresh_text_tags()
            where = "and sent to Anki" if rec.get("anki") else "to your list"
            self.status(f"Saved {rec['word']} {where}. {self.saved_count} this session.")
            if self.tooltip.visible():
                self.tooltip.key = None  # re-render so the button shows 'Saved'
        elif kind == "anki_error":
            if not self._anki_warned:
                self._anki_warned = True
                messagebox.showwarning("WordMine", msg[1] + "\n\nYour words are safe in the list (My words tab); use 'Send to Anki' later.")
        elif kind == "status":
            self.status(msg[1])
        elif kind == "status_append":
            self.status((self.status_var.get() + "   ·   " + msg[1]).strip(" ·"))
        elif kind == "error":
            self.status(msg[1])
        elif kind == "refresh":
            self.refresh_words()
        elif kind == "refresh_list":
            self.refresh_list()
        elif kind == "meaning":
            pass  # a prefetch finished; the hover tick re-renders when it looks again
        elif kind == "call":
            try:
                msg[1]()
            except tk.TclError:
                pass  # the window it targeted is gone
        elif kind == "ocr_done":
            if self._pending_capture and not self.busy:
                region, source = self._pending_capture
                self._pending_capture = None
                self.capture(region=region, source=source)
        elif kind == "hotkey":
            {"capture": self.capture, "select": self.select_region, "snip": self.snip, "save_hovered": self.save_hovered,
             "auto": lambda: self.v_auto.set(not self.v_auto.get())}[msg[1]]()

    def _show_capture(self, cap: Capture):
        self.cap = cap
        self.hovered = None
        self.tooltip.hide()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", cap.cleaned)
        self._refresh_text_tags()
        self._show_preview(cap.crop)
        self.refresh_words()
        self.refresh_grammar()
        self._maybe_save_shot(cap.source)
        self._start_prefetch(cap)
        n_new = sum(1 for t in cap.tokens if t.lemma not in self.store.known)
        if cap.tokens:
            self.status(f"{len(cap.tokens)} words ({n_new} new), {sum(1 for h in cap.hits if h.category == 'pattern')} grammar points."
                        + ("  Hover a word on screen or in the Read tab." if cap.hover else "  Hover words in the Read tab."))
        else:
            self.status("No words found. Make the region tighter around the text, or check the language setting.")

    def _start_prefetch(self, cap: Capture):
        if self._prefetch_stop:
            self._prefetch_stop.set()
        if not self.cfg["lookup"]:
            return
        self._prefetch_stop = threading.Event()
        unknown = [(t.lemma, t.reading) for t in cap.tokens if t.lemma not in self.store.known]
        known = [(t.lemma, t.reading) for t in cap.tokens if t.lemma in self.store.known]
        self.dictionary.prefetch(unknown + known, cap.lang, on_each=lambda w, e: self.q.put(("meaning", w)), stop=self._prefetch_stop)

    def _meaning_text(self, token: Token) -> str:
        entry = self.dictionary.cached(token.lemma, self.cfg["lang"], token.reading)
        if entry is None:
            if self.cfg["lookup"]:
                key = f"{token.lemma}|{token.reading}"
                if key not in self._fetching:
                    self._fetching.add(key)

                    def job():
                        try:
                            self.dictionary.get(token.lemma, self.cfg["lang"], token.reading, token.pos)
                        finally:
                            self._fetching.discard(key)
                    threading.Thread(target=job, daemon=True).start()
                return "looking up…"
            return ""
        return strip_html(entry.meaning) if entry.meaning else "(no dictionary entry)"

    def _hover_tick(self):
        delay = 90
        try:
            modifier_ok = not self.cfg.get("hover_modifier") or self._modifier_down or self.tooltip.visible()
            if self.v_hover.get() and self.cap and self.cap.hover and modifier_ok:
                x, y = self.root.winfo_pointerxy()
                if self.tooltip.contains(x, y):
                    self._hover_seen = time.time()
                else:
                    spans = self.cap.hover.at(x, y)
                    if spans:
                        self._show_spans(spans, x, y, self.cap.hover)
                    elif (self.tooltip.visible() and self.tooltip.key and self.tooltip.key[0] == "screen"
                          and time.time() - self._hover_seen > float(self.cfg.get("hover_hide_delay", 0.4))):
                        self.tooltip.hide()
                        self.hovered = None
            elif self.tooltip.visible() and self.tooltip.key and self.tooltip.key[0] == "screen":
                self.tooltip.hide()
        except tk.TclError:
            pass
        self.root.after(delay, self._hover_tick)

    def _show_spans(self, spans: list[Span], x: int, y: int, hmap: HoverMap, where: str = "screen"):
        words = [s for s in spans if s.kind == "word" and s.token]
        token = min((s.token for s in words), key=lambda t: t.end - t.start) if words else None
        self.hovered = token
        self._hover_seen = time.time()
        key = (where, token.lemma if token else None, tuple((s.start, s.end) for s in spans))
        lines = describe(spans, meaning_for=self._meaning_text)
        if token and token.lemma in self.store.known and lines:
            lines[0] = (lines[0][0] + "   ✓ known", lines[0][1])
        looking = any(body == "looking up…" for _, body in lines)
        if looking:
            key = key + (time.time() // 0.5,)  # re-render until the meaning arrives
        can_save = token is not None and not self.store.has(token.lemma)
        avoid = None
        if where == "screen" and self.cfg.get("region"):
            r = self.cfg["region"]
            avoid = (r["left"], r["top"], r["left"] + r["width"], r["top"] + r["height"])
        self.tooltip.show(key, lines, x, y, f"{self.cfg['hotkey_add_hovered']} saves" if where == "screen" else "double-click saves",
                          avoid=avoid, can_save=can_save)

    def _text_motion(self, event):
        if not self.cap:
            return
        try:
            index = self.text.index(f"@{event.x},{event.y}")
            offset = self.text.count("1.0", index, "chars")[0] if self.text.count("1.0", index, "chars") else 0
        except tk.TclError:
            return
        spans = self.cap.window_map.spans_at_offset(offset)
        if spans and self.text.bbox(index):
            self._show_spans(spans, self.root.winfo_pointerx(), self.root.winfo_pointery(), self.cap.window_map, where="window")
        elif self.tooltip.visible() and self.tooltip.key and self.tooltip.key[0] == "window":
            self._hide_window_tip()

    def _hide_window_tip(self):
        if self.tooltip.visible() and self.tooltip.key and self.tooltip.key[0] == "window":
            self.tooltip.hide()
            self.hovered = None

    def _text_double_click(self, event):
        if not self.cap:
            return "break"
        index = self.text.index(f"@{event.x},{event.y}")
        offset = self.text.count("1.0", index, "chars")
        offset = offset[0] if offset else 0
        words = [s.token for s in self.cap.window_map.spans_at_offset(offset) if s.kind == "word" and s.token]
        if words:
            self.save_tokens([min(words, key=lambda t: t.end - t.start)])
        return "break"

    def _refresh_text_tags(self):
        if not self.cap:
            return
        for tag in ("word", "grammar"):
            self.text.tag_remove(tag, "1.0", "end")
        for s in self.cap.window_map.spans:
            if s.kind == "word" and s.token and s.token.lemma not in self.store.known:
                self.text.tag_add("word", f"1.0+{s.start}c", f"1.0+{s.end}c")
            elif s.kind == "grammar" and s.grammar is not None and s.grammar.category == "pattern":
                self.text.tag_add("grammar", f"1.0+{s.start}c", f"1.0+{s.end}c")

    def _auto_tick(self):
        interval = max(0.3, float(self.cfg.get("auto_interval", 1.0)))
        region = self.cfg.get("region")
        snipping = self.cap is not None and self.cap.source == "snip"  # a snipped bubble stays until you read the region again
        if (self.v_auto.get() and region and not self.busy and not self._selecting and not snipping
                and not self.tooltip.overlaps(region)):
            try:
                fp = fingerprint(grab(region))
                stable = not changed(self._auto_prev, fp)
                if stable and changed(self._auto_done, fp):
                    self._auto_done = fp
                    self.tooltip.hide()  # the text changed: whatever the popup showed is gone
                    self.hovered = None
                    self.capture(source="screen")
                self._auto_prev = fp
            except Exception as exc:
                self.status(f"Auto capture error: {exc}")
        self.root.after(int(interval * 1000), self._auto_tick)

    def _clipboard_tick(self):
        if self.v_clip.get() and not self.busy:
            try:
                text = self.root.clipboard_get()
            except tk.TclError:
                text = None
            if self._clip_last is None:
                self._clip_last = text or ""  # ignore whatever was already there when watching started
            elif text and text != self._clip_last and len(text) < 4000:
                self._clip_last = text
                self.busy = True
                threading.Thread(target=self._clip_job, args=(text,), daemon=True).start()
        self.root.after(500, self._clipboard_tick)

    def _clip_job(self, text):
        try:
            self.q.put(("capture", self._analyze(text, [], None, None, None, "clipboard")))
        except Exception as exc:
            self.q.put(("error", f"Could not parse clipboard text: {exc}"))
        finally:
            self.busy = False

    # ------------------------------------------------------------------- view
    def refresh_words(self):
        self.tree.delete(*self.tree.get_children())
        if not self.cap:
            return
        hide = self.v_hide_known.get()
        for i, t in enumerate(self.cap.tokens):
            known = t.lemma in self.store.known
            if known and hide:
                continue
            notes = []
            if t.alt_readings:
                notes.append("reading: " + "/".join(t.alt_readings))
            if t.alt_lemmas:
                notes.append("or " + "/".join(t.alt_lemmas))
            if t.alt_splits:
                notes.append("split: " + " | ".join(t.alt_splits))
            tags = ("known",) if known else (("ambiguous",) if t.ambiguous else ())
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(t.lemma, t.reading, t.pos, "; ".join(notes), t.sentence))

    def refresh_grammar(self):
        self.gtree.delete(*self.gtree.get_children())
        if not self.cap:
            return
        for i, h in enumerate(self.cap.hits):
            self.gtree.insert("", "end", iid=str(i), tags=(h.category,), values=(h.name, h.meaning, h.level, h.text if h.category == "pattern" else h.sentence))

    def refresh_list(self):
        self.ltree.delete(*self.ltree.get_children())
        for rec in reversed(self.store.words):
            tags = (rec.get("kind", "word"),) if rec.get("kind", "word") != "word" else (("known",) if rec.get("status") == "known" else ())
            self.ltree.insert("", "end", iid=str(rec["id"]), tags=tags, values=(
                rec["word"], rec.get("reading", ""), strip_html(rec.get("meaning", "")).replace("\n", " / ")[:120],
                rec.get("sentence", "")[:120], rec.get("source", ""), rec.get("status", "new"), "✓" if rec.get("anki") else "",
                rec.get("added", "")[:16].replace("T", " ")))
        n = len(self.store.words)
        unsent = len(self.store.unsent())
        self.list_summary.configure(text=f"{n} entr{'y' if n == 1 else 'ies'}, {unsent} not yet in Anki. Double-click to edit; select rows to export only those.")

    def _show_preview(self, img: Optional[Image.Image]):
        if img is None:
            self.preview.configure(image="", text="")
            self._preview_photo = None
            return
        try:
            from PIL import ImageTk
            thumb = img.copy()
            thumb.thumbnail((860, 90))
            self._preview_photo = ImageTk.PhotoImage(thumb)
            self.preview.configure(image=self._preview_photo, text="")
        except Exception:
            self.preview.configure(image="", text="(no preview)")

    def _maybe_save_shot(self, source: str):
        if not self.cfg["save_screenshots"] or not self.cap:
            return
        img = self._card_image() or self.cap.full
        if img is not None:
            self._save_image(img, source)

    def on_close(self):
        cfgmod.save(self.cfg)
        self.dictionary.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app.root)
        self.app = app
        c = app.cfg
        self.title("WordMine settings")
        self.transient(app.root)
        self.resizable(False, False)
        pad = {"padx": 6, "pady": 3}
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.vars: dict[str, tk.Variable] = {}

        def var(key, kind=tk.StringVar):
            v = kind(value=c.get(key, ""))
            self.vars[key] = v
            return v

        def section(title):
            f = ttk.Frame(nb, padding=8)
            nb.add(f, text=title)
            return f

        f = section("Cards")
        ttk.Label(f, text="Sentence on the card").grid(row=0, column=0, sticky="e", **pad)
        Choice(f, CONTEXTS, var("context"), width=24).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(f, text="Screenshot on the card").grid(row=1, column=0, sticky="e", **pad)
        Choice(f, SCREENSHOTS, var("screenshot"), width=24).grid(row=1, column=1, sticky="w", **pad)
        ttk.Checkbutton(f, text="Also save a screenshot file for every capture", variable=var("save_screenshots", tk.BooleanVar)).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(f, text="Source (game / book title)").grid(row=3, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("source_name"), width=28).grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(f, text="Changing the Mode at the top resets the first two to that mode's presets.", foreground="#666").grid(row=4, column=0, columnspan=2, sticky="w", **pad)

        f = section("Anki")
        ttk.Label(f, text="Deck").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("deck"), width=28).grid(row=0, column=1, sticky="w", **pad)
        ttk.Checkbutton(f, text="Send every saved word to Anki immediately (when Anki is open)", variable=var("anki_auto_send", tk.BooleanVar)).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        ttk.Label(f, text="Note type (words)").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("note_type"), width=28).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(f, text="Note type (grammar)").grid(row=3, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("note_type_grammar"), width=28).grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(f, text="Note type (sentences)").grid(row=4, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("note_type_sentence"), width=28).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(f, text="AnkiConnect URL").grid(row=5, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("anki_connect_url"), width=28).grid(row=5, column=1, sticky="w", **pad)

        f = section("Dictionary & AI")
        ttk.Checkbutton(f, text="Look up meanings (jisho.org / Wiktionary online, or JMdict offline)", variable=var("lookup", tk.BooleanVar)).grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(f, text="Offline JMdict file").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("jmdict_path"), width=34).grid(row=1, column=1, sticky="w", **pad)
        ttk.Button(f, text="Browse…", command=self.browse_jmdict).grid(row=1, column=2, **pad)
        ttk.Label(f, text="jmdict-eng-*.json.zip from github.com/scriptin/jmdict-simplified/releases (instant, no internet needed)", foreground="#666").grid(row=2, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(f, text="AI context check").grid(row=3, column=0, sticky="e", **pad)
        Choice(f, AI_CHECKS, var("ai_check"), width=24).grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(f, text="Model").grid(row=4, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("ai_model"), width=34).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(f, text="API key").grid(row=5, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("anthropic_api_key"), width=34, show="•").grid(row=5, column=1, sticky="w", **pad)
        ttk.Label(f, text="Leave the key empty to use the ANTHROPIC_API_KEY environment variable. Needs: pip install anthropic", foreground="#666").grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        f = section("Reading")
        ttk.Label(f, text="OCR engine").grid(row=0, column=0, sticky="e", **pad)
        Choice(f, ENGINES, var("ocr_engine"), width=30).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(f, text="Text direction").grid(row=1, column=0, sticky="e", **pad)
        Choice(f, ORIENTATIONS, var("orientation"), width=30).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(f, text="Tesseract language(s)").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("tesseract_lang"), width=32).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(f, text="e.g. jpn+eng for games mixing English; empty = from the Language box", foreground="#666").grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(f, text="Tesseract program").grid(row=4, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("tesseract_cmd"), width=32).grid(row=4, column=1, sticky="w", **pad)
        ttk.Button(f, text="Browse…", command=self.browse_tesseract).grid(row=4, column=2, **pad)
        ttk.Label(f, text="Upscale (auto / 1 / 2 / 3)").grid(row=5, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("ocr_scale"), width=10).grid(row=5, column=1, sticky="w", **pad)
        ttk.Label(f, text="Auto re-read interval (s)").grid(row=6, column=0, sticky="e", **pad)
        ttk.Entry(f, textvariable=var("auto_interval"), width=10).grid(row=6, column=1, sticky="w", **pad)
        ttk.Label(f, text="Word popup over the game").grid(row=7, column=0, sticky="e", **pad)
        Choice(f, HOVER_MODIFIERS, var("hover_modifier"), width=30).grid(row=7, column=1, sticky="w", **pad)
        ttk.Checkbutton(f, text="Keep the WordMine window on top", variable=var("stay_on_top", tk.BooleanVar)).grid(row=8, column=0, columnspan=2, sticky="w", **pad)

        f = section("Hotkeys")
        for i, (key, label) in enumerate([("hotkey_select_region", "Select region"), ("hotkey_capture", "Read now"), ("hotkey_snip", "Snip"),
                                          ("hotkey_toggle_auto", "Toggle Auto"), ("hotkey_add_hovered", "Save hovered word")]):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="e", **pad)
            ttk.Entry(f, textvariable=var(key), width=28).grid(row=i, column=1, sticky="w", **pad)
        ttk.Label(f, text="Format: <ctrl>+<alt>+c, <shift>+<f8>, … Hotkey changes apply after restarting WordMine.", foreground="#666").grid(row=6, column=0, columnspan=2, sticky="w", **pad)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Save", command=self.save).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())

    def browse_jmdict(self):
        p = filedialog.askopenfilename(title="JMdict file", filetypes=[("JMdict JSON / zip", "*.zip *.json"), ("All files", "*.*")], parent=self)
        if p:
            self.vars["jmdict_path"].set(p)

    def browse_tesseract(self):
        p = filedialog.askopenfilename(title="tesseract executable", parent=self)
        if p:
            self.vars["tesseract_cmd"].set(p)

    def save(self):
        for key, v in self.vars.items():
            val = v.get()
            if key in ("ocr_scale",):
                sval = str(val).strip()
                try:
                    val = float(sval) if sval not in ("", "auto") else "auto"
                except ValueError:
                    val = "auto"
                if isinstance(val, float) and not 0.5 <= val <= 4:
                    val = "auto"  # anything else is a typo; 0 would break reading entirely
            elif key == "auto_interval":
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = 1.0
            self.app.cfg[key] = val
        cfgmod.save(self.app.cfg)
        self.app.apply_settings()
        self.destroy()
        self.app.status("Settings saved.")


class EditDialog(tk.Toplevel):
    """Fix the word, pick between readings, trim the sentence, then save."""

    def __init__(self, app: App, token: Token):
        super().__init__(app.root)
        self.app, self.token = app, token
        self.title(f"Edit: {token.lemma}")
        self.transient(app.root)
        pad = {"padx": 6, "pady": 3}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(frm, text="Word").grid(row=0, column=0, sticky="e", **pad)
        self.v_word = tk.StringVar(value=token.lemma)
        ttk.Entry(frm, textvariable=self.v_word, width=30).grid(row=0, column=1, sticky="we", **pad)
        if token.alt_lemmas:
            ttk.Label(frm, text="also: " + ", ".join(token.alt_lemmas), foreground="#b25c00").grid(row=0, column=2, sticky="w", **pad)

        ttk.Label(frm, text="Reading").grid(row=1, column=0, sticky="e", **pad)
        self.v_reading = tk.StringVar(value=token.reading)
        readings = [token.reading] + [r for r in token.alt_readings if r != token.reading]
        ttk.Combobox(frm, textvariable=self.v_reading, values=[r for r in readings if r], width=28).grid(row=1, column=1, sticky="we", **pad)
        if token.alt_readings:
            ttk.Label(frm, text="pick the one that fits the sentence", foreground="#b25c00").grid(row=1, column=2, sticky="w", **pad)

        ttk.Label(frm, text="Meaning").grid(row=2, column=0, sticky="ne", **pad)
        self.meaning = tk.Text(frm, height=5, width=48, wrap="word")
        self.meaning.grid(row=2, column=1, columnspan=2, sticky="we", **pad)
        cached = app.dictionary.cached(token.lemma, app.cfg["lang"], token.reading)
        if cached and cached.meaning:
            self.meaning.insert("1.0", strip_html(cached.meaning))
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Button(btns, text="Look up", command=self.do_lookup).pack(side="left", **pad)
        ttk.Button(btns, text="Ask AI about this sentence", command=self.do_ai).pack(side="left", **pad)

        ttk.Label(frm, text="Sentence").grid(row=4, column=0, sticky="ne", **pad)
        self.sentence = tk.Text(frm, height=4, width=48, wrap="word")
        self.sentence.grid(row=4, column=1, columnspan=2, sticky="we", **pad)
        self.sentence.insert("1.0", app._card_context(token))

        self.info = ttk.Label(frm, text="", foreground="#555", wraplength=460, justify="left")
        self.info.grid(row=5, column=1, columnspan=2, sticky="w", **pad)
        if token.alt_splits:
            self.info.configure(text="The analyser also considered splitting this as: " + " | ".join(token.alt_splits))

        ok = ttk.Frame(frm)
        ok.grid(row=6, column=1, columnspan=2, sticky="e")
        ttk.Button(ok, text="Cancel", command=self.destroy).pack(side="right", **pad)
        ttk.Button(ok, text="Save", command=self.add).pack(side="right", **pad)
        frm.columnconfigure(1, weight=1)
        self.bind("<Escape>", lambda _e: self.destroy())

    def do_lookup(self):
        word, reading = self.v_word.get().strip(), self.v_reading.get().strip()
        self.info.configure(text="Looking up…")

        def job():
            entry = self.app.dictionary.get(word, self.app.cfg["lang"], reading_hint=reading, pos=self.token.pos)
            self.app.ui(lambda: self._set_lookup(entry))
        threading.Thread(target=job, daemon=True).start()

    def _set_lookup(self, entry):
        if not self.winfo_exists():
            return
        self.meaning.delete("1.0", "end")
        self.meaning.insert("1.0", strip_html(entry.meaning))
        if not self.v_reading.get() and entry.reading:
            self.v_reading.set(entry.reading)
        msg = "" if entry.meaning else "Nothing found (offline, or not in the dictionary)."
        if entry.readings and not entry.matched_context:
            msg = f"The dictionary lists readings {', '.join(entry.readings)}; none matched '{self.v_reading.get()}'."
        self.info.configure(text=msg)

    def do_ai(self):
        self.info.configure(text="Asking Claude…")
        t = self.token
        reading = self.v_reading.get()  # read Tk state on the UI thread, not in the worker

        def job():
            try:
                v = ai.check(t.sentence, t.surface, reading, t.alt_readings, t.alt_lemmas,
                             self.app.cfg["lang"], self.app.cfg["ai_model"], self.app.cfg["anthropic_api_key"])
                self.app.ui(lambda: self._set_ai(v))
            except ai.AIError as exc:
                self.app.ui(lambda: self.info.configure(text=str(exc)) if self.winfo_exists() else None)
        threading.Thread(target=job, daemon=True).start()

    def _set_ai(self, v):
        if not self.winfo_exists():
            return
        if v is None:
            self.info.configure(text="No answer.")
            return
        if v.reading and self.app.cfg["lang"] == "ja":
            self.v_reading.set(v.reading)
        if v.dictionary_form:
            self.v_word.set(v.dictionary_form)
        current = self.meaning.get("1.0", "end").strip()
        self.meaning.delete("1.0", "end")
        self.meaning.insert("1.0", v.meaning + ("\n" + current if current else ""))
        self.info.configure(text=(v.note or "") + ("" if v.analyser_was_right else "  (the analyser's reading was wrong here)"))

    def add(self):
        overrides = {
            "word": self.v_word.get().strip() or self.token.lemma,
            "reading": self.v_reading.get().strip(),
            "meaning": html.escape(self.meaning.get("1.0", "end").strip()).replace("\n", "<br>"),
            "sentence": self.sentence.get("1.0", "end").strip(),
        }
        self.destroy()
        self.app.save_tokens([self.token], overrides)


class RecordDialog(tk.Toplevel):
    """Edit an entry of the word list."""

    def __init__(self, app: App, rec: dict):
        super().__init__(app.root)
        self.app, self.rec = app, rec
        self.title(f"Edit: {rec['word']}")
        self.transient(app.root)
        pad = {"padx": 6, "pady": 3}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        self.vars = {}
        for i, (key, label) in enumerate([("word", "Word"), ("reading", "Reading"), ("source", "Source")]):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="e", **pad)
            v = tk.StringVar(value=rec.get(key, ""))
            self.vars[key] = v
            ttk.Entry(frm, textvariable=v, width=48).grid(row=i, column=1, sticky="we", **pad)
        ttk.Label(frm, text="Meaning").grid(row=3, column=0, sticky="ne", **pad)
        self.meaning = tk.Text(frm, height=5, width=48, wrap="word")
        self.meaning.grid(row=3, column=1, sticky="we", **pad)
        self.meaning.insert("1.0", strip_html(rec.get("meaning", "")))
        ttk.Label(frm, text="Sentence").grid(row=4, column=0, sticky="ne", **pad)
        self.sentence = tk.Text(frm, height=4, width=48, wrap="word")
        self.sentence.grid(row=4, column=1, sticky="we", **pad)
        self.sentence.insert("1.0", rec.get("sentence", ""))
        ok = ttk.Frame(frm)
        ok.grid(row=5, column=1, sticky="e")
        ttk.Button(ok, text="Cancel", command=self.destroy).pack(side="right", **pad)
        ttk.Button(ok, text="Save", command=self.save).pack(side="right", **pad)
        self.bind("<Escape>", lambda _e: self.destroy())

    def save(self):
        self.app.store.update(
            self.rec["id"], word=self.vars["word"].get().strip() or self.rec["word"], reading=self.vars["reading"].get().strip(),
            source=self.vars["source"].get().strip(), meaning=html.escape(self.meaning.get("1.0", "end").strip()).replace("\n", "<br>"),
            sentence=self.sentence.get("1.0", "end").strip(), anki=False,
        )
        self.app.refresh_list()
        self.destroy()


class ExplainDialog(tk.Toplevel):
    """AI translation + grammar breakdown of a sentence."""

    def __init__(self, app: App, sentence: str):
        super().__init__(app.root)
        self.app, self.sentence = app, sentence
        self.title("Sentence breakdown")
        self.transient(app.root)
        self.geometry("720x520")
        top = ttk.Label(self, text=sentence, wraplength=680, font=("Yu Gothic UI", 13) if sys.platform == "win32" else ("TkDefaultFont", 12))
        top.pack(anchor="w", padx=10, pady=(10, 4))
        self.translation = ttk.Label(self, text="Asking Claude…", wraplength=680, foreground="#1a5276")
        self.translation.pack(anchor="w", padx=10, pady=(0, 6))
        cols = ("text", "reading", "grammar", "explanation")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, title, width in (("text", "Part", 120), ("reading", "Reading", 90), ("grammar", "Grammar", 130), ("explanation", "Explanation", 340)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=(col == "explanation"))
        self.tree.pack(fill="both", expand=True, padx=10)
        self.detail = ttk.Label(self, text="Select a row to read its full explanation.", wraplength=680, foreground="#333", justify="left")
        self.detail.pack(anchor="w", padx=10, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._select)
        row = ttk.Frame(self)
        row.pack(fill="x", padx=10, pady=(0, 10))
        self.save_btn = ttk.Button(row, text="Save as sentence card", command=self.save_card, state="disabled")
        self.save_btn.pack(side="left")
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")
        self.breakdown = None
        threading.Thread(target=self._job, daemon=True).start()

    def _job(self):
        try:
            b = ai.explain_sentence(self.sentence, self.app.cfg["lang"], self.app.cfg["ai_model"], self.app.cfg["anthropic_api_key"])
            self.app.ui(lambda: self._show(b))
        except ai.AIError as exc:
            self.app.ui(lambda: self.translation.configure(text=str(exc)) if self.winfo_exists() else None)

    def _show(self, b):
        if not self.winfo_exists():
            return
        if b is None:
            self.translation.configure(text="No answer.")
            return
        self.breakdown = b
        self.translation.configure(text=b.translation)
        for i, p in enumerate(b.parts):
            self.tree.insert("", "end", iid=str(i), values=(p.get("text", ""), p.get("reading", ""), p.get("grammar", ""), p.get("explanation", "")))
        if b.notes:
            self.detail.configure(text=b.notes)
        self.save_btn.configure(state="normal")

    def _select(self, _e=None):
        sel = self.tree.selection()
        if sel and self.breakdown:
            p = self.breakdown.parts[int(sel[0])]
            self.detail.configure(text=f"{p.get('text', '')}  —  {p.get('role', '')}\n{p.get('explanation', '')}")

    def save_card(self):
        if self.breakdown:
            notes = "<br>".join(f"<b>{html.escape(p.get('text', ''))}</b> {html.escape(p.get('grammar', '') or p.get('role', ''))}: {html.escape(p.get('explanation', ''))}"
                                for p in self.breakdown.parts)
            self.app.save_sentence(translation=html.escape(self.breakdown.translation), notes=notes)
            self.destroy()


def main(cfg: Optional[dict] = None):
    App(cfg or cfgmod.load()).run()
