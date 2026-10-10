import json
import logging
from pathlib import Path

import mcp.server.stdio
from mcp.server import Server
from mcp.types import Tool, TextContent

from vigil.models.aoi import AreaOfInterest
from vigil.storage.database import get_connection, upsert_detections
from vigil.ingest.firms import FIRMSIngestor
from vigil.tools.fire import get_active_fires, get_fire_summary, assess_fire_risk

logger = logging.getLogger(__name__)


def create_server(
    aoi: AreaOfInterest,
    firms_api_key: str,
    db_path: Path | str = ":memory:",
) -> Server:
    """
    Creates and configures the vigil MCP server.
    All tools are registered here. Business logic lives in tools/.
    """
    conn = get_connection(db_path)
    ingestor = FIRMSIngestor(aoi=aoi, api_key=firms_api_key)
    server = Server("vigil")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="get_active_fires",
                description=(
                    "Returns all active fire detections from NASA FIRMS inside the "
                    "configured area of interest. Use this to get the raw list of "
                    "detections with coordinates, intensity (FRP in MW), confidence, "
                    "and acquisition time."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "How many hours back to query (default: 24, max: 240)",
                            "default": 24,
                        },
                        "min_confidence": {
                            "type": "string",
                            "enum": ["low", "nominal", "high"],
                            "description": "Minimum confidence level to include (default: nominal)",
                            "default": "nominal",
                        },
                    },
                },
            ),
            Tool(
                name="get_fire_summary",
                description=(
                    "Returns an executive intelligence summary of fire activity in the AOI. "
                    "Includes risk level (NONE/MEDIUM/HIGH/CRITICAL), detection counts by "
                    "confidence tier, peak intensity location, and recommendations. "
                    "Use this when you need a quick situational picture, not the full list."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Time window in hours (default: 24)",
                            "default": 24,
                        },
                    },
                },
            ),
            Tool(
                name="assess_fire_risk",
                description=(
                    "Provides a structured risk assessment of fire conditions in the AOI. "
                    "Returns risk level, specific risk factors, and actionable recommendations. "
                    "Use this when you need to make or support an operational decision."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Time window in hours (default: 24)",
                            "default": 24,
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        # Refresh data from FIRMS before every tool call
        # In production, this should be cached/polled asynchronously
        try:
            detections = await ingestor.fetch()
            upsert_detections(conn, detections)
        except Exception as e:
            logger.error("Failed to refresh FIRMS data: %s", e)

        hours = int(arguments.get("hours", 24))

        if name == "get_active_fires":
            result = get_active_fires(
                conn=conn,
                aoi=aoi,
                hours=hours,
                min_confidence=arguments.get("min_confidence", "nominal"),
            )
        elif name == "get_fire_summary":
            result = get_fire_summary(conn=conn, aoi=aoi, hours=hours)
        elif name == "assess_fire_risk":
            result = assess_fire_risk(conn=conn, aoi=aoi, hours=hours)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    return server


async def run_server(
    aoi: AreaOfInterest,
    firms_api_key: str,
    db_path: Path | str = ":memory:",
) -> None:
    server = create_server(aoi, firms_api_key, db_path)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )