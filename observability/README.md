# Observability

Request metrics from the flight service, scraped by Prometheus and shown in Grafana.

## What the service exposes

`GET /metrics` on every pod, in the Prometheus text format:

| Metric | Type | Labels | Answers |
|---|---|---|---|
| `http_requests_total` | counter | `method`, `path`, `status` | How many requests, and how many failed? |
| `http_request_duration_seconds` | histogram | `method`, `path` | How long do requests take? |

`path` is the route (`/flights/{flight_no}`), not the real address, so a flight number never becomes
its own time series. Requests that match no route are counted as `unmatched`. The scrape of
`/metrics` itself is not counted. Probe requests (`/health`, `/ready`) are counted, and the
dashboard leaves them out so they do not hide the customer traffic.

There is no separate error counter: errors are the requests whose `status` starts with 5.

## Install on the local cluster

Prometheus, Alertmanager and Grafana come from the `kube-prometheus-stack` chart. The values file in
this folder makes it fit a kind cluster.

```bash
# 1. The monitoring stack, in its own namespace
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack --version 93.2.2 \
  -n monitoring --create-namespace -f observability/kube-prometheus-stack-values.yaml --wait

# 2. Switch on scraping and the dashboard for the flight service
helm upgrade --install flight helm/flight-service \
  --set metrics.serviceMonitor.enabled=true --set metrics.dashboard.enabled=true
```

The two `metrics` values are off by default. They create a `ServiceMonitor`, a resource type that only
exists after step 1, so a cluster without monitoring can still install the chart.

## Check it

```bash
# Prometheus: both pods must be listed under the flight-service target, state UP
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090
# open http://localhost:9090/targets

# Grafana: user admin, the password is in a Secret
kubectl -n monitoring get secret monitoring-grafana -o jsonpath='{.data.admin-password}' | base64 -d; echo
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
# open http://localhost:3000 and find the dashboard "Flight service"
```

## The dashboard

`helm/flight-service/dashboards/flight-service.json`, shipped by the chart as a ConfigMap that Grafana
loads by its label. It follows the RED method: rate, errors, duration.

| Panel | Query idea | Reading it |
|---|---|---|
| Pods scraped | `count(up == 1)` | Should equal the replica count |
| Requests per second | `sum(rate(http_requests_total[5m]))` | How much work the service does |
| Error ratio (5xx) | failed rate divided by total rate | The share of requests the service failed |
| Latency p50, p95, p99 | `histogram_quantile` over the buckets | A rising p99 with a flat p50 means a few slow requests |
| Requests per second by pod | rate grouped by `pod` | A flat line means a pod gets no traffic |

## Known limitations

- `/metrics` is on the same port as the API, so on OpenShift the Route exposes it too. A production
  setup would serve it on a second port that the Route does not publish.
- Each pod counts from zero after a restart. `rate()` handles that; raw totals do not survive.
- Only checked on kind. On the OpenShift sandbox a user cannot install the operator.
