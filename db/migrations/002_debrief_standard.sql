-- 002: the clause the debrief was matched against.
--
-- NOTE: these columns are also in schema.sql, which is what a FRESH database
-- gets. This file exists for databases that were already running when the
-- column was added, and is safe to re-run. Keep the two in step: schema.sql is
-- the source of truth for a new install, and a migration that is not also in
-- schema.sql is a bug that only shows up on somebody else's machine.
--
-- A staff member who speaks a debrief should be shown the hotel's OWN wording
-- for that situation, not a generic tip. Resolving it once at extraction time
-- and storing the chunk id means every later read shows the same clause: the
-- retrieval is part of the record, not re-rolled on each page load.
ALTER TABLE shift_debrief
    ADD COLUMN IF NOT EXISTS standard_chunk_id uuid REFERENCES sop_chunk(id),
    ADD COLUMN IF NOT EXISTS standard_why      text;
