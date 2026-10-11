"""Gate rules, read from the airport config file that the cluster mounts into the pod.

The file is checked on every request but parsed again only when it has changed, so an
uploaded config takes effect without restarting the service.

If there is no usable config, nothing is checked. A half-finished install must not
stop the service from working.
"""
import logging
import os
from typing import Dict, Optional, Set, Tuple

import yaml

log = logging.getLogger("flight.gates")

DEFAULT_PATH = "/etc/aos/airport.yaml"


class GateRules:
    def __init__(self, path: Optional[str] = None):
        self._path = path
        self._stamp: Optional[Tuple] = None
        self._gates: Optional[Set[str]] = None        # None = no usable config
        self._airlines: Dict[str, Set[str]] = {}

    def _config_path(self) -> str:
        return self._path or os.environ.get("AOS_CONFIG_PATH", DEFAULT_PATH)

    def _reload_if_changed(self) -> None:
        path = self._config_path()
        try:
            info = os.stat(path)
        except OSError:
            if self._stamp is not None:
                log.warning("config file is gone, gate checks are off: %s", path)
            self._stamp, self._gates, self._airlines = None, None, {}
            return

        # A mounted ConfigMap is replaced by swapping a directory, which changes the inode.
        stamp = (path, info.st_mtime_ns, info.st_size, info.st_ino)
        if stamp == self._stamp:
            return
        self._stamp = stamp

        try:
            with open(path) as handle:
                data = yaml.safe_load(handle)
            gates = {g["id"] for g in data["gates"]}
            airlines = {a["code"]: set(a.get("gates", [])) for a in data["airlines"]}
        except Exception as exc:                      # unreadable or malformed file
            log.error("ignoring unusable config %s: %s", path, exc)
            self._gates, self._airlines = None, {}
            return

        self._gates, self._airlines = gates, airlines
        log.info("loaded %d gates and %d airlines from %s", len(gates), len(airlines), path)

    def problem(self, flight_no: str, gate: Optional[str]) -> Optional[str]:
        """Return a message if the gate is not allowed, or None if it is fine."""
        if gate is None:
            return None
        self._reload_if_changed()
        if self._gates is None:
            return None                               # no config: do not block

        if gate not in self._gates:
            return f"unknown gate {gate}"

        airline = flight_no[:2].upper()               # TK1234 -> TK
        allowed = self._airlines.get(airline)
        if allowed is not None and gate not in allowed:
            return f"gate {gate} is not allowed for airline {airline}"
        return None


rules = GateRules()
