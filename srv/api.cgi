#!/usr/local/bin/python3
# PodTube PWA - API entry (Python CGI).  The code and the data live outside the web root: ~/.podtube/
import os
import sys

sys.dont_write_bytecode = True
_here = os.path.dirname(os.path.realpath(__file__))
_home = os.environ.get("PT_HOME") or os.path.join(os.path.dirname(os.path.dirname(_here)), ".podtube")
os.environ["PT_HOME"] = _home
sys.path.insert(0, os.environ.get("PT_CODE") or os.path.join(_home, "code"))
try:
    from podtube import api
    api.main()
except Exception:
    sys.stdout.write("Status: 500 Internal Server Error\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
                     "{\"error\":{\"code\":\"internal\",\"message\":\"internal error\",\"status\":500}}")
