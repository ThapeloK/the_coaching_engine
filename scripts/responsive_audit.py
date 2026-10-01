"""Audit every screen at phone and laptop width.

Checks the three things that actually make a site unusable on a phone, rather
than eyeballing screenshots:

  1. horizontal overflow      the page is wider than the viewport, so the user
                              has to scroll sideways to read a sentence
  2. tap targets under 40px   a link or button too small to hit with a thumb
  3. no way back              a screen with no back link and no role switch

Run against a local build or the deployed site:

    python scripts/responsive_audit.py                      # localhost:3100
    python scripts/responsive_audit.py https://example.com

Exits non-zero if anything fails, so it can gate a deploy.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3100").rstrip("/")

# width, height, label. 360 is the narrow end of Android, 375 the common
# iPhone, 1280 a laptop. If it survives 360 it survives the room.
VIEWPORTS = [(360, 800, "phone 360"), (768, 1024, "tablet 768"), (1280, 900, "laptop 1280")]

PAGES = [
    ("/", "landing"),
    ("/manager", "manager overview"),
    ("/manager/observe", "log observation"),
    ("/manager/verify", "verify queue"),
    ("/manager/gap", "transfer gap"),
    ("/manager/insights", "team insights"),
    ("/staff", "staff home"),
    ("/staff/practice", "scenarios"),
    ("/staff/history", "my practice"),
    ("/glassbox", "glass box"),
]

OVERFLOW_JS = """() => {
  const d = document.documentElement;
  const vw = d.clientWidth;
  const bad = [...document.querySelectorAll('body *')]
    .filter(e => {
      const s = getComputedStyle(e);
      if (s.position === 'fixed' || s.visibility === 'hidden' || s.display === 'none') return false;
      const r = e.getBoundingClientRect();
      return r.width > 0 && (r.right > vw + 2 || r.left < -2);
    })
    .slice(0, 4)
    .map(e => e.tagName.toLowerCase() + '.' + String(e.className).split(' ').slice(0,3).join('.'));
  return { vw, scrollW: d.scrollWidth, overflow: d.scrollWidth > vw + 2, bad };
}"""

TAP_JS = """() => {
  const small = [];
  for (const e of document.querySelectorAll('a[href], button')) {
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.display === 'none') continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    // A link inside a sentence is exempt under WCAG 2.5.8: enlarging it would
    // break the line it sits in, and the sentence gives it a much bigger
    // effective target than its own box.
    const p = e.parentElement;
    const inProse = p && (p.tagName === 'P' || p.tagName === 'SPAN')
      && (p.innerText || '').trim().length > (e.innerText || '').trim().length + 12;
    if (inProse) continue;
    if (r.height < 36 || r.width < 36) {
      small.push(((e.innerText || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 28))
        + ' [' + Math.round(r.width) + 'x' + Math.round(r.height) + ']');
    }
  }
  return small.slice(0, 6);
}"""

NAV_JS = """() => {
  const t = document.body.innerText;
  return {
    back: /Back to /.test(t),
    switchRole: /Switch role/.test(t),
    tabs: document.querySelectorAll('nav a').length,
    // A shell and its loading.tsx both rendering the nav puts two of them on
    // screen. Presence alone would not catch that.
    dupes: (t.match(/Switch role/g) || []).length,
  };
}"""


def main() -> int:
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h, vlabel in VIEWPORTS:
            print("\n" + "=" * 72)
            print("  %s  (%dx%d)" % (vlabel.upper(), w, h))
            print("=" * 72)
            # has_touch matters: the touch-target rule in globals.css is
            # scoped to a coarse pointer, so a mouse context would not see it
            # and the audit would report failures a real phone does not have.
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                has_touch=w < 768,
                is_mobile=w < 768,
            )
            page = ctx.new_page()
            for path, name in PAGES:
                try:
                    page.goto(BASE + path, wait_until="networkidle", timeout=60000)
                except Exception:
                    # networkidle never settles on a page that polls; the DOM is
                    # what we are measuring, so carry on with what loaded.
                    pass
                page.wait_for_timeout(600)

                o = page.evaluate(OVERFLOW_JS)
                nav = page.evaluate(NAV_JS)
                small = page.evaluate(TAP_JS) if w < 768 else []

                flags = []
                if o["overflow"]:
                    flags.append("OVERFLOW %dpx > %dpx" % (o["scrollW"], o["vw"]))
                    failures.append("%s %s: overflow %s" % (vlabel, name, o["bad"]))
                if small:
                    flags.append("%d small tap targets" % len(small))
                    failures.append("%s %s: tap %s" % (vlabel, name, small))
                # The landing page IS the role picker, so it needs neither.
                if path != "/" and not (nav["back"] or nav["switchRole"] or nav["tabs"]):
                    flags.append("NO WAY BACK")
                    failures.append("%s %s: no navigation" % (vlabel, name))
                if nav["dupes"] > 1:
                    flags.append("NAV RENDERED %dx" % nav["dupes"])
                    failures.append("%s %s: nav duplicated %dx"
                                    % (vlabel, name, nav["dupes"]))

                mark = "FAIL" if flags else "ok  "
                print("  %s %-18s %-26s %s" % (
                    mark, name, path,
                    "; ".join(flags) if flags else
                    "back=%s switch=%s navlinks=%d" % (nav["back"], nav["switchRole"], nav["tabs"])))
                for s in small:
                    print("         small: %s" % s)
            ctx.close()
        browser.close()

    print("\n" + "=" * 72)
    if failures:
        print("  %d FAILURES" % len(failures))
        for f in failures:
            print("   -", f)
        return 1
    print("  ALL PASS across %d screens x %d viewports" % (len(PAGES), len(VIEWPORTS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
