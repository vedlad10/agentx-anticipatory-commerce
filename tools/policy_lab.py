"""Compare commit policies on a dev file with the evaluator's scoring formula.

Offline analysis only. Each policy sees exactly what the agent would see at word t.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from simulate import NLU, candidates  # noqa: E402

W_CORRECT, W_EARLY, P_WRONG = 0.4, 0.6, 1.0


def features(p, t):
    last_val = p.last_value_word            # 0-indexed word of the last slot value
    cur = t - 1                             # 0-indexed current word
    closer_after = any(k == "CLOSER" and w > last_val for w, k in p.events)
    late_seen = any(k == "LATE" for w, k in p.events)
    late_after_value = any(k == "LATE" and w > last_val for w, k in p.events)
    return {
        "since_value": cur - last_val,
        "corr_done": p.count("CORRECTED") > 0 or (p.count("CORR") > 0 and not p.blocked()),
        "closer": closer_after,
        "late": late_seen,
        "late_open": late_after_value,
        "corr_prefix": "corr-prefix" in p.pending,
        "n_slots": len([f for f in ("category", "colour", "brand", "size", "max_price") if f in p.slots]),
        "has_cat": "category" in p.slots,
    }


def build(reqs):
    data = []
    for r in reqs:
        steps = []
        for t in range(1, len(r["words"]) + 1):
            p = NLU.parse(r["words"][:t])
            f = p.filters(hard_only=True)
            c = candidates(f) if f else []
            uid = c[0]["product_id"] if len(c) == 1 else None
            steps.append((t, p, uid, features(p, t)))
        full = NLU.parse(r["words"])
        fc = candidates(full.filters(include_pending=True))
        final = min(fc, key=lambda x: x["price"])["product_id"] if fc else None
        data.append((r, steps, final))
    return data


def score(data, policy, verbose=False):
    tot, wrong_n, early_sum, acc = 0.0, 0, 0.0, 0
    bad = []
    for r, steps, final in data:
        n = len(r["words"])
        commit = None
        for t, p, uid, f in steps:
            if uid and not p.blocked() and policy(p, f, t, n):
                commit = (t, uid)
                break
        correct = final == r["target"]
        wrong = 1 if commit and commit[1] != r["target"] else 0
        early = (n - commit[0]) if (commit and not wrong and correct) else 0
        s = (W_CORRECT + W_EARLY * early / n if correct else 0) - P_WRONG * wrong
        tot += s
        acc += correct
        wrong_n += wrong
        early_sum += early / n
        if wrong:
            bad.append((r["id"], commit[0], " ".join(r["words"][:commit[0]]), " ".join(r["words"][commit[0]:])))
    N = len(data)
    if verbose:
        for b in bad:
            print("    wrong", b)
    return 100 * tot / N, acc / N, wrong_n, early_sum / N


POLICIES = {
    "never (final only)": lambda p, f, t, n: False,
    "first unique": lambda p, f, t, n: True,
    "wait>=1": lambda p, f, t, n: f["since_value"] >= 1 and not f["corr_prefix"],
    "wait>=2": lambda p, f, t, n: f["since_value"] >= 2 and not f["corr_prefix"],
    "wait>=1 | corr_done": lambda p, f, t, n: f["corr_done"] or (f["since_value"] >= 1 and not f["corr_prefix"]),
    "wait>=2 | corr_done": lambda p, f, t, n: f["corr_done"] or (f["since_value"] >= 2 and not f["corr_prefix"]),
    "closer | corr_done": lambda p, f, t, n: f["corr_done"] or f["closer"],
    "closer | corr_done | late": lambda p, f, t, n: f["corr_done"] or f["closer"] or f["late"],
    "closer|corr|late|wait>=2": lambda p, f, t, n: f["corr_done"] or f["closer"] or f["late"] or (f["since_value"] >= 2 and not f["corr_prefix"]),
    "closer|corr|late|wait>=1": lambda p, f, t, n: f["corr_done"] or f["closer"] or f["late"] or (f["since_value"] >= 1 and not f["corr_prefix"]),
}

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else str(ROOT / "kit" / "dev.jsonl")
    reqs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    data = build(reqs)
    print(f"{'policy':32} score   acc   wrong  earliness")
    for name, pol in POLICIES.items():
        s, a, w, e = score(data, pol, verbose="-v" in sys.argv)
        print(f"{name:32} {s:5.1f}  {a:.3f}  {w:4d}   {e:.3f}")
