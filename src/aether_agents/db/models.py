"""SQLAlchemy ORM models for stations, observations, and raw ingest payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for AetherAgents tables."""


class Station(Base):
    """Monitoring station, possibly linked across CPCB and OpenAQ identities."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country: Mapped[str] = mapped_column(String(64), default="IN", nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpcb_station_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    openaq_location_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    source_primary: Mapped[str] = mapped_column(String(32), nullable=False, default="cpcb")
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    observations: Mapped[list[Observation]] = relationship(back_populates="station")

    __table_args__ = (
        Index("ix_stations_city_state", "city", "state"),
    )


class Observation(Base):
    """Normalized pollutant observation at a station and timestamp.

    Gaps are intentional: missing hours are not interpolated. Callers that need
    continuous series must treat absent rows as missing data.
    """

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    pollutant: Mapped[str] = mapped_column(String(32), nullable=False)
    # Value semantics: "concentration" (µg/m³ or ppm) or "sub_index" (CPCB AQI sub-index 0–500).
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_semantics: Mapped[str] = mapped_column(String(32), nullable=False, default="concentration")
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # cpcb | openaq
    qa_flags: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    raw_payload_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("raw_payloads.id"), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    station: Mapped[Station] = relationship(back_populates="observations")
    raw_payload: Mapped[Optional[RawPayload]] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "observed_at",
            "pollutant",
            "source",
            "value_semantics",
            name="uq_observation_identity",
        ),
        Index("ix_observations_pollutant_time", "pollutant", "observed_at"),
    )


class RawPayload(Base):
    """Immutable raw API response retained for provenance and reprocessing."""

    __tablename__ = "raw_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(64), default="application/json", nullable=False)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    observations: Mapped[list[Observation]] = relationship(back_populates="raw_payload")
