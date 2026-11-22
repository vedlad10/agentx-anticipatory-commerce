"""Live demo server: python demo/server.py  ->  open http://localhost:8765

Runs the real Agent (the same class evaluate.py scores) behind a tiny JSON API, and serves a
page where you type, paste or *speak* a request (browser speech-to-text) and watch the agent
predict filters, narrow the shelf and commit, word by word.

Three copies of the agent race on every request, differing only in the commit threshold:
    eager  locks the instant one product matches (no risk model)
    bold   also commits mid-request, one word after the deciding value
    safe   the default: commits only in states with no observed wrong commit
so the page can show what the risk model buys: the eager twins lock early and sometimes wrong.

Standard library only.
"""
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit"))

from evaluate import Tools                                    # noqa: E402  (counted search)
from agent import Agent                                       # noqa: E402
from anticipate.nlu import SLOT_OF, VALUE_KINDS               # noqa: E402
from anticipate.policy import THRESHOLDS, CommitPolicy        # noqa: E402
from anticipate.shelf import matches                          # noqa: E402

HERE = Path(__file__).resolve().parent
LOCK = threading.Lock()
MODES = ("eager", "bold", "safe")
THRESHOLD = {"eager": 0.5, "bold": THRESHOLDS["bold"], "safe": THRESHOLDS["safe"]}
STATE_NOTE = {
    "unsettled": "a correction may be starting",
    "at-value": "the deciding word was just said: an 'oops, I mean…' could follow",
    "past-value": "the request is still going: a late correction is possible",
    "past-value-unknown": "an unknown word: it could be a correction",
    "tail": "the shopper has moved past the filters",
    "twist-done": "the correction or late addition has landed",
}
ROLE = {"CAT": "category", "COLOUR": "colour", "BRAND": "brand", "SIZE": "size",
        "CORR": "correction", "NEG": "correction", "LATE": "late", "CLOSER": "closer",
        "PRICE_PRE": "price", "PRICE_POST": "price", "CURRENCY": "price",
        "SIZE_PRE": "size", "SIZE_POST": "size", "UNK": "unknown", "FILLER": "filler"}

SAMPLES = [
    ("Plain", "I need black size 9 UK floaters by Strydo less than 0.8k for the gym"),
    ("The trap", "I need size 7 Strydo slides in navy, within Rs. 1500, no, change that to "
                 "Urbanyx for the gym"),
    ("Correction", "I need Pacevo navy tshirt medium, below eight hundred. no, change that "
                   "to large"),
    ("Mid-request fix", "hey, do you have any black oops, grey size M hooded sweatshirt by "
                        "Urbanyx, for under 1.1k for the gym"),
    ("Late constraint", "I'm looking for slides UK 10 not more than 3,500 from Kudova oh, "
                        "and in navy blue"),
    ("Hinglish", "mujhe kaala Urbanyx jacket budget saadhe teen hazaar, M size milega?"),
    ("Hindi numbers", "bhaiya, dikhao navy denims size 32, from Northweft pandrah sau se kam "
                      "chahiye"),
    ("Category last", "show me olive Urbanyx size 6 UK slides not more than seven hundred "
                      "nothing too flashy"),
    ("Unseen wording", "could you show me midnight blue sports shoes 7 number from Zentrail "
                       "for my sister"),
]


def card(p):
    return {"id": p["product_id"], "title": p["title"], "price": p["price"], "size": p["size"],
            "colour": p["colour"], "brand": p["brand"], "category": p["category"]}


class Runner:
    """The real Agent under one commit threshold."""

    def __init__(self, mode):
        self.mode = mode
        self.tools = Tools()
        self.agent = Agent(self.tools)
        self.agent.policy = CommitPolicy(mode, threshold=THRESHOLD[mode])
        self.start()

    def start(self):
        self.tools.searches = 0
        self.agent.start("live")
        self.commit_word = self.commit_card = None

    def word(self, w):
        out = self.agent.observe(w)
        if out.get("commit") and self.commit_word is None:
            self.commit_word = len(self.agent.words)
            prod = next((p for p in (self.agent.shelf.items or [])
                         if p["product_id"] == out["commit"]), None)
            self.commit_card = card(prod) if prod else {"id": out["commit"]}
        return out


