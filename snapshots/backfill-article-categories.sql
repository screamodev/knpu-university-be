-- ─────────────────────────────────────────────────────────────────────────────
-- One-off data migration: legacy single `articles.category` (M2O)
-- -> `articles_categories` junction (M2M).
--
-- The committed schema snapshot both creates the junction and drops
-- `articles.category`, so a single `schema apply` would take the mapping with
-- it. Run this file TWICE, around the apply:
--
--   1. before `schema apply` — copies articles.id/articles.category into the
--      holding table `articles_categories_legacy`;
--   2. after `schema apply`  — inserts the held rows into the junction.
--
-- Each phase runs whichever step is possible right now, and both are
-- idempotent, so re-running (or running it on an already-migrated database) is
-- a no-op.
--
-- From the host (dev):
--   docker compose -f docker-compose.dev.yml exec -T postgres \
--     psql -U directus -d knpu_university -v ON_ERROR_STOP=1 \
--     < snapshots/backfill-article-categories.sql
--
-- On prod use docker-compose.prod.yml and the DB_USER / DB_DATABASE from .env.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
  has_legacy_column boolean;
  has_junction      boolean;
  has_holding       boolean;
  moved             bigint;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'articles' AND column_name = 'category'
  ) INTO has_legacy_column;

  SELECT to_regclass('public.articles_categories') IS NOT NULL INTO has_junction;

  -- Phase 1: park the legacy mapping somewhere `schema apply` will not touch.
  IF has_legacy_column THEN
    CREATE TABLE IF NOT EXISTS articles_categories_legacy (
      articles_id   uuid NOT NULL,
      categories_id uuid NOT NULL,
      PRIMARY KEY (articles_id, categories_id)
    );

    INSERT INTO articles_categories_legacy (articles_id, categories_id)
    SELECT a.id, a.category
    FROM articles a
    WHERE a.category IS NOT NULL
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS moved = ROW_COUNT;
    RAISE NOTICE 'phase 1: parked % legacy link(s) in articles_categories_legacy.', moved;
  ELSE
    RAISE NOTICE 'phase 1: articles.category is gone - nothing to park.';
  END IF;

  -- Phase 2: fill the junction from whatever is available.
  SELECT to_regclass('public.articles_categories_legacy') IS NOT NULL INTO has_holding;

  IF has_junction AND has_holding THEN
    INSERT INTO articles_categories (articles_id, categories_id)
    SELECT l.articles_id, l.categories_id
    FROM articles_categories_legacy l
    WHERE EXISTS (SELECT 1 FROM articles a WHERE a.id = l.articles_id)
      AND EXISTS (SELECT 1 FROM categories c WHERE c.id = l.categories_id)
      AND NOT EXISTS (
        SELECT 1 FROM articles_categories j
        WHERE j.articles_id = l.articles_id AND j.categories_id = l.categories_id
      );

    GET DIAGNOSTICS moved = ROW_COUNT;
    RAISE NOTICE 'phase 2: inserted % junction row(s).', moved;
  ELSIF NOT has_junction THEN
    RAISE NOTICE 'phase 2: articles_categories does not exist yet - apply the schema, then re-run.';
  END IF;
END
$$;

-- The holding table may legitimately be absent (nothing to migrate), so the
-- summary is built dynamically rather than referencing it in plain SQL.
DO $$
DECLARE
  junction bigint := 0;
  parked   text   := 'n/a (no holding table)';
BEGIN
  IF to_regclass('public.articles_categories') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM articles_categories' INTO junction;
  END IF;

  IF to_regclass('public.articles_categories_legacy') IS NOT NULL THEN
    EXECUTE 'SELECT count(*)::text FROM articles_categories_legacy' INTO parked;
  END IF;

  RAISE NOTICE 'summary: junction_rows=%, parked_legacy_rows=%', junction, parked;
END
$$;

-- Once `junction_rows >= parked_legacy_rows` on every environment, the holding
-- table can go:  DROP TABLE articles_categories_legacy;
