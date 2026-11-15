# Contributing

## Scope

This repository builds reproducible episode intelligence for Delhi–NCT winter smog. Prefer small, testable changes over large speculative refactors.

## Development setup

1. Create a virtual environment and install editable deps: `pip install -e ".[dev]"`.
2. Copy `.env.example` to `.env` and fill keys as needed (never commit secrets).
3. Run unit tests: `pytest`.
4. Lint: `ruff check src apps tests`.

## Code conventions

- Python 3.11+, type hints on public functions.
- Keep numerical episode detection classical/stats/ML; LLM use only for reasoning over structured evidence in Attribution / Critic / Advisory.
- Gaps in observation data stay gaps; no silent imputation in ingest.
- Human researcher voice in docs, UI copy, commit messages, and citations. Do not add tool co-authorship trailers or generated-by footers.

## Pull requests

- One focused change per PR when possible.
- Include tests for ingest parsers, episode rules, and API contracts.
- Update `docs/` when behavior or CIRRUS deployment assumptions change.

## Security

- No secrets in Git, Helm defaults, or CI logs.
- Prefer External Secrets patterns documented in `docs/cirrus-onboarding.md`.
