"""
run_ragas.py
============
Measure whether retrieval finds the RIGHT clause, and whether the system stays
quiet when it should.

    python evals/retrieval/run_ragas.py            # free, no model calls
    python evals/retrieval/run_ragas.py --ragas    # + faithfulness (costs tokens)

The cite gate proves a quote appears in the chunk we cited. It cannot tell you
we cited the WRONG chunk: a verbatim quote from an irrelevant standard passes
every check and is still useless coaching. That is the gap this closes.

Ground truth is data-generation/output/golden_set.jsonl. Read the warning this
script prints before trusting any number from it: the 45 items were GENERATED
by pairing transcripts with clauses, not curated by a person, and the pairings
do not survive inspection. One example, the first item in the file: a phone
complaint about noise is labelled as grounded in "make eye contact".
Three kinds of item, and the last two are the interesting ones:

    grounded (35)               a specific clause should be found
    must_abstain (5)            NOTHING should clear the floor
    adversarial_near_miss (5)   a topically similar clause exists and is wrong

Abstention accuracy is the headline number. Precision and recall say how good
the search is; abstention accuracy says whether the product keeps the promise
it makes on the slide, and it is the one a judge can check.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")

GOLDEN = ROOT / "data-generation" / "output" / "golden_set.jsonl"

# Same namespace and mapping the seeder uses, so a readable id from the golden
# set resolves to the uuid the row was stored under.
NS = uuid.UUID("6f4d1c2e-0000-4000-8000-000000000001")


def uid(readable: str) -> str:
    return str(uuid.uuid5(NS, readable))


def load_golden() -> list[dict]:
    if not GOLDEN.exists():
        print(f"{RED}No golden set at {GOLDEN.relative_to(ROOT)}{RESET}\n"
              f"Generate it: cd data-generation && python generate_corpus.py")
        raise SystemExit(1)
    return [json.loads(line) for line in
            GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


_STOP = {"the", "a", "an", "and", "to", "i", "it", "was", "were", "is", "of",
         "in", "on", "at", "for", "with", "that", "this", "so", "but", "they",
         "them", "he", "she", "we", "you", "as", "if", "then", "had", "have",
         "her", "his", "their", "said", "about", "just", "not", "no", "my"}


def _overlap(a: str, b: str) -> float:
    """Share of the labelled clause's content words that appear in the query.

    Crude on purpose. It is not trying to measure relevance, only to catch a
    label that has no lexical relationship to the text at all, which is what a
    generated pairing looks like when nobody checked it.
    """
    def words(text: str) -> set[str]:
        return {w.strip(".,;:!?()'\"").lower() for w in text.split()} - _STOP
    qa, qb = words(a), words(b)
    if not qb:
        return 0.0
    return len(qa & qb) / len(qb)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ragas", action="store_true",
                    help="also run ragas faithfulness (needs a judge model)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from dotenv import load_dotenv                            # noqa: PLC0415
    load_dotenv(ROOT / ".env", override=False)

    from app.db import pool, resolve_actor, session           # noqa: PLC0415
    from app.retrieval import search                          # noqa: PLC0415

    items = load_golden()
    if args.limit:
        items = items[: args.limit]

    pool.open(); pool.wait()
    actor = resolve_actor("Fiona")

    # A retrieval score is only as good as the labels it is scored against, so
    # the labels get checked too. If the "correct" clause shares almost no
    # vocabulary with the transcript, a zero here says the label is wrong, not
    # that search is. Reporting 0.00 without this distinction would send
    # someone off to tune a retriever that is working.
    label_overlap: list[float] = []
    hits_at_1 = hits_at_5 = graded = 0
    abstain_right = abstain_total = 0
    false_positive: list[tuple[str, str]] = []
    missed: list[tuple[str, str, list[str]]] = []
    rows: list[dict] = []

    with session(actor) as cur:
        for item in items:
            query = item.get("transcript", "")
            expected = item.get("expected_grounding")
            must_abstain = bool(item.get("must_abstain"))

            found = search(cur, query, limit=5)
            ids = [h["id"] for h in found]
            paths = [h["section_path"] for h in found]

            if must_abstain:
                abstain_total += 1
                if not found:
                    abstain_right += 1
                else:
                    # Retrieval returned something for an item labelled as
                    # having no applicable standard. The similarity floor is
                    # the only thing standing between this and invented advice.
                    false_positive.append((query[:58], paths[0]))
            elif expected:
                graded += 1
                target = uid(expected)
                if ids and ids[0] == target:
                    hits_at_1 += 1
                if target in ids:
                    hits_at_5 += 1
                else:
                    missed.append((query[:58], expected, paths[:2]))

                cur.execute("SELECT content FROM sop_chunk WHERE id = %s",
                            (target,))
                labelled = cur.fetchone()
                if labelled:
                    label_overlap.append(
                        _overlap(query, labelled["content"]))

            rows.append({"id": item.get("id"), "kind": item.get("kind"),
                         "query": query, "retrieved": paths,
                         "top_similarity": found[0]["similarity"] if found else None})
    pool.close()

    print(f"\n{DIM}Retrieval over {len(items)} labelled items{RESET}\n")

    if graded:
        print(f"  precision@1               {hits_at_1 / graded:.2f}"
              f"   {DIM}the right clause was first{RESET}")
        print(f"  recall@5                  {hits_at_5 / graded:.2f}"
              f"   {DIM}the right clause was in the top five{RESET}")
    if label_overlap:
        mean_overlap = sum(label_overlap) / len(label_overlap)
        weak = sum(1 for o in label_overlap if o < 0.15)
        colour = GREEN if mean_overlap >= 0.3 else RED
        print(f"  label/query overlap       {colour}{mean_overlap:.2f}{RESET}"
              f"   {DIM}shared content words with the labelled clause{RESET}")
        if mean_overlap < 0.2:
            print(f"\n  {RED}READ THIS BEFORE TRUSTING THE NUMBERS "
                  f"ABOVE.{RESET}")
            print(f"  {weak} of {len(label_overlap)} labelled clauses share "
                  f"almost no vocabulary with\n  the transcript they are the "
                  f"'correct' answer for. The golden set was\n  generated by "
                  f"pairing, not curated, so precision and recall here are\n  "
                  f"measuring agreement with labels that are themselves wrong.")
            print(f"  {DIM}Fix the labels, or stop citing this as a golden "
                  f"set. Do not tune retrieval against it.{RESET}")

    if abstain_total:
        rate = abstain_right / abstain_total
        colour = GREEN if rate == 1 else (YELLOW if rate >= 0.6 else RED)
        print(f"  abstention accuracy       {colour}{rate:.2f}{RESET}"
              f"   {DIM}stayed quiet on {abstain_right}/{abstain_total} items "
              f"with no applicable standard{RESET}")

    if false_positive:
        print(f"\n  {RED}{len(false_positive)} item(s) retrieved a standard "
              f"where the label says none applies:{RESET}")
        for query, path in false_positive[:5]:
            print(f"    {DIM}{query}{RESET}\n      returned {path}")
        print(f"  {DIM}Each of these is a chance to give confident advice "
              f"about a situation the hotel has not documented.{RESET}")

    if missed:
        print(f"\n  {YELLOW}{len(missed)} item(s) missed the labelled clause "
              f"entirely:{RESET}")
        for query, want, got in missed[:5]:
            print(f"    {DIM}{query}{RESET}\n      wanted {want}, got {got}")

    out = ROOT / "evals" / "retrieval" / "last_run.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n  {DIM}per-item detail written to "
          f"{out.relative_to(ROOT)}{RESET}")

    if not args.ragas:
        print(f"  {DIM}faithfulness skipped; add --ragas to run it{RESET}")
        return 0

    try:
        from ragas import evaluate                            # noqa: PLC0415
        from ragas.metrics import faithfulness                # noqa: PLC0415
        from datasets import Dataset                          # noqa: PLC0415
    except ImportError:
        print(f"\n{YELLOW}ragas is not installed.{RESET}  "
              f"pip install ragas datasets")
        return 0

    usable = [r for r in rows if r["retrieved"]]
    ds = Dataset.from_dict({
        "question": [r["query"] for r in usable],
        "contexts": [r["retrieved"] for r in usable],
        "answer": [" ".join(r["retrieved"][:2]) for r in usable],
    })
    print(f"\n  faithfulness              {evaluate(ds, metrics=[faithfulness])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
