# How we work

Five people, twelve days, one demo that has to run on stage. The rules below exist so nobody
breaks `main` the night before.

---

## Branches

There is one branch per person. Work on yours, open a PR into `main`.

| Branch | Owner | Lane |
|---|---|---|
| `main` | everyone | **Protected. Always demoable.** Never push directly |
| `nathan` | Nathan | Agent graph, retrieval, calibration, eval, voice |
| `ziyi` | Ziyi | API, database, both frontends, deployment, n8n |
| `thapelo` | Thapelo | Scoring engine, rules engine, cohort and root-cause routing |
| `puneet` | Puneet | Session service, model routing, QA and adversarial tests |
| `mary-susan` | Mary-Susan | BARS rubric, golden-set ground truth, scenario content |

For a big or risky piece, branch off your own branch rather than cluttering it:
`nathan/cite-gate`, `ziyi/observation-api`. Merge back into your branch, then PR to `main`.

---

## The one rule about `main`

**`main` must be demoable at all times.**

From **11 September** that is not a guideline. If `main` is broken on the 13th we have no
submission, and if it is broken on the 14th we have no pitch.

So:

- Never push directly to `main`. Always a PR.
- Never merge a PR that has not been run by someone else.
- If you break `main`, revert first and fix afterwards. Do not debug on `main`.

---

## Pull requests

Small and frequent beats one enormous merge on the 10th.

**Before you open one:**
1. Pull `main` and merge it into your branch, you resolve the conflicts, not the reviewer
2. Run it. Actually run it, not "it compiled"
3. If you touched the contract in `contracts/`, say so in the title

**PR title:** what changed, in plain words. `Add cite gate with abstain path`, not `updates`.

**Review:** one approval. Anyone can approve. If nobody has looked within four hours and it is
blocking you, say so in the tech group and merge, a stalled build is worse than an unreviewed
merge on a twelve-day project.

---

## Contracts are frozen

`contracts/` and `db/` define how our pieces fit together. Ziyi builds the API against them,
Nathan builds the agent against them, Puneet tests against them, all in parallel, none of us
waiting.

**Changing a contract breaks somebody else's work in progress.** So:

- Post in the tech group before you change one, naming what breaks
- Never change one silently in a PR that is mostly about something else

Two weeks is not long enough to renegotiate interfaces mid-build.

---

## Never commit

- **The hotel SOPs.** Real property, real internal manuals, shared for prototype use only. Not
  ours to publish. `.gitignore` blocks them, do not work around it.
- **Real staff data.** Synthetic personas only, everywhere.
- **Secrets.** No keys, no service-account JSON, no `.env`.

This repo is **public**. Every commit is world-readable, permanently, including after you delete
the file. Check `git status` before you commit.

---

## Commits

Present tense, says what it does:

```
Add Wilson interval to calibration service
Fix null handling in transfer gap when no floor score exists
Seed demo data for the room-readiness cohort
```

Commit often on your own branch, it is yours, nobody else is reading it.

---

## If you are stuck for more than two hours

Say so in the tech group. On a twelve-day build, one person quietly stuck for a day costs us
roughly 8% of the remaining time. Nobody will think less of you; we will think less of a silent
Thursday.
