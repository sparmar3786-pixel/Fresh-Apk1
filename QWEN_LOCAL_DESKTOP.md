# Fresh-Apk1 web + local Qwen desktop mode

## Current compatibility findings

- The repository already contains a static HTML/CSS dashboard and a FastAPI trading backend.
- The current HTML referenced `frontend/app.js` and `frontend/puter-ai.js`, but neither file existed on the default branch at inspection time. The web UI therefore was incomplete.
- The backend exposes `/health`, `/api/signals` and `/v1/signals`. Signal endpoints require a valid `X-Device-Id` header (43–128 URL-safe characters).
- The backend's configured cloud signal AI is OpenRouter via server environment configuration; the existing UI also loads Puter.js. No native GGUF inference runtime or Qwen model weights are bundled in the repository.
- A local Qwen GGUF model is supported through a local OpenAI-compatible inference server (such as LM Studio). The actual model file and desktop RAM/GPU determine performance.

## Run on a desktop

1. Install Python 3.11+.
2. Download a compatible Qwen GGUF model and load it in LM Studio.
3. In LM Studio, start its local server on `127.0.0.1:1234` with the OpenAI-compatible Chat Completions endpoint enabled.
4. From the repository root run `python desktop_bridge.py`.
5. Open `http://127.0.0.1:8787`.
6. In Logs/Settings, save the deployed HTTPS backend URL (for example the actual Railway/Render URL assigned to your deployment). Do not put Angel One, OpenAI, or other secret keys in browser storage.
7. Use the AI tab to run local Qwen first; the optional Puter cloud fallback is attempted only if local Qwen fails and the Puter client is available.

Alternative model endpoint:
`FRESH_LOCAL_MODEL_URL=http://127.0.0.1:1234/v1/chat/completions`
`FRESH_LOCAL_MODEL_NAME=your-loaded-model-id`
`FRESH_DESKTOP_PORT=8787`

The desktop bridge binds to loopback only. Do not change it to listen on 0.0.0.0 or forward its port to the internet.

## Hosted web version

The frontend can be hosted as static files, but a hosted page cannot access a desktop model directly without a local bridge, and the backend must allow the web origin in CORS. Configure the hosting origin and HTTPS backend URL only after checking the actual deployment domain and CORS policy. Never embed broker/API secrets in static JavaScript.

## Safety and validation

- This is research software, not investment advice.
- A connected backend does not prove Angel One is authenticated or that ticks are fresh.
- If the data is stale, incomplete, or conflicting, use WAIT / NO TRADE.
- Real order execution remains outside this web UI; the conversion does not enable automatic orders.
- Model output is commentary and must never override deterministic risk/data-quality gates.
