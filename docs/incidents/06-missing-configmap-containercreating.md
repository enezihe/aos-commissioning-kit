# Incident: Flight service in lab is stuck in ContainerCreating (missing ConfigMap)

**Date / environment:** 2026-10-11, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

The new deployment never starts. Both pods stay in `ContainerCreating`, `READY 0/1`,
`RESTARTS 0`, and do not move forward after more than 40 seconds.

This is not a crash and not an image problem: the container was never even created.

## Evidence (the commands I ran and the exact lines that proved it)

1. The pod waits before the container exists, and the Events say what it is waiting for:

   ```
   $ kubectl -n lab describe pod flight-service-75b5dbb6c6-456p6
       State:          Waiting
         Reason:       ContainerCreating
   Events:
     Warning  FailedMount  9s (x7 over 40s)  kubelet
              MountVolume.SetUp failed for volume "airport-config" : configmap "airport-config" not found
   ```

   The pod wants to mount a volume built from the ConfigMap `airport-config`, and the
   kubelet cannot find it. It keeps retrying (`x7`).

2. The log cannot help, because nothing started:

   ```
   $ kubectl -n lab logs flight-service-75b5dbb6c6-456p6
   Error from server (BadRequest): container "flight-service" in pod ... is waiting to start: ContainerCreating
   ```

3. The ConfigMap really is missing in this namespace:

   ```
   $ kubectl -n lab get configmap
   NAME               DATA   AGE
   kube-root-ca.crt   1      41s
   ```

   Only Kubernetes' own `kube-root-ca.crt` exists. `airport-config` was never uploaded to `lab`.

## Root cause

The Deployment mounts the ConfigMap `airport-config` as a required volume, but nobody uploaded
the airport config to the `lab` namespace. A ConfigMap must exist in the same namespace as the
pod that mounts it, so the kubelet cannot build the volume and the container is never created.
Nothing is wrong with the image, the application or the pod settings.

## Fix

Uploaded the customer's airport config to the `lab` namespace with our tool (validated first,
dry-run default, then applied):

```
$ aos-config upload config/airport.yaml -n lab --context kind-aos-dev --apply --yes
VALID: ../../config/airport.yaml
Target: context=kind-aos-dev namespace=lab
12 added, 0 removed, 0 changed - first install (nothing deployed yet)
UPLOADED: version 1 is now live in context=kind-aos-dev namespace=lab
```

The kubelet retried the mount by itself. About 30 seconds later the same two pods (no restart,
`RESTARTS 0`) were `1/1 Running`.

Checked the result beyond "it is running", because the point of the config is that it is used:

- The file is inside the pod (`/etc/aos/airport.yaml`, first lines shown).
- From inside the cluster, through the Service name: gate `A1` for a TK flight was accepted
  (201) and gate `Z9` was rejected (`422 unknown gate Z9`), so the service reads and enforces
  the uploaded config.

## Escalate to

Nobody for the repair itself: I own the deployment and I had the config. It depends on who
holds the airport definition: if the **customer** has not sent it yet, this is a waiting
item for the customer, not a technical fault. It would go to the **platform team** if the
ConfigMap existed in the right namespace and the mount still failed (a cluster or permission
problem).

## Prevention

- Our Helm chart marks this mount `optional: true`, so pods start even when no config was
  uploaded yet. The service then simply skips gate checks. This incident came from a
  hand-written manifest that made the mount required.
- Put "upload the config to this namespace" into the deployment runbook, before the
  deployment step, and check it with `aos-config history -n <namespace>`.
- Decide on purpose whether a missing config should stop the service (required mount) or
  let it start without checks (optional mount). Here an unchecked start was judged safer than
  no service.
- Reading tip: `ContainerCreating` that does not move, plus `FailedMount` in the Events, means
  "something the pod needs is missing" (a ConfigMap, a Secret or a volume). Read the name in
  the message, then check that it exists in the same namespace.
