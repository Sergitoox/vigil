import duckdb
from pathlib import Path
from vigil.models.events import FireDetection


# DuckDB schema for fire detections
# Using DOUBLE for coordinates — DuckDB spatial works on these natively
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fire_detections (
    id              VARCHAR PRIMARY KEY,
    latitude        DOUBLE NOT NULL,
    longitude       DOUBLE NOT NULL,
    frp             DOUBLE NOT NULL,
    confidence      VARCHAR NOT NULL,
    acq_datetime    TIMESTAMP NOT NULL,
    satellite       VARCHAR,
    daynight        VARCHAR,
    bright_ti4      DOUBLE,
    source          VARCHAR
);
"""

# Index for time-range queries (most common query pattern)
_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_fire_datetime ON fire_detections (acq_datetime);
"""


def get_connection(db_path: Path | str = ":memory:") -> duckdb.DuckDBPyConnection:
    """
    Returns a DuckDB connection with the spatial extension loaded.
    Use ':memory:' for tests and a file path for production.
    """
    conn = duckdb.connect(str(db_path))
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute(_SCHEMA_SQL)
    conn.execute(_INDEX_SQL)
    return conn


def upsert_detections(
    conn: duckdb.DuckDBPyConnection,
    detections: list[FireDetection],
) -> int:
    """
    Inserts or replaces fire detections. Uses unique_id for deduplication.
    Returns the number of rows inserted.
    """
    if not detections:
        return 0

    rows = [
        (
            d.unique_id,
            d.latitude,
            d.longitude,
            d.frp,
            d.confidence.value,
            d.acq_datetime,
            d.satellite,
            d.daynight.value,
            d.bright_ti4,
            d.source,
        )
        for d in detections
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO fire_detections
        (id, latitude, longitude, frp, confidence, acq_datetime,
         satellite, daynight, bright_ti4, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def query_fires_in_bbox(
    conn: duckdb.DuckDBPyConnection,
    west: float,
    south: float,
    east: float,
    north: float,
    hours: int = 24,
    min_confidence: str = "nominal",
) -> list[dict]:
    """
    Queries fire detections within a bounding box and time window.
    Confidence filter: 'low' returns all, 'nominal' excludes low, 'high' only high.
    """
    confidence_filter = {
        "low": ("low", "nominal", "high"),
        "nominal": ("nominal", "high"),
        "high": ("high",),
    }.get(min_confidence, ("nominal", "high"))

    placeholders = ", ".join("?" * len(confidence_filter))

    result = conn.execute(
        f"""
        SELECT
            id, latitude, longitude, frp, confidence,
            acq_datetime, satellite, daynight, bright_ti4, source
        FROM fire_detections
        WHERE
            longitude BETWEEN ? AND ?
            AND latitude  BETWEEN ? AND ?
            AND acq_datetime >= NOW() - INTERVAL (?) HOURS
            AND confidence IN ({placeholders})
        ORDER BY frp DESC
        """,
        [west, east, south, north, hours, *confidence_filter],
    ).fetchall()

    columns = [
        "id", "latitude", "longitude", "frp", "confidence",
        "acq_datetime", "satellite", "daynight", "bright_ti4", "source"
    ]
    return [dict(zip(columns, row)) for row in result]