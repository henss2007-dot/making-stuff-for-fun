// HintLadder backend: a Cloudflare Worker that answers hint requests on the
// site owner's Anthropic API key, so visitors pay nothing.
//
//   POST /api/hint   {turns: [{role, content}, ...]}  ->  {ladder, cached}
//   GET  /api/health                                   ->  {ok, model}
//
// Everything else is served from ./public by Workers Static Assets (see
// wrangler.toml). Safety nets: input size limits, a per-IP rate limit when the
// RATE_LIMITER binding is configured, and a shared cache so a question that was
// already answered is served again for free.

const DEFAULT_MODEL = "claude-sonnet-5-5";
const MAX_TURNS = 9;            // one question plus four "still stuck" rounds
const MAX_TURN_CHARS = 6000;
const CACHE_SECONDS = 60 * 60 * 24 * 30;

// Keep in sync with RULES in public/index.html (the page uses its own copy
// when it runs inside claude.ai without this server).
const RULES = `You write spoiler-free hints for video games, in the style of the Universal Hint System: a ladder of five hints that starts vague and gets more specific, so the player can stop reading as soon as they have enough to continue on their own.

The player tells you the game, where they are, and what they are stuck on. Reply with ONLY a JSON object of this exact shape:
{"understood": "one sentence restating what the player is stuck on, in your words, adding no new information",
 "confidence": "high" | "medium" | "low",
 "note": "one short sentence if something needs saying (you are unsure which puzzle they mean, the game is obscure, their description conflicts with the game as you remember it); otherwise an empty string",
 "hints": [
   {"level": 1, "title": "2-4 word label", "text": "..."},
   {"level": 2, "title": "...", "text": "..."},
   {"level": 3, "title": "...", "text": "..."},
   {"level": 4, "title": "...", "text": "..."},
   {"level": 5, "title": "...", "text": "..."}
 ]}

The ladder:
1 Nudge: reorient their thinking. Say what KIND of thing to consider (a timing contradiction in a statement, an item they already carry, a room they can go back to, a mechanic they have not used yet). No names, no specifics.
2 Narrow: shrink the search space. Which area, which character, which category of evidence or item, which statement roughly, without naming the exact thing.
3 Point: a concrete pointer that still leaves the final connection to the player (name the statement or the room or the character, but not the item to use there).
4 Almost: everything but the last step; the player should be able to do it from here with a little thought.
5 Answer: the exact solution, step by step (present X on statement Y, use item A on B, the code, the route, the strategy).

Spoiler rules, which override everything else:
- Help only with the immediate obstacle. Never mention anything from after the player's current point: later plot, twists, culprits, endings, characters or areas not yet reached, items not yet obtained.
- Never hint at the shape of what is coming ("you will soon find out", "this matters later", "the real culprit").
- Earlier rungs must not give away later rungs. Someone who reads only rung 1 learns only where to look.
- Each rung stands alone; do not refer to "the previous hint".
- If the description is ambiguous or you are unsure of the game's details, say so in "note", set confidence accordingly, and still give your best ladder. Do not bluff and do not invent item or character names.
- If the player says what they already tried, do not suggest it again; account for it.
- Keep each rung to 1-3 sentences of plain language, no markdown, no headings.`;

const SCHEMA = {
  type: "object",
  properties: {
    understood: { type: "string" },
    confidence: { type: "string", enum: ["high", "medium", "low"] },
    note: { type: "string" },
    hints: {
      type: "array",
      items: {
        type: "object",
        properties: { level: { type: "integer" }, title: { type: "string" }, text: { type: "string" } },
        required: ["level", "title", "text"],
        additionalProperties: false
      }
    }
  },
  required: ["understood", "confidence", "note", "hints"],
  additionalProperties: false
};

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...extra }
  });
}

function fail(code, message, status) {
  return json({ error: { code, message } }, status);
}

