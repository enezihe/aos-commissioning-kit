"""Everything that talks to the cluster lives here, so the rest of the tool never calls kubectl.

How versions are stored (all in one namespace):
- airport-config        the live config, the one the service reads (label version=N)
- airport-config-vN     an archive copy of every uploaded version, never deleted

Upload  = write a new archive airport-config-v(N+1), then update airport-config.
Rollback = copy an older archive back into airport-config.
"""
import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional

LIVE_NAME = "airport-config"
ARCHIVE_PREFIX = "airport-config-v"
DATA_KEY = "airport.yaml"
LABEL = "app.kubernetes.io/managed-by=aos-config"


class ClusterError(Exception):
    """kubectl failed or the cluster did not answer as expected."""


@dataclass
class Target:
    context: str
    namespace: str

    def __str__(self) -> str:
        return f"context={self.context} namespace={self.namespace}"


def current_context(kubectl: str = "kubectl") -> str:
    """The context kubectl would use right now (it is always printed before anything happens)."""
    try:
        result = subprocess.run([kubectl, "config", "current-context"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        raise ClusterError(f"'{kubectl}' was not found on this computer")
    if result.returncode != 0:
        raise ClusterError("no current kubectl context is set; pass --context")
    return result.stdout.strip()


class Cluster:
    """Talks to one cluster and namespace through the kubectl command."""

    def __init__(self, context: str, namespace: str, kubectl: str = "kubectl"):
        self.target = Target(context, namespace)
        self._kubectl = kubectl

    # -- low level ---------------------------------------------------------
    def _run(self, args: List[str], stdin: Optional[str] = None) -> str:
        cmd = [self._kubectl, "--context", self.target.context, "--namespace", self.target.namespace] + args
        try:
            result = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise ClusterError(f"'{self._kubectl}' was not found on this computer")
        except subprocess.TimeoutExpired:
            raise ClusterError("the cluster did not answer within 60 seconds")
        if result.returncode != 0:
            raise ClusterError(result.stderr.strip() or "kubectl failed")
        return result.stdout

    def _get(self, name: str) -> Optional[dict]:
        """Return a ConfigMap as a dict, or None if it does not exist."""
        try:
            return json.loads(self._run(["get", "configmap", name, "-o", "json"]))
        except ClusterError as exc:
            if "NotFound" in str(exc) or "not found" in str(exc):
                return None
            raise

    def _apply(self, name: str, text: str, version: int) -> None:
        manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": name,
                "labels": {"app.kubernetes.io/managed-by": "aos-config", "aos-config/version": str(version)},
            },
            "data": {DATA_KEY: text},
        }
        self._run(["apply", "-f", "-"], stdin=json.dumps(manifest))

    # -- what the commands need -------------------------------------------
    def check_reachable(self) -> None:
        self._run(["get", "namespace", self.target.namespace])

    def live_text(self) -> Optional[str]:
        """The config the service uses right now, or None on a first install."""
        cm = self._get(LIVE_NAME)
        return cm["data"][DATA_KEY] if cm else None

    def live_version(self) -> int:
        cm = self._get(LIVE_NAME)
        return int(cm["metadata"]["labels"]["aos-config/version"]) if cm else 0

    def versions(self) -> List[int]:
        out = json.loads(self._run(["get", "configmap", "-l", LABEL, "-o", "json"]))
        found = []
        for item in out["items"]:
            name = item["metadata"]["name"]
            if name.startswith(ARCHIVE_PREFIX):
                found.append(int(name[len(ARCHIVE_PREFIX):]))
        return sorted(found)

    def archived_text(self, version: int) -> Optional[str]:
        cm = self._get(f"{ARCHIVE_PREFIX}{version}")
        return cm["data"][DATA_KEY] if cm else None

    def publish(self, text: str) -> int:
        """Store a new version and make it the live one. Returns the new version number."""
        known = self.versions()
        new_version = (known[-1] if known else 0) + 1
        self._apply(f"{ARCHIVE_PREFIX}{new_version}", text, new_version)
        self._apply(LIVE_NAME, text, new_version)
        return new_version

    def restore(self, version: int) -> None:
        text = self.archived_text(version)
        if text is None:
            raise ClusterError(f"version {version} does not exist")
        self._apply(LIVE_NAME, text, version)
