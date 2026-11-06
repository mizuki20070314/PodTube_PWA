"""Generates web/js/01-icons.js from the Material icon path data of the original app (Apache License 2.0)."""
import json
import re

SRC = r"C:/Users/Mizuki/podtube-pwa/src-orig/repo/PodTube/Sources/App/IconData.swift"
OUT = r"C:/Users/Mizuki/podtube-pwa/pwa/web/js/01-icons.js"

paths = {}
for line in open(SRC, encoding="utf-8"):
    m = re.match(r'\s*"([a-z0-9_]+)":\s*"([^"]+)",?\s*$', line)
    if m:
        paths[m.group(1)] = m.group(2)
print(len(paths), "icons")

js = """/* Icons: Material Icons (Apache License 2.0), 24x24 path data taken from the original PodTube app. */
(function (PT) {
  'use strict';
  var P = %s;
  var NS = 'http://www.w3.org/2000/svg';

  // Shorts glyph and the logo mark are drawn by the original app itself
  var SHORTS = '<path fill-rule="evenodd" d="M9.5 2.5h5a4 4 0 0 1 4 4v11a4 4 0 0 1-4 4h-5a4 4 0 0 1-4-4v-11a4 4 0 0 1 4-4zM10 8.5v7l6-3.5z"/>';
  var SHORTS_OUTLINE = '<rect x="6.5" y="3.5" width="11" height="17" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 8.5v7l6-3.5z"/>';

  PT.iconPath = function (name) {
    return P[name] || P[String(name).replace('_outline', '')] || '';
  };

  /** SVG markup of an icon (tinted with the CSS `color`). */
  PT.iconSvg = function (name, size) {
    size = size || 24;
    var inner;
    if (name === 'shorts') inner = SHORTS;
    else if (name === 'shorts_outline') inner = SHORTS_OUTLINE;
    else inner = '<path d="' + PT.iconPath(name) + '"/>';
    return '<svg class="ic" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">' + inner + '</svg>';
  };

  /** An element holding the icon (a <span class="ico">). */
  PT.icon = function (name, size) {
    var s = document.createElement('span');
    s.className = 'ico';
    s.innerHTML = PT.iconSvg(name, size);
    return s;
  };

  PT.setIcon = function (el, name, size) {
    el.innerHTML = PT.iconSvg(name, size);
    el.setAttribute('data-icon', name);
  };

  PT.logoSvg = function (height) {
    var w = Math.round(height * 1.42);
    return '<svg class="logo" width="' + w + '" height="' + height + '" viewBox="0 0 142 100" aria-hidden="true">' +
      '<rect width="142" height="100" rx="28" fill="#f00"/><path d="M58 26v48l42-24z" fill="#fff"/></svg>';
  };
})(window.PT);
""" % json.dumps(paths, ensure_ascii=False, indent=1)
open(OUT, "w", encoding="utf-8", newline="\n").write(js)
print("wrote", OUT, len(js))
