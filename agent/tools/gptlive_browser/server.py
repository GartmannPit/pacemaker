"""Lokaler GPT-Live-Browsertest (WebRTC direkt zu OpenAI, ohne Pipecat).

Zweck: Stimmen anhören und vergleichen, kurze Clip-Messung im Browser. Kein Messvertrag-Lauf.

    cd agent && OPENAI_LIVE_REGION=referenz uv run python tools/gptlive_browser/server.py
    -> http://localhost:3000

Der API-Key bleibt serverseitig (agent/.env, OPENAI_API_KEY); der Server lauscht nur auf
127.0.0.1. Clips: agent/fixtures/audio (synthetisch). Ergebnisse der Clip-Messung:
experiments/runs/browser/browser_messung.jsonl (gitignored).
"""

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

from pacemaker_agent.config import LIVE_REGIONS
from pacemaker_agent.personas.kaltakquise_head_of_ops import system_prompt

HERE = Path(__file__).parent
AGENT = HERE.parent.parent
CLIPS = AGENT / "fixtures" / "audio"
RESULTS = AGENT.parent / "experiments" / "runs" / "browser" / "browser_messung.jsonl"
ORIGIN = "http://localhost:3000"

load_dotenv(AGENT / ".env")
REGION = os.environ.get("OPENAI_LIVE_REGION", "")
if REGION not in LIVE_REGIONS:
    raise SystemExit(
        f"OPENAI_LIVE_REGION={REGION!r} unzulässig. Erlaubt: {', '.join(LIVE_REGIONS)} "
        "(referenz = api.openai.com)."
    )
KEY = os.environ["OPENAI_API_KEY"]
BASE = "https://eu.api.openai.com" if REGION == "eu" else "https://api.openai.com"
PROMPT = system_prompt(short_opener=False)
BACKEND = os.environ.get("OPENAI_LIVE_BACKEND_MODEL", "gpt-4.1-mini")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            page = (HERE / "index.html").read_text(encoding="utf-8").replace("{{REGION}}", REGION)
            return self.reply(200, page.encode(), "text/html; charset=utf-8")
        if self.path == "/api/clips":
            names = sorted(p.name for p in CLIPS.glob("*.wav"))
            return self.reply(200, json.dumps(names).encode())
        name = self.path.removeprefix("/clips/")
        if self.path.startswith("/clips/") and "/" not in name and name.endswith(".wav"):
            f = CLIPS / name
            if f.exists():
                return self.reply(200, f.read_bytes(), "audio/wav")
        self.reply(404, b"{}")

    def do_POST(self) -> None:
        if self.headers.get("Origin") != ORIGIN:
            return self.reply(403, b'{"error":"nicht erlaubt"}')
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/result":
            row = json.loads(body) | {"region": REGION}
            RESULTS.parent.mkdir(parents=True, exist_ok=True)
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            return self.reply(204, b"")
        if self.path != "/api/session":
            return self.reply(404, b"{}")
        req_body = json.loads(body)
        session = {
            "model": "gpt-live-1",
            "instructions": PROMPT,
            "delegation": {"type": "responses", "responses": {"model": BACKEND}},
        }
        if req_body.get("voice"):
            session["audio"] = {"output": {"voice": req_body["voice"]}}
        req = urllib.request.Request(
            f"{BASE}/v1/live/sessions",
            data=json.dumps(
                {"session": session, "transport": {"type": "webrtc", "sdp": req_body["sdp"]}}
            ).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self.reply(201, r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:2000]
            print("OpenAI-Fehler", e.code, detail)
            self.reply(e.code, json.dumps({"error": detail}).encode())


if __name__ == "__main__":
    print(f"Öffnen: {ORIGIN}  (Region: {REGION}, Endpunkt: {BASE})")
    ThreadingHTTPServer(("127.0.0.1", 3000), Handler).serve_forever()
