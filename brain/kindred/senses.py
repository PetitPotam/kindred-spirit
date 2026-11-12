"""New and familiar: what stands out to her.

Something she's never seen or heard stands out; the same cows every day stop being news (like
anyone, she gets used to things). Each thing she perceives has an exposure that grows while it's
around and slowly fades when it's gone, so a species she hasn't seen for a while feels a little new
again. The brain marks what's new in each snapshot; the description puts it first.
"""
import math


class Novelty:
    def __init__(self, half_life=1800.0, familiar=40.0):
        self.exposure = {}      # key -> (amount, when)
        self.half_life = half_life
        self.familiar = familiar  # snapshots of exposure until it's no longer news

    def _now_amount(self, key, now):
        amount, when = self.exposure.get(key, (0.0, now))
        return amount * math.pow(0.5, max(0.0, now - when) / self.half_life)

    def seen(self, key, now):
        """Counts one more moment of it; returns True while it's still new to her."""
        amount = self._now_amount(key, now)
        new = amount < self.familiar * 0.25
        self.exposure[key] = (min(self.familiar * 3, amount + 1.0), now)
        return new

    def annotate(self, s, now):
        """Marks what's new in a snapshot (in place): animals she sees, sounds she hears."""
        for a in (s or {}).get("animals") or []:
            if a.get("seen", True):
                a["new"] = self.seen("see:" + a.get("type", ""), now)
        for h in (s or {}).get("sounds") or []:
            h["new"] = self.seen("hear:" + h.get("what", ""), now)
        return s
