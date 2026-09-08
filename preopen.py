"""Compatibility import for older entry points.

The maintained implementation lives in :mod:`core.preopen`. Keeping this
small bridge prevents the legacy root module from drifting back to obsolete
fixed pricing thresholds.
"""

from core.preopen import *  # noqa: F401,F403
