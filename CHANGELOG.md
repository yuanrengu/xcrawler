# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Serialize JSON reads, writes, record appends, recovery, and multi-file transactions with cross-platform advisory lock files, bounded timeouts, and link-swap protection
- Create new local cache/export directories with POSIX `0700` and managed data files with `0600`, while warning instead of modifying pre-existing parent directories
- Reject path traversal in JSON storage keys and file-level symlinks for managed JSON, backup, SQLite, CSV, HTML, and PNG targets
- Split the monolithic test suite by responsibility and enforce independent coverage floors for full fetch, incremental fetch, and X API pagination code
- Add a full-fetch transaction matrix plus property-based timeline response contract tests
- Add a reproducible development extra, type-checking CI, Python 3.13/3.14 coverage, and Python dependency updates
- Make the unified CLI `--verbose` flag emit command, HTTP retry, and JSON storage diagnostics

### Fixed
- Sort mixed-precision tweet timestamps chronologically with numeric ID tie-breaking for incremental boundaries
- Isolate translation caches and record fingerprints by normalized API endpoint identity
- Reject bare batch labels in new and cached translations; sync retries affected legacy records
- Reject empty profile/provider responses before recording success or saving reports
- Correct forced-retranslation restart guidance and verify recovery through actual fetch/sync command entry points
- Checkpoint translation caches after each batch so interrupted fetch/sync runs can reuse completed work
- Revalidate legacy translations without configuration fingerprints and preserve old results until successful replacement
- Prevent stale translation cache snapshots from reverting concurrent corrections and retain pending changes after failed saves
- Check optional translated-file existence under both snapshot locks during no-translation replacement
- Hold JSON locks across business-level read/merge/write updates for tweets, translations, and shared caches
- Reject empty translation responses and ignore existing blank cache entries so retries can recover
- Clean up multi-file transaction temporary files when serialization or flushing fails
- Treat a full-fetch page limit with a remaining `next_token` as partial instead of a complete snapshot
- Reject HTTP 200 X API responses containing errors, malformed pagination metadata, or repeated pagination tokens
- Prevent partial full-fetch results from entering `--replace`; archive mode may save them but exits with status 2
- Make incremental fetch exit statuses explicit: complete success is 0, failure is 1, and safely persisted partial progress is 2
- Reuse the full-fetch timeline response contract for incremental HTTP 200 errors, malformed metadata, and pagination-token cycles
- Record incremental `complete`, `has_more`, and per-phase completion fields without losing successfully persisted earlier phases

## [0.4.2] - 2026-07-13

### Fixed
- Use an absolute HTTPS URL for the README preview image so it renders on both GitHub and PyPI
- Convert README language, license, configuration, contribution, security, and release-document links to absolute GitHub URLs for PyPI compatibility
- Update the English quick-start installation commands to use the published `xcrawler-ai` distribution

## [0.4.1] - 2026-07-12

### Fixed
- Full timeline fetching now retries transient failures and fails explicitly when any later page cannot be fetched, instead of returning a partial result as complete
- `xcrawler fetch --replace` commits raw and translated snapshots together and preserves both previous files when translation is incomplete or either replacement fails
- Translation commands now return a non-zero status when requested translations are partially or completely unsuccessful
- Incremental forward/backward phases persist independently and record structured success/partial/failed status with request, data-page, retry, and stop-reason metrics
- Raw tweet inputs are schema-validated before merge; missing IDs, invalid timestamps, non-string text, and duplicate IDs are rejected instead of silently dropped
- Translation records include source and configuration fingerprints, causing changed source text to be retranslated
- Successful translation runs clear stale failure lists

### Changed
- `fetch-more --pages` is now explicitly a shared HTTP request budget that includes retries
- Full fetch behavior is documented as archive mode by default and snapshot mode with `--replace`
- Full and incremental X API operations share one retry, rate-limit, and error-classification engine
- `--replace --no-translate` filters retained translations to the new raw snapshot instead of leaving stale records
- CI now enforces a coverage floor and performs scheduled base, visualization, and ML installation smoke tests
- The PyPI distribution is named `xcrawler-ai` (the CLI and import package remain `xcrawler`) and uses Trusted Publishing

## [0.4.0] - 2026-07-11

### Added
- Per-attempt LLM telemetry in `llm_calls.json`, including provider, model, timing, token usage, status, sanitized errors, and optional estimated cost
- Configurable `LLM_PRICING_JSON` table; provider prices are not hard-coded
- Run-linked telemetry for interest, behavior, and sentiment analysis, plus translation retry/fallback telemetry
- Optional `SQLiteStore` with structured `analysis_runs` and `llm_calls` tables, WAL mode, indexes, transactions, and generic Storage compatibility
- `STORAGE_BACKEND`, `SQLITE_PATH`, `--storage`, and `--sqlite-path` selection while retaining JSON as the default
- No-key `xcrawler demo` command with fictional local data and an evidence-linked HTML report
- Strict X username, date, timezone, storage backend, and derived-path validation
- Wheel/sdist build and clean-install smoke tests in CI, Dependabot configuration, and a pull request template
- English project overview in `README.en.md`

### Changed
- Telemetry persistence is best-effort and cannot interrupt the primary analysis workflow
- Raw tweets, translations, caches, charts, and reports remain file-based when SQLite metadata storage is enabled
- Full fetches merge with existing history by default; `--replace` explicitly rebuilds the snapshot
- Forced retranslation is all-or-nothing and preserves the primary file when any item fails
- The legacy `refetch_data.sh` entry point is now a thin wrapper around the unified CLI
- Base installations save fetched and translated data, then skip ML clustering with an actionable message when `.[ml]` is unavailable

### Fixed
- Visualization commands now fail with an actionable `viz` dependency message instead of crashing when `matplotlib` is unavailable
- `xcrawler report --format png` now omits the HTML report, while the default and `--format html` retain the documented charts-plus-report behavior
- Missing input data now produces a non-zero exit status for network analysis and report generation
- Incremental fetch failures no longer appear as successful no-update runs; timeouts, 5xx responses, and rate limits use bounded retries
- Network and sentiment analysis failures are recorded as failed analysis runs when storage remains available

## [0.3.0] - 2026-07-06

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
