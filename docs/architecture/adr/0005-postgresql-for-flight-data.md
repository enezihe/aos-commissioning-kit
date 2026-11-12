# ADR 0005: Store flights in PostgreSQL, with the login in a Secret

- **Status:** Accepted
- **Date:** 2026-11-11

## Context
The flight service kept flights in a dict inside the process. With two replicas, each pod had its own
list, so the answer to `GET /flights` depended on which pod the Service picked, and a pod restart
lost everything.

## Decision
- Flights live in one PostgreSQL table. The service talks to it through a small store interface
  (`app/store.py`), with a PostgreSQL implementation and an in-memory one for tests and local runs.
- PostgreSQL runs as a StatefulSet with a 1 Gi volume, in the same Helm chart (`db.enabled`).
- The login (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) comes from a Secret named `flight-db`
  that exists before the install. The chart refers to it by name and never holds the password.
- Readiness uses `/ready`, which asks the database. Liveness stays on `/health`, so a database outage
  removes pods from the Service but does not restart them.

## Alternatives considered
- **Sticky sessions on the Service:** hides the problem for one client, but data is still lost on restart.
- **A managed database (Azure Database for PostgreSQL, RDS):** the right choice in production, but it
  cannot run on a laptop kind cluster; the store interface keeps that switch small.
- **The Secret created by the chart from values:** the password would sit in values files and in the
  Helm release record.
- **SQLite on a shared volume:** a `ReadWriteOnce` volume cannot be shared by pods on different nodes.

## Consequences
- Replicas return the same data and a deleted pod loses nothing.
- Starting the chart without the Secret leaves every pod in `CreateContainerConfigError`
  (incident 07). That is deliberate: no pod runs with a guessed login.
- The database is one pod without backups or replication. A restart takes it away for several seconds,
  and the service answers 503 on `/ready` meanwhile.
- No migration tool yet: the table is created when the service first reaches the database.
