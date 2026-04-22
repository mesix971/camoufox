"""
launcher.bridge — JSON-over-subprocess API between the Electron launcher
and the Python tooling (fpgen, proxypool, camoufox).

Design: every request is one invocation of `python -m launcher.bridge <cmd>`,
printing exactly one JSON object to stdout. Errors go to stderr and the
process exits non-zero. This keeps the renderer->main->python boundary
trivial to reason about.

Public modules:
    commands   — command handlers (list_profiles, launch_session, etc.)
    sessions   — SessionManager: tracks running Camoufox subprocesses
                 via pidfiles in ~/.camoufox/launcher/sessions/

The bridge adds a single concept not in fpgen/proxypool: Session. A Session
binds (profile_id, proxy_id, url) to a running subprocess (PID + log file).
"""

from launcher.bridge.sessions import Session, SessionManager, SessionStatus

__all__ = ["Session", "SessionManager", "SessionStatus"]
__version__ = "0.1.0"
