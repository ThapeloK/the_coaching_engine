"""
test_e2e.py
===========
Drive the running system over HTTP, the way the product is actually used.

    python tests/test_e2e.py                 # against localhost
    python tests/test_e2e.py --base http://127.0.0.1:8000/api/v1
    python tests/test_e2e.py --skip-ai       # deterministic paths only

This is not a unit test and does not replace one. services/agent has 72 tests
that pin the reasoning with no I/O at all, and they run in a second. This is
the other half: it proves the pieces are wired to each other, which unit tests
by construction cannot, and it is the check to run before a pitch.

Two rules it holds itself to:

* It asserts BEHAVIOUR, not prose. A model writes the headlines, so asserting
  their wording would produce a test that fails on a good day. It asserts that
  a recommendation cites both evidence streams, that a blocked quadrant never
  recommends training, that a colleague reads zero rows.
* An abstention is a pass. The product declining to advise is the feature; a
  test that demanded a recommendation every time would push us toward the
  behaviour we built this to avoid.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")

results: list[tuple[str, bool, str]] = []


class Failure(AssertionError):
    pass


def call(method: str, path: str, body=None, actor: str = "Marta",
         raw: bool = False, timeout: int = 120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"X-CE-Actor": actor, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return (r.status, payload) if raw else (r.status, json.loads(payload))
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, {"raw": payload[:200].decode("utf-8", "replace")}


def check(name: str):
    """Decorator that turns a function into one reported line."""
    def wrap(fn):
        def run():
            started = time.time()
            try:
                detail = fn() or ""
                results.append((name, True, detail))
                mark, colour = "PASS", GREEN
            except Failure as exc:
                results.append((name, False, str(exc)))
                detail, mark, colour = str(exc), "FAIL", RED
            except Exception as exc:                        # noqa: BLE001
                results.append((name, False, f"{type(exc).__name__}: {exc}"))
                detail, mark, colour = f"{type(exc).__name__}: {exc}", "FAIL", RED
            ms = int((time.time() - started) * 1000)
            print(f"  [{colour}{mark}{RESET}] {name:44} {ms:>6}ms  {detail}")
        run.__name__ = fn.__name__
        return run
    return wrap


def need(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


# ----------------------------------------------------------------- the flow

@check("service is up, database attached")
def t_health():
    # /health sits outside the versioned prefix on purpose: a load balancer
    # should not have to know which API version is current to ask whether the
    # process is alive.
    root = BASE.split("/api/")[0]
    req = urllib.request.Request(root + "/health")
    with urllib.request.urlopen(req, timeout=15) as r:
        status, body = r.status, json.loads(r.read())
    need(status == 200, f"HTTP {status}")
    need(body.get("database") == "up", f"database {body.get('database')}")
    idx = body.get("search_index", {})
    # An unembedded corpus makes the whole product abstain while every check
    # below still passes. This is the single most valuable assertion here.
    need(idx.get("ready"),
         f"search index not ready: {idx.get('embedded')} of {idx.get('chunks')} "
         f"chunks embedded. Run scripts/bootstrap.py to backfill.")
    live = [k for k, v in body.get("providers", {}).items() if v]
    return (f"{idx['embedded']}/{idx['chunks']} chunks embedded; "
            f"providers: {', '.join(sorted(live))}")


@check("roster resolves uuid, generator id and name")
def t_staff_refs():
    seen = {}
    for ref in ("staff-001", "Diego", "9f2c-diego"):
        status, body = call("GET", f"/staff/{ref}/gap")
        need(status == 200, f"{ref} -> HTTP {status}")
        seen[ref] = body["staff_id"]
    need(len(set(seen.values())) == 1,
         f"the three forms resolved to different people: {seen}")
    return "all three forms reach the same person"


@check("transfer gap is arithmetic, quadrants are consistent")
def t_gap():
    status, body = call("GET", "/staff/staff-001/gap")
    need(status == 200, f"HTTP {status}")
    need(body["dimensions"], "no dimension had both streams")
    for d in body["dimensions"]:
        gap = round(d["practice_mean"] - d["floor_mean"], 2)
        need(abs(gap - d["gap"]) < 0.02,
             f"{d['dimension']}: gap {d['gap']} but means differ by {gap}")
        # The quadrant is a function of the two means. If these ever disagree,
        # the number on the manager's screen and the label beside it are
        # telling different stories.
        if d["quadrant"] == "blocked":
            need(d["practice_mean"] > d["floor_mean"],
                 f"{d['dimension']} is blocked but practice <= floor")
        if d["quadrant"] == "recalibrate":
            need(d["floor_mean"] > d["practice_mean"],
                 f"{d['dimension']} is recalibrate but floor <= practice")
    return f"{len(body['dimensions'])} dimensions, all consistent"


@check("BR-01: manager cannot read practice before observing")
def t_sequencing_gate():
    # Fiona is L&D and has observed nobody, so the gate must hold for her.
    status, body = call("GET", "/staff/staff-001/scores?source=practice",
                        actor="Fiona")
    need(status in (409, 200), f"HTTP {status}")
    if status == 409:
        return "409 with an explanation, as designed"
    need(body.get("scores") == [],
         "L&D read practice scores without observing, the gate is open")
    return "returns nothing rather than leaking"


@check("row level security: same query, three viewers, three answers")
def t_rls():
    status, body = call("GET", "/demo/rls?staff_id=Aoife")
    need(status == 200, f"HTTP {status}")
    by = {v["viewer"]: v for v in body["viewers"]}
    need(by["Diego"]["practice_rows"] == 0 and by["Diego"]["floor_rows"] == 0,
         "a colleague could read another staff member's scores")
    need(by["Marta"]["floor_rows"] > 0,
         "the observing manager could not read their own observations")
    need(by["Fiona"]["practice_rows"] == 0,
         "L&D could read individual practice scores")
    return (f"colleague 0, manager {by['Marta']['practice_rows']}/"
            f"{by['Marta']['floor_rows']}, L&D 0 practice")


@check("cite gate rejects every fabricated citation")
def t_gate():
    status, body = call("GET", "/demo/gate")
    need(status == 200, f"HTTP {status}")
    need(body["all_as_expected"],
         "a probe behaved unexpectedly: "
         + ", ".join(p["id"] for p in body["probes"] if not p["as_expected"]))
    rejected = sum(1 for p in body["probes"] if not p["passed"])
    return f"{rejected} of {len(body['probes'])} rejected, 1 honest claim passed"


@check("k-anonymity holds on cohort insights")
def t_k_anon():
    status, body = call("GET", "/insights/team")
    need(status == 200, f"HTTP {status}")
    k = body["k_threshold"]
    for p in body["patterns"]:
        need(p["staff_count"] >= k,
             f"pattern {p['id']} shown with only {p['staff_count']} staff")
    hidden = sum(s["count"] for s in body.get("suppressed", []))
    return f"{len(body['patterns'])} shown at k>={k}, {hidden} suppressed"


@check("agent run: grounded, or an honest abstention")
def t_agent():
    status, body = call("POST", "/staff/staff-001/coach", {})
    need(status == 200, f"HTTP {status}")
    if body["status"] == "abstained":
        need(bool(body.get("abstain_reason")),
             "abstained without saying why, which is useless to a manager")
        return f"abstained: {body['abstain_reason'][:60]}"

    cites = body.get("citations", [])
    need(cites, "a recommendation shipped with no citations at all")
    kinds = {c["kind"] for c in cites}
    need("attempt_turn" in kinds and "observation" in kinds,
         f"cited only {kinds}, a transfer gap needs both streams")
    need(body.get("escalation"), "no routing rule fired")
    return (f"{body['classification']} via "
            f"{body['escalation']['rule_id']}, {len(cites)} citations")


@check("a blocked quadrant is never told to train")
def t_blocked_never_trains():
    status, gap = call("GET", "/staff/staff-001/gap")
    need(status == 200, f"HTTP {status}")
    blocked = [d for d in gap["dimensions"] if d["quadrant"] == "blocked"]
    if not blocked:
        return "no blocked dimension on this person right now"
    status, body = call("POST", "/staff/staff-001/coach", {})
    need(status == 200, f"HTTP {status}")
    if body["status"] == "abstained":
        return "abstained, which is also not a training instruction"
    # The whole product thesis in one assertion: someone who can already do it
    # must never be sent to practise it again.
    need(body["classification"] != "behavioural",
         "a blocked quadrant was classified behavioural, which routes to "
         "training the one person we know has the skill")
    return f"classified {body['classification']}, not behavioural"


@check("verify moves calibration, and cannot be done twice")
def t_verify():
    status, queue = call("GET", "/recommendations?status=pending_verify")
    need(status == 200, f"HTTP {status}")
    if not queue:
        return "nothing pending to verify"
    rec = queue[0]
    payload = {"verdict": "confirmed",
               "dimension_verdicts": [{"dimension": "service_recovery",
                                       "manager_level": 2, "agent_level": 2}],
               "reason": "Matches what I saw.", "seconds_to_decide": 30}
    status, body = call("POST", f"/recommendations/{rec['id']}/verify", payload)
    need(status == 200, f"HTTP {status}: {body}")
    need(body["status"] == "confirmed", f"verdict came back {body['status']}")
    measured = [c for c in body["calibration"] if c["sample_size"]]
    need(measured, "calibration did not move after a verdict")

    # Article 14 again: a decision is made once. A double tap on hotel wifi
    # must not produce two calibration entries.
    status, _ = call("POST", f"/recommendations/{rec['id']}/verify", payload)
    need(status == 409, f"second verify returned {status}, expected 409")
    return f"confirmed, calibration n={measured[0]['sample_size']}, replay 409s"


@check("staff cannot verify, or commission a report")
def t_role_gates():
    status, queue = call("GET", "/recommendations?status=pending_verify")
    if queue:
        status, _ = call("POST", f"/recommendations/{queue[0]['id']}/verify",
                         {"verdict": "confirmed", "dimension_verdicts": [],
                          "reason": "x", "seconds_to_decide": 1}, actor="Diego")
        need(status == 403, f"a staff member verified their own coaching: {status}")
    status, _ = call("POST", "/reports/weekly", {}, actor="Diego")
    need(status == 403, f"a staff member commissioned a report: {status}")
    return "403 on both"


@check("practice: live guest reacts, then scores the whole transcript")
def t_practice():
    status, scenarios = call("GET", "/scenarios", actor="Diego")
    need(status == 200 and scenarios, f"no scenarios: HTTP {status}")

    status, attempt = call("POST", f"/scenarios/{scenarios[0]['id']}/attempts",
                           {}, actor="Diego")
    need(status == 201, f"HTTP {status}")
    need(attempt["turns"], "the attempt opened with no guest line")
    opening = attempt["turns"][0]["guest"]["content"]
    need(len(opening) > 10, "the guest opened with nothing to respond to")

    replies = []
    for line in ("I'm sorry about that. Can you tell me exactly what happened?",
                 "That's on us. Let me fix it now and take it off your bill."):
        status, turn = call("POST", f"/attempts/{attempt['id']}/turns",
                            {"content": line}, actor="Diego")
        need(status == 200, f"turn HTTP {status}")
        replies.append(turn["guest"]["content"])
    need(replies[0] != replies[1],
         "the guest said the same thing twice, so it is not reacting")

    status, scored = call("POST", f"/attempts/{attempt['id']}/complete",
                          {}, actor="Diego")
    need(status == 200, f"complete HTTP {status}")
    need(scored["scores"], "the attempt scored no dimension at all")
    for s in scored["scores"]:
        need(s["level"] is None or 1 <= s["level"] <= 5,
             f"{s['dimension']} scored {s['level']}, outside the 1-5 scale")
    # The staff-facing wording must never be a bare number.
    need(not any(ch.isdigit() for ch in scored["overall_feedback"]),
         f"feedback showed a number to a staff member: "
         f"{scored['overall_feedback']}")
    voiced = attempt["turns"][0]["guest"].get("audio_id")
    return (f"{len(scored['scores'])} dimension(s) scored"
            + (", guest voiced" if voiced else ", text only"))


@check("spoken debrief: transcribed, extracted, audio dropped")
def t_debrief_audio():
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve()
                          .parents[1] / "services" / "api"))
    from app import providers as P                          # noqa: PLC0415

    spoken = ("Table twelve waited nearly forty minutes for their mains. The "
              "guest was annoyed and I offered them a round of drinks, but I "
              "was not sure I was allowed to do that.")
    audio = P.speak(spoken, "guest_male")
    if audio is None:
        return "skipped, no speech provider to generate a fixture"

    boundary = "----ce-e2e"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"debrief.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode(),
        audio, f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(
        BASE + "/debriefs/audio", data=b"".join(parts), method="POST",
        headers={"X-CE-Actor": "Diego",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        reg = json.loads(r.read())
    need(reg.get("id"), "no debrief id came back")

    status, debrief = call("GET", f"/debriefs/{reg['id']}", actor="Diego")
    need(status == 200, f"HTTP {status}")
    need(debrief["status"] == "extracted",
         f"debrief ended {debrief['status']}")
    words = (debrief["transcript"] or "").lower()
    need("forty" in words or "40" in words,
         f"transcript lost the substance: {words[:90]}")
    need(debrief["incident"]["situation_type"],
         "no structured incident was extracted")
    return (f"'{debrief['incident']['situation_type']}', standard "
            + ("cited" if debrief.get("standard") else "not matched"))


@check("trace shows more decisions by code than by model")
def t_trace():
    status, body = call("POST", "/demo/trace/staff-002", {})
    need(status == 200, f"HTTP {status}")
    t = body["trace"]
    need(t["steps"], "the trace recorded no steps")
    # The claim the glass box makes. If this ever inverts, the page is lying
    # and we would rather find out here than in front of a judge.
    need(t["decisions_by_code"] > t["decisions_by_model"],
         f"code {t['decisions_by_code']} vs model {t['decisions_by_model']}, "
         f"the pipeline is now mostly model decisions")
    actors = {s["actor"] for s in t["steps"]}
    need({"code", "database"} <= actors, f"trace only saw {actors}")
    return (f"{t['decisions_by_code']} code / {t['decisions_by_model']} model, "
            f"{t['total_ms']}ms")


@check("synthesised guest audio is served and cacheable")
def t_voice():
    status, budget = call("GET", "/voice/budget")
    need(status == 200, f"HTTP {status}")
    if not budget.get("configured"):
        return "skipped, no speech provider configured"
    status, attempt = call("POST", "/scenarios/"
                           + call("GET", "/scenarios", actor="Diego")[1][0]["id"]
                           + "/attempts", {}, actor="Diego")
    need(status == 201, f"HTTP {status}")
    audio_id = attempt["turns"][0]["guest"].get("audio_id")
    if not audio_id:
        return "no audio on this turn, conversation still works as text"
    status, payload = call("GET", f"/voice/{audio_id}.mp3", raw=True)
    need(status == 200, f"audio HTTP {status}")
    need(len(payload) > 1000, f"audio was only {len(payload)} bytes")
    return f"{len(payload) // 1024}KB mp3, {budget['remaining']} chars left"


DETERMINISTIC = [t_health, t_staff_refs, t_gap, t_sequencing_gate, t_rls,
                 t_gate, t_k_anon, t_role_gates]
AI = [t_agent, t_blocked_never_trains, t_verify, t_practice, t_debrief_audio,
      t_trace, t_voice]


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-ai", action="store_true",
                    help="deterministic paths only, no model calls")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    print(f"\nEnd to end against {BASE}\n")
    print(f"{DIM}deterministic{RESET}")
    for t in DETERMINISTIC:
        t()
    if not args.skip_ai:
        print(f"\n{DIM}with model calls{RESET}")
        for t in AI:
            t()

    failed = [r for r in results if not r[1]]
    print()
    if failed:
        print(f"{RED}{len(failed)} of {len(results)} failed{RESET}")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")
        return 1
    print(f"{GREEN}all {len(results)} passed{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
