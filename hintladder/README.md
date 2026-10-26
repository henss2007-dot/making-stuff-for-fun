# HintLadder

Spoiler-free hints for any video game, one rung at a time.

You say which game you're playing, where you are, and what you're stuck on.
HintLadder writes a ladder of five hints, from a vague nudge to the full
answer, and shows them one at a time. Stop reading as soon as you've got
enough. It works like the Universal Hint System, except it isn't limited to a
fixed list of games: the hints are written on the spot by Claude.

```
1 Nudge    what KIND of thing to think about, no names
2 Narrow   which area / character / category of evidence
3 Point    a concrete pointer, you still make the last connection
4 Almost   everything but the final step
5 Answer   the exact solution (hidden behind an extra confirm)
```

The hints only ever cover the immediate obstacle. The prompt forbids
mentioning anything after your current point in the game: later plot, twists,
culprits, characters or areas you haven't reached, items you don't have.
Earlier rungs are written so they don't give away later ones.

If a hint didn't get you through, the **Still stuck?** box sends what happened
back and gets a fresh ladder that accounts for it. Recent questions are kept in
your browser so you can come back to a ladder mid-game.

## Two ways to run it

**On claude.ai (no API key).** Published as a Claude artifact, the page asks
Claude on the viewer's own account. The first question asks you once to allow
it. This is the easiest way to use it on a phone next to the console.

**Standalone (your own API key).** Open `index.html` in a browser, or serve the
folder with any static server. Expand **Connection**, paste an Anthropic API
key from https://console.anthropic.com and pick a model (Opus 5.5 gives the
best hints; Haiku 5.5 is the cheapest). The key is stored in that browser's
local storage and sent only to `api.anthropic.com`.

Everything is in the one file, `index.html`: no build step, no dependencies
beyond the fonts.

## How it works

The whole app is one HTML page. On load it checks whether it's running inside
the claude.ai artifact viewer (`window.claude.use("sample")`); if so it uses
that, otherwise it shows the API key settings and calls the Messages API
directly from the browser with structured JSON output. Both paths send the same
instructions and the same conversation, and parse the same JSON shape:

```json
{"understood": "...", "confidence": "high|medium|low", "note": "...",
 "hints": [{"level": 1, "title": "...", "text": "..."}, "... x5"]}
```

Unrevealed rungs are drawn as redaction bars whose widths are derived from the
hint text, so nothing about the hidden hint is in the page until you click.

## Limits

The hints come from the model's memory of the game, with no web lookup, so for
obscure games or very specific puzzles it can be wrong or vague. The
**confidence** badge and the note under the title say when it isn't sure.
Telling it what you already tried helps a lot.
