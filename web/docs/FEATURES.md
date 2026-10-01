# Frontend Feature List

The Coaching Engine — frontend feature inventory for team integration
discussions. Covers every user-facing screen, the API endpoints it calls,
its mock data source, and open contract items.

> Last updated: 2026-09-09 · synced with commit `cbbf718` (debrief voice
> input — shared hook). Keep this file in step with the code — update it
> whenever a feature, endpoint, or contract detail changes.

## A. Landing page (demo-only, no backend)

- Hero, "Who this is for", bento grid (two streams, citations,
  human-in-the-loop, calibration preview), Cornell link, CTA buttons into
  both role views.
- The three citation chips use real seeded anchors: an SOP chunk, Diego's
  practice turn, Marta's observation.

## B. Manager console (Marta)

| # | Feature | Route | Endpoints |
|---|---|---|---|
| 1 | Overview dashboard — pending count, team radar (values hidden), queue list, calibration card | `/manager` | GET `/recommendations`, `/calibration`, `/insights/team`, `/staff/{id}/gap` (per roster member) |
| 2 | Verify queue — filter chips (All / dimension / Abstained), inline expand with Confirm-Correct-Reject verdict UI, abstained cards dashed | `/manager/verify` | GET `/recommendations`; POST `/recommendations/{id}/verify` |
| 3 | Verify detail — default view shows name + one sentence + Confirm / Correct / Reject; "Why is the AI saying this?" opens cited evidence; Correct picks a BARS description row | `/manager/verify/{id}` | GET `/recommendations/{id}`; POST `/recommendations/{id}/verify` `{verdict, dimension_verdicts[], reason, seconds_to_decide}` |
| 4 | Transfer gap — conclusion card, quadrant badges, radar (values hidden), practice-side privacy note | `/manager/gap?staff=` | GET `/staff/{id}/gap`, `/staff/{id}/scores?source=floor` |
| 5 | Observation wizard — one question at a time (who → full/partial → kind of moment → one dimension at a time → note); partial rates only witnessed dimensions; BARS description picker (no numbers); idempotent write, 409 sequencing gate | `/manager/observe` | GET `/staff/{id}/scores`; POST `/observations` `{staff_id, observed_at, context, what_happened, ratings[]}` |
| 6 | Team insights — k-anonymised patterns (k = 5), suppressed rows visible, calibration card | `/manager/insights` | GET `/insights/team` |

## C. Staff PWA (Diego)

| # | Feature | Route | Endpoints |
|---|---|---|---|
| 7 | Home — debrief entry with voice input (mic permission-first, demo fallback), last practice (level words only), trust footer | `/staff` | POST `/debriefs`, GET `/debriefs/{id}` |
| 8 | Practice list — 1 personal replay + 3 starter scenarios | `/staff/practice` | GET `/scenarios` |
| 9 | Practice chat — scripted guest (4 turns), mood shifts, voice input with fallback, optimistic send, finish-to-score | `/staff/practice/{id}` | POST `/scenarios/{id}/attempts`; POST `/attempts/{id}/turns`; POST `/attempts/{id}/complete` |
| 10 | Results — level words (Finding this hard → Leading here), quoted evidence, "What earned this" | `/staff/results/{id}` | GET `/attempts/{id}` |
| 11 | History — per-run feedback, manager-observation lock icons | `/staff/history` | (seed data) |

## D. Shared layer

### Route handlers (`src/app/api/v1/**`)

All wrap the mock store; none enforce Bearer auth or validate
`Idempotency-Key` in mock mode. Errors are RFC 9457
`application/problem+json`. The only 409 is
`GET /staff/{id}/scores?source=practice` before the manager's first floor
observation (sequencing gate, not permission).

| Method + Path | Wraps | Notes |
|---|---|---|
| GET `/scenarios` | `listScenarios` | not in openapi.yaml |
| POST `/scenarios/{id}/attempts` | `startAttempt` | 201; idempotent per scenario |
| GET `/attempts/{id}` | `getAttempt` | 404 problem+json; not in yaml |
| POST `/attempts/{id}/turns` | `sendTurn` | body `{content}` |
| POST `/attempts/{id}/complete` | `completeAttempt` | |
| GET `/observations` | `listObservations` | not in yaml |
| POST `/observations` | `logObservation` | 201 |
| GET `/recommendations` | `listRecommendations` | |
| GET `/recommendations/{id}` | `getRecommendation` | 404 |
| POST `/recommendations/{id}/verify` | `verifyRecommendation` | |
| GET `/staff/{id}/gap` | `getGap` | 404 |
| GET `/staff/{id}/scores?source=practice\|floor` | builds rows from attempts/observations | 400 invalid source; 404 unknown staff; 409 sequencing |
| POST `/debriefs` | `createDebrief` | 202 `{id, status, poll_after_ms}`; accepts legacy `{text}` variant beyond yaml |
| GET `/debriefs/{id}` | `getDebrief` | 404 |
| GET `/insights/team` | `getTeamInsights` | |
| GET `/calibration` | `getCalibration` | bare `CalibrationReading[]` |

### Real-API switch

`NEXT_PUBLIC_USE_REAL_API=true` + `NEXT_PUBLIC_API_BASE_URL` flips reads and
writes to the gateway (`src/lib/api/client.ts`); every POST auto-adds
`Idempotency-Key`. In mock mode, server pages call the mock store in-process;
mutating client components use raw `fetch("/api/v1/…")`.

### Mock store

`globalThis.__coachingMockStore` (`src/lib/mock/db.ts`) — shared by SSR pages
and route handlers. Seeded from the team dataset snapshot **seed 20260913**
(13 staff, 22 observations, 45 attempts, 65 gap rows). Mutations: verify
recommendation (recomputes calibration), log observation (drafts a
recommendation, may abstain), attempt turns/complete (scripted guest,
template-scored), create debrief.

### Domain model

- 5 canonical dimensions: `service_recovery, empathy, communication,
  composure, anticipation`.
- Quadrants: blocked / skill_gap / competent / recalibrate.
- Calibration: Wilson interval z=1.96; provisional n<10, reliable
  lower≥0.75, unreliable upper<0.65.
- `INSIGHT_K = 5` — team patterns only surface when ≥5 staff share them;
  suppressed rows are shown deliberately.

### UI system

- Light spa palette (cream/sage/sand/brown), Fraunces headings + Inter body,
  12px caption floor, WCAG contrast, sr-only "not shown" for hidden radar
  values, two-level disclosure pattern (Details toggles), "Back to overview"
  link on every manager tab page.

## E. Open contract items (frontend ↔ backend)

1. **Idempotency-Key missing on two writes** — verify POST and attempt
   complete POST don't send the header the contract requires.
2. **Debrief payload mismatch** — UI sends legacy `{text}`; openapi.yaml
   wants `upload_key` + `duration_ms` + `recorded_at`.
3. **Frontend-only endpoints beyond the yaml** — GET `/scenarios`,
   POST `/scenarios/{id}/attempts`, GET `/attempts/{id}`,
   GET `/observations` need contract decisions (add to yaml or replace).
4. **Result shape divergence** — yaml `DimensionScore` (per-dimension
   `evidence_span`) vs frontend `ScoreResult` (separate `evidence[]` +
   `overall_feedback`).
5. **`ObservationInput.source` enum** in the yaml isn't in the frontend type.
6. **Scenario engine (Nathan's lane)** — guest replies are scripted and
   don't react to reply quality; scripts trimmed to 4 turns for the demo
   (turn budget now derives from script length).
7. Minor: overview dashboard does N+1 gap calls over the roster; mock
   doesn't enforce Bearer auth.
