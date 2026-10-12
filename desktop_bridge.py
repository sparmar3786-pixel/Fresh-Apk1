"""Local-only desktop bridge for Fresh-Apk1 web UI and a local GGUF model.

Run an OpenAI-compatible local model server (e.g. LM Studio) on 127.0.0.1:1234,
then run: python desktop_bridge.py
Open http://127.0.0.1:8787. Never expose this bridge to a public network.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MODEL_URL = os.environ.get("FRESH_LOCAL_MODEL_URL", "http://127.0.0.1:1234/v1/chat/completions")
MODEL_NAME = os.environ.get("FRESH_LOCAL_MODEL_NAME", "local-gguf")
HOST = "127.0.0.1"
PORT = int(os.environ.get("FRESH_DESKTOP_PORT", "8787"))


class Handler(BaseHTTPRequestHandler):
    def _headers(self, status: int, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' https://js.puter.com; script-src 'self' https://js.puter.com; connect-src 'self' http://127.0.0.1:1234 https://*; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/local-ai/status":
            self._headers(200)
            self.wfile.write(json.dumps({"ok": True, "model_url": MODEL_URL, "model": MODEL_NAME}).encode())
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        target = (FRONTEND / path.lstrip("/")).resolve()
        if not target.is_relative_to(FRONTEND.resolve()) or not target.is_file():
            self._headers(404)
            self.wfile.write(b'{"detail":"Not found"}')
            return
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
        self._headers(200, content_type)
        self.wfile.write(target.read_bytes())

    def do_POST(self) -> None:
        if self.path != "/local-ai/chat":
            self._headers(404)
            self.wfile.write(b'{"detail":"Not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 200_000:
                raise ValueError("Invalid request size")
            incoming = json.loads(self.rfile.read(length))
            prompt = str(incoming.get("prompt", "")).strip()
            if not prompt or len(prompt) > 80_000:
                raise ValueError("Prompt is empty or too large")
            payload = json.dumps({
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": float(incoming.get("temperature", 0.1)),
                "stream": False,
            }).encode()
            req = urllib.request.Request(MODEL_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=85) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise RuntimeError("Local model returned an empty completion")
            self._headers(200)
            self.wfile.write(json.dumps({"response": content, "model": result.get("model", MODEL_NAME)}).encode())
        except (ValueError, KeyError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            self._headers(502)
            self.wfile.write(json.dumps({"detail": str(exc)}).encode())

    def log_message(self, fmt: str, *args: object) -> None:
        print("[Fresh desktop] " + fmt % args)


if __name__ == "__main__":
    if not FRONTEND.is_dir():
        raise SystemExit("frontend/ directory not found")
    print(f"Fresh-Apk1 desktop UI: http://{HOST}:{PORT}")
    print(f"Local model endpoint: {MODEL_URL}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
