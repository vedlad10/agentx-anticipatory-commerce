"""Vocabulary: every surface form we understand, mapped to a canonical meaning.

Canonical filter values (categories, colours, brands, sizes) come from catalogue.csv at start-up,
so the lexicon can never point at a value the store does not have. On top of that sits a curated
synonym layer: English, Indian-English and romanised Hindi forms, built to cover wording that is
*not* in dev.jsonl (the hidden test set promises new wording).

Every entry is a phrase (a tuple of normalised tokens) with one meaning:

    ("CAT", value)       category, value is a tuple of canonical categories (usually one)
    ("COLOUR", value)    canonical colour
    ("BRAND", value)     canonical brand
    ("SIZE", value)      canonical size ("M", "XL", "9", "32"...)
    ("SIZE_PRE", None)   "size", "uk", "waist"   -> a size value follows
    ("SIZE_POST", None)  "uk", "number", "waist" -> the number before was a size
    ("PRICE_PRE", "max"/"min")  "under", "within", "budget"... -> an amount follows
    ("PRICE_POST", "max"/"min") "tak", "se kam", "ke andar", "or less"... -> the amount before
    ("CURRENCY", None)   "rs", "rupees", "inr"
    ("CORR", None)       a correction is starting: "oops", "sorry", "make that", "nahi"...
    ("LATE", None)       a constraint is being added late: "oh and", "also", "ek aur baat"...
    ("NEG", None)        the next value is excluded: "not", "instead of", "except"
    ("CLOSER", None)     polite tail / purpose: "please", "for my dad", "as a gift"...
    ("FILLER", None)     "um", "like", "only", "brand"...

Strength: a meaning can be "soft" (a plausible but uncertain synonym such as cream -> beige).
Soft values are used for the final answer but never trusted enough to commit early.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------------------------
# Curated synonyms. Keys are canonical catalogue values. Values: list of surface phrases.
# A phrase prefixed with "~" is soft (uncertain).
# --------------------------------------------------------------------------------------------

CATEGORY_SYNONYMS = {
    "running shoes": [
        "running shoes", "running shoe", "running sneakers", "running sneaker", "runners",
        "runner shoes", "jogging shoes", "jogging shoe", "jogging sneakers", "jogger shoes",
        "sports shoes", "sport shoes", "sports shoe", "sports sneakers", "training shoes",
        "~trainers", "~trainer shoes", "road running shoes", "running trainers", "gym shoes",
        "athletic shoes", "track shoes", "marathon shoes", "daily trainers", "daily trainer",
        "running kicks", "run shoes",
    ],
    "sneakers": [
        "sneakers", "sneaker", "casual sneakers", "casual sneaker", "casual shoes", "casual shoe",
        "kicks", "canvas shoes", "lifestyle shoes", "lifestyle sneakers", "street shoes",
        "everyday shoes", "low tops", "low top sneakers", "~court shoes", "court sneakers",
        "tennis shoes", "skate shoes", "platform sneakers", "retro sneakers",
    ],
    "sandals": [
        "sandals", "sandal", "slides", "slide", "sliders", "slider", "floaters", "floater",
        "flip flops", "flip flop", "flipflops", "flipflop", "slippers", "slipper", "chappals",
        "chappal", "chappalein", "sandles", "sandle", "strap sandals", "slide sandals",
        "thong sandals", "hawai chappal", "hawaii chappal",
    ],
    "track pants": [
        "track pants", "track pant", "trackpants", "trackpant", "joggers", "jogger",
        "jogger pants", "jogging pants", "sweatpants", "sweat pants", "track bottoms",
        "trackies", "lowers", "~lower", "track suit pants", "tracksuit pants", "~tracks",
        "training pants", "gym pants", "jogging bottoms",
    ],
    "hoodies": [
        "hoodies", "hoodie", "hoody", "hooded sweatshirt", "hooded sweatshirts",
        "hooded sweat shirt", "sweatshirt", "sweatshirts", "sweat shirt", "pullover hoodie",
        "zip hoodie", "zip up hoodie", "hooded top", "hooded pullover",
    ],
    "t-shirts": [
        "t shirt", "t shirts", "tshirt", "tshirts", "tee", "tees", "tee shirt", "tee shirts",
        "tea shirt", "round neck", "round neck tee", "crew neck tee", "v neck tee",
        "half sleeve tee", "graphic tee", "basic tee", "~polo", "~polo tee", "~polo t shirt",
        "~polos",
    ],
    "shirts": [
        "shirt", "shirts", "casual shirt", "casual shirts", "formal shirt", "formal shirts",
        "button down", "button down shirt", "button up shirt", "dress shirt", "office shirt",
        "full sleeve shirt", "linen shirt", "oxford shirt", "denim shirt", "check shirt",
        "checked shirt",
    ],
    "jeans": [
        "jeans", "jean", "pair of jeans", "denims", "denim jeans", "denim pants", "denim",
        "jeans pant", "jeans pants", "skinny jeans", "slim jeans", "straight jeans",
    ],
    "dresses": [
        "dress", "dresses", "frock", "frocks", "one piece", "onepiece", "~gown", "midi dress",
        "maxi dress", "wrap dress", "party dress", "~midi", "~maxi",
    ],
    "kurtas": [
        "kurta", "kurtas", "kurti", "kurtis", "kurtha", "kurta set", "ethnic kurta",
        "pathani", "pathani kurta", "chikankari kurta", "chikankari",
    ],
    "jackets": [
        "jacket", "jackets", "windcheater", "wind cheater", "windbreaker", "bomber",
        "bomber jacket", "puffer", "puffer jacket", "rain jacket", "raincoat", "rain coat",
        "quilted jacket", "denim jacket", "~coat", "~jacket coat",
    ],
    "backpacks": [
        "backpack", "backpacks", "back pack", "back packs", "bag pack", "bagpack", "bagpacks",
        "rucksack", "rucksacks", "ruck sack", "daypack", "day pack", "school bag",
        "college bag", "laptop bag", "laptop backpack", "travel backpack", "bag", "bags",
        "travel bag",
    ],
    "caps": [
        "cap", "caps", "baseball cap", "baseball caps", "trucker cap", "~hat", "~hats", "topi",
        "peak cap", "snapback", "running cap", "sports cap",
    ],
    "headphones": [
        "headphones", "headphone", "headset", "headsets", "head phones", "head phone",
        "over ear headphones", "over ear", "on ear headphones", "on ear", "wireless headphones",
        "noise cancelling headphones", "gaming headphones", "gaming headset", "~cans",
        "~earphones", "~earphone",
    ],
    "watches": [
        "watch", "watches", "wrist watch", "wrist watches", "wristwatch", "wristwatches",
        "timepiece", "ghadi", "ghari", "analog watch", "digital watch", "chronograph",
        "~smart watch", "sports watch",
    ],
    "wallets": [
        "wallet", "wallets", "~purse", "~purses", "billfold", "card holder", "cardholder",
        "bifold", "bifold wallet", "trifold", "trifold wallet", "batua", "~money clip",
    ],
}

# Words that name a family of categories rather than one.
AMBIGUOUS_CATEGORIES = {
    "shoes": ("running shoes", "sneakers"),
    "shoe": ("running shoes", "sneakers"),
    "joote": ("running shoes", "sneakers"),
    "juta": ("running shoes", "sneakers"),
    "joota": ("running shoes", "sneakers"),
    "jute": ("running shoes", "sneakers"),
    "footwear": ("running shoes", "sneakers", "sandals"),
    "pants": ("track pants", "jeans"),
    "pant": ("track pants", "jeans"),
    "trousers": ("track pants", "jeans"),
    "trouser": ("track pants", "jeans"),
}

COLOUR_SYNONYMS = {
    "black": ["black", "kaala", "kaali", "kala", "kali", "jet black", "pitch black", "onyx",
              "kaale"],
    "navy": ["navy", "navy blue", "~dark blue", "navyblue", "nevy", "neavy", "midnight blue",
             "deep blue", "gehra neela"],
    "grey": ["grey", "gray", "charcoal", "charcoal grey", "charcoal gray", "ash", "ash grey",
             "slate", "slate grey", "heather grey", "grey melange", "dark grey", "light grey",
             "dark gray", "light gray", "sleti", "slety", "saleti", "steel grey", "greyish",
             "grayish"],
    "blue": ["blue", "sky blue", "light blue", "royal blue", "neela", "nila", "neeli", "nili",
             "neele", "aasmani", "asmani", "cobalt", "cobalt blue", "bluish", "~denim blue"],
    "white": ["white", "safed", "safaid", "sufed", "sufaid", "pure white",
              "snow white", "~off white", "~ivory", "whitish"],
    "olive": ["olive", "olive green", "army green", "military green", "~khaki green",
              "jaitooni", "olive colour"],
    "red": ["red", "laal", "lal", "crimson", "scarlet", "cherry red", "bright red", "reddish"],
    "maroon": ["maroon", "mehroon", "maroonish", "burgundy", "wine", "wine red", "~dark red",
               "oxblood", "~plum"],
    "green": ["green", "hara", "hari", "hare", "haraa", "emerald", "bottle green",
              "~dark green", "forest green", "~mint", "greenish"],
    "beige": ["beige", "~cream", "~off white", "sand", "~khaki", "nude", "~ivory", "biscuit",
              "oatmeal", "~fawn"],
    "brown": ["brown", "bhura", "bhoora", "bhuri", "bhoori", "chocolate", "coffee",
              "dark brown", "chocolate brown", "~camel", "brownish"],
    "yellow": ["yellow", "peela", "pila", "peeli", "pili", "mustard", "lemon", "~golden yellow",
               "yellowish"],
    "pink": ["pink", "gulabi", "baby pink", "rose", "~rose pink", "hot pink", "pinkish",
             "blush"],
    "tan": ["tan", "~camel", "~caramel", "tan brown", "cognac", "~light brown"],
    "gold": ["gold", "golden", "sunehra", "sunehri", "sunahra", "sunahri", "rose gold"],
    "silver": ["silver", "silvery", "chandi", "chaandi", "chrome", "steel", "~metallic"],
}

# Letter sizes. Single letters are only trusted when typed in capitals or next to "size".
SIZE_SYNONYMS = {
    "XS": ["xs", "extra small", "x small", "xtra small", "extrasmall"],
    "S": ["s", "small", "sm", "~chhota", "~chota", "~chhoti", "~choti"],
    "M": ["m", "medium", "med", "medium size", "~madhyam"],
    "L": ["l", "large", "lg", "~bada", "~badi"],
    "XL": ["xl", "extra large", "x large", "xtra large", "extralarge", "1xl"],
    "XXL": ["xxl", "2xl", "xx large", "double xl", "double extra large", "2 xl", "xxl size",
            "double x l", "extra extra large"],
}
SINGLE_LETTER_SIZES = {"s", "m", "l"}

SIZE_PRE = ["size", "sizes", "uk", "uk size", "size uk", "waist", "waist size", "size of",
            "in size", "number", "numbr", "naap", "saiz", "euro", "eu", "us"]
SIZE_POST = ["uk", "size", "number", "waist", "inch waist", "inches", "inch",
             "waist size", "numbr", "saiz", "ka size", "size ka", "size mein"]

PRICE_PRE_MAX = [
    "under", "below", "within", "max", "maximum", "upto", "up to", "not more than",
    "no more than", "less than", "lesser than", "lower than", "cheaper than", "at most",
    "atmost", "budget", "budget of", "budget is", "my budget is", "budget around",
    "budget hai", "for under", "not above", "not over", "nothing above", "nothing over",
    "within budget", "within a budget of", "costing under", "costing less than",
    "priced under", "priced below", "price under", "price below", "price within",
    "price limit", "limit", "max price", "maximum price", "less then", "lesser then",
    "not exceeding", "under rs", "below rs", "max budget", "price range", "range",
    "affordable under", "cap of", "around", "about", "approx", "approximately", "roughly",
    "less", "till", "upper limit",
]
PRICE_PRE_MIN = ["above", "over", "more than", "at least", "atleast", "minimum", "starting from",
                 "starting at", "min"]
PRICE_POST_MAX = [
    "tak", "tak ka", "tak ki", "tak ke", "tak mein", "se kam", "se kam ka", "se kam ki",
    "se kam mein", "ke andar", "ke andar ka", "ke andar ki", "ke neeche", "ke niche",
    "se neeche", "se niche", "ke under", "ke bheetar", "ke bhitar", "mein", "me",
    "se zyada nahi", "se jyada nahi", "se zyada na ho", "or less", "or below", "or under",
    "max", "maximum", "at most", "tops", "budget", "ka budget", "and below", "and under",
    "or cheaper", "only", "ke aas paas", "ke around", "range",
]
PRICE_POST_MIN = ["or more", "and above", "or above", "plus", "se zyada", "se upar", "ke upar"]
CURRENCY = ["rs", "rupees", "rupee", "inr", "rupaye", "rupay", "rupiya", "rupaiye", "bucks",
            "rs only", "only rs", "rupees only", "₹"]

CORRECTION_MARKERS = [
    "oops", "oop", "sorry", "sorry i meant", "sorry i mean", "i mean", "i meant", "make that",
    "make it", "no make it", "change that to", "change it to", "no change that to",
    "change to", "switch to", "switch that to", "wait", "wait i meant", "wait no", "no wait",
    "actually", "actually make it", "no no", "no", "nope", "or rather", "rather",
    "scratch that", "correction", "nahi", "nahin", "nai", "nahi nahi", "matlab", "mera matlab",
    "i mean to say", "on second thought", "second thought", "hold on", "uh no",
    "um no", "no sorry", "instead make it", "let me correct", "let me change", "not that",
    "galti se", "galat", "sorry matlab", "arre nahi", "nahi nahi", "rehne do",
    "whoops", "woops", "err", "errr", "oh no", "oh wait", "hmm actually", "hmm no", "nah",
    "my mistake", "change of mind", "changed my mind", "ek minute", "ruko", "ruk",
    "ruko ruko", "nahi yaar", "galti ho gayi", "rather make it", "not this", "i said wrong",
    "i misspoke", "let me rephrase", "edit", "sorry i said", "sorry not", "uh actually",
    "um actually", "actually no", "no actually", "nahi actually", "no not", "wait wait",
    "scratch", "make that a", "make it a", "change it", "update", "replace",
]
LATE_MARKERS = [
    "also", "oh and", "oh also", "and also", "one more thing", "and make sure",
    "make sure", "make sure it's", "make sure its", "and make sure it's", "it has to be",
    "has to be", "it should be", "should be", "it must be", "must be", "and it should be",
    "plus", "aur", "aur haan", "aur han", "ek aur baat", "ek aur cheez", "btw", "by the way",
    "additionally", "oh", "and", "ek baat aur", "haan aur",
]
NEGATION_MARKERS = ["not", "no", "instead of", "except", "other than", "but not", "anything but",
                    "apart from", "avoid", "nahi chahiye"]
CLOSERS = [
    "please", "pls", "plz", "thanks", "thank you", "thankyou", "ty", "cheers",
    "if you have it", "if you have one", "if available", "if possible", "if you can",
    "as a gift", "for a gift", "gift", "for my brother", "for my sister", "for my dad",
    "for my father", "for my mom", "for my mother", "for my wife", "for my husband",
    "for my son", "for my daughter", "for my friend", "for my girlfriend",
    "for my boyfriend", "for me", "for myself", "for the gym", "for gym", "for office",
    "for the office", "for work", "for college", "for school", "for a wedding",
    "for the wedding", "for a party", "for the party", "for travel", "for a trip",
    "for running", "for daily use", "for everyday", "for diwali", "for the weekend",
    "need it this week", "need it soon", "need it today", "need it urgently", "asap",
    "urgently", "urgent", "nothing too flashy", "nothing flashy", "something simple",
    "chahiye", "chahiye please", "chahiye tha", "milega", "milegi", "milenge", "dikhao",
    "dikhao na", "dikha do", "dikhaiye", "hai kya", "hain kya", "hai", "please dikhao",
    "bhejo", "de do", "dedo", "kar do", "hona chahiye", "ho to", "mil jayega",
    "anything works", "that's all", "thats all", "that is all", "that's it", "thats it",
]
FILLERS = [
    "um", "umm", "uh", "uhh", "hmm", "hmmm", "er", "erm", "like", "only", "brand", "the",
    "a", "an", "some", "any", "one", "in", "by", "from", "of", "with", "for", "and", "colour",
    "color", "coloured", "colored", "shade", "pair", "ka", "ki", "ke", "wala", "wali",
    "wale", "mein", "me", "made", "company", "make", "model", "type", "kind", "something",
    "just", "really", "very", "nice", "good", "cool", "new", "latest", "ek", "koi", "bhi",
    "mujhe", "mere", "liye", "kya", "aapke", "paas", "bhaiya", "bhai", "didi", "ji",
    "i", "i'd", "i'm", "want", "need", "looking", "show", "me", "get", "find", "can", "you",
    "do", "have", "hi", "hey", "hello", "would", "love", "buy", "searching", "search",
    "is", "it", "it's", "its", "that", "this", "there", "are", "for", "something",
]

# Filler words that introduce or glue a filter: after one of these, more of the request body is
# coming, so they never count as the polite tail of a request.
BODY_FILLERS = {
    "in", "by", "from", "only", "of", "with", "brand", "colour", "color", "coloured", "colored",
    "shade", "like", "ka", "ki", "ke", "wala", "wali", "wale", "um", "umm", "uh", "uhh", "hmm",
    "hmmm", "er", "erm", "for", "and", "a", "an", "the", "pair", "made", "company", "make",
    "model", "type", "kind", "some", "any", "one", "ek", "koi", "mein", "me", "just", "also",
    "plus", "aur", "oh", "is", "it's", "its", "it", "that", "should", "must", "be", "has",
}

# Number words (English and romanised Hindi). Hindi words that collide with common English or
# Hindi function words ("do", "ek", "teen", "saath"...) are "weak": they only count as numbers
# next to a multiplier ("do hazaar") or a size/price marker ("das number", "size nau").
EN_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
HI_UNITS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "paach": 5,
    "chhe": 6, "chhah": 6, "che": 6, "chah": 6, "chheh": 6, "chha": 6, "saat": 7, "sat": 7,
    "aath": 8, "ath": 8, "aat": 8, "nau": 9, "das": 10, "dus": 10, "gyarah": 11,
    "gyaarah": 11, "gyara": 11, "barah": 12, "baarah": 12, "bara": 12, "terah": 13, "tera": 13,
    "chaudah": 14, "chodah": 14, "chaudha": 14, "pandrah": 15, "pandra": 15, "pundrah": 15,
    "solah": 16, "sola": 16, "satrah": 17, "satra": 17, "sattrah": 17, "atharah": 18,
    "athara": 18, "attharah": 18, "unnis": 19, "unees": 19, "unnees": 19, "bees": 20,
    "bis": 20, "pachchees": 25, "pachees": 25, "pachis": 25, "tees": 30, "chalis": 40,
    "chaalis": 40, "pachaas": 50, "pachas": 50, "pachattar": 75, "sattar": 70, "assi": 80,
}
HI_WEAK = {"ek", "do", "teen", "tees", "bees", "sat", "bis", "bara", "che", "chah", "ath", "aat",
           "char", "das", "nau", "saat", "aath", "chhe", "tera", "sola"}
EN_WEAK = {"one"}
MULTIPLIERS = {"hundred": 100, "thousand": 1000, "k": 1000, "grand": 1000, "lakh": 100000,
               "lac": 100000, "lakhs": 100000, "sau": 100, "hazaar": 1000,
               "hazar": 1000, "hajaar": 1000, "hajar": 1000, "hazzar": 1000, "thousands": 1000,
               "hundreds": 100, "thou": 1000}
FRACTION_WORDS = {"saadhe": 0.5, "sadhe": 0.5, "saade": 0.5, "saadhe": 0.5, "sava": 0.25,
                  "savaa": 0.25, "sawa": 0.25, "paune": -0.25, "pone": -0.25}
FIXED_FRACTIONS = {"dedh": 1.5, "dhedh": 1.5, "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5,
                   "dhaayi": 2.5, "dhaiyi": 2.5}


# --------------------------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------------------------

_K_NUMBER = re.compile(r"^(\d+(?:\.\d+)?)k$")
_PLAIN_NUMBER = re.compile(r"^\d{1,3}(?:,\d{2,3})+(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_PUNCT_TAIL = ".,!?;:\"')]}…"
_PUNCT_HEAD = "\"'([{¿¡"


class Token:
    """One normalised token. `word` is the index of the request word it came from."""
    __slots__ = ("text", "raw", "word", "num", "upper", "boundary")

    def __init__(self, text, raw, word, num=None, upper=False):
        self.text = text          # normalised (lowercase, no punctuation)
        self.raw = raw            # as typed
        self.word = word          # index of the source word in the request
        self.num = num            # numeric value if the token is a number written in digits
        self.upper = upper        # typed in capitals ("L", "XS")
        self.boundary = ""        # punctuation that followed: "," or "." or ""

    def __repr__(self):
        return f"Token({self.text!r}@{self.word}{self.boundary})"


def tokenize_word(word, index):
    """Split one incoming request word into normalised tokens."""
    raw = word.strip()
    tail = ""
    while raw and raw[-1] in _PUNCT_TAIL:
        tail = raw[-1] if raw[-1] in ".,!?;:…" and not tail else tail
        raw = raw[:-1]
    while raw and raw[0] in _PUNCT_HEAD:
        raw = raw[1:]
    if tail == "." and raw.lower() in ("rs", "no", "approx", "max", "min", "nos", "pls", "st"):
        tail = ""
    out = []
    # currency glued to the front: ₹1500, rs.4000, Rs1500, INR2000
    m = re.match(r"^(₹|rs\.?|inr)\s*(.+)$", raw, flags=re.I)
    if m and re.match(r"^[\d.,]+k?$", m.group(2), flags=re.I):
        out.append(Token("rs", m.group(1), index))
        raw = m.group(2)
    elif raw in ("₹",):
        out.append(Token("rs", raw, index))
        raw = ""
    # amount with a currency / size suffix glued on: 1500rs, 2000/-, 9uk
    m = re.match(r"^([\d.,]+k?)(rs|/-|rupees|inr|uk)$", raw, flags=re.I)
    suffix = None
    if m:
        raw, suffix = m.group(1), m.group(2).lower()
    if raw:
        parts = [raw]
        low = raw.lower()
        if "-" in raw and not re.match(r"^[\d.,]+$", raw):
            parts = [p for p in raw.split("-") if p]   # t-shirt -> t shirt, x-large -> x large
        elif "/" in raw and not re.match(r"^[\d.,/]+$", raw):
            parts = [p for p in raw.split("/") if p]
        for part in parts:
            low = part.lower().strip(_PUNCT_TAIL + _PUNCT_HEAD)
            if not low:
                continue
            num = None
            mk = _K_NUMBER.match(low.replace(",", ""))
            if mk:
                num = float(mk.group(1)) * 1000
            elif _PLAIN_NUMBER.match(low):
                num = float(low.replace(",", ""))
            m2 = re.match(r"^(\d)xl$", low)
            if m2:                                   # 2xl, 3xl
                low = "x" * int(m2.group(1)) + "l" if int(m2.group(1)) <= 3 else low
            if low in ("rs.", "rs", "₹", "inr"):
                low = "rs"
            if low.endswith("'s") and len(low) > 3 and low not in ("it's", "that's", "what's"):
                low = low[:-2]
            tok = Token(low if num is None else str(int(num)) if num == int(num) else str(num),
                        part, index, num=num, upper=part.isupper() and part.isalpha())
            out.append(tok)
    if suffix:
        out.append(Token("rs" if suffix in ("rs", "/-", "rupees", "inr") else "uk", suffix, index))
    if out:
        out[-1].boundary = tail
    return out


def _edit_distance(a, b, limit):
    """Levenshtein distance, giving up (returning limit + 1) once it exceeds `limit`."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


