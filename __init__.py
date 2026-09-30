"""Dashboard Button — agent-side half (intentionally empty).

The whole plugin is the desktop half in ``desktop/plugin.js``: a sidebar row, an
in-app page and a status-bar chip for the Hermes Web Dashboard. It registers no
tools, hooks or middleware, never calls the agent and spends no tokens, so this
side exists only to make the folder a valid, installable Hermes package (and to
let the Desktop half ride along with it).
"""

from __future__ import annotations


def register(ctx):
    del ctx
