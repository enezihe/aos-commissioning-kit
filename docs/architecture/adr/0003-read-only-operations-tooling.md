# ADR 0003: Make the operations tool read-only by construction

- **Status:** Accepted
- **Date:** 2026-11-11

## Context
Operations tools are dangerous: the wrong cluster or namespace, or an accidental delete, causes an
outage. `aos-ops` is used during incidents, when people are under pressure.

## Decision
`aos-ops` calls kubectl only through one wrapper that allows the reading verbs `get`, `describe`,
`logs` and `exec`, and refuses everything else before kubectl is started. The target cluster is
printed first, and a namespace is always required. Fixes are suggested in the output, never applied.

## Alternatives considered
- **A confirmation prompt before every change:** people confirm out of habit under pressure.
- **Rely on Kubernetes RBAC alone:** the right control, but it depends on how each customer sets up the
  account. The wrapper protects even when the account is too powerful.
- **Allow changes behind a flag:** one more way to make a mistake; the config tool already covers
  changes, with a dry run and versions.

## Consequences
- A bug or a wrong command in the tool cannot change the cluster.
- The engineer applies each fix by hand, which is slower but deliberate.
- `exec` can still run a command inside a pod; the readiness gate uses it for a connection check from inside a pod.
