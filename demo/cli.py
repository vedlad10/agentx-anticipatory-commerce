"""Watch the agent think, word by word.

    python demo/cli.py "show me olive Urbanyx size 6 UK slides not more than seven hundred"
    python demo/cli.py dev-0040                 # replay a request from kit/dev.jsonl
    python demo/cli.py --bold dev-0002           # the bolder commit mode
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit"))
sys.stdout.reconfigure(encoding="utf-8")

from evaluate import Tools                     # noqa: E402  (the kit's counted search)
from agent import Agent                        # noqa: E402

STATE_NOTE = {
    "unsettled": "a correction may be starting",
    "at-value": "value just said: an 'oops, I mean...' could follow",
    "past-value": "request still going",
    "past-value-unknown": "unknown word: could be a correction",
    "tail": "shopper is past the filters",
    "twist-done": "the correction / late addition has landed",
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--bold" in sys.argv:
        os.environ["AGENTX_MODE"] = "bold"
    if not args:
        print(__doc__)
        return
    target = None
    if args[0].startswith("dev-"):
        reqs = {json.loads(l)["id"]: json.loads(l) for l in
                open(ROOT / "kit" / "dev.jsonl", encoding="utf-8")}
        req = reqs[args[0]]
        words, target = req["words"], req["target"]
        print(f"{req['id']}  tags={req['tags']}  target={target}")
    else:
        words = " ".join(args).split()
    tools = Tools()
    agent = Agent(tools)
    agent.start("demo")
    print(f"\n{'#':>3}  {'word':14} {'shelf':>5}  {'conf':>5}  state")
    commit_at = None
    for i, w in enumerate(words, 1):
        out = agent.observe(w)
        t = agent.trace[-1]
        f = {k: v for k, v in out["filters"].items() if v is not None}
        flag = ""
        if out.get("commit"):
            commit_at = i
            flag = f"  >>> COMMIT {out['commit']}"
        shelf = t["candidates"] if t["candidates"] else "-"
        print(f"{i:>3}  {w:14} {shelf:>5}  {out['confidence']:5.3f}  {t['state']:<18}{flag}")
        if out.get("commit") or i == len(words):
            print(f"       filters: {f}")
    final = agent.finish()
    prod = next((p for p in (agent.shelf.items or []) if p["product_id"] == final), None)
    print(f"\nfinal answer: {final}" + (f"  {prod['title']}, size {prod['size'] or '-'}, "
                                         f"Rs {prod['price']}" if prod else ""))
    if commit_at:
        left = len(words) - commit_at
        print(f"committed after word {commit_at} of {len(words)}: "
              f"{left} word{'' if left == 1 else 's'} before the shopper finished")
    else:
        print("no early commit: answered when the request was complete")
    print(f"searches: {tools.searches}")
    if target:
        print("CORRECT" if final == target else f"WRONG (target {target})")


if __name__ == "__main__":
    main()
