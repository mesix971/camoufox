"""
humanlike — humanized cursor and typing primitives for Camoufox.

Replaces `page.click(selector)` and `page.fill(selector, text)` with
calls that simulate real user behavior: cubic-Bezier mouse paths with
overshoot/correction, per-keystroke delays with occasional typos.

Public API:
    move(page, to, ...)                      # Bezier-path cursor move
    click(page, selector, ...)               # humanized click
    drag(page, from_sel, to_sel, ...)        # humanized drag
    type_text(page, selector, text, ...)     # typing with delays/typos
    fill(page, selector, text, ...)          # typing without typos
    Bezier                                   # low-level curve math
"""

from humanlike.bezier import Bezier
from humanlike.cursor import click, drag, move
from humanlike.typing import fill, type_text

__all__ = [
    "Bezier",
    "click",
    "drag",
    "fill",
    "move",
    "type_text",
]

__version__ = "0.1.0"
