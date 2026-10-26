# HintLadder

Spoiler-free hints for any video game, one rung at a time. Free for the people
who use it: the site owner's API key does the work, behind a rate limit and a
shared cache.

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

## Hosting it for everyone (Cloudflare, free tier)

Visitors pay nothing. You pay Anthropic for the hints that aren't already in
the cache, which is pennies (table below), and Cloudflare's free plan covers
the hosting.

```
hintladder/
  public/index.html   the page
  worker.js           the backend: POST /api/hint, GET /api/health
  wrangler.toml       Cloudflare config (model, rate limit, static files)
```

1. Install Node.js (https://nodejs.org), then in this folder:
   ```
   npm install
   npx wrangler login
   ```
   The login opens a browser; a free Cloudflare account is enough.
2. Add your Anthropic API key (from https://console.anthropic.com) as a
   secret. It is stored by Cloudflare, never in this repo:
   ```
   npx wrangler secret put ANTHROPIC_API_KEY
   ```
3. Deploy:
   ```
   npx wrangler deploy
   ```
   Wrangler prints the public address, something like
   `https://hintladder.<your-name>.workers.dev`. Share that link.
4. Set a monthly spend limit in the Anthropic console (Settings → Limits) so a
   surprise crowd can't run up a bill.

Run `npm run dev` for a local copy at http://localhost:8787 (set the key in a
`.dev.vars` file as `ANTHROPIC_API_KEY=sk-ant-...`).

### What a question costs you

A question is about 1,000 input tokens (the rules plus the player's text) and
about 500 output tokens. Prices are per million tokens.

| Model (set `MODEL` in `wrangler.toml`) | Input / output | About 1,000 questions |
|---|---|---|
| `claude-haiku-5-5` | $0.10 / $0.50 | $0.35 |
| `claude-sonnet-5-5` (default) | $2 / $10 | $7 |
| `claude-opus-5-5` | $4 / $20 | $14 |

Repeated questions cost nothing: a fresh question is cached for 30 days, keyed
on the player's text, and served from the cache the next time anyone asks the
same thing. Follow-up rounds ("Still stuck?") are never cached.

### Keeping it from being abused

- **Rate limit.** `wrangler.toml` allows 10 questions a minute per connection.
  Cloudflare counts per location, so it is approximate.
- **Input limits.** At most 9 turns of at most 6,000 characters each, and
  the model's output is capped at 2,048 tokens.
- **Spend limit.** The Anthropic console's limit is the hard stop; set it.
- **One site only.** The page is served from the same Worker as the API, and
  the API doesn't answer cross-origin browser requests.

## Other ways to run it

**Inside claude.ai.** Published as a Claude artifact the page asks Claude on
the viewer's own account instead, which uses that viewer's Claude usage. Good
for yourself; not the "free for everyone" setup above.

**Standalone with your own key.** Open `public/index.html` straight from
disk and expand **Connection** to paste an API key. The key stays in that
browser's local storage and is sent only to `api.anthropic.com`.

## How it works

The whole app is one HTML page plus one Worker. On load the page checks, in
order: is it inside the claude.ai artifact viewer (`window.claude`); is there
a backend at `api/health`; otherwise it shows the API key settings and calls
the Messages API directly from the browser. All three paths send the same
instructions and parse the same JSON shape, produced with structured output:

```json
{"understood": "...", "confidence": "high|medium|low", "note": "...",
 "hints": [{"level": 1, "title": "...", "text": "..."}, "... x5"]}
```

Unrevealed rungs are drawn as redaction bars whose widths are derived from the
hint text, so nothing about a hidden hint is readable until you click.

`npm test` runs the Worker against a fake Anthropic API to check the
validation, caching and error paths without spending anything.

## Limits

The hints come from the model's memory of the game, with no web lookup, so for
obscure games or very specific puzzles it can be wrong or vague. The
**confidence** badge and the note under the title say when it isn't sure.
Telling it what you already tried helps a lot.
