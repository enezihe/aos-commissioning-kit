# Incident: Flight service in lab keeps restarting (OOMKilled)

**Date / environment:** 2026-10-11, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

The service does not stay up. `kubectl get pods` shows `READY 0/1`, the status flips between
`Running`, `OOMKilled` and `CrashLoopBackOff`, and `RESTARTS` climbs within seconds
(3 restarts in the first 45 seconds).

## Evidence (the commands I ran and the exact lines that proved it)

1. The container did not exit by itself, it was killed from outside:

   ```
   $ kubectl -n lab describe pod flight-service-6fcd47b5c6-nf7nc
       Last State:     Terminated
         Reason:       OOMKilled
         Exit Code:    137
         Started:      Sun, 11 Oct 2026 09:36:23 -0400
         Finished:     Sun, 11 Oct 2026 09:36:24 -0400
   ```

   `OOMKilled` means "killed for running out of memory". Exit code 137 is 128 + 9: the
   operating system sent SIGKILL. The container lived about one second.

2. The log is empty, which is itself a finding:

   ```
   $ kubectl -n lab logs flight-service-6fcd47b5c6-nf7nc --previous
   (no output)
   ```

   The program was killed before it could write anything. This is different from a normal
   crash, where the application prints its own error (see incident 02).

3. The limit the Deployment sets, against what the service really needs:

   ```
   $ kubectl -n lab get deployment flight-service -o jsonpath='{.spec.template.spec.containers[0].resources}'
   {"limits":{"cpu":"200m","memory":"20Mi"},"requests":{"cpu":"50m","memory":"16Mi"}}

   $ docker run -d --name memtest flight-service:0.2 && docker stats --no-stream memtest
   memory in use: 59.68MiB / 7.654GiB
   ```

   The service needs about 60 MiB right after it starts (a little more under use). The limit
   is 20 MiB, so it is killed while it is still starting.

## Root cause

The memory limit in the Deployment is 20 MiB (request 16 MiB), but the service needs about
60 MiB just to start. The kernel kills the container as soon as it passes the limit, so it
never becomes ready. The application is not at fault: the resources were sized by guess, not
by measurement.

## Fix

Set the memory request and limit to the values our Helm chart uses (64 MiB and 128 MiB), which
leave room above the measured 60 to 76 MiB:

```
$ kubectl -n lab patch deployment flight-service --type=json -p '[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"64Mi"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"128Mi"}]'
deployment "flight-service" successfully rolled out
```

Checked the result:

- Two new pods at `1/1 Running` with `restarts=0` and no `lastTerminated` reason. The old pod
  that was killed shows `OOMKilled` and is `Terminating`.
- `kubectl -n lab get endpoints flight-service` lists `10.244.0.23:8000` and `10.244.0.24:8000`.
- Through the Service name (the customer's path), `urlopen("http://flight-service/health")`
  returned `{"status":"ok"}`.

## Escalate to

Nobody for this repair: sizing the limit is part of what I deploy, and I measured the need
before changing it. It would go to the **application team** if memory kept growing over
hours or days (a leak, where a bigger limit only delays the kill), and to the **platform
team** if the cluster had no room left to give the pods the memory they need.

## Prevention

- Size limits from measurements (`docker stats` here, `kubectl top pod` where metrics are
  available), and keep headroom of about twice the normal use.
- Keep the resource values in one place: our chart's `values.yaml`. Hand-written manifests
  with their own numbers are how a 20 MiB limit appears.
- Watch for `RESTARTS` and for `lastState.terminated.reason: OOMKilled` after every deploy.
- Reading tip: exit code 137 plus an empty log means "killed from outside", not "crashed".
  Exit code 1 plus an error line in the log means the program failed by itself.
