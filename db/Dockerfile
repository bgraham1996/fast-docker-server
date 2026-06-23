# Postgres image with the pg_cron extension baked in.
#
# Why a custom image at all? The stock `postgres:16-alpine` we used before can't run
# pg_cron: the extension ships only as a Debian apt package (`postgresql-16-cron`),
# there is no Alpine build, and pg_cron must be loaded at server start via
# `shared_preload_libraries` (set in docker-compose.yml's `command:`). So we start
# from the Debian-based official image and install the matching extension.
#
# pg_cron lets the *database itself* schedule jobs on standard cron syntax — the
# schedule lives in the `cron.job` table and survives restarts, no extra process.
FROM postgres:16

# The official postgres image already has the PGDG apt repo configured, so the
# version-matched extension package is one install away. Pin to the server's major
# version (16); clean the apt lists to keep the layer small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-cron \
    && rm -rf /var/lib/apt/lists/*

# Scripts in /docker-entrypoint-initdb.d/ run ONCE, the first time the cluster is
# initialised (i.e. when the data volume is empty), against the POSTGRES_DB. This one
# creates the extension, the heartbeat table, and registers the cron job. The numeric
# prefix just makes ordering explicit if more init scripts are added later.
COPY init.sql /docker-entrypoint-initdb.d/10-pg_cron.sql
