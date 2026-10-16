"""Command line entry point: python -m aosops <command>."""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml

from aosops import gate as gate_mod
from aosops import triage as triage_mod
from aosops.evidence import collect_evidence
from aosops.kube import Kube, KubeError, current_context

app = typer.Typer(help="Readiness checks and diagnosis for the airport deployment (read-only).", no_args_is_help=True)

NAMESPACE = typer.Option(..., "--namespace", "-n", help="Namespace to check. Required: there is no default.")
CONTEXT = typer.Option(None, "--context", help="kubectl context. Default: the current one (always printed first).")


@app.callback()
def main():
    """Airport operations tool. It only reads from the cluster."""


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2)


@app.command()
def gate(
    namespace: str = NAMESPACE,
    context: Optional[str] = CONTEXT,
    deployment: str = typer.Option("flight-service", help="Deployment to check"),
    service: str = typer.Option("flight-service", help="Service in front of it"),
    config: Optional[Path] = typer.Option(None, "--config", help="Airport YAML the live config must equal"),
    require_config: bool = typer.Option(False, "--require-config", help="Fail (not just warn) when no config is uploaded"),
    max_restarts: int = typer.Option(0, help="Restarts allowed before a warning"),
    no_probe: bool = typer.Option(False, "--no-probe", help="Skip asking the Service by its own name"),
    report: Optional[Path] = typer.Option(None, "--report", help="Also write the result as a markdown file"),
):
    """Run the go-live checks. Exit code 0 = gate passed, 1 = gate failed, 2 = could not run."""
    expected = None
    if config:
        try:
            expected = yaml.safe_load(config.read_text())
        except (OSError, yaml.YAMLError) as exc:
            _fail(f"cannot read --config {config}: {exc}")

    opts = gate_mod.Options(deployment=deployment, service=service, probe=not no_probe,
                            max_restarts=max_restarts, require_config=require_config, expected_config=expected)
    try:
        kube = Kube(context or current_context(), namespace)
        typer.secho(f"Target: {kube.target}", bold=True)
        snapshot = gate_mod.collect(kube, opts)
    except KubeError as exc:
        _fail(f"CLUSTER ERROR: {exc}")

    results = gate_mod.evaluate(snapshot, opts)
    colors = {gate_mod.PASS: typer.colors.GREEN, gate_mod.WARN: typer.colors.YELLOW, gate_mod.FAIL: typer.colors.RED}
    typer.echo("")
    for r in results:
        typer.secho(f"[{r.status}] ", fg=colors[r.status], nl=False)
        typer.echo(f"{r.name}: {r.detail}")

    ok = gate_mod.passed(results)
    fails = sum(r.status == gate_mod.FAIL for r in results)
    warns = sum(r.status == gate_mod.WARN for r in results)
    typer.echo("")
    typer.secho(f"GATE {'PASSED' if ok else 'FAILED'} ({fails} failed, {warns} warnings)",
                fg=typer.colors.GREEN if ok else typer.colors.RED, bold=True)

    if report:
        report.write_text(gate_mod.to_markdown(results, kube.target, datetime.now().strftime("%Y-%m-%d %H:%M")))
        typer.echo(f"Report written to {report}")
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def triage(
    namespace: str = NAMESPACE,
    context: Optional[str] = CONTEXT,
    deployment: str = typer.Option("flight-service", help="Deployment to look at"),
    service: str = typer.Option("flight-service", help="Service in front of it"),
    complaint: str = typer.Option("The service does not work as expected.", "--complaint", help="What the customer said"),
    model: str = typer.Option(os.environ.get("AOS_OPS_MODEL", triage_mod.DEFAULT_MODEL), "--model", help="Claude model"),
    send: bool = typer.Option(False, "--send", help="Really send the evidence to Claude. Without it nothing leaves this computer."),
    show_evidence: bool = typer.Option(False, "--show-evidence", help="Print the cleaned evidence in full"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write the draft incident note to this file"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before sending (automation only)"),
):
    """Collect evidence (read-only), clean it, and ask Claude for a diagnosis. Dry run unless --send."""
    try:
        kube = Kube(context or current_context(), namespace)
        typer.secho(f"Target: {kube.target}", bold=True)
        evidence = collect_evidence(kube, deployment, service)
    except KubeError as exc:
        _fail(f"CLUSTER ERROR: {exc}")

    user_message = triage_mod.build_user_message(complaint, evidence)
    tokens = triage_mod.estimate_input_tokens(triage_mod.SYSTEM_PROMPT, user_message)
    typer.echo("\nEvidence collected (secrets already removed):")
    for e in evidence:
        cleaned = ", ".join(f"{n} {k}" for k, n in e.redactions.items()) or "nothing to remove"
        typer.echo(f"  {e.id:<4} {len(e.text):>5} chars  {e.command[:78]}  [{cleaned}{'; cut' if e.truncated else ''}]")
    removed = sum(sum(e.redactions.values()) for e in evidence)
    typer.echo(f"\n{removed} secret-looking item(s) removed. About {tokens} input tokens.")
    price = triage_mod.PRICES.get(model)
    if price:
        typer.echo(f"Input cost at {model}: about ${tokens * price[0] / 1_000_000:.3f}, plus the answer (usually 1-2 thousand tokens).")

    if show_evidence:
        for e in evidence:
            typer.secho(f"\n--- {e.id}: {e.command}", bold=True)
            typer.echo(e.text)

    if not send:
        typer.secho("\nDRY RUN: nothing was sent. Read the evidence above (--show-evidence), then add --send.", fg=typer.colors.CYAN)
        raise typer.Exit(code=0)

    if not triage_mod.have_credentials():
        _fail("no credentials: set ANTHROPIC_API_KEY in this terminal (export ANTHROPIC_API_KEY=...)")
    if not yes and not typer.confirm(f"\nSend this evidence from {kube.target} to Claude ({model})?"):
        typer.echo("Cancelled. Nothing was sent.")
        raise typer.Exit(code=1)

    try:
        result = triage_mod.make_analyzer(model).analyze(triage_mod.SYSTEM_PROMPT, user_message)
    except triage_mod.AnalysisError as exc:
        _fail(f"ANALYSIS FAILED: {exc}")

    diag = result.diagnosis
    checks = triage_mod.verify_quotes(diag, evidence)
    ok = triage_mod.trusted(checks)
    cost = triage_mod.cost_usd(result.model, result.input_tokens, result.output_tokens)

    typer.secho(f"\nDiagnosis: {diag.category} (confidence {diag.confidence})", bold=True)
    typer.echo(f"Root cause: {diag.root_cause}")
    typer.echo(f"Escalate to: {diag.escalate_to}: {diag.escalate_reason}")
    typer.echo("Quotes checked against the evidence:")
    for c in checks:
        color = typer.colors.GREEN if c.status == "verified" else typer.colors.YELLOW if c.status == "wrong_source" else typer.colors.RED
        typer.secho(f"  [{c.status}] {c.evidence_id}: {c.quote[:90]}", fg=color)
    typer.echo(f"Tokens: {result.input_tokens} in, {result.output_tokens} out" + (f", about ${cost:.3f}" if cost is not None else ""))
    if not ok:
        typer.secho("NOT TRUSTED: at least one quote is not in the evidence, or nothing was quoted.", fg=typer.colors.RED, bold=True)

    note = triage_mod.render_note(f"{deployment} in {namespace}", complaint, str(kube.target), diag, checks,
                                  evidence, result, datetime.now().strftime("%Y-%m-%d %H:%M"))
    if out:
        out.write_text(note)
        typer.echo(f"Draft note written to {out}")
    else:
        typer.echo("\n" + note)
    raise typer.Exit(code=0 if ok else 1)
