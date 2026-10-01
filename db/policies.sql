-- ============================================================
--  Row level security
--
--  These policies ARE the governance story. Not a slide, not a promise:
--  a set of rules the database enforces even when a service has a bug.
--
--  Run after schema.sql.
-- ============================================================

BEGIN;

-- Session context, set by the API gateway on every request:
--   SELECT set_config('app.property_id', $1, true);
--   SELECT set_config('app.staff_id',    $2, true);
--   SELECT set_config('app.role',        $3, true);

CREATE FUNCTION app_property() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.property_id', true), '')::uuid $$;

CREATE FUNCTION app_staff() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.staff_id', true), '')::uuid $$;

CREATE FUNCTION app_role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT coalesce(nullif(current_setting('app.role', true), ''), 'none') $$;

-- Has this manager already logged an observation of this staff member?
-- Everything about BR-01 depends on this function.
CREATE FUNCTION has_observed(p_manager uuid, p_staff uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM observation o
        WHERE o.manager_id = p_manager
          AND o.staff_id   = p_staff
          AND o.logged_at > now() - interval '30 days'
    )
$$;

ALTER TABLE score          ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation    ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation      ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation_rating  ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event    ENABLE ROW LEVEL SECURITY;


-- 1. Hard tenant boundary. Nothing crosses a property, ever.
--
--    RESTRICTIVE is load bearing. Postgres OR's permissive policies together,
--    so a permissive tenant policy would grant every row in the property to
--    every role and silently defeat all four policies below it. Restrictive
--    policies are AND'd, which is what a boundary actually means.
--
--    This was a real bug: it let a staff member read a colleague's scores.
--    Caught by NT4.
CREATE POLICY score_tenant ON score AS RESTRICTIVE
    USING (property_id = app_property());


-- 2. TRANSPARENCY PARITY. A staff member reads everything about themselves.
--    There is no screen in this product an employee is not allowed to see,
--    and this is the line that makes that true rather than aspirational.
CREATE POLICY score_self_read ON score FOR SELECT
    USING (property_id = app_property() AND staff_id = app_staff());


-- 3. Managers read floor scores for their own team freely.
CREATE POLICY score_manager_floor ON score FOR SELECT
    USING (
        property_id = app_property()
        AND app_role() IN ('manager', 'ld_admin')
        AND source = 'floor'
        AND EXISTS (SELECT 1 FROM team_assignment t
                     WHERE t.manager_id = app_staff()
                       AND t.staff_id = score.staff_id)
    );


-- 4. ...but PRACTICE scores only AFTER logging their own observation.
--
--    The single most important policy in this file. It is a psychological
--    safety control and a measurement validity control at the same time: if
--    the manager sees the practice score first, their observation is anchored
--    on it, the two streams stop being independent, and the transfer gap
--    stops meaning anything.
--
--    Expect UI pressure to show everything on one screen. Do not give in.
CREATE POLICY score_manager_practice ON score FOR SELECT
    USING (
        property_id = app_property()
        AND app_role() = 'manager'
        AND source = 'practice'
        AND EXISTS (SELECT 1 FROM team_assignment t
                     WHERE t.manager_id = app_staff()
                       AND t.staff_id = score.staff_id)
        AND has_observed(app_staff(), score.staff_id)
    );


-- 5. L&D gets patterns, not individual practice transcripts.
CREATE POLICY score_ld_aggregate_only ON score FOR SELECT
    USING (
        property_id = app_property()
        AND app_role() = 'ld_admin'
        AND source = 'floor'
    );


-- 6. Observations follow the same tenant and parity rules.
CREATE POLICY observation_tenant ON observation AS RESTRICTIVE
    USING (property_id = app_property());

-- A staff member reads observations about themselves. Transparency parity.
CREATE POLICY observation_self_read ON observation FOR SELECT
    USING (staff_id = app_staff());

-- A manager reads and writes observations for their own team.
CREATE POLICY observation_manager ON observation
    USING (
        app_role() IN ('manager', 'ld_admin')
        AND EXISTS (SELECT 1 FROM team_assignment t
                     WHERE t.manager_id = app_staff()
                       AND t.staff_id = observation.staff_id)
    )
    WITH CHECK (
        app_role() IN ('manager', 'ld_admin')
        AND manager_id = app_staff()
    );


-- 7. Writes.
--
--    Scores are written by the agent after scoring an attempt, and by the API
--    when a manager's observation ratings land. No human role writes them
--    directly, so the policy is scoped to the tenant and the API is the only
--    caller. Note there is deliberately no UPDATE or DELETE policy: a score is
--    a record of a judgement at a point in time, and rewriting one would
--    corrupt both the transfer gap and the calibration series.
CREATE POLICY score_insert ON score FOR INSERT
    WITH CHECK (property_id = app_property());

CREATE POLICY observation_rating_all ON observation_rating
    USING (property_id = app_property())
    WITH CHECK (property_id = app_property());

--    Recommendations are written by the agent and updated once, by the
--    verification step, to record the manager's verdict.
CREATE POLICY recommendation_rw ON recommendation
    USING (property_id = app_property())
    WITH CHECK (property_id = app_property());

-- 8. Audit is insert only. Article 12 record keeping is worth nothing if the
--    record can be edited afterwards. The REVOKE in roles.sql is what enforces
--    that; this policy just permits the insert.
CREATE POLICY audit_insert ON audit_event FOR INSERT WITH CHECK (true);
CREATE POLICY audit_read ON audit_event FOR SELECT
    USING (property_id = app_property());

COMMIT;


-- ============================================================
--  Negative tests. All must return ZERO rows or raise.
--  Puneet owns running these. NT2 and NT3 are the pair that matter most.
--
--  NT1   Manager at property A queries scores for staff at property B
--          -> zero rows. Not an error: zero rows is correct RLS behaviour
--  NT2   Manager reads practice scores for someone they have NOT observed
--          -> zero rows
--  NT3   Same manager logs an observation, then repeats NT2
--          -> rows returned
--  NT4   Staff member queries another staff member's scores
--          -> zero rows
--  NT5   ld_admin queries practice transcripts
--          -> zero rows
--  NT6   INSERT cohort_pattern with staff_count = 4
--          -> k_anonymity constraint violation
--  NT7   UPDATE or DELETE an audit_event
--          -> permission denied
--  NT8   INSERT recommendation with no citation rows in the same transaction
--          -> rejected by the service layer transaction guard
--  NT9   INSERT score with level = 0 or 6
--          -> check constraint violation
--  NT10  INSERT practice-source score carrying an observation_id
--          -> score_source_consistency violation
-- ============================================================
