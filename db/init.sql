-- pg_cron bootstrap — runs once, on first cluster init (empty data volume), against
-- the POSTGRES_DB (`app`). See db/Dockerfile for how this file gets mounted.
--
-- IMPORTANT: this only runs when the data directory is empty. If you've already done
-- `docker compose up` once, the `pgdata` volume exists and this script is skipped —
-- wipe it with `docker compose down -v` and bring it back up to re-bootstrap.
--
-- It also requires the server to have been started with
--   shared_preload_libraries = 'pg_cron'
-- (set in docker-compose.yml's `command:`). Without that, CREATE EXTENSION fails with
-- "pg_cron can only be loaded via shared_preload_libraries".

-- 1) Turn on the extension. pg_cron's metadata tables (cron.job, cron.job_run_details)
--    live in whichever database `cron.database_name` points at — we set that to `app`
--    in compose, which is the database this script runs in, so they line up.
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 2) The table the scheduled job writes to. One row per tick — a visible, append-only
--    heartbeat you can query to confirm the scheduler is alive.
CREATE TABLE IF NOT EXISTS cron_heartbeat (
    id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ran_at timestamptz NOT NULL DEFAULT now()
);

-- 3) Register the job: every minute, append a timestamped row. cron.schedule upserts
--    by job name, so re-running this is harmless (it won't create duplicate jobs).
--    The '* * * * *' is standard 5-field cron (min hour day month weekday) = every
--    minute; pg_cron also accepts interval syntax like '30 seconds' for sub-minute.
SELECT cron.schedule(
    'heartbeat-minute',
    '* * * * *',
    $$INSERT INTO cron_heartbeat (ran_at) VALUES (now())$$
);

-- Watch it work (from psql):
--   SELECT * FROM cron_heartbeat ORDER BY ran_at DESC LIMIT 5;   -- the ticks
--   SELECT jobid, jobname, schedule, command FROM cron.job;       -- registered jobs
--   SELECT status, start_time, return_message
--     FROM cron.job_run_details ORDER BY start_time DESC LIMIT 5; -- run history
