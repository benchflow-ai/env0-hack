"""CLI: mock-gdrive serve|seed|reset."""

from __future__ import annotations

import sys
from pathlib import Path

import click

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def _default_port(env_name: str = "mock-gdrive", fallback: int = 9005) -> int:
    """Read default port from config.toml, walking up from cwd."""
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "config.toml"
        if candidate.is_file():
            with open(candidate, "rb") as f:
                cfg = tomllib.load(f)
            return cfg.get(env_name, {}).get("port", fallback)
    return fallback


@click.group()
@click.option("--db", default="mock_gdrive.db", help="Path to SQLite database file")
@click.pass_context
def cli(ctx, db):
    """Mock Google Drive — Drive-compatible environment for AI agent evaluation."""
    from mock_gdrive.models.base import resolve_db_path
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = str(resolve_db_path(db))


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=_default_port(), type=int, help="Bind port")
@click.option("--no-mcp", is_flag=True, help="Disable MCP endpoint")
@click.pass_context
def serve(ctx, host, port, no_mcp):
    """Start the Mock Google Drive API server."""
    db_path = ctx.obj["db_path"]
    click.echo(f"Starting Mock Google Drive server on {host}:{port}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  API: http://{host}:{port}/drive/v3/files")
    click.echo(f"  Docs: http://{host}:{port}/docs")
    if not no_mcp:
        click.echo(f"  MCP: http://{host}:{port}/mcp")
    click.echo()

    from mock_gdrive.server import run_server
    run_server(host=host, port=port, db_path=db_path, enable_mcp=not no_mcp)


@cli.command()
@click.option("--scenario", default="default", help="Scenario name")
@click.option(
    "--task-data",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Absolute path to one task's data directory",
)
@click.option(
    "--task-name",
    default=None,
    help="Explicit task identity for task-data seeding",
)
@click.option("--seed", default=42, type=int, help="Random seed for reproducibility")
@click.pass_context
def seed(ctx, scenario, task_data, task_name, seed):
    """Seed the database with test data."""
    db_path = ctx.obj["db_path"]
    if Path(db_path).exists():
        Path(db_path).unlink()
        click.echo(f"Removed existing database: {db_path}")

    from mock_gdrive.seed.generator import seed_database
    result = seed_database(
        scenario=scenario,
        seed=seed,
        db_path=db_path,
        task_data_path=str(task_data) if task_data else None,
        task_name=task_name,
    )
    scenario_label = f"task-data:{task_name or task_data}" if task_data else scenario
    click.echo(f"Seeded database with scenario '{scenario_label}':")
    click.echo(f"  Users: {result['users']}")
    click.echo(f"  Folders: {result['folders']}")
    click.echo(f"  Files: {result['files']}")
    click.echo(f"  Total items: {result['total_items']}")
    click.echo(f"  Permissions: {result['permissions']}")
    click.echo(f"  Database: {db_path}")
    click.echo("  Initial snapshot saved.")


@cli.command()
@click.pass_context
def reset(ctx):
    """Reset database to initial seed state."""
    db_path = ctx.obj["db_path"]
    from mock_gdrive.models import init_db, reset_engine
    reset_engine()
    init_db(db_path)
    from mock_gdrive.state.snapshots import restore_snapshot
    success = restore_snapshot("initial")
    if success:
        click.echo("Database reset to initial state.")
    else:
        click.echo("Error: No initial snapshot found. Run `mock-gdrive seed` first.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