function validateTurns(turns) {
  if (!Array.isArray(turns) || turns.length === 0) return "turns must be a non-empty array";
  if (turns.length > MAX_TURNS) return "too many follow-ups; start a new question";
  for (const t of turns) {
    if (!t || (t.role !== "user" && t.role !== "assistant")) return "each turn needs a role of user or assistant";
    if (typeof t.content !== "string" || !t.content.trim()) return "each turn needs text";
    if (t.content.length > MAX_TURN_CHARS) return "a turn is too long; shorten the description";
  }
  if (turns[0].role !== "user" || turns[turns.length - 1].role !== "user") return "the conversation must start and end with the player";
  return null;
}

async function cacheKeyFor(turn, model) {
  const normalized = turn.content.toLowerCase().replace(/\s+/g, " ").trim() + "\n" + model;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normalized));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  // The host is never fetched; it only namespaces the entry in the Cache API.
  return new Request("https://hintladder.cache/ladder/" + hex);
}

async function askAnthropic(env, turns, model) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01"
    },
    body: JSON.stringify({
      model,
      max_tokens: 2048,
      system: RULES,
      messages: turns.map((t) => ({ role: t.role, content: t.content })),
      output_config: { format: { type: "json_schema", schema: SCHEMA } }
    })
  });

  if (res.status === 429 || res.status === 529) return { error: ["rate_limited", "The hint service is busy; try again in a minute.", 429] };
  if (res.status === 401 || res.status === 403) return { error: ["not_configured", "The site's API key was rejected.", 500] };
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).error.message; } catch (e) { /* keep statusText */ }
    return { error: ["upstream", msg, 502] };
  }

  const body = await res.json();
  if (body.stop_reason === "refusal") return { error: ["refused", "Claude declined that one; try rewording.", 422] };
  if (body.stop_reason === "max_tokens") return { error: ["truncated", "The answer was cut short; try again.", 502] };
  const text = (body.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
  try {
    return { ladder: JSON.parse(text) };
  } catch (e) {
    return { error: ["invalid_json", "The answer came back garbled; try again.", 502] };
  }
}

async function handleHint(request, env, ctx) {
  if (!env.ANTHROPIC_API_KEY) return fail("not_configured", "ANTHROPIC_API_KEY is not set on this Worker.", 500);

  let payload;
  try { payload = await request.json(); } catch (e) { return fail("bad_request", "body must be JSON", 400); }
  const turns = payload && payload.turns;
  const problem = validateTurns(turns);
  if (problem) return fail("bad_request", problem, 400);

  const model = env.MODEL || DEFAULT_MODEL;
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const firstAsk = turns.length === 1;

  // A question somebody already asked is answered from the shared cache, free.
  let key = null;
  if (firstAsk && cache) {
    try {
      key = await cacheKeyFor(turns[0], model);
      const hit = await cache.match(key);
      if (hit) {
        const ladder = await hit.json();
        return json({ ladder, cached: true });
      }
    } catch (e) { key = null; }
  }

  if (env.RATE_LIMITER) {
    const ip = request.headers.get("cf-connecting-ip") || "unknown";
    const { success } = await env.RATE_LIMITER.limit({ key: ip });
    if (!success) return fail("rate_limited", "Too many questions from your connection; wait a minute.", 429);
  }

  const result = await askAnthropic(env, turns, model);
  if (result.error) return fail(...result.error);

  if (key && cache) {
    const stored = new Response(JSON.stringify(result.ladder), {
      headers: { "content-type": "application/json", "cache-control": "s-maxage=" + CACHE_SECONDS }
    });
    const put = cache.put(key, stored).catch(() => {});
    if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
  }
  return json({ ladder: result.ladder, cached: false });
}

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/health") {
      if (request.method !== "GET") return fail("bad_request", "GET only", 405);
      return json({ ok: Boolean(env.ANTHROPIC_API_KEY), model: env.MODEL || DEFAULT_MODEL });
    }
    if (pathname === "/api/hint") {
      if (request.method !== "POST") return fail("bad_request", "POST only", 405);
      return handleHint(request, env, ctx);
    }
    if (env.ASSETS) return env.ASSETS.fetch(request);
    return new Response("Not found", { status: 404 });
  }
};
