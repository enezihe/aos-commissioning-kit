# ADR 0001: Package the service as a Helm chart, keep plain manifests as a reference

- **Status:** Accepted
- **Date:** 2026-11-11

## Context
The flight service runs on two platforms, a local kind cluster and the Red Hat OpenShift Developer
Sandbox. They need the same Deployment and Service, but OpenShift also needs a Route, and image,
replica count and resource limits differ per environment.

## Decision
Use a Helm chart (`helm/flight-service`) with `values.yaml` for kind and `values-openshift.yaml` for
OpenShift. Keep the plain manifests in `k8s/` as the simplest reference of what the chart renders.

## Alternatives considered
- **Plain manifests only:** simplest to read, but each environment needs its own copy of every file,
  and a change has to be made twice.
- **Kustomize overlays:** also removes the duplication and needs no template language, but the chart
  gives versioned releases with `helm upgrade` and `helm rollback`, which the project practises.

## Consequences
- One chart serves both platforms; the differences are a few values.
- Releases can be upgraded and rolled back, and `helm lint` runs in CI for both values files.
- Contributors need to read Go templates. The plain manifests in `k8s/` are kept to lower that cost.
