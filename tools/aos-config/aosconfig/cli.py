"""Command line entry point: python -m aosconfig <command>."""
from pathlib import Path
from typing import Optional

import typer

from aosconfig.differ import diff_configs
from aosconfig.loader import ConfigError, load_config
from aosconfig.models import AirportConfig

app = typer.Typer(help="Validate, compare and upload airport configuration.", no_args_is_help=True)


@app.callback()
def main():
    """Airport configuration tool."""


def _load_or_exit(path: Path) -> AirportConfig:
    """Load a config file, or print every problem and exit with code 1."""
    try:
        return load_config(path)
    except ConfigError as exc:
        typer.secho(f"INVALID: {len(exc.problems)} problem(s) in {path}", fg=typer.colors.RED, err=True)
        for problem in exc.problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1)


@app.command()
def validate(path: Path = typer.Argument(..., help="Path to the airport YAML file")):
    """Check a config file against the rules. Exit code 0 = valid, 1 = problems found."""
    cfg = _load_or_exit(path)
    typer.secho(
        f"VALID: {path} ({len(cfg.terminals)} terminals, {len(cfg.gates)} gates, "
        f"{len(cfg.carousels)} carousels, {len(cfg.airlines)} airlines)",
        fg=typer.colors.GREEN,
    )


@app.command()
def diff(
    new: Path = typer.Argument(..., help="The new config file"),
    old: Optional[Path] = typer.Option(
        None, "--old", help="The current config to compare with. Leave out for a first install."
    ),
):
    """Show what would change: + added, - removed, ~ changed. Both files are validated first."""
    new_cfg = _load_or_exit(new)
    old_cfg = _load_or_exit(old) if old else None

    changes = diff_configs(old_cfg, new_cfg)
    if not changes:
        typer.echo("No differences.")
        return

    colors = {"added": typer.colors.GREEN, "removed": typer.colors.RED, "changed": typer.colors.YELLOW}
    for change in changes:
        typer.secho(str(change), fg=colors[change.kind])

    counts = {kind: sum(1 for c in changes if c.kind == kind) for kind in colors}
    source = f"compared with {old}" if old else "first install (nothing deployed yet)"
    typer.echo(f"\n{counts['added']} added, {counts['removed']} removed, {counts['changed']} changed - {source}")
