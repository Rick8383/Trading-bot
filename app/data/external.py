"""External-signal providers: macro, news, social sentiment.

These wrap data sources that are *not* price/volume. Phase 5 ships offline-safe,
deterministic defaults:

  * Neutral providers return 0 (no opinion, low confidence) — safe placeholder.
  * Static providers accept an injected dict — for tests and manual overrides.

Real feeds (FRED/central-bank calendars for macro, a news API for headlines,
Reddit/X for social) plug in by subclassing and implementing ``score``. Until
then these agents abstain rather than fabricate a signal, honoring the founding
rule: no unexplained or invented inputs.
"""

from __future__ import annotations


class SignalProvider:
    """Base: return (score in [-100,100], confidence in [0,1], reason)."""

    name = "external"

    def score(self, asset: str, context: dict | None = None) -> tuple[float, float, str]:
        return 0.0, 0.2, "no external signal (neutral)"


class NeutralProvider(SignalProvider):
    """Always neutral — the safe default when no feed is connected."""


class StaticProvider(SignalProvider):
    """Returns injected per-asset scores. Useful for tests / manual overrides.

    ``scores`` maps asset -> score in [-100, 100]. ``default`` is used for
    unknown assets.
    """

    def __init__(self, scores: dict[str, float], confidence: float = 0.5, default: float = 0.0,
                 name: str = "static"):
        self.scores = scores
        self.confidence = confidence
        self.default = default
        self.name = name

    def score(self, asset: str, context: dict | None = None) -> tuple[float, float, str]:
        s = float(self.scores.get(asset, self.default))
        return max(-100.0, min(100.0, s)), self.confidence, f"{self.name}={s:+.0f}"