class Session:
    def __init__(self):
        self.runners = {m: Runner(m) for m in MODES}
        self.reset("safe")

    def reset(self, mode):
        self.mode = mode if mode in MODES else "safe"
        for r in self.runners.values():
            r.start()
        self.times = []

    def lanes(self):
        return {m: {"commit_word": r.commit_word, "card": r.commit_card}
                for m, r in self.runners.items()}

    def word(self, w):
        main = self.runners[self.mode]
        out = None
        for m, r in self.runners.items():
            t0 = time.perf_counter()
            o = r.word(w)
            if m == self.mode:
                out = o
                self.times.append(time.perf_counter() - t0)
        a = main.agent
        tr = a.trace[-1]
        p = a.nlu.parse(a.words, a.toks)

        # what each word turned out to be, and whether a later word has overruled it
        roles = [{"word": x, "role": "filler", "stale": False} for x in a.words]
        for it in p.items:
            role, field, value = ROLE.get(it.kind, "filler"), None, None
            if it.kind == "NUM":
                role = {"max_price": "price", "min_price": "price", "size": "size"}.get(
                    it.role, "filler")
                if it.role in ("max_price", "min_price"):
                    field, value = it.role, int(round(it.value))
                elif it.role == "size":
                    field, value = "size", str(int(it.value))
            elif it.kind in VALUE_KINDS:
                field = SLOT_OF[it.kind]
                value = it.value
                if it.kind == "CAT" and not isinstance(value, tuple):
                    value = (value,)
            elif it.role == "size":
                role, field, value = "size", "size", it.get("SIZE")[1]
            stale = field is not None and (field not in p.slots or p.slots[field].value != value)
            for wi in range(it.word, it.end_word + 1):
                if roles[wi]["role"] == "filler" or role not in ("filler", "unknown"):
                    roles[wi]["role"] = role
                    roles[wi]["stale"] = stale

        hard = p.filters(hard_only=True)
        items = a.shelf.items or []
        match = [c for c in items if matches(c, hard)] if items else None
        return {
            "i": len(a.words), "word": w, "mode": self.mode, "state": tr["state"],
            "note": STATE_NOTE.get(tr["state"], ""), "confidence": out["confidence"],
            "threshold": a.policy.threshold, "commit": out.get("commit"),
            "n": tr["candidates"],
            "filters": out["filters"], "pending": sorted(p.pending_fields()),
            "soft": sorted(f for f, s in p.slots.items() if s.strength == "soft"),
            "roles": roles,
            "shelf_key": a.shelf.key,
            "shelf_items": [card(c) for c in items],
            "matching_ids": None if match is None else [c["product_id"] for c in match],
            "searches": main.tools.searches,
            "ms": round(1000 * self.times[-1], 2),
            "lanes": self.lanes(),
        }

    def finish(self):
        main = self.runners[self.mode]
        a = main.agent
        final = a.finish()
        prod = next((p for p in (a.shelf.items or []) if p["product_id"] == final), None)
        n = len(a.words)
        lanes = self.lanes()
        for m, r in self.runners.items():
            r.agent.finish()
            lane = lanes[m]
            if r.commit_word is None:
                lane["status"], lane["early"] = "end", 0
            elif r.commit_card["id"] == final:
                lane["status"], lane["early"] = "right", n - r.commit_word
            else:
                lane["status"], lane["early"] = "wrong", 0
        return {"final": card(prod) if prod else {"id": final}, "mode": self.mode,
                "words": n, "lanes": lanes, "searches": main.tools.searches,
                "ms_per_word": round(1000 * sum(self.times) / max(1, len(self.times)), 2)}


SESSION = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/samples":
            self.send(200, [{"label": l, "text": t} for l, t in SAMPLES])
        else:
            self.send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        with LOCK:
            if self.path == "/api/start":
                SESSION.reset(body.get("mode", "safe"))
                self.send(200, {"ok": True, "modes": list(MODES)})
            elif self.path == "/api/word":
                words = str(body.get("word", "")).split()
                out = None
                for w in words:
                    out = SESSION.word(w)
                self.send(200, out or {"error": "empty word"})
            elif self.path == "/api/finish":
                self.send(200, SESSION.finish())
            else:
                self.send(404, {"error": "not found"})


def port_in_use(port):
    """Is something already answering on this port? (On Windows a second server can bind the
    same port without an error, and the older one keeps receiving the requests.)"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    global SESSION
    port = int(os.environ.get("PORT", "8765"))
    if port_in_use(port):
        sys.exit(f"Port {port} is already in use: an older demo server is probably still "
                 f"running. Stop it, or start this one on another port (PORT=8766).")
    SESSION = Session()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"AgentX live demo on http://localhost:{port}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
