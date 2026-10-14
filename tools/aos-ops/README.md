# aos-ops

Readiness checks and diagnosis for the airport deployment. It only **reads** from the
cluster: the kubectl wrapper refuses every verb except `get`, `describe`, `logs` and `exec`
(`exec` is used once, to ask the Service by its own name).

## Setup

```bash
cd tools/aos-ops
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run every command from this folder as `python -m aosops <command>`.

## `gate`: the go-live checklist

```bash
python -m aosops gate -n default
python -m aosops gate -n default --config ../../config/airport.yaml --report readiness.md
```

Exit code 0 = gate passed, 1 = gate failed, 2 = could not run. `--namespace` is required, and
the target (context and namespace) is printed first.

| Criterion | Fails when |
|---|---|
| namespace | it does not exist |
| deployment | it is missing (warns when scaled to 0) |
| pods ready | fewer pods are Ready than wanted; the detail names the reason (`CrashLoopBackOff`, `ErrImagePull`, `ContainerCreating`, `Running but not Ready`) |
| restarts | a container was OOMKilled (warns on any other restart) |
| service selector | it selects labels that no pod carries |
| endpoints | the Service has none while pods are wanted |
| customer path | the Service name does not answer `/health` from inside the cluster |
| config | `--config` is given and the live config differs, or `--require-config` and none is uploaded |

Warnings (do not fail the gate, but should be read): no readiness probe, no resource limits,
a start-command override, restarts above `--max-restarts`, no config uploaded.

A gate fails if any criterion fails. These are fixed rules, there is no AI in this command. Use `triage` when the gate fails and the cause is not obvious.

## `triage`: an AI-drafted diagnosis you must verify

```bash
python -m aosops triage -n lab --complaint "customers cannot reach the flight list"        # dry run
python -m aosops triage -n lab --complaint "..." --show-evidence                           # read what would be sent
export ANTHROPIC_API_KEY=...                                                              # set in your own terminal
python -m aosops triage -n lab --complaint "..." --send --out draft.md
```

It collects the evidence an engineer would collect by hand (read-only), cleans it, asks a Claude
model for a diagnosis, checks the answer, and writes a draft incident note.

| Safeguard | What it does |
|---|---|
| Dry run by default | Nothing leaves the computer unless `--send` is given and the target is confirmed. |
| Secret removal | Keys, tokens, JWTs, passwords written as `name=value` and e-mail addresses are replaced before sending. Environment variable values are never collected, only their names. |
| Fixed answer shape | The model must return symptom, root cause, category, confidence, exact evidence quotes, read-only verification steps, fix, escalation and prevention. |
| Quote check | Every quote must appear in the evidence that was sent. If any quote is missing the draft is marked "do not trust" and the exit code is 1. |
| Human in the loop | The note is labelled an AI draft. Nothing in the cluster is changed. |

The evidence is treated as data: the prompt tells the model to ignore instructions that appear inside it.
The cost is estimated before sending and reported afterwards. The model can be set with `--model`
or `AOS_OPS_MODEL`.

## Lab: reproduce the six faults

`scenarios/` holds one manifest per fault from `docs/incidents/`, plus a healthy baseline.
`scenarios/lab.sh` applies them, and refuses any context that is not a local `kind-` cluster.

```bash
./scenarios/lab.sh up 05     # selector mismatch
python -m aosops gate -n lab
./scenarios/lab.sh down
```

Verified on kind: the healthy baseline passes, and each of the six scenarios fails the gate on
the expected criterion.

## Tests

```bash
python -m pytest -v
```

The criteria are tested with made-up cluster data, one test per fault. Other tests check that
write commands are refused before kubectl is called, the exit codes, secret removal, and the quote
check (with a fake analyzer, so the tests need no API key and cost nothing).
