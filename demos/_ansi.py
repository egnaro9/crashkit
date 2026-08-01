"""Truecolor helpers with a two-layer palette.

Structure borrowed from Pi's theme format: `VARS` holds the hex, `TOKENS` map a
*meaning* onto a var. Call sites ask for `fail()` or `warn()`, never `coral()` or
`yellow()`, so retheming touches this file and nothing else. That separation is
what makes two themes off one codebase possible, and it is exactly what went
wrong when 'high' severity was squatting on the accent colour — the call site
had picked a colour instead of naming a job.

Two themes ship. `blue` is the default: deep blue ground, blue-white body, and
the accent held back for the single thing a reader should look at. `slate` is
the portfolio's own CSS custom properties, for when a cast should dissolve into
that page instead of reading as a device sitting on it. Select with CAST_THEME.

Kept as a local module rather than a dependency so each repo's demo stays
runnable from a fresh clone with nothing installed.
"""

import os

VARS = {
    "blue": {
        "fg": "192;201;229",  # #c0c9e5  cool blue-white
        "gray": "126;163;199",  # #7ea3c7
        "dimGray": "85;119;155",  # #55779b
        "orange": "249;115;22",  # #f97316
        "aqua": "122;253;225",  # #7afde1
        "coral": "252;100;77",  # #fc644d
        "pink": "255;79;161",  # #ff4fa1
        "blue": "108;155;245",  # #6c9bf5
        "yellow": "255;240;155",  # #fff09b
    },
    "slate": {
        "fg": "218;226;228",  # --fg        #dae2e4
        "gray": "138;152;158",  # --fg-dim    #8a989e
        "dimGray": "94;108;114",  # --fg-faint  #5e6c72
        "orange": "242;165;60",  # --amber     #f2a53c
        "aqua": "72;193;172",  # --teal      #48c1ac
        "coral": "248;113;113",  # #f87171
        "pink": "192;132;252",  # #c084fc
        "blue": "96;165;250",  # #60a5fa
        "yellow": "245;208;122",  # #f5d07a
    },
}

# What each colour is FOR. Add a job here; never pick a colour at a call site.
TOKENS = {
    "text": "fg",  # primary
    "muted": "gray",  # labels, secondary structure
    "dim": "dimGray",  # quoted model output, asides
    "ok": "aqua",  # passed, recovered, healthy
    "fail": "coral",  # failed, critical, alarm
    "warn": "yellow",  # degraded but not broken
    "accent": "orange",  # the ONE attention colour — spend it rarely
    "ident": "pink",  # identifiers: branches, dates, task kinds
    "link": "blue",  # references and paths off-screen
}

_V = VARS[os.environ.get("CAST_THEME", "blue")]
_RGB = {token: _V[var] for token, var in TOKENS.items()}


def _c(rgb, s, bold=False, italic=False):
    pre = f"\033[38;2;{rgb}m"
    if bold:
        pre = "\033[1m" + pre
    if italic:
        pre = "\033[3m" + pre
    return f"{pre}{s}\033[0m"


def _token(name):
    def paint(s, **kw):
        return _c(_RGB[name], s, **kw)

    paint.__name__ = name
    return paint


text = _token("text")
muted = _token("muted")
dim = _token("dim")
ok = _token("ok")
fail = _token("fail")
warn = _token("warn")
accent = _token("accent")
ident = _token("ident")
link = _token("link")


def quote(s):
    """The model's own words, set apart from the grader's assertion about them."""
    return _c(_RGB["dim"], s, italic=True)


# Severity is a meaning, so it maps to tokens rather than to colours.
SEVERITY = {"critical": "fail", "high": "warn", "med": "ident", "low": "muted", "none": "ok"}


def severity(name):
    key = name.strip()
    return _c(_RGB[SEVERITY.get(key, "muted")], name, bold=(key == "critical"))


def bar(frac, width=22, token=None):
    """A filled proportion bar, coloured by value unless a token is given.

    The empty track is '·' rather than '░': shade blocks rasterise as solid
    fills in agg, which turns an empty bar into a filled rectangle — the exact
    opposite of what it means.
    """
    filled = round(frac * width)
    tok = token or ("ok" if frac >= 0.75 else "warn" if frac >= 0.4 else "fail")
    return _c(_RGB[tok], "█" * filled) + _c(_RGB["dim"], "·" * (width - filled))
