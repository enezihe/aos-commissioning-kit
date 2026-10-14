# Incident (AI draft): flight-service in lab

> **AI draft, verify before use.** Written by a model from collected evidence. Read every claim, run the verification steps yourself, and correct it before filing.

**Date / target:** 2026-10-14 13:31, context=kind-aos-dev namespace=lab
**Customer report:** customers cannot reach the flight list

## Symptom (what the customer sees)

Customers cannot reach the flight list through the flight-service Service. Both pods are Running and Ready (1/1) and answer /health with 200 OK, but the Service has no endpoints.

## Evidence (exact quotes, each checked against what was collected)

- **E5** (`kubectl -n lab describe service flight-service`) [verified]
  > Selector:                 app=flight-svc
- **E2** (`kubectl -n lab get pods --show-labels`) [verified]
  > app=flight-service,pod-template-hash=79b8f4b6db
- **E6** (`kubectl -n lab get endpointslices -l kubernetes.io/service-name=flight-service (with ready state)`) [verified]
  > no endpoints at all
- **E7** (`kubectl -n lab get deployment flight-service (container settings, env values never collected)`) [verified]
  >   app: flight-service
- **E1** (`kubectl -n lab get pods -o wide`) [verified]
  > flight-service-79b8f4b6db-2tjwl   1/1     Running   0          5m6s   10.244.0.11   aos-dev-control-plane   <none>           <none>
- **E4** (`kubectl -n lab logs flight-service-79b8f4b6db-2tjwl --tail=30`) [verified]
  > INFO:     10.244.0.1:45058 - "GET /health HTTP/1.1" 200 OK

## Root cause

The Service selector is app=flight-svc, but the pods carry the label app=flight-service. The selector matches no pods, so the Service has no endpoints and traffic sent to it reaches nothing.

*Category: service_selector. Confidence stated by the model: high.*

## Verify it yourself (read-only)

- `kubectl -n lab get service flight-service -o yaml`
- `kubectl -n lab get pods -l app=flight-svc`
- `kubectl -n lab get pods -l app=flight-service`
- `kubectl -n lab get endpointslices -l kubernetes.io/service-name=flight-service -o wide`
- `kubectl -n lab describe service flight-service`

## Fix (suggested, nothing was changed)

Change the selector in the flight-service Service manifest from app=flight-svc to app=flight-service, so it matches the pod labels set by the Deployment. Reapply it through the normal deployment process. The Service should then list both pod IPs (10.244.0.11 and 10.244.0.12 on port 8000) as endpoints.

## Escalate to

**self**: The application is healthy: pods are Ready and /health returns 200. The fault is a wrong label value in the Service settings, which the implementation engineer owns.

## Prevention

Define the app label once, for example in a Helm value or a Kustomize commonLabels entry, and use it for both the Deployment and the Service. Add a post-deploy check that fails when a Service has zero ready endpoints.

## About this draft

- Model: `claude-opus-5-5`
- Tokens: 4734 in, 796 out, about $0.035
- Quote check: all quotes found in the evidence
- Request id: `req_011Cg2XZ7DYbCwQjkCGaoMiG`
