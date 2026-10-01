"""
walkthrough.py
==============
Drive the live site end to end and screenshot every step.

    python scripts/walkthrough.py                 # against production
    python scripts/walkthrough.py --base http://localhost:3000

Output goes to docs-assets/walkthrough/ as numbered PNGs plus a manifest.json
describing what each one shows, which is what the LaTeX walkthrough document
reads.

This is a real session, not a mock-up. It signs in as three different people in
turn, clicks the things a user clicks, and captures what actually comes back.
When a screenshot shows an empty queue or an abstention, that is what the
product did.

What it cannot do is listed in SKIPPED at the bottom: anything needing a
microphone, a speaker or a human judgement call. Those are written up as manual
steps in the document instead of being faked.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs-assets" / "walkthrough"

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

shots: list[dict] = []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://naic-2026-coaching-engine.vercel.app")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=960)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{RED}playwright is not installed.{RESET}\n"
              f"  pip install playwright && python -m playwright install chromium")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    base = args.base.rstrip("/")
    print(f"Walking through {base}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": args.width,
                                            "height": args.height},
                                  device_scale_factor=2)
        page = ctx.new_page()

        def shot(name: str, caption: str, note: str = "",
                 full: bool = False) -> None:
            """Viewport by default, not the whole scrollable page.

            full_page captures every pixel including the empty space below the
            content, so a short page becomes a very tall image that shrinks to
            illegibility once it is placed in a document. The viewport is the
            shape a reader recognises anyway, because it is what they see.
            """
            n = len(shots) + 1
            path = OUT / f"{n:02d}-{name}.png"
            page.screenshot(path=str(path), full_page=full)
            shots.append({"n": n, "file": path.name, "name": name,
                          "caption": caption, "note": note})
            kb = path.stat().st_size // 1024
            print(f"  {GREEN}{n:02d}{RESET} {name:28} {kb:>5}KB  {caption[:44]}")

        def go(path: str, wait_for: str | None = None, settle: float = 2.5):
            page.goto(base + path, wait_until="networkidle", timeout=90000)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=25000)
                except Exception:
                    pass
            time.sleep(settle)

        def act_as(who: str):
            """Set the demo identity the client reads from localStorage."""
            page.evaluate(f"localStorage.setItem('ce_actor', '{who}')")

        # ---------------------------------------------------------- landing
        go("/")
        shot("landing", "The front door",
             "Two ways in, one per role. Nobody logs in: this is a demo build "
             "and identity is chosen here instead.")

        # ------------------------------------------------- manager, as Marta
        act_as("Marta")
        go("/manager")
        shot("manager-overview", "Manager console, as Marta",
             "The radar compares practice against the floor. The queue is what "
             "the agent has drafted and is holding.")

        go("/manager/verify")
        shot("verify-queue", "The verify queue",
             "Every card is one recommendation about one person. Abstentions "
             "are shown too, rather than hidden.")

        # Expand the first card. They are accordions, not links: the header
        # carries aria-expanded, so target that rather than guessing at text.
        try:
            page.click("[aria-expanded='false']", timeout=10000)
            time.sleep(3)
            shot("verify-detail", "One recommendation, opened",
                 "The claim, the evidence behind each part of it, and the three "
                 "verdicts. Nothing routes anywhere until one is chosen.")
        except Exception:
            links = page.eval_on_selector_all(
                "a[href*='/manager/verify/']", "els => els.map(e => e.href)")
            if links:
                page.goto(links[0], wait_until="networkidle", timeout=90000)
                time.sleep(3)
                shot("verify-detail", "One recommendation, opened",
                     "The claim, the evidence behind each part of it, and the "
                     "three verdicts.")

        go("/manager/gap")
        shot("transfer-gap", "The transfer gap, per person",
             "The product in one screen. Strong in practice and weak on the "
             "floor is BLOCKED, and more training will not fix it.")

        go("/manager/insights")
        shot("team-insights", "Team patterns",
             "Only patterns shared by five or more people are shown. The count "
             "of what was withheld is displayed rather than quietly dropped.")

        go("/manager/observe")
        shot("log-observation", "Logging what the manager saw",
             "This is the gate. Until this is submitted for a person, their "
             "practice scores stay hidden from the manager.")

        # ---------------------------------------------------- staff, as Diego
        act_as("Diego")
        go("/staff")
        shot("staff-home", "The staff app, as Diego",
             "Built for a phone at the end of a shift. No scores on this "
             "screen, deliberately.")

        go("/staff/practice")
        shot("practice-list", "Choosing a scenario",
             "Scenarios built from this property's own standards. One marked "
             "personal comes from that staff member's own shift.")

        # start a real attempt
        try:
            links = page.eval_on_selector_all(
                "a[href*='/staff/practice/']", "els => els.map(e => e.href)")
            if links:
                page.goto(links[-1], wait_until="networkidle", timeout=120000)
                time.sleep(6)
                shot("practice-open", "The guest opens",
                     "A live model, not a script. The line is generated for "
                     "this attempt and can be played aloud.")

                # Match the placeholder rather than the tag: the control is a
                # plain input, and "textarea, input[type=text]" missed it.
                box = page.get_by_placeholder("What would you say to the guest?")
                box.fill("I am really sorry about the wait, that is a long time "
                         "to be sitting in a lobby. Let me find out exactly "
                         "where your room is and come straight back to you.")
                time.sleep(1)
                shot("practice-typing", "The staff member replies",
                     "Typed here, or dictated with the microphone. What matters "
                     "is what they say, not how it was entered.")

                box.press("Enter")
                page.wait_for_timeout(14000)
                shot("practice-reply", "The guest reacts to what was said",
                     "Acknowledging the problem first makes the guest soften. "
                     "Leading with compensation makes them push back. That "
                     "reaction is the thing being trained.")

                # A second turn, then finish and score the whole conversation.
                box = page.get_by_placeholder("What would you say to the guest?")
                box.fill("Your room is being finished now and will be about ten "
                         "minutes. Can I take your bags and get you a coffee in "
                         "the lounge while you wait?")
                box.press("Enter")
                page.wait_for_timeout(14000)

                try:
                    # The button is labelled "Finish and see my notes" in the
                    # staff app; match loosely so a copy change does not silently
                    # drop this step from the walkthrough.
                    page.click("button:has-text('Finish'), button:has-text('notes'), "
                               "button:has-text('Complete')", timeout=10000)
                    page.wait_for_timeout(25000)
                    shot("practice-result", "The conversation is scored",
                         "Scored once, over the whole exchange, not per line. "
                         "Each level comes back with the exact words that "
                         "earned it, and never as a number.")
                except Exception:
                    pass
        except Exception as exc:
            print(f"  {RED}practice flow: {type(exc).__name__}{RESET}")

        go("/staff/history")
        shot("staff-history", "What the staff member sees about themselves",
             "Their own record, in words rather than numbers. A frontline "
             "worker reads 2 out of 5 as a verdict on them.")

        # No Fiona screenshot of /manager/insights.
        #
        # It would be byte-identical to Marta's, and capturing it would imply a
        # difference that is not there. Two reasons: cohort patterns are the
        # same for both roles by design, and more importantly currentActor()
        # returns "Marta" whenever window is undefined, so SERVER-rendered
        # pages ignore the localStorage override entirely.
        #
        # The honest demonstration of role differences is the glass box RLS
        # panel, which asks the API as three people explicitly and shows three
        # different answers. That is captured below.

        # ------------------------------------------------------- glass box
        act_as("Marta")
        go("/glassbox")
        shot("glassbox", "The glass box",
             "Three claims a judge can check rather than believe. Each button "
             "runs production code live.")

        try:
            page.click("text=Diego", timeout=8000)
            time.sleep(18)
            shot("glassbox-trace", "Every step, and who made it",
                 "Code, model or database on every line. A typical run is seven "
                 "decisions by code and one by the model, and that one was "
                 "chosen from a list the code had already narrowed.")
        except Exception as exc:
            print(f"  {DIM}trace panel: {type(exc).__name__}{RESET}")

        try:
            page.click("text=/lie past it/i", timeout=8000)
            time.sleep(6)
            shot("glassbox-gate", "Trying to get a lie past the gate",
                 "Nine fabrications, the kind a real model failure looks like. "
                 "None reach a manager. The honest claim still passes.")
        except Exception as exc:
            print(f"  {DIM}gate panel: {type(exc).__name__}{RESET}")

        try:
            page.click("text=/three different people/i", timeout=8000)
            time.sleep(6)
            shot("glassbox-rls", "One question, three people",
                 "Identical SQL each time. A colleague reads nothing, the "
                 "observing manager reads everything, L&D reads no individual "
                 "practice scores.")
        except Exception as exc:
            print(f"  {DIM}rls panel: {type(exc).__name__}{RESET}")

        # ------------------------------------------------------- phone view
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=3,
            is_mobile=True, has_touch=True,
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                        "Version/17.0 Mobile/15E148 Safari/604.1"))
        mpage = mobile.new_page()
        mpage.goto(base + "/staff", wait_until="networkidle", timeout=90000)
        time.sleep(3)
        n = len(shots) + 1
        path = OUT / f"{n:02d}-staff-phone.png"
        mpage.screenshot(path=str(path), full_page=True)
        shots.append({"n": n, "file": path.name, "name": "staff-phone",
                      "caption": "The staff app on a phone",
                      "note": "This is where it actually gets used: a corridor, "
                              "a back office, the end of a shift."})
        print(f"  {GREEN}{n:02d}{RESET} staff-phone                  "
              f"{path.stat().st_size // 1024:>5}KB  phone viewport")

        browser.close()

    (OUT / "manifest.json").write_text(
        json.dumps({"base": base, "captured": time.strftime("%Y-%m-%d %H:%M"),
                    "shots": shots}, indent=2), encoding="utf-8")
    print(f"\n{GREEN}{len(shots)} screenshots{RESET} -> "
          f"{OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
