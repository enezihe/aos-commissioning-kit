# Incident: Pods stuck in CreateContainerConfigError (missing database Secret)

**Date / environment:** 2026-11-11, kind-aos-dev, namespace `pgdemo`

## Symptom (what the customer sees)

After `helm install`, no pod becomes ready. The database pod and both flight-service pods show
`CreateContainerConfigError`, `READY 0/1`, `RESTARTS 0`, and stay that way.

This is not `ContainerCreating` (incident 06) and not a crash: Kubernetes could not even build the
container's configuration.

## Evidence (the commands I ran and the exact lines that proved it)

1. The status names the stage that failed:

   ```
   $ kubectl -n pgdemo get pods
   NAME                              READY   STATUS                       RESTARTS   AGE
   flight-db-0                       0/1     CreateContainerConfigError   0          25s
   flight-service-7784cfd5fc-rlpzh   0/1     CreateContainerConfigError   0          25s
   flight-service-7784cfd5fc-t6lm5   0/1     CreateContainerConfigError   0          25s
   ```

2. The Events say what is missing:

   ```
   $ kubectl -n pgdemo describe pod flight-service-7784cfd5fc-rlpzh
       State:          Waiting
         Reason:       CreateContainerConfigError
   Events:
     Warning  Failed  14s (x3 over 25s)  kubelet  Error: secret "flight-db" not found
   ```

   The image was pulled fine (`Pulled ... already present`). The failure is after that, when the
   kubelet resolves the environment variables.

3. The log cannot help, because nothing started:

   ```
   $ kubectl -n pgdemo logs flight-service-7784cfd5fc-rlpzh
   Error from server (BadRequest): container "flight-service" in pod ... is waiting to start: CreateContainerConfigError
   ```

4. The Secret really is missing. Only Helm's own release record exists:

   ```
   $ kubectl -n pgdemo get secret
   NAME                           TYPE                 DATA   AGE
   sh.helm.release.v1.flight.v1   helm.sh/release.v1   1      31s
   ```

## Root cause

The chart reads `DB_USER`, `DB_PASSWORD` and `DB_NAME` (and the database pod reads its own login) from
the Secret `flight-db` with `secretKeyRef`. A Secret must exist in the same namespace as the pod. It
was never created, so the kubelet could not build the environment and refused to create the
containers. The chart, the image and the application are fine.

## Fix

Created the Secret with a generated password (the value is not shown in any output):

```
$ kubectl -n pgdemo create secret generic flight-db \
    --from-literal=POSTGRES_USER=flight --from-literal=POSTGRES_DB=flight \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 16)"
secret/flight-db created
```

The kubelet retried by itself. Within 45 seconds the same three pods (no restart, `RESTARTS 0`) were
`1/1 Running`.

Checked the result the way the customer uses it, not only that the pods are Ready:

- A flight created through one pod was returned by the other pod.
- Deleting both service pods and then the database pod lost no data.
- `aos-ops gate -n pgdemo` passed: 2 of 2 pods ready, 2 ready endpoints, `/health` answered through the
  Service name.

## Escalate to

Nobody for the repair itself: I own the deployment and can create the Secret. If the Secret must hold a
password chosen by the customer or the platform team, wait for them to provide it. It would go to the
**platform team** if the Secret existed in the right namespace and the pods still failed (a permission
or cluster problem).

## Prevention

- The chart refuses to run with a guessed login on purpose: a missing Secret stops the pods instead of
  starting them with a default password. Keep it that way.
- Put "create the `flight-db` Secret" into the deployment runbook before `helm install`, next to
  "upload the airport config" (incident 06). The README install steps are in that order.
- Reading tip: `CreateContainerConfigError` means the container's settings could not be built. Read the
  Events for the name (a Secret or a ConfigMap key), then check it exists in the same namespace.
  `ContainerCreating` that does not move points at a volume instead.
- A Secret that exists but lacks a key gives a different message (`couldn't find key POSTGRES_PASSWORD
  in Secret`), so read the whole line.
