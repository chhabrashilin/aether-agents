"""External context features: FIRMS fires, Open-Meteo, Delhi calendar hooks."""

from aether_agents.context.calendar_delhi import DelhiCalendar
from aether_agents.context.firms import FirmsClient, FirmsFireEvent, MockFirmsClient
from aether_agents.context.meteo import MeteoClient, MeteoSnapshot, MockMeteoClient

__all__ = [
    "DelhiCalendar",
    "FirmsClient",
    "FirmsFireEvent",
    "MeteoClient",
    "MeteoSnapshot",
    "MockFirmsClient",
    "MockMeteoClient",
]
