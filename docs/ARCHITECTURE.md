# AgentX: Architecture Note (Challenge 1, Anticipatory Commerce)

A deterministic agent in standard-library Python, with no model calls and no network. It reads
a request word by word, keeps a live reading of the filters, fetches the shelf with one counted
search, and commits when a calibrated risk model says nothing still to come can change the
answer.

```
word ─► tokenise ─► incremental parser ─► filters · what is still pending · events
                    (phrase trie, number         ▼
                     grammar, last mention wins)  shelf: 1 counted search (the category)
                                                  narrowed locally on every word
                                                  ▼
                        policy: request state ─► measured risk ─► confidence ≥ τ ?  commit | wait
                                                  ▼
                        finish(): re-read the whole request and answer from it
```

**1. Understanding** (`nlu.py`, `lexicon.py`). Canonical values come from `catalogue.csv`. A
curated layer adds English, Indian-English and romanised-Hindi forms (kicks, lowers, kaala,
"das number"), and misspelt brands are caught by edit distance. A phrase trie takes the longest
match. A number grammar reads "0.8k", "forty five hundred" and "saadhe teen hazaar", and
context decides price or size. The prefix is re-read on every word, so a slot holds its last
mention and corrections need no special case. The parser also flags what is **not settled**:

- a number still growing ("under two…")
- a phrase whose meaning can change ("denim…" could become "denim jacket")
- a correction not yet landed, or not understood
- a word that may start a correction ("I…" could become "I mean")

**2. Shelf** (`shelf.py`). Once the category is known, one search fetches it (at most 89
products, one page) and later words narrow it locally. A search that would overflow a page
waits for another filter. Dev needs 301 searches for 300 requests. The limit on wasted
searches is tunable down to zero.

**3. Calibrated commits** (`policy.py`). A late addition cannot move a product that is already
the only match; only a correction can. So confidence is the chance that no correction is
still coming, given where the shopper is. Each state's errors on dev, measured at the first
unique moment per request (`tools/calibrate.py`):

| state | wrong/seen | state | wrong/seen |
|---|---|---|---|
| unsettled (correction half-said) | 21/29 | tail ("for my dad", "thanks", "chahiye") | 0/121 |
| at-value (deciding word just said) | 18/194 | twist-done (correction/late addition landed) | 0/99 |
| past-value (request still going) | 2/48 | | |

`confidence = (1 − risk) / #matching products`, and the agent commits when this is ≥ τ.
*Safe* mode (τ = 0.99, the default) commits only in zero-error states. *Bold* mode (τ = 0.94)
also commits mid-request.

**4. Final check.** `finish()` re-reads the full request and answers from the shelf. If
nothing matches, it relaxes the least-trusted filter first.

**Results** (official `evaluate.py`, dev.jsonl, safe mode):

| Request type | Requests | Accuracy | Wrong commits | Earliness | Score |
|---|---|---|---|---|---|
| Corrections | 55 | 100% | 0 | 13.1% | 47.8 |
| Late constraints | 50 | 100% | 0 | 10.7% | 46.4 |
| Hindi–English | 25 | 100% | 0 | 8.4% | 45.1 |
| Plain | 177 | 100% | 0 | 7.1% | 44.3 |
| **All** | 300 | 100% | 0 | 8.6% | **45.2** (baseline 20.0) |

On 600 generated stress requests (unseen wording, gibberish words) wrong commits stay at zero.
Agent compute is about 0.3 ms per word.
