"""Library entrypoint used by the worker process and console script.

Each tick:
1. Run configured ingest (CPCB + OpenAQ when keys present).
2. Run full science pipeline in fixture mode when ``AETHER_WORKER_PIPELINE=fixture``,
   or live mode when ``AETHER_WORKER_PIPELINE=live`` (default: fixture for safe
   offline CIRRUS smoke; set live explicitly when keys + history exist).
"""

from __future__ import annotations

import logging
import time

from aether_agents.config import get_settings
from aether_agents.ingest.pipeline import run_ingest
from aether_agents.logging_util import bind_fields, configure_structured_logging
from aether_agents.pipeline.full import PipelineMode, run_full_pipeline

logger = logging.getLogger(__name__)


def run_once() -> None:
    """Single worker tick: ingest + optional full pipeline."""
    settings = get_settings()
    run_id = f"worker-{int(time.time())}"
    log = bind_fields(logger, run_id=run_id)
    log.info(
        "worker tick region=%s interval=%ss: starting ingest",
        settings.region,
        settings.worker_interval_seconds,
    )
    result = run_ingest(
        database_url=settings.database_url,
        data_gov_in_api_key=settings.data_gov_in_api_key,
        openaq_api_key=settings.openaq_api_key,
    )
    log.info(
        "worker ingest done cpcb=%s openaq_locs=%s openaq_meas=%s "
        "stations=%s observations=%s matches=%s",
        result.cpcb_records,
        result.openaq_locations,
        result.openaq_measurements,
        result.stations_upserted,
        result.observations_upserted,
        len(result.matches),
    )

    pipeline_mode = (settings.worker_pipeline_mode or "fixture").lower()
    if pipeline_mode in {"off", "none", "false", "0"}:
        log.info("worker pipeline skipped (AETHER_WORKER_PIPELINE=%s)", pipeline_mode)
        return

    mode = PipelineMode.LIVE if pipeline_mode == "live" else PipelineMode.FIXTURE
    pipe = run_full_pipeline(mode=mode, settings=settings, run_id=run_id)
    ep_id = pipe.episode.episode_id if pipe.episode else None
    log = bind_fields(logger, run_id=run_id, episode_id=ep_id, station_id=pipe.station_id)
    log.info(
        "worker pipeline done mode=%s episodes=%s dominant_refused=%s errors=%s",
        pipe.mode.value,
        pipe.episodes_detected,
        bool(pipe.science and pipe.science.critic.dominant_refused),
        len(pipe.errors),
    )


def main() -> None:
    settings = get_settings()
    configure_structured_logging(settings.log_level)
    logger.info(
        "aether-worker starting (ingest every %ss, pipeline=%s)",
        settings.worker_interval_seconds,
        settings.worker_pipeline_mode,
    )
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("worker tick failed")
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    main()
