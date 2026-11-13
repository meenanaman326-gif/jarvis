// JARVIS Cloudflare Worker. GEMINI_API_KEY must be a Cloudflare Secret.
const API = "https://generativelanguage.googleapis.com/v1beta";
const ALLOWED = "https://meenanaman326-gif.github.io";
const SYSTEM = "You are JARVIS, a helpful and efficient voice-first assistant. Answer directly in the user's language (Hindi, Hinglish, or English). Be concise unless detail is requested.";
let modelCache = { names: [], expires: 0 };
function json(body, status, headers) { return new Response(JSON.stringify(body), { status, headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } }); }
async function timedFetch(url, options, ms) {
  return fetch(url, { ...options, signal: AbortSignal.timeout(ms) });
}
async function models(key) {
  if (modelCache.expires > Date.now()) return modelCache.names;
  const response = await timedFetch(API + "/models?pageSize=100", { headers: { "x-goog-api-key": key } }, 4500);
  if (!response.ok) throw new Error("Model discovery unavailable (" + response.status + ")");
  const data = await response.json();
  const names = (data.models || []).filter(m => m.supportedGenerationMethods?.includes("generateContent"))
    .map(m => (m.name || "").replace(/^models\//, ""))
    .filter(n => /flash/i.test(n) && !/image|tts|audio|live|embedding|preview|experimental/i.test(n));
  // Lite is usually quicker; prefer available stable Flash variants.
  names.sort((a,b) => Number(/lite/i.test(b)) - Number(/lite/i.test(a)));
  modelCache = { names, expires: Date.now() + 15 * 60 * 1000 };
  return names;
}
export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowed = env.ALLOWED_ORIGIN || ALLOWED;
    const cors = { "Access-Control-Allow-Origin": allowed, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET") return json({ service: "jarvis", status: "online", keyConfigured: !!env.GEMINI_API_KEY }, 200, cors);
    if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, cors);
    if (origin !== allowed) return json({ error: "Origin not allowed" }, 403, cors);
    if (!env.GEMINI_API_KEY) return json({ error: "GEMINI_API_KEY secret is missing from this deployment." }, 503, cors);
    let messages;
    try { ({ messages } = await request.json()); } catch { return json({ error: "Invalid request JSON" }, 400, cors); }
    if (!Array.isArray(messages) || !messages.length || messages.length > 25) return json({ error: "Invalid messages" }, 400, cors);
    const contents = messages.filter(m => m && (m.role === "user" || m.role === "assistant")).slice(-12)
      .map(m => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: String(m.content || "").slice(0, 2000) }] }));
    if (!contents.length || contents.at(-1).role !== "user") return json({ error: "Last message must be from user" }, 400, cors);
    const payload = JSON.stringify({ systemInstruction: { parts: [{ text: SYSTEM }] }, contents, generationConfig: { maxOutputTokens: 220, temperature: 0.5 } });
    const key = env.GEMINI_API_KEY;
    let names;
    try { names = await models(key); }
    catch (e) { names = ["gemini-3.8-flash"]; }
    if (!names.length) return json({ error: "No compatible Gemini Flash model found for this API key." }, 503, cors);
    const tried = [];
    for (const name of names.slice(0, 3)) {
      try {
        const res = await timedFetch(API + "/models/" + encodeURIComponent(name) + ":generateContent", {
          method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": key }, body: payload
        }, 7500);
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          const reply = data.candidates?.[0]?.content?.parts?.map(p => p.text || "").join("").trim();
          if (reply) return json({ reply, model: name }, 200, cors);
          tried.push(name + ": empty response"); continue;
        }
        const reason = data.error?.message || "API error";
        tried.push(name + ": " + res.status);
        if (![404, 429, 500, 502, 503, 504].includes(res.status)) {
          return json({ error: "Gemini (" + res.status + "): " + reason.slice(0, 250) }, 502, cors);
        }
      } catch (e) { tried.push(name + ": " + (e.name === "TimeoutError" ? "timeout" : "network error")); }
    }
    return json({ error: "AI models are busy or timed out. Try again shortly.", attempts: tried }, 503, cors);
  }
};
