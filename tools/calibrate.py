"""Measure, per commit state, how often the unique product at that moment is NOT the target.

For each request and each state, take the first word at which the product is unique (hard,
settled filters) while the request is in that state, and record whether it is the target.
Risk = (wrong + 0.5) / (seen + 1)  (Jeffreys prior). The numbers go into anticipate/policy.py.

    python tools/calibrate.py [kit/dev.jsonl]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from simulate import NLU, candidates          # noqa: E402
from anticipate.policy import state_of         # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "kit" / "dev.jsonl")
reqs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
seen, wrong, examples = {}, {}, {}
for r in reqs:
    done = set()
    for t in range(1, len(r["words"]) + 1):
        p = NLU.parse(r["words"][:t])
        f = p.filters(hard_only=True)
        if not f:
            continue
        c = candidates(f)
        if len(c) != 1:
            continue
        st = state_of(p)
        if st in done:
            continue
        done.add(st)
        seen[st] = seen.get(st, 0) + 1
        if c[0]["product_id"] != r["target"]:
            wrong[st] = wrong.get(st, 0) + 1
            examples.setdefault(st, []).append(f'{r["id"]}: {" ".join(r["words"][:t])} || {" ".join(r["words"][t:])}')
print(f"{'state':20} seen  wrong  risk")
for st in sorted(seen, key=lambda s: -seen[s]):
    w = wrong.get(st, 0)
    print(f"{st:20} {seen[st]:4}  {w:5}  {(w + 0.5) / (seen[st] + 1):.3f}")
for st, ex in examples.items():
    if st == "at-value":
        continue
    print(f"\nwrong in {st}:")
    for e in ex:
        print("  ", e)
