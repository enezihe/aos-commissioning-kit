# AOS Commissioning Kit

A hands-on project that practises the work of an implementation engineer: deploy, configure and
troubleshoot a small **Airport Operational System (AOS)** on Kubernetes and Red Hat OpenShift, check
that it is ready for go-live, and diagnose faults from logs and events.

The system is deliberately small (one flight service) so the focus stays on the engineering around it:
packaging, configuration, readiness checks, incident diagnosis and documentation.

```
config/airport.yaml ──► aos-config (validate, diff, upload, rollback)
                              │ ConfigMap airport-config (versioned)
                              ▼
services/flight (FastAPI) ──► Docker image ──► Helm chart ──► kind (local) / OpenShift Developer Sandbox
                                                                   │ read-only
                                                                   ▼
                                                  aos-ops: gate (go-live checks) and triage (AI draft)
```

## What is in the repo

| Path | What it is |
|---|---|
| `services/flight` | FastAPI flight service: list, create and update flights; checks gates against the mounted airport config (422 on a gate the airport does not allow); `/health` endpoint. Dockerfile and tests. |
| `k8s/` | Plain Kubernetes Deployment and Service with probes and resource limits. |
| `helm/flight-service` | Helm chart (`values.yaml` for kind, `values-openshift.yaml` with a Route for OpenShift). |
| `config/airport.yaml` | The "customer data" for a fictional airport: terminals, gates, carousels, airlines. |
| `tools/aos-config` | Python CLI that validates the config by field and cross rules, shows a semantic diff, uploads it as a versioned ConfigMap (dry run by default) and rolls back. [README](tools/aos-config/README.md) |
| `tools/aos-ops` | Read-only readiness gate, evidence collection with secret removal, and AI triage that drafts an incident note. [README](tools/aos-ops/README.md) |
| `docs/incidents` | Six faults reproduced on purpose and diagnosed with commands only, plus a playbook. [Playbook](docs/incidents/README.md) |
| `docs/presentation.html` | Slide deck that walks through the project. |

## Quick start (local)

Requirements: Docker, kind, kubectl, Helm, Python 3.

```bash
kind create cluster --name aos-dev
kubectl get nodes                                    # STATUS must be Ready

# 1. Build the image and load it into the cluster
docker build -t flight-service:0.2 services/flight
kind load docker-image flight-service:0.2 --name aos-dev

# 2. Upload the airport config first: the chart mounts the ConfigMap airport-config,
#    and the pods stay in ContainerCreating without it (see docs/incidents/06)
cd tools/aos-config
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m aosconfig validate ../../config/airport.yaml
python -m aosconfig upload ../../config/airport.yaml -n default --apply
cd ../..

# 3. Install the chart and check readiness
helm install flight helm/flight-service
cd tools/aos-ops
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m aosops gate -n default
```

## Phases

| Phase | Result |
|---|---|
| 0. Environment | docker, kind, kubectl, helm, oc |
| 1. Flight service | FastAPI service and container image |
| 2. Kubernetes and Helm | Manifests with probes and limits; Helm chart; upgrade and rollback practised |
| 3. OpenShift | Deployed to the Red Hat Developer Sandbox with a Route and an OpenShift values file |
| 4. Config tool | `aos-config` with rules, diff, versions and rollback; the service validates gates from the live config |
| 5. Broken deployments | Six faults diagnosed from evidence; incident notes and a playbook |
| 6. Readiness and triage | `aos-ops gate` (fixed rules) and `aos-ops triage` (AI draft with quote verification) |
| 7. Documentation | This README, the per-tool READMEs and the incident playbook |

## Design choices worth knowing

- **Read-only operations tooling.** `aos-ops` refuses every kubectl verb except `get`, `describe`,
  `logs` and `exec`. Changes are suggested, never made.
- **Dry run first.** `aos-config` and `aos-ops triage` print the target and what would happen, and do
  nothing until `--apply` or `--send` is given.
- **AI is a draft, not an authority.** Evidence is cleaned of secrets before it leaves the computer, the
  model must answer in a fixed shape with exact quotes, and every quote is checked against the evidence.
  A draft with an unverifiable quote is marked "do not trust".
- **Known limitation.** The flight service keeps its data in memory, so replicas do not share flights.
  This is kept on purpose to show why state must live outside the pod; a database is the next step.

## Tests

```bash
cd services/flight   && python -m pytest
cd tools/aos-config  && python -m pytest
cd tools/aos-ops     && python -m pytest
```
