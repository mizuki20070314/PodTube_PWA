#!/usr/bin/env python3
"""rsh.py - run a script on the Sakura rental server through a PTY session."""
import argparse
import base64
import os
import re
import subprocess
import sys
import threading
import time
import uuid

SSH = r"C:\Program Files\Git\usr\bin\ssh.exe"   # NOT the Windows OpenSSH (hangs with -tt + pipes)
HOST = "my-dev@www3414.sakura.ne.jp"
CHUNK = 360          # base64 chars per line typed into the pty
BATCH = 16           # lines typed between flow-control syncs


class Session:
    def __init__(self):
        self.p = subprocess.Popen(
            [SSH, "-tt", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
             "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=9", HOST],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0)
        self.buf = bytearray()
        self.pos = 0
        self.cv = threading.Condition()
        self.eof = False
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        f = self.p.stdout
        while True:
            try:
                d = f.read(65536)
            except Exception:
                d = b""
            with self.cv:
                if not d:
                    self.eof = True
                    self.cv.notify_all()
                    return
                self.buf += d
                self.cv.notify_all()

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.p.stdin.write(data)
        self.p.stdin.flush()

    def wait(self, pattern, timeout):
        end = time.time() + timeout
        with self.cv:
            while True:
                m = pattern.search(self.buf, self.pos)
                if m:
                    return m
                if self.eof:
                    return None
                left = end - time.time()
                if left <= 0:
                    return None
                self.cv.wait(min(left, 0.5))

    def close(self):
        # kill csh (parent of the .cshrc-started bash) so that the forced `passwd` never runs
        try:
            self.send("kill -KILL $PPID; exit\n")
        except Exception:
            pass
        try:
            self.p.wait(timeout=6)
        except Exception:
            self.p.kill()


def sync(s, timeout=60):
    """Round-trip marker so that everything typed so far has been consumed."""
    t = uuid.uuid4().hex[:10]
    s.send("echo __SY''NC_%s__\n" % t)
    m = s.wait(re.compile(("__SYNC_%s__\n" % t).encode()), timeout)
    if not m:
        raise RuntimeError("sync timeout")
    s.pos = m.end()


def open_session():
    s = Session()
    if not s.wait(re.compile(rb"\]\$ "), 45):          # prompt of the bash started by ~/.cshrc
        sys.stderr.write("no prompt from server; got: %r\n" % bytes(s.buf[-400:]))
        s.close()
        sys.exit(98)
    s.pos = len(s.buf)
    # bash saves its history right before `exec`, so switch history off *first*
    s.send("unset HISTFILE; set +o history\n")
    time.sleep(0.4)
    s.send("PS1='' PS2='' exec bash --noprofile --norc --noediting\n")
    tok = uuid.uuid4().hex[:10]
    # never touch the user's ~/.bash_history (bash keeps only 500 lines, so a few sessions would push it out)
    init = ("unset HISTFILE; set +o history; "
            "stty -echo -onlcr cols 200 2>/dev/null; umask 077; "
            "export LANG=C.UTF-8 LC_ALL=C.UTF-8; "
            "PATH=$HOME/.local/bin:$HOME/.local/sbin:$HOME/bin:$PATH; export PATH; "
            "LD_LIBRARY_PATH=$HOME/.local/lib:$HOME/.local/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; "
            "export LD_LIBRARY_PATH; "
            "echo __RE''ADY_%s__\n" % tok)
    pat = re.compile(("__READY_%s__\r?\n" % tok).encode())
    for _ in range(6):                                  # retry: readline of the old bash may eat input
        time.sleep(0.6)
        s.send(init)
        m = s.wait(pat, 4)
        if m:
            s.pos = m.end()
            return s
    sys.stderr.write("init failed; got: %r\n" % bytes(s.buf[-400:]))
    s.close()
    sys.exit(97)


