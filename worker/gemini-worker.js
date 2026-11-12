// Cloudflare Worker — deploy this as a Worker, not GitHub Pages.
// Set GEMINI_API_KEY as an encrypted Worker secret, never in source code.
// Set ALLOWED_ORIGIN to your GitHub Pages URL, e.g. https://meenanaman326-gif.github.io
export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowed = env.ALLOWED_ORIGIN || "https://meenanaman326-gif.github.io";
    const cors = {
      "Access-Control-Allow-Origin": origin === allowed ? origin : allowed,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: cors });
    if (origin !== allowed) return new Response("Origin not allowed", { status: 403, headers: cors });
    if (!env.GEMINI_API_KEY) return Response.json({ error: "Missing GEMINI_API_KEY secret" }, { status: 500, headers: cors });
    try {
      const { messages } = await request.json();
      if (!Array.isArray(messages) || messages.length > 24) throw Error("Invalid conversation");
      const contents = messages.filter(m => ["user", "assistant"].includes(m.role)).map(m => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text: String(m.content || "").slice(0, 4000) }]
      }));
      if (!contents.length) throw Error("Empty conversation");
      const upstream = await fetch("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
        body: JSON.stringify({ systemInstruction: { parts: [{ text: "You are JARVIS, a concise, friendly personal AI assistant. Reply in the user's language, including Hinglish." }] }, contents, generationConfig: { maxOutputTokens: 700 } })
      });
      const data = await upstream.json();
      if (!upstream.ok) return Response.json({ error: data.error?.message || "AI request failed" }, { status: upstream.status, headers: cors });
      const reply = data.candidates?.[0]?.content?.parts?.map(p => p.text || "").join("").trim();
      if (!reply) throw Error("Empty AI response");
      return Response.json({ reply }, { headers: cors });
    } catch (e) {
      return Response.json({ error: e.message || "Unexpected error" }, { status: 400, headers: cors });
    }
  }
};