# --------------------------------------------------------------------------------------------
# The lexicon: a phrase trie built from the catalogue + the tables above
# --------------------------------------------------------------------------------------------

class Lexicon:
    """Phrase trie over normalised tokens.

    lookup(tokens, i) -> (length, meanings) for the longest phrase starting at tokens[i].
    is_prefix(tokens[j:]) -> True if those tokens start a longer phrase (the meaning may change
    when the next word arrives).
    """

    def __init__(self, catalogue):
        self.trie = {}
        self.categories = sorted({p["category"] for p in catalogue})
        self.colours = sorted({p["colour"] for p in catalogue if p["colour"]})
        self.brands = sorted({p["brand"] for p in catalogue if p["brand"]})
        self.sizes = sorted({p["size"] for p in catalogue if p["size"]})
        self.sizes_by_category = {}
        for p in catalogue:
            if p["size"]:
                self.sizes_by_category.setdefault(p["category"], set()).add(p["size"])
        self.numeric_sizes = {int(s) for s in self.sizes if s.isdigit()}
        self.letter_sizes = {s for s in self.sizes if not s.isdigit()}
        # single-facet counts (store statistics, not product lookups): used to estimate how
        # selective a filter set is before spending a search on it
        n = len(catalogue)
        self.n_products = n
        self.facet_share = {}
        for field in ("category", "colour", "brand", "size"):
            counts = {}
            for p in catalogue:
                counts[p[field]] = counts.get(p[field], 0) + 1
            self.facet_share[field] = {k: v / n for k, v in counts.items()}

        def add_all(kind, table, canonical_ok):
            for value, phrases in table.items():
                if not canonical_ok(value):
                    continue
                for ph in phrases:
                    soft = ph.startswith("~")
                    self.add(ph.lstrip("~"), (kind, value, "soft" if soft else "hard"))

        cats = set(self.categories)
        add_all("CAT", {c: v for c, v in CATEGORY_SYNONYMS.items()}, lambda c: c in cats)
        for c in self.categories:                      # the catalogue's own names, always
            self.add(c, ("CAT", c, "hard"))
            if c.endswith("s"):
                self.add(c[:-1], ("CAT", c, "hard"))
        for word, group in AMBIGUOUS_CATEGORIES.items():
            group = tuple(g for g in group if g in cats)
            if group:
                self.add(word, ("CAT", group, "soft"))
        colours = set(self.colours)
        add_all("COLOUR", COLOUR_SYNONYMS, lambda c: c in colours)
        for c in self.colours:
            self.add(c, ("COLOUR", c, "hard"))
        for b in self.brands:
            self.add(b.lower(), ("BRAND", b, "hard"))
            squashed = b.lower().replace(" ", "")
            if squashed != b.lower():
                self.add(squashed, ("BRAND", b, "hard"))
        for b in self.brands:                          # first word of a two-word brand: soft
            if " " in b:
                self.add(b.lower().split()[0], ("BRAND", b, "soft"))
        letter = set(self.letter_sizes)
        add_all("SIZE", SIZE_SYNONYMS, lambda s: s in letter)
        for ph in SIZE_PRE:
            self.add(ph, ("SIZE_PRE", None, "hard"))
        for ph in SIZE_POST:
            self.add(ph, ("SIZE_POST", None, "hard"))
        for ph in PRICE_PRE_MAX:
            self.add(ph, ("PRICE_PRE", "max", "hard"))
        for ph in PRICE_PRE_MIN:
            self.add(ph, ("PRICE_PRE", "min", "hard"))
        for ph in PRICE_POST_MAX:
            self.add(ph, ("PRICE_POST", "max", "hard"))
        for ph in PRICE_POST_MIN:
            self.add(ph, ("PRICE_POST", "min", "hard"))
        for ph in CURRENCY:
            self.add(ph, ("CURRENCY", None, "hard"))
        for ph in CORRECTION_MARKERS:
            self.add(ph, ("CORR", None, "hard"))
        for ph in LATE_MARKERS:
            self.add(ph, ("LATE", None, "hard"))
        for ph in NEGATION_MARKERS:
            self.add(ph, ("NEG", None, "hard"))
        for ph in CLOSERS:
            self.add(ph, ("CLOSER", None, "hard"))
        for ph in FILLERS:
            self.add(ph, ("FILLER", None, "hard"))

    def add(self, phrase, meaning):
        toks = []
        for i, w in enumerate(phrase.split()):
            toks += [t.text for t in tokenize_word(w, i)]
        if not toks:
            return
        node = self.trie
        for t in toks:
            node = node.setdefault(t, {})
        node.setdefault(None, [])
        if meaning not in node[None]:
            node[None].append(meaning)

    def fuzzy_brand(self, text):
        """A misspelt or split brand ("urbanix", "zen trail" -> "zentrail"), or None.

        Brands only: they are invented names, so a near miss is almost surely a typo or a
        speech-to-text rendering, never another English word.
        """
        if len(text) < 5 or not text.isalpha():
            return None
        limit = 1 if len(text) <= 6 else 2
        best, best_d = None, limit + 1
        for b in self.brands:
            target = b.lower().replace(" ", "")
            if abs(len(target) - len(text)) > limit:
                continue
            d = _edit_distance(text, target, limit)
            if d < best_d:
                best, best_d = b, d
            elif d == best_d and best != b:
                best = None if d <= limit else best        # ambiguous: two brands as close
        return best if best_d <= limit else None

    def below(self, node):
        """All meanings of the phrases strictly below a trie node (cached)."""
        cache = self.__dict__.setdefault("_below", {})
        key = id(node)
        if key not in cache:
            found = []
            stack = [sub for k, sub in node.items() if k is not None]
            while stack:
                sub = stack.pop()
                found.extend(sub.get(None, []))
                stack.extend(s for k, s in sub.items() if k is not None)
            cache[key] = tuple(found)
        return cache[key]

    def lookup(self, texts, i):
        """Longest phrase starting at texts[i]: (length, meanings) or (0, [])."""
        node, best = self.trie, (0, [])
        j = i
        while j < len(texts) and texts[j] in node:
            node = node[texts[j]]
            j += 1
            if None in node:
                best = (j - i, node[None])
        return best

    def continues(self, texts):
        """True if `texts` is a proper prefix of some longer phrase."""
        node = self.trie
        for t in texts:
            if t not in node:
                return False
            node = node[t]
        return any(k is not None for k in node)
