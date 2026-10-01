"""Record the backup demo video, by driving the live site for real.

    python scripts/record_demo.py                      # record
    python scripts/record_demo.py --keep-observation   # do not clean up after

WHY THIS EXISTS

If the venue wifi dies on Monday, the demo dies with it. This is the insurance:
a silent screen capture of the actual product doing the actual thing, which
somebody narrates over live from the run sheet. Silent is deliberate, not a
limitation to apologise for. The words should be his, said in the room, at the
pace the room is going; a video with a recorded voiceover is harder to talk
over and sounds like an advert.

WHAT IT CAPTURES

The real deployed site at naic-2026-coaching-engine.vercel.app, talking to the
real API on Cloud Run, against the real database. Nothing is mocked and nothing
is sped up. The typing is done at human speed on purpose: text that appears
instantly reads as a mockup, and the whole argument of this product is that it
is not one.

Playwright records the browser context natively, so what lands in the file is
the page's own animation, including the timeline in the glass box and the
staggered cards, rather than a slideshow of stills.

WHAT IT DOES TO THE DATABASE

Act two logs a real observation on Diego, because that is what the demo does.
It is deleted again at the end unless --keep-observation is passed. Logging a
low service-recovery score on Diego actually reinforces the story, since it
holds his floor mean down, but it is removed anyway so the recording can be run
repeatedly without drifting the numbers the pitch quotes.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

SITE = "https://naic-2026-coaching-engine.vercel.app"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "demo-video"

# Typed at roughly 55ms a character, which is a fast but human typing speed.
# Instant text reads as a mockup.
TYPE_DELAY = 55

SPANISH = ("El senor estaba muy molesto porque la guagua no llego y su pieza no "
           "estaba lista. Le dije que esperara, parce, pero la vaina se puso fea "
           "y tuve que llamar al manager.")
OBSERVATION = ("Diego handled that checkout dispute at the front desk. He stayed "
               "completely calm even though the guest was shouting at him, but he "
               "never actually offered her anything to fix it.")


def beat(page, seconds: float, note: str = "") -> None:
    """Hold the frame. The holds are what make it narratable: each one is a
    place the narration expects somebody to still be talking."""
    if note:
        print(f"    {note}")
    page.wait_for_timeout(int(seconds * 1000))


def record() -> pathlib.Path:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(OUT),
            record_video_size={"width": 1280, "height": 800},
            # A real device pixel ratio, so text is crisp when projected.
            device_scale_factor=1,
        )
        page = context.new_page()

        # ---------------------------------------------------- ACT ONE, DIEGO
        #
        # One viewport for the whole recording, deliberately. Shrinking it for
        # the phone-shaped staff app seemed like it would fill the frame
        # better, and it does the opposite: Playwright's recording canvas is
        # fixed at record_video_size, so a smaller page leaves half the frame
        # flat grey. The staff app floating in its own cream margins reads as
        # intentional, which it is, because it is a phone app.
        print("  ACT ONE: Diego")
        page.goto(f"{SITE}/staff", wait_until="networkidle", timeout=60_000)
        beat(page, 3, "landing on the staff app")

        box = page.get_by_placeholder("A guest asked for something")
        box.click()
        box.type(SPANISH, delay=TYPE_DELAY)
        beat(page, 1.2, "Spanish typed")

        page.get_by_role("button", name="Get instant feedback").click()
        page.wait_for_selector("text=You said it in your own words", timeout=90_000)
        beat(page, 4, "translation and regional words on screen")

        page.mouse.wheel(0, 260)
        beat(page, 4.5, "the hotel's own clause")

        # ---------------------------------------------------- ACT TWO, MARTA
        print("  ACT TWO: Marta")
        page.goto(f"{SITE}/manager/observe", wait_until="networkidle", timeout=60_000)
        beat(page, 2.5, "manager console")

        page.get_by_role("button", name="Type it instead").click()
        beat(page, 0.8)
        note = page.get_by_placeholder("Diego handled the checkout dispute")
        note.click()
        note.type(OBSERVATION, delay=TYPE_DELAY)
        beat(page, 1, "observation typed")

        page.get_by_role("button", name="Read it back").click()
        page.wait_for_selector("text=to confirm", timeout=90_000)
        beat(page, 5, "draft with the evidence underlined")

        page.get_by_role("button", name="Log this").click()
        print("    logging, this runs the full agent")
        page.wait_for_selector("text=Logged for", timeout=120_000)
        beat(page, 3, "logged, recommendation created")

        # ------------------------------------------------------- THE PAYOFF
        print("  THE PAYOFF: the transfer gap")
        page.goto(f"{SITE}/manager/gap", wait_until="networkidle", timeout=60_000)
        page.wait_for_selector("text=Scored dimensions", timeout=60_000)
        beat(page, 6, "practice 4.8 against floor 1.6, BLOCKED")

        page.mouse.wheel(0, 300)
        beat(page, 5, "holding on the quadrant")

        context.close()
        browser.close()

    videos = sorted(OUT.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    return videos[-1]


def to_mp4(webm: pathlib.Path) -> pathlib.Path | None:
    """H.264 in an mp4, because that is what plays on a borrowed laptop and a
    conference projector without anybody installing anything."""
    mp4 = OUT / "coaching-engine-demo.mp4"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm),
         "-c:v", "libx264", "-preset", "slow", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(mp4)],
        capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-600:])
        return None
    return mp4


def cleanup_observation() -> None:
    """Remove the observation act two logged, so the numbers the pitch quotes
    do not drift every time this is re-recorded."""
    import psycopg

    def env(path):
        out = {}
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
        return out

    e = env(".env.neon")
    dsn = e.get("SEED_DATABASE_URL",
                e["DATABASE_URL"].replace("ce_app:ce_app", "coaching:coaching"))
    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        # observation is stamped with observed_at and logged_at; there is no
        # created_at on it, which is what broke this the first time.
        cur.execute("""SELECT id::text, staff_id::text FROM observation
                       WHERE what_happened =
                             'handled that checkout dispute at the front desk'
                         AND logged_at > now() - interval '2 hours'""")
        rows = cur.fetchall()
        for oid, staff_id in rows:
            cur.execute("""SELECT id::text FROM recommendation
                           WHERE staff_id = %s
                           ORDER BY created_at DESC LIMIT 1""", (staff_id,))
            rec = cur.fetchone()
            if rec:
                cur.execute("DELETE FROM escalation WHERE recommendation_id=%s",
                            (rec[0],))
                cur.execute("DELETE FROM recommendation WHERE id=%s", (rec[0],))
            cur.execute("DELETE FROM score WHERE observation_id=%s", (oid,))
            cur.execute("DELETE FROM observation_rating WHERE observation_id=%s",
                        (oid,))
            cur.execute("DELETE FROM observation WHERE id=%s", (oid,))
        conn.commit()
        print(f"  removed {len(rows)} observation(s) created by this recording")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-observation", action="store_true",
                    help="leave the logged observation in place")
    args = ap.parse_args()

    print(f"Recording against {SITE}\n")
    started = time.time()
    webm = record()
    print(f"\n  raw capture: {webm.name} ({webm.stat().st_size // 1024} KB)")

    mp4 = to_mp4(webm)
    if mp4:
        print(f"  mp4: {mp4} ({mp4.stat().st_size // 1024} KB)")

    if not args.keep_observation:
        try:
            cleanup_observation()
        except Exception as exc:            # noqa: BLE001
            print(f"  cleanup failed, remove it by hand: {exc}")

    print(f"\nDone in {time.time() - started:.0f}s. "
          f"Narrate over it from the run sheet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
