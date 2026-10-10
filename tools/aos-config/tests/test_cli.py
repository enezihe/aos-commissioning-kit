from pathlib import Path

import yaml
from typer.testing import CliRunner

from aosconfig.cli import app

SAMPLE = Path(__file__).resolve().parents[3] / "config" / "airport.yaml"
runner = CliRunner()


def test_validate_good_file_exits_zero():
    result = runner.invoke(app, ["validate", str(SAMPLE)])
    assert result.exit_code == 0
    assert "VALID" in result.output


def test_validate_bad_file_exits_one_and_lists_problems(tmp_path):
    data = yaml.safe_load(SAMPLE.read_text())
    data["gates"].append({"id": "Z1", "terminal": "T9"})
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))

    result = runner.invoke(app, ["validate", str(bad)])

    assert result.exit_code == 1
    assert "INVALID" in result.output
    assert "unknown terminal T9" in result.output


def test_validate_missing_file_exits_one(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert "file not found" in result.output
