# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Per-attempt LLM telemetry in `llm_calls.json`, including provider, model, timing, token usage, status, sanitized errors, and optional estimated cost
- Configurable `LLM_PRICING_JSON` table; provider prices are not hard-coded
- Run-linked telemetry for interest, behavior, and sentiment analysis, plus translation retry/fallback telemetry
- Optional `SQLiteStore` with structured `analysis_runs` and `llm_calls` tables, WAL mode, indexes, transactions, and generic Storage compatibility
- `STORAGE_BACKEND`, `SQLITE_PATH`, `--storage`, and `--sqlite-path` selection while retaining JSON as the default

### Changed
- Telemetry persistence is best-effort and cannot interrupt the primary analysis workflow
- Raw tweets, translations, caches, charts, and reports remain file-based when SQLite metadata storage is enabled

### Fixed
- Visualization commands now fail with an actionable `viz` dependency message instead of crashing when `matplotlib` is unavailable
- `xcrawler report --format png` now omits the HTML report, while the default and `--format html` retain the documented charts-plus-report behavior
- Missing input data now produces a non-zero exit status for network analysis and report generation

## [0.3.0] - 2025-07-06

### Added
- Engineering foundation: `pyproject.toml`, `.env.example`, CI, LICENSE, and test configuration
- Modular packages: `config`, `paths`, `storage`, `clients`, `services`, `utils`
- Unified CLI: `xcrawler fetch/translate/analyze/report/export`
- Execution plan, parameter validation, `--analysis-limit`, interest `--limit`
- Evidence traceability with `tweet_id` and `evidence_tweet_ids`
- Privacy by default: sensitive events hidden, HTML redaction
- Analysis run tracking: `analysis_runs.json` with model, params, timing, token usage
- `Storage` ABC + `JsonStore` implementation
- `LLMProvider` Protocol + `DeepSeekProvider` / `OpenAICompatibleProvider`
- `CONTRIBUTING.md`, `SECURITY.md`, `RELEASE_CHECKLIST.md`

### Changed
- Legacy scripts retained for backward compatibility
- All translation calls record usage metrics

### Fixed
- Critical bug in `fetch_more_history.py` (`combined` undefined)
- `analyze_sentiment.py` missing `raise SystemExit` in `__main__`
- `parse_twitter_datetime` improved error message for unknown formats
- `get_user_profile` narrowed exception handling
- Non-greedy JSON regex in `analyze_behavior.py` replaced with bracket-counting parser

## [0.2.0] - 2024

### Added
- User profile fetch (bio, followers, following, tweet count)
- Sentiment analysis (`analyze_sentiment.py`) with trend and pie charts
- CSV export (`export_csv.py`) for tweets, translations, and interests
- Batch translation (10 tweets per LLM call) with cache and retry
- Data visualization (`visualize.py`): 24h heatmap, language pie, interest bars, HTML report
- Network analysis (`analyze_network.py`): hashtags, mentions, co-occurrence
- Translation sync (`translate_sync.py`): incremental and force re-translate

## [0.1.0] - 2024

### Added
- Professional interest profiling (`analyze_pro.py`): AI-driven, evidence-based
- Time behavior analysis (`analyze_behavior.py`): hourly, weekday, life events
- Incremental fetch (`fetch_more_history.py` + `refetch_data.sh`)
- Multi-language translation with auto-detection and cache
- Multi-user support via `.env` configuration
