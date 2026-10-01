# Database

`schema.sql` then `policies.sql`, in that order. Postgres 15+ with the
`vector` extension.

```bash
psql "$DATABASE_URL" -f schema.sql
psql "$DATABASE_URL" -f policies.sql
psql "$DATABASE_URL" -f ../data-generation/output/seed.sql
```

## Two things worth reading before you change anything

**Row level security is enforced in the database, not the application.** It
holds even when a service has a bug, and it means tenant isolation is
something we can prove with a failing query rather than assert on a slide.

**Policy `score_manager_practice` is the most important rule in the schema.**
A manager cannot read a staff member's practice scores until they have logged
their own observation of that person. That is a psychological safety control
and a measurement validity control at once: if the manager sees the score
first, their observation is anchored on it, the two streams stop being
independent, and the transfer gap stops meaning anything.

Expect pressure to relax it so everything fits on one screen. Do not.

## Negative tests

Ten of them, listed at the bottom of `policies.sql`. They must all return zero
rows or raise. NT2 and NT3 are the pair that matter most: a manager cannot see
practice scores before observing, and can immediately after.

Puneet owns running these.
