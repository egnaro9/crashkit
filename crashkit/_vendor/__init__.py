"""Third-party source vendored into crashkit, verbatim.

Nothing in here is crashkit's code and nothing in here may be edited. Each
vendored tree is pinned to an upstream commit in MODELDRIFT_FIDELITY.json and
the bytes are checked against that manifest by tests/test_vendor_fidelity.py,
so a local edit fails the suite instead of quietly becoming the new truth.

Why vendor at all: model-drift is not on any package index, so `pip install
git+...` was the only way to get it. A Worker runtime cannot install from git,
and a replay that has to clone a second repository is weaker evidence than one
that needs only this tree. See MODELDRIFT_FIDELITY.json for the full reason.
"""
