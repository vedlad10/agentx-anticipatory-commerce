"""Unit tests: python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit"))

from search import load_catalogue                      # noqa: E402
from anticipate.lexicon import Lexicon                  # noqa: E402
from anticipate.nlu import Understander                 # noqa: E402
from anticipate.policy import state_of                  # noqa: E402

LEX = Lexicon(load_catalogue())
NLU = Understander(LEX)


def parse(text):
    return NLU.parse(text.split())


def filters(text):
    return parse(text).report()


class Numbers(unittest.TestCase):
    def price(self, text):
        return filters(text)["max_price"]

    def test_digits_and_k(self):
        self.assertEqual(self.price("shoes under 2,000"), 2000)
        self.assertEqual(self.price("shoes less than 0.8k"), 800)
        self.assertEqual(self.price("shoes under 1.1k"), 1100)
        self.assertEqual(self.price("shoes up to ₹1500"), 1500)
        self.assertEqual(self.price("shoes budget Rs. 4000"), 4000)
        self.assertEqual(self.price("shoes 1500/-"), 1500)

    def test_english_words(self):
        self.assertEqual(self.price("shoes within forty five hundred"), 4500)
        self.assertEqual(self.price("shoes below one thousand five hundred"), 1500)
        self.assertEqual(self.price("shoes under two thousand five hundred"), 2500)
        self.assertEqual(self.price("shoes max one thousand one hundred"), 1100)
        self.assertEqual(self.price("shoes under a thousand"), 1000)

    def test_hindi_words(self):
        self.assertEqual(self.price("jacket budget saadhe teen hazaar"), 3500)
        self.assertEqual(self.price("jeans pandrah sau se kam"), 1500)
        self.assertEqual(self.price("joggers satrah sau ke andar"), 1700)
        self.assertEqual(self.price("jacket dhai hazaar tak"), 2500)
        self.assertEqual(self.price("kurta dedh hazaar tak"), 1500)
        self.assertEqual(self.price("watch do hazaar paanch sau tak"), 2500)

    def test_do_you_have_is_not_two(self):
        self.assertIsNone(self.price("do you have black sneakers"))


class Sizes(unittest.TestCase):
    def size(self, text):
        return filters(text)["size"]

    def test_shoe_sizes(self):
        self.assertEqual(self.size("runners size nine"), "9")
        self.assertEqual(self.size("runners UK 10"), "10")
        self.assertEqual(self.size("runners size 9 UK"), "9")
        self.assertEqual(self.size("sneakers das number"), "10")

    def test_letters(self):
        self.assertEqual(self.size("tee L size"), "L")
        self.assertEqual(self.size("tee extra large"), "XL")
        self.assertEqual(self.size("jacket double XL"), "XXL")
        self.assertEqual(self.size("joggers 2XL"), "XXL")
        self.assertEqual(self.size("tee size m"), "M")          # lowercase, but next to "size"

    def test_waist(self):
        self.assertEqual(self.size("jeans 32 waist"), "32")
        self.assertEqual(self.size("denims waist 28"), "28")


class Corrections(unittest.TestCase):
    def test_last_mention_wins(self):
        f = filters("show me black oops, grey hoodie")
        self.assertEqual(f["colour"], "grey")
        f = filters("tee medium, below eight hundred. no, change that to large")
        self.assertEqual(f["size"], "L")
        self.assertEqual(f["max_price"], 800)

    def test_correction_in_progress_blocks(self):
        self.assertTrue(parse("Pacevo navy tee size M. no,").blocked())
        self.assertIn("corr-prefix", parse("Pacevo navy tee size M, I").pending)

    def test_unreadable_correction_stays_blocked(self):
        p = parse("jacket in brown, I mean in flimp, by Urbanyx")
        self.assertTrue(p.corr_unresolved)
        self.assertTrue(p.blocked())

    def test_negation(self):
        self.assertEqual(filters("white sneakers, not black")["colour"], "white")


class Pending(unittest.TestCase):
    def test_number_still_growing(self):
        p = parse("tee under two")
        self.assertIn("max_price", p.pending_fields())

    def test_phrase_still_growing(self):
        self.assertIn("category", parse("Northweft black denim").pending_fields())
        self.assertNotIn("colour", parse("Loomsy navy").pending_fields())   # navy blue = navy

    def test_suffix_closes_size(self):
        self.assertNotIn("size", parse("olive Urbanyx size 6 UK").pending_fields())


class States(unittest.TestCase):
    def test_tail_after_closer_prefix(self):
        self.assertEqual(state_of(parse("Kudova slides black size 7 for my")), "tail")
        self.assertNotEqual(state_of(parse("Kudova slides black size 7 for")), "tail")

    def test_twist_done(self):
        self.assertEqual(state_of(parse("Strydo hoodie in navy, nahi, in olive green")),
                         "twist-done")

    def test_at_value(self):
        self.assertEqual(state_of(parse("Pacevo navy tee medium")), "at-value")


class EndToEnd(unittest.TestCase):
    def test_agent_commits_early_and_right(self):
        sys.path.insert(0, str(ROOT / "kit"))
        import evaluate
        from agent import Agent
        req = {"id": "t-1", "words": "I need black size 9 UK floaters by Strydo less than "
                                     "0.8k for the gym".split(),
               "target": "P0206", "earliest": 9, "filters": {}}
        results, _ = evaluate.run(Agent, [req])
        r = results[0]
        self.assertTrue(r["correct"])
        self.assertEqual(r["wrong_commits"], 0)
        self.assertGreater(r["early_words"], 0)
        self.assertLessEqual(r["searches"], 1)


if __name__ == "__main__":
    unittest.main()
