"""ContextAgent: fire / meteorology / Delhi calendar feature vector (deterministic)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aether_agents.agents.base.types import ContextFeatureVector
from aether_agents.context.calendar_delhi import DelhiCalendar
from aether_agents.context.firms import (
    FirmsClient,
    FirmsClientProtocol,
    FirmsFireEvent,
    is_upwind,
)
from aether_agents.context.meteo import MeteoClient, MeteoClientProtocol, MeteoSnapshot


class ContextAgent:
    """Build a structured context feature vector for a location and time.

    FIRMS and Open-Meteo clients are injectable so tests never need live keys.
    """

    def __init__(
        self,
        *,
        firms: FirmsClientProtocol | None = None,
        meteo: MeteoClientProtocol | None = None,
        calendar: DelhiCalendar | None = None,
        fire_radius_km: float = 250.0,
        upwind_sector_half_width_deg: float = 60.0,
    ) -> None:
        self.firms = firms if firms is not None else FirmsClient()
        self.meteo = meteo if meteo is not None else MeteoClient()
        self.calendar = calendar or DelhiCalendar()
        self.fire_radius_km = fire_radius_km
        self.upwind_sector_half_width_deg = upwind_sector_half_width_deg

    def build(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        as_of: datetime | None = None,
    ) -> ContextFeatureVector:
        when = as_of or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        met = self.meteo.fetch_snapshot(
            latitude=latitude,
            longitude=longitude,
            as_of=when,
        )
        fires = self.firms.fetch_fires(
            latitude=latitude,
            longitude=longitude,
            radius_km=self.fire_radius_km,
            days=3,
            as_of=when,
        )
        upwind_24 = self._count_upwind(
            fires,
            station_lat=latitude,
            station_lon=longitude,
            wind_direction_deg=met.wind_direction_deg,
            as_of=when,
            lookback=timedelta(hours=24),
        )
        upwind_72 = self._count_upwind(
            fires,
            station_lat=latitude,
            station_lon=longitude,
            wind_direction_deg=met.wind_direction_deg,
            as_of=when,
            lookback=timedelta(hours=72),
        )
        cal = self.calendar.features(when)
        completeness = self._completeness(met, fires_queried=True)

        return ContextFeatureVector(
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            valid_at=met.valid_at if met.valid_at else when,
            upwind_fire_count_24h=upwind_24,
            upwind_fire_count_72h=upwind_72,
            wind_speed_ms=met.wind_speed_ms,
            wind_direction_deg=met.wind_direction_deg,
            boundary_layer_height_m=met.boundary_layer_height_m,
            relative_humidity_pct=met.relative_humidity_pct,
            is_delhi_winter_season=bool(cal["is_delhi_winter_season"]),
            is_festival=bool(cal["is_festival"]),
            festival_name=cal["festival_name"] if isinstance(cal["festival_name"], str) else None,
            is_holiday=bool(cal["is_holiday"]),
            holiday_name=cal["holiday_name"] if isinstance(cal["holiday_name"], str) else None,
            feature_completeness=completeness,
            extras={
                "fire_radius_km": self.fire_radius_km,
                "upwind_sector_half_width_deg": self.upwind_sector_half_width_deg,
                "fire_events_total": len(fires),
            },
        )

    def _count_upwind(
        self,
        fires: list[FirmsFireEvent],
        *,
        station_lat: float,
        station_lon: float,
        wind_direction_deg: float | None,
        as_of: datetime,
        lookback: timedelta,
    ) -> int:
        start = as_of - lookback
        count = 0
        for ev in fires:
            if ev.acq_datetime is not None:
                ts = ev.acq_datetime
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < start or ts > as_of:
                    continue
            if is_upwind(
                station_lat=station_lat,
                station_lon=station_lon,
                fire_lat=ev.latitude,
                fire_lon=ev.longitude,
                wind_direction_deg=wind_direction_deg,
                sector_half_width_deg=self.upwind_sector_half_width_deg,
            ):
                count += 1
        return count

    @staticmethod
    def _completeness(met: MeteoSnapshot, *, fires_queried: bool) -> float:
        fields = [
            met.wind_speed_ms,
            met.wind_direction_deg,
            met.boundary_layer_height_m,
            met.relative_humidity_pct,
        ]
        present = sum(1 for f in fields if f is not None)
        # Fire query success contributes one slot (counts may be zero legitimately).
        total = len(fields) + 1
        present += 1 if fires_queried else 0
        return present / total
