"""Drive one practice conversation end to end against a running API.

    python tests/test_practice_flow.py                       # production
    python tests/test_practice_flow.py --base http://localhost:8001
    python tests/test_practice_flow.py --staff <uuid>

Checks the things that actually have to hold for the demo:

  1. a new attempt opens with exactly CE_MAX_PRACTICE_TURNS turns
  2. the counter goes down by one per staff turn and never below zero
  3. finishing unlocks after two turns, not before
  4. the guest reacts to what was said rather than reciting a script
  5. the turn AFTER the last one is refused, not silently accepted
  6. completing produces a scored result with evidence

It spends real money: one guest reply per turn plus one scoring run, so
roughly a cent. It also writes to whatever database the API is pointed at, so
pass --staff someone outside the demo narrative when running it against
production, and restore from demo-state-backup afterwards if it matters.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")

results: list[tuple[str, bool, str]] = []


class Failure(Exception):
    pass


def call(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-CE-Actor": "Diego"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200].decode("utf-8", "replace")}


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {name:<46} {DIM}{detail}{RESET}")


REPLIES = [
    "I'm really sorry about that, let me check the allergen sheet for you "
    "right now so we know exactly what is in the room.",
    "I've taken the nut items out of your room and I'm having it cleaned "
    "again before you go up.",
    "I'll flag your allergy on your booking so the kitchen and housekeeping "
    "both see it for the rest of your stay.",
    "Is there anything else I can do to make you feel comfortable tonight?",
    "This fifth message should never be accepted.",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://coaching-engine-api.onrender.com")
    ap.add_argument("--staff", default="b0e38c7f-bd4c-5160-8648-6afc90bff1eb")
    args = ap.parse_args()
    base = args.base.rstrip("/") + "/api/v1"

    print(f"\nPractice flow against {args.base}\n")

    # ---------------------------------------------------------------- open
    status, scen = call(base, "GET", "/scenarios")
    rows = scen if isinstance(scen, list) else scen.get("scenarios", [])
    if not rows:
        print(f"{RED}No scenarios to practise{RESET}")
        return 1
    sid = rows[0]["id"]

    status, attempt = call(base, "POST", f"/scenarios/{sid}/attempts",
                           {"staff_id": args.staff})
    if status != 201:
        print(f"{RED}Could not open an attempt: HTTP {status} {attempt}{RESET}")
        return 1
    attempt_id = attempt["id"]
    opening = (attempt.get("turns") or [{}])[0]
    limit = opening.get("turns_remaining")

    check("opens with 4 turns", limit == 4, f"turns_remaining={limit}")
    check("cannot finish before speaking", opening.get("can_complete") is False,
          f"can_complete={opening.get('can_complete')}")
    opening_line = (opening.get("content")
                    or (opening.get("guest") or {}).get("content") or "")
    check("guest speaks first", bool(opening_line.strip()),
          opening_line[:56] + ("..." if opening_line else "EMPTY"))

    # ---------------------------------------------------------------- turns
    guest_lines = [opening_line]
    expected = limit
    for i in range(limit):
        status, turn = call(base, "POST", f"/attempts/{attempt_id}/turns",
                            {"content": REPLIES[i]})
        if status != 200 and status != 201:
            check(f"turn {i + 1} accepted", False, f"HTTP {status} {turn}")
            break
        expected -= 1
        got = turn.get("turns_remaining")
        check(f"turn {i + 1}: counter reads {expected}", got == expected,
              f"turns_remaining={got}")
        if i == 0:
            check("still locked after one turn",
                  turn.get("can_complete") is False,
                  f"can_complete={turn.get('can_complete')}")
        if i == 1:
            check("finish unlocks after two turns",
                  turn.get("can_complete") is True,
                  f"can_complete={turn.get('can_complete')}")
        # The reply is nested under "guest"; reading turn["content"] gives
        # nothing and made this check pass vacuously the first time.
        guest_lines.append((turn.get("guest") or {}).get("content") or "")

    check("counter reached zero", expected == 0, f"turns_remaining={expected}")

    # The guest has to respond to what was said. Identical replies every time
    # would mean the scenario is a recording with a chat box on top.
    distinct = len({ln.strip() for ln in guest_lines if ln.strip()})
    check("guest replies are all different", distinct == len(
        [ln for ln in guest_lines if ln.strip()]),
        f"{distinct} distinct of {len(guest_lines)}")

    # ------------------------------------------------------- one turn too many
    status, extra = call(base, "POST", f"/attempts/{attempt_id}/turns",
                         {"content": REPLIES[4]})
    check("the 5th turn is refused", status >= 400,
          f"HTTP {status} {str(extra)[:70]}")

    # ------------------------------------------------------------- complete
    status, done = call(base, "POST", f"/attempts/{attempt_id}/complete")
    check("completes", status in (200, 201), f"HTTP {status}")

    result = done.get("result") or done
    dims = result.get("dimensions") or result.get("scores") or []
    check("returns a scored result", bool(dims), f"{len(dims)} dimensions")
    if dims:
        first = dims[0]
        check("each dimension carries a level",
              first.get("level") is not None or first.get("score") is not None,
              json.dumps(first)[:70])
    ev = result.get("evidence") or []
    check("scores cite the conversation", bool(ev), f"{len(ev)} evidence items")

    # ------------------------------------------------------------- summary
    failed = sum(1 for _, ok, _ in results if not ok)
    print()
    if failed:
        print(f"{RED}{failed} of {len(results)} checks failed{RESET}")
    else:
        print(f"{GREEN}{len(results)}/{len(results)} checks passed{RESET}")
    print(f"{DIM}attempt {attempt_id}{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
