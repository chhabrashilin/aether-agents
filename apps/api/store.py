"""In-memory stub store for stations / episodes / context until ingest+DB land."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aether_agents.agents.base.types import (
    ContextFeatureVector,
    EpisodeObject,
    Observation,
    StationStub,
)
from aether_agents.agents.context import ContextAgent
from aether_agents.agents.episode import EpisodeAgent
from aether_agents.context.firms import FirmsFireEvent, MockFirmsClient
from aether_agents.context.meteo import MockMeteoClient, MeteoSnapshot

# Representative Delhi–NCT CPCB-style stations (stub coordinates).
DELHI_STATIONS: list[StationStub] = [
    StationStub(
        station_id="DL001",
        name="Anand Vihar",
        city="Delhi",
        latitude=28.6460,
        longitude=77.3160,
    ),
    StationStub(
        station_id="DL002",
        name="RK Puram",
        city="Delhi",
        latitude=28.5630,
        longitude=77.1860,
    ),
    StationStub(
        station_id="DL003",
        name="Dwarka Sector 8",
        city="Delhi",
        latitude=28.5710,
        longitude=77.0710,
    ),
    StationStub(
        station_id="DL004",
        name="ITO",
        city="Delhi",
        latitude=28.6280,
        longitude=77.2410,
    ),
    StationStub(
        station_id="GJ001",
        name="Sector 62 Noida",
        city="Noida",
        latitude=28.6280,
        longitude=77.3640,
    ),
]


def _synthetic_observations(
    station_id: str,
    *,
    start: datetime,
    hours: int = 48,
) -> list[Observation]:
    """Build a Very Poor → Severe → decay synthetic series for demos/tests."""
    rows: list[Observation] = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        if h < 6:
            aqi = 180 + h * 5  # Moderate / Poor ramp
        elif h < 18:
            aqi = 320 + (h - 6) * 8  # Very Poor climb
        elif h < 30:
            aqi = 420 - (h - 18)  # Severe peak plateau
        elif h < 40:
            aqi = 350 - (h - 30) * 10  # decay through Very Poor
        else:
            aqi = 220 - (h - 40) * 5  # below floor
        rows.append(
            Observation(
                station_id=station_id,
                observed_at=ts,
                pollutant="pm25",
                aqi=aqi,
            )
        )
    return rows


class ReadStore:
    """Process-local cache populated with deterministic stub episode/context."""

    def __init__(self) -> None:
        self.stations: list[StationStub] = list(DELHI_STATIONS)
        self.episodes: list[EpisodeObject] = []
        self.latest_context: ContextFeatureVector | None = None
        self._seed()

    def _seed(self) -> None:
        start = datetime(2024, 11, 5, 0, 0, tzinfo=timezone.utc)
        obs: list[Observation] = []
        for st in self.stations[:2]:
            obs.extend(_synthetic_observations(st.station_id, start=start))
        self.episodes = EpisodeAgent().detect(obs)

        station = self.stations[0]
        as_of = start + timedelta(hours=20)
        fires = [
            FirmsFireEvent(
                latitude=station.latitude + 1.5,
                longitude=station.longitude - 0.2,
                acq_datetime=as_of - timedelta(hours=6),
            ),
            FirmsFireEvent(
                latitude=station.latitude - 2.0,
                longitude=station.longitude + 1.0,
                acq_datetime=as_of - timedelta(hours=12),
            ),
        ]
        met = MeteoSnapshot(
            valid_at=as_of,
            wind_speed_ms=2.5,
            wind_direction_deg=320.0,  # NW, Punjabi fire corridor
            boundary_layer_height_m=280.0,
            relative_humidity_pct=72.0,
        )
        agent = ContextAgent(
            firms=MockFirmsClient(fires),
            meteo=MockMeteoClient(met),
        )
        self.latest_context = agent.build(
            location_id=station.station_id,
            latitude=station.latitude,
            longitude=station.longitude,
            as_of=as_of,
        )


store = ReadStore()
