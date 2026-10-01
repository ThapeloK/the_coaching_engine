-- ============================================================
--  The Coaching Engine: core schema
--  Matches 02A-LLD-Data-Model. Postgres 15+ with pgvector.
--
--  Two rules worth reading before you change anything here:
--
--  1. Row level security is enforced in the DATABASE, not the app. It holds
--     even when a service has a bug, and it means we can prove tenant
--     isolation with a failing query rather than asserting it on a slide.
--
--  2. Policy score_manager_practice in policies.sql is the most important
--     rule we have. A manager cannot read a staff member's practice scores
--     until they have logged their own observation. That is not only
--     psychological safety, it is measurement validity: if the manager sees
--     the score first, their observation is anchored on it and the transfer
--     gap becomes meaningless.
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";


-- ------------------------------------------------------------
--  Tenancy and identity
-- ------------------------------------------------------------

CREATE TYPE staff_role AS ENUM ('staff', 'manager', 'ld_admin');

CREATE TABLE property (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text        NOT NULL,
    country_code    char(2)     NOT NULL DEFAULT 'IE',
    star_rating     smallint    CHECK (star_rating BETWEEN 1 AND 5),
    room_count      integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE staff_member (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    auth_user_id    uuid        UNIQUE,
    display_name    text        NOT NULL,
    department      text        NOT NULL,
    role            staff_role  NOT NULL DEFAULT 'staff',
    is_active       boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Many to many on purpose: hospitality shifts do not respect org charts.
CREATE TABLE team_assignment (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    manager_id      uuid NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    staff_id        uuid NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manager_id, staff_id)
);


-- ------------------------------------------------------------
--  Knowledge: the hotel's own standards
-- ------------------------------------------------------------

CREATE TABLE sop_document (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    title           text        NOT NULL,
    doc_type        text        NOT NULL,
    department      text        NOT NULL DEFAULT 'all',
    source_ref      text,
    version         integer     NOT NULL DEFAULT 1,
    is_synthetic    boolean     NOT NULL DEFAULT false,
    ingested_at     timestamptz NOT NULL DEFAULT now(),
    -- Keyed on title, not doc_type: a property has several documents of the
    -- same type. The Service Promise, Professional Ethic and Positive
    -- Alternatives are all doc_type 'standard' for department 'all'.
    UNIQUE (property_id, title, version)
);

-- Chunks are IMMUTABLE once written. A corpus update creates a new document
-- version and a new set of chunks, so citations written months ago still
-- resolve even after the standard has moved on.
--
-- step_number is not decoration. The demo claim "you skipped step 3" has to
-- resolve to a real numbered clause, which means an ordered procedure is
-- never split across chunks.
CREATE TABLE sop_chunk (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    document_id     uuid        NOT NULL REFERENCES sop_document(id) ON DELETE CASCADE,
    section_path    text        NOT NULL,
    ordinal         integer     NOT NULL,
    step_number     integer,
    content         text        NOT NULL,
    embedding       vector(768),
    content_tsv     tsvector GENERATED ALWAYS AS
                        (to_tsvector('english', content)) STORED,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, ordinal)
);

CREATE INDEX sop_chunk_vec_idx ON sop_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX sop_chunk_fts_idx ON sop_chunk USING gin (content_tsv);
CREATE INDEX ON sop_chunk (property_id, document_id);


-- ------------------------------------------------------------
--  The BARS rubric, as data rather than prompt text
-- ------------------------------------------------------------

CREATE TABLE bars_rubric (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    version         integer     NOT NULL,
    is_active       boolean     NOT NULL DEFAULT false,
    authored_by     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (property_id, version)
);

CREATE TABLE bars_dimension (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rubric_id       uuid        NOT NULL REFERENCES bars_rubric(id) ON DELETE CASCADE,
    code            text        NOT NULL,
    label           text        NOT NULL,
    description     text        NOT NULL,
    UNIQUE (rubric_id, code)
);

-- Each level carries a written behavioural anchor. This is what makes
-- "we are not letting the model decide what good looks like" architecturally
-- true rather than rhetorically true.
CREATE TABLE bars_anchor (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dimension_id    uuid        NOT NULL REFERENCES bars_dimension(id) ON DELETE CASCADE,
    level           smallint    NOT NULL CHECK (level BETWEEN 1 AND 5),
    anchor_text     text        NOT NULL,
    UNIQUE (dimension_id, level)
);


-- ------------------------------------------------------------
--  Evidence stream one: practice
-- ------------------------------------------------------------

