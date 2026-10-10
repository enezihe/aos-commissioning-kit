"""Upload, history and rollback tested against a fake cluster, so no real cluster is touched."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from aosconfig import cli
from aosconfig.cluster import ClusterError, Target

SAMPLE = Path(__file__).resolve().parents[3] / "config" / "airport.yaml"
runner = CliRunner()


class FakeCluster:
    """Same methods as aosconfig.cluster.Cluster, but keeps everything in memory."""

    last = None

    def __init__(self, context, namespace):
        self.target = Target(context, namespace)
        self.archive = {}          # version -> yaml text
        self.live = None           # (version, text)
        self.writes = 0
        FakeCluster.last = self

    def check_reachable(self):
        if self.target.namespace == "missing":
            raise ClusterError('namespaces "missing" not found')

    def live_text(self):
        return self.live[1] if self.live else None

    def live_version(self):
        return self.live[0] if self.live else 0

    def versions(self):
        return sorted(self.archive)

    def archived_text(self, version):
        return self.archive.get(version)

    def publish(self, text):
        version = (max(self.archive) if self.archive else 0) + 1
        self.archive[version] = text
        self.live = (version, text)
        self.writes += 1
        return version

    def restore(self, version):
        self.live = (version, self.archive[version])
        self.writes += 1


@pytest.fixture(autouse=True)
def fake_cluster(monkeypatch):
    monkeypatch.setattr(cli, "Cluster", FakeCluster)
    monkeypatch.setattr(cli, "current_context", lambda: "test-context")
    FakeCluster.last = None


def run(*args, **kwargs):
    return runner.invoke(cli.app, list(args), **kwargs)


def test_namespace_is_required():
    result = run("upload", str(SAMPLE))
    assert result.exit_code == 2           # there is no default namespace


def test_dry_run_is_the_default_and_writes_nothing():
    result = run("upload", str(SAMPLE), "-n", "demo")
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert FakeCluster.last.writes == 0


def test_the_target_is_always_printed():
    result = run("upload", str(SAMPLE), "-n", "demo")
    assert "context=test-context namespace=demo" in result.output


def test_apply_with_yes_uploads_version_one():
    result = run("upload", str(SAMPLE), "-n", "demo", "--apply", "--yes")
    assert result.exit_code == 0
    assert "version 1 is now live" in result.output
    assert FakeCluster.last.live_version() == 1


def test_declining_the_confirmation_writes_nothing():
    result = run("upload", str(SAMPLE), "-n", "demo", "--apply", input="n\n")
    assert result.exit_code == 1
    assert "Nothing was written" in result.output
    assert FakeCluster.last.writes == 0


def test_invalid_file_never_reaches_the_cluster(tmp_path):
    data = yaml.safe_load(SAMPLE.read_text())
    data["gates"].append({"id": "Z1", "terminal": "T9"})
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))

    result = run("upload", str(bad), "-n", "demo", "--apply", "--yes")

    assert result.exit_code == 1
    assert "INVALID" in result.output
    assert FakeCluster.last is None        # the cluster object was never even created


def test_unknown_namespace_is_reported_and_nothing_is_written():
    result = run("upload", str(SAMPLE), "-n", "missing", "--apply", "--yes")
    assert result.exit_code == 1
    assert "CLUSTER ERROR" in result.output
    assert FakeCluster.last.writes == 0


def test_rollback_to_an_older_version(tmp_path):
    v1 = SAMPLE.read_text()
    data = yaml.safe_load(v1)
    data["airport"]["name"] = "Renamed Airport"
    v2_file = tmp_path / "v2.yaml"
    v2_file.write_text(yaml.safe_dump(data, sort_keys=False))

    # The fake lives only inside one command, so seed it through a shared instance.
    seeded = {}

    class Seeded(FakeCluster):
        def __init__(self, context, namespace):
            super().__init__(context, namespace)
            if seeded:
                self.archive, self.live = seeded["archive"], seeded["live"]
            seeded["archive"], seeded["live"] = self.archive, self.live

        def publish(self, text):
            version = super().publish(text)
            seeded["live"] = self.live
            return version

        def restore(self, version):
            super().restore(version)
            seeded["live"] = self.live

    cli.Cluster = Seeded
    try:
        run("upload", str(SAMPLE), "-n", "demo", "--apply", "--yes")
        run("upload", str(v2_file), "-n", "demo", "--apply", "--yes")
        dry = run("rollback", "1", "-n", "demo")
        assert "DRY RUN" in dry.output
        assert seeded["live"][0] == 2                      # the dry run changed nothing

        done = run("rollback", "1", "-n", "demo", "--apply", "--yes")
        assert done.exit_code == 0
        assert seeded["live"][0] == 1
        assert sorted(seeded["archive"]) == [1, 2]         # nothing was deleted
    finally:
        cli.Cluster = FakeCluster


def test_rollback_to_a_missing_version_fails():
    result = run("rollback", "9", "-n", "demo")
    assert result.exit_code == 1
    assert "does not exist" in result.output
