"""Prove the spoken-observation extractor cannot invent evidence.

    python tests/test_voice_observation.py                  # offline checks only
    python tests/test_voice_observation.py --base http://localhost:8077

The offline half needs no API, no network and no money: it drives the matcher
and the name resolver directly, including a stubbed model that fabricates,
which a real model will not do to order. The --base half calls a running API
and spends about a cent.

What has to hold:

  1. an exact quote is found, and the span is the manager's real words
  2. a quote that elides a word is still found, because models compress
  3. a PARAPHRASE is refused, which is the whole point
  4. an invented quote is refused
  5. words gathered from across the note are refused
  6. a fabricated rating is dropped rather than shown
  7. a person is never guessed between two candidates
  8. a name nobody has comes back unmatched, not attached to somebody
  9. a person the manager named but never rated is still returned, flagged
 10. only a manager can draft an observation
 11. nothing in the draft path writes to the database
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "api"))

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    mark = f"{GREEN}pass{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  {mark}  {name}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


ROSTER = [
    {"id": "s1", "name": "Diego Ramos", "department": "front_office"},
    {"id": "s2", "name": "Maria Santos", "department": "housekeeping"},
    {"id": "s3", "name": "Maria Oliveira", "department": "f_and_b"},
    {"id": "s4", "name": "Amara Okafor", "department": "front_office"},
]

NOTE = (
    "Diego handled the checkout dispute. He stayed completely calm even though "
    "the guest was shouting at him, but he never actually offered her anything "
    "to fix it."
)


def offline_checks() -> None:
    from app import voice_observation as vo

    print("\nEvidence matching")
    span = vo._find_span(NOTE, "stayed completely calm")
    check("exact quote is found", span is not None
          and NOTE[span[0]:span[1]] == "stayed completely calm")

    # The real failure seen in testing: the model drops an interior word as it
    # quotes. The rating is still supported, so refusing it would throw away a
    # true observation on a technicality.
    span = vo._find_span(NOTE, "never actually offered anything to fix it")
    check("elided quote is found", span is not None,
          NOTE[span[0]:span[1]] if span else "not found")

    check("paraphrase is refused",
          vo._find_span(NOTE, "he remained composed throughout") is None)
    check("invention is refused",
          vo._find_span(NOTE, "he shouted back at the guest") is None)
    check("words from across the note are refused",
          vo._find_span(NOTE, "Diego calm anything") is None)

    print("\nWho it was")
    check("first name resolves when unique",
          vo.resolve_name("Diego", ROSTER)["status"] == "matched")
    ambiguous = vo.resolve_name("Maria", ROSTER)
    check("two Marias is a question, not a guess",
          ambiguous["status"] == "ambiguous"
          and len(ambiguous["candidates"]) == 2)
    check("an unknown name stays unmatched",
          vo.resolve_name("Kevin", ROSTER)["status"] == "unmatched")

    print("\nThe gate, with a model that fabricates")
    # A real model will not invent on demand, so stand in for one that does.
    real_complete = vo.complete
    try:
        vo.complete = lambda *a, **k: {"observations": [{
            "staff_name": "Diego",
            "moment": "complaint",
            "scope": "full",
            "what_happened": "Handled a dispute.",
            "ratings": [
                {"dimension": "composure", "level": 4,
                 "quote": "stayed completely calm"},          # real
                {"dimension": "empathy", "level": 1,
                 "quote": "he was cold and dismissive"},      # invented
                {"dimension": "communication", "level": 2,
                 "quote": "his explanation was muddled"},     # invented
            ],
        }]}
        out = vo.draft_from_text(NOTE, ROSTER)
        kept = out["drafts"][0]["ratings"] if out["drafts"] else []
        check("the supported rating survives",
              [r["dimension"] for r in kept] == ["composure"],
              f"kept {[r['dimension'] for r in kept]}")
        check("both fabrications are dropped", out["dropped_ratings"] == 2,
              f"dropped {out['dropped_ratings']}")

        # A person named but never rated must still come back. Dropping them
        # would be a silent failure: nobody notices an absence.
        vo.complete = lambda *a, **k: {"observations": [{
            "staff_name": "Amara", "moment": "routine", "scope": "partial",
            "what_happened": "Was on the desk.",
            "ratings": [{"dimension": "empathy", "level": 3,
                         "quote": "she was lovely with them"}],
        }]}
        out = vo.draft_from_text(NOTE, ROSTER)
        check("an unrateable person is returned, flagged",
              len(out["drafts"]) == 1 and out["drafts"][0]["needs_rating"] is True
              and out["drafts"][0]["ratings"] == [])
    finally:
        vo.complete = real_complete


def call(base: str, path: str, body: dict, actor: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-CE-Actor": actor,
                 "Idempotency-Key": "voice-observation-test"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "{}")


def live_checks(base: str) -> None:
    print("\nAgainst a running API")
    status, _ = call(base, "/api/v1/observations/draft",
                     {"text": "Diego was calm with that guest."}, "Diego")
    check("a staff member cannot draft an observation", status == 403,
          f"HTTP {status}")

    status, body = call(base, "/api/v1/observations/draft", {"text": ""}, "Marta")
    check("empty text is refused", status == 422, f"HTTP {status}")

    before = count_observations(base)
    status, body = call(base, "/api/v1/observations/draft", {"text": NOTE}, "Marta")
    check("a manager gets drafts back", status == 200 and body.get("drafts"),
          f"HTTP {status}, {len(body.get('drafts', []))} draft(s)")

    spans_ok = all(
        body["transcript"][r["span"][0]:r["span"][1]] == r["quote"]
        for d in body.get("drafts", []) for r in d["ratings"])
    check("every span points at the quote it claims", spans_ok)

    # The promise the whole design rests on.
    check("drafting wrote nothing to the database",
          count_observations(base) == before,
          f"{before} before, {count_observations(base)} after")


def count_observations(base: str) -> int:
    req = urllib.request.Request(base.rstrip("/") + "/api/v1/observations",
                                 headers={"X-CE-Actor": "Marta"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return len(json.loads(r.read()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="run the live checks against this API too")
    args = ap.parse_args()

    for name in ("OPENAI_API_KEY",):
        if not os.environ.get(name):
            env = pathlib.Path(__file__).resolve().parents[1] / ".env"
            if env.is_file():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.strip() and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(),
                                              v.strip().strip('"').strip("'"))

    offline_checks()
    if args.base:
        live_checks(args.base)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print(f"{RED}failed:{RESET} " + ", ".join(r[0] for r in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
