"""Build stress sets with wording that is NOT in dev.jsonl (the hidden set promises some).

Every dev request is parsed (the parse is exact on dev), so we know where each filter value,
price phrase, correction marker and closer sits. Each of those spans is re-rendered with a
different surface form of the *same* meaning, so filters and target stay valid:

    stress_paraphrase.jsonl  unseen synonyms, number formats, markers, closers, openers
    stress_unknown.jsonl     one word per request replaced by gibberish: the agent cannot
                             understand it and must degrade safely (no wrong commits)

    python tools/make_stress.py            -> writes outputs/stress_*.jsonl
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from simulate import NLU  # noqa: E402

CATEGORY = {
    "running shoes": ["sports shoes", "running shoe", "jogging sneakers", "sport shoes",
                      "training shoes"],
    "sneakers": ["kicks", "canvas shoes", "lifestyle sneakers", "casual sneaker", "sneaker"],
    "sandals": ["flip flops", "flip-flops", "chappals", "sliders", "sandal"],
    "track pants": ["sweatpants", "lowers", "track bottoms", "jogger pants", "track pant"],
    "hoodies": ["hoody", "sweatshirt", "hoodies", "zip hoodie", "hooded top"],
    "t-shirts": ["tees", "tee shirt", "t-shirts", "round neck tee", "tshirts"],
    "shirts": ["formal shirt", "button down shirt", "shirts", "casual shirts", "office shirt"],
    "jeans": ["denim jeans", "denim pants", "jeans pant", "pair of denims", "jean"],
    "dresses": ["frock", "one piece", "midi dress", "dresses", "party dress"],
    "kurtas": ["kurti", "kurtas", "ethnic kurta", "kurta set", "kurtis"],
    "jackets": ["windcheater", "bomber jacket", "jackets", "rain jacket", "puffer jacket"],
    "backpacks": ["school bag", "laptop bag", "back pack", "bagpack", "daypack"],
    "caps": ["baseball cap", "caps", "trucker cap", "topi", "sports cap"],
    "headphones": ["headphone", "over-ear headphones", "wireless headphones", "headsets",
                   "head phones"],
    "watches": ["timepiece", "analog watch", "watches", "ghadi", "wrist-watch"],
    "wallets": ["billfold", "bifold wallet", "card holder", "wallets", "batua"],
}
COLOUR = {
    "black": ["jet black", "kala", "kaali", "pitch black"],
    "navy": ["navy-blue", "midnight blue", "navyblue"],
    "grey": ["charcoal grey", "ash grey", "slate grey", "heather grey", "sleti"],
    "blue": ["neela", "royal blue", "cobalt blue", "nila"],
    "white": ["safed", "pure white", "sufaid", "snow white"],
    "olive": ["army green", "olive-green", "military green"],
    "red": ["lal", "crimson", "scarlet", "cherry red"],
    "maroon": ["burgundy", "wine", "mehroon", "oxblood"],
    "green": ["hara", "bottle green", "emerald", "forest green"],
    "beige": ["sand", "oatmeal", "biscuit"],
    "brown": ["chocolate brown", "bhoora", "coffee", "dark brown"],
    "yellow": ["mustard", "peela", "lemon"],
    "pink": ["baby pink", "hot pink", "blush"],
    "tan": ["cognac", "tan brown"],
    "gold": ["sunehra", "golden"],
    "silver": ["chandi", "silvery"],
}
LETTER = {
    "XS": ["x-small", "extra-small", "XS size", "size XS"],
    "S": ["small size", "size small", "S"],
    "M": ["medium size", "size medium", "med"],
    "L": ["large size", "size large", "L"],
    "XL": ["x-large", "XL size", "size XL", "extra-large"],
    "XXL": ["double extra large", "2 XL", "XXL size", "xx-large"],
}
NUM_WORD = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven"}
HI_NUM = {6: "chhe", 7: "saat", 8: "aath", 9: "nau", 10: "das", 11: "gyarah"}
EN_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
            8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
            14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
            19: "nineteen", 20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
            60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
HI_WORDS = {1: "ek", 2: "do", 3: "teen", 4: "chaar", 5: "paanch", 6: "chhe", 7: "saat",
            8: "aath", 9: "nau", 10: "das", 11: "gyarah", 12: "barah", 13: "terah",
            14: "chaudah", 15: "pandrah", 16: "solah", 17: "satrah", 18: "atharah", 19: "unnis"}
CORR = ["whoops,", "my mistake,", "scratch that,", "on second thought,", "err, make it",
        "hmm no, make it", "change it to", "no wait,", "sorry no,", "galti ho gayi,",
        "uh actually,"]
LATE = ["btw,", "by the way,", "oh also,", "additionally,", "plus,", "ek baat aur,"]
CLOSER = ["for my mom", "for my sister", "for a party", "need it urgently", "for college",
          "if available", "asap please", "for my wife", "thanks a lot", "for daily use"]
OPENER = ["could you show me", "I am searching for", "please find me", "do you guys have",
          "I want to buy", "need"]


def en_number(v):
    if v % 1000 == 0 and v // 1000 < 20:
        return f"{EN_WORDS[v // 1000]} thousand"
    if v % 100 == 0 and v // 100 < 100:
        h = v // 100
        if h in EN_WORDS:
            return f"{EN_WORDS[h]} hundred"
        return f"{EN_WORDS[h // 10 * 10]} {EN_WORDS[h % 10]} hundred"
    return str(v)


def hi_number(v):
    if v % 1000 == 0 and v // 1000 in HI_WORDS:
        return f"{HI_WORDS[v // 1000]} hazaar"
    if v % 1000 == 500 and v // 1000 in HI_WORDS and v > 1000:
        if v == 1500:
            return "dedh hazaar"
        if v == 2500:
            return "dhai hazaar"
        return f"saadhe {HI_WORDS[v // 1000]} hazaar"
    if v % 100 == 0 and v // 100 in HI_WORDS:
        return f"{HI_WORDS[v // 100]} sau"
    return str(v)


def price_phrase(v, rng):
    forms = [f"below rs {v}", f"within ₹{v:,}", f"upto {v}", f"at most {v}",
             f"no more than INR {v}", f"{v} or less", f"under {en_number(v)}",
             f"{v} se kam", f"{hi_number(v)} tak", f"not above {v} rupees",
             f"within a budget of {v}", f"cheaper than {v}"]
    if v % 1000 == 0:
        forms.append(f"max {v // 1000} thousand")
    if v % 100 == 0 and v >= 1000:
        forms.append(f"under {v / 1000:g}k")
    return rng.choice(forms)


def size_phrase(size, rng):
    if size.isdigit():
        v = int(size)
        if v >= 28:
            return rng.choice([f"waist size {v}", f"{v} inch waist", f"size {v}", f"{v} waist"])
        return rng.choice([f"UK {NUM_WORD[v]}", f"{v} number", f"size UK {v}",
                           f"{NUM_WORD[v]} UK", f"{HI_NUM[v]} number", f"size {NUM_WORD[v]}"])
    return rng.choice(LETTER[size])


def paraphrase(req, rng):
    words = req["words"]
    p = NLU.parse(words)
    spans = []                      # (first word, last word, replacement text)
    items = p.items
    k = 0
    while k < len(items):
        it = items[k]
        if it.kind == "CAT" and rng.random() < 0.8:
            cat = it.value if isinstance(it.value, str) else it.value[0]
            spans.append((it.word, it.end_word, rng.choice(CATEGORY[cat])))
        elif it.kind == "COLOUR" and rng.random() < 0.7:
            spans.append((it.word, it.end_word, rng.choice(COLOUR[it.value])))
        elif it.kind == "BRAND" and rng.random() < 0.3:
            spans.append((it.word, it.end_word, it.value.lower()))
        elif it.role == "size" and rng.random() < 0.6:
            first = it.word
            if k > 0 and items[k - 1].has("SIZE_PRE") and items[k - 1].end_word == it.word - 1:
                first = items[k - 1].word
            last = it.end_word
            if k + 1 < len(items) and items[k + 1].has("SIZE_POST") and items[k + 1].word == last + 1:
                last = items[k + 1].end_word
            if it.kind == "NUM":
                canonical = str(int(it.value))
            else:
                canonical = it.get("SIZE")[1] if it.has("SIZE") else str(it.value)
            spans.append((first, last, size_phrase(canonical, rng)))
        elif it.kind == "SIZE" and rng.random() < 0.6:
            spans.append((it.word, it.end_word, size_phrase(it.value, rng)))
        elif it.role == "max_price" and rng.random() < 0.8:
            first = it.word
            j = k - 1
            while j >= 0 and (items[j].has("PRICE_PRE") or items[j].has("CURRENCY")) \
                    and items[j].end_word >= first - 1:
                first = items[j].word
                j -= 1
            last = it.end_word
            j = k + 1
            while j < len(items) and (items[j].has("PRICE_POST") or items[j].has("CURRENCY")) \
                    and items[j].word == last + 1 and items[j].kind != "CAT":
                last = items[j].end_word
                j += 1
            spans.append((first, last, price_phrase(int(it.value), rng)))
        elif it.kind == "CORR" and rng.random() < 0.8:
            spans.append((it.word, it.end_word, rng.choice(CORR)))
        elif it.kind == "LATE" and rng.random() < 0.7:
            spans.append((it.word, it.end_word, rng.choice(LATE)))
        elif it.kind == "CLOSER" and it.word > p.last_value_word and rng.random() < 0.7:
            spans.append((it.word, it.end_word, rng.choice(CLOSER)))
        k += 1
    # drop overlapping spans, keep the first
    spans.sort()
    clean, last_end = [], -1
    for s in spans:
        if s[0] > last_end:
            clean.append(s)
            last_end = s[1]
    out, w = [], 0
    for first, last, text in clean:
        out += words[w:first]
        tail = words[last][len(words[last].rstrip(",.?!")):]   # keep trailing punctuation
        rep = text.split()
        rep[-1] += tail
        out += rep
        w = last + 1
    out += words[w:]
    if rng.random() < 0.25 and p.items and p.items[0].kind in ("FILLER", "UNK"):
        # swap the opener: drop leading filler words up to the first value
        first_val = min((it.word for it in p.items if it.kind in ("CAT", "COLOUR", "BRAND",
                                                                  "SIZE") or it.role), default=0)
        lead = 0
        while lead < len(out) and lead < first_val and out[lead].lower().strip(",") in (
                "hi", "hey", "i", "want", "need", "i'd", "like", "show", "me", "get",
                "looking", "for", "i'm", "can", "you", "find", "do", "have", "any"):
            lead += 1
        if lead:
            out = rng.choice(OPENER).split() + out[lead:]
    return out


def gibberish(req, rng):
    """Replace one understood word (category, colour or a closer word) with nonsense."""
    words = list(req["words"])
    p = NLU.parse(words)
    cands = [it for it in p.items if it.kind in ("CAT", "COLOUR", "CLOSER")]
    if not cands:
        return words
    it = rng.choice(cands)
    tail = words[it.end_word][len(words[it.end_word].rstrip(",.?!")):]
    junk = rng.choice(["zorblat", "flimp", "quandle", "brizzo", "mernick"]) + tail
    return words[:it.word] + [junk] + words[it.end_word + 1:]


def main():
    rng = random.Random(7)
    reqs = [json.loads(l) for l in open(ROOT / "kit" / "dev.jsonl", encoding="utf-8")]
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    for name, fn in (("stress_paraphrase", paraphrase), ("stress_unknown", gibberish)):
        path = out_dir / f"{name}.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            for r in reqs:
                words = fn(r, rng)
                row = {"id": r["id"].replace("dev", name.split("_")[1][:4]), "text": " ".join(words),
                       "words": words, "filters": r["filters"], "target": r["target"],
                       "tags": r["tags"]}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
