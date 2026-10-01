# Data generation

Deterministic synthetic dataset, grounded in patterns extracted from four real
hotel SOP sources.

```bash
python generate_corpus.py              # default seed, identical every time
python generate_corpus.py --seed 42    # a different world, same structure
```

## Why it is seeded

NFR N12: the demo has to be restorable in under five minutes. Hand-crafted demo
data does not survive a redeploy the night before, and "it worked on my machine
yesterday" is not a recovery plan.

## What it produces

Into `output/`: 62 SOP chunks with citation metadata, 15 staff, 65 shift
debriefs, 53 practice attempts, 28 floor observations, computed transfer gaps,
a 45-item golden set, and `seed.sql`.

Verified on every run:

```
Diego  service_recovery: practice 4.2  floor 2.0  gap 2.2  -> BLOCKED
Aoife  service_recovery: practice 4.5  floor 5.0  gap -0.5 -> COMPETENT
cohort on room_not_ready: 9 distinct staff (k-anonymity threshold is 5)
```

## What it is grounded in

`sop_patterns.py` holds frameworks lifted from the real sources: the
A.L.O.U.D. recovery model, the nine-step complaint procedure, the Service
Promise, the timed 11 Steps of Service, Professional Ethic SOP02.

The central finding is encoded deliberately. **F&B has a documented authority
boundary and front office does not.** Source 4 states what a server may offer
without approval; sources 2 and 3 both list the same thing as a gap for front
office, and the bar has no complaint SOP at all. So room-not-ready incidents
carry `grounding_chunk_id: null` on purpose, and the agent should classify that
cohort as a **policy** gap rather than nine behavioural problems.

That is not a contrivance built to make a demo work. It is a real
inconsistency inside one hotel's own manuals.

## The one thing a human still has to do

`golden_set.jsonl` ships with every `ground_truth_scores` field set to null.

**Mary-Susan hand-scores all 45.** If we generated the ground truth we would be
measuring the agent against another model's opinion, which is circular and
worthless. Everything in the calibration story depends on that window.

## Note on the source SOPs

The four extracts are not in this repository and must not be. They are a real
property's internal operations manuals, shared for prototype use only. Only the
structured patterns derived from them live here.
