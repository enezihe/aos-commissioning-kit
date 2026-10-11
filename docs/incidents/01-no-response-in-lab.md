# Incident: Flight service in lab does not respond

**Date / environment:** 2026-10-10, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

The customer says the pods look healthy, but requests to the service get no answer.

`kubectl get pods` does show `STATUS Running`, but `READY 0/1` on both pods, after almost
two minutes and with `RESTARTS 0`. `Running` only says the container started. `READY` says
whether the pod may receive traffic, and it did not.

## Evidence (the commands I ran and the exact lines that proved it)

1. What Kubernetes says about the pod:

   ```
   $ kubectl -n lab describe pod flight-service-d7d59b67d-895nl
   Readiness:    http-get http://:8000/healthz delay=3s timeout=1s period=5s ...
   Warning  Unhealthy  1s (x25 over 117s)  kubelet  Readiness probe failed: HTTP probe failed with statuscode: 404
   ```

   The probe asks for `/healthz` and gets 404. The container itself is fine
   (`State: Running`, `Restart Count: 0`).

2. What the application says (a second, independent witness):

   ```
   $ kubectl -n lab logs flight-service-d7d59b67d-895nl | tail -5
   INFO:     10.244.0.1:39156 - "GET /healthz HTTP/1.1" 404 Not Found
   INFO:     10.244.0.1:39164 - "GET /healthz HTTP/1.1" 404 Not Found
   ```

   The service received the question and answered 404, because it has no `/healthz`.
   Its health endpoint is `/health`.

3. What this means for the customer's traffic:

   ```
   $ kubectl -n lab get endpoints flight-service
   NAME             ENDPOINTS   AGE
   flight-service               2m28s
   ```

   `ENDPOINTS` is empty. A pod that is not Ready is not added to the Service, so the Service
   had nowhere to send the customer's requests.

## Root cause

The readiness probe in the Deployment pointed at `/healthz`, but the service answers on
`/health`. The application was healthy. Kubernetes asked the wrong address, got 404, kept both
pods "not ready", and so the Service had no endpoints and every customer request failed.

## Fix

Changed the probe path to `/health` on the live Deployment:

```
$ kubectl -n lab patch deployment flight-service --type=json \
    -p '[{"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/health"}]'
deployment "flight-service" successfully rolled out
```

Checked the result in two ways:

- `kubectl -n lab get pods` shows two new pods at `1/1 Running`, and
  `kubectl -n lab get endpoints flight-service` lists two addresses
  (`10.244.0.11:8000`, `10.244.0.12:8000`).
- From inside the cluster, through the Service name (the customer's path):
  `urlopen("http://flight-service/health")` returned `{"status":"ok"}`.

## Escalate to

Nobody. I can resolve this myself: it was a typo in the deployment settings, which are part
of what I deploy, and not a defect in the application code. (If the application itself had
been returning 404 on `/health`, that would go to the application team.)

## Prevention

- The patch only fixed the live object. The wrong value still lives in the file the
  Deployment was created from, so a redeploy from that file would bring the error back.
  The real fix belongs in the source (the manifest in git, or the Helm chart), and the
  deployment should always come from that single source and not from hand-written files.
- In our Helm chart the path is written once in the template, and the liveness and readiness
  probes use the same `/health`, so this mistake cannot happen there. The incident came from
  a hand-written manifest that bypassed the chart.
- Add a check after every deploy: `READY` must equal the desired count and `get endpoints`
  must not be empty, before telling the customer the service is up.
