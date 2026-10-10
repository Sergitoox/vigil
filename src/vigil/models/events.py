from datetime import datetime, date, time
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class Confidence(str, Enum):
    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"


class DayNight(str, Enum):
    DAY = "D"
    NIGHT = "N"


class FireDetection(BaseModel):
    """
    A single fire detection from NASA FIRMS (VIIRS or MODIS).
    One row from the FIRMS API response, normalized.
    """

    latitude: float
    longitude: float
    frp: float = Field(description="Fire Radiative Power in MW — proxy for fire intensity")
    confidence: Confidence
    acq_datetime: datetime = Field(description="UTC acquisition timestamp")
    satellite: str = Field(description="Satellite identifier (e.g. 'N' for Suomi NPP)")
    daynight: DayNight
    bright_ti4: float | None = Field(
        default=None,
        description="Brightness temperature band I4 in Kelvin (VIIRS only)"
    )
    source: str = Field(
        default="VIIRS_SNPP_NRT",
        description="FIRMS data source product name"
    )

    @model_validator(mode="before")
    @classmethod
    def parse_firms_datetime(cls, data: dict) -> dict:
        """
        FIRMS returns date and time as separate fields:
        acq_date: "2026-04-24", acq_time: "1423" (HHMM)
        We combine them into a single UTC datetime.
        """
        if "acq_date" in data and "acq_time" in data and "acq_datetime" not in data:
            acq_date = data.pop("acq_date")
            acq_time_raw = str(data.pop("acq_time")).zfill(4)  # ensure 4 digits

            if isinstance(acq_date, str):
                acq_date = date.fromisoformat(acq_date)

            hour = int(acq_time_raw[:2])
            minute = int(acq_time_raw[2:])
            data["acq_datetime"] = datetime.combine(acq_date, time(hour, minute))

        return data

    @property
    def is_high_intensity(self) -> bool:
        """FRP > 50 MW is considered high intensity."""
        return self.frp > 50.0

    @property
    def unique_id(self) -> str:
        """Deterministic ID for deduplication in DuckDB."""
        ts = self.acq_datetime.strftime("%Y%m%d%H%M")
        return f"{self.latitude:.4f}_{self.longitude:.4f}_{ts}"