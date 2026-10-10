import asyncio
import os
import click
from vigil.models.aoi import AreaOfInterest
from vigil.server import run_server


@click.group()
def main() -> None:
    """vigil — multi-domain situational awareness MCP server."""
    pass


@main.command()
@click.option(
    "--aoi",
    required=True,
    help=(
        'Area of interest as WKT polygon or bbox. '
        'WKT: "POLYGON((-5 36, 5 36, 5 44, -5 44, -5 36))" '
        'Bbox: "-5,36,5,44" (west,south,east,north)'
    ),
)
@click.option(
    "--firms-key",
    envvar="VIGIL_FIRMS_KEY",
    required=True,
    help="NASA FIRMS API key. Also readable from VIGIL_FIRMS_KEY env var.",
)
@click.option(
    "--db",
    default=":memory:",
    show_default=True,
    help="DuckDB database path. Use :memory: for ephemeral (default) or a file path to persist.",
)
def serve(aoi: str, firms_key: str, db: str) -> None:
    """Start the vigil MCP server."""

    # Parse AOI — support both WKT polygon and simple bbox string
    if aoi.strip().upper().startswith("POLYGON"):
        area = AreaOfInterest(wkt_str=aoi.strip())
    else:
        try:
            parts = [float(x) for x in aoi.split(",")]
            area = AreaOfInterest(bbox=parts)
        except ValueError:
            raise click.BadParameter(
                'AOI must be a WKT polygon or a bbox string "W,S,E,N"',
                param_hint="--aoi",
            )

    click.echo(f"vigil MCP server starting — {area}", err=True)
    click.echo("Waiting for agent connections via stdio...", err=True)

    asyncio.run(run_server(aoi=area, firms_api_key=firms_key, db_path=db))