# Architecture

Why the AOS Commissioning Kit is built the way it is. The [project README](../../README.md) says what
was built; these pages say why, and what the alternatives were.

## Diagrams (C4)

| Level | Question it answers | Page |
|---|---|---|
| 1. System context | Who uses the kit, and what does it touch? | [c4-context.md](c4-context.md) |
| 2. Containers | What runs where, and what talks to what? | [c4-containers.md](c4-containers.md) |

## Decision records

Each record has a context, the decision, the alternatives that were considered and the consequences.

| # | Decision |
|---|---|
| [0001](adr/0001-helm-over-plain-manifests.md) | Package the service as a Helm chart, keep plain manifests as a reference |
| [0002](adr/0002-versioned-configmap-for-airport-config.md) | Store the airport config as versioned ConfigMaps |
| [0003](adr/0003-read-only-operations-tooling.md) | Make the operations tool read-only by construction |
| [0004](adr/0004-ai-triage-with-quote-verification.md) | Use AI for triage drafts and verify every quote against the evidence |
| [0005](adr/0005-postgresql-for-flight-data.md) | Store flights in PostgreSQL, with the login in a Secret |
| [0006](adr/0006-prometheus-metrics-with-the-operator.md) | Expose request metrics and scrape them with the Prometheus Operator |
