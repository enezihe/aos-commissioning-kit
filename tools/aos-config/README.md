# aos-config

Command line tool for the airport configuration of the AOS Commissioning Kit.
It checks a config file before it reaches a cluster, shows what would change,
and keeps every uploaded version so a change can be undone.

## Setup

```bash
cd tools/aos-config
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run every command from this folder as `python -m aosconfig <command>`.

## Commands

| Command | What it does |
|---|---|
| `validate FILE` | Checks the file against the rules. Exit code 0 = valid, 1 = problems |
| `diff NEW [--old OLD]` | Shows `+` added, `-` removed, `~` changed. Without `--old` it is a first install |
| `upload FILE -n NAMESPACE` | Validates, prints the target and the changes. Dry run unless `--apply` is given |
| `history -n NAMESPACE` | Lists stored versions and marks the live one |
| `rollback VERSION -n NAMESPACE` | Makes an older version live again. Dry run unless `--apply` is given |

Examples:

```bash
python -m aosconfig validate ../../config/airport.yaml
python -m aosconfig diff new.yaml --old ../../config/airport.yaml
python -m aosconfig upload ../../config/airport.yaml -n aos-demo            # dry run
python -m aosconfig upload ../../config/airport.yaml -n aos-demo --apply    # asks to confirm
python -m aosconfig history -n aos-demo
python -m aosconfig rollback 1 -n aos-demo --apply
```

## Rules checked by `validate`

Field rules (one value):
- airport code: exactly 3 capital letters
- airline code: exactly 2 capital letters or digits
- ids and names must not be empty

Cross rules (lists compared with each other):
- no duplicate terminal id, gate id, carousel id or airline code
- every gate and carousel must belong to an existing terminal
- every gate an airline may use must exist

Field rules run first. If a field rule fails, the cross rules are skipped, so a
customer may need two rounds to see every problem.

## Safe defaults

- `--namespace` is required, there is no default.
- The target (context and namespace) is printed before anything happens.
- Nothing is written without `--apply`.
- The confirmation question defaults to No. `--yes` skips it, for automation only.
- A config that fails validation never reaches the cluster.

## How versions are stored

Everything lives in the chosen namespace as ConfigMaps:

| ConfigMap | Content |
|---|---|
| `airport-config` | The live config (label `aos-config/version=N`) |
| `airport-config-v1`, `v2`, ... | An archive copy of every uploaded version, never deleted |

Upload writes a new archive version and updates the live one. Rollback copies an
older archive back to the live one. The tool talks to the cluster through `kubectl`,
using the context you are logged in with.

## Code map

| File | Role |
|---|---|
| `aosconfig/models.py` | The rules (Pydantic) |
| `aosconfig/loader.py` | Reads YAML and turns problems into readable lines |
| `aosconfig/differ.py` | Compares two configs by meaning |
| `aosconfig/cluster.py` | The only place that calls `kubectl` |
| `aosconfig/cli.py` | The commands (Typer) |

## Tests

```bash
python -m pytest -v
```

The upload and rollback tests use a fake cluster, so they never touch a real one.

## Known limits

- The flight service does not read this config yet.
- `rollback` simply makes a stored version live, so it can also move forward.
- The tool must be run from this folder (it is not installed as a package).
