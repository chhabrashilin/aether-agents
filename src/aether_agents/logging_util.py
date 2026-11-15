"""Structured logging helpers with episode_id / station_id / run_id fields."""

from __future__ import annotations

import logging
from typing import Any


def bind_fields(
    logger: logging.Logger,
    *,
    run_id: str | None = None,
    episode_id: str | None = None,
    station_id: str | None = None,
    **extra: Any,
) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that always emits structured identity fields."""

    payload: dict[str, Any] = {}
    if run_id is not None:
        payload["run_id"] = run_id
    if episode_id is not None:
        payload["episode_id"] = episode_id
    if station_id is not None:
        payload["station_id"] = station_id
    payload.update(extra)
    return logging.LoggerAdapter(logger, payload)


class StructuredFormatter(logging.Formatter):
    """Append known structured keys to the message for grep-friendly logs."""

    _KEYS = ("run_id", "episode_id", "station_id")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        parts: list[str] = []
        for key in self._KEYS:
            val = getattr(record, key, None)
            if val is not None:
                parts.append(f"{key}={val}")
        # LoggerAdapter merges extra into record.__dict__
        if parts:
            return f"{base} [{' '.join(parts)}]"
        return base


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure root logging once with structured field suffix."""

    root = logging.getLogger()
    if getattr(root, "_aether_structured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        StructuredFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root._aether_structured = True  # type: ignore[attr-defined]
