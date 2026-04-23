"""
CreepJS scoring for Camoufox profiles.

Drives a Playwright-style page against https://abrahamjuliot.github.io/creepjs/
and scrapes the Trust Score and Fingerprint Score. Profiles whose scores fall
below the configured thresholds are rejected automatically via the `passed`
flag on the returned CreepJSScore dataclass.

The scraping runs entirely inside the target page via page.evaluate(); we use
try/catch per field because creepjs' DOM structure has shifted between
releases and we prefer a partial score with an error note to a crash.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# JS evaluated in-page. Returns a dict of best-effort scraped values; every
# field is wrapped in try/catch so one broken selector can't null the rest.
_SCRAPE_JS = r"""
() => {
  const out = {
    fingerprint_score: null,
    trust_score: null,
    lies_count: null,
    bot_signals: null,
    has_webdriver: null,
    consistent: null,
    errors: [],
  };

  const parsePct = (s) => {
    if (s === null || s === undefined) return null;
    const m = String(s).match(/(-?\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  };

  try {
    let el = document.querySelector('.fingerprint-id .percent');
    if (!el) el = document.querySelector('[data-score]');
    if (el) {
      const raw = el.getAttribute && el.getAttribute('data-score');
      out.fingerprint_score = parsePct(raw !== null && raw !== undefined ? raw : el.textContent);
    }
  } catch (e) { out.errors.push('fp_score: ' + e.message); }

  try {
    let el = document.querySelector('.trust-score');
    if (!el) el = document.querySelector('.trust-rating');
    if (!el) {
      // Fall back: any element whose text starts with "Trust" and contains a %.
      const nodes = document.querySelectorAll('*');
      for (const n of nodes) {
        const t = (n.textContent || '').trim();
        if (t.length < 200 && /^Trust/i.test(t) && /%/.test(t)) { el = n; break; }
      }
    }
    if (el) out.trust_score = parsePct(el.textContent);
  } catch (e) { out.errors.push('trust_score: ' + e.message); }

  try {
    let nodes = document.querySelectorAll('.lies-list li');
    if (!nodes || nodes.length === 0) nodes = document.querySelectorAll('.lie');
    out.lies_count = nodes ? nodes.length : 0;
  } catch (e) { out.errors.push('lies: ' + e.message); out.lies_count = 0; }

  try {
    let nodes = document.querySelectorAll('.bot-signal, .bot-marker');
    out.bot_signals = nodes ? nodes.length : 0;
  } catch (e) { out.errors.push('bot_signals: ' + e.message); out.bot_signals = 0; }

  try {
    out.has_webdriver = !!navigator.webdriver;
  } catch (e) { out.errors.push('webdriver: ' + e.message); out.has_webdriver = false; }

  try {
    const badge = document.querySelector('.fp-id-consistent, .consistent-badge');
    out.consistent = !!badge;
  } catch (e) { out.errors.push('consistent: ' + e.message); out.consistent = false; }

  return out;
}
"""

# Selector we wait on before scraping — whichever appears first indicates
# creepjs has finished computing. We pick a broad CSS selector; the default
# `.fingerprint-id` element is present once the async hashing completes.
_READY_SELECTOR = ".fingerprint-id .percent, [data-score], .trust-score"


@dataclass
class CreepJSScore:
    """Result of scoring a profile against creepjs.com."""

    profile_id: str
    fingerprint_score: float = 0.0  # 0..100
    trust_score: float = 0.0  # 0..100
    lies_count: int = 0
    bot_signals: int = 0
    has_webdriver: bool = False
    consistent: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
    scored_at: str = field(default_factory=_utc_now_iso)
    error: Optional[str] = None
    # These are set by Scorer after applying thresholds; kept here so the
    # dataclass is self-describing and JSON-serializable.
    passed: bool = False
    pass_fp_threshold: float = 75.0
    pass_trust_threshold: float = 70.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Scorer:
    """Run a profile against creepjs.com and score it."""

    def __init__(
        self,
        pass_fp_threshold: float = 75.0,
        pass_trust_threshold: float = 70.0,
        url: str = "https://abrahamjuliot.github.io/creepjs/",
        timeout: float = 60.0,
    ) -> None:
        if pass_fp_threshold < 0 or pass_fp_threshold > 100:
            raise ValueError("pass_fp_threshold must be 0..100")
        if pass_trust_threshold < 0 or pass_trust_threshold > 100:
            raise ValueError("pass_trust_threshold must be 0..100")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        self.pass_fp_threshold = float(pass_fp_threshold)
        self.pass_trust_threshold = float(pass_trust_threshold)
        self.url = url
        self.timeout = float(timeout)

    # --- public API ---

    def score(self, page: Any, profile_id: str) -> CreepJSScore:
        """Score a profile. `page` is any duck-typed Playwright-like page.

        Expected page API (all synchronous):
            page.goto(url, timeout=<ms>)
            page.wait_for_selector(css, timeout=<ms>)
            page.evaluate(js) -> value

        On any exception a CreepJSScore with `error` set and `passed=False`
        is returned — we never raise to the caller.
        """
        result = CreepJSScore(
            profile_id=profile_id,
            pass_fp_threshold=self.pass_fp_threshold,
            pass_trust_threshold=self.pass_trust_threshold,
        )

        timeout_ms = int(self.timeout * 1000)

        try:
            page.goto(self.url, timeout=timeout_ms)
        except Exception as e:
            result.error = f"goto failed: {type(e).__name__}: {e}"
            result.passed = False
            return result

        try:
            page.wait_for_selector(_READY_SELECTOR, timeout=timeout_ms)
        except Exception as e:
            result.error = f"creepjs never loaded: {type(e).__name__}: {e}"
            result.passed = False
            return result

        try:
            scraped = page.evaluate(_SCRAPE_JS)
        except Exception as e:
            result.error = f"scrape failed: {type(e).__name__}: {e}"
            result.passed = False
            return result

        if not isinstance(scraped, dict):
            result.error = f"scrape returned {type(scraped).__name__}, expected dict"
            result.passed = False
            result.raw = {"scraped": scraped}
            return result

        result.raw = dict(scraped)

        # Copy fields with per-field fallbacks. Bad/missing fields don't kill
        # the score — they just record an error note and stay at defaults.
        errors = []
        try:
            fp = scraped.get("fingerprint_score")
            result.fingerprint_score = float(fp) if fp is not None else 0.0
        except (TypeError, ValueError):
            errors.append("fingerprint_score unparseable")

        try:
            ts = scraped.get("trust_score")
            result.trust_score = float(ts) if ts is not None else 0.0
        except (TypeError, ValueError):
            errors.append("trust_score unparseable")

        try:
            lc = scraped.get("lies_count")
            result.lies_count = int(lc) if lc is not None else 0
        except (TypeError, ValueError):
            errors.append("lies_count unparseable")

        try:
            bs = scraped.get("bot_signals")
            result.bot_signals = int(bs) if bs is not None else 0
        except (TypeError, ValueError):
            errors.append("bot_signals unparseable")

        result.has_webdriver = bool(scraped.get("has_webdriver"))
        result.consistent = bool(scraped.get("consistent"))

        # Surface any JS-side errors too.
        js_errs = scraped.get("errors") or []
        if js_errs:
            errors.extend(f"js: {e}" for e in js_errs)

        if errors:
            result.error = "; ".join(errors)

        result.passed = self._passes(result)
        return result

    # --- internal ---

    def _passes(self, r: CreepJSScore) -> bool:
        if r.has_webdriver:
            return False
        if r.fingerprint_score < self.pass_fp_threshold:
            return False
        if r.trust_score < self.pass_trust_threshold:
            return False
        return True
