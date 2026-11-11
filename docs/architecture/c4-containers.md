# C4 level 2: containers

What runs on the engineer's laptop and what runs in the cluster.

```mermaid
flowchart LR
  subgraph Laptop["Engineer's laptop"]
    CFG[/"config/airport.yaml"/]
    CONFIGCLI["aos-config<br/>Python, Typer<br/>validate, diff, upload, rollback"]
    OPSCLI["aos-ops<br/>Python, Typer<br/>gate, triage"]
  end

  subgraph Cluster["Kubernetes (kind) / OpenShift"]
    CM[("ConfigMap airport-config<br/>live version")]
    ARCH[("ConfigMaps airport-config-vN<br/>archive of every version")]
    SVC["Service / Route"]
    POD["flight-service x2<br/>Python, FastAPI<br/>probes, resource limits"]
    SVC --> POD
    CM -. "mounted at /etc/aos" .-> POD
  end

  HELM["Helm chart<br/>helm/flight-service"] --> POD
  CFG --> CONFIGCLI
  CONFIGCLI -->|"upload (dry run first)"| CM
  CONFIGCLI --> ARCH
  OPSCLI -->|"get, describe, logs, exec"| Cluster
  OPSCLI -.->|"cleaned evidence, only with --send"| CLAUDE[["Claude API"]]
  CUSTOMER(["Customer / airline systems"]) -->|"/flights, /health"| SVC
```

## Containers

| Container | Technology | Responsibility |
|---|---|---|
| `aos-config` | Python, Typer, Pydantic | Checks the airport file by field and cross rules, shows a semantic diff, uploads a numbered version, rolls back. Dry run by default. |
| `aos-ops` | Python, Typer | Read-only readiness gate; collects evidence, removes secrets, asks for a diagnosis draft and verifies its quotes. |
| `flight-service` | Python, FastAPI, Docker | Lists, creates and updates flights; rejects a gate the airport config does not allow (HTTP 422). Keeps data in memory. |
| `airport-config` | ConfigMap | The live airport file the service reads at `/etc/aos/airport.yaml`. |
| `airport-config-vN` | ConfigMaps | One archive copy per uploaded version, never deleted. |
| Helm chart | Helm | Deployment, Service and (OpenShift only) Route, with values per environment. |

## Known limitation
The flight service keeps data in memory, so replicas do not share flights. A database is on the
roadmap (issue #2).
