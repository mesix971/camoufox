"""
actions — macro DSL and interaction recorder for Camoufox.

Two complementary pieces:

* **DSL** (:mod:`actions.dsl`): a tiny JSON-serialisable scripting
  language for driving a Playwright sync ``Page`` — goto, wait_for,
  click, fill, type, select, scroll, screenshot, set_cookie, eval_js,
  if/repeat control flow.
* **Recorder** (:mod:`actions.recorder`): injects a JS listener into a
  live Playwright page, captures user interactions, and serialises them
  back to a :class:`ActionScript`. Pairs with :class:`ScriptStore` for
  round-tripping macros to ``~/.camoufox/macros/``.

Public API:
    Action, ActionScript, ActionResult, run_script, Recorder, ScriptStore

Typical use:
    from actions import Recorder, ScriptStore, run_script

    # record
    rec = Recorder("login-flow")
    rec.start(page)
    # ... user drives the browser ...
    script = rec.stop()
    ScriptStore().save(script)

    # replay
    script = ScriptStore().load("login-flow")
    run_script(page, script)
"""

from actions.dsl import Action, ActionResult, ActionScript, run_script
from actions.recorder import Recorder
from actions.store import ScriptStore

__all__ = [
    "Action",
    "ActionResult",
    "ActionScript",
    "Recorder",
    "ScriptStore",
    "run_script",
]

__version__ = "0.1.0"
