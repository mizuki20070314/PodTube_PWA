#!/usr/bin/env python3
"""cdp.py - drive a headless Edge through the Chrome DevTools Protocol (stdlib only: a minimal websocket client)."""
import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
# profile folder prefix of the headless Edge instances: a run only stops the leftovers with its own prefix, so a long install session
# (rosdrive.py, default prefix) can keep running while the test suite runs with CDP_PREFIX=edge-tst-
PREFIX = os.environ.get("CDP_PREFIX", "edge-cdp-")


class WS:
    def __init__(self, url):
        u = urllib.parse.urlsplit(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                        "Sec-WebSocket-Version: 13\r\n\r\n" % (u.path, u.hostname, u.port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake failed: %r" % buf[:200])
        self.rest = buf.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.rest) < n:
            d = self.s.recv(1 << 20)
            if not d:
                raise EOFError("websocket closed")
            self.rest += d
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def send(self, text):
        data = text.encode()
        head = bytearray([0x81])
        n = len(data)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        # XOR with the mask quickly for big payloads
        big = int.from_bytes(data, "big") ^ int.from_bytes((mask * (n // 4 + 1))[:n], "big") if n else 0
        self.s.sendall(bytes(head) + (big.to_bytes(n, "big") if n else b""))

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 8:
                raise EOFError("websocket closed by peer")
            if op == 9:
                continue
            msg += payload
            if b1 & 0x80:
                return msg.decode("utf-8", "replace")


class Browser:
    def __init__(self, port=None, size=(1280, 900), scale=1.0, args=None, throttle=False):
        # always a fresh free port: a just-killed Edge can keep its port busy for a moment, and then the new one only binds ::1
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.port, self.size, self.scale = port, size, scale
        self.prof = tempfile.mkdtemp(prefix=PREFIX, dir=HERE)
        self.extra = args or []
        self.throttle = throttle          # True: leave Edge's own background-tab throttling switched on (what a real user gets)
        self.proc = None
        self.n = 0
        self.events = []

    @staticmethod
    def kill_stale():
        """Stop leftover headless Edge instances of earlier test runs (only those started with our <PREFIX>* profile)."""
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
              "Where-Object { $_.CommandLine -like '*" + PREFIX + "*' -and $_.CommandLine -notlike '*--type=*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self):
        self.kill_stale()
        time.sleep(1.0)
        no_throttle = [] if self.throttle else ["--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows"]
        args = ([EDGE, "--headless=new", "--no-first-run", "--disable-extensions", "--hide-scrollbars",
                 "--remote-debugging-port=%d" % self.port, "--user-data-dir=" + self.prof,
                 "--window-size=%d,%d" % self.size, "--force-device-scale-factor=%s" % self.scale,
                 "--autoplay-policy=no-user-gesture-required"] + no_throttle + self.extra + ["about:blank"])
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % self.port, timeout=2))
                pages = [t for t in tabs if t.get("type") == "page"]
                if pages:
                    self.ws = WS(pages[0]["webSocketDebuggerUrl"])
                    break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("Edge did not start")
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Log.enable")
        return self

    def __exit__(self, *a):
        try:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        time.sleep(0.5)
        try:
            import shutil
            shutil.rmtree(self.prof, ignore_errors=True)
        except Exception:
            pass

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError("%s: %s" % (method, m["error"]))
                return m.get("result", {})
            if "method" in m:
                self.events.append(m)

    def pump(self, seconds):
        self.ws.s.settimeout(0.3)
        end = time.time() + seconds
        while time.time() < end:
            try:
                m = json.loads(self.ws.recv())
                if "method" in m:
                    self.events.append(m)
            except (socket.timeout, TimeoutError):
                pass
        self.ws.s.settimeout(120)

    def open(self, url, wait=2.0):
        self.events = []
        self.call("Page.navigate", url=url)
        self.pump(wait)

    def js(self, expr, timeout=120):
        self.ws.s.settimeout(timeout)
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True, timeout=int(timeout * 1000))
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            return "EXC: " + json.dumps(d.get("exception", {}).get("description", d.get("text")))[:600]
        return r.get("result", {}).get("value")

    def console_messages(self, clear=False):
        out = []
        for e in self.events:
            if e["method"] == "Runtime.consoleAPICalled":
                out.append(e["params"]["type"] + ": " + " ".join(str(a.get("value", a.get("description", ""))) for a in e["params"]["args"]))
            elif e["method"] == "Runtime.exceptionThrown":
                d = e["params"]["exceptionDetails"]
                out.append("EXCEPTION: " + str(d.get("exception", {}).get("description", d.get("text"))))
            elif e["method"] == "Log.entryAdded":
                out.append("LOG[%s]: %s" % (e["params"]["entry"].get("level"), e["params"]["entry"].get("text", "")))
        if clear:
            self.events = []
        return out

    def key(self, key, code=None, vk=0, text=None, mods=0):
        base = {"key": key, "code": code or key, "windowsVirtualKeyCode": vk, "modifiers": mods}
        down = dict(base, type="keyDown")
        if text is not None:
            down["text"] = text
        self.call("Input.dispatchKeyEvent", **down)
        self.call("Input.dispatchKeyEvent", **dict(base, type="keyUp"))

    _CODES = {" ": ("Space", 32), "-": ("Minus", 189), ".": ("Period", 190), "/": ("Slash", 191), "=": ("Equal", 187), ",": ("Comma", 188), ";": ("Semicolon", 186)}

    def type_text(self, text, delay=0.02):
        for ch in text:
            if ch == "\n":
                self.key("Enter", "Enter", 13, "\r")
            elif ch.isascii() and ch.isalpha():
                self.key(ch, "Key" + ch.upper(), ord(ch.upper()), ch)
            elif ch.isascii() and ch.isdigit():
                self.key(ch, "Digit" + ch, ord(ch), ch)
            elif ch in self._CODES:
                c, vk = self._CODES[ch]
                self.key(ch, c, vk, ch)
            elif ch == "$":
                self.key(ch, "Digit4", 52, ch, mods=8)
            elif ch == "_":
                self.key(ch, "Minus", 189, ch, mods=8)
            else:
                raise ValueError("no mapping for %r" % ch)
            time.sleep(delay)

    def click(self, x, y, button="left"):
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button=button, clickCount=1)

    def set_files(self, selector, paths):
        doc = self.call("DOM.getDocument", depth=0)
        node = self.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
        if not node.get("nodeId"):
            raise RuntimeError("no element for " + selector)
        self.call("DOM.setFileInputFiles", nodeId=node["nodeId"], files=list(paths))

    def shot(self, name, full=False):
        r = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=full)
        path = os.path.join(HERE, name)
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return path


