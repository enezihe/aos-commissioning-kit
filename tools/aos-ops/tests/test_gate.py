"""The go-live criteria, tested with made-up cluster data (no cluster needed)."""
import subprocess

import pytest
from typer.testing import CliRunner

from aosops import cli, gate
from aosops.gate import FAIL, PASS, WARN, Options, Result, Snapshot
from aosops.kube import Kube, KubeError, Target

LABELS = {"app": "flight-service"}


def deployment(replicas=2, probe=True, limits=True, command=None, labels=None):
    container = {"name": "flight-service", "image": "flight-service:0.2"}
    if probe:
        container["readinessProbe"] = {"httpGet": {"path": "/health", "port": 8000}}
    if limits:
        container["resources"] = {"limits": {"cpu": "200m", "memory": "128Mi"}}
    if command:
        container["command"] = command
    return {"spec": {"replicas": replicas, "selector": {"matchLabels": LABELS},
                     "template": {"metadata": {"labels": labels or LABELS}, "spec": {"containers": [container]}}}}


def pod(ready=True, restarts=0, waiting=None, terminated=None, phase="Running"):
    status = {"ready": ready, "restartCount": restarts, "state": {}, "lastState": {}}
    if waiting:
        status["state"] = {"waiting": {"reason": waiting}}
    if terminated:
        status["lastState"] = {"terminated": {"reason": terminated[0], "exitCode": terminated[1]}}
    return {"metadata": {"name": "p"},
            "status": {"phase": phase, "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                       "containerStatuses": [status]}}


def service(selector=None):
    return {"spec": {"selector": selector or LABELS}}


def config(version="1", text="airport: {code: GLB}\n"):
    return {"metadata": {"labels": {"aos-config/version": version}}, "data": {"airport.yaml": text}}


def healthy(**overrides):
    base = dict(deployment=deployment(), pods=[pod(), pod()], service=service(), ready_endpoints=2,
                live_config=config(), probe=(True, "HTTP 200"))
    base.update(overrides)
    return Snapshot(**base)


def run(snap, **opts):
    return {r.name: r for r in gate.evaluate(snap, Options(**opts))}


def test_a_healthy_deployment_passes():
    results = gate.evaluate(healthy(), Options())
    assert gate.passed(results)
    assert all(r.status == PASS for r in results)


# the six faults from the incident playbook, as the gate sees them
def test_fault_1_wrong_probe_path_pods_running_but_not_ready():
    snap = healthy(pods=[pod(ready=False), pod(ready=False)], ready_endpoints=0, probe=None)
    r = run(snap)
    assert r["pods ready"].status == FAIL and "Running but not Ready" in r["pods ready"].detail
    assert r["endpoints"].status == FAIL
    assert not gate.passed(list(r.values()))


def test_fault_2_crash_loop_names_the_reason():
    snap = healthy(pods=[pod(ready=False, restarts=5, waiting="CrashLoopBackOff", terminated=("Error", 1))] * 2,
                   ready_endpoints=0, probe=None)
    r = run(snap)
    assert r["pods ready"].status == FAIL and "CrashLoopBackOff" in r["pods ready"].detail
    assert r["restarts"].status == WARN


def test_fault_3_image_pull_names_the_reason():
    snap = healthy(pods=[pod(ready=False, waiting="ErrImagePull", phase="Pending")] * 2, ready_endpoints=0, probe=None)
    assert "ErrImagePull" in run(snap)["pods ready"].detail


def test_fault_4_out_of_memory_fails_the_gate():
    killed = pod(ready=False, restarts=3, waiting="CrashLoopBackOff", terminated=("OOMKilled", 137))
    r = run(healthy(pods=[killed, killed], ready_endpoints=0, probe=None))
    assert r["restarts"].status == FAIL and "OOMKilled" in r["restarts"].detail


def test_fault_5_service_selector_matches_no_pod_even_though_pods_are_ready():
    snap = healthy(service=service({"app": "flight-svc"}), ready_endpoints=0, probe=(False, "connection refused"))
    r = run(snap)
    assert r["pods ready"].status == PASS                      # the pods are fine
    assert r["service selector"].status == FAIL
    assert "flight-svc" in r["service selector"].detail and "flight-service" in r["service selector"].detail
    assert r["endpoints"].status == FAIL
    assert r["customer path"].status == FAIL


def test_fault_6_missing_configmap_leaves_pods_waiting():
    snap = healthy(pods=[pod(ready=False, waiting="ContainerCreating", phase="Pending")] * 2,
                   ready_endpoints=0, probe=None, live_config=None)
    assert "ContainerCreating" in run(snap)["pods ready"].detail


# the other criteria
def test_no_config_is_a_warning_unless_it_is_required():
    assert run(healthy(live_config=None))["config"].status == WARN
    assert run(healthy(live_config=None), require_config=True)["config"].status == FAIL


def test_live_config_must_equal_the_expected_file():
    expected = {"airport": {"code": "GLB"}}
    assert run(healthy(), expected_config=expected)["config"].status == PASS
    different = run(healthy(), expected_config={"airport": {"code": "XXX"}})["config"]
    assert different.status == FAIL and "version 1" in different.detail


def test_scaled_to_zero_is_flagged():
    r = run(healthy(deployment=deployment(replicas=0), pods=[], ready_endpoints=0, probe=None))
    assert r["deployment"].status == WARN and "scaled to 0" in r["deployment"].detail


def test_missing_probe_limits_and_start_command_override_only_warn():
    snap = healthy(deployment=deployment(probe=False, limits=False, command=["uvicorn", "x"]))
    results = gate.evaluate(snap, Options())
    names = {r.name: r.status for r in results}
    assert names["readiness probe"] == WARN and names["resource limits"] == WARN and names["start command"] == WARN
    assert gate.passed(results)                               # warnings do not fail the gate


def test_restarts_above_the_allowance_warn():
    assert run(healthy(pods=[pod(restarts=2), pod()]))["restarts"].status == WARN
    assert run(healthy(pods=[pod(restarts=2), pod()]), max_restarts=2)["restarts"].status == PASS


def test_a_missing_namespace_stops_early():
    results = gate.evaluate(Snapshot(namespace_exists=False), Options())
    assert [r.status for r in results] == [FAIL]


def test_markdown_report_states_the_decision():
    text = gate.to_markdown([Result(PASS, "namespace", "exists"), Result(FAIL, "endpoints", "none")], Target("c", "n"), "now")
    assert "gate FAILED (1 failed, 0 warnings)" in text and "| FAIL | endpoints | none |" in text


# the tool must never change the cluster
@pytest.mark.parametrize("verb", ["delete", "apply", "patch", "scale", "create", "edit", "replace", "rollout"])
def test_write_commands_are_refused_before_kubectl_is_called(monkeypatch, verb):
    def must_not_run(*args, **kwargs):
        raise AssertionError("kubectl was called")
    monkeypatch.setattr(subprocess, "run", must_not_run)
    with pytest.raises(KubeError, match="read-only"):
        Kube("c", "n").run([verb, "pod", "x"])


# the command
runner = CliRunner()


@pytest.fixture
def fake_cluster(monkeypatch):
    class FakeKube:
        def __init__(self, context, namespace):
            self.target = Target(context, namespace)
    monkeypatch.setattr(cli, "Kube", FakeKube)
    monkeypatch.setattr(cli, "current_context", lambda: "test-context")
    state = {"snapshot": healthy()}
    monkeypatch.setattr(cli.gate_mod, "collect", lambda kube, opts: state["snapshot"])
    return state


def test_command_exits_zero_when_the_gate_passes(fake_cluster):
    result = runner.invoke(cli.app, ["gate", "-n", "lab"])
    assert result.exit_code == 0 and "GATE PASSED" in result.output
    assert "context=test-context namespace=lab" in result.output


def test_command_exits_one_when_the_gate_fails(fake_cluster):
    fake_cluster["snapshot"] = healthy(service=service({"app": "flight-svc"}), ready_endpoints=0, probe=None)
    result = runner.invoke(cli.app, ["gate", "-n", "lab"])
    assert result.exit_code == 1 and "GATE FAILED" in result.output and "[FAIL] service selector" in result.output


def test_command_requires_a_namespace(fake_cluster):
    assert runner.invoke(cli.app, ["gate"]).exit_code == 2


def test_command_writes_the_report_file(fake_cluster, tmp_path):
    out = tmp_path / "report.md"
    runner.invoke(cli.app, ["gate", "-n", "lab", "--report", str(out)])
    assert "Readiness report" in out.read_text() and "gate PASSED" in out.read_text()
