# AgentX: finding the product before the shopper finishes

**The problem.** Shoppers speak in fragments: "black running shoes, size nine, under two
thousand…". Assistants wait for the full sentence, then search. A good salesperson is at the
shelf by "running shoes" and hands over the right pair the moment they are sure, never a wrong
one.

**What we built.** AgentX reads a request word by word, predicts the five filters (category,
colour, size, brand, budget), fetches the right shelf with one search, and shows the product
once a calibrated confidence says nothing still to come can change it. It handles Hindi–English
("kaala jacket saadhe teen hazaar tak", "das number"), spelled-out prices, synonyms
("floaters", "lowers"), corrections ("black — no wait, white") and late constraints.

**Innovation.**
1. *Risk-aware commits.* Once a product is the only match, a late addition cannot change it;
   only a correction can. AgentX tracks where the shopper is in the request (deciding word just
   said, still going, closing words, correction already made) and uses each state's measured
   error rate as its confidence. Safe mode commits only in states with zero observed errors.
2. *Knowing what it doesn't know yet.* The parser flags half-said numbers ("under two…"),
   phrases that may still change meaning ("denim…" could become "denim jacket") and half-said
   corrections, and never commits on them.
3. *Walk-to-the-shelf retrieval.* One counted search fetches the category; later words narrow
   it locally. The dev run needs 301 searches for 300 requests, and the limit on wasted
   searches is tunable down to zero.
4. *Tested beyond the dev set.* On 600 generated requests with unseen synonyms, number formats,
   correction markers and gibberish words, accuracy stays 100% on unseen wording and wrong
   commits stay at zero.

**Results** (official evaluate.py, dev.jsonl). Score 45.2 (baseline 20.0), accuracy 100%
(baseline 52.7%) and zero wrong commits. Corrections, late constraints and Hindi–English
requests are all at 100%. A tunable bold mode reaches 46.1.

**Impact.** Shoppers see the right product while still speaking: 168 of 300 dev requests were
answered early, by up to 7 words. That cuts time-to-product in voice commerce, kiosks and chat,
and since the agent never shows a wrong product, trust holds. The same policy can gate any
early action a streaming agent takes, such as adding to cart.

**Cost and scale.** There are no model calls and no external services at run time. The agent
needs about 0.3 ms of CPU per word, 3.6 ms per request, so one core serves over 150 requests
per second. A million requests a day take about one vCPU-hour, under ₹5 of cloud compute, plus
one catalogue search per request. An LLM-per-word design would need about 13 model calls per
request.

**Build summary.** Python 3.9+, standard library only, about 2,500 lines with 18 unit tests.
The live console, with voice input, races the agent against two eager variants of itself.
Everything runs offline and reproduces from the repository.
