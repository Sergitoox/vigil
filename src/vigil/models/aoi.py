from pydantic import BaseModel, field_validator, model_validator
from shapely.geometry import Polygon, box
from shapely import wkt
import json


class AreaOfInterest(BaseModel):
    """
    Defines the geographic boundary for all vigil operations.
    Accepts a WKT polygon string or a bounding box [west, south, east, north].

    Examples:
        wkt:  "POLYGON((-1.0 39.0, 0.0 39.0, 0.0 40.0, -1.0 40.0, -1.0 39.0))"
        bbox: [-5.0, 36.0, 5.0, 44.0]
    """

    wkt_str: str | None = None
    bbox: list[float] | None = None  # [west, south, east, north]

    # Computed at validation time — not part of the serialized model
    _polygon: Polygon | None = None

    @model_validator(mode="after")
    def build_polygon(self) -> "AreaOfInterest":
        if self.wkt_str:
            self._polygon = wkt.loads(self.wkt_str)
        elif self.bbox:
            w, s, e, n = self.bbox
            self._polygon = box(w, s, e, n)
        else:
            raise ValueError("Either wkt_str or bbox must be provided")
        return self

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return v
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 values: [west, south, east, north]")
        w, s, e, n = v
        if w >= e:
            raise ValueError("west must be less than east")
        if s >= n:
            raise ValueError("south must be less than north")
        return v

    @property
    def polygon(self) -> Polygon:
        """Returns the Shapely polygon for geospatial operations."""
        if self._polygon is None:
            self.build_polygon()
        return self._polygon  # type: ignore[return-value]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Returns (west, south, east, north) bounding box."""
        return self.polygon.bounds  # type: ignore[return-value]

    @property
    def firms_bbox_str(self) -> str:
        """
        Returns the bounding box as a string in the format NASA FIRMS expects:
        'W,S,E,N'
        """
        w, s, e, n = self.bounds
        return f"{w},{s},{e},{n}"

    def contains_point(self, lat: float, lon: float) -> bool:
        """Returns True if the point (lat, lon) is within the AOI polygon."""
        from shapely.geometry import Point
        return self.polygon.contains(Point(lon, lat))  # Note: Shapely uses (x=lon, y=lat)

    def __str__(self) -> str:
        w, s, e, n = self.bounds
        return f"AOI(W={w}, S={s}, E={e}, N={n})"