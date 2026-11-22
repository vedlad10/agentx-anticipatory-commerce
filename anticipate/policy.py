"""When is it safe to show the shopper a product before they finish speaking?

A commit can only go wrong if the words still to come change a filter we relied on. In this
domain that happens through corrections ("size M. no, change that to XL"); a late addition can
only narrow the search, never move it off a product that is already the only match. So the
confidence of a commit is the probability that no correction is still on its way, and that
depends on *where we are in the request*:

  twist-done   a correction (or a late addition) has already landed: shoppers make one
  tail         the filters are over and the polite tail has started ("for my dad", "thanks")
  past-value   one or more words after the deciding value, but the request is still going
  at-value     the deciding value was just said: an immediate "oops, I mean..." is common
  unsettled    a correction/negation is half-said, or the next word may start one ("I", "make")

The per-state risk below was measured on dev.jsonl by tools/calibrate.py: for each request and
state, the first word at which one product is the only match, counted wrong if that product is
not the target, then Jeffreys-smoothed, (wrong + 0.5) / (seen + 1). A commit is made when
confidence = (1 - risk) / #matching products clears the threshold. The default threshold admits
only states with no observed wrong commit; "bold" trades a small, measured risk for earliness.
"""
from __future__ import annotations

# risk = P(the only matching product is NOT the final target | state)
# dev.jsonl, wrong/seen: tail 0/121, twist-done 0/99, past-value 2/48,
# past-value-unknown 1/11, at-value 18/194, unsettled 21/29
RISK = {
    "tail": 0.004,
    "twist-done": 0.005,
    "past-value": 0.051,
    "at-value": 0.095,
    "past-value-unknown": 0.125,
    "unsettled": 1.0,       # a correction is in progress: never commit, whatever the count
}

THRESHOLDS = {
    "safe": 0.99,       # default: commit only where dev showed zero wrong commits
    "bold": 0.94,       # also commit mid-request, one word after the deciding value
}


def state_of(p):
    """Classify the parse of the words so far into one of the RISK states."""
    if p.blocked() or "corr-prefix" in p.pending:
        return "unsettled"
    if p.corr_done or p.late_done:
        return "twist-done"
    if p.tail:
        return "tail"
    if p.n_words - 1 > p.value_end:
        last = p.items[-1] if p.items else None
        if last is not None and last.kind == "UNK":
            return "past-value-unknown"
        return "past-value"
    return "at-value"


class CommitPolicy:
    def __init__(self, mode="safe", threshold=None):
        self.mode = mode
        self.threshold = THRESHOLDS.get(mode, THRESHOLDS["safe"]) if threshold is None \
            else threshold

    def allows(self, state):
        """Could a commit be made in this state if exactly one product matched?"""
        return 1.0 - RISK[state] >= self.threshold

    @staticmethod
    def confidence(state, n_candidates):
        """P(the top candidate is the final target): the state's safety, shared equally among
        the products that still match."""
        return (1.0 - RISK[state]) / n_candidates if n_candidates else 0.0

    def should_commit(self, state, n_candidates):
        return n_candidates == 1 and self.confidence(state, 1) >= self.threshold
