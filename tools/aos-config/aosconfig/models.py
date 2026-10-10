"""Rules for the airport configuration file.

Two kinds of rules:
- field rules: look at one value (for example, an airline code must be 2 characters)
- cross rules: compare several lists with each other (for example, every gate
  must belong to a terminal that really exists)
"""
from typing import Iterable, List

from pydantic import BaseModel, Field, model_validator


class Airport(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{3}$")   # exactly 3 capital letters
    name: str = Field(min_length=1)


class Terminal(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class Gate(BaseModel):
    id: str = Field(min_length=1)
    terminal: str = Field(min_length=1)


class Carousel(BaseModel):
    id: str = Field(min_length=1)
    terminal: str = Field(min_length=1)


class Airline(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9]{2}$")  # exactly 2 capital letters or digits
    name: str = Field(min_length=1)
    gates: List[str]


def _duplicates(items: Iterable[str]) -> List[str]:
    """Return the values that appear more than once, sorted."""
    seen = set()
    repeated = set()
    for item in items:
        if item in seen:
            repeated.add(item)
        seen.add(item)
    return sorted(repeated)


class AirportConfig(BaseModel):
    airport: Airport
    terminals: List[Terminal]
    gates: List[Gate]
    carousels: List[Carousel]
    airlines: List[Airline]

    @model_validator(mode="after")
    def check_references(self):
        """Cross rules. Collect every problem and report them all at once."""
        errors = []

        terminal_ids = {t.id for t in self.terminals}
        gate_ids = [g.id for g in self.gates]

        # Rule 1: no duplicate ids
        for dup in _duplicates(t.id for t in self.terminals):
            errors.append(f"duplicate terminal id: {dup}")
        for dup in _duplicates(gate_ids):
            errors.append(f"duplicate gate id: {dup}")
        for dup in _duplicates(c.id for c in self.carousels):
            errors.append(f"duplicate carousel id: {dup}")
        for dup in _duplicates(a.code for a in self.airlines):
            errors.append(f"duplicate airline code: {dup}")

        # Rule 2: every gate must belong to an existing terminal
        for g in self.gates:
            if g.terminal not in terminal_ids:
                errors.append(f"gate {g.id}: unknown terminal {g.terminal}")

        # Rule 3: every carousel must belong to an existing terminal
        for c in self.carousels:
            if c.terminal not in terminal_ids:
                errors.append(f"carousel {c.id}: unknown terminal {c.terminal}")

        # Rule 4: every gate an airline may use must exist
        known_gates = set(gate_ids)
        for a in self.airlines:
            for gate in a.gates:
                if gate not in known_gates:
                    errors.append(f"airline {a.code}: unknown gate {gate}")

        if errors:
            raise ValueError("; ".join(errors))
        return self
