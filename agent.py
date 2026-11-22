"""AgentX anticipatory shopping agent (Techfest IIT Bombay 2026-27, AgentX Problem Statement 1).

    python kit/evaluate.py --agent agent.py                      # safe mode (default)
    AGENTX_MODE=bold python kit/evaluate.py --agent agent.py     # earlier, slightly riskier
    AGENTX_MAX_WASTED_SEARCHES=0 python kit/evaluate.py --agent agent.py   # one search/request

Per word:  understand the prefix (anticipate/nlu.py)  ->  narrow the fetched shelf
(anticipate/shelf.py)  ->  decide commit-or-wait from a calibrated confidence
(anticipate/policy.py). At the end: re-read the whole request and answer from it, so the final
answer is always checked against everything the shopper said.

Standard library only, no network calls. catalogue.csv is read once at start-up for vocabulary
and store-level statistics; products themselves are only ever obtained through counted searches.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from anticipate.lexicon import Lexicon, tokenize_word   # noqa: E402
from anticipate.nlu import Understander              # noqa: E402
from anticipate.policy import CommitPolicy, state_of  # noqa: E402
from anticipate.shelf import Shelf                   # noqa: E402


def _load_catalogue():
    try:
        from search import load_catalogue            # the kit's search.py, as evaluate.py uses
    except ImportError:
        sys.path.append(str(HERE / "kit"))
        from search import load_catalogue
    return load_catalogue()


class Agent:
    def __init__(self, tools, mode=None, max_wasted_searches=None):
        self.tools = tools
        catalogue = _load_catalogue()                # vocabulary + facet statistics only
        self.lex = Lexicon(catalogue)
        self.nlu = Understander(self.lex)
        self.policy = CommitPolicy(mode or os.environ.get("AGENTX_MODE", "safe"))
        # Tunable limit on wasted searches per request (a wasted search is any beyond the first).
        if max_wasted_searches is None:
            max_wasted_searches = int(os.environ.get("AGENTX_MAX_WASTED_SEARCHES", "3"))
        self.shelf = Shelf(tools, self.lex, max_searches=1 + max(0, max_wasted_searches))
        self.words, self.toks, self.committed, self.trace = [], [], None, []

    def start(self, request_id):
        self.request_id = request_id
        self.words, self.toks, self.committed, self.trace = [], [], None, []
        self.shelf.reset()

    def observe(self, word):
        self.words.append(word)
        self.toks += tokenize_word(word.replace("’", "'").replace("‘", "'"),
                                   len(self.words) - 1)
        p = self.nlu.parse(self.words, self.toks)
        hard = p.filters(hard_only=True)             # settled, trustworthy filters
        state = state_of(p)

        # Walk to the shelf as soon as we know the category, and to the new shelf if the shopper
        # corrects it: the first search is free. When the budget is a single search, hold it
        # until a commit is possible, so it is spent on the most complete reading.
        cat = hard.get("category")
        if cat and len(cat) == 1 and self.shelf.max_searches > 1 \
                and not self.shelf.covers(hard):
            self.shelf.candidates(hard)

        # Fetch candidates when a commit would be allowed if the product were unique, or
        # when the shelf we already hold covers the current reading (free).
        allowed = self.policy.allows(state)
        cands = None
        if hard and (self.shelf.covers(hard) or (allowed and self.committed is None)):
            cands = self.shelf.candidates(hard)
        n = len(cands) if cands is not None else 0

        out = {"filters": p.report(),
               "confidence": round(self.policy.confidence(state, n), 4)}
        if self.committed is None and self.policy.should_commit(state, n):
            self.committed = cands[0]["product_id"]
            out["commit"] = self.committed
        self.trace.append({"word": word, "state": state, "candidates": n,
                           "confidence": out["confidence"], "commit": out.get("commit"),
                           "filters": out["filters"]})
        return out

    def finish(self):
        """Check against the full request: answer from everything the shopper said."""
        p = self.nlu.parse(self.words, self.toks)
        filters = p.filters(include_pending=True)
        soft = [f for f, s in p.slots.items() if s.strength == "soft"]
        if p.corr_unresolved and p.corr_suspect in p.slots:
            soft.insert(0, p.corr_suspect)       # probably the value that was taken back
        words = set(re.findall(r"[a-z0-9]+", " ".join(self.words).lower()))
        pick = self.shelf.best(filters, words, soft_fields=soft)
        if pick is not None:
            return pick["product_id"]
        return self.committed
