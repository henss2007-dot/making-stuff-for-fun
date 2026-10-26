// Runs worker.js against a fake Anthropic API. No network, no spend.
//   node test/worker.test.js
import assert from "node:assert/strict";
import worker from "../worker.js";
import { installFakes } from "./fakes.js";

const fakes = installFakes();

const LADDER = {
  understood: "You can't find the contradiction.",
  confidence: "high",
  note: "",
  hints: [1, 2, 3, 4, 5].map((n) => ({ level: n, title: "Rung " + n, text: "Hint text " + n }))
};

function env(extra = {}) {
  return { ANTHROPIC_API_KEY: "sk-test", MODEL: "claude-sonnet-5-5", ...extra };
}

function post(body, headers = {}) {
  return new Request("https://hintladder.example/api/hint", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body)
  });
}

const ctx = { waitUntil: (p) => fakes.pending.push(p) };
const ask = (text) => ({ turns: [{ role: "user", content: text }] });

async function run(name, fn) {
  try { await fn(); console.log("ok   " + name); }
  catch (e) { console.log("FAIL " + name); console.log(e); process.exitCode = 1; }
}

await run("health reports model and key presence", async () => {
  const r = await worker.fetch(new Request("https://x/api/health"), env(), ctx);
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true, model: "claude-sonnet-5-5" });
  const r2 = await worker.fetch(new Request("https://x/api/health"), { }, ctx);
  assert.equal((await r2.json()).ok, false);
});

await run("missing key is reported as not_configured", async () => {
  const r = await worker.fetch(post(ask("Game: X")), { }, ctx);
  assert.equal(r.status, 500);
  assert.equal((await r.json()).error.code, "not_configured");
});

await run("validation rejects bad bodies", async () => {
  const cases = [
    ["not json", "{nope"],
    ["empty turns", { turns: [] }],
    ["bad role", { turns: [{ role: "system", content: "x" }] }],
    ["ends on assistant", { turns: [{ role: "user", content: "a" }, { role: "assistant", content: "b" }] }],
    ["too long", ask("x".repeat(6001))],
    ["too many", { turns: Array.from({ length: 10 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: "t" })).concat([{ role: "user", content: "end" }]) }]
  ];
  for (const [label, body] of cases) {
    const r = await worker.fetch(post(body), env(), ctx);
    assert.equal(r.status, 400, label);
    assert.equal((await r.json()).error.code, "bad_request", label);
  }
  assert.equal(fakes.calls.length, 0, "nothing reached the API");
});

await run("a fresh question calls the API once and is cached for the next asker", async () => {
  fakes.reply(LADDER);
  const r1 = await worker.fetch(post(ask("Game: Ace Attorney\nStuck on: which evidence")), env(), ctx);
  assert.equal(r1.status, 200);
  const b1 = await r1.json();
  assert.equal(b1.cached, false);
  assert.deepEqual(b1.ladder, LADDER);
  assert.equal(fakes.calls.length, 1);
  const sent = fakes.calls[0];
  assert.equal(sent.model, "claude-sonnet-5-5");
  assert.equal(sent.output_config.format.type, "json_schema");
  assert.match(sent.system, /spoiler-free/i);
  await Promise.all(fakes.pending);

  // Same question, different whitespace and case: served from cache, no API call.
  const r2 = await worker.fetch(post(ask("game: ace attorney \n stuck on:   WHICH evidence")), env(), ctx);
  const b2 = await r2.json();
  assert.equal(b2.cached, true);
  assert.deepEqual(b2.ladder, LADDER);
  assert.equal(fakes.calls.length, 1);
});

await run("follow-up rounds are sent in full and never cached", async () => {
  fakes.reply(LADDER);
  const turns = [
    { role: "user", content: "Game: X\nStuck on: Y" },
    { role: "assistant", content: JSON.stringify(LADDER) },
    { role: "user", content: "That didn't work" }
  ];
  const before = fakes.calls.length;
  await worker.fetch(post({ turns }), env(), ctx);
  await worker.fetch(post({ turns }), env(), ctx);
  assert.equal(fakes.calls.length, before + 2);
  assert.equal(fakes.calls[before].messages.length, 3);
});

await run("rate limiter blocks a flood but not cached answers", async () => {
  const hits = {};
  const RATE_LIMITER = { limit: async ({ key }) => { hits[key] = (hits[key] || 0) + 1; return { success: hits[key] <= 1 }; } };
  const e = env({ RATE_LIMITER });
  const h = { "cf-connecting-ip": "203.0.113.9" };
  fakes.reply(LADDER);
  const first = await worker.fetch(post(ask("Game: new one"), h), e, ctx);
  assert.equal(first.status, 200, "first question from this IP goes through");
  const blocked = await worker.fetch(post(ask("Game: another new one"), h), e, ctx);
  assert.equal(blocked.status, 429, "second fresh question within the window is blocked");
  assert.equal((await blocked.json()).error.code, "rate_limited");
  await Promise.all(fakes.pending);
  const cached = await worker.fetch(post(ask("Game: new one"), h), e, ctx);
  assert.equal(cached.status, 200);
  assert.equal((await cached.json()).cached, true, "cache is checked before the limiter");
});

await run("API refusal, truncation and garbage are mapped to error codes", async () => {
  fakes.reply(LADDER, { stop_reason: "refusal" });
  let r = await worker.fetch(post(ask("q1 " + Math.random())), env(), ctx);
  assert.equal((await r.json()).error.code, "refused");
  fakes.reply(LADDER, { stop_reason: "max_tokens" });
  r = await worker.fetch(post(ask("q2 " + Math.random())), env(), ctx);
  assert.equal((await r.json()).error.code, "truncated");
  fakes.replyText("not json at all");
  r = await worker.fetch(post(ask("q3 " + Math.random())), env(), ctx);
  assert.equal((await r.json()).error.code, "invalid_json");
  fakes.replyStatus(429);
  r = await worker.fetch(post(ask("q4 " + Math.random())), env(), ctx);
  assert.equal(r.status, 429);
  fakes.replyStatus(401);
  r = await worker.fetch(post(ask("q5 " + Math.random())), env(), ctx);
  assert.equal((await r.json()).error.code, "not_configured");
});

await run("unknown paths fall through to static assets", async () => {
  const ASSETS = { fetch: async () => new Response("page", { status: 200 }) };
  const r = await worker.fetch(new Request("https://x/"), env({ ASSETS }), ctx);
  assert.equal(await r.text(), "page");
  const r2 = await worker.fetch(new Request("https://x/nothing"), env(), ctx);
  assert.equal(r2.status, 404);
});

if (process.exitCode) { console.log("\nsome tests failed"); } else { console.log("\nall worker tests passed"); }
