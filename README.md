# WordMine

Read games, visual novels, manga and books in another language on your
computer, **hover any word to see what it means**, and save the ones you want
to learn, with the sentence and a screenshot, to **your own word list**, which
you can send to **Anki** or export anywhere.

It works on anything you can see on screen: PC games (windowed or borderless
fullscreen), emulators, browser games, digital manga, Kindle/ebook readers,
PDFs, even photos of a paper book. No per-game setup.

```
1. Select region  →  2. Play / read  →  3. Hover a word  →  4. "+ Save"  →  5. Send list to Anki (or export)
```

## What it does

- **Reads the screen.** Draw a box over the text once. Whenever the text in it
  changes, it is read again (OCR via Tesseract, 100+ languages, or
  [manga-ocr](https://github.com/kha-white/manga-ocr) for Japanese).
- **Hover to understand.** Move the mouse over a word on the game screen: a
  popup shows the dictionary form, reading, meaning, and the grammar it sits
  in (〜ている, 〜なければならない, passive, …). The same text appears in
  the WordMine window with the same hover.
- **One action to save.** Click **+ Save** in the popup (or press
  `Ctrl+Alt+Enter`). The word goes to your list with the sentence it came from
  and a screenshot: the whole game scene, just the text bubble, or none,
  depending on what you are reading.
- **Your word list first.** Everything you save lives in *My words*: mark
  entries new / learning / known, edit them, then **Send to Anki** (one click,
  cards with the image), or export an **Anki TSV**, a **CSV**, or a plain
  list to paste anywhere. Anki is optional.
- **Grammar, not just words.** Common Japanese patterns are detected and
  explained offline, with JLPT level; verb forms are broken down
  (倒した = 倒す + past). Optional AI gives a translation and a part-by-part
  explanation of any sentence, in any language.
- **Context-aware Japanese.** Words are split and read using the whole
  sentence (MeCab/UniDic). When a word could be read or split another way
  (辛い からい/つらい, 開く あく/ひらく, 東京/都 vs 東/京都) the alternatives
  are shown and the dictionary entry is matched to the reading used in
  context. Optional AI check asks Claude which reading fits the sentence.
- **Modes with presets.** Game, Visual novel, Manga (vertical text, snip a
  bubble), Book (sentence from the page, no screenshot).
- **Also:** clipboard watching for text hookers (Textractor, Agent) and
  ebook readers; open image files / PDF pages; import words you already know
  from your Anki deck so they stay hidden; optional fully offline Japanese
  dictionary.

## Install (10 minutes)

1. **Python 3.12, 3.13 or 3.14** — https://www.python.org/downloads/ (pick a
   3.14.x or 3.13.x installer, *not* the newest 3.15: one of the Japanese
   libraries has no 3.15 build yet). Windows: tick *Add Python to PATH*.
2. **Tesseract OCR**
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki — in the
     installer expand *Additional language data* and tick the languages you
     read (Japanese: tick **Japanese** and **Japanese (vertical)**).
   - macOS: `brew install tesseract tesseract-lang`
   - Linux: `sudo apt install tesseract-ocr tesseract-ocr-jpn tesseract-ocr-jpn-vert python3-tk`
3. **WordMine**: download this repository (green *Code* button → *Download
   ZIP*, unzip) or `git clone https://github.com/henss2007-dot/making-stuff-for-fun`.
   - Windows: double-click **`setup.bat`** once (installs the Python
     packages and runs a check), then **`WordMine.bat`** to start.
   - macOS/Linux: `python3 -m pip install -r requirements.txt`, then
     `./wordmine.sh` (or `python3 -m wordmine`).
4. **Anki** (optional, for flashcards): install the **AnkiConnect** add-on
   in Anki (*Tools → Add-ons → Get Add-ons…*, code `2055492159`) and restart
   Anki. Keep Anki open when you press *Send to Anki*.

The *Help* tab has a **Run setup check** button that tells you what is
missing and how to fix it (same as `python -m wordmine check`).

### Optional extras

| Want | Install | Then |
|---|---|---|
| Instant, offline Japanese dictionary (no internet needed, best hover experience) | *Settings → Dictionary & AI → Download offline dictionary* (about 12 MB; `setup.bat` does this for you, or run `python -m wordmine dictionary`) | nothing else: after a one-time index build of about 30 s, hover meanings are instant and work offline. You can also download `jmdict-eng-*.json.zip` by hand from https://github.com/scriptin/jmdict-simplified/releases and pick it with *Browse…*. |
| Much better Japanese OCR (stylised fonts, furigana, manga) | `pip install manga-ocr` (downloads a ~400 MB model on first use) | Settings → Reading → OCR engine |
| Better Japanese readings (full UniDic, ~1 GB) | `pip install unidic && python -m unidic download` | picked up automatically |
| Chinese word splitting | `pip install jieba` | choose Chinese as the language |
| AI: translation + grammar breakdown, reading check | `pip install anthropic` + an API key from https://console.anthropic.com | Settings → Dictionary & AI |
| Open PDF pages from the window | `pip install pymupdf` | |

## Using it

### Games and visual novels

1. Run the game **windowed or borderless-windowed** (exclusive fullscreen
   can't be captured and swallows hotkeys).
2. In WordMine pick **Mode: Game** (or *Visual novel*) and your language.
3. Click **1. Select region** (or `Ctrl+Alt+S`) and drag a box over the
   dialogue area. It is remembered; with *Auto* on, every new line is read.
4. Play. Hover a word you don't know on the game screen → popup → **+ Save**
   or `Ctrl+Alt+Enter`. The card gets the line and a screenshot of the scene.
5. For visual novels with **Textractor** or **Agent**, turn on *Clipboard*:
   the hooked text is used instead of OCR (perfect text, no errors).

### Manga and comics

**Mode: Manga.** Hover over a bubble, press `Ctrl+Alt+X` (**Snip**), drag over
the bubble. Vertical text is detected automatically. Hover works over the
snipped bubble; saved words get the bubble as the screenshot. While a snipped
bubble is shown, Auto leaves it alone (press *Read now* to go back to the
saved region). For Japanese manga, `manga-ocr` is strongly recommended over
Tesseract.

### Books, articles, ebook readers

**Mode: Book.** Select the page area as the region (and re-read with
`Ctrl+Alt+C` after turning the page, or leave *Auto* on), or, when the text
is selectable (Kindle app, browser, PDF reader), turn on *Clipboard* and copy
the paragraph. The card gets the sentence the word came from. Photos of
paper pages: **Open image / PDF…** in the Read tab.

### The window

| Tab | What's there |
|---|---|
| **Read** | The captured text with a preview image. Hover words (yellow = not yet known, underlined = grammar), double-click to save. *Save sentence* and *Explain with AI*. |
| **Words** | Every word of the capture with reading and type. Orange rows had an uncertain reading/split; the alternatives are listed. Enter saves, Delete marks known, *Merge* joins pieces of a compound. |
| **Grammar** | Patterns found in the text with meaning and JLPT level, plus verb/adjective form breakdowns. *Save grammar card*. |
| **My words** | Your list. *Send to Anki*, *Export…* (Anki TSV, CSV, plain text), status buttons, edit, delete, show the stored screenshot. The switch *Also send new words to Anki automatically* decides whether saving a word also creates the card right away (off by default: words collect here until you press *Send to Anki*). |
| **Help** | Getting started, hotkeys, *Run setup check*. |

**Settings…** (top right): what goes on the card (sentence / everything /
nothing; screenshot of the whole screen / text box only / none), Anki deck
and auto-send, dictionaries and AI, OCR engine and text direction, whether
the popup appears whenever the mouse rests on a word or only while you hold
Alt/Ctrl/Shift, hotkeys.

### Hotkeys

| Key | Action |
|---|---|
| `Ctrl+Alt+S` | Select / change the capture region |
| `Ctrl+Alt+C` | Read the region now |
| `Ctrl+Alt+X` | Snip: drag over any text and read it once |
| `Ctrl+Alt+A` | Toggle Auto |
| `Ctrl+Alt+Enter` | Save the word under the mouse |

Change them in *Settings → Hotkeys* (pynput syntax, e.g. `<ctrl>+<shift>+j`;
restart WordMine afterwards). Some anti-cheat systems block global hotkeys;
the buttons and the popup's *+ Save* still work.

## Anki cards

WordMine creates three note types on first use (names configurable):

| Note type | Fields |
|---|---|
| **WordMine** | Word, Reading, Meaning, Sentence (word in bold), Image, Source |
| **WordMine Grammar** | Pattern, Meaning, Sentence, Notes, Image, Source |
| **WordMine Sentence** | Sentence, Translation, Notes, Image, Source |

The deck (default *WordMine*) **starts empty and fills with what you save**;
nothing is pre-imported. Edit the card templates in Anki as you like; WordMine
only fills the fields that exist. To hide words you already know, use
*Import known words from Anki* (reads your deck) or put a word list, one per
line, in `~/.wordmine/known_words.txt`.

**Importing the TSV instead of using Send to Anki:** press *Send to Anki*
once with Anki open so the WordMine note types exist (or create them by
hand), then in Anki *File → Import* the `.tsv`; the file names its note type
and deck and its columns match the fields. Grammar and sentence entries go
into separate `…_grammar.tsv` / `…_sentences.tsv` files. Screenshots are
copied into a `…_media` folder next to the file: move those PNGs into Anki's
`collection.media` folder (Tools → Add-ons → *View files*, one level up) and
the images show on the cards.

## Languages

- **Reading the screen:** any language Tesseract has data for (100+). The
  Language box lists the common ones; pick *Other…* to type any Tesseract
  code (`ind`, `ara`, `hin`, …) whose language pack you installed, and
  *Settings → Reading → Tesseract language(s)* takes combinations such as
  `jpn+eng`.
- **Word splitting:** Japanese gets full analysis (dictionary forms,
  readings, alternatives, grammar); Chinese uses jieba; every other language
  is split on word boundaries (no lemmatiser, so *ran* and *running* are
  separate entries).
- **Meanings:** Japanese from JMdict (offline, one click to download) or
  jisho.org; English from dictionaryapi.dev; every other language from
  English Wiktionary; and the optional AI explains any sentence in any
  language. Without internet and without the JMdict download, hover still
  shows readings and grammar but the meaning line stays empty.

## Files

Everything lives in `~/.wordmine/` (Windows: `C:\Users\<you>\.wordmine\`):
`config.json`, `words.json` (your list), `known_words.txt`, `dict_cache.json`,
`screenshots/`, `dictionaries/` (the downloaded JMdict zip, about 12 MB) and
`jmdict-eng-*.index.pkl` (its lookup index, about 28 MB, rebuilt automatically
if deleted; deleting both turns offline meanings off). *My words → Export →
Open data folder* opens it.

## How the Japanese disambiguation works

MeCab scores every way of splitting and reading the whole sentence at once,
so the reading it picks already depends on the neighbouring words. WordMine
then looks at the runner-up parses: when they read the same word differently
or draw the word boundary elsewhere, the word is flagged and the alternatives
offered. The dictionary lookup prefers the entry whose reading matches the
one chosen in context and the senses matching its part of speech. The
analyser is statistical and can still be wrong (unidic-lite reads 辛い as
つらい even next to 料理); the full UniDic improves this, and the AI check
reads the sentence like a person would and fixes the rest.

## Command line

```
python -m wordmine check                 # diagnose the setup
python -m wordmine text "店を開く。"       # split text, show alternatives
python -m wordmine ocr page.png --lang ja [--vertical]
python -m pytest tests                   # run the test suite
```

## Troubleshooting

- **Nothing captured / black image:** the game is in exclusive fullscreen.
  Switch to borderless windowed.
- **Garbage text:** make the region tight around the text, set *Upscale* to
  `3` for tiny fonts, or switch to `manga_ocr` for Japanese.
- **Hover popup appears over the text box:** it moves above the region when
  it would cover it; make the region a little tighter if it still overlaps.
- **Popups get in the way while playing:** Settings → Reading → *Word popup
  over the game* → only while holding Alt (or Ctrl/Shift), or turn *Hover*
  off and use the Read tab.
- **"Cannot reach Anki":** Anki must be open with AnkiConnect installed. Your
  words are safe in the list; press *Send to Anki* later or export a TSV.
- **Linux:** hotkeys need X11 (not Wayland) and Tk needs `python3-tk`.

## Credits

- [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html) by the Electronic
  Dictionary Research and Development Group, used under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), in the
  JSON form published by [jmdict-simplified](https://github.com/scriptin/jmdict-simplified).
- Readings and word splitting: [MeCab](https://taku910.github.io/mecab/) via
  [fugashi](https://github.com/polm/fugashi) with UniDic.
- OCR: [Tesseract](https://github.com/tesseract-ocr/tesseract); optional
  [manga-ocr](https://github.com/kha-white/manga-ocr).
- Online meanings: [jisho.org](https://jisho.org), [dictionaryapi.dev](https://dictionaryapi.dev), [Wiktionary](https://en.wiktionary.org).
