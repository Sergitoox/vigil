from abc import ABC, abstractmethod
from vigil.models.aoi import AreaOfInterest


class BaseIngestor(ABC):
    """
    Abstract base class for all vigil data ingestors.

    Each domain (fire, maritime, conflict...) implements this interface.
    The MCP server and CLI never interact with concrete ingestors directly —
    they always go through this abstraction.

    Subclasses must implement:
    - fetch(): call the external API and return normalized events
    - source_name: human-readable name for logging
    """

    def __init__(self, aoi: AreaOfInterest, api_key: str | None = None) -> None:
        self.aoi = aoi
        self.api_key = api_key

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for logging (e.g. 'NASA FIRMS VIIRS')."""
        ...

    @abstractmethod
    async def fetch(self) -> list:
        """
        Fetch current data from the external source for the configured AOI.
        Returns a list of normalized Pydantic event objects.
        Must not raise on transient network errors — log and return [].
        """
        ...