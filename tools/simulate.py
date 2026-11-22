"""Offline analysis: replay every request word by word and record what the parser knew.

For analysis only (it matches against the whole catalogue in memory, which the real agent
does not do: the agent looks products up through counted searches).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit"))
sys.stdout.reconfigure(encoding="utf-8")

from search import load_catalogue                      # noqa: E402
from anticipate.lexicon import Lexicon                  # noqa: E402
from anticipate.nlu import Understander                 # noqa: E402

CAT = load_catalogue()
LEX = Lexicon(CAT)
NLU = Understander(LEX)


def matches(p, f):
    for k, v in f.items():
        if k == "category":
            if p["category"] not in v:
                return False
        elif k == "max_price":
            if p["price"] > v:
                return False
        elif k == "min_price":
            if p["price"] < v:
                return False
        elif str(p[k]).lower() != str(v).lower():
            return False
    return True


def candidates(f):
    return [p for p in CAT if matches(p, f)]


def trace(req):
    """Per prefix: (t, parse, candidate ids using settled hard filters)."""
    rows = []
    for t in range(1, len(req["words"]) + 1):
        p = NLU.parse(req["words"][:t])
        f = p.filters(hard_only=True)
        c = candidates(f) if f else CAT
        rows.append((t, p, [x["product_id"] for x in c[:3]], len(c)))
    return rows


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "kit" / "dev.jsonl")
    reqs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    first_unique_wrong, first_unique_right, never = [], [], []
    for r in reqs:
        rows = trace(r)
        hit = next(((t, p, ids) for t, p, ids, n in rows if n == 1 and not p.blocked()
                    and not (p.pending - {x for x in p.pending if x.startswith("field:")} - {"phrase-open", "number-open"} and False)), None)
        if hit is None:
            never.append(r)
            continue
        t, p, ids = hit
        (first_unique_right if ids[0] == r["target"] else first_unique_wrong).append((r, t, p))
    n = len(reqs)
    print(f"first unique = target: {len(first_unique_right)}  wrong: {len(first_unique_wrong)}  never unique: {len(never)}")
    for r, t, p in first_unique_wrong:
        w = r["words"]
        print(f"  WRONG {r['id']} {r['tags']} t={t}/{len(w)} earliest={r['earliest']}: {' '.join(w[:t])} || {' '.join(w[t:])}")
    for r in never[:10]:
        print(f"  NEVER {r['id']} {r['tags']} {r['text']}")
    # earliness if we committed at first unique for the right ones
    e = sum((len(r["words"]) - t) / len(r["words"]) for r, t, p in first_unique_right) / n
    o = sum((len(r["words"]) - r["earliest"]) / len(r["words"]) for r in reqs) / n
    early_vs_oracle = sum(1 for r, t, p in first_unique_right if t < r["earliest"])
    print(f"earliness if all first-unique commits were made: {e:.3f} (oracle {o:.3f}); before oracle point: {early_vs_oracle}")
