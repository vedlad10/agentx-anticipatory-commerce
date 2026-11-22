"""Incremental request understanding: the words so far -> filters, plus how settled they are.

The whole prefix is re-read on every word (a request is ~13 words, so this costs well under a
millisecond), which keeps the logic simple and makes corrections natural: a slot's reading is
always its last mention, so "black, no wait, white" ends as white without a special case.

Besides the filters, the parse reports what a commit decision needs to know:
  * pending   - the meaning may still change with the next word ("denim" -> "denim jacket",
                "under two" -> "under two thousand", a correction marker with no new value yet)
  * strength  - hard (exact or well-known synonym) or soft (plausible guess)
  * events    - word positions of corrections, late additions, polite closers
"""
from __future__ import annotations

from .lexicon import (BODY_FILLERS, EN_UNITS, EN_WEAK, FIXED_FRACTIONS, FRACTION_WORDS,
                      HI_UNITS, HI_WEAK, MULTIPLIERS, SINGLE_LETTER_SIZES, tokenize_word)

VALUE_KINDS = ("CAT", "COLOUR", "BRAND", "SIZE")
SLOT_OF = {"CAT": "category", "COLOUR": "colour", "BRAND": "brand", "SIZE": "size"}
FIELDS = ("category", "colour", "size", "brand", "max_price")
_RANK = {k: i for i, k in enumerate(("CAT", "COLOUR", "BRAND", "SIZE", "CORR", "PRICE_PRE",
                                     "SIZE_PRE", "NEG", "LATE", "CLOSER", "PRICE_POST",
                                     "SIZE_POST", "CURRENCY", "FILLER"))}


class Item:
    """A span of tokens with a meaning (and, for ambiguous phrases, its other meanings)."""
    __slots__ = ("kind", "value", "strength", "start", "end", "word", "end_word", "meanings",
                 "weak", "spelled", "boundary", "role")

    def __init__(self, kind, value, strength, start, end, word, end_word, meanings=None,
                 weak=False, spelled=False, boundary=""):
        self.kind, self.value, self.strength = kind, value, strength
        self.start, self.end = start, end              # token span [start, end)
        self.word, self.end_word = word, end_word      # request word span (inclusive)
        self.meanings = meanings or [(kind, value, strength)]
        self.weak = weak                               # weak number ("das", "do"...)
        self.spelled = spelled                         # number spelled in words (may grow)
        self.boundary = boundary                       # punctuation after the span
        self.role = None                               # for numbers: the field they filled

    def has(self, kind):
        return any(m[0] == kind for m in self.meanings)

    def get(self, kind):
        for m in self.meanings:
            if m[0] == kind:
                return m
        return None

    def __repr__(self):
        return f"{self.kind}:{self.value}@{self.word}"


class Slot:
    __slots__ = ("value", "strength", "word", "changes", "corrected", "mentions")

    def __init__(self, value, strength, word):
        self.value, self.strength, self.word = value, strength, word
        self.changes = 0          # times the value was replaced by a different one
        self.corrected = False    # replaced right after a correction marker
        self.mentions = 1

    def __repr__(self):
        return f"{self.value}({self.strength}@{self.word})"