def push_b64(s, data, path):
    """Write `data` (bytes) to remote `path` via base64 typed into the pty."""
    b64 = base64.b64encode(data).decode()
    tmp = path + ".b64"
    s.send(": > '%s'\n" % tmp)
    lines = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    for i in range(0, len(lines), BATCH):
        s.send("".join("echo '%s' >> '%s'\n" % (l, tmp) for l in lines[i:i + BATCH]))
        sync(s)
    # openssl base64 -d wants 64-col lines unless -A (single line) is used
    s.send("tr -d '\\n' < '%s' | openssl base64 -d -A -out '%s'; echo __DE''C_$?__; rm -f '%s'\n"
           % (tmp, path, tmp))
    m = s.wait(re.compile(rb"__DEC_(\d+)__\n"), 60)
    if not m or m.group(1) != b"0":
        raise RuntimeError("remote base64 decode failed: %r; tail=%r"
                           % (m and m.group(0), bytes(s.buf[max(0, s.pos - 400):])[-700:]))
    s.pos = m.end()


def run_script(s, script, timeout):
    t = uuid.uuid4().hex[:10]
    path = "/tmp/.rsh_%s.sh" % t
    push_b64(s, script, path)
    s.send("bash '%s' < /dev/null; echo __EN''D_%s:$?; rm -f '%s'\n" % (path, t, path))
    pat = re.compile(("__END_%s:(\\d+)\n" % t).encode())
    start = s.pos
    m = s.wait(pat, timeout)
    if not m:
        s.send(b"\x03")
        m = s.wait(pat, 10)
        timed_out = True
    else:
        timed_out = False
    if m:
        out = bytes(s.buf[start:m.start()])
        rc = int(m.group(1))
    else:
        out = bytes(s.buf[start:])
        rc = 124
    return out, rc, timed_out


def fixpath(p):
    """Undo MSYS/Git-Bash argument path conversion of remote absolute paths."""
    for pre in ("C:/Program Files/Git", r"C:\Program Files\Git"):
        if p.startswith(pre):
            return p[len(pre):].replace("\\", "/")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-t", "--timeout", type=float, default=120)
    ap.add_argument("-f", "--file")
    ap.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"))
    ap.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"))
    ap.add_argument("--mode", default=None)
    ap.add_argument("cmd", nargs="*")
    a = ap.parse_args()
    if a.put:
        a.put[1] = fixpath(a.put[1])
    if a.get:
        a.get[0] = fixpath(a.get[0])

    if a.put:
        data = open(a.put[0], "rb").read()
        s = open_session()
        try:
            push_b64(s, data, a.put[1])
            if a.mode:
                s.send("chmod %s '%s'; echo __CH''MOD_$?__\n" % (a.mode, a.put[1]))
                s.wait(re.compile(rb"__CHMOD_\d+__\n"), 20)
            print("uploaded %d bytes -> %s" % (len(data), a.put[1]))
        finally:
            s.close()
        return 0

    if a.get:
        s = open_session()
        try:
            t = uuid.uuid4().hex[:10]
            s.send("openssl base64 -in '%s'; echo __EN''D_%s:$?\n" % (a.get[0], t))
            m = s.wait(re.compile(("__END_%s:(\\d+)\n" % t).encode()), a.timeout)
            if not m or m.group(1) != b"0":
                sys.stderr.write("get failed\n")
                return 1
            raw = bytes(s.buf[s.pos:m.start()])
            data = base64.b64decode(re.sub(rb"[^A-Za-z0-9+/=]", b"", raw))
            open(a.get[1], "wb").write(data)
            print("downloaded %d bytes -> %s" % (len(data), a.get[1]))
        finally:
            s.close()
        return 0

    if a.file and a.file != "-":
        script = open(a.file, "rb").read()
    elif a.cmd and a.cmd != ["-"]:
        script = (" ".join(a.cmd) + "\n").encode()
    else:
        script = sys.stdin.buffer.read()
    script = script.replace(b"\r\n", b"\n")

    s = open_session()
    try:
        out, rc, timed_out = run_script(s, script, a.timeout)
    finally:
        s.close()
    sys.stdout.buffer.write(out.replace(b"\r", b""))
    sys.stdout.buffer.flush()
    if timed_out:
        sys.stderr.write("\n[rsh] TIMEOUT after %ss (sent Ctrl-C)\n" % a.timeout)
    sys.stderr.write("[rsh] exit=%d\n" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
