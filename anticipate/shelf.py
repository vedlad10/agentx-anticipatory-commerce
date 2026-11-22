"""Product lookups through counted searches: fetch a shelf once, then narrow it locally.

A human sales assistant walks to the right shelf as soon as they hear "running shoes", then
picks from it as the size and colour arrive. The Shelf does the same: one search fetches every
product under a few broad, stable filters (usually just the category, at most ~90 products);
every later word only narrows that list on the client, which costs no further searches. A new
search runs only when a filter the shelf was fetched with changes (a corrected category) or the
shelf was cut off by the page size.

Every search goes through `tools.search`, so the evaluator counts all of them. `max_searches`
caps the searches spent on one request (the tunable limit on wasted searches).
"""
from __future__ import annotations

import re

SHELF_K = 100          # page size of one search; the largest category has 89 products
STABILITY = ("category", "brand", "colour", "size")   # least -> most often corrected


def matches(product, filters):
    """Does a product satisfy canonical filters (category may be a tuple of options)?"""
    for key, want in filters.items():
        if want is None:
            continue
        if key == "category":
            options = want if isinstance(want, tuple) else (want,)
            if product["category"] not in options:
                return False
        elif key == "max_price":
            if product["price"] > want:
                return False
        elif key == "min_price":
            if product["price"] < want:
                return False
        elif str(product.get(key, "")).lower() != str(want).lower():
            return False
    return True


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def keyword_score(product, words):
    """How many request words appear in a product's text (tie-breaking only)."""
    text = _tokens(" ".join(str(product.get(k, "")) for k in
                            ("title", "brand", "category", "colour", "size", "description")))
    return len(words & text)


class Shelf:
    def __init__(self, tools, lexicon, k=SHELF_K, max_searches=4):
        self.tools = tools
        self.lex = lexicon
        self.k = k
        self.max_searches = max_searches   # tunable cap on searches per request
        self.reset()

    def reset(self):
        self.key = None          # filters the current shelf was fetched with
        self.items = None
        self.complete = False
        self.searches = 0
        self._cache = {}         # filters -> matching products on the current shelf

    # -- which filters to fetch a shelf with ------------------------------------------------
    def key_for(self, filters):
        """Broad, stable filters to fetch with, and whether their result should fit one page.

        Sizes come from store-level counts: exact for a single facet ("89 track pants"),
        an independence estimate for a combination, where we keep a 2x margin.
        """
        key = {}
        est = float(self.lex.n_products)
        fits = False
        for field in STABILITY:
            value = filters.get(field)
            if value is None:
                continue
            if field == "category":
                if not isinstance(value, tuple) or len(value) != 1:
                    continue                     # "shoes" = two categories: filter locally
                value = value[0]
            key[field] = value
            est *= self.lex.facet_share[field].get(value, 0.0)
            fits = est < self.k if len(key) == 1 else est < self.k / 2
            if fits:
                break
        return (key or None), fits

    def covers(self, filters):
        """True if the shelf holds every product that matches `filters`."""
        if self.items is None or not self.complete:
            return False
        for field, value in self.key.items():
            want = filters.get(field)
            if field == "category":
                if not (isinstance(want, tuple) and len(want) == 1 and want[0] == value):
                    return False
            elif want is None or str(want).lower() != str(value).lower():
                return False
        return True

    def can_search(self):
        return self.searches < self.max_searches

    def fetch(self, filters, force=False):
        """Run one search. Unless forced, skip a search that would overflow the page: it
        would come back cut off, so it is better to wait for one more filter."""
        key, fits = self.key_for(filters)
        if key is None or not self.can_search() or not (fits or force):
            return False
        if self.items is not None and key == self.key:
            return False                 # the same search would return the same page
        hits = self.tools.search(query="", filters=key, k=self.k)
        self.searches += 1
        self.key, self.items = key, hits
        self.complete = len(hits) < self.k
        self._cache = {}
        return True

    # -- what the agent asks ----------------------------------------------------------------
    def candidates(self, filters, fetch=True, force=False):
        """Products matching `filters`, or None if we cannot know without a search we skip."""
        if not filters:
            return None
        if not self.covers(filters):
            if not fetch or not self.fetch(filters, force) or not self.complete:
                return None
        key = tuple(sorted((k, str(v)) for k, v in filters.items()))
        if key not in self._cache:
            self._cache[key] = [p for p in self.items if matches(p, filters)]
        return self._cache[key]

    def best(self, filters, words, soft_fields=()):
        """The final answer for the full request, relaxing filters if nothing matches.

        Relaxation drops the least trustworthy filters first: soft guesses, then price, then
        size, colour, brand and, last, the category. Ties among several matches go to the
        product whose text shares most words with the request, then the cheaper one.
        """
        order = [f for f in soft_fields] + ["min_price", "max_price", "size", "colour", "brand",
                                            "category"]
        tried = dict(filters)
        attempts = [dict(tried)]
        for field in order:
            if field in tried:
                tried = {k: v for k, v in tried.items() if k != field}
                attempts.append(dict(tried))
        for f in attempts:
            if not f:
                break
            cands = self.candidates(f, force=True)      # last chance: search even if broad
            if cands is None and self.items:
                # the page was cut off or the search budget is spent: best effort from what
                # we already hold
                cands = [p for p in self.items if matches(p, f)]
            if cands:
                return max(cands, key=lambda p: (keyword_score(p, set(words)), -p["price"]))
        return None
