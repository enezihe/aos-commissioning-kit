"""Compare two configs by meaning, not by text lines.

Items are matched by their key (id or code), so moving a gate to another line of
the file is not a change, but changing its terminal is.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aosconfig.models import AirportConfig

# section name -> field that identifies an item inside that section
SECTIONS = {
    "terminals": "id",
    "gates": "id",
    "carousels": "id",
    "airlines": "code",
}


@dataclass
class Change:
    kind: str       # "added", "removed" or "changed"
    section: str    # for example "gates"
    key: str        # for example "B3"
    detail: str = ""

    def __str__(self) -> str:
        symbol = {"added": "+", "removed": "-", "changed": "~"}[self.kind]
        label = self.section[:-1] if self.section.endswith("s") else self.section
        text = f"{symbol} {label} {self.key}"
        return f"{text}: {self.detail}" if self.detail else text


def _describe_fields(old: Dict[str, Any], new: Dict[str, Any]) -> str:
    """Say which fields differ between two versions of the same item."""
    parts = []
    for name in new:
        before, after = old.get(name), new[name]
        if before == after:
            continue
        if isinstance(before, list) and isinstance(after, list):
            added = [x for x in after if x not in before]
            removed = [x for x in before if x not in after]
            bits = [f"+{x}" for x in added] + [f"-{x}" for x in removed]
            parts.append(f"{name} {' '.join(bits)}")
        else:
            parts.append(f"{name} {before} -> {after}")
    return "; ".join(parts)


def diff_configs(old: Optional[AirportConfig], new: AirportConfig) -> List[Change]:
    """List what must change to turn `old` into `new`. old=None means nothing deployed yet."""
    changes: List[Change] = []

    # the airport block (one item, no list)
    old_airport = old.airport.model_dump() if old else {}
    new_airport = new.airport.model_dump()
    if old is None:
        changes.append(Change("added", "airport", new.airport.code, new.airport.name))
    elif old_airport != new_airport:
        changes.append(Change("changed", "airport", new.airport.code, _describe_fields(old_airport, new_airport)))

    # the four lists
    for section, key_field in SECTIONS.items():
        old_items = {getattr(i, key_field): i.model_dump() for i in getattr(old, section)} if old else {}
        new_items = {getattr(i, key_field): i.model_dump() for i in getattr(new, section)}

        for key in sorted(new_items.keys() - old_items.keys()):
            changes.append(Change("added", section, key))
        for key in sorted(old_items.keys() - new_items.keys()):
            changes.append(Change("removed", section, key))
        for key in sorted(new_items.keys() & old_items.keys()):
            if old_items[key] != new_items[key]:
                changes.append(Change("changed", section, key, _describe_fields(old_items[key], new_items[key])))

    return changes
