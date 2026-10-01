# API contract

`openapi.yaml` is the interface between the frontends, the API and the agent.

It is **frozen**. Ziyi builds the API against it, Nathan builds the agent
against it, Puneet writes tests against it, all at the same time and none of us
blocked on the others. That only works while the contract holds still.

**Before changing it:** post in the tech group naming what breaks. Never change
it silently inside a PR that is mostly about something else.

Full narrative version with worked request and response examples:
`02B-LLD-API-Contracts` in the shared drive.

## Three things in here that are easy to get wrong

**`Idempotency-Key` is required, not optional,** on every endpoint that spends
model tokens or writes a decision. A double tap on hotel wifi otherwise
produces two scoring runs and two entries in the calibration record, which
silently corrupts the accuracy number we plan to say out loud on stage.

**`unlocked_practice_history` is in the response, never the request.** The
manager's judgement is captured first; only then does the system reveal what it
thinks.

**Citations are inline, never a second request.** If checking the evidence
costs a round trip, nobody checks, and the transparency claim becomes
theoretical.
