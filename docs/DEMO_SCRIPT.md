# 3-minute demo video: shot list and narration

Setup before recording:
- Run `python demo/server.py` and open http://localhost:8765 in Chrome.
- Press **F11** for full screen. The console scales to fit any screen, so nothing is cut off.
- Click once anywhere on the page first, so the browser allows sound.
- In a second window, open a terminal at the repo root with a large font.
- Do one rehearsal pass so the first search is warm.

Keys (when the text box is not focused):

| Key | Does |
|---|---|
| `1`–`9` | Run that sample |
| `R` | Replay the current request |
| `S` / `B` / `E` | Replay it as the SAFE, BOLD or EAGER agent |
| `M` | Mute the sound effects |
| `Esc` | Stop a run |

What is on screen:
- **Signal** (left): the word just heard, what it means ("floaters → SANDALS"), the five
  filter reels, a plain-language decision log, and the risk tape.
- **Risk tape**: three copies of the agent race on the same words. EAGER locks the instant
  one product fits, BOLD waits one word, SAFE is our default. Hover the tape to rewind the
  whole screen to any word.
- **The shelf** (right): every product the one search fetched. Tiles drop out as words
  arrive.
- **Commit reactor**: the confidence, and the line it must cross.
- **Locked product**: where the product lands, and how many words early.

| Time | Do | Say (roughly) |
|---|---|---|
| 0:00–0:12 | Idle console | "Shoppers talk in fragments. A good salesperson is walking to the shelf before you finish. AgentX does that, and it never shows you a wrong product." |
| 0:12–0:40 | Press `1` (Plain) | "Each word is read as it arrives. 'Floaters' means sandals, so one search fetches that shelf: 75 products. 'Black', 'size 9', 'Strydo': 75, then 7, then 1. It locks two words before the shopper finishes. Notice the two reckless twins at the bottom locked even earlier. Now watch why we don't do that." |
| 0:40–1:15 | Press `2` (The trap) | "Same start. One product fits at 'navy', and EAGER and BOLD both lock it. Then the shopper says 'no, change that to Urbanyx'. The screen goes red: our agent saw a correction starting and held. The brand flips, the right sandal locks, still three words early. Both twins showed the wrong product." |
| 1:15–1:30 | Press `E`, let it run, then `S` | "This is the same request driven by the eager agent: wrong product shown. That is the failure the brief penalises most, and it is the one our risk model exists to prevent." |
| 1:30–1:48 | Press `6` (Hinglish) | "Hindi–English works the same way. 'Kaala' is black. 'Saadhe teen hazaar' is 3,500." |
| 1:48–2:05 | Click **SPEAK**, say "show me navy Pacevo casual shoes size eight under five thousand for my brother" | "Any speech-to-text works. Here the browser's recogniser streams words into the same agent." |
| 2:05–2:30 | `docs/ARCHITECTURE.md`, diagram and state table | "Three parts. A parser that also knows what isn't settled yet. One search that fetches the shelf. And a commit policy: once a product is the only match, only a correction can change it, so we measured how often each moment in a request is followed by one, and commit only where that never happened." |
| 2:30–2:52 | Terminal: `python kit/evaluate.py --agent agent.py` | "Official scorer: 45.2 against a baseline of 20.0, 100% accuracy, zero wrong commits, 301 searches for 300 requests. On 600 generated requests with wording the dev set never uses, still zero wrong commits." |
| 2:52–3:00 | README results table | "No model calls and no external services at run time: under five rupees of compute per million requests. Thank you." |

Tips:
- If you narrate live, press `M` first so the sound effects don't fight your voice, or keep
  them and add the narration afterwards.
- If voice recognition mishears, skip that shot. The typed samples show the same thing.
- For questions at the finals, hover the risk tape: it rewinds the whole screen to any word,
  which answers "what did it know at that point?" directly.
