"""Truecolor helpers, keyed to the palette published by the portfolio site.

Kept as a local module rather than a dependency so each repo's demo stays
runnable from a fresh clone with nothing installed.
"""

FG = "218;226;228"  # --fg      #dae2e4
DIM = "138;152;158"  # --fg-dim  #8a989e
FAINT = "94;108;114"  # --fg-faint #5e6c72
AMBER = "242;165;60"  # --amber   #f2a53c
TEAL = "72;193;172"  # --teal    #48c1ac
RED = "248;113;113"  # #f87171
VIOLET = "192;132;252"  # #c084fc
BLUE = "96;165;250"  # #60a5fa


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
