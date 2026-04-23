"""Tests for the Recorder — simulates JS events via the exposed callback."""

from __future__ import annotations

from unittest.mock import MagicMock

from actions import ActionScript, Recorder


def _mk_page() -> MagicMock:
    """Mock Playwright page that captures the exposed callback + init script."""
    page = MagicMock()
    exposed: dict = {}

    def expose_function(name, fn):
        exposed[name] = fn

    def add_init_script(script):
        exposed.setdefault("_init_scripts", []).append(script)

    page.expose_function.side_effect = expose_function
    page.add_init_script.side_effect = add_init_script
    # Stash for the tests to reach in and fire events.
    page._exposed = exposed
    return page


def _fire(page: MagicMock, evt: dict) -> None:
    page._exposed["__camoufox_record__"](evt)


def test_start_registers_callback_and_injects_script() -> None:
    page = _mk_page()
    rec = Recorder("login")
    rec.start(page)
    assert "__camoufox_record__" in page._exposed
    assert page._exposed["_init_scripts"]  # at least one init script
    assert "bestSelector" in page._exposed["_init_scripts"][0]


def test_click_event_appended_as_click_action() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "click", "selector": "#btn"})
    script = rec.stop()
    assert isinstance(script, ActionScript)
    assert script.actions == [{"type": "click", "selector": "#btn"}]


def test_fill_event_appended_as_fill_action() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "fill", "selector": "#u", "value": "alice"})
    script = rec.stop()
    assert script.actions == [{"type": "fill", "selector": "#u", "value": "alice"}]


def test_consecutive_fills_on_same_selector_are_coalesced() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "fill", "selector": "#u", "value": "ali"})
    _fire(page, {"kind": "fill", "selector": "#u", "value": "alice"})
    script = rec.stop()
    # Only one fill action, with the final value.
    assert script.actions == [{"type": "fill", "selector": "#u", "value": "alice"}]


def test_fills_on_different_selectors_are_separate_actions() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "fill", "selector": "#u", "value": "alice"})
    _fire(page, {"kind": "fill", "selector": "#p", "value": "hunter2"})
    script = rec.stop()
    assert len(script.actions) == 2
    assert script.actions[0]["selector"] == "#u"
    assert script.actions[1]["selector"] == "#p"


def test_select_event_appended() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "select", "selector": "#c", "value": "US"})
    assert rec.stop().actions == [{"type": "select", "selector": "#c", "value": "US"}]


def test_enter_key_appended_as_press() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "press", "key": "Enter"})
    assert rec.stop().actions == [{"type": "press", "key": "Enter"}]


def test_unknown_event_kind_is_ignored() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "rightclick", "selector": "#b"})
    assert rec.stop().actions == []


def test_stop_produces_script_with_metadata() -> None:
    page = _mk_page()
    rec = Recorder("my-macro")
    rec.start(page)
    script = rec.stop()
    assert script.name == "my-macro"
    assert script.metadata.get("source") == "recorder"


def test_events_after_stop_are_ignored() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    _fire(page, {"kind": "click", "selector": "#a"})
    rec.stop()
    _fire(page, {"kind": "click", "selector": "#b"})
    # Only the pre-stop event should be present in rec.actions.
    assert rec.actions == [{"type": "click", "selector": "#a"}]


def test_start_is_idempotent() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    rec.start(page)
    # expose_function should only be called once.
    assert page.expose_function.call_count == 1


def test_framenavigated_records_goto() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    # Simulate a main-frame navigation.
    frame = MagicMock()
    frame.parent_frame = None
    frame.url = "https://example.com/dash"
    rec._on_framenavigated(frame)
    assert rec.actions == [{"type": "goto", "url": "https://example.com/dash"}]


def test_framenavigated_ignores_iframes() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    frame = MagicMock()
    frame.parent_frame = MagicMock()  # has a parent -> iframe
    frame.url = "https://ads.example/track"
    rec._on_framenavigated(frame)
    assert rec.actions == []


def test_framenavigated_ignores_about_blank() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    frame = MagicMock()
    frame.parent_frame = None
    frame.url = "about:blank"
    rec._on_framenavigated(frame)
    assert rec.actions == []


def test_framenavigated_dedupes_same_url() -> None:
    page = _mk_page()
    rec = Recorder("t")
    rec.start(page)
    frame = MagicMock()
    frame.parent_frame = None
    frame.url = "https://example.com/x"
    rec._on_framenavigated(frame)
    rec._on_framenavigated(frame)
    assert rec.actions == [{"type": "goto", "url": "https://example.com/x"}]


def test_full_recording_sequence() -> None:
    page = _mk_page()
    rec = Recorder("signup")
    rec.start(page)

    frame = MagicMock()
    frame.parent_frame = None
    frame.url = "https://example.com/signup"
    rec._on_framenavigated(frame)

    _fire(page, {"kind": "fill", "selector": "#email", "value": "a@b.c"})
    _fire(page, {"kind": "fill", "selector": "#pw", "value": "hunter2"})
    _fire(page, {"kind": "click", "selector": "#submit"})
    _fire(page, {"kind": "press", "key": "Enter"})

    script = rec.stop()
    types = [a["type"] for a in script.actions]
    assert types == ["goto", "fill", "fill", "click", "press"]
