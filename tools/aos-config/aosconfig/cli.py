"""Command line entry point: python -m aosconfig <command>."""
from pathlib import Path

import typer

from aosconfig.loader import ConfigError, load_config

app = typer.Typer(help="Validate, compare and upload airport configuration.", no_args_is_help=True)


@app.callback()
def main():
    """Airport configuration tool."""


@app.command()
def validate(path: Path = typer.Argument(..., help="Path to the airport YAML file")):
    """Check a config file against the rules. Exit code 0 = valid, 1 = problems found."""
    try:
        cfg = load_config(path)
    except ConfigError as exc:
        typer.secho(f"INVALID: {len(exc.problems)} problem(s) in {path}", fg=typer.colors.RED, err=True)
        for problem in exc.problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1)

    typer.secho(
        f"VALID: {path} ({len(cfg.terminals)} terminals, {len(cfg.gates)} gates, "
        f"{len(cfg.carousels)} carousels, {len(cfg.airlines)} airlines)",
        fg=typer.colors.GREEN,
    )
