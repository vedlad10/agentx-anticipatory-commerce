"""Score an anticipatory shopping agent: requests arrive one word at a time.

    python evaluate.py                                  # the baseline, on dev.jsonl
    python evaluate.py --agent my_agent.py              # your agent (a class named Agent)
    python evaluate.py --agent my_agent.py:MyAgent --log results.jsonl --limit 50

Your agent is a class with four methods (see README.md):

    class Agent:
        def __init__(self, tools): ...      # tools.search(...) and tools.record_search()
        def start(self, request_id): ...    # a new request begins
        def observe(self, word): ...        # one more word; return None to wait,
                                            # or {"commit": "P0123"} to show that product now
        def finish(self): ...               # the request is complete; return your final product_id

The same script, with a hidden set of ~300 requests, produces the leaderboard.
"""
import argparse
import importlib.util
import json
import re
import statistics
import sys
import time
from pathlib import Path

from search import FILTER_FIELDS, load_catalogue, search

HERE = Path(__file__).resolve().parent

# Scoring (per request, then averaged and multiplied by 100).
W_CORRECT = 0.4    # the final answer is the target product
W_EARLY = 0.6      # x the share of the request still to come when the target was committed
P_WRONG = 1.0      # each commit of a product that is not the target
P_WASTE = 0.02     # each search beyond the first, counting at most 10 per request
FILTER_KEYS = FILTER_FIELDS + ("max_price",)


class Tools:
    """What the harness gives your agent. Every search counts, wherever it runs."""

    def __init__(self):
        self.searches = 0

    def search(self, query="", filters=None, k=10):
        """search.search over the local catalogue, counted."""
        self.searches += 1
        return search(query, filters, k)

    def record_search(self, n=1):
        """Count n searches performed through an external search service."""
        self.searches += n


class BaselineAgent:
    """Waits for the whole request, picks out filters it can spell, runs one search, answers.

    It never commits early, so it earns no earliness, and it understands no synonyms,
    number words, sizes like "medium" or Hindi.
    """

    def __init__(self, tools):
        self.tools = tools
        cat = load_catalogue()
        self.vocab = {f: sorted({p[f].lower() for p in cat if p[f]}, key=len, reverse=True)
                      for f in ("category", "colour", "brand")}
        self.sizes = {p["size"].lower(): p["size"] for p in cat if p["size"]}

    def start(self, request_id):
        self.words = []

    def observe(self, word):
        self.words.append(word)
        return None

    def finish(self):
        text = " ".join(self.words).lower()
        filters = {}
        for field, values in self.vocab.items():
            spots = []
            for v in values:
                forms = [v, v[:-1]] if field == "category" and v.endswith("s") else [v]
                spots += [(m.start(), v) for f in forms for m in re.finditer(rf"\b{re.escape(f)}\b", text)]
            if spots:
                filters[field] = max(spots)[1]          # the last one mentioned wins
        sizes = re.findall(r"\b(?:size|uk|waist)\s+([a-z0-9]+)\b", text)
        if sizes and sizes[-1] in self.sizes:
            filters["size"] = self.sizes[sizes[-1]]
        budget = re.findall(r"\b(?:under|below|less than|within|max|up to|budget)\s+(?:rs\.?\s*|₹)?([\d,]+)\b", text)
        if budget:
            filters["max_price"] = int(budget[-1].replace(",", ""))
        for drop in (None, "max_price", "size", "brand", "colour", "category"):
            filters.pop(drop, None)
            hits = self.tools.search(text, filters, k=1)
            if hits:
                return hits[0]["product_id"]
        return None


def load_agent(spec):
    if spec in (None, "baseline"):
        return BaselineAgent
    path, _, name = spec.partition(":")
    path = Path(path).resolve()
    sys.path.insert(0, str(path.parent))
    mod_spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    return getattr(module, name or "Agent")


def run(agent_cls, requests):
    tools = Tools()
    agent = agent_cls(tools)
    results, per_word = [], []
    for req in requests:
        tools.searches = 0
        agent.start(req["id"])
        commits, current, reported = [], None, None
        for t, word in enumerate(req["words"], 1):
            t0 = time.perf_counter()
            out = agent.observe(word)
            per_word.append(time.perf_counter() - t0)
            if out is None:
                continue
            if isinstance(out, str):
                out = {"commit": out}
            if out.get("commit") and out["commit"] != current:
                current = out["commit"]
                commits.append((t, current))
            if out.get("filters") is not None:
                reported = out["filters"]
        final = agent.finish() or current
        results.append(score_one(req, commits, final, tools.searches, reported))
    return results, per_word


def score_one(req, commits, final, searches, reported):
    n, target = len(req["words"]), req["target"]
    correct = final == target
    wrong = sum(1 for _, c in commits if c != target)
    first_right = next((t for t, c in commits if c == target), None)
    early = n - first_right if correct and not wrong and first_right else 0
    wasted = max(0, searches - 1)
    score = (W_CORRECT + W_EARLY * early / n if correct else 0) - P_WRONG * wrong - P_WASTE * min(wasted, 10)
    return {"id": req["id"], "tags": req.get("tags", []), "words": n, "target": target, "final": final,
            "correct": correct, "commits": commits, "wrong_commits": wrong, "early_words": early,
            "early_share": early / n, "oracle_share": (n - req["earliest"]) / n if "earliest" in req else None,
            "searches": searches, "wasted": wasted, "score": score,
            "filters_reported": reported, "filters_gold": req.get("filters")}


def summarise(results):
    n = len(results)
    return {
        "requests": n,
        "accuracy": sum(r["correct"] for r in results) / n,
        "wrong_commits": sum(r["wrong_commits"] for r in results),
        "requests_with_wrong_commit": sum(1 for r in results if r["wrong_commits"]),
        "early_words": sum(r["early_words"] for r in results) / n,
        "early_share": sum(r["early_share"] for r in results) / n,
        "oracle_share": statistics.mean(r["oracle_share"] for r in results) if results[0]["oracle_share"] is not None else None,
        "searches": sum(r["searches"] for r in results) / n,
        "wasted": sum(r["wasted"] for r in results) / n,
        "score": 100 * sum(r["score"] for r in results) / n,
    }


def filter_accuracy(results):
    rows = [r for r in results if r["filters_reported"] is not None and r["filters_gold"]]
    if not rows:
        return None
    acc = {}
    for k in FILTER_KEYS:
        same = [str(r["filters_reported"].get(k)).lower() == str(r["filters_gold"].get(k)).lower() for r in rows]
        acc[k] = sum(same) / len(same)
    return len(rows), acc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agent", default="baseline", help="path/to/agent.py[:ClassName], or 'baseline'")
    ap.add_argument("--data", default=str(HERE / "dev.jsonl"))
    ap.add_argument("--limit", type=int, help="score only the first N requests")
    ap.add_argument("--log", help="write one JSON line per request here")
    ap.add_argument("--no-baseline", action="store_true", help="skip the baseline comparison")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        requests = [json.loads(line) for line in fh if line.strip()]
    requests = requests[:args.limit] if args.limit else requests

    results, per_word = run(load_agent(args.agent), requests)
    s = summarise(results)
    base = None
    if args.agent != "baseline" and not args.no_baseline:
        base = summarise(run(BaselineAgent, requests)[0])

    def vs(key, fmt):
        return f"   (baseline {format(base[key], fmt)})" if base else ""

    print(f"agent               {args.agent}")
    print(f"requests            {s['requests']}   ({Path(args.data).name})")
    print(f"accuracy            {s['accuracy']:.3f}{vs('accuracy', '.3f')}"
          + ("   BELOW BASELINE" if base and s["accuracy"] < base["accuracy"] else ""))
    print(f"wrong commits       {s['wrong_commits']} in {s['requests_with_wrong_commit']} requests")
    oracle = f", best possible {s['oracle_share']:.1%}" if s["oracle_share"] is not None else ""
    print(f"earliness           {s['early_words']:.2f} words before the end ({s['early_share']:.1%} of the request{oracle})")
    print(f"searches/request    {s['searches']:.2f}   (wasted {s['wasted']:.2f})")
    ms = sorted(per_word)
    print(f"latency             {1000 * statistics.mean(ms):.2f} ms/word, p95 {1000 * ms[int(.95 * (len(ms) - 1))]:.2f} ms")
    print(f"SCORE               {s['score']:.1f}{vs('score', '.1f')}")

    tags = sorted({t for r in results for t in r["tags"]}) + ["plain"]
    print("\nby tag              n    accuracy  wrong  earliness  score")
    for tag in tags:
        rows = [r for r in results if (tag in r["tags"]) or (tag == "plain" and not r["tags"])]
        if rows:
            t = summarise(rows)
            print(f"  {tag:17} {t['requests']:4}    {t['accuracy']:.3f}   {t['wrong_commits']:4}    {t['early_share']:6.1%}  {t['score']:6.1f}")

    fa = filter_accuracy(results)
    if fa:
        print(f"\nfilters you reported at the last word, vs the gold ones ({fa[0]} requests):")
        print("  " + "  ".join(f"{k} {v:.2f}" for k, v in fa[1].items()))

    if args.log:
        with open(args.log, "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nper-request results: {args.log}")


if __name__ == "__main__":
    main()
