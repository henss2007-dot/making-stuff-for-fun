"""The WordMine desktop window (Tkinter)."""

from __future__ import annotations

import datetime as dt
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from PIL import Image

from . import ai
from . import config as cfgmod
from .anki import AnkiConnect, AnkiError
from .capture import RegionSelector, changed, fingerprint, grab, grab_game_and_region
from .lookup import lookup
from .ocr import get_engine, is_vertical
from .store import Store
from .tokenizer import Token, clean_ocr_text, tagger_dictionary, tokenize

LANGS = [
    ("ja", "Japanese"), ("en", "English"), ("zh", "Chinese (simplified)"),
    ("zh-tw", "Chinese (traditional)"), ("ko", "Korean"), ("de", "German"),
    ("fr", "French"), ("es", "Spanish"), ("it", "Italian"), ("pt", "Portuguese"),
    ("ru", "Russian"), ("nl", "Dutch"), ("pl", "Polish"), ("sv", "Swedish"),
    ("tr", "Turkish"), ("vi", "Vietnamese"), ("th", "Thai"),
]
MODES = [("game", "Game"), ("manga", "Manga / comics"), ("book", "Book / article")]
# Presets applied when you switch mode. Any setting can still be changed after.
MODE_PRESETS = {
    "game": {"orientation": "horizontal", "context": "full", "screenshot": "region"},
    "manga": {"orientation": "auto", "context": "sentence", "screenshot": "region"},
    "book": {"orientation": "horizontal", "context": "sentence", "screenshot": "off"},
}
ORIENTATIONS = [("auto", "Auto"), ("horizontal", "Horizontal"), ("vertical", "Vertical")]
CONTEXTS = [("sentence", "Sentence with the word"), ("full", "Everything captured"), ("none", "No context")]
SCREENSHOTS = [("off", "No screenshot"), ("region", "Text box / bubble"), ("full", "Whole screen")]
AI_CHECKS = [("off", "Off"), ("ambiguous", "Ambiguous words only"), ("always", "Every word")]


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


