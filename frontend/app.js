(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const storage = window.localStorage;
  const getDeviceId = () => {
    let id = storage.getItem("fresh_device_id");
    if (!id || !/^[A-Za-z0-9_-]{43,128}$/.test(id)) {
      const bytes = new Uint8Array(48);
      crypto.getRandomValues(bytes);
      id = Array.from(bytes, (b) => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"[b % 64]).join("");
      storage.setItem("fresh_device_id", id);
    }
    return id;
  };
  const DEFAULT_BACKEND = "https://nse-algo-backend-final-production.up.railway.app";
  const state = { backend: (storage.getItem("fresh_backend_url") || "").trim() || DEFAULT_BACKEND, data: null, timer: null };
  const apiUrl = (path) => state.backend.replace(/\/$/, "") + path;
  const esc = (v) => String(v ?? "—").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const log = (message) => {
    const box = $("logBox");
    if (box) box.textContent = "[" + new Date().toLocaleTimeString() + "] " + message + "\n" + box.textContent;
  };
  const setPill = (id, text, klass) => {
    const el = $(id); if (!el) return;
    el.textContent = text; el.className = "pill " + (klass || "");
  };
  function renderSettings() {
    const el = $("settingsBox");
    if (!el) return;
    el.textContent = "";
    const wrap = document.createElement("div");
    wrap.className = "settings-form";
    wrap.id = "settingsBox";
    wrap.innerHTML = '<label>Backend HTTPS URL <input id="backendInput" placeholder="https://your-backend.example.com" autocomplete="url"></label> <button id="saveBackend">Save & connect</button><p class="muted">Device ID is generated locally and sent as X-Device-Id. Never enter broker/API secrets into this browser setting.</p><p>Local Qwen: use the desktop bridge started with <code>python desktop_bridge.py</code>.</p>';
    el.replaceWith(wrap);
    const input = wrap.querySelector("#backendInput");
    input.value = state.backend;
    wrap.querySelector("#saveBackend").addEventListener("click", () => {
      const value = input.value.trim().replace(/\/$/, "");
      if (!value || !/^https:\/\//i.test(value)) { alert("Enter a public backend URL beginning with https://"); return; }
      state.backend = value;
      storage.setItem("fresh_backend_url", value);
      connect();
    });
  }
  async function request(path, options = {}) {
    if (!state.backend) throw new Error("Backend URL not set. Open Logs/Settings and save your HTTPS backend URL.");
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: { "X-Device-Id": getDeviceId(), ...(options.headers || {}) },
      signal: AbortSignal.timeout(12000),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : "HTTP " + response.status);
    return body;
  }
  function renderChain(data) {
    const market = data.market || {};
    const indexNames = Object.keys(market);
    const select = $("chainIndex");
    if (select && !select.dataset.ready) {
      select.innerHTML = indexNames.map(n => '<option value="' + esc(n) + '">' + esc(n) + '</option>').join("");
      select.dataset.ready = "1";
      select.addEventListener("change", () => renderSelectedChain());
    }
    const selected = select?.value || indexNames[0];
    const row = market[selected] || {};
    $("chainMeta").textContent = selected + " · " + (row.feed_mode || "data status unknown") + " · last fetch " + (row.last_fetch_label || "unknown");
    const chain = row.option_chain || [];
    const table = $("chainTable");
    if (!table) return;
    if (!chain.length) {
      table.innerHTML = '<tr><td>Option-chain data unavailable. Confirm Angel One session, instrument sync and backend status.</td></tr>';
      return;
    }
    const headers = Object.keys(chain[0]).slice(0, 12);
    table.innerHTML = "<thead><tr>" + headers.map(h => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      chain.slice(0, 160).map(item => "<tr>" + headers.map(h => "<td>" + esc(item[h]) + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }
  function renderSelectedChain() { if (state.data) renderChain(state.data); }
  function renderRegistry() {
    const list = $("regList");
    if (!list) return;
    const items = [
      ["STR-377","Strategy 377","Deterministic strategy layer; verify exact registered implementation in backend."],
      ["TREND","Trend","EMA 8/13, MACD and slope"],
      ["MOMENTUM","Momentum","RSI 14 and MACD direction"],
      ["VOL","Volatility","ATR 14 and optional IV/Greeks"],
      ["VWAP","Volume context","VWAP and premium/volume context"],
      ["OI","Derivatives / OI","PCR, OI delta and buildup quadrants"],
      ["RISK","Risk gates","Stale data, missing chain, conflicting regime => WAIT"],
      ["AI-1","Data Quality AI","Freshness and completeness"],
      ["AI-2","Market Regime AI","Trend, volatility and event context"],
      ["AI-3","Technical AI","Indicator packet"],
      ["AI-4","Derivatives AI","OI, premium, PCR and strike structure"],
      ["AI-5","Risk AI","Entry, stop, target and invalidation"],
      ["AI-6","Decision AI","CALL BUY / PUT BUY / WAIT / NO TRADE"]
    ];
    const q = ($("regSearch")?.value || "").toLowerCase();
    const filtered = items.filter(x => x.join(" ").toLowerCase().includes(q));
    $("regCount").textContent = filtered.length + " reference entries";
    list.innerHTML = filtered.map(x => '<li><span class="id">' + esc(x[0]) + '</span><span class="fam">' + esc(x[1]) + '</span><span>' + esc(x[2]) + '</span></li>').join("");
  }
  function renderData(data) {
    state.data = data;
    const feed = data.feed || {};
    setPill("conn", feed.authenticated ? (data.live ? "Angel One LIVE" : "Angel One connected · data stale") : "Backend reachable · Angel One disconnected", feed.authenticated && data.live ? "good" : "warn");
    setPill("src", "source: " + (data.live ? "live" : "cached / unavailable"), data.live ? "good" : "warn");
    setPill("adv", "trade plans: " + (data.qualified_trade_count ?? 0), "");
    const signals = data.signals || {};
    const first = Object.values(signals)[0];
    setPill("verdict", first?.decision || first?.verdict || "WAIT", "");
    renderChain(data);
    const flow = $("flowText");
    if (flow) flow.textContent = JSON.stringify({ feed, store: data.store, OBI: data.obi }, null, 2);
    const regime = $("regimeText");
    if (regime) regime.textContent = Object.entries(signals).map(([k,v]) => k + ": " + (v.regime || v.market_regime || "unknown") + " · " + (v.decision || "WAIT") + " · " + (v.reason || v.guards?.join(", ") || "")).join("\n") || "No signal snapshots available.";
    const plans = $("plansTable");
    if (plans) {
      const rows = data.trade_plans || [];
      plans.innerHTML = rows.length ? "<thead><tr><th>Index</th><th>Side</th><th>Strike</th><th>Entry</th><th>Stop</th><th>Target</th><th>Reason</th></tr></thead><tbody>" + rows.map(p => "<tr>" + ["index","side","strike","entry","stop_loss","target","reason"].map(k => "<td>" + esc(p[k]) + "</td>").join("") + "</tr>").join("") + "</tbody>" : "<tr><td>No qualified trade plans. WAIT is expected when data/risk gates fail.</td></tr>";
    }
    const bt = $("backtestText");
    if (bt) bt.textContent = "Use the backend historical backtest API after connecting Angel One. This web surface does not fabricate historical results.";
    const settings = $("settingsBox");
    if (settings && settings.tagName === "PRE") settings.textContent = "Backend: " + (state.backend || "not configured") + "\nDevice ID: stored locally (not shown)\nMarket feed: " + (feed.authenticated ? "authenticated" : "not authenticated") + "\nLast fetch: " + (data.last_fetch || "none") + "\nLive order controls are intentionally not exposed in this web conversion.";
    if ($("heatmap")) drawHeatmap(data);
    if ($("premvolText")) $("premvolText").textContent = "Market snapshot: " + (data.last_fetch || "no timestamp") + ". Heatmap/volume visuals require option-chain rows from a live or cached snapshot.";
    if ($("greeksText")) $("greeksText").textContent = "Greeks/IV are shown only when the provider supplies the fields; missing values are not inferred.";
  }
  function drawHeatmap(data) {
    const canvas = $("heatmap"); if (!canvas) return;
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle = "#7c8b9c"; ctx.font = "16px monospace";
    const market = data.market || {}; const key = $("chainIndex")?.value || Object.keys(market)[0];
    const rows = market[key]?.option_chain || [];
    if (!rows.length) { ctx.fillText("No option-chain data — check broker session / data freshness.", 20, 40); return; }
    const sample = rows.slice(0, 35); const w = canvas.width / sample.length;
    sample.forEach((r,i) => {
      const ce = Number(r.ce_oi ?? r.CE_OI ?? r.call_oi ?? 0), pe = Number(r.pe_oi ?? r.PE_OI ?? r.put_oi ?? 0);
      const total = Math.max(ce,pe,1); ctx.fillStyle = ce >= pe ? "#1b6948" : "#7b2936";
      ctx.fillRect(i*w+2, canvas.height-30-(Math.max(ce,pe)/total)*220, Math.max(2,w-4), 220);
      ctx.fillStyle="#d7e3ee"; ctx.fillText(String(r.strike ?? ""),i*w+2,canvas.height-8);
    });
  }
  async function connect() {
    if (!state.backend) { setPill("conn","backend URL required","bad"); return; }

    // Test service health separately from the data endpoint so a signals
    // route/market-data error is not mislabeled as a completely offline API.
    try {
      const healthResponse = await fetch(apiUrl("/health"), { signal: AbortSignal.timeout(7000) });
      if (!healthResponse.ok) throw new Error("Health endpoint HTTP " + healthResponse.status);
      setPill("conn","backend online · checking signals","good");
    } catch (e) {
      setPill("conn","backend offline","bad");
      setPill("src","source: unavailable","bad");
      log("Health check failed: " + e.message);
      return;
    }

    try {
      const data = await request("/api/signals");
      renderData(data);
      log("Signals refreshed successfully.");
    } catch (e) {
      setPill("conn","backend online · signals API error","warn");
      setPill("src","source: signals unavailable","bad");
      log("Backend health is OK, but signals request failed: " + e.message);
    }
  }
  document.querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach(b => b.classList.toggle("active", b === button));
    document.querySelectorAll(".tab").forEach(s => s.classList.toggle("active", s.id === "tab-" + button.dataset.tab));
  }));
  $("regSearch")?.addEventListener("input", renderRegistry);
  renderRegistry();
  renderSettings();
  connect();
  state.timer = window.setInterval(connect, 15000);
  window.addEventListener("beforeunload", () => window.clearInterval(state.timer));
  window.FreshWeb = { request, get data() { return state.data; }, log };
})();