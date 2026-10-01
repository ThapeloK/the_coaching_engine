# The Coaching Engine

Frontline coaching that closes the gap between training and the floor.

TechIreland National AI Challenge 2026 — demo build.

## What it is

Two apps, one loop:

- **Staff PWA** (`/staff`) — debrief your shift in your own words and get your
  hotel's own standard back; practise 3-minute AI-scored scenarios; see exactly
  what earned each score.
- **Manager Console** (`/manager`) — log 20-second floor observations, read the
  transfer gap between practice and the floor, verify the agent's cited
  recommendations, and watch the calibration number move.

## Demo path

1. `/` — landing, two role entries
2. `/staff` — debrief ("the missing starter") → standard reference → personal scenario
3. `/staff/practice/5e9d-personal` — chat with the guest (mood shifts)
4. `/manager/observe` — log a floor observation for Diego
5. `/manager/gap` — transfer-gap scatter + radar
6. `/manager/verify/r91a-diego` — verify the recommendation → calibration moves

## Architecture notes

- Next.js 16 App Router. The mock API layer (`src/lib/mock`) sits behind the
  same contracts the real AI integration will fill — citations
  (`sop_chunk`, `attempt_turn`, `observation`) are the shape of future RAG
  output.
- Nothing routes on AI output alone: every recommendation waits for a human
  verdict, and every verdict trains the calibration metric.
- Team insights are k-anonymised; individual coaching is suppressed when the
  root cause is process or policy.

## Docs

- [Frontend feature list](docs/FEATURES.md) — every screen, its endpoints,
  mock sources, and open contract items with the backend.

## Related work

[Cornell's AI-powered hospitality training](https://innovationhub.ai.cornell.edu/articles/training-the-next-generation-of-hotel-staff-an-ai-powered-approach-to-hospitality-education/)
(Info 5940, Fall 2025, with the Statler Hotel) built guest/coach/report agents
grounded in hotel SOPs — practice simulation only, no evaluation data.

This demo extends that direction: floor observations, a transfer-gap radar,
mandatory human verification, and a calibration metric that moves with every
verdict.
