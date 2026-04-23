"""Tests for the Action DSL executor and script type."""

from __future__ import annotations

from unittest.mock import MagicMock

from actions import ActionResult, ActionScript, run_script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_page() -> MagicMock:
    """Mock Playwright page that supports all the methods our handlers call."""
    page = MagicMock()
    page.context = MagicMock()
    page.mouse = MagicMock()
    page.keyboard = MagicMock()
    return page


def _script(*actions, name: str = "t") -> ActionScript:
    return ActionScript(name=name, actions=list(actions))


# ---------------------------------------------------------------------------
# Per-action dispatch
# ---------------------------------------------------------------------------


def test_goto_calls_page_goto_with_default_wait_until() -> None:
    page = _mk_page()
    results = run_script(page, _script({"type": "goto", "url": "https://x.test"}))
    page.goto.assert_called_once_with("https://x.test", wait_until="domcontentloaded")
    assert results[0].ok
    assert results[0].duration_ms >= 0


def test_goto_respects_explicit_wait_until_and_timeout() -> None:
    page = _mk_page()
    run_script(page, _script({
        "type": "goto", "url": "https://x.test",
        "wait_until": "load", "timeout_ms": 5000,
    }))
    page.goto.assert_called_once_with("https://x.test", wait_until="load", timeout=5000)


def test_wait_sleeps(monkeypatch) -> None:
    page = _mk_page()
    called: list = []
    monkeypatch.setattr("actions.dsl.time.sleep", lambda s: called.append(s))
    run_script(page, _script({"type": "wait", "seconds": 0.25}))
    assert called == [0.25]


def test_wait_for_calls_wait_for_selector() -> None:
    page = _mk_page()
    run_script(page, _script({
        "type": "wait_for", "selector": ".ready", "timeout_ms": 1234,
    }))
    page.wait_for_selector.assert_called_once_with(".ready", timeout=1234)


def test_wait_for_url_calls_wait_for_url() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "wait_for_url", "pattern": "checkout"}))
    page.wait_for_url.assert_called_once_with("checkout")


def test_click_default_uses_page_click() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "click", "selector": "#btn"}))
    page.click.assert_called_once_with("#btn")


def test_click_humanlike_uses_humanlike_module_when_available() -> None:
    page = _mk_page()
    hl = MagicMock()
    run_script(page,
               _script({"type": "click", "selector": "#btn", "humanlike": True}),
               humanlike_module=hl)
    hl.click.assert_called_once_with(page, "#btn")
    page.click.assert_not_called()


def test_click_humanlike_falls_back_when_module_missing() -> None:
    page = _mk_page()
    # Pass an object without `click` attribute — should fall back.
    class NoClick:
        pass
    run_script(page,
               _script({"type": "click", "selector": "#btn", "humanlike": True}),
               humanlike_module=NoClick())
    page.click.assert_called_once_with("#btn")


def test_fill_default_calls_page_fill() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "fill", "selector": "#u", "value": "alice"}))
    page.fill.assert_called_once_with("#u", "alice")


def test_type_with_delay() -> None:
    page = _mk_page()
    run_script(page, _script({
        "type": "type", "selector": "#q", "text": "hi", "delay_ms": 50,
    }))
    page.type.assert_called_once_with("#q", "hi", delay=50)


def test_press_without_selector_uses_keyboard() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "press", "key": "Enter"}))
    page.keyboard.press.assert_called_once_with("Enter")
    page.press.assert_not_called()


def test_press_with_selector_uses_page_press() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "press", "key": "Tab", "selector": "#q"}))
    page.press.assert_called_once_with("#q", "Tab")


def test_select_calls_select_option() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "select", "selector": "#c", "value": "US"}))
    page.select_option.assert_called_once_with("#c", "US")


def test_check_calls_page_check() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "check", "selector": "#tos"}))
    page.check.assert_called_once_with("#tos")


def test_scroll_down_uses_mouse_wheel() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "scroll", "direction": "down", "pixels": 800}))
    page.mouse.wheel.assert_called_once_with(0, 800)


def test_scroll_up_negative() -> None:
    page = _mk_page()
    run_script(page, _script({"type": "scroll", "direction": "up", "pixels": 300}))
    page.mouse.wheel.assert_called_once_with(0, -300)


def test_screenshot_passes_path() -> None:
    page = _mk_page()
    results = run_script(page, _script({"type": "screenshot", "path": "out.png"}))
    page.screenshot.assert_called_once_with(path="out.png")
    assert results[0].output == {"path": "out.png"}


def test_set_cookie_calls_context_add_cookies() -> None:
    page = _mk_page()
    run_script(page, _script({
        "type": "set_cookie", "name": "sid", "value": "abc", "domain": ".x.test",
        "secure": True,
    }))
    page.context.add_cookies.assert_called_once()
    (cookies,), _ = page.context.add_cookies.call_args
    assert cookies == [{
        "name": "sid", "value": "abc", "domain": ".x.test",
        "path": "/", "secure": True,
    }]