class Parse:
    """The reading of a prefix."""

    def __init__(self):
        self.slots = {}                 # field -> Slot
        self.pending = set()            # reasons the meaning may still change
        self.events = []                # (word, kind): CORR, CORRECTED, LATE, CLOSER, NEG...
        self.items = []
        self.n_words = 0
        self.unknown = []               # words nobody understood (fallback search query)
        self.last_value_word = -1       # word index of the latest slot value
        self.body_end = -1              # last word that belongs to the request body
        self.tail = False               # the latest word is past the body (polite tail)
        self.value_end = -1             # last word of the latest value incl. its suffix
                                        # ("size 9 UK", "1700 rupees", "Pacevo brand")
        self.corr_done = False          # a correction has landed (its new value arrived)
        self.late_done = False          # a late addition has landed ("oh, and in blue")
        self.open_kinds = set()         # kinds of phrase the trailing words could grow into
        self.corr_unresolved = False    # a correction whose new value we could not read
        self.corr_suspect = None        # the field that correction probably meant

    def value(self, field):
        s = self.slots.get(field)
        return s.value if s else None

    def pending_fields(self):
        return {r[6:] for r in self.pending if r.startswith("field:")}

    def blocked(self):
        """A correction or negation is half-said (or was never understood): nothing said so far
        can be trusted enough to commit on."""
        return self.corr_unresolved or bool(
            self.pending & {"correction-open", "negation-open"})

    def filters(self, hard_only=False, include_pending=False):
        """Canonical filters, leaving out slots still pending (and soft ones if asked)."""
        out = {}
        skip = set() if include_pending else self.pending_fields()
        for f in ("category", "colour", "size", "brand", "max_price", "min_price"):
            s = self.slots.get(f)
            if s is None or f in skip or (hard_only and s.strength != "hard"):
                continue
            out[f] = s.value
        return out

    def report(self):
        """Filters in the evaluator's format (for its filter-accuracy printout)."""
        out = {}
        for f in FIELDS:
            v = self.value(f)
            if isinstance(v, tuple):
                v = v[0] if len(v) == 1 else None
            out[f] = v
        return out

    def count(self, kind):
        return sum(1 for _, k in self.events if k == kind)

    def last_event(self, kind):
        return max((w for w, k in self.events if k == kind), default=None)

    def __repr__(self):
        return f"Parse({self.slots}, pending={sorted(self.pending)}, events={self.events})"


# ---------------------------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------------------------

_TEN_MULTIPLES = {20, 30, 40, 50, 60, 70, 80, 90}


def parse_number(tokens, i):
    """Longest number expression starting at tokens[i].

    Returns (value, n_tokens, weak, spelled) or None. Understands "4500", "4.5k", "2 thousand",
    "forty five hundred", "one thousand five hundred", "twenty five", "saadhe teen hazaar",
    "pandrah sau", "dedh hazaar", "do hazaar paanch sau", "paune do hazaar".
    weak: the expression is a lone ambiguous word ("do", "ek", "das", "one") with no multiplier.
    """
    n = len(tokens)
    j = i
    total, group, frac = 0.0, 0.0, 0.0
    last = None          # None, digit, unit, teen, tens, hundred, thousand, fracword, fixed
    spelled = False
    multiplied = False
    weak_words = 0
    while j < n:
        if j > i and tokens[j - 1].boundary:
            break                                       # punctuation ends a number
        t = tokens[j]
        x = t.text
        if x in ("a", "an") and last is None and j + 1 < n and tokens[j + 1].text in MULTIPLIERS:
            group, last, spelled = 1.0, "unit", True
        elif x in FRACTION_WORDS and last in (None, "thousand"):
            frac, last, spelled = FRACTION_WORDS[x], "fracword", True
        elif x in FIXED_FRACTIONS and last in (None, "thousand"):
            group, last, spelled = FIXED_FRACTIONS[x], "fixed", True
        elif x in MULTIPLIERS:
            if last in (None, "fracword") or (last == "hundred" and MULTIPLIERS[x] < 1000):
                break
            if last == "thousand":
                break
            m = MULTIPLIERS[x]
            base = (group if group else 1.0) + frac
            frac = 0.0
            if m >= 1000:
                total += base * m
                group, last = 0.0, "thousand"
            else:
                group, last = base * m, "hundred"
            multiplied = True
            spelled = spelled or x not in ("k",)
        elif t.num is not None:
            if last not in (None, "thousand", "fracword"):
                break
            if last == "thousand" and t.num >= 1000:
                break
            group = t.num if last != "thousand" else t.num
            last = "digit"
        else:
            v = EN_UNITS.get(x, HI_UNITS.get(x))
            if v is None:
                break
            if x in HI_WEAK or x in EN_WEAK:
                weak_words += 1
            if v in _TEN_MULTIPLES and x in EN_UNITS:                   # twenty, thirty...
                if last not in (None, "thousand", "hundred", "fracword"):
                    break
                group = (group if last == "hundred" else 0.0) + v
                last = "tens"
            elif v < 10 and x in EN_UNITS:                             # one .. nine
                if last not in (None, "thousand", "hundred", "tens", "fracword"):
                    break
                group = (group if last in ("hundred", "tens") else 0.0) + v
                last = "unit"
            else:                                                       # teens, Hindi words
                if last not in (None, "thousand", "hundred", "fracword"):
                    break
                group = (group if last == "hundred" else 0.0) + v
                last = "teen"
            spelled = True
        j += 1
    if j == i or last in (None, "fracword"):
        return None
    value = total + group + (frac if last != "thousand" and frac else 0.0)
    if value <= 0:
        return None
    length = j - i
    weak = not multiplied and weak_words == length
    return value, length, weak, spelled


