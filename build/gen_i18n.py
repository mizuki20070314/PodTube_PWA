"""Generates web/js/02-i18n.js from the string table of the original app (L10n.swift): every key has ja + en."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(ROOT), "src-orig", "repo", "PodTube", "Sources", "App", "L10n.swift")
OUT = os.path.join(ROOT, "web", "js", "02-i18n.js")

STR = r'"((?:[^"\\]|\\.)*)"'
pat = re.compile(r'^\s*"([a-zA-Z0-9_.]+)":\s*\(' + STR + r',\s*' + STR + r'\),?\s*$')
table = {}
for line in open(SRC, encoding="utf-8"):
    m = pat.match(line)
    if m:
        ja = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        en = m.group(3).replace('\\"', '"').replace("\\\\", "\\")
        table[m.group(1)] = [ja, en]
print(len(table), "strings")

js = """/* Strings: ja / en, taken from the original app (L10n.swift).  Unknown keys fall back to the key itself. */
(function (PT) {
  'use strict';
  PT.L10N = %s;

  PT.isJapanese = function () {
    var s = PT.settings ? PT.settings.uiLanguage : 'auto';
    if (s === 'ja') return true;
    if (s === 'en') return false;
    var lang = (navigator.languages && navigator.languages[0]) || navigator.language || 'en';
    return /^ja/i.test(lang);
  };

  PT.t = function (key, arg) {
    var pair = PT.L10N[key];
    if (!pair) return key;
    var s = PT.isJapanese() ? pair[0] : pair[1];
    return arg === undefined ? s : s.replace('%%@', arg);
  };
})(window.PT);
""" % json.dumps(table, ensure_ascii=False, indent=1)
open(OUT, "w", encoding="utf-8", newline="\n").write(js)
print("wrote", OUT)
