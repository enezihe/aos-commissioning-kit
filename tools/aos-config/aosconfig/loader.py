"""Read a config file and check it against the rules in models.py."""
from pathlib import Path
from typing import List

import yaml
from pydantic import ValidationError

from aosconfig.models import AirportConfig


class ConfigError(Exception):
    """The config file cannot be used. `problems` is a list of readable messages."""

    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _readable(error: ValidationError) -> List[str]:
    """Turn a pydantic error into short lines a customer can act on."""
    lines = []
    for err in error.errors():
        where = ".".join(str(part) for part in err["loc"])
        message = err["msg"].replace("Value error, ", "")
        if where:
            lines.append(f"{where}: {message}")
        else:
            # cross rules raise one error that holds several messages joined by "; "
            lines.extend(part for part in message.split("; "))
    return lines


def load_config(path: Path) -> AirportConfig:
    """Return a valid config, or raise ConfigError with every problem found."""
    if not path.is_file():
        raise ConfigError([f"file not found: {path}"])

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError([f"not valid YAML: {exc}"])

    if not isinstance(data, dict):
        raise ConfigError(["the file must contain a mapping (airport, terminals, gates, ...)"])

    try:
        return AirportConfig(**data)
    except ValidationError as exc:
        raise ConfigError(_readable(exc))
