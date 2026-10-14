"""Stage-gate readiness check: is this deployment fit to hand over to the customer?

Two separate steps:
- collect(): asks the cluster (read-only) and returns a Snapshot of plain data
- evaluate(): applies the criteria to a Snapshot and returns the results

Keeping them apart means every criterion can be tested with made-up data, no cluster needed.
No artificial intelligence here: each criterion is a fixed, explainable rule.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aosops.kube import Kube, KubeError

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
LIVE_CONFIG = "airport-config"
CONFIG_KEY = "airport.yaml"


@dataclass
class Options:
    deployment: str = "flight-service"
    service: str = "flight-service"
    probe_path: str = "/health"
    probe: bool = True
    max_restarts: int = 0
    require_config: bool = False
    expected_config: Optional[dict] = None      # parsed airport.yaml the live config must equal


@dataclass
class Snapshot:
    namespace_exists: bool = True
    deployment: Optional[dict] = None
    pods: List[dict] = field(default_factory=list)
    service: Optional[dict] = None
    ready_endpoints: Optional[int] = None       # None = could not be read
    live_config: Optional[dict] = None
    probe: Optional[Tuple[bool, str]] = None    # None = not attempted


@dataclass
class Result:
    status: str
    name: str
    detail: str


# --------------------------------------------------------------------------- collect
def collect(kube: Kube, opts: Options) -> Snapshot:
    snap = Snapshot()
    snap.namespace_exists = kube.get_json_or_none("namespace", kube.target.namespace) is not None
    if not snap.namespace_exists:
        return snap

    snap.deployment = kube.get_json_or_none("deployment", opts.deployment)
    if snap.deployment:
        labels = snap.deployment["spec"]["selector"].get("matchLabels", {})
        selector = ",".join(f"{k}={v}" for k, v in labels.items())
        snap.pods = kube.get_json("pods", "-l", selector)["items"] if selector else []

    snap.service = kube.get_json_or_none("service", opts.service)
    if snap.service:
        slices = kube.get_json("endpointslices", "-l", f"kubernetes.io/service-name={opts.service}")["items"]
        snap.ready_endpoints = sum(
            1 for s in slices for e in s.get("endpoints") or []
            if (e.get("conditions") or {}).get("ready") is not False
        )

    snap.live_config = kube.get_json_or_none("configmap", LIVE_CONFIG)

    if opts.probe and snap.service:
        ready = [p for p in snap.pods if _pod_ready(p)]
        if ready:
            snap.probe = _probe(kube, ready[0]["metadata"]["name"], opts)
    return snap


def _probe(kube: Kube, pod: str, opts: Options) -> Tuple[bool, str]:
    """Ask the Service by its own name, from inside the cluster, the way a customer's client would."""
    code = (
        "import urllib.request\n"
        f"r = urllib.request.urlopen('http://{opts.service}{opts.probe_path}', timeout=5)\n"
        "print(r.status)"
    )
    try:
        out = kube.run(["exec", pod, "--", "python", "-c", code], timeout=30).strip()
    except KubeError as exc:
        text = str(exc)
        if "Connection refused" in text:
            return False, "connection refused"
        if "not found" in text and "python" in text:
            return False, "cannot probe: no python in the image"
        return False, text.splitlines()[-1][:120] if text else "probe failed"
    return out == "200", f"HTTP {out}"


# --------------------------------------------------------------------------- helpers
def _pod_ready(pod: dict) -> bool:
    return any(c.get("type") == "Ready" and c.get("status") == "True"
               for c in pod.get("status", {}).get("conditions", []))


def _pod_reason(pod: dict) -> str:
    """The short reason a pod is not ready, in the words kubectl shows."""
    for cs in pod.get("status", {}).get("containerStatuses", []) or []:
        waiting = (cs.get("state") or {}).get("waiting")
        if waiting and waiting.get("reason"):
            return waiting["reason"]
        last = (cs.get("lastState") or {}).get("terminated")
        if last and last.get("reason") and not cs.get("ready"):
            return f"{last['reason']} (exit {last.get('exitCode')})"
    if pod.get("status", {}).get("phase") == "Pending":
        return "Pending"
    return "Running but not Ready"


def _restarts(pod: dict) -> int:
    return sum(cs.get("restartCount", 0) for cs in pod.get("status", {}).get("containerStatuses", []) or [])


def _oom_killed(pod: dict) -> bool:
    return any(((cs.get("lastState") or {}).get("terminated") or {}).get("reason") == "OOMKilled"
               for cs in pod.get("status", {}).get("containerStatuses", []) or [])


