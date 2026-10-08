import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

INDEX = Path(__file__).resolve().parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self)
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, INDEX.read_bytes(), "text/html")
            if u.path == "/api/match":
                n = int(q.get("n", 1))
                if not 1 <= n <= 20:
                    return self._send(404, json.dumps({"error": "match must be 1-20"}))
                payload = render.build_payload(n, q.get("mode", "analyst"), q.get("lang", "en"),
                                               q.get("inject") == "1")
                return self._send(200, json.dumps(payload, ensure_ascii=False))
            if u.path == "/api/events":
                n = int(q.get("n", 1))
                ids = [i for i in q.get("ids", "").split(",") if i][:80]
                return self._send(200, json.dumps(render.get_events(n, ids)))
            if u.path == "/api/eval":
                p = ROOT / "data" / "eval_results.json"
                return self._send(200, p.read_text() if p.exists() else "{}")
            return self._send(404, json.dumps({"error": "not found"}))
        except Exception as ex:  # keep the demo alive and show the problem
            return self._send(500, json.dumps({"error": str(ex)}))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = 8000
    print(f"StoryDesk running: http://localhost:{port}   (Ctrl+C to stop)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()