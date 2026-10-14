"""Read-only access to a cluster through kubectl.

This tool diagnoses, it never changes anything. The wrapper enforces that: only a short
list of reading verbs is allowed, and everything else is refused before kubectl is called.
"""
import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional

READ_ONLY_VERBS = {"get", "describe", "logs", "exec"}


class KubeError(Exception):
    """kubectl failed, or the request was refused."""


@dataclass
class Target:
    context: str
    namespace: str

    def __str__(self) -> str:
        return f"context={self.context} namespace={self.namespace}"


def current_context(kubectl: str = "kubectl") -> str:
    try:
        result = subprocess.run([kubectl, "config", "current-context"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        raise KubeError(f"'{kubectl}' was not found on this computer")
    if result.returncode != 0:
        raise KubeError("no current kubectl context is set; pass --context")
    return result.stdout.strip()


class Kube:
    def __init__(self, context: str, namespace: str, kubectl: str = "kubectl"):
        self.target = Target(context, namespace)
        self._kubectl = kubectl

    def run(self, args: List[str], timeout: int = 60) -> str:
        if not args or args[0] not in READ_ONLY_VERBS:
            raise KubeError(f"refused: '{args[0] if args else ''}' is not a read-only command")
        cmd = [self._kubectl, "--context", self.target.context, "--namespace", self.target.namespace] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise KubeError(f"'{self._kubectl}' was not found on this computer")
        except subprocess.TimeoutExpired:
            raise KubeError(f"the cluster did not answer within {timeout} seconds")
        if result.returncode != 0:
            raise KubeError(result.stderr.strip() or "kubectl failed")
        return result.stdout

    def get_json(self, *args: str) -> dict:
        return json.loads(self.run(["get", *args, "-o", "json"]))

    def get_json_or_none(self, *args: str) -> Optional[dict]:
        """Like get_json, but a missing object gives None instead of an error."""
        try:
            return self.get_json(*args)
        except KubeError as exc:
            if "NotFound" in str(exc) or "not found" in str(exc):
                return None
            raise
