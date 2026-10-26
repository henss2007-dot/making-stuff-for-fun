// Test doubles shared by the unit test and the browser test: a fake
// api.anthropic.com behind global fetch, and an in-memory Cache API.

export function installFakes() {
  const state = { calls: [], pending: [], next: null };
  const realFetch = globalThis.fetch;

  state.reply = (ladder, extra = {}) => {
    state.next = () => new Response(JSON.stringify({
      stop_reason: "end_turn",
      content: [{ type: "text", text: JSON.stringify(ladder) }],
      ...extra
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  state.replyText = (text) => {
    state.next = () => new Response(JSON.stringify({ stop_reason: "end_turn", content: [{ type: "text", text }] }), { status: 200 });
  };
  state.replyStatus = (status) => {
    state.next = () => new Response(JSON.stringify({ error: { message: "status " + status } }), { status });
  };

  globalThis.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.startsWith("https://api.anthropic.com/")) {
      state.calls.push(JSON.parse(init.body));
      if (!state.next) throw new Error("fake API had no reply queued");
      const make = state.next;
      return make();
    }
    return realFetch(input, init);
  };

  const store = new Map();
  globalThis.caches = {
    default: {
      match: async (req) => { const hit = store.get(req.url); return hit ? new Response(hit, { headers: { "content-type": "application/json" } }) : undefined; },
      put: async (req, res) => { store.set(req.url, await res.text()); }
    }
  };

  return state;
}