# --------------------------------------------------------------------------- evaluate
def evaluate(snap: Snapshot, opts: Options) -> List[Result]:
    results: List[Result] = []
    add = lambda status, name, detail: results.append(Result(status, name, detail))

    if not snap.namespace_exists:
        add(FAIL, "namespace", "the namespace does not exist")
        return results
    add(PASS, "namespace", "exists")

    dep = snap.deployment
    if dep is None:
        add(FAIL, "deployment", f"'{opts.deployment}' was not found")
        return results
    desired = dep["spec"].get("replicas", 1)
    if desired == 0:
        add(WARN, "deployment", "scaled to 0 replicas (idle or switched off), nothing is serving")
    else:
        add(PASS, "deployment", f"'{opts.deployment}' wants {desired} replicas")

    # pods ready
    ready_pods = [p for p in snap.pods if _pod_ready(p)]
    if desired > 0:
        if len(ready_pods) >= desired:
            add(PASS, "pods ready", f"{len(ready_pods)} of {desired} are Ready")
        else:
            bad = [p for p in snap.pods if not _pod_ready(p)]
            why = "; ".join(sorted({_pod_reason(p) for p in bad})) or "no pods exist"
            add(FAIL, "pods ready", f"{len(ready_pods)} of {desired} are Ready ({why})")

    # restarts
    total = sum(_restarts(p) for p in snap.pods)
    if any(_oom_killed(p) for p in snap.pods):
        add(FAIL, "restarts", "a container was killed for running out of memory (OOMKilled)")
    elif total > opts.max_restarts:
        add(WARN, "restarts", f"{total} restart(s), allowed {opts.max_restarts}; read the logs with --previous")
    else:
        add(PASS, "restarts", f"{total} restart(s)")

    # settings that make a deployment easy to run and easy to diagnose
    container = (dep["spec"]["template"]["spec"].get("containers") or [{}])[0]
    if not container.get("readinessProbe"):
        add(WARN, "readiness probe", "none defined: traffic reaches the pod before it is ready")
    else:
        add(PASS, "readiness probe", "defined")
    limits = (container.get("resources") or {}).get("limits") or {}
    if "memory" not in limits or "cpu" not in limits:
        add(WARN, "resource limits", "cpu or memory limit missing: one pod can starve the others")
    else:
        add(PASS, "resource limits", f"cpu {limits['cpu']}, memory {limits['memory']}")
    if container.get("command") or container.get("args"):
        add(WARN, "start command", "the deployment overrides the image's own start command")

    # service
    svc = snap.service
    if svc is None:
        add(FAIL, "service", f"'{opts.service}' was not found")
    else:
        selector = svc.get("spec", {}).get("selector") or {}
        pod_labels = dep["spec"]["template"]["metadata"].get("labels", {})
        mismatched = {k: v for k, v in selector.items() if pod_labels.get(k) != v}
        if mismatched:
            asked = ",".join(f"{k}={v}" for k, v in selector.items())
            have = ",".join(f"{k}={v}" for k, v in pod_labels.items())
            add(FAIL, "service selector", f"selects '{asked}' but the pods carry '{have}'")
        else:
            add(PASS, "service selector", "matches the pod labels")

        if snap.ready_endpoints is None:
            add(WARN, "endpoints", "could not be read")
        elif snap.ready_endpoints == 0 and desired > 0:
            add(FAIL, "endpoints", "the service has no endpoints: it sends traffic nowhere")
        elif snap.ready_endpoints < len(ready_pods):
            add(WARN, "endpoints", f"{snap.ready_endpoints} endpoint(s) for {len(ready_pods)} ready pod(s)")
        else:
            add(PASS, "endpoints", f"{snap.ready_endpoints} ready endpoint(s)")

        # the customer's path
        if not opts.probe:
            pass
        elif snap.probe is None:
            add(WARN, "customer path", "not tested (no ready pod to ask from)")
        elif snap.probe[0]:
            add(PASS, "customer path", f"{opts.service}{opts.probe_path} answered through the Service name ({snap.probe[1]})")
        else:
            add(FAIL, "customer path", f"{opts.service}{opts.probe_path} did not answer through the Service name ({snap.probe[1]})")

    # config
    cfg = snap.live_config
    if cfg is None:
        add(FAIL if opts.require_config else WARN, "config",
            f"no live config ('{LIVE_CONFIG}') in this namespace; upload one with aos-config")
    else:
        version = (cfg["metadata"].get("labels") or {}).get("aos-config/version", "?")
        if opts.expected_config is None:
            add(PASS, "config", f"live config present (version {version})")
        else:
            try:
                live = yaml.safe_load(cfg.get("data", {}).get(CONFIG_KEY, ""))
            except yaml.YAMLError:
                live = None
            if live == opts.expected_config:
                add(PASS, "config", f"live config (version {version}) equals the expected file")
            else:
                add(FAIL, "config", f"live config (version {version}) differs from the expected file; run aos-config upload to see what changes")
    return results


def passed(results: List[Result]) -> bool:
    return all(r.status != FAIL for r in results)


def to_markdown(results: List[Result], target: Any, stamp: str) -> str:
    verdict = "PASSED" if passed(results) else "FAILED"
    fails = sum(r.status == FAIL for r in results)
    warns = sum(r.status == WARN for r in results)
    lines = [
        "# Readiness report",
        "",
        f"**Target:** {target}  ",
        f"**Date:** {stamp}  ",
        f"**Decision:** gate {verdict} ({fails} failed, {warns} warnings)",
        "",
        "| Result | Criterion | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {r.status} | {r.name} | {r.detail} |" for r in results]
    lines += ["", "A gate fails if any criterion fails. Warnings do not fail the gate but should be read and accepted."]
    return "\n".join(lines) + "\n"
