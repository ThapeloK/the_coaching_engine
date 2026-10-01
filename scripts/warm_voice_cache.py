"""
warm_voice_cache.py
===================
Synthesise the guest lines a demo will actually hit, and commit them.

    python scripts/warm_voice_cache.py

The ElevenLabs free tier is 10,000 characters for the LIFE of the account, not
per month. A deployed container has an ephemeral filesystem, so without this
every cold start re-synthesises the same opening lines and a week of rehearsals
would spend the budget on dialogue we had already paid for.

Baking them into the image also removes the only slow step in the first guest
turn, which is the one a judge sees.

The cache is keyed by (voice, text), so anything the live model happens to say
that is not in here still synthesises on demand and still works. This is a warm
start, not a script: the guest is not being faked.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

CACHE = ROOT / "services" / "api" / ".voice-cache"
GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

# Openers for the five seeded scenarios, plus the reactions the guest gives
# most often. Written the way the live model writes them: direct, tired, not a
# caricature.
LINES: list[tuple[str, str]] = [
    ("guest_upset",
     "I've been standing here for twenty minutes and my room still isn't "
     "ready. Check-in was supposed to be at three."),
    ("guest_upset",
     "This is the second time this has happened. Is anyone actually going to "
     "sort it out?"),
    ("guest_female",
     "Sorry, before I order, I have a serious nut allergy. Can you check what "
     "the kitchen uses?"),
    ("guest_female",
     "There's a charge on here I don't recognise. Can you tell me what it is?"),
    ("guest_male",
     "We ordered nearly forty minutes ago and the table next to us has "
     "already eaten."),
    ("guest_male",
     "There's been banging from the room above since eleven. I have an early "
     "flight."),
    ("guest_female",
     "Thank you for actually listening. That's all I wanted."),
    ("guest_upset",
     "I don't want a voucher, I want someone to tell me when I can get into "
     "my room."),
]


def main() -> int:
    from dotenv import load_dotenv                            # noqa: PLC0415
    load_dotenv(ROOT / ".env", override=False)
    os.environ["CE_VOICE_CACHE"] = str(CACHE)

    from app import providers as P                            # noqa: PLC0415

    budget = P.voice_budget()
    if not budget.get("configured"):
        print(f"{RED}ELEVENLABS_API_KEY is not set.{RESET} Nothing to warm; "
              f"the product still works in text.")
        return 1
    print(f"Budget before: {budget.get('remaining')} of {budget.get('limit')} "
          f"characters")

    CACHE.mkdir(parents=True, exist_ok=True)
    made = cached = failed = 0
    for voice, text in LINES:
        key = P.voice_key(text, voice)
        if (CACHE / f"{key}.mp3").exists():
            cached += 1
            print(f"  {DIM}cached{RESET}  {text[:58]}")
            continue
        audio = P.speak(text, voice)
        if audio:
            made += 1
            print(f"  {GREEN}made{RESET}    {text[:58]}")
        else:
            failed += 1
            print(f"  {RED}failed{RESET}  {text[:58]}")

    after = P.voice_budget()
    print(f"\n{made} synthesised, {cached} already cached, {failed} failed")
    print(f"Budget after: {after.get('remaining')} characters")
    print(f"\nCommit {CACHE.relative_to(ROOT)} so the deployed image ships "
          f"with them.")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
