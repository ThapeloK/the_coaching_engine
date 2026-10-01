-- ============================================================
--  Application role
--
--  The API connects as ce_app, NOT as the database owner. That matters:
--  row level security does not apply to a table's owner or to a superuser,
--  so connecting as the owner would silently disable every policy in
--  policies.sql and we would ship a governance story that does not run.
--
--  Applied third, after schema.sql and policies.sql.
-- ============================================================

BEGIN;

CREATE ROLE ce_app LOGIN PASSWORD 'ce_app';

GRANT USAGE ON SCHEMA public TO ce_app;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO ce_app;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ce_app;

-- Article 12: the audit record is append only. The application can write
-- events and read them back, and can never rewrite history.
REVOKE UPDATE, DELETE ON audit_event FROM ce_app;

-- Belt and braces. Without FORCE, a future migration that happens to make
-- ce_app an owner would turn the policies off again.
ALTER TABLE score          FORCE ROW LEVEL SECURITY;
ALTER TABLE observation    FORCE ROW LEVEL SECURITY;
ALTER TABLE recommendation FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_event    FORCE ROW LEVEL SECURITY;

COMMIT;
