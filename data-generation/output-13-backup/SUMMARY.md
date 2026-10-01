# Generated demo dataset

Seed `20260913`. Regenerate identically with:

    python generate_corpus.py --seed 20260913

| Artefact | Count |
|---|---|
| SOP chunks | 62 |
| Staff | 15 |
| Shift debriefs | 65 |
| Practice attempts | 45 |
| Floor observations | 22 |
| Transfer-gap rows | 65 |
| Golden-set items | 45 |

## Demo narrative checks

- **Diego** (front office), service recovery:
  practice 4.0, floor 2.0,
  gap **2.0**, quadrant **blocked**
- **Aoife** (F&B), service recovery:
  practice 4.5, floor 4.0,
  gap **0.5**, quadrant **competent**
- Cohort on `room_not_ready`: **9 distinct staff**
  (k-anonymity threshold is 5)

## The finding this dataset is built around

Front-office incidents about `room_not_ready` carry
`grounding_chunk_id: null` **on purpose**. The four real SOP sources
document what F&B staff may offer without approval (A.L.O.U.D. authority
rules, source S4) and document nothing equivalent for front office
(confirmed gaps in S2 and S3). The agent should therefore classify the
cohort as a **policy** gap, not nine behavioural problems.

## What still needs a human

`golden_set.jsonl` has `ground_truth_scores` set to null for every
dimension. **Mary-Susan hand-scores those.** Generated scores would make
the evaluation circular and worthless.