# ---- additions for the PodTube PWA tests: device emulation and touch --------------------------------------------------
def emulate(b, width, height, mobile=True, scale=2.0, touch=True):
    """Phone-like viewport (CSS pixels) with touch events."""
    b.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale, mobile=mobile)
    if touch:
        b.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    else:
        b.call("Emulation.setTouchEmulationEnabled", enabled=False)


def touch(b, kind, x, y):
    """kind: touchStart | touchMove | touchEnd (a single finger)."""
    pts = [] if kind == "touchEnd" else [{"x": x, "y": y, "id": 1}]
    b.call("Input.dispatchTouchEvent", type=kind, touchPoints=pts)


def swipe(b, x1, y1, x2, y2, steps=10, delay=0.02):
    touch(b, "touchStart", x1, y1)
    for i in range(1, steps + 1):
        touch(b, "touchMove", x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        time.sleep(delay)
    touch(b, "touchEnd", x2, y2)


def tap(b, x, y):
    touch(b, "touchStart", x, y)
    time.sleep(0.04)
    touch(b, "touchEnd", x, y)


def rect(b, selector, index=0):
    """Bounding box (CSS px) of the index-th element matching selector, or None."""
    return b.js("(function(){var e=document.querySelectorAll(%s)[%d]; if(!e) return null; var r=e.getBoundingClientRect(); return {x:r.left,y:r.top,w:r.width,h:r.height};})()" % (json.dumps(selector), index))


def tap_sel(b, selector, index=0, dx=0.5, dy=0.5):
    r = rect(b, selector, index)
    if not r or r["w"] <= 0:
        return False
    tap(b, r["x"] + r["w"] * dx, r["y"] + r["h"] * dy)
    return True
