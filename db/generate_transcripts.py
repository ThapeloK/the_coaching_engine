"""
generate_transcripts.py
=======================
Give the seeded practice attempts real transcripts, then score them with the
real scoring engine.

Why this exists: the data generator produced per-dimension scores but no
dialogue, so score.evidence_span was null everywhere. That is fine for
computing a transfer gap and fatal for a citation, because "here is what he
actually said in practice" is half the demo. The agent correctly abstained
rather than cite an empty span, which is the gate doing its job and also a
clear signal that the seed was incomplete.

So: generate a plausible transcript per attempt, score it against the
property's own BARS anchors, and write both the turns and the quoted evidence
back. After this the citation chain is real end to end.

    python db/generate_transcripts.py --limit 12       # demo staff first
    python db/generate_transcripts.py --all
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "services" / "api"))

# Override, not setdefault: .env has already set DATABASE_URL to the ce_app
# connection, and a maintenance script running as ce_app with no RLS context
# sees zero rows and silently does nothing. That is RLS behaving correctly and
# it cost a confusing "0 attempts transcribed" to notice.
os.environ["DATABASE_URL"] = os.environ.get(
    "SEED_DATABASE_URL",
    "postgresql://coaching:coaching@localhost:5433/coaching_engine")

from app.agent import score_transcript          # noqa: E402
from app.db import pool, session                # noqa: E402
from app.providers import Trace, complete       # noqa: E402

TRANSCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["turns"],
    "properties": {
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["speaker", "content"],
                "properties": {
                    "speaker": {"type": "string", "enum": ["guest", "staff"]},
                    "content": {"type": "string"},
                },
            },
        }
    },
}

SYSTEM = """You write short, realistic hospitality practice transcripts.

A guest with a legitimate grievance, and a staff member handling it. Six to
eight turns, starting with the guest.

RULES
- Write how people actually speak on a shift: contractions, short sentences,
  the occasional false start. Not customer-service brochure prose.
- The guest is a person with a problem, never a caricature.
- Reflect the TARGET PERFORMANCE exactly. If it says the staff member offers
  compensation before acknowledging the problem, write that, and do not have
  them recover well later.
- Never use real names, room numbers or booking references."""


def target_description(scores: dict[str, int]) -> str:
    """Turn the stored scores into an instruction, so the generated dialogue
    matches the levels already in the database rather than drifting from them."""
    lines = []
    for dim, level in scores.items():
        if level is None:
            continue
        if level >= 4:
            lines.append(f"- {dim}: handles this well, close to the standard")
        elif level == 3:
            lines.append(f"- {dim}: adequate but generic, sequence partly out of order")
        else:
            lines.append(f"- {dim}: clearly falls short. For service_recovery that "
                         f"means offering compensation before acknowledging the "
                         f"problem, or escalating without attempting recovery")
    return "\n".join(lines) or "- competent throughout"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    pool.open()
    trace = Trace()
    done = 0

    with session() as cur:
        # Demo staff first: if the budget or the clock runs out, the demo path
        # is the part that is finished.
        cur.execute("""
            SELECT sa.id::text AS attempt_id, sa.staff_id::text,
                   sm.display_name, sm.department, sc.title, sc.situation,
                   sc.target_dimensions
            FROM scenario_attempt sa
            JOIN staff_member sm ON sm.id = sa.staff_id
            JOIN scenario sc ON sc.id = sa.scenario_id
            WHERE NOT EXISTS (SELECT 1 FROM attempt_turn t
                               WHERE t.attempt_id = sa.id)
            ORDER BY (sm.display_name IN ('Diego','Aoife')) DESC, sa.completed_at DESC
        """)
        attempts = cur.fetchall()
        if not args.all:
            attempts = attempts[:args.limit]

        print(f"{len(attempts)} attempts to transcribe\n")

        for a in attempts:
            cur.execute("""
                SELECT bd.code, s.level, s.id::text AS score_id
                FROM score s JOIN bars_dimension bd ON bd.id = s.dimension_id
                WHERE s.attempt_id = %s AND s.source = 'practice'
            """, (a["attempt_id"],))
            rows = cur.fetchall()
            if not rows:
                continue
            stored = {r["code"]: r["level"] for r in rows}

            try:
                result = complete(
                    "guest_turn", SYSTEM,
                    f"SCENARIO: {a['title']}\nSITUATION: {a['situation']}\n"
                    f"DEPARTMENT: {a['department']}\n\n"
                    f"TARGET PERFORMANCE\n{target_description(stored)}",
                    schema=TRANSCRIPT_SCHEMA, temperature=0.8, trace=trace)
            except Exception as e:
                print(f"  skip {a['display_name']:<8} {type(e).__name__}")
                continue

            turns = result["turns"][:10]
            for i, t in enumerate(turns):
                cur.execute("""
                    INSERT INTO attempt_turn (property_id, attempt_id, turn_index,
                                              speaker, content)
                    SELECT property_id, id, %s, %s, %s FROM scenario_attempt
                    WHERE id = %s
                """, (i, t["speaker"], t["content"], a["attempt_id"]))
            cur.execute("UPDATE scenario_attempt SET turn_count = %s WHERE id = %s",
                        (len(turns), a["attempt_id"]))

            # Score the transcript we just wrote, with the real scorer, and use
            # its quoted spans as the citable evidence.
            scored = score_transcript(cur, turns, list(stored.keys()), trace=trace)
            spans = {s["dimension"]: s["evidence_span"] for s in scored}
            updated = 0
            for r in rows:
                span = spans.get(r["code"])
                if span:
                    cur.execute("UPDATE score SET evidence_span = %s WHERE id = %s",
                                (span[:400], r["score_id"]))
                    updated += 1

            cur.connection.commit()
            done += 1
            print(f"  {a['display_name']:<8} {a['title'][:34]:<34} "
                  f"{len(turns)} turns, {updated} spans")

    print(f"\n{done} attempts transcribed. "
          f"{trace.total_ms} ms, {trace.total_tokens} tokens.")


if __name__ == "__main__":
    main()
