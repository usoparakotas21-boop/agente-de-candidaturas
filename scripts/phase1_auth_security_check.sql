-- Candidatura Certa - Fase 1 verification queries.
-- Run this in the Supabase SQL editor or with the Supabase SQL runner.
-- Hosted Auth configuration (including leaked-password protection) is not
-- exposed as a normal public Postgres table. Use verify_supabase_auth_config.py
-- or Dashboard > Authentication > Password Protection for that setting.

-- 1) RLS coverage. The second result is the pass/fail summary expected by CI.
WITH public_tables AS (
    SELECT c.oid, n.nspname AS schema_name, c.relname AS table_name,
           c.relrowsecurity AS rls_enabled
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
), coverage AS (
    SELECT COUNT(*) AS total_tables,
           COUNT(*) FILTER (WHERE rls_enabled) AS rls_enabled_tables,
           COUNT(*) FILTER (WHERE NOT rls_enabled) AS rls_disabled_tables
    FROM public_tables
)
SELECT * FROM coverage;

-- 2) List any public table without RLS. An empty result is required.
SELECT schema_name, table_name
FROM (
    SELECT n.nspname AS schema_name, c.relname AS table_name,
           c.relrowsecurity AS rls_enabled
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
) tables
WHERE NOT rls_enabled
ORDER BY table_name;

-- 3) Trigger coverage. Every public table that has an updated_at column must
-- have trigger_set_updated_at. The result should be empty.
WITH updated_tables AS (
    SELECT c.oid, c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN information_schema.columns col
      ON col.table_schema = n.nspname AND col.table_name = c.relname
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND col.column_name = 'updated_at'
)
SELECT u.table_name
FROM updated_tables u
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_trigger t
    WHERE t.tgrelid = u.oid
      AND NOT t.tgisinternal
      AND t.tgname = 'trigger_set_updated_at'
)
ORDER BY u.table_name;

-- 4) Detailed trigger report and count.
WITH public_tables AS (
    SELECT c.oid, c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
), updated_tables AS (
    SELECT DISTINCT p.oid, p.table_name
    FROM public_tables p
    JOIN information_schema.columns col
      ON col.table_schema = 'public' AND col.table_name = p.table_name
    WHERE col.column_name = 'updated_at'
)
SELECT u.table_name,
       EXISTS (
           SELECT 1 FROM pg_trigger t
           WHERE t.tgrelid = u.oid AND NOT t.tgisinternal
             AND t.tgname = 'trigger_set_updated_at'
       ) AS has_updated_at_trigger
FROM updated_tables u
ORDER BY u.table_name;

-- 5) Core constraints and indexes.
SELECT conname, conrelid::regclass AS table_name
FROM pg_constraint
WHERE conname IN ('uq_vaga_origem_externo', 'uq_candidato_vaga', 'uq_candidatura_candidato_vaga')
ORDER BY conname;

-- 6) Auth password-protection handoff. Supabase Auth owns this setting outside
-- the public database; this result makes the required external check explicit.
SELECT
    'pwned_passwords_enabled' AS setting,
    'managed_by_supabase_auth' AS source,
    'verify_supabase_auth_config.py or Dashboard > Authentication > Password Protection' AS verification_path;