class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.store = Store()
        self.anki = AnkiConnect(cfg["anki_connect_url"], cfg["deck"], cfg["note_type"])
        self.engine = None
        self.engine_lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.tokens: list[Token] = []
        self.shots: dict[str, Optional[Image.Image]] = {"region": None, "full": None}
        self.last_text = ""
        self.last_source = ""
        self.added_count = 0
        self._auto_prev: Optional[bytes] = None
        self._auto_done: Optional[bytes] = None
        self._clip_last: Optional[str] = None
        self._preview_photo = None
        self._anki_warned = False

        self.root = tk.Tk()
        self.root.title("WordMine")
        self.root.geometry("820x680")
        self.root.minsize(640, 480)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build_vars()
        self._build_ui()
        self._apply_topmost()
        self._setup_hotkeys()
        self.root.after(80, self._pump)
        self.root.after(500, self._auto_tick)
        self.root.after(500, self._clipboard_tick)
        self.status("Ready. Select a region over the text, then press the capture hotkey.")
        threading.Thread(target=self._startup_checks, daemon=True).start()

    # ------------------------------------------------------------------ setup
    def _build_vars(self):
        c = self.cfg
        self.v_mode = tk.StringVar(value=c["mode"])
        self.v_lang = tk.StringVar(value=c["lang"])
        self.v_orient = tk.StringVar(value=c["orientation"])
        self.v_context = tk.StringVar(value=c["context"])
        self.v_shot = tk.StringVar(value=c["screenshot"])
        self.v_save_shots = tk.BooleanVar(value=c["save_screenshots"])
        self.v_auto = tk.BooleanVar(value=False)
        self.v_clip = tk.BooleanVar(value=c["watch_clipboard"])
        self.v_hide_known = tk.BooleanVar(value=c["hide_known"])
        self.v_lookup = tk.BooleanVar(value=c["lookup"])
        self.v_ai = tk.StringVar(value=c["ai_check"])
        self.v_deck = tk.StringVar(value=c["deck"])
        self.v_source = tk.StringVar(value=c["source_name"])
        self.v_topmost = tk.BooleanVar(value=c["stay_on_top"])

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
        bind(self.v_orient, "orientation")
        bind(self.v_context, "context")
        bind(self.v_shot, "screenshot")
        bind(self.v_save_shots, "save_screenshots")
        bind(self.v_clip, "watch_clipboard")
        bind(self.v_hide_known, "hide_known", lambda _v: self.refresh_tree())
        bind(self.v_lookup, "lookup")
        bind(self.v_ai, "ai_check")
        bind(self.v_deck, "deck", self._on_deck)
        bind(self.v_source, "source_name")
        bind(self.v_topmost, "stay_on_top", lambda _v: self._apply_topmost())

    def _build_ui(self):
        root = self.root
        pad = {"padx": 4, "pady": 3}

        # Row 0: actions
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(bar, text="Select region", command=self.select_region).pack(side="left", **pad)
        ttk.Button(bar, text="Capture", command=self.capture).pack(side="left", **pad)
        ttk.Button(bar, text="Snip", command=self.snip).pack(side="left", **pad)
        ttk.Checkbutton(bar, text="Auto (OCR when text changes)", variable=self.v_auto,
                        command=self._on_auto).pack(side="left", **pad)
        ttk.Checkbutton(bar, text="Watch clipboard", variable=self.v_clip).pack(side="left", **pad)
        ttk.Button(bar, text="Open image / PDF…", command=self.open_file).pack(side="left", **pad)
        ttk.Checkbutton(bar, text="On top", variable=self.v_topmost).pack(side="right", **pad)

        # Row 1: settings
        opts = ttk.Frame(root)
        opts.pack(fill="x", padx=6)
        ttk.Label(opts, text="Mode").grid(row=0, column=0, sticky="e", **pad)
        Choice(opts, MODES, self.v_mode, width=16).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(opts, text="Language").grid(row=0, column=2, sticky="e", **pad)
        Choice(opts, LANGS, self.v_lang, width=20).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(opts, text="Text direction").grid(row=0, column=4, sticky="e", **pad)
        Choice(opts, ORIENTATIONS, self.v_orient, width=11).grid(row=0, column=5, sticky="w", **pad)

        ttk.Label(opts, text="Card context").grid(row=1, column=0, sticky="e", **pad)
        Choice(opts, CONTEXTS, self.v_context, width=20).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(opts, text="Screenshot").grid(row=1, column=2, sticky="e", **pad)
        Choice(opts, SCREENSHOTS, self.v_shot, width=16).grid(row=1, column=3, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Also save screenshots to folder", variable=self.v_save_shots).grid(
            row=1, column=4, columnspan=2, sticky="w", **pad)

        ttk.Label(opts, text="Deck").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(opts, textvariable=self.v_deck, width=22).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(opts, text="Source (title)").grid(row=2, column=2, sticky="e", **pad)
        ttk.Entry(opts, textvariable=self.v_source, width=24).grid(row=2, column=3, sticky="w", **pad)
        ttk.Label(opts, text="AI context check").grid(row=2, column=4, sticky="e", **pad)
        Choice(opts, AI_CHECKS, self.v_ai, width=18).grid(row=2, column=5, sticky="w", **pad)

        # Captured text + preview
        mid = ttk.Frame(root)
        mid.pack(fill="x", padx=6, pady=(4, 0))
        self.preview = ttk.Label(mid, relief="sunken", anchor="center")
        self.preview.pack(side="right", padx=(6, 0))
        txt_frame = ttk.Frame(mid)
        txt_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(txt_frame, text="Captured text (edit to fix OCR mistakes, then Re-parse)").pack(anchor="w")
        self.text = tk.Text(txt_frame, height=4, wrap="word", font=("Yu Gothic UI", 12) if sys.platform == "win32" else None)
        self.text.pack(fill="both", expand=True)
        row = ttk.Frame(txt_frame)
        row.pack(fill="x")
        ttk.Button(row, text="Re-parse", command=self.reparse).pack(side="left", **pad)
        ttk.Checkbutton(row, text="Hide known words", variable=self.v_hide_known).pack(side="left", **pad)
        ttk.Checkbutton(row, text="Look up meanings online", variable=self.v_lookup).pack(side="left", **pad)

        # Candidate words
        cols = ("word", "reading", "pos", "note", "sentence")
        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        for col, title, width in (("word", "Word", 110), ("reading", "Reading", 110), ("pos", "POS", 70),
                                  ("note", "Also possible", 150), ("sentence", "Sentence", 330)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=(col == "sentence"))
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("known", foreground="#999")
        self.tree.tag_configure("ambiguous", foreground="#b25c00")
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Return>", lambda _e: self.add_selected())

        actions = ttk.Frame(root)
        actions.pack(fill="x", padx=6)
        ttk.Button(actions, text="Add selected to Anki", command=self.add_selected).pack(side="left", **pad)
        ttk.Button(actions, text="Edit & add…", command=self.edit_selected).pack(side="left", **pad)
        ttk.Button(actions, text="Merge into one word", command=self.merge_selected).pack(side="left", **pad)
        ttk.Button(actions, text="Mark known", command=self.mark_known_selected).pack(side="left", **pad)
        ttk.Button(actions, text="Import known words from Anki", command=self.sync_known).pack(side="left", **pad)
        ttk.Button(actions, text="Open data folder", command=self.open_folder).pack(side="right", **pad)

        self.status_var = tk.StringVar()
        ttk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken").pack(fill="x", side="bottom")

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
        }
        try:
            self._hotkeys = keyboard.GlobalHotKeys(mapping)
            self._hotkeys.daemon = True
            self._hotkeys.start()
        except Exception as exc:  # pragma: no cover
            self.status(f"Could not register hotkeys: {exc}")

    def _startup_checks(self):
        notes = []
        if self.cfg["lang"] == "ja":
            try:
                notes.append(f"Japanese dictionary: {tagger_dictionary()}")
            except RuntimeError as exc:
                notes.append(str(exc))
        notes.append("Anki: connected" if self.anki.available() else "Anki: not reachable (cards are still saved to mined.tsv)")
        self.q.put(("status", " | ".join(notes)))

    # --------------------------------------------------------------- settings
    def _on_mode(self, mode: str):
        for key, val in MODE_PRESETS.get(mode, {}).items():
            {"orientation": self.v_orient, "context": self.v_context, "screenshot": self.v_shot}[key].set(val)
        self.status(f"Mode: {mode}. Presets applied; tweak any setting on the right.")

    def _on_lang(self, _lang: str):
        with self.engine_lock:
            self.engine = None  # rebuilt with the new language on next OCR
        self.refresh_tree()

    def _on_deck(self, deck: str):
        self.anki.deck = deck
        self.anki._ready = False

    def _on_auto(self):
        if self.v_auto.get() and not self.cfg.get("region"):
            self.v_auto.set(False)
            self.status("Select a region first, then turn Auto on.")
            return
        self._auto_prev = self._auto_done = None
        self.status("Auto mode on: the region is OCR'd whenever its text changes." if self.v_auto.get() else "Auto mode off.")

    # ----------------------------------------------------------------- actions
    def status(self, msg: str):
        self.status_var.set(msg)

    def select_region(self):
        region = RegionSelector(self.root).select()
        if region:
            self.cfg["region"] = region
            cfgmod.save(self.cfg)
            self.status(f"Region set: {region['width']}x{region['height']} at ({region['left']}, {region['top']}). Press capture.")
            self._auto_prev = self._auto_done = None

    def snip(self):
        """Drag over a speech bubble or paragraph and OCR it right away."""
        region = RegionSelector(self.root).select()
        if region:
            self.capture(region=region, source="snip")

    def capture(self, region: Optional[dict] = None, source: str = "screen"):
        region = region or self.cfg.get("region")
        if not region:
            self.status("No region yet. Click 'Select region' (or press the select hotkey) and drag over the text.")
            return
        if self.busy:
            self.status("Still working on the previous capture…")
            return
        try:
            full, crop = grab_game_and_region(region)
        except Exception as exc:
            self.status(f"Screen capture failed: {exc}")
            return
        self._ocr_async(crop, full, source)

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
        self._ocr_async(img, img, source=os.path.basename(path))

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

    def _ocr_async(self, crop: Image.Image, full: Image.Image, source: str):
        self.busy = True
        self.status("Reading text…")
        threading.Thread(target=self._ocr_job, args=(crop, full, source), daemon=True).start()

    def _ocr_job(self, crop, full, source):
        try:
            with self.engine_lock:
                if self.engine is None:
                    self.engine = get_engine(self.cfg)
                    for w in getattr(self.engine, "warnings", []):
                        self.q.put(("status", w))
                engine = self.engine
            vertical = is_vertical(crop, self.cfg["orientation"])
            text = engine.recognize(crop, vertical=vertical)
            tokens = tokenize(text, self.cfg["lang"])
            self.q.put(("ocr", text, tokens, crop, full, source))
        except Exception as exc:
            self.q.put(("error", f"OCR failed: {exc}"))
        finally:
            self.busy = False

    def reparse(self):
        text = self.text.get("1.0", "end").strip()
        if not text:
            return
        self.busy = True
        threading.Thread(target=self._reparse_job, args=(text,), daemon=True).start()

    def _reparse_job(self, text):
        try:
            tokens = tokenize(text, self.cfg["lang"])
            self.q.put(("tokens", text, tokens))
        except Exception as exc:
            self.q.put(("error", f"Could not parse text: {exc}"))
        finally:
            self.busy = False

    def _selected_tokens(self) -> list[Token]:
        out = []
        for iid in self.tree.selection():
            try:
                out.append(self.tokens[int(iid)])
            except (ValueError, IndexError):
                pass
        return out

    def add_selected(self):
        tokens = self._selected_tokens()
        if not tokens:
            self.status("Select one or more words first (Ctrl/Shift-click for several).")
            return
        self.status(f"Adding {len(tokens)} word(s)…")
        threading.Thread(target=self._add_job, args=(tokens, None), daemon=True).start()

    def _card_context(self, token: Token) -> str:
        mode = self.cfg["context"]
        if mode == "none":
            return ""
        if mode == "full":
            return clean_ocr_text(self.last_text, self.cfg["lang"])
        return token.sentence

    def _card_image(self) -> Optional[Image.Image]:
        return self.shots.get(self.cfg["screenshot"]) if self.cfg["screenshot"] != "off" else None

    def _add_job(self, tokens: list[Token], overrides: Optional[dict]):
        """Look up, optionally AI-check, then add each token. Runs off the UI thread."""
        lang = self.cfg["lang"]
        anki_ok = True
        for token in tokens:
            word, reading, meaning = token.lemma, token.reading, ""
            note_lines: list[str] = []
            if overrides:
                word = overrides.get("word", word)
                reading = overrides.get("reading", reading)
                meaning = overrides.get("meaning", meaning)
            if self.cfg["lookup"] and not meaning:
                entry = lookup(word, lang, reading_hint=reading, pos=token.pos)
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
                        meaning = f"<b>{verdict.meaning}</b>" + (f"<br>{meaning}" if meaning else "")
                    if verdict.note:
                        note_lines.append(verdict.note)
            if note_lines:
                meaning = (meaning + "<br>" if meaning else "") + "<i>" + " · ".join(note_lines) + "</i>"
            sentence = overrides.get("sentence") if overrides and "sentence" in overrides else self._card_context(token)
            source = self.cfg["source_name"] or self.last_source
            image = self._card_image()
            self.store.log(word, reading, meaning, sentence, source)
            if anki_ok:
                try:
                    self.anki.add_note(word, reading, meaning, sentence, source, image)
                except AnkiError as exc:
                    anki_ok = False
                    self.q.put(("anki_error", str(exc)))
            self.store.mark_known(word, token.lemma)
            self.q.put(("added", token.lemma, word, anki_ok))

    def edit_selected(self):
        tokens = self._selected_tokens()
        if not tokens:
            self.status("Select a word to edit.")
            return
        EditDialog(self, tokens[0])

    def merge_selected(self):
        """Join adjacent tokens into one word (e.g. 魔法/少女 -> 魔法少女)."""
        iids = sorted((int(i) for i in self.tree.selection()), key=int)
        if len(iids) < 2:
            self.status("Select two or more neighbouring words to merge.")
            return
        parts = [self.tokens[i] for i in iids]
        if len({p.sentence for p in parts}) != 1:
            self.status("Merge only works for words from the same sentence.")
            return
        surface = "".join(p.surface for p in parts)
        if surface not in parts[0].sentence:
            self.status("Those words are not next to each other in the sentence.")
            return
        lemma = "".join(p.surface for p in parts[:-1]) + parts[-1].lemma
        reading = "".join(p.reading or p.surface for p in parts) if self.cfg["lang"] == "ja" else ""
        merged = Token(surface=surface, lemma=lemma, reading=reading, pos=parts[-1].pos, sentence=parts[0].sentence)
        self.tokens[iids[0]] = merged
        for i in reversed(iids[1:]):
            del self.tokens[i]
        self.refresh_tree()
        self.tree.selection_set(str(iids[0]))
        self.status(f"Merged into {lemma}")

    def mark_known_selected(self):
        tokens = self._selected_tokens()
        if tokens:
            self.store.mark_known(*(t.lemma for t in tokens))
            self.refresh_tree()
            self.status(f"Marked {len(tokens)} word(s) as known.")

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

    def open_folder(self):
        path = str(cfgmod.APP_DIR)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            self.status(f"Data folder: {path} ({exc})")

    # ------------------------------------------------------------------ loops
    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "ocr":
            _, text, tokens, crop, full, source = msg
            self.last_text, self.tokens, self.last_source = text, tokens, source
            self.shots = {"region": crop, "full": full}
            self.text.delete("1.0", "end")
            self.text.insert("1.0", clean_ocr_text(text, self.cfg["lang"]))
            self._show_preview(crop)
            self.refresh_tree()
            self._maybe_save_shot(source)
            self.status(f"{len(tokens)} candidate word(s) from {source}." if tokens else "No words found. Try a tighter region or higher ocr_scale.")
        elif kind == "tokens":
            _, text, tokens = msg
            self.last_text, self.tokens = text, tokens
            self.refresh_tree()
            self.status(f"{len(tokens)} candidate word(s).")
        elif kind == "added":
            _, lemma, word, anki_ok = msg
            self.added_count += 1
            self.refresh_tree()
            where = "Anki" if anki_ok else "mined.tsv (Anki unreachable)"
            self.status(f"Added {word} to {where}. {self.added_count} card(s) this session.")
        elif kind == "anki_error":
            if not self._anki_warned:
                self._anki_warned = True
                messagebox.showwarning("WordMine", msg[1] + "\n\nWords are still being saved to mined.tsv, which Anki can import later.")
        elif kind == "status":
            self.status(msg[1])
        elif kind == "error":
            self.status(msg[1])
        elif kind == "refresh":
            self.refresh_tree()
        elif kind == "hotkey":
            {"capture": self.capture, "select": self.select_region, "snip": self.snip,
             "auto": lambda: (self.v_auto.set(not self.v_auto.get()), self._on_auto())}[msg[1]]()

    def _auto_tick(self):
        interval = max(0.3, float(self.cfg.get("auto_interval", 1.0)))
        if self.v_auto.get() and self.cfg.get("region") and not self.busy:
            try:
                fp = fingerprint(grab(self.cfg["region"]))
                stable = not changed(fp, self._auto_prev)
                if stable and changed(fp, self._auto_done):
                    self._auto_done = fp
                    self.capture(source="auto")
                self._auto_prev = fp
            except Exception as exc:
                self.status(f"Auto capture error: {exc}")
        self.root.after(int(interval * 1000), self._auto_tick)

    def _clipboard_tick(self):
        if self.v_clip.get() and not self.busy:
            try:
                import pyperclip
                text = pyperclip.paste()
            except Exception:
                text = None
            if text and text != self._clip_last and 0 < len(text) < 4000:
                self._clip_last = text
                self.busy = True
                self.last_source = "clipboard"
                threading.Thread(target=self._clip_job, args=(text,), daemon=True).start()
            elif text is not None and self._clip_last is None:
                self._clip_last = text  # ignore whatever was already there when watching started
        self.root.after(500, self._clipboard_tick)

    def _clip_job(self, text):
        try:
            tokens = tokenize(text, self.cfg["lang"])
            self.q.put(("ocr", text, tokens, None, None, "clipboard"))
        except Exception as exc:
            self.q.put(("error", f"Could not parse clipboard text: {exc}"))
        finally:
            self.busy = False

    # ------------------------------------------------------------------- view
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        hide = self.v_hide_known.get()
        for i, t in enumerate(self.tokens):
            known = t.lemma in self.store.known
            if known and hide:
                continue
            notes = []
            if t.alt_readings:
                notes.append("読み: " + "/".join(t.alt_readings))
            if t.alt_lemmas:
                notes.append("or " + "/".join(t.alt_lemmas))
            if t.alt_splits:
                notes.append("split: " + " | ".join(t.alt_splits))
            tags = ("known",) if known else (("ambiguous",) if t.ambiguous else ())
            self.tree.insert("", "end", iid=str(i), tags=tags,
                             values=(t.lemma, t.reading, t.pos, "; ".join(notes), t.sentence))

    def _show_preview(self, img: Optional[Image.Image]):
        if img is None:
            self.preview.configure(image="", text="")
            self._preview_photo = None
            return
        try:
            from PIL import ImageTk
            thumb = img.copy()
            thumb.thumbnail((260, 110))
            self._preview_photo = ImageTk.PhotoImage(thumb)
            self.preview.configure(image=self._preview_photo, text="")
        except Exception:
            self.preview.configure(image="", text="(no preview)")

    def _maybe_save_shot(self, source: str):
        if not self.v_save_shots.get():
            return
        img = self.shots.get(self.cfg["screenshot"]) or self.shots.get("full")
        if img is None:
            return
        folder = cfgmod.APP_DIR / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        name = dt.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{source}.png"
        try:
            img.save(folder / name)
        except OSError as exc:
            self.status(f"Could not save screenshot: {exc}")

    def on_close(self):
        cfgmod.save(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


class EditDialog(tk.Toplevel):
    """Fix the word, pick between readings, trim the sentence, then add."""

    def __init__(self, app: App, token: Token):
        super().__init__(app.root)
        self.app, self.token = app, token
        self.title(f"Edit card: {token.lemma}")
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
        ttk.Button(ok, text="Add to Anki", command=self.add).pack(side="right", **pad)
        frm.columnconfigure(1, weight=1)
        self.bind("<Escape>", lambda _e: self.destroy())

    def do_lookup(self):
        word, reading = self.v_word.get().strip(), self.v_reading.get().strip()
        self.info.configure(text="Looking up…")

        def job():
            entry = lookup(word, self.app.cfg["lang"], reading_hint=reading, pos=self.token.pos)
            self.after(0, lambda: self._set_lookup(entry))
        threading.Thread(target=job, daemon=True).start()

    def _set_lookup(self, entry):
        if not self.winfo_exists():
            return
        self.meaning.delete("1.0", "end")
        self.meaning.insert("1.0", entry.meaning.replace("<br>", "\n"))
        if not self.v_reading.get() and entry.reading:
            self.v_reading.set(entry.reading)
        msg = "" if entry.meaning else "Nothing found (offline, or not in the dictionary)."
        if entry.readings and not entry.matched_context:
            msg = f"The dictionary lists readings {', '.join(entry.readings)}; none matched '{self.v_reading.get()}'."
        self.info.configure(text=msg)

    def do_ai(self):
        if self.app.cfg["ai_check"] == "off" and not self.app.cfg["anthropic_api_key"] and not os.environ.get("ANTHROPIC_API_KEY"):
            self.info.configure(text="AI check needs `pip install anthropic` and an API key (see README).")
        self.info.configure(text="Asking Claude…")
        t = self.token

        def job():
            try:
                v = ai.check(t.sentence, t.surface, self.v_reading.get(), t.alt_readings, t.alt_lemmas,
                             self.app.cfg["lang"], self.app.cfg["ai_model"], self.app.cfg["anthropic_api_key"])
                self.after(0, lambda: self._set_ai(v))
            except ai.AIError as exc:
                self.after(0, lambda: self.info.configure(text=str(exc)))
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
            "meaning": self.meaning.get("1.0", "end").strip().replace("\n", "<br>"),
            "sentence": self.sentence.get("1.0", "end").strip(),
        }
        self.destroy()
        self.app.status(f"Adding {overrides['word']}…")
        threading.Thread(target=self.app._add_job, args=([self.token], overrides), daemon=True).start()


def main(cfg: Optional[dict] = None):
    App(cfg or cfgmod.load()).run()
