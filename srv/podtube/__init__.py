"""PodTube PWA server side (Python CGI, runs on Python 3.8+).

The PWA in ../web talks to `api.cgi/<route>`.  This package does what a browser cannot:
it calls YouTube's InnerTube API (CORS), turns the large responses into small JSON documents,
and relays the HLS media (the URLs YouTube hands out are bound to the IP address that asked).
"""
VERSION = "1.0.0"
