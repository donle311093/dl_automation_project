"""VMForge CLI — validate, generate, run, report, migrate."""
from __future__ import annotations

import shlex
import shutil
import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from migrate.json_to_new_schema import migrate_file

from .core.schema.loader import ConfigLoadError, load, load_all
from .core.schema.models import ProductConfig
from .robot.generator.renderer import render_suite, suite_filename
from .robot.generator.suite_builder import build_suite

app = typer.Typer(
    name="vmforge",
    help="VMForge — JSON-driven VM test automation framework.",
    no_args_is_help=True,
)


# ── validate ──────────────────────────────────────────────────────────────────

@app.command()
def validate(
    config: Annotated[Path, typer.Argument(help="Path to a VMForge JSON config file.")],
) -> None:
    """Validate a VMForge JSON config and print a summary."""
    try:
        cfg = load(config)
    except ConfigLoadError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Product : {cfg.product.name} ({cfg.product.id})")
    typer.echo(f"Envs    : {len(cfg.environments)}")
    for env in cfg.environments:
        typer.echo(f"  - {env.id}  template={env.template}  tests={len(env.run_tests)}")
    typer.echo(f"Tests   : {len(cfg.tests)}")
    typer.echo("OK — config is valid.")


# ── generate ──────────────────────────────────────────────────────────────────

@app.command()
def generate(
    config: Annotated[Path, typer.Argument(help="Path to a VMForge JSON config file or directory.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o", help="Output directory for .robot files.")] = Path("."),
) -> None:
    """Generate Robot Framework .robot suite files from a JSON config."""
    generated = _generate_suites(config, out_dir)
    typer.echo(f"Generated {len(generated)} suite(s) in {out_dir}.")


def _generate_suites(config: Path, out_dir: Path) -> list[Path]:
    configs = _load_configs(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for cfg in configs:
        for env in cfg.environments:
            suite = build_suite(cfg, env)
            fname = suite_filename(suite)
            dest = out_dir / fname
            dest.write_text(render_suite(suite), encoding="utf-8")
            generated.append(dest)
            typer.echo(f"  wrote {dest}")
    return generated


# ── run ───────────────────────────────────────────────────────────────────────

@app.command()
def run(
    config: Annotated[Path, typer.Argument(help="Path to a VMForge JSON config file or directory.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o", help="Directory for generated .robot files and results.")] = Path("results"),
    processes: Annotated[int, typer.Option("--processes", "-p", help="Number of parallel pabot workers.")] = 4,
    use_robot: Annotated[bool, typer.Option("--robot/--pabot", help="Use robot instead of pabot (single-process).")] = False,
) -> None:
    """Generate suites and execute them with pabot (or robot)."""
    suite_dir = out_dir / "suites"
    _generate_suites(config, suite_dir)

    _runner = "robot" if use_robot else "pabot"
    exe = shutil.which(_runner)
    if exe is None:
        typer.echo(
            f"ERROR: {_runner!r} not found on PATH; "
            f"install robotframework{'' if use_robot else '-pabot'}.",
            err=True,
        )
        raise typer.Exit(1)

    cmd: list[str] = [exe]
    if not use_robot:
        cmd += ["--processes", str(processes)]
    cmd += ["--outputdir", str(out_dir), str(suite_dir)]

    # shlex.join reflects the actual list passed to subprocess (not a shell string).
    typer.echo(f"Running: {shlex.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    raise typer.Exit(result.returncode)


# ── report ────────────────────────────────────────────────────────────────────

class ReportFormat(StrEnum):
    excel = "excel"
    junit = "junit"
    both = "both"


@app.command()
def report(
    output_xml: Annotated[Path, typer.Argument(help="Path to Robot Framework output.xml.")],
    fmt: Annotated[ReportFormat, typer.Option("--format", "-f", help="Output format.")] = ReportFormat.excel,
    out: Annotated[Path | None, typer.Option("--out", help="Output file path (omit to auto-name beside output.xml).")] = None,
) -> None:
    """Generate an Excel or JUnit report from a Robot Framework output.xml."""
    if not output_xml.is_file():
        typer.echo(f"ERROR: output.xml not found: {output_xml}", err=True)
        raise typer.Exit(1)

    base = output_xml.parent

    if fmt in (ReportFormat.excel, ReportFormat.both):
        from .reporters.excel import ExcelReporter

        # When fmt is "both", --out is ignored and both files are auto-named.
        dest = base / (output_xml.stem + ".xlsx") if fmt == ReportFormat.both else (out or base / (output_xml.stem + ".xlsx"))
        try:
            ExcelReporter().generate(output_xml, dest)
            typer.echo(f"Excel report: {dest}")
        except (ValueError, OSError) as exc:
            typer.echo(f"ERROR generating Excel report: {exc}", err=True)
            raise typer.Exit(1) from exc

    if fmt in (ReportFormat.junit, ReportFormat.both):
        from .reporters.junit import JUnitReporter

        # When fmt is "both", --out is ignored and both files are auto-named.
        dest = base / (output_xml.stem + "_junit.xml") if fmt == ReportFormat.both else (out or base / (output_xml.stem + "_junit.xml"))
        try:
            JUnitReporter().generate(output_xml, dest)
            typer.echo(f"JUnit report: {dest}")
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            typer.echo(f"ERROR generating JUnit report: {exc}", err=True)
            raise typer.Exit(1) from exc


# ── migrate ───────────────────────────────────────────────────────────────────

@app.command()
def migrate(
    src: Annotated[Path, typer.Argument(help="Old-format JSON file or directory of JSON files.")],
    out_dir: Annotated[Path | None, typer.Option("--out-dir", help="Output directory (required when src is a directory).")] = None,
    dst: Annotated[Path | None, typer.Option("--dst", help="Output file path (single-file mode only).")] = None,
    product_id: Annotated[str | None, typer.Option("--product-id", help="Override product id (single-file mode only).")] = None,
) -> None:
    """Migrate old vuln_automation JSON configs to the VMForge schema."""
    if src.is_dir():
        if out_dir is None:
            typer.echo("ERROR: --out-dir is required when src is a directory.", err=True)
            raise typer.Exit(1)
        files = sorted(src.glob("*.json"))
        if not files:
            typer.echo(f"No JSON files found in {src}.", err=True)
            raise typer.Exit(1)
        out_dir.mkdir(parents=True, exist_ok=True)
        ok = fail = 0
        for f in files:
            d = out_dir / f.name
            try:
                migrate_file(f, d)
                typer.echo(f"  migrated {f.name}")
                ok += 1
            except (ValueError, OSError) as exc:
                typer.echo(f"  SKIP {f.name}: {exc}", err=True)
                fail += 1
        typer.echo(f"Done: {ok} migrated, {fail} skipped.")
        if fail:
            raise typer.Exit(1)
    else:
        if not src.is_file():
            typer.echo(f"ERROR: {src} is not a file.", err=True)
            raise typer.Exit(1)
        target = dst or src.with_suffix(".new.json")
        try:
            migrate_file(src, target, product_id=product_id)
            typer.echo(f"Migrated: {target}")
        except (ValueError, OSError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(1) from exc


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_configs(path: Path) -> list[ProductConfig]:
    try:
        if path.is_dir():
            return load_all(path)
        return [load(path)]
    except ConfigLoadError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
