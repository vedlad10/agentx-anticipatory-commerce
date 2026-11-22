"""Parse every full request in a .jsonl file and compare with the gold filters.

    python tools/check_parse.py [kit/dev.jsonl] [--show N]
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

FIELDS = ("category", "colour", "size", "brand", "max_price")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 40
    path = args[0] if args else str(ROOT / "kit" / "dev.jsonl")
    reqs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    nlu = Understander(Lexicon(load_catalogue()))
    right = {f: 0 for f in FIELDS}
    all_right = 0
    bad = []
    for r in reqs:
        rep = nlu.parse(r["words"]).report()
        ok = True
        for f in FIELDS:
            if str(rep.get(f)).lower() == str(r["filters"].get(f)).lower():
                right[f] += 1
            else:
                ok = False
        all_right += ok
        if not ok:
            bad.append((r, rep))
    n = len(reqs)
    print(f"{n} requests, all five filters right: {all_right / n:.3f}")
    print("  " + "  ".join(f"{f} {right[f] / n:.3f}" for f in FIELDS))
    for r, rep in bad[:show]:
        diff = {f: (rep.get(f), r["filters"].get(f)) for f in FIELDS
                if str(rep.get(f)).lower() != str(r["filters"].get(f)).lower()}
        print(f"- {r['id']} {r['tags']} {r['text']}\n    got/gold {diff}")


if __name__ == "__main__":
    main()
