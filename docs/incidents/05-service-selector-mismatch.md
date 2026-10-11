# Incident: Healthy pods, but the service refuses connections

**Date / environment:** 2026-10-11, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

Requests to the service fail with `Connection refused`, although the pods look perfectly
healthy: `kubectl get pods` shows `1/1 Running`, `RESTARTS 0`, no errors.

This is a different shape from the earlier incidents: nothing is wrong with the pods
themselves. The fault is in the part that connects the Service to the pods.

## Evidence (the commands I ran and the exact lines that proved it)

1. The pods are fine, so the problem is not in them:

   ```
   $ kubectl -n lab get pods
   flight-service-79b8f4b6db-fhc4c   1/1   Running   0   25s
   flight-service-79b8f4b6db-kcjmp   1/1   Running   0   25s
   ```

2. The Service has nowhere to send traffic, and the customer's request fails the same way:

   ```
   $ kubectl -n lab get endpoints flight-service
   NAME             ENDPOINTS   AGE
   flight-service   <none>      27s

   $ (from inside the cluster, through the Service name)
   urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
   ```

3. The Service looks for one label, the pods carry another:

   ```
   $ kubectl -n lab describe service flight-service
   Selector:                 app=flight-svc
   Endpoints:

   $ kubectl -n lab get pods --show-labels
   flight-service-79b8f4b6db-fhc4c   1/1   Running   0   27s   app=flight-service,pod-template-hash=79b8f4b6db
   ```

   The Service selects `app=flight-svc`. No pod has that label (they have `app=flight-service`).

## Root cause

The Service selector says `app: flight-svc`, but the pods are labelled `app: flight-service`.
No pod matches, so the Service has no endpoints and refuses every connection. Pods and
application are healthy; only the label in the Service is wrong.

## Fix

Pointed the Service selector at the label the pods really carry. The pods were not touched
(same names, same age, no restarts):

```
$ kubectl -n lab patch service flight-service --type=json \
    -p '[{"op":"replace","path":"/spec/selector/app","value":"flight-service"}]'
service/flight-service patched
```

Checked the result:

- `kubectl -n lab get endpoints flight-service` now lists `10.244.0.25:8000` and
  `10.244.0.26:8000`.
- Through the Service name (the customer's path), `urlopen("http://flight-service/health")`
  returned `{"status":"ok"}`.

## Escalate to

Nobody: a label typo in a Service I own. A good question for whoever wrote the manifest is why
the Service and the Deployment were written with two different names for the same thing.

## Prevention

- Our Helm chart writes the label in two places that must match (`selector` in the Service and
  `labels` in the Deployment template). It is worth a test or a lint step that renders the chart
  and checks that the Service selector matches the pod labels.
- After every deploy run `kubectl get endpoints <service>`: an empty list is the signature of
  this fault, even when every pod is Ready.
- Reading tip: pods Ready and connection refused means "look at the Service", and
  `get endpoints` is the fastest check. If a Service and its pods do not meet, compare
  `describe service` (Selector) with `get pods --show-labels`.
