# Start from TimescaleDB with Postgres 17
# Stage 1: pgvector image with Postgres 17 (already has vector extension installed)
FROM pgvector/pgvector:pg17 AS pgvector_src

# Stage 2: final image - TimescaleDB with Postgres 17
FROM timescale/timescaledb:2.20.3-pg17

# Copy pgvector extension binaries and control files from pgvector image
COPY --from=pgvector_src /usr/lib/postgresql/17/lib/vector.so /usr/lib/postgresql/17/lib/vector.so
COPY --from=pgvector_src /usr/share/postgresql/17/extension/vector* /usr/share/postgresql/17/extension/

# Optional: auto-enable extensions on first DB init
#COPY init.sql /docker-entrypoint-initdb.d/init.sql