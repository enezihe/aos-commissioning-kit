"""Collect the same evidence an engineer would collect by hand, read-only, and clean it.

Each item gets an id (E1, E2, ...) so a diagnosis can point at it. Environment variable
values are never collected (only their names), and everything goes through redact().
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Counter as CounterType, List, Optional

import yaml

from aosops.kube import Kube, KubeError
from aosops.redact import redact

MAX_CHARS = 6000


@dataclass
class Evidence:
    id: str
    command: str
    text: str
    redactions: CounterType = field(default_factory=Counter)
    truncated: bool = False


def _keep_tail(text: str, limit: int):
    if len(text) <= limit:
        return text, False
    return "[... earlier output cut ...]\n" + text[-limit:], True


def _trim_describe(text: str) -> str:
    """Keep what matters in `describe pod`: the container block and the events. Hide env values."""
    lines = text.splitlines()
    out, section, in_env = [], None, False
    for line in lines:
        if line.startswith("Containers:"):
            section = "containers"
        elif line.startswith("Conditions:"):
            section = None
        elif line.startswith("Events:"):
            section = "events"
        if section is None:
            continue
        if section == "containers":
            stripped = line.strip()
            if stripped.startswith("Environment:"):
                in_env = True
                out.append(line)
                continue
            if in_env and stripped.startswith("Mounts:"):
                in_env = False
            if in_env and ":" in stripped:
                name = stripped.split(":", 1)[0]
                out.append(f"      {name}: <hidden>")
                continue
            if stripped.startswith(("Container ID:", "Image ID:", "Host Port:")):
                continue
        out.append(line)
    return "\n".join(out)


def _trim_service(text: str) -> str:
    keep = ("Name:", "Namespace:", "Selector:", "Type:", "Port:", "TargetPort:", "Endpoints:")
    return "\n".join(l for l in text.splitlines() if l.startswith(keep))


def _container_spec(dep: dict) -> str:
    """The deployment's container settings as YAML, with environment names only."""
    spec = dep["spec"]["template"]["spec"]
    container = (spec.get("containers") or [{}])[0]
    view = {k: container[k] for k in
            ("image", "command", "args", "ports", "readinessProbe", "livenessProbe", "resources", "volumeMounts")
            if k in container}
    if container.get("env"):
        view["env_names"] = [e.get("name") for e in container["env"]]
    view["replicas"] = dep["spec"].get("replicas")
    view["pod_labels"] = dep["spec"]["template"]["metadata"].get("labels", {})
    view["selector"] = dep["spec"]["selector"].get("matchLabels", {})
    volumes = []
    for v in spec.get("volumes") or []:
        kind = next((k for k in v if k != "name"), "?")
        volumes.append({"name": v.get("name"), kind: {k: val for k, val in (v.get(kind) or {}).items() if k in ("name", "optional")}})
    if volumes:
        view["volumes"] = volumes
    return yaml.safe_dump(view, sort_keys=False)


def _endpoints_view(slices: dict) -> str:
    """List every address with its ready state. The plain table lists addresses that are NOT ready
    too, which reads as "the service has endpoints" and misleads."""
    lines, ready = [], 0
    for s in slices.get("items", []):
        for e in s.get("endpoints") or []:
            state = (e.get("conditions") or {}).get("ready")
            label = "unknown" if state is None else str(state).lower()
            ready += state is not False
            target = (e.get("targetRef") or {}).get("name", "")
            lines.append(f"{', '.join(e.get('addresses', []))}  ready={label}  {target}".rstrip())
    if not lines:
        return "no endpoints at all"
    return f"{ready} of {len(lines)} endpoint(s) are ready (traffic is only sent to ready ones)\n" + "\n".join(lines)


def _ready(pod: dict) -> bool:
    return any(c.get("type") == "Ready" and c.get("status") == "True"
               for c in pod.get("status", {}).get("conditions", []))


def collect_evidence(kube: Kube, deployment: str = "flight-service", service: str = "flight-service",
                     tail: int = 30, max_chars: int = MAX_CHARS) -> List[Evidence]:
    ns = kube.target.namespace
    items: List[Evidence] = []

    def add(command: str, produce: Callable[[], str]) -> None:
        try:
            text = produce()
        except KubeError as exc:
            text = f"(command failed) {exc}"
        text, counts = redact(text.rstrip() or "(no output)")
        text, cut = _keep_tail(text, max_chars)
        items.append(Evidence(f"E{len(items) + 1}", f"kubectl -n {ns} {command}", text, counts, cut))

    dep = kube.get_json_or_none("deployment", deployment)
    selector = ",".join(f"{k}={v}" for k, v in dep["spec"]["selector"].get("matchLabels", {}).items()) if dep else ""
    pods = kube.get_json("pods", *(["-l", selector] if selector else []))["items"]
    pod: Optional[dict] = next((p for p in pods if not _ready(p)), pods[0] if pods else None)
    name = pod["metadata"]["name"] if pod else None
    restarts = sum(cs.get("restartCount", 0) for cs in (pod or {}).get("status", {}).get("containerStatuses", []) or [])

    add("get pods -o wide", lambda: kube.run(["get", "pods", "-o", "wide"]))
    add("get pods --show-labels", lambda: kube.run(["get", "pods", "--show-labels"]))
    if name:
        add(f"describe pod {name}", lambda: _trim_describe(kube.run(["describe", "pod", name])))
        add(f"logs {name} --tail={tail}", lambda: kube.run(["logs", name, f"--tail={tail}"]))
        if restarts:
            add(f"logs {name} --previous --tail={tail}", lambda: kube.run(["logs", name, "--previous", f"--tail={tail}"]))
    add(f"describe service {service}", lambda: _trim_service(kube.run(["describe", "service", service])))
    add(f"get endpointslices -l kubernetes.io/service-name={service} (with ready state)",
        lambda: _endpoints_view(kube.get_json("endpointslices", "-l", f"kubernetes.io/service-name={service}")))
    add(f"get deployment {deployment} (container settings, env values never collected)",
        lambda: _container_spec(dep) if dep else f"deployment '{deployment}' was not found")
    add("get configmap", lambda: kube.run(["get", "configmap"]))
    add("get events --sort-by=.lastTimestamp (last 15)",
        lambda: "\n".join(kube.run(["get", "events", "--sort-by=.lastTimestamp"]).splitlines()[-15:]))
    return items