CREATE TYPE scenario_origin AS ENUM ('library', 'debrief_derived', 'manager_assigned');
CREATE TYPE attempt_status  AS ENUM ('in_progress', 'completed', 'abandoned', 'scored');

CREATE TABLE scenario (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id        uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    origin             scenario_origin NOT NULL,
    title              text        NOT NULL,
    situation          text        NOT NULL,
    guest_persona      jsonb       NOT NULL,
    target_dimensions  text[]      NOT NULL,
    grounded_chunk_ids uuid[]      NOT NULL DEFAULT '{}',
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scenario_attempt (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    scenario_id     uuid        NOT NULL REFERENCES scenario(id),
    staff_id        uuid        NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    status          attempt_status NOT NULL DEFAULT 'in_progress',
    rubric_id       uuid        REFERENCES bars_rubric(id),
    started_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    turn_count      smallint    NOT NULL DEFAULT 0
);

CREATE TABLE attempt_turn (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    attempt_id      uuid        NOT NULL REFERENCES scenario_attempt(id) ON DELETE CASCADE,
    turn_index      smallint    NOT NULL,
    speaker         text        NOT NULL CHECK (speaker IN ('guest', 'staff')),
    content         text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (attempt_id, turn_index)
);


-- ------------------------------------------------------------
--  Evidence stream two: the floor
-- ------------------------------------------------------------

-- source distinguishes where a floor observation came from. Adding this enum
-- now costs one column and turns "all we have is manager opinions" from an
-- architectural limitation into a data sourcing roadmap.
-- See 11-Observability-Gap.
CREATE TYPE observation_source AS ENUM ('manager', 'mystery_guest', 'peer', 'self');

CREATE TABLE observation (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    staff_id        uuid        NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    manager_id      uuid        NOT NULL REFERENCES staff_member(id),
    source          observation_source NOT NULL DEFAULT 'manager',
    observed_at     timestamptz NOT NULL,
    context         text        NOT NULL,
    what_happened   text        NOT NULL,
    rubric_id       uuid        NOT NULL REFERENCES bars_rubric(id),
    logged_at       timestamptz NOT NULL DEFAULT now()
);

-- level is nullable on purpose. A dimension with no evidence must score NULL,
-- never the midpoint. Defaulting an unevidenced dimension to 3 drags every
-- mean toward the middle and compresses the transfer gap toward zero, which
-- makes the whole product look like it has nothing to say.
CREATE TABLE observation_rating (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    observation_id  uuid        NOT NULL REFERENCES observation(id) ON DELETE CASCADE,
    dimension_id    uuid        NOT NULL REFERENCES bars_dimension(id),
    level           smallint    CHECK (level BETWEEN 1 AND 5),
    UNIQUE (observation_id, dimension_id)
);

CREATE TYPE debrief_status AS ENUM
    ('uploaded', 'transcribed', 'redacted', 'extracted', 'failed');

CREATE TABLE shift_debrief (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id      uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    staff_id         uuid        NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    status           debrief_status NOT NULL DEFAULT 'uploaded',
    audio_uri        text,
    audio_deleted_at timestamptz,
    transcript       text,
    incident         jsonb,
    duration_ms      integer,
    -- The clause this debrief was matched against, resolved once at extraction
    -- and stored. A staff member should be shown their employer's OWN wording
    -- for the situation they just described, not a generic tip, and storing
    -- the chunk id means every later read shows the same clause rather than
    -- re-rolling the retrieval on each page load.
    standard_chunk_id uuid REFERENCES sop_chunk(id),
    standard_why      text,
    created_at       timestamptz NOT NULL DEFAULT now()
);


-- ------------------------------------------------------------
--  Scores: ONE table for BOTH streams
-- ------------------------------------------------------------

-- One table, one scale, shared by the rules engine and the model. A second
-- scale is how a hybrid system ends up contradicting itself in front of a
-- manager, so there is not one.
CREATE TYPE score_source AS ENUM ('practice', 'floor');

CREATE TABLE score (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    staff_id        uuid        NOT NULL REFERENCES staff_member(id) ON DELETE CASCADE,
    dimension_id    uuid        NOT NULL REFERENCES bars_dimension(id),
    rubric_id       uuid        NOT NULL REFERENCES bars_rubric(id),
    source          score_source NOT NULL,
    level           smallint    NOT NULL CHECK (level BETWEEN 1 AND 5),
    attempt_id      uuid        REFERENCES scenario_attempt(id),
    observation_id  uuid        REFERENCES observation(id),
    evidence_span   text,
    model_id        text,
    prompt_version  text,
    scored_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT score_source_consistency CHECK (
        (source = 'practice' AND attempt_id IS NOT NULL AND observation_id IS NULL) OR
        (source = 'floor'    AND observation_id IS NOT NULL AND attempt_id IS NULL)
    )
);

CREATE INDEX ON score (property_id, staff_id, dimension_id, scored_at DESC);


-- ------------------------------------------------------------
--  Decisions: recommendations, citations, verification
-- ------------------------------------------------------------

CREATE TYPE rec_status AS ENUM
    ('pending_verify', 'confirmed', 'corrected', 'rejected', 'abstained');
CREATE TYPE rec_class  AS ENUM ('behavioural', 'process', 'policy');
CREATE TYPE cite_kind  AS ENUM
    ('attempt_turn', 'observation', 'sop_chunk', 'rubric_anchor', 'metric');

CREATE TABLE recommendation (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id      uuid        NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    staff_id         uuid        REFERENCES staff_member(id) ON DELETE CASCADE,
    manager_id       uuid        REFERENCES staff_member(id),
    classification   rec_class,
    status           rec_status  NOT NULL DEFAULT 'pending_verify',
    headline         text,
    body             text,
    suggested_action text,
    evidence_hash    char(64)    NOT NULL,
    rubric_id        uuid        NOT NULL REFERENCES bars_rubric(id),
    model_id         text,
    prompt_version   text,
    abstain_reason   text,
    trace_id         text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- A recommendation and its citations are written in ONE transaction.
-- An uncited recommendation must never be persistable.
CREATE TABLE recommendation_citation (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id       uuid      NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    recommendation_id uuid      NOT NULL REFERENCES recommendation(id) ON DELETE CASCADE,
    kind              cite_kind NOT NULL,
    claim_text        text      NOT NULL,
    source_ref        text      NOT NULL,
    quoted_span       text
);

CREATE TABLE verification (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id       uuid      NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    recommendation_id uuid      NOT NULL UNIQUE REFERENCES recommendation(id) ON DELETE CASCADE,
    manager_id        uuid      NOT NULL REFERENCES staff_member(id),
    verdict           rec_status NOT NULL
                      CHECK (verdict IN ('confirmed', 'corrected', 'rejected')),
    correction_text   text,
    reason            text,
    seconds_to_decide integer,
    decided_at        timestamptz NOT NULL DEFAULT now()
);

-- The compounding asset: how THIS property judges behaviour. Proprietary,
-- per property, and it does not transfer to a competitor.
CREATE TABLE verification_label (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     uuid     NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    verification_id uuid     NOT NULL REFERENCES verification(id) ON DELETE CASCADE,
    dimension_id    uuid     NOT NULL REFERENCES bars_dimension(id),
    agent_level     smallint NOT NULL,
    manager_level   smallint,
    agreed          boolean  NOT NULL
);


-- ------------------------------------------------------------
--  Cohorts, escalation, audit
-- ------------------------------------------------------------

CREATE TYPE escalation_route AS ENUM ('manager', 'ld_hr', 'operations');

CREATE TABLE cohort_pattern (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id    uuid      NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    window_start   date      NOT NULL,
    window_end     date      NOT NULL,
    classification rec_class NOT NULL,
    staff_count    smallint  NOT NULL,
    description    text      NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- k-anonymity as a constraint, not a convention. An attempt to persist a
    -- pattern below five staff is a database error, which means it cannot be
    -- quietly forgotten during a rushed build.
    CONSTRAINT k_anonymity CHECK (staff_count >= 5)
);

CREATE TABLE escalation (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id       uuid     NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    recommendation_id uuid     REFERENCES recommendation(id),
    cohort_pattern_id uuid     REFERENCES cohort_pattern(id),
    route             escalation_route NOT NULL,
    severity          smallint NOT NULL CHECK (severity BETWEEN 1 AND 3),
    rule_id           text     NOT NULL,
    summary           text     NOT NULL,
    acknowledged_at   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_event (
    id            bigserial PRIMARY KEY,
    property_id   uuid      NOT NULL,
    actor         text      NOT NULL,
    event_type    text      NOT NULL,
    subject_ref   text,
    evidence_hash char(64),
    payload       jsonb     NOT NULL,
    occurred_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON escalation (property_id, route, created_at DESC);
CREATE INDEX ON audit_event (property_id, occurred_at DESC);

COMMIT;