def test_eval_js_returns_value_in_output() -> None:
    page = _mk_page()
    page.evaluate.return_value = 42
    results = run_script(page, _script({"type": "eval_js", "code": "1+1"}))
    page.evaluate.assert_called_once_with("1+1")
    assert results[0].output == {"value": 42}


def test_log_records_message() -> None:
    page = _mk_page()
    results = run_script(page, _script({"type": "log", "message": "hello"}))
    assert results[0].ok
    assert results[0].output == {"message": "hello"}


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


def test_repeat_runs_n_times() -> None:
    page = _mk_page()
    script = _script({
        "type": "repeat", "times": 3,
        "actions": [{"type": "click", "selector": "#b"}],
    })
    results = run_script(page, script)
    assert page.click.call_count == 3
    # 1 repeat + 3 inner clicks = 4 results
    assert len(results) == 4
    assert all(r.ok for r in results)


def test_if_then_branch_runs_when_condition_true() -> None:
    page = _mk_page()
    page.query_selector.return_value = object()  # element exists
    run_script(page, _script({
        "type": "if",
        "condition": {"selector_exists": ".error"},
        "then": [{"type": "click", "selector": "#retry"}],
        "else": [{"type": "click", "selector": "#ok"}],
    }))
    page.click.assert_called_once_with("#retry")


def test_if_else_branch_runs_when_condition_false() -> None:
    page = _mk_page()
    page.query_selector.return_value = None
    run_script(page, _script({
        "type": "if",
        "condition": {"selector_exists": ".error"},
        "then": [{"type": "click", "selector": "#retry"}],
        "else": [{"type": "click", "selector": "#ok"}],
    }))
    page.click.assert_called_once_with("#ok")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_on_error_abort_stops_further_actions() -> None:
    page = _mk_page()
    page.click.side_effect = RuntimeError("boom")
    results = run_script(page, _script(
        {"type": "click", "selector": "#bad"},
        {"type": "log", "message": "should not run"},
    ))
    assert len(results) == 1
    assert not results[0].ok
    assert "RuntimeError" in (results[0].error or "")


def test_on_error_continue_runs_remaining_actions() -> None:
    page = _mk_page()
    page.click.side_effect = RuntimeError("boom")
    results = run_script(page, _script(
        {"type": "click", "selector": "#bad", "on_error": "continue"},
        {"type": "log", "message": "still runs"},
    ))
    assert len(results) == 2
    assert results[0].ok is False
    assert results[1].ok is True


def test_unknown_action_type_returns_error_result() -> None:
    page = _mk_page()
    results = run_script(page, _script({"type": "bogus"}))
    assert len(results) == 1
    assert results[0].ok is False
    assert "unknown action type" in (results[0].error or "")


def test_result_is_actionresult_dataclass() -> None:
    page = _mk_page()
    results = run_script(page, _script({"type": "log", "message": "x"}))
    assert isinstance(results[0], ActionResult)
    d = results[0].to_dict()
    assert d["ok"] is True
    assert d["action"]["type"] == "log"


# ---------------------------------------------------------------------------
# ActionScript (de)serialisation & validation
# ---------------------------------------------------------------------------


def test_from_json_round_trip() -> None:
    s = ActionScript(
        name="login",
        actions=[{"type": "goto", "url": "https://x.test"}],
        metadata={"author": "alice"},
    )
    raw = s.to_json()
    s2 = ActionScript.from_json(raw)
    assert s2.name == s.name
    assert s2.actions == s.actions
    assert s2.metadata == s.metadata


def test_validate_ok() -> None:
    s = ActionScript(name="ok", actions=[
        {"type": "goto", "url": "u"},
        {"type": "click", "selector": "#b"},
    ])
    assert s.validate() == []


def test_validate_catches_missing_required_field() -> None:
    s = ActionScript(name="bad", actions=[{"type": "goto"}])  # no url
    errors = s.validate()
    assert any("missing required key 'url'" in e for e in errors)


def test_validate_catches_unknown_type() -> None:
    s = ActionScript(name="bad", actions=[{"type": "bogus"}])
    errors = s.validate()
    assert any("unknown action type" in e for e in errors)


def test_validate_recurses_into_repeat() -> None:
    s = ActionScript(name="bad", actions=[{
        "type": "repeat", "times": 2,
        "actions": [{"type": "click"}],  # missing selector
    }])
    errors = s.validate()
    assert any("missing required key 'selector'" in e for e in errors)


def test_validate_empty_name() -> None:
    s = ActionScript(name="", actions=[])
    errors = s.validate()
    assert any("name" in e for e in errors)
