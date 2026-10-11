# Incident playbook

Six faults, reproduced on purpose in a lab namespace and diagnosed with commands only.
Each note lists the evidence (real command output), the root cause, the fix, who to escalate
to, and how to prevent it. This page is the quick way in: find the symptom, then read the note.

## Find the fault from the symptom

| What `kubectl get pods` shows | Restarts | Logs | Likely fault | Note |
|---|---|---|---|---|
| `Running`, `READY 0/1` | 0 | normal, with `404` lines | Readiness probe asks the wrong address | [01](01-no-response-in-lab.md) |
| `CrashLoopBackOff` | climbing, each run lasts a few seconds | **error message** (`--previous`) | Wrong start command | [02](02-crashloop-wrong-start-command.md) |
| `ErrImagePull` / `ImagePullBackOff` | 0 | none, "waiting to start" | Image tag does not exist | [03](03-image-pull-wrong-tag.md) |
| `OOMKilled` / `CrashLoopBackOff` | climbing, each run lasts about a second | **empty**, exit code 137 | Memory limit too low | [04](04-oomkilled-memory-limit-too-low.md) |
| `Running`, `READY 1/1`, but connections are refused | 0 | normal | Service selector matches no pod | [05](05-service-selector-mismatch.md) |
| `ContainerCreating` that does not move | 0 | none, "waiting to start" | A required ConfigMap is missing | [06](06-missing-configmap-containercreating.md) |

## The method (same order every time)

1. **Look.** `kubectl get pods`: status, ready count, restarts, age. Check `get endpoints`
   when pods are Ready but the customer still cannot connect.
2. **Why.** `kubectl describe pod <name>`, read the **Events** at the bottom and the
   `State` / `Last State` block (reason and exit code).
3. **Application.** `kubectl logs <name>`; for a crashing pod add `--previous`.
4. **Connection.** `kubectl get endpoints <service>`, then compare `describe service`
   (Selector) with `get pods --show-labels`.
5. **Think.** Separate the **symptom** (what you see) from the **root cause** (why).
   Name one cause, backed by evidence from two independent places.
6. **Verify the way the customer uses it**, not only that the pod is Ready.

## Two rules that kept proving true

- **Events say what happened, the log says why.** Pull and mount failures are only in the Events
  (nothing started, so there is no log). Crashes are only explained by the log.
- **Exit code tells who stopped it.** `1` means the program failed by itself and printed a
  reason. `137` means it was killed from outside (out of memory) and printed nothing.

## When to fix and when to escalate

| Situation | Who |
|---|---|
| A wrong value in a deployment I own (probe path, tag, command, limit, selector) | Fix it myself |
| A missing input the customer must provide (the airport definition) | Wait for the customer, tell them exactly what is missing |
| The application misbehaves although its settings are right (it returns 404 on `/health`, memory grows for hours) | Application team |
| The image is correct but the registry refuses it, or the cluster has no room or denies access | Platform / registry team |

## The prevention that appears in every note

All six faults came from **hand-written manifests**, never from the Helm chart. Keep each
value in one place (the chart), render and check it before deploying, and after every deploy
check three things: `READY` equals the desired count, `get endpoints` is not empty, and the
service answers through its own Service name.
