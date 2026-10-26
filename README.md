# making-stuff-for-fun

Small projects, each in its own folder:

| Folder | What it is |
|---|---|
| [`wordmine/`](#wordmine) | Mine vocabulary from games, manga and books on your screen into Anki (below) |
| [`bookpress/`](bookpress/) | Write or paste text, add pictures, get a PDF that looks like a real printed book. Downloads for Windows, Mac and Linux on the [Releases page](https://github.com/henss2007-dot/making-stuff-for-fun/releases). |

---

# WordMine

Mine vocabulary from **games, manga and books on your screen** straight into **Anki**.

Draw a box over the game's dialogue (or a speech bubble, or a page), press a
hotkey, and WordMine reads the text, splits it into words with their
dictionary forms and readings, and lets you send the ones you don't know to
Anki with the sentence, a screenshot and a dictionary definition.

It works on anything you can see on screen: PC games (windowed or borderless
fullscreen), emulators, browser games, digital manga, Kindle/ebook readers,
PDFs, even photos of a paper book. No per-game setup.

## Features

- **Any game, any language.** OCR via Tesseract (100+ languages) or
  [manga-ocr](https://github.com/kha-white/manga-ocr) for Japanese.
- **Three modes with presets:** Game (horizontal text box, whole text as
  context), Manga (vertical text, one-shot "snip" of each bubble), Book
  (paragraphs, the sentence containing the word goes on the card).
- **Context-aware Japanese analysis.** Words are split and read using the
  whole sentence (MeCab/UniDic). When a word could be read or split another
  way (辛い からい/つらい, 開く あく/ひらく, 東京/都 vs 東/京都) the
  alternatives are shown so you can pick, and dictionary entries are matched
  to the reading chosen in context. An optional **AI check** asks Claude
  which reading and sense actually fit the sentence.
- **Screenshots, your choice:** none, just the text box / bubble, or the
  whole game screen, attached to the card and/or saved to a folder.
- **Sentence on the card, your choice:** the sentence containing the word,
  everything captured, or nothing.
- **Auto mode:** watches the text box and OCRs whenever the text changes, so
  you just play and pick words.
- **Clipboard mode:** works with text hookers (Textractor, Agent) and ebook
  readers. Copy text, it shows up as words.
- **Known-word filtering:** import what's already in your Anki deck; words
  you add or mark known are hidden next time.
- **Anki integration** through AnkiConnect (creates the deck and note type
  for you). If Anki isn't running, everything is also written to a TSV that
  Anki can import.

## Install

1. **Python 3.9+** — https://www.python.org/downloads/ (on Windows tick
   "Add Python to PATH").
2. **Tesseract OCR**
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki — in the
     installer, expand *Additional language data* and tick the languages you
     read (for Japanese tick **Japanese** and **Japanese (vertical)**).
   - macOS: `brew install tesseract tesseract-lang`
   - Linux: `sudo apt install tesseract-ocr tesseract-ocr-jpn tesseract-ocr-jpn-vert`
3. **Anki** with the **AnkiConnect** add-on: in Anki, *Tools → Add-ons →
   Get Add-ons…* and enter code `2055492159`, then restart Anki.
4. WordMine itself:

   ```
   git clone https://github.com/henss2007-dot/making-stuff-for-fun
   cd making-stuff-for-fun
   pip install -r requirements.txt
   python -m wordmine check
   ```

   `check` tells you what is missing. When everything says OK:

   ```
   python -m wordmine
   ```

### Optional extras

| Want | Install | Then |
|---|---|---|
| Much better Japanese OCR (stylised game fonts, furigana, vertical manga) | `pip install manga-ocr` | set `"ocr_engine": "manga_ocr"` in config.json |
| Better Japanese readings (full UniDic, ~1 GB) | `pip install unidic && python -m unidic download` | picked up automatically |
| Chinese word splitting | `pip install jieba` | pick Chinese as the language |
| AI context check for ambiguous readings | `pip install anthropic` + an API key in `ANTHROPIC_API_KEY` | set *AI context check* in the window |
| Open PDF pages from the window | `pip install pymupdf` | |

## Using it

### Games

1. Start the game in **windowed or borderless-windowed** mode (exclusive
   fullscreen often can't be captured and swallows hotkeys).
2. Open WordMine, choose **Mode: Game** and your language.
3. Click **Select region** (or press `Ctrl+Alt+S`) and drag a box over the
   dialogue area. The region is remembered.
4. Each time new text appears press `Ctrl+Alt+C`, or turn on **Auto** and
   it captures whenever the text changes.
5. Words appear in the list. Known words are hidden; orange words have a
   reading or split the analyser wasn't sure about, with the alternatives in
   the *Also possible* column.
6. Click the words you don't know (Ctrl-click for several) and press
   **Add selected to Anki** (or Enter). Double-click a word to fix the
   spelling, pick a reading, trim the sentence or ask the AI first.

### Manga / comics

Choose **Mode: Manga**. Instead of a fixed region, hover over a bubble and
press `Ctrl+Alt+X` (**Snip**), drag over the bubble, done. Vertical text is
detected automatically (set *Text direction* to force it). For Japanese
manga, `manga-ocr` is strongly recommended over Tesseract.

### Books, articles, ebook readers

Choose **Mode: Book**. Either select the page area as the region and press
capture (or use Auto when turning pages), or, if the text is selectable
(Kindle app, browser, PDF reader), turn on **Watch clipboard** and just copy
the paragraph. The card gets the sentence the word came from. Use **Open
image / PDF…** for photos of paper pages or PDF files.

### Hotkeys

| Key | Action |
|---|---|
| `Ctrl+Alt+S` | Select / change the capture region |
| `Ctrl+Alt+C` | Capture the region now |
| `Ctrl+Alt+X` | Snip: drag over any text and read it once |
| `Ctrl+Alt+A` | Toggle auto mode |

Change them in `config.json` (pynput syntax, e.g. `"<ctrl>+<shift>+j"`).

### The cards

Note type **WordMine** with fields Word, Reading, Meaning, Sentence (word
in bold), Image, Source. Edit the templates in Anki as you like; WordMine
only fills the fields that exist. The *Source* box in the window (game or
book title) goes into every card.

## Settings

Everything lives in `~/.wordmine/config.json` (Windows:
`C:\Users\you\.wordmine\config.json`); the window changes most of it. Also in
that folder: `known_words.txt`, `mined.tsv` (every word you ever added, in
Anki import format) and `screenshots/`.

Useful knobs: `ocr_scale` (`"auto"` tries 1x and 2x and keeps the more
confident read; a fixed number such as `3` is faster and suits tiny fonts), `tesseract_lang`
(e.g. `"jpn+eng"` for games that mix in English), `auto_interval`,
`ai_model` (`claude-opus-5-5` by default; `claude-haiku-5-5` is cheaper).

## How the Japanese disambiguation works

MeCab scores every way of splitting and reading the whole sentence at once,
so the reading it picks already depends on the neighbouring words. WordMine
then also looks at the runner-up parses: when they read the same word
differently or draw the word boundary elsewhere, the word is flagged and the
alternatives are offered. The dictionary lookup prefers the entry whose
reading matches the one chosen in context and the senses matching its part
of speech. The analyser is statistical and can still be wrong (unidic-lite
reads 辛い as つらい even next to 料理); the full UniDic improves this, and
the AI check reads the sentence like a person would and fixes the rest.

## Command line

```
python -m wordmine check                 # diagnose the setup
python -m wordmine text "店を開く。"       # split text, show alternatives
python -m wordmine ocr page.png --lang ja [--vertical]
```

## Troubleshooting

- **Nothing captured / black image:** the game is in exclusive fullscreen.
  Switch to borderless windowed.
- **Garbage text:** make the region tight around the text, set `ocr_scale`
  to `3` for tiny fonts, or switch to `manga_ocr` for Japanese.
- **Hotkeys don't fire in the game:** some anti-cheat systems block global
  hotkeys; use the buttons, or Auto mode.
- **"Cannot reach Anki":** Anki must be open with AnkiConnect installed.
  Cards still go to `mined.tsv`; import it with *File → Import* in Anki.
- **Linux:** hotkeys need X11 (not Wayland) and may need
  `sudo apt install python3-tk`.
