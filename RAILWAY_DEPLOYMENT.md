# Fresh-Apk1 — Railway backend deployment

This repository's backend is a FastAPI service. Deploy from the **repository root** so Railway can see `Dockerfile`, `requirements.txt`, `backend/`, and `railway.toml`.

## Create a fresh Railway service

1. In Railway, create a new project and choose **Deploy from GitHub repo**.
2. Select `sparmar3786-pixel/Fresh-Apk1` and the `main` branch.
3. Set the service root directory to `/` (repository root). Use the repository's `Dockerfile`; do not set the root to `backend/`.
4. Add a public domain under the service's Networking settings.
5. Add required environment variables in Railway Variables. Start with the names in `.env.example`; add real provider credentials only in Railway's Variables UI, never in Git.
6. Keep `FRESH_LIVE_TRADING_ENABLED=false` until data, risk gates, and broker credentials are verified. Set `APP_FERNET_KEY` to a persistent secret so encrypted sessions remain readable after redeploys.
7. Wait for deployment to finish, then open `https://YOUR-RAILWAY-DOMAIN/health`. A healthy response is JSON with `"ok": true`.
8. In GitHub, open **Settings → Secrets and variables → Actions → Variables**, create repository variable `BACKEND_URL`, and set it to the exact Railway public HTTPS origin (no trailing slash). The Android workflow now requires this value and embeds it in the APK rather than silently using the old Render URL.

## Troubleshooting

- **Build fails:** inspect Railway's build logs; confirm root directory is `/` and the Dockerfile is selected.
- **Health check fails:** inspect deployment/runtime logs and confirm Railway assigned `PORT`; the Docker command binds Uvicorn to `0.0.0.0:$PORT`.
- **APK says backend offline:** open the exact `BACKEND_URL/health` in the phone browser, verify it returns HTTP 200, then rebuild from GitHub Actions after setting the repository variable.
- **Health works but Angel One is disconnected:** backend uptime and broker authentication are separate checks. Configure Angel One credentials securely in the app/backend and inspect `/v1/angel/status`.

Do not put API keys, MPIN/PIN, TOTP secrets, Fernet keys, or access tokens in this document, APK, or GitHub source files.
