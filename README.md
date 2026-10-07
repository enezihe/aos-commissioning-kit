# AOS Commissioning Kit

Hands-on project: deploy, configure and troubleshoot a mini Airport
Operational System (AOS) on Kubernetes / OpenShift.

## Environment (Phase 0)

| Tool | Purpose |
|---|---|
| docker | run containers |
| kind | local Kubernetes cluster (`aos-dev`) |
| kubectl | manage the cluster |
| helm | package/deploy manifests |
| oc | OpenShift CLI (Phase 3) |

## Verify

    kind create cluster --name aos-dev
    kubectl get nodes    # STATUS must be Ready
