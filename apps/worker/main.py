"""Worker process entrypoint (scheduled ingest + agent runs).

Interval is controlled by ``AETHER_WORKER_INTERVAL_SECONDS`` (default 900).
Each tick runs CPCB + OpenAQ ingest when API keys are present; missing keys
are logged and skipped so the loop stays healthy in local/dev without secrets.
"""

from aether_agents.worker import main

if __name__ == "__main__":
    main()
