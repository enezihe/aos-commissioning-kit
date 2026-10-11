# Incident: Flight service in lab never starts (ImagePullBackOff)

**Date / environment:** 2026-10-11, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

The new deployment does not come up. `kubectl get pods` shows both pods stuck in
`ErrImagePull` (and a moment later `ImagePullBackOff`), `READY 0/1`, `RESTARTS 0`.

`RESTARTS 0` is the first clue: the container never started, so it cannot have crashed.

## Evidence (the commands I ran and the exact lines that proved it)

1. The container is waiting, it did not run:

   ```
   $ kubectl -n lab describe pod flight-service-7b95547d7-9p9sx
       State:          Waiting
         Reason:       ErrImagePull
   Events:
     Normal   Pulling  Pulling image "flight-service:0.9"
     Warning  Failed   Failed to pull image "flight-service:0.9": ... failed to resolve reference
                       "docker.io/library/flight-service:0.9": pull access denied, repository does
                       not exist or may require authorization ...
     Warning  Failed   Error: ImagePullBackOff
   ```

   The image name has no registry, so it is looked up on Docker Hub (`docker.io/library/...`)
   and is not found there.

2. The log has nothing to say, which is also a finding:

   ```
   $ kubectl -n lab logs flight-service-7b95547d7-9p9sx
   Error from server (BadRequest): container "flight-service" in pod ... is waiting to start: image can't be pulled
   ```

   There is no application log because the application never started. The answer is in the
   Events, not in the log.

3. Which tags really exist where the pod runs:

   ```
   $ docker exec aos-dev-control-plane crictl images | grep flight-service
   docker.io/library/flight-service:0.1
   docker.io/library/flight-service:0.2
   ```

   The Deployment asks for `0.9`. Only `0.1` and `0.2` exist.

## Root cause

The Deployment asks for the image tag `flight-service:0.9`, which does not exist. The node
only has `0.1` and `0.2`, and the name carries no registry, so the lookup on Docker Hub fails.
The application and the cluster are fine. The tag is wrong.

## Fix

Pointed the Deployment at the tag that exists:

```
$ kubectl -n lab set image deployment/flight-service flight-service=flight-service:0.2
deployment "flight-service" successfully rolled out
```

Checked the result:

- Two new pods at `1/1 Running`; the old failing pod is `Terminating`.
- `kubectl -n lab get endpoints flight-service` lists `10.244.0.19:8000` and `10.244.0.20:8000`.
- Through the Service name (the customer's path), `urlopen("http://flight-service/health")`
  returned `{"status":"ok"}`.

## Escalate to

Nobody here: a wrong tag in a deployment I own. It would go to the **platform / registry team**
if the tag was correct but the registry refused the pull (a login or permission problem, which
shows up as "unauthorized" instead of "does not exist"), and to the **build team** if the tag
was expected to exist but the build never published it.

## Prevention

- Never type image tags by hand in a manifest. In our Helm chart the tag is one value
  (`image.tag`) in one file, so it can be reviewed and changed in one place.
- Make sure the image exists before deploying: in this lab `docker images` / `crictl images`,
  on OpenShift `oc get is`, in a real registry a `docker manifest inspect <image:tag>` check.
- Let the build pipeline write the tag into the deployment, so a tag that was never built
  cannot be deployed.
- Reading tip: `RESTARTS 0` plus `ErrImagePull` means "never started". Look at Events, not logs.
