# Round 1 submission checklist (deadline: 30 November 2026, 11:59 PM IST)

The organisers' email of 22 November says the deadline is strict, with no extensions.
Registration closes **the same night** as submission, so do step 1 first.

## What changed on 22 November

- The requirement to use Rezolve Labs capabilities was **removed**. Nothing in this repository
  uses them, and no API key or coupon is needed.
- The starter kit was re-issued as `ps1-anticipatory-commerce-no-rezolve.zip`. It is already in
  `kit/`. Only its README and one docstring changed; the data, the search function and the
  scoring are identical, so every score in this repository still stands.
- The problem-statement PDF linked from the email still describes Rezolve as required, but its
  own starter-kit link is the no-Rezolve kit. The email and the kit are consistent with each
  other. If you want it in writing, ask in the portal's Doubt section.

## Steps

1. **Register the team** at techfest.org (AgentX, Challenge 1) and note the Team ID. Only the
   team leader can submit.
2. **Regenerate the outputs** (takes about a minute):
   - `python kit/evaluate.py --agent agent.py --log outputs/dev_results.jsonl > outputs/dev_score.txt`
   - `python -m unittest discover -s tests`
3. **Keep the repository up to date.** The code is public on GitHub at
   https://github.com/vedlad10/agentx-anticipatory-commerce. Push any last changes
   (`git push`) before you submit, then open the link in a private browser window to confirm
   the jury sees the latest version.
4. **Record the 3-minute video** using [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Upload it as MP4.
5. **Make the Google Drive folder**, shared as "anyone with the link can view". It should
   contain:
   - `Abstract.pdf`: [ABSTRACT.md](ABSTRACT.md), max 500 words (currently about 480). Add the team
     name and members.
   - `Architecture_Note.pdf`: [ARCHITECTURE.md](ARCHITECTURE.md), one page.
   - `Demo_Video.mp4`
   - `Code_Repository_Link.txt`: the GitHub URL
   - `outputs/`: `dev_results.jsonl` and `dev_score.txt`
6. **The team leader submits** the Drive link in the "Submission Link" field on the Techfest
   site. Leave a buffer of a day; late entries are not accepted.
7. Afterwards, watch the Techfest portal's Doubt section and the email from
   siddhi@techfest.org. Round 1 results come out by 5 December, and the finals are
   16–18 December at IIT Bombay.

If the organisers issue another kit update, replace the files in `kit/` and repeat step 2.
