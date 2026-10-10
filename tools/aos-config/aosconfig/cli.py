"""Command line entry point: python -m aosconfig <command>."""
from pathlib import Path
from typing import List, Optional

import typer

from aosconfig.cluster import Cluster, ClusterError, current_context
from aosconfig.differ import Change, diff_configs
from aosconfig.loader import ConfigError, load_config, parse_config
from aosconfig.models import AirportConfig

app = typer.Typer(help="Validate, compare and upload airport configuration.", no_args_is_help=True)

NAMESPACE = typer.Option(..., "--namespace", "-n", help="Namespace to work in. Required: there is no default.")
CONTEXT = typer.Option(None, "--context", help="kubectl context. Default: the current one (always printed first).")
APPLY = typer.Option(False, "--apply", help="Really write to the cluster. Without it nothing is changed.")
YES = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation (use in automation only).")


@app.callback()
def main():
    """Airport configuration tool."""


def _fail(lines: List[str], title: str) -> None:
    typer.secho(title, fg=typer.colors.RED, err=True)
    for line in lines:
        typer.echo(f"  - {line}", err=True)
    raise typer.Exit(code=1)


def _load_or_exit(path: Path) -> AirportConfig:
    """Load a config file, or print every problem and exit with code 1."""
    try:
        return load_config(path)
    except ConfigError as exc:
        _fail(exc.problems, f"INVALID: {len(exc.problems)} problem(s) in {path}")


def _cluster_or_exit(context: Optional[str], namespace: str) -> Cluster:
    """Build the cluster handle, print the target, and make sure it answers."""
    try:
        cluster = Cluster(context or current_context(), namespace)
        typer.secho(f"Target: {cluster.target}", bold=True)
        cluster.check_reachable()
    except ClusterError as exc:
        _fail([str(exc)], "CLUSTER ERROR")
    return cluster


def _print_changes(changes: List[Change], source: str) -> None:
    colors = {"added": typer.colors.GREEN, "removed": typer.colors.RED, "changed": typer.colors.YELLOW}
    for change in changes:
        typer.secho(str(change), fg=colors[change.kind])
    counts = {kind: sum(1 for c in changes if c.kind == kind) for kind in colors}
    typer.echo(f"\n{counts['added']} added, {counts['removed']} removed, {counts['changed']} changed - {source}")


def _live_config(cluster: Cluster) -> Optional[AirportConfig]:
    """The config the cluster uses now. None on a first install (or if it is unreadable)."""
    try:
        text = cluster.live_text()
    except ClusterError as exc:
        _fail([str(exc)], "CLUSTER ERROR")
    if text is None:
        return None
    try:
        return parse_config(text)
    except ConfigError as exc:
        typer.secho("WARNING: the config in the cluster is not valid; comparing with nothing.", fg=typer.colors.YELLOW)
        for problem in exc.problems:
            typer.echo(f"  - {problem}")
        return None


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
    _print_changes(changes, f"compared with {old}" if old else "first install (nothing deployed yet)")


@app.command()
def upload(
    path: Path = typer.Argument(..., help="The config file to upload"),
    namespace: str = NAMESPACE,
    context: Optional[str] = CONTEXT,
    apply: bool = APPLY,
    yes: bool = YES,
):
    """Validate, show the changes, and (only with --apply) store a new version in the cluster."""
    new_cfg = _load_or_exit(path)
    text = path.read_text()
    typer.secho(f"VALID: {path}", fg=typer.colors.GREEN)

    cluster = _cluster_or_exit(context, namespace)
    live = _live_config(cluster)
    changes = diff_configs(live, new_cfg)
    if not changes:
        typer.echo("No differences: the cluster already has this config. Nothing to upload.")
        return
    _print_changes(changes, "compared with the live config" if live else "first install (nothing deployed yet)")

    if not apply:
        typer.secho("\nDRY RUN: nothing was written. Add --apply to upload.", fg=typer.colors.CYAN)
        return
    if not yes and not typer.confirm(f"\nUpload these changes to {cluster.target}?"):
        typer.echo("Cancelled. Nothing was written.")
        raise typer.Exit(code=1)

    try:
        version = cluster.publish(text)
    except ClusterError as exc:
        _fail([str(exc)], "UPLOAD FAILED")
    typer.secho(f"UPLOADED: version {version} is now live in {cluster.target}", fg=typer.colors.GREEN)


@app.command()
def history(namespace: str = NAMESPACE, context: Optional[str] = CONTEXT):
    """List the stored versions and mark the live one."""
    cluster = _cluster_or_exit(context, namespace)
    try:
        versions = cluster.versions()
        live = cluster.live_version()
    except ClusterError as exc:
        _fail([str(exc)], "CLUSTER ERROR")
    if not versions:
        typer.echo("No versions stored yet.")
        return
    for v in versions:
        typer.echo(f"  v{v}" + ("   <- live" if v == live else ""))


@app.command()
def rollback(
    version: int = typer.Argument(..., help="Version number to go back to (see 'history')"),
    namespace: str = NAMESPACE,
    context: Optional[str] = CONTEXT,
    apply: bool = APPLY,
    yes: bool = YES,
):
    """Make an older stored version the live one again. Archived versions are never deleted."""
    cluster = _cluster_or_exit(context, namespace)
    try:
        text = cluster.archived_text(version)
        live_version = cluster.live_version()
    except ClusterError as exc:
        _fail([str(exc)], "CLUSTER ERROR")
    if text is None:
        _fail([f"version {version} does not exist (see 'history')"], "ROLLBACK IMPOSSIBLE")
    if version == live_version:
        typer.echo(f"Version {version} is already live. Nothing to do.")
        return

    try:
        target_cfg = parse_config(text)
    except ConfigError as exc:
        _fail(exc.problems, f"version {version} is not a valid config")
    changes = diff_configs(_live_config(cluster), target_cfg)
    _print_changes(changes, f"going from v{live_version} back to v{version}")

    if not apply:
        typer.secho("\nDRY RUN: nothing was written. Add --apply to roll back.", fg=typer.colors.CYAN)
        return
    if not yes and not typer.confirm(f"\nRoll {cluster.target} back to version {version}?"):
        typer.echo("Cancelled. Nothing was written.")
        raise typer.Exit(code=1)

    try:
        cluster.restore(version)
    except ClusterError as exc:
        _fail([str(exc)], "ROLLBACK FAILED")
    typer.secho(f"ROLLED BACK: version {version} is now live in {cluster.target}", fg=typer.colors.GREEN)
