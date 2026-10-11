# Incident: Flight service in lab never starts (CrashLoopBackOff)

**Date / environment:** 2026-10-10, kind-aos-dev, namespace `lab`

## Symptom (what the customer sees)

The customer says the service does not come up after the new deployment and the pods keep
failing.

`kubectl get pods` shows `CrashLoopBackOff` on both pods, `READY 0/1`, and `RESTARTS` going up
(5 restarts in about five minutes). A pod never reaches Ready.

## Evidence (the commands I ran and the exact lines that proved it)

1. The pod starts and dies right away. The cause is not an image problem:

   ```
   $ kubectl -n lab describe pod flight-service-6d77756fd6-bp55c
       Last State:     Terminated
         Reason:       Error
         Exit Code:    1
         Started:      Sat, 10 Oct 2026 21:59:57 -0400
         Finished:     Sat, 10 Oct 2026 22:00:00 -0400
   Events:
     Normal   Pulled   Container image "flight-service:0.2" already present on machine ...
     Normal   Started  Container started
     Warning  BackOff  Back-off restarting failed container flight-service ...
   ```

   The image is pulled and the container starts, so this is not `ImagePullBackOff`. It lives
   about three seconds and exits with code 1 (the program itself failed). Kubernetes only
   knows that it crashed. The Events do not say why.

2. The reason is in the application's own log:

   ```
   $ kubectl -n lab logs flight-service-6d77756fd6-bp55c --previous
   ERROR:    Error loading ASGI app. Attribute "application" not found in module "app.main".
   ```

3. Where the wrong name comes from (the command the container really runs, against what the
   image intends and what the code defines):

   ```
   $ kubectl -n lab get deployment flight-service -o jsonpath='{.spec.template.spec.containers[0].command}'
   ["uvicorn","app.main:application","--host","0.0.0.0","--port","8000"]

   $ docker inspect flight-service:0.2 --format '{{json .Config.Cmd}}'
   ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

   $ grep -n "^app" services/flight/app/main.py
   8:app = FastAPI(title="Flight Service")
   ```

## Root cause

The Deployment overrides the image's start command (`command:`) and names the application
object `application`. The code defines it as `app`, so uvicorn cannot load it and exits with
code 1 a few seconds after every start. The image and the application are fine. The override
in the Deployment is wrong.

## Fix

Removed the unnecessary override, so the container uses the image's own correct `CMD`:

```
$ kubectl -n lab patch deployment flight-service --type=json \
    -p '[{"op":"remove","path":"/spec/template/spec/containers/0/command"}]'
deployment "flight-service" successfully rolled out
```

Checked the result:

- Two new pods at `1/1 Running`, and `kubectl -n lab get endpoints flight-service` lists
  `10.244.0.15:8000` and `10.244.0.16:8000`.
- Through the Service name (the customer's path), `urlopen("http://flight-service/health")`
  returned `{"status":"ok"}`.
- The new pod's log shows the normal startup lines (`Application startup complete`).

## Escalate to

Nobody for the repair: the start command is part of the deployment I own, and the application
code is correct. Worth asking whoever wrote this manifest why `command:` was set at all, so
the mistake is not copied into other environments.

## Prevention

- Do not override `command:` unless there is a real reason. The image already knows how to
  start itself, and our Helm chart does not set it, so the mistake cannot appear there.
- Fix the source, not only the live object: this manifest was hand-written, so the wrong
  command still sits in that file until it is corrected or deleted.
- Before deploying, run the exact start command once outside the cluster
  (`docker run --rm flight-service:0.2`) or run the pre-deploy smoke test. A start-up error
  like this shows up in seconds.
- Reading tip: `kubectl logs --previous` shows the attempt that just died. For a pod in
  `CrashLoopBackOff`, the Events say that it crashed and the log says why.
