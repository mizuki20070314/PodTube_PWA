"""Makes the stylesheet work on Safari 12 (iOS 12), the main target of the original app.

  * flexbox `gap` (Safari 14.1+): every flex rule with `gap` loses it and gets  `<selector> > * + * { margin-left|top: ... !important }`
  * grid `gap` is kept and also written as `grid-gap` (the Safari 10.1 - 11 name)
  * `position: sticky` gets its `-webkit-` form (Safari < 13)

The transformation is textual and relies on the simple shape of app.css (no nested braces other than @media / @supports blocks).
"""
import re

_RULE = re.compile(r"([^{}@][^{}]*)\{([^{}]*)\}")
_GAP = re.compile(r"(?<![-\w])gap\s*:\s*([^;}]+);?")


def _repl(m):
    sel, body = m.group(1), m.group(2)
    g = _GAP.search(body)
    if not g:
        return m.group(0)
    val = g.group(1).strip()
    rest = _GAP.sub("", body)
    if re.search(r"display\s*:\s*grid", body):
        return "%s{%s grid-gap: %s; gap: %s;}" % (sel, rest.rstrip(), val, val)
    parts = val.split()
    column = re.search(r"flex-direction\s*:\s*column", body) is not None
    amount = parts[0] if column else parts[-1]
    prop = "margin-top" if column else "margin-left"
    sels = [s.strip() for s in sel.split(",") if s.strip()]
    owl = ",".join("%s > * + *" % s for s in sels)
    return "%s{%s}\n%s{%s: %s !important}" % (sel, rest.rstrip(), owl, prop, amount)


def fix(css):
    css = _RULE.sub(_repl, css)
    css = re.sub(r"position\s*:\s*sticky\s*;", "position: -webkit-sticky; position: sticky;", css)
    return css


if __name__ == "__main__":
    import sys
    sys.stdout.write(fix(open(sys.argv[1], encoding="utf-8").read()))
