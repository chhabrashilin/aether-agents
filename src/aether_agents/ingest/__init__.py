"""Data ingest clients (CPCB OGD, OpenAQ) and persistence pipeline."""

from aether_agents.ingest.cpcb import CpcbClient, parse_cpcb_records
from aether_agents.ingest.matching import match_stations, normalize_station_name
from aether_agents.ingest.openaq import OpenAqClient, parse_openaq_locations, parse_openaq_measurements
from aether_agents.ingest.pipeline import IngestResult, run_ingest, run_ingest_from_payloads

__all__ = [
    "CpcbClient",
    "IngestResult",
    "OpenAqClient",
    "match_stations",
    "normalize_station_name",
    "parse_cpcb_records",
    "parse_openaq_locations",
    "parse_openaq_measurements",
    "run_ingest",
    "run_ingest_from_payloads",
]
