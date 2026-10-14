(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const btn = $("aiRun");
  if (!btn) return;
  btn.textContent = "Run 6-Layer AI (Local Qwen → optional cloud fallback)";
  const status = $("aiStatus");
  const layers = $("aiLayers");
  const getLocal = async (prompt) => {
    const response = await fetch("/local-ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, temperature: 0.1 }),
      signal: AbortSignal.timeout(90000),
    });
    if (!response.ok) throw new Error("Local Qwen HTTP " + response.status);
    const data = await response.json();
    if (!data.response) throw new Error("Local Qwen returned no response");
    return { text: data.response, provider: "Local Qwen", model: data.model || "desktop GGUF" };
  };
  const getCloud = async (prompt) => {
    if (!window.puter?.ai?.chat) throw new Error("Puter cloud fallback unavailable in this browser.");
    const result = await window.puter.ai.chat(prompt);
    const text = typeof result === "string" ? result : (result?.message?.content || result?.text || JSON.stringify(result));
    return { text, provider: "Puter cloud fallback", model: "provider-managed" };
  };
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.textContent = "Checking local Qwen…";
    layers.innerHTML = "";
    try {
      const data = window.FreshWeb?.data;
      if (!data) throw new Error("No backend signal data yet. Connect backend first.");
      const summary = {
        generated_at: data.generated_at,
        live: data.live,
        feed: { authenticated: data.feed?.authenticated, last_error: data.feed?.last_error },
        signals: data.signals,
        ai: data.ai,
        trade_plans: data.trade_plans,
        data_quality_note: "Do not invent missing market data. If stale, missing or conflicting, return WAIT / NO TRADE."
      };
      const prompt = "You are a cautious trading research assistant. Analyze this JSON only; do not invent prices, market facts, timestamps or indicators. This is research, not an order instruction. Return exactly six labeled sections: Data Quality AI, Market Regime AI, Technical AI, Derivatives/OI AI, Risk AI, Final Decision AI. For each state evidence, uncertainty, and PASS/FAIL/WAIT. Final decision must be WAIT/NO TRADE if data is missing/stale or deterministic validation fails. Do not claim statistical confidence unless supplied. JSON: " + JSON.stringify(summary);
      let answer;
      try { answer = await getLocal(prompt); }
      catch (localError) {
        status.textContent = "Local Qwen unavailable; trying optional cloud fallback…";
        answer = await getCloud(prompt);
        answer.localError = localError.message;
      }
      status.textContent = answer.provider + (answer.localError ? " (local unavailable)" : "") + " · " + answer.model;
      const card = document.createElement("article");
      card.className = "layer";
      const heading = document.createElement("h4"); heading.textContent = answer.provider + " · " + answer.model;
      const pre = document.createElement("pre"); pre.className = "log"; pre.textContent = answer.text;
      card.append(heading, pre); layers.append(card);
      window.FreshWeb?.log("AI analysis completed via " + answer.provider + ".");
    } catch (e) {
      status.textContent = "AI unavailable: " + e.message;
      const card = document.createElement("article"); card.className = "layer";
      card.textContent = "Local Qwen needs the desktop bridge and a running OpenAI-compatible GGUF server. Cloud fallback is optional and must be explicitly enabled by the user.";
      layers.append(card);
      window.FreshWeb?.log("AI failed: " + e.message);
    } finally { btn.disabled = false; }
  });
})();