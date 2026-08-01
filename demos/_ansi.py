"""Truecolor helpers, keyed to a named palette.

Two themes ship. `blue` is the default — deep blue ground, blue-white body, and
orange held back for the single thing the reader should look at. That restraint
is the point: an accent used everywhere stops being an accent. `slate` is the
portfolio's own CSS custom properties, for when a cast should dissolve into the
page instead of reading as a device sitting on it. Select with CAST_THEME.

Kept as a local module rather than a dependency so each repo's demo stays
runnable from a fresh clone with nothing installed.
"""

import os

_THEMES = {
    "slate": dict(
        FG="218;226;228",    # --fg        #dae2e4
        DIM="138;152;158",   # --fg-dim    #8a989e
        FAINT="94;108;114",  # --fg-faint  #5e6c72
        AMBER="242;165;60",  # --amber     #f2a53c
        TEAL="72;193;172",   # --teal      #48c1ac
        RED="248;113;113",   # #f87171
        VIOLET="192;132;252",  # #c084fc
        BLUE="96;165;250",   # #60a5fa
    ),
    "blue": dict(
        FG="192;201;229",    # #c0c9e5  cool blue-white body
        DIM="126;163;199",   # #7ea3c7
        FAINT="85;119;155",  # #55779b
        AMBER="249;115;22",  # #f97316  orange, used sparingly
        TEAL="122;253;225",  # #7afde1  aqua
        RED="252;100;77",    # #fc644d  coral
        VIOLET="255;79;161",  # #ff4fa1
        BLUE="108;155;245",  # #6c9bf5
    ),
}

_P = _THEMES[os.environ.get("CAST_THEME", "blue")]
FG = _P["FG"]
DIM = _P["DIM"]
FAINT = _P["FAINT"]
AMBER = _P["AMBER"]
TEAL = _P["TEAL"]
RED = _P["RED"]
VIOLET = _P["VIOLET"]
BLUE = _P["BLUE"]



def _c(rgb, s, bold=False, italic=False):
    pre = f"\033[38;2;{rgb}m"
    if bold:
        pre = "\033[1m" + pre
    if italic:
        pre = "\033[3m" + pre
    return f"{pre}{s}\033[0m"


def fg(s, **k):
    return _c(FG, s, **k)


def dim(s, **k):
    return _c(DIM, s, **k)


def faint(s, **k):
    return _c(FAINT, s, **k)


def amber(s, **k):
    return _c(AMBER, s, **k)


def teal(s, **k):
    return _c(TEAL, s, **k)


def red(s, **k):
    return _c(RED, s, **k)


def violet(s, **k):
    return _c(VIOLET, s, **k)


def blue(s, **k):
    return _c(BLUE, s, **k)


SEVERITY = {"critical": RED, "high": AMBER, "med": VIOLET, "low": DIM, "none": TEAL}


def severity(name):
    key = name.strip()
    return _c(SEVERITY.get(key, DIM), name, bold=(key == "critical"))


def bar(frac, width=22, rgb=None):
    """A filled proportion bar. Colored by value unless rgb is given.

    The empty track is '·' rather than '░': shade blocks rasterise as solid
    fills in agg, which turns an empty bar into a filled rectangle — the exact
    opposite of what it means.
    """
    filled = round(frac * width)
    rgb = rgb or (TEAL if frac >= 0.75 else AMBER if frac >= 0.4 else RED)
    return _c(rgb, "█" * filled) + _c(FAINT, "·" * (width - filled))
