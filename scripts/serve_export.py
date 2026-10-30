"""Serve frontend/out with clean URLs (/x -> x.html)."""
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "out"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3210


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def translate_path(self, path):
        p = super().translate_path(path)
        fp = Path(p)
        if fp.is_dir():
            idx = fp / "index.html"
            if idx.exists():
                return str(idx)
        if not fp.suffix and (Path(str(fp) + ".html")).exists():
            return str(fp) + ".html"
        return p

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
