"""Generate the README artwork.

GitHub sanitises <style> and inline style= out of markdown, so a README cannot
be styled directly. CSS *inside* an SVG referenced by <img> survives, so the
artwork carries the design. Each graphic is emitted twice, light and dark, and
the README picks between them with <picture media="prefers-color-scheme">.

Fonts cannot be loaded by an SVG inside an <img>, so everything here uses the
generic families actually present on a reader's machine, and every text box is
sized with slack because nothing in this script can measure a glyph.
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs-assets" / "readme"
OUT.mkdir(parents=True, exist_ok=True)

SANS = ("system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',"
        "Arial,sans-serif")
SERIF = "Georgia,'Times New Roman',serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# Product tokens. The dark column is the same set lifted for luminance: the
# meanings (teal = machine, violet = human, amber = the gap) do not change.
THEMES = {
    "dark": dict(
        bg="#0D1524", panel="#172236", panel2="#1F2C44", rule="#2A3852",
        text="#FFFFFF", mute="#8FA0BC", mute2="#C3CEDF",
        teal="#18A9B8", amber="#F0A339", violet="#9B87D4",
        mint="#3DD6A0", red="#F05A5A", blocked="#3A2A12",
    ),
    "light": dict(
        bg="#FFFFFF", panel="#F4F6F9", panel2="#EAEFF5", rule="#D9DFE8",
        text="#1A2233", mute="#5A6B88", mute2="#4A5568",
        teal="#0E7C86", amber="#B26A00", violet="#5B4B8A",
        mint="#2E6B3E", red="#A32B2B", blocked="#FBEBD2",
    ),
}


def head(w, h, t):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"
     viewBox="0 0 {w} {h}" role="img">
<style>
  .bg   {{ fill: {t['bg']}; }}
  .pan  {{ fill: {t['panel']}; stroke: {t['rule']}; stroke-width: 1; }}
  .pan2 {{ fill: {t['panel2']}; stroke: none; }}
  text  {{ font-family: {SANS}; }}
  .h1   {{ fill: {t['text']}; font-size: 56px; font-weight: 700; }}
  .h2   {{ fill: {t['text']}; font-size: 26px; font-weight: 700; }}
  .h3   {{ fill: {t['text']}; font-size: 16px; font-weight: 700; }}
  .tag  {{ fill: {t['teal']}; font-size: 25px; font-style: italic;
           font-family: {SERIF}; }}
  .body {{ fill: {t['mute2']}; font-size: 16px; }}
  .mute {{ fill: {t['mute']}; font-size: 13px; }}
  .cap  {{ fill: {t['mute']}; font-size: 14px; }}
  .num  {{ font-size: 30px; font-weight: 700; }}
  .lbl  {{ fill: {t['mute']}; font-size: 12px; letter-spacing: 1.1px;
           font-weight: 600; }}
  .mono {{ font-family: {MONO}; font-size: 13px; fill: {t['mute2']}; }}
</style>
<rect class="bg" width="{w}" height="{h}" rx="10"/>
'''


def gapmark(x, y, u, t, label=True):
    """Two bars for one person. The distance between the ends is the product,
    so the mark is the gap rather than anything drawn inside it."""
    s = f'''
<rect x="{x}" y="{y}" width="{230*u}" height="{14*u}" rx="{7*u}" fill="{t['teal']}"/>
<rect x="{x}" y="{y+30*u}" width="{125*u}" height="{14*u}" rx="{7*u}" fill="{t['amber']}"/>
<line x1="{x+125*u}" y1="{y-8*u}" x2="{x+125*u}" y2="{y+54*u}"
      stroke="{t['amber']}" stroke-width="1.5" stroke-dasharray="3 3"/>
<line x1="{x+230*u}" y1="{y-8*u}" x2="{x+230*u}" y2="{y+54*u}"
      stroke="{t['teal']}" stroke-width="1.5" stroke-dasharray="3 3"/>'''
    if label:
        s += f'''
<text x="{x+177*u}" y="{y+72*u}" text-anchor="middle"
      style="font-family:{SERIF};font-style:italic;font-size:{13*u}px"
      fill="{t['amber']}">the gap</text>'''
    return s


# ------------------------------------------------------------------ banner
def banner(t):
    W, H = 1200, 360
    g = head(W, H, t)
    g += gapmark(60, 46, 1.0, t)
    g += f'''
<text x="60" y="182" class="h1">The Coaching Engine</text>
<text x="60" y="222" class="tag">Completion is not behaviour.</text>
<text x="60" y="256" class="body">Every learning platform measures whether training was finished.</text>
<text x="60" y="280" class="body">We measure whether the behaviour turned up on the floor.</text>
<rect x="0" y="304" width="{W}" height="56" class="pan2"/>'''
    mets = [("10\u201320%", "of training reaches the floor", t['red']),
            ("7 : 1", "decisions by code vs by model", t['teal']),
            ("48", "synthetic staff, live right now", t['mint']),
            ("0", "uncited recommendations, ever", t['amber'])]
    for i, (v, l, c) in enumerate(mets):
        x = 60 + i * 280
        g += f'''
<text x="{x}" y="331" class="num" fill="{c}">{v}</text>
<text x="{x}" y="349" class="mute">{l}</text>'''
    return g + "\n</svg>\n"


# -------------------------------------------------------------- transfer gap
def transfer(t):
    W, H = 1200, 540
    g = head(W, H, t)
    g += f'''
<text x="60" y="52" class="h2">The transfer gap</text>
<text x="60" y="80" class="cap">Two independent readings of one person. Where they disagree is the diagnosis.</text>'''

    gx, gy, cw, ch = 250, 112, 280, 150
    quads = [(0, 0, "RECALIBRATE", t['violet'], "Our rubric is wrong,", "not the person"),
             (1, 0, "COMPETENT", t['mint'], "They can do it.", "Stretch them"),
             (0, 1, "SKILL GAP", t['teal'], "Genuine gap. The only", "quadrant training fixes"),
             (1, 1, "BLOCKED", t['amber'], "They already know how.", "Do NOT send training")]
    for cx, cy, name, col, l1, l2 in quads:
        x, y = gx + cx * cw, gy + cy * ch
        b = name == "BLOCKED"
        g += f'''
<rect x="{x}" y="{y}" width="{cw}" height="{ch}"
      fill="{t['blocked'] if b else t['panel']}"
      stroke="{col if b else t['rule']}" stroke-width="{2.5 if b else 1}"/>
<text x="{x+cw/2}" y="{y+60}" text-anchor="middle" class="h3" fill="{col}">{name}</text>
<text x="{x+cw/2}" y="{y+88}" text-anchor="middle" class="mute">{l1}</text>
<text x="{x+cw/2}" y="{y+108}" text-anchor="middle" class="mute">{l2}</text>'''
    g += f'''
<text x="{gx+cw}" y="{gy+2*ch+32}" text-anchor="middle" class="lbl">PRACTICE SCORE &#8594;</text>
<text x="0" y="0" class="lbl" transform="translate({gx-26},{gy+ch}) rotate(-90)"
      text-anchor="middle">FLOOR OBSERVATION &#8594;</text>'''

    # The two streams, in the space the grid was otherwise wasting. They also
    # explain the axes, which the grid alone leaves the reader to infer.
    streams = [(t['teal'], "STREAM 1 \u00b7 PRACTICE",
                "A guest scenario, scored against",
                "the hotel's own rubric."),
               (t['amber'], "STREAM 2 \u00b7 THE FLOOR",
                "What the manager actually saw,",
                "logged before they see stream 1."),
               (t['violet'], "THE GAP",
                "Two readings, one person, one",
                "dimension. The disagreement.")]
    for i, (col, name, l1, l2) in enumerate(streams):
        y = 118 + i * 104
        g += f'''
<rect x="880" y="{y}" width="272" height="88" rx="8" class="pan"/>
<rect x="898" y="{y+20}" width="5" height="48" rx="2.5" fill="{col}"/>
<text x="916" y="{y+34}" class="lbl" fill="{col}">{name}</text>
<text x="916" y="{y+56}" class="mute">{l1}</text>
<text x="916" y="{y+74}" class="mute">{l2}</text>'''

    g += '''
<text x="60" y="490" class="cap">Nobody else can see the amber box. Every other platform watches the simulator</text>
<text x="60" y="510" class="cap">only, so the teal answer is the only answer it is able to give.</text>'''
    return g + "\n</svg>\n"


# -------------------------------------------------------------- who decides
def decides(t):
    W, H = 1200, 430
    g = head(W, H, t)
    g += '''
<text x="60" y="52" class="h2">Who actually decides</text>
<text x="60" y="80" class="cap">A typical run, as recorded in the trace. Not a claim: /glassbox replays it live.</text>'''
    for i in range(8):
        x = 60 + i * 96
        model = i == 6
        col = t['violet'] if model else t['teal']
        sub = "1 call" if model else f"step {i + 1 if i < 6 else i}"
        g += f'''
<rect x="{x}" y="118" width="80" height="58" rx="8" fill="{col}"/>
<text x="{x+40}" y="145" text-anchor="middle"
      style="font-size:12px;font-weight:700" fill="{t['bg']}">{"MODEL" if model else "CODE"}</text>
<text x="{x+40}" y="163" text-anchor="middle"
      style="font-size:11px" fill="{t['bg']}">{sub}</text>'''
    g += f'''
<text x="60" y="206" class="mute">Seven decisions by code, one by the model, and that one picks from a list the code had already narrowed.</text>
<line x1="60" y1="228" x2="1140" y2="228" stroke="{t['rule']}" stroke-width="1"/>
<text x="60" y="264" class="h3" style="font-size:18px">Then four checks, before a single word reaches a human</text>'''

    checks = [("Source exists", "the cited id is in the bundle"),
              ("Span is real", "the sentence is in that document"),
              ("Both streams", "one practice and one floor cite"),
              ("No crossover", "no evidence from another person")]
    for i, (a, b) in enumerate(checks):
        x = 60 + i * 282
        g += f'''
<rect x="{x}" y="284" width="262" height="82" rx="8" class="pan"/>
<circle cx="{x+26}" cy="312" r="11" fill="{t['mint']}"/>
<text x="{x+26}" y="317" text-anchor="middle"
      style="font-size:13px;font-weight:700" fill="{t['bg']}">&#10003;</text>
<text x="{x+48}" y="317" class="h3" style="font-size:14px">{a}</text>
<text x="{x+18}" y="344" class="mute">{b}</text>'''
    g += '''
<text x="60" y="400" class="cap">Fail any one and it does not guess. It abstains and names the evidence it could not find.</text>'''
    return g + "\n</svg>\n"


for name, fn in (("banner", banner), ("transfer-gap", transfer),
                 ("who-decides", decides)):
    for theme, tok in THEMES.items():
        path = OUT / f"{name}-{theme}.svg"
        path.write_text(fn(tok), encoding="utf-8")
        print("wrote", path.name, path.stat().st_size, "bytes")