# ---------------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------------

class Understander:
    """Turns the words so far into a Parse. Stateless between calls."""

    def __init__(self, lexicon):
        self.lex = lexicon

    def tokenize(self, words):
        toks = []
        for i, w in enumerate(words):
            toks += tokenize_word(w.replace("’", "'").replace("‘", "'"), i)
        return toks

    # -- step 1: spans with meanings ------------------------------------------------------------
    def segment(self, toks):
        texts = [t.text for t in toks]
        items = []
        i = 0
        while i < len(toks):
            num = parse_number(toks, i)
            L, meanings = self.lex.lookup(texts, i)
            # a real number wins over a phrase of the same length; a weak one ("do", "one")
            # only when no phrase claims the word
            if num and ((not num[2] and num[1] >= L) or not L):
                value, length, weak, spelled = num
                items.append(Item("NUM", value, "hard", i, i + length, toks[i].word,
                                  toks[i + length - 1].word, weak=weak, spelled=spelled,
                                  boundary=toks[i + length - 1].boundary))
                i += length
                continue
            if L:
                kind, value, strength = self._primary(meanings, toks, i, L)
                items.append(Item(kind, value, strength, i, i + L, toks[i].word,
                                  toks[i + L - 1].word, meanings=meanings,
                                  boundary=toks[i + L - 1].boundary))
                i += L
                continue
            # an unknown word may be a misspelt or split brand: "urbanix", "zen trail"
            for span in (2, 1):
                if i + span > len(toks) or any(texts[j] in self.lex.trie or toks[j].num
                                               for j in range(i, i + span)):
                    continue
                brand = self.lex.fuzzy_brand("".join(texts[i:i + span]))
                if brand:
                    items.append(Item("BRAND", brand, "soft", i, i + span, toks[i].word,
                                      toks[i + span - 1].word,
                                      boundary=toks[i + span - 1].boundary))
                    i += span
                    break
            else:
                items.append(Item("UNK", toks[i].text, "hard", i, i + 1, toks[i].word,
                                  toks[i].word, boundary=toks[i].boundary))
                i += 1
        return items

    @staticmethod
    def _primary(meanings, toks, i, L):
        ranked = sorted(meanings, key=lambda m: _RANK.get(m[0], 99))
        if L == 1 and toks[i].text in SINGLE_LETTER_SIZES and not toks[i].upper:
            # a lowercase "s"/"m"/"l" is noise unless a size marker vouches for it (see parse)
            ranked = [m for m in ranked if m[0] != "SIZE"] or [("FILLER", None, "hard")]
        return ranked[0]

    # -- step 2: fill slots ---------------------------------------------------------------------
    def parse(self, words, toks=None):
        """Read the words so far. `toks` (their tokens) can be passed in to save re-tokenising."""
        p = Parse()
        p.n_words = len(words)
        if toks is None:
            toks = self.tokenize(words)
        items = self.segment(toks)
        p.items = items
        n = len(items)
        corr_armed = False      # a correction marker waits for its new value
        neg_left = 0            # items for which a negation stays armed

        def neighbour(k, step):
            k += step
            while 0 <= k < n and items[k].kind == "FILLER" and not (
                    items[k].has("PRICE_PRE") or items[k].has("SIZE_PRE")
                    or items[k].has("PRICE_POST") or items[k].has("SIZE_POST")
                    or items[k].has("CURRENCY")):
                k += step
            return items[k] if 0 <= k < n else None

        def set_slot(field, value, strength, word):
            nonlocal corr_armed, neg_left
            if neg_left > 0:
                neg_left = 0
                p.events.append((word, "NEGATED"))
                return
            old = p.slots.get(field)
            if old is not None and old.value == value:
                old.mentions += 1
                old.word = word
                if strength == "hard":
                    old.strength = "hard"
            else:
                s = Slot(value, strength, word)
                if old is not None:
                    s.changes = old.changes + 1
                    s.mentions = old.mentions + 1
                    s.corrected = corr_armed
                p.slots[field] = s
            if corr_armed:
                if old is None:
                    # the "corrected" value fills a slot never said before: we did not catch
                    # what was being corrected
                    p.corr_unresolved = True
                    p.events.append((word, "CORR-UNRESOLVED"))
                else:
                    p.events.append((word, "CORRECTED"))
                    if p.corr_suspect == field or old.value != value:
                        p.corr_unresolved = False
                corr_armed = False
            p.last_value_word = max(p.last_value_word, word)

        for k, it in enumerate(items):
            if neg_left > 0:
                neg_left -= 1
            kind = it.kind
            if kind == "NUM":
                prev = neighbour(k, -1)
                if prev is not None and prev.has("CURRENCY") and not prev.has("PRICE_PRE"):
                    before = neighbour(items.index(prev), -1)      # "below rs 2000"
                    if before is not None and before.has("PRICE_PRE"):
                        prev = before
                nxt = None if it.boundary else neighbour(k, +1)
                role = self._number_role(it, prev, nxt, p)
                if role is not None:
                    it.role = role[0]
                    set_slot(role[0], role[1], "soft" if it.weak and role[2] == "guess"
                             else "hard", it.end_word)
                continue
            if kind in VALUE_KINDS:
                value = it.value
                if kind == "CAT" and isinstance(value, str):
                    value = (value,)
                set_slot(SLOT_OF[kind], value, it.strength, it.end_word)
                continue
            if it.has("SIZE") and kind in ("FILLER", "UNK", "CORR", "LATE"):
                # lowercase "l"/"m"/"s" right next to "size": a size after all
                pv, nx = neighbour(k, -1), neighbour(k, +1)
                if (pv is not None and pv.has("SIZE_PRE")) or (nx is not None and nx.has("SIZE_POST")):
                    m = it.get("SIZE")
                    it.role = "size"
                    set_slot("size", m[1], "hard", it.end_word)
                    continue
            if kind == "CORR":
                corr_armed = True
                p.events.append((it.word, "CORR"))
                before = [x for x in items[:k] if x.kind in VALUE_KINDS or x.role]
                if before:
                    x = before[-1]
                    p.corr_suspect = x.role or SLOT_OF.get(x.kind)
            elif kind == "UNK" and corr_armed:
                # "I mean in flimp": the new value was not understood
                p.corr_unresolved = True
                p.events.append((it.word, "CORR-UNRESOLVED"))
                p.unknown.append(it.value)
                corr_armed = False
            elif kind == "NEG":
                neg_left = 3
                p.events.append((it.word, "NEG"))
            elif kind == "LATE":
                p.events.append((it.word, "LATE"))
            elif kind == "CLOSER":
                p.events.append((it.word, "CLOSER"))
            elif kind == "UNK":
                p.unknown.append(it.value)

        self._pending(p, items, len(words) - 1, corr_armed, neg_left > 0, toks)
        self._body_and_tail(p, items, toks)
        return p

    @staticmethod
    def _is_body(it, toks):
        """Does this span belong to the request body (filters and the words that glue them)?"""
        if it.kind in VALUE_KINDS or it.kind == "NUM" or it.role:
            return True
        if it.kind in ("PRICE_PRE", "PRICE_POST", "SIZE_PRE", "SIZE_POST", "CURRENCY", "CORR",
                       "NEG", "LATE"):
            return True
        if it.kind == "FILLER":
            words = {toks[j].text for j in range(it.start, it.end)}
            return bool(words & BODY_FILLERS) or any(
                it.has(k) for k in ("PRICE_PRE", "PRICE_POST", "SIZE_PRE", "SIZE_POST"))
        return False                                   # CLOSER, UNK, chit-chat

    def _body_and_tail(self, p, items, toks):
        body_end, value_end = -1, -1
        corr_at, late_at = None, None
        set_after_late = False
        seen_fields = set()
        for k, it in enumerate(items):
            if self._is_body(it, toks):
                body_end = max(body_end, it.end_word)
            is_value = it.kind in VALUE_KINDS or (it.kind == "NUM" and it.role) or (
                it.role == "size")
            if is_value:
                value_end = it.end_word
                field = it.role or SLOT_OF.get(it.kind)
                if late_at is not None and it.word > late_at and field not in seen_fields:
                    set_after_late = True
                seen_fields.add(field)
            elif value_end >= 0 and it.word == value_end + 1 and self._is_suffix(it, toks):
                value_end = it.end_word                # "UK", "rupees", "brand", "ka" ...
            if it.kind == "LATE":
                late_at = it.word
        p.body_end = body_end
        p.value_end = value_end
        p.corr_done = any(k == "CORRECTED" for _, k in p.events)
        p.late_done = set_after_late
        last = items[-1] if items else None
        if last is None or p.last_value_word < 0:
            p.tail = False
            return
        kinds = set(p.open_kinds)
        settled = p.pending_fields()
        if "max_price" in p.slots and "max_price" not in settled:
            kinds.discard("PRICE_PRE")        # budget already said: "for ..." is not "for under"
        if "size" in p.slots and "size" not in settled:
            kinds.discard("SIZE_PRE")
        if kinds:
            # the trailing words are still a phrase in progress: tail only if every way it can
            # finish is a polite closer ("for my" -> "for my dad"), not a filter ("for under")
            p.tail = kinds <= {"CLOSER", "FILLER"} and last.end_word > value_end
        elif last.kind == "UNK":
            # an unknown word may be an unseen correction marker ("err", "whoops"): it counts
            # as tail only after another non-body word already opened the tail
            prev = items[-2] if len(items) > 1 else None
            p.tail = (last.word > body_end and prev is not None and prev.word > body_end
                      and not self._is_body(prev, toks))
        else:
            p.tail = not self._is_body(last, toks) and last.word > body_end

    @staticmethod
    def _is_suffix(it, toks):
        if it.kind in ("SIZE_POST", "PRICE_POST", "CURRENCY") or it.has("SIZE_POST") \
                or it.has("PRICE_POST") or it.has("CURRENCY"):
            return True
        words = {toks[j].text for j in range(it.start, it.end)}
        return bool(words & {"brand", "ka", "ki", "ke", "wala", "wali", "wale", "colour",
                             "color", "coloured", "colored", "shade", "size"})

    def _number_role(self, it, prev, nxt, p):
        """Is this number a price or a size? -> (field, value, how) or None."""
        v = it.value
        prev_price = prev is not None and (prev.has("PRICE_PRE") or prev.has("CURRENCY"))
        prev_size = prev is not None and prev.has("SIZE_PRE")
        next_price = nxt is not None and (nxt.has("PRICE_POST") or nxt.has("CURRENCY"))
        next_size = nxt is not None and nxt.has("SIZE_POST")
        price_field = "max_price"
        if prev_price and prev.get("PRICE_PRE") and prev.get("PRICE_PRE")[1] == "min":
            price_field = "min_price"
        elif next_price and nxt.get("PRICE_POST") and nxt.get("PRICE_POST")[1] == "min" \
                and not (nxt.get("PRICE_POST")[1] == "max"):
            price_field = "min_price"
        if it.weak and not (prev_price or prev_size or next_price or next_size):
            return None
        if v >= 100:
            return (price_field, int(round(v)), "marked" if prev_price or next_price else "guess")
        whole = int(v) == v
        if (prev_size or next_size) and whole and int(v) in self.lex.numeric_sizes:
            return ("size", str(int(v)), "marked")
        if prev_price or next_price or not whole or int(v) not in self.lex.numeric_sizes:
            return None
        cat = p.value("category")
        if cat:
            allowed = set()
            for c in cat:
                allowed |= self.lex.sizes_by_category.get(c, set())
            if str(int(v)) not in allowed:
                return None
        return ("size", str(int(v)), "guess")

    def _pending(self, p, items, last_word, corr_open, neg_open, toks):
        if not items:
            return
        if corr_open:
            p.pending.add("correction-open")
        if neg_open:
            p.pending.add("negation-open")
        last = items[-1]
        if last.end_word != last_word:
            return
        size_slot, price_slot = p.slots.get("size"), p.slots.get("max_price")
        if last.kind == "NUM":
            if last.role == "size" and not last.spelled:
                pass                                     # "size 9" is settled
            elif last.role == "max_price" and not last.spelled and last.value >= 100:
                pass                                     # "under 1500" is settled
            else:
                fields = {"max_price", "size"} if last.role is None else {last.role}
                if last.spelled or last.weak or last.value < 100:
                    p.pending.update("field:" + f for f in fields)
                    p.pending.add("number-open")
        elif last.weak:
            p.pending.add("field:size")
            p.pending.add("number-open")
        if (last.has("PRICE_PRE") or last.has("CURRENCY")) and last.role is None:
            just_set = price_slot is not None and price_slot.word >= last.word - 1
            if not just_set:
                p.pending.add("price-open")
                p.pending.add("field:max_price")
        if last.has("SIZE_PRE") and last.role is None and last.kind != "SIZE":
            just_set = size_slot is not None and size_slot.word >= last.word - 1
            if not just_set:
                p.pending.add("size-open")
                p.pending.add("field:size")
        # could the trailing words grow into a phrase with a different value, or into a
        # correction ("I" -> "I mean", "make" -> "make that", "or" -> "or rather")?
        # Phrases can only grow from a span boundary, so only tails starting at one count.
        texts = [t.text for t in toks]
        starts = [it.start for it in items[-3:]]
        for start in starts:                           # the longest open phrase decides
            tail = texts[start:]
            if len(tail) > 4:
                continue
            kinds = self._open_kinds(tail)
            if kinds:
                p.open_kinds = kinds
                break
        # inside an open closer ("for my" -> "for my dad") a fragment like "my" is not the
        # start of "my mistake"
        closer_bound = bool(p.open_kinds) and p.open_kinds <= {"CLOSER", "FILLER"}
        for start in reversed(starts):                 # shortest tail first
            tail = texts[start:]
            if len(tail) > 4:
                continue
            changed, corr = self._completion_changes(tail)
            if changed:
                p.pending.update("field:" + f for f in changed)
                p.pending.add("phrase-open")
            if corr and not closer_bound:
                p.pending.add("corr-prefix")

    def _node(self, tail):
        node = self.lex.trie
        for t in tail:
            if t not in node:
                return None
            node = node[t]
        return node

    def _open_kinds(self, tail):
        """Kinds of the longer phrases `tail` is a proper prefix of (empty if none)."""
        node = self._node(tail)
        if node is None:
            return set()
        return {m[0] for m in self.lex.below(node)}

    def _completion_changes(self, tail):
        """(fields whose value would differ, could-become-a-correction) if `tail` grows."""
        node = self._node(tail)
        if node is None:
            return set(), False
        here = {(m[0], m[1]) for m in node.get(None, []) if m[0] in VALUE_KINDS}
        here_corr = any(m[0] in ("CORR", "NEG") for m in node.get(None, []))
        found, corr = set(), False
        for m in self.lex.below(node):
            if m[0] in VALUE_KINDS and (m[0], m[1]) not in here:
                found.add(SLOT_OF[m[0]])
            if m[0] in ("CORR", "NEG") and not here_corr:
                corr = True
        return found, corr
