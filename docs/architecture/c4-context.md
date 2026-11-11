# C4 level 1: system context

The kit sits between an engineer and a Kubernetes or OpenShift cluster that runs the Airport
Operational System (AOS) flight service for a customer.

```mermaid
flowchart TB
  ENG(["Implementation engineer<br/>validates config, deploys, runs the go-live gate"])
  ONCALL(["On-call engineer<br/>diagnoses faults"])
  CUST(["Customer / airline systems<br/>call /flights and /health"])

  KIT["AOS Commissioning Kit<br/>config tool, readiness gate, AI triage, flight service"]

  K8S[["Kubernetes (kind) or<br/>Red Hat OpenShift Developer Sandbox"]]
  CLAUDE[["Claude API<br/>drafts a diagnosis from cleaned evidence"]]

  ENG -->|"validate, upload, gate"| KIT
  ONCALL -->|"triage, incident notes"| KIT
  CUST -->|"HTTP"| KIT
  KIT -->|"deploys to and reads from"| K8S
  KIT -.->|"cleaned evidence, only with --send"| CLAUDE
```

## Notes
- The dashed arrow is optional. Nothing leaves the engineer's computer unless `--send` is given
  ([ADR 0004](adr/0004-ai-triage-with-quote-verification.md)).
- The kit reads from the cluster with read-only commands
  ([ADR 0003](adr/0003-read-only-operations-tooling.md)).
