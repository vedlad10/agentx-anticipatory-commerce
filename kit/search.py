"""A simple local search over catalogue.csv.

    from search import search
    search("black running shoes", {"size": "9", "max_price": 2000}, k=5)

Filters are exact and case-insensitive: category, colour, size, brand, plus max_price and
min_price in rupees. The query ranks what the filters let through by how many of its words
appear in a product's title, brand, category, colour, size and description; ties go to the
cheaper product. No stemming, no synonyms, no meaning: that part is up to you.
"""
import csv
import re
from pathlib import Path

CATALOGUE_PATH = Path(__file__).with_name("catalogue.csv")
FILTER_FIELDS = ("category", "colour", "size", "brand")

_catalogue = None


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def load_catalogue(path=CATALOGUE_PATH):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["price"] = int(r["price"])
    return rows


def _index():
    global _catalogue
    if _catalogue is None:
        _catalogue = [(p, set(tokens(" ".join(str(p[k]) for k in
                      ("title", "brand", "category", "colour", "size", "description")))))
                      for p in load_catalogue()]
    return _catalogue


def search(query="", filters=None, k=10):
    """Return up to k products (dicts) that pass every filter, best keyword match first."""
    filters = {key: v for key, v in (filters or {}).items() if v is not None}
    unknown = set(filters) - set(FILTER_FIELDS) - {"max_price", "min_price"}
    if unknown:
        raise ValueError(f"unknown filters: {sorted(unknown)}")
    want = {key: str(filters[key]).lower() for key in FILTER_FIELDS if key in filters}
    q = set(tokens(query))
    hits = []
    for p, words in _index():
        if any(p[key].lower() != v for key, v in want.items()):
            continue
        if "max_price" in filters and p["price"] > filters["max_price"]:
            continue
        if "min_price" in filters and p["price"] < filters["min_price"]:
            continue
        hits.append((-len(q & words), p["price"], p))
    hits.sort(key=lambda h: h[:2])
    return [dict(p, score=-s) for s, _, p in hits[:k]]


if __name__ == "__main__":
    import sys
    for p in search(" ".join(sys.argv[1:]) or "black running shoes", k=5):
        print(p["product_id"], p["price"], p["size"], p["title"], f"(score {p['score']})")
