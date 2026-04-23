"""
Action recorder — injects a JS event listener into a Playwright page and
serialises user interactions back into DSL action dicts.

The recorder exposes a Python callback (``__camoufox_record__``) that the
injected JS invokes on every observed interaction. Each event is
translated into the matching DSL action and accumulated in
``self.actions``; calling :meth:`Recorder.stop` packages everything into
an :class:`ActionScript` the caller can save to disk via the sibling
:class:`ScriptStore`.

Selector generation is deliberately minimal — enough to replay the
recorded session reliably without reimplementing a Playwright-style
picker:

    1. ``#id`` when the target has an id
    2. ``<tag>[name="..."]`` when it has a name attribute
    3. ``<tag>[data-testid="..."]``
    4. text-based (``<tag>:has-text("...")``) for <=40 char labels
    5. ``<tag>:nth-of-type(n)`` as a last resort

Recorded events:

    click       -> {"type": "click", "selector": "..."}
    input/blur  -> {"type": "fill",  "selector": "...", "value": "..."}
    change      -> {"type": "select","selector": "...", "value": "..."}
    Enter key   -> {"type": "press", "key": "Enter"}
    navigation  -> {"type": "goto",  "url": "..."}  (via page.on framenavigated)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from actions.dsl import ActionScript


# JavaScript installed at document-start on every frame. It listens for
# the core interaction events and posts a sanitised payload back to
# Python via the `__camoufox_record__` binding created with
# `page.expose_function`.
RECORDER_JS = r"""
(() => {
  if (window.__camoufox_recorder_installed__) return;
  window.__camoufox_recorder_installed__ = true;

  function bestSelector(el) {
    if (!el || el.nodeType !== 1) return null;
    if (el.id) return '#' + el.id;
    const tag = el.tagName.toLowerCase();
    const name = el.getAttribute && el.getAttribute('name');
    if (name) return tag + '[name="' + name + '"]';
    const testid = el.getAttribute && el.getAttribute('data-testid');
    if (testid) return tag + '[data-testid="' + testid + '"]';
    const text = (el.innerText || el.textContent || '').trim();
    if (text && text.length <= 40 && /^[\x20-\x7e]+$/.test(text)) {
      const safe = text.replace(/"/g, '\\"');
      return tag + ':has-text("' + safe + '")';
    }
    // nth-of-type fallback
    const parent = el.parentNode;
    if (!parent) return tag;
    let n = 1;
    for (const sib of parent.children) {
      if (sib === el) break;
      if (sib.tagName === el.tagName) n++;
    }
    return tag + ':nth-of-type(' + n + ')';
  }

  function send(evt) {
    try {
      if (window.__camoufox_record__) window.__camoufox_record__(evt);
    } catch (e) { /* swallow — recorder must never break the page */ }
  }

  document.addEventListener('click', (e) => {
    const sel = bestSelector(e.target);
    if (!sel) return;
    send({kind: 'click', selector: sel});
  }, true);

  // Debounce fills: emit only the final value on blur.
  document.addEventListener('blur', (e) => {
    const el = e.target;
    if (!el || !('value' in el)) return;
    const tag = (el.tagName || '').toLowerCase();
    if (tag !== 'input' && tag !== 'textarea') return;
    const sel = bestSelector(el);
    if (!sel) return;
    send({kind: 'fill', selector: sel, value: el.value});
  }, true);

  document.addEventListener('change', (e) => {
    const el = e.target;
    if (!el) return;
    const tag = (el.tagName || '').toLowerCase();
    if (tag !== 'select') return;
    const sel = bestSelector(el);
    if (!sel) return;
    send({kind: 'select', selector: sel, value: el.value});
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      send({kind: 'press', key: 'Enter'});
    }
  }, true);
})();
"""


class Recorder:
    """Capture user interactions against a Playwright page into DSL actions."""

    def __init__(self, script_name: str):
        self.script_name = script_name
        self.actions: List[Dict[str, Any]] = []
        self._page: Any = None
        self._started = False
        self._stopped = False
        self._last_url: Optional[str] = None
        # Used to suppress the page.on("framenavigated") event that fires
        # for the very first page load if the page is already on a URL.
        self._seen_first_nav = False

    # --- lifecycle ---

    def start(self, page: Any) -> None:
        """Install listeners on ``page``. Idempotent."""
        if self._started:
            return
        self._page = page
        # Expose a Python-side callback invoked from the injected JS.
        page.expose_function("__camoufox_record__", self._on_event)
        # Inject the recorder script on every navigation so it survives
        # SPA-style route changes.
        page.add_init_script(RECORDER_JS)
        # Navigation events come through Playwright directly.
        try:
            page.on("framenavigated", self._on_framenavigated)
        except Exception:
            pass
        self._started = True

    def stop(self) -> ActionScript:
        """Stop capturing and return the recorded script."""
        self._stopped = True
        # Best-effort removal of the navigation listener.
        if self._page is not None:
            try:
                self._page.remove_listener("framenavigated", self._on_framenavigated)
            except Exception:
                pass
        return ActionScript(
            name=self.script_name,
            actions=list(self.actions),
            metadata={"source": "recorder"},
        )

    # --- event handlers ---

    def _on_event(self, evt: Dict[str, Any]) -> None:
        """Callback invoked by the injected JS via expose_function."""
        if self._stopped or not isinstance(evt, dict):
            return
        kind = evt.get("kind")
        if kind == "click":
            self.actions.append({"type": "click", "selector": evt.get("selector", "")})
        elif kind == "fill":
            # Collapse consecutive fills on the same selector — users
            # typically type, blur, re-focus, correct a typo, then blur
            # again. We only want the final value.
            selector = evt.get("selector", "")
            value = evt.get("value", "")
            if (self.actions
                    and self.actions[-1].get("type") == "fill"
                    and self.actions[-1].get("selector") == selector):
                self.actions[-1]["value"] = value
            else:
                self.actions.append({"type": "fill", "selector": selector, "value": value})
        elif kind == "select":
            self.actions.append({
                "type": "select",
                "selector": evt.get("selector", ""),
                "value": evt.get("value", ""),
            })
        elif kind == "press":
            key = evt.get("key", "")
            if key:
                self.actions.append({"type": "press", "key": key})

    def _on_framenavigated(self, frame: Any) -> None:
        """Record top-level navigations as goto actions."""
        if self._stopped:
            return
        # Only record main-frame navigations; iframe navigations are noise.
        try:
            if getattr(frame, "parent_frame", None) is not None:
                return
            url = frame.url
        except Exception:
            return
        if not url or url == "about:blank":
            return
        if url == self._last_url:
            return
        self._last_url = url
        self.actions.append({"type": "goto", "url": url})
