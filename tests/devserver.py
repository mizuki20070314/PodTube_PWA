"""A local stand-in for the Sakura server: static files from ../web under /podtube/ and the real api.cgi, run as a CGI
subprocess exactly the way Apache would (environment variables in, `Status:` + headers + body out).

usage: python tests/devserver.py [port]      then open http://localhost:8080/podtube/
Environment: PT_KEY=secret  (sets require_key in the dev config; default: no key needed)
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SRV = os.path.join(ROOT, "srv")
HOME = os.path.join(ROOT, ".dev-home")
BASE = "/podtube"
CGI = BASE + "/api.cgi"

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("application/javascript", ".js")


def write_dev_config():
    os.makedirs(HOME, exist_ok=True)
    key = os.environ.get("PT_KEY", "")
    cfg = {"require_key": bool(key), "access_key": key}
    with open(os.path.join(HOME, "config.json"), "w") as f:
        json.dump(cfg, f)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pt-dev"

    def log_message(self, fmt, *args):
        if os.environ.get("PT_QUIET"):
            return
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_HEAD(self):
        self.route()

    def do_OPTIONS(self):
        self.route()

    def route(self):
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        if path.startswith(CGI):
            self.cgi(path[len(CGI):], parts.query)
        elif path == "/" or path == BASE:
            self.send_response(302)
            self.send_header("Location", BASE + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path.startswith(BASE + "/"):
            self.static(path[len(BASE) + 1:] or "index.html")
        else:
            self.send_error(404)

    def static(self, rel):
        if rel.endswith("/"):
            rel += "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            data = f.read()
        if rel == "css/app.css":
            sys.path.insert(0, os.path.join(ROOT, "build"))
            import cssfix
            data = cssfix.fix(data.decode("utf-8")).encode("utf-8")
        if rel == "sw.js":
            data = data.replace(b"__VERSION__", b"dev").replace(b"__PRECACHE__", b"[]")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def cgi(self, path_info, query):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        env = dict(os.environ)
        env.update({
            "REQUEST_METHOD": self.command, "PATH_INFO": path_info, "SCRIPT_NAME": CGI, "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "SERVER_PROTOCOL": "HTTP/1.1", "PT_HOME": HOME, "PT_CODE": SRV, "PYTHONIOENCODING": "utf-8",
        })
        for k, v in self.headers.items():
            env["HTTP_" + k.upper().replace("-", "_")] = v
        p = subprocess.Popen([sys.executable, os.path.join(SRV, "api.cgi")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        try:
            p.stdin.write(body)
            p.stdin.close()
        except OSError:
            pass
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = p.stdout.read(1)
            if not chunk:
                break
            head += chunk
        lines = head.decode("utf-8", "replace").split("\r\n")
        status = 200
        headers = []
        for l in lines:
            if not l:
                continue
            k, _, v = l.partition(":")
            if k.lower() == "status":
                status = int(v.strip().split()[0])
            else:
                headers.append((k, v.strip()))
        self.send_response(status)
        has_len = any(k.lower() == "content-length" for k, _ in headers)
        for k, v in headers:
            self.send_header(k, v)
        if not has_len:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        try:
            while True:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                if self.command != "HEAD":
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionError):
            p.kill()
        err = p.stderr.read()
        p.wait()
        if err:
            sys.stderr.write(err.decode("utf-8", "replace")[-1500:])


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    write_dev_config()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("dev server on http://localhost:%d%s/  (key %s)" % (port, BASE, "required" if os.environ.get("PT_KEY") else "off"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
