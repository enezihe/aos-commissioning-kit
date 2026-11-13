# ADR 0006: Expose request metrics and scrape them with the Prometheus Operator

- **Status:** Accepted
- **Date:** 2026-11-12

## Context
The readiness gate says whether a deployment is healthy at one moment. Nothing said how the service
behaves over time: how many requests it gets, how many fail and how slow they are. Without those
numbers there is no way to set a reliability target.

## Decision
- The flight service counts and times every request in a middleware and exposes the result on
  `GET /metrics` with the `prometheus_client` library: one counter (`http_requests_total` by method,
  path, status) and one histogram (`http_request_duration_seconds` by method, path).
- The `path` label is the route template, never the real address, and unknown addresses share one
  value (`unmatched`). The number of time series stays fixed whatever the callers send.
- Prometheus and Grafana come from the `kube-prometheus-stack` chart. The flight-service chart adds a
  `ServiceMonitor` and the dashboard as a labelled ConfigMap, both behind values that are off by default.

## Alternatives considered
- **A separate error counter:** simpler to read, but it repeats what the `status` label already says,
  and two numbers can disagree.
- **Hand-written Prometheus and Grafana manifests:** smaller, and nothing to learn but the two tools.
  The operator is what clusters run in practice, and its `PrometheusRule` resource is the place for
  the alert rules that come next.
- **Scrape annotations on the pods (`prometheus.io/scrape`):** no extra resource type, but they only
  work with a hand-written scrape configuration, not with the operator.
- **A ready-made FastAPI instrumentation package:** less code, but the middleware is about twenty
  lines and the label choices are the part worth owning.
- **OpenTelemetry:** the better choice once traces are needed. For three numbers it adds a collector
  and more configuration than the problem needs.

## Consequences
- Rate, errors and latency are visible per route and per pod, and SLOs can be built on them.
- The chart refers to a resource type (`ServiceMonitor`) that a plain cluster does not have, so
  monitoring must be switched on deliberately, after the stack is installed.
- `/metrics` shares the API port, so the OpenShift Route exposes it. Acceptable for a lab; a
  production setup would use a second port.
- Probe requests are counted too. Queries about customer traffic must leave out `/health` and `/ready`.
