# xcrawler

[中文](https://github.com/yuanrengu/xcrawler/blob/main/README.md) | [English](https://github.com/yuanrengu/xcrawler/blob/main/README.en.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/yuanrengu/xcrawler/main/assets/note.png" alt="xcrawler report preview" width="800">
</p>

<p align="center">
  <a href="https://github.com/yuanrengu/xcrawler/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/yuanrengu/xcrawler/test.yml?branch=main&label=tests" alt="Tests"></a>
  <a href="https://github.com/yuanrengu/xcrawler/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
</p>

**xcrawler** is a local-first command-line toolkit that turns a public X/Twitter timeline into evidence-linked profiles, behavioral insights, charts, and reports.

- **Evidence-linked analysis** — interest labels, confidence scores, and supporting tweet IDs
- **Multilingual translation** — automatic language detection, batched translation, retries, and versioned caching
- **Multiple analysis views** — interests, activity patterns, life-event signals, sentiment, hashtags, and mentions
- **Privacy by default** — sensitive life-event details and evidence are hidden unless explicitly enabled
- **Local-first outputs** — JSON, SQLite metadata, CSV, PNG, and HTML remain on your machine
- **Defensive persistence** — atomic JSON writes, recovery backups, cross-process locks, private permissions, and path validation
- **Unified CLI** — one `xcrawler` command with modular storage and LLM provider layers

```bash
python3 -m pip install "xcrawler-ai[all]"
xcrawler demo
xcrawler fetch --user your_x_username
xcrawler analyze interest --user your_x_username
xcrawler report --user your_x_username
```

> Use xcrawler only for public content you are authorized to access. Do not use it for harassment, stalking, doxxing, discriminatory profiling, off-platform ad targeting, or attempts to obtain non-public personal information.

## Contents

- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Recommended workflows](#recommended-workflows)
- [CLI reference](#cli-reference)
- [Outputs](#outputs)
- [Reliability and data safety](#reliability-and-data-safety)
- [Storage and observability](#storage-and-observability)
- [Installation profiles](#installation-profiles)
- [Project structure](#project-structure)
- [Development and testing](#development-and-testing)
- [Troubleshooting](#troubleshooting)
- [Responsible use and privacy](#responsible-use-and-privacy)
- [Documentation and contributing](#documentation-and-contributing)

## Quick start

### No-key demo in 60 seconds

```bash
python3 -m pip install xcrawler-ai
xcrawler demo
```

The demo creates fictional JSON data and an evidence-linked HTML report under `demo_output/`. It does not make network or LLM requests.

Use a custom output directory if needed:

```bash
xcrawler demo --output ./sample-report
```

### Full installation

xcrawler requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install "xcrawler-ai[all]"
```

For Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Create a `.env` file in the directory where you run xcrawler:

```bash
touch .env
```

At minimum, configure:

```dotenv
X_BEARER_TOKEN=your_x_bearer_token
DEEPSEEK_API_KEY=your_deepseek_api_key
TARGET_USERNAME=your_x_username
```

Then run the primary workflow:

```bash
xcrawler fetch --user your_x_username
xcrawler analyze interest --user your_x_username
xcrawler report --user your_x_username
```

## Configuration

Copy [`.env.example`](https://github.com/yuanrengu/xcrawler/blob/main/.env.example) or define the following variables yourself.

| Variable | Default | Purpose |
|---|---|---|
| `X_BEARER_TOKEN` | — | X API bearer token used to fetch public posts |
| `DEEPSEEK_API_KEY` | — | DeepSeek/OpenAI-compatible key used for translation and AI analysis |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek-compatible API base URL |
| `LLM_MODEL` | `deepseek-chat` | Default model for translation and analysis |
| `OPENAI_API_KEY` | empty | Optional fallback for professional interest analysis |
| `OPENAI_BASE_URL` | `https://api.openai.com` | Optional OpenAI-compatible base URL |
| `TARGET_USERNAME` | `MiracleHe` | Target X username, without `@` |
| `TARGET_DATE` | `2024-01-01` | Oldest desired date for incremental history fetching |
| `TIMEZONE_OFFSET` | `8` | UTC offset used by behavior and visualization reports |
| `CACHE_DIR` | `cache` | Local cache and output directory |
| `STORAGE_BACKEND` | `json` | Run-metadata backend: `json` or `sqlite` |
| `SQLITE_PATH` | `cache/xcrawler.db` | Optional SQLite metadata database path |
| `LLM_PRICING_JSON` | unset | Optional per-model prices for local cost estimates |

Example optional pricing configuration:

```dotenv
LLM_PRICING_JSON={"deepseek-chat":{"input_per_million":0.0,"output_per_million":0.0}}
```

Prices are intentionally not built into the project because provider pricing changes. Always use current provider pricing when populating this field.

Command-line options such as `--user`, `--cache-dir`, `--model`, `--storage`, and `--sqlite-path` override the corresponding defaults for that invocation.

See [CONFIG_GUIDE.md](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md) for more configuration examples.

## Recommended workflows

### First analysis

```bash
# Fetch public posts, translate them, and run clustering when ML extras are installed
xcrawler fetch --user your_x_username

# Build an evidence-linked interest profile
xcrawler analyze interest --user your_x_username

# Analyze time patterns and non-sensitive life-event signals
xcrawler analyze behavior --user your_x_username

# Generate charts and an HTML report
xcrawler report --user your_x_username
```

### Low-quota or routine updates

```bash
# Forward and backward fetching share this HTTP request budget
xcrawler fetch-more --user your_x_username --pages 5 --target-date 2024-01-01

# Translate only records that are missing or stale
xcrawler translate --user your_x_username

# Refresh downstream analysis and reports
xcrawler analyze interest --user your_x_username
xcrawler report --user your_x_username
```

The compatibility helper `./refetch_data.sh -i` remains available, but the unified CLI is the recommended interface.

### Analyze existing local data only

```bash
xcrawler analyze interest --user your_x_username --limit 200
xcrawler analyze behavior --user your_x_username
xcrawler analyze sentiment --user your_x_username --top 10
xcrawler analyze network --user your_x_username --top 30
xcrawler report --user your_x_username
xcrawler export csv --user your_x_username
```

### Explicit snapshot replacement

Full fetches use archive/merge behavior by default. Use snapshot replacement only when that is intentionally required:

```bash
xcrawler fetch --user your_x_username --replace
```

Snapshot mode replaces the local raw and translated snapshot only after pagination completes and all required translations succeed. Partial results never overwrite a known-good snapshot.

## CLI reference

| Command | Purpose |
|---|---|
| `xcrawler demo` | Generate a local report from fictional data without API keys |
| `xcrawler fetch` | Fetch public posts, translate them, and optionally cluster them |
| `xcrawler fetch-more` | Incrementally fetch newer posts and older history |
| `xcrawler translate` | Synchronize or force-retranslate cached posts |
| `xcrawler analyze interest` | Build a professional evidence-linked interest profile |
| `xcrawler analyze behavior` | Analyze activity patterns and life-event signals |
| `xcrawler analyze sentiment` | Analyze sentiment distribution and trends |
| `xcrawler analyze network` | Analyze hashtag and mention signals |
| `xcrawler report` | Generate PNG charts and, by default, an HTML report |
| `xcrawler export csv` | Export local data to spreadsheet-safe CSV files |

### Common examples

```bash
# Limit fetch pages and downstream analysis size
xcrawler fetch --user alice --pages 3 --analysis-limit 200

# Fetch without translation
xcrawler fetch --user alice --no-translate

# Force retranslation; the primary file changes only if all requested items succeed
xcrawler translate --user alice --force

# Choose a model and metadata backend for an analysis run
xcrawler analyze interest --user alice --model deepseek-chat --storage sqlite

# Store SQLite metadata at an explicit path
xcrawler analyze sentiment --user alice --storage sqlite --sqlite-path state/xcrawler.db

# PNG charts only; omit the HTML report
xcrawler report --user alice --format png

# Include sensitive event evidence only after an explicit privacy decision
xcrawler report --user alice --include-sensitive-events

# Export only translations
xcrawler export csv --user alice --type translations --output ./exports

# Show dispatch, retry, and storage diagnostics without printing secrets
xcrawler fetch --user alice --verbose
```

Run `xcrawler <command> --help` for every option. Numeric CLI values are validated, including positive page/batch/limit values, non-negative intervals, and temperatures between 0 and 2.

Legacy script entry points such as `main.py`, `fetch_more_history.py`, and `analyze_pro.py` remain available for compatibility, but new workflows should use `xcrawler`.

## Outputs

The default output root is `cache/`.

| Path | Contents |
|---|---|
| `cache/{username}_raw_tweets.json` | Validated public post records |
| `cache/{username}_translated.json` | Original text, translation, language, timestamps, and fingerprints |
| `cache/{username}_interest_profile.json` | Interest labels, confidence, keywords, and evidence tweet IDs |
| `cache/{username}_behavior.json` | Activity patterns and privacy-filtered life-event signals |
| `cache/{username}_sentiment.json` | Sentiment results; failed/unparseable items remain `unknown` |
| `cache/{username}_network.json` | Hashtag and mention analysis |
| `cache/{username}_fetch_status.json` | Incremental request, retry, completion, and stop-reason state |
| `cache/translation_cache.json` | Versioned translation cache keyed by provider/model/prompt context |
| `cache/analysis_runs.json` | Analysis-run metadata when JSON storage is selected |
| `cache/llm_calls.json` | Per-call LLM metadata when JSON storage is selected |
| `cache/xcrawler.db` | Structured run and LLM-call metadata when SQLite is selected |

Reports and charts default to `cache/charts/`:

- `{username}_hourly.png`
- `{username}_weekday.png`
- `{username}_language.png`
- `{username}_interests.png`
- `{username}_hashtags.png`
- `{username}_mentions.png`
- `{username}_sentiment.png`
- `{username}_sentiment_pie.png`
- `{username}_report.html`

CSV exports default to `cache/csv/`:

- `{username}_tweets.csv`
- `{username}_translations.csv`
- `{username}_interests.csv`

CSV fields with spreadsheet formula prefixes are escaped, and tweet IDs are exported as text to prevent numeric rounding in spreadsheet applications.

## Reliability and data safety

### Fetch semantics

- Full fetches default to **archive mode**: records merge by tweet ID, so a remote deletion does not silently delete local history.
- `xcrawler fetch --replace` enables **snapshot mode** and commits raw and translated files together only after a complete fetch and successful translation.
- A page limit reached while another `next_token` exists is partial, not complete.
- X API HTTP 200 responses that contain errors, malformed pagination metadata, or repeated pagination tokens are rejected.
- Forward and backward incremental phases persist independently, so a later failure does not discard a successfully saved earlier phase.
- `fetch-more --pages` is a shared HTTP request budget across forward fetching, backward fetching, and retries.
- Incremental exit codes are `0` for complete success, `1` for failure, and `2` for safely persisted but incomplete progress.

### Translation integrity

- Translation records include source-content and configuration fingerprints. Changed source text or model/prompt context triggers retranslation.
- The translation cache is isolated by provider, model, target language, and prompt version.
- Forced retranslation is all-or-nothing for the primary translated file.
- A failed or unparseable sentiment batch is marked `unknown`, never silently counted as neutral.

### Local persistence security

- JSON writes use temporary files, `fsync`, atomic replacement, and `.bak` recovery files.
- Managed JSON reads, writes, recovery, appends, and multi-file transactions use cross-process advisory locks with a five-second default timeout.
- `append_json_record()` holds one lock across its complete read-modify-write sequence; multi-file transactions acquire locks in canonical path order to avoid deadlocks.
- Persistent `.lock` files are safe to leave in place. The operating system releases the actual lock when a process exits or crashes.
- On POSIX systems, new cache/output directories use `0700`; managed JSON, backup, lock, SQLite, CSV, HTML, and PNG files use `0600`.
- Existing parent directory permissions are never changed automatically. xcrawler warns when they appear too broad.
- Explicitly symlinked cache roots are supported, while managed files, backups, lock files, SQLite sidecars, path traversal, and unsafe link replacement are rejected.
- Windows permission enforcement is best-effort and should be paired with appropriate filesystem ACLs.

Archive updates and shared cache saves re-read and merge the latest disk data under one lock. Network requests and model calls run outside the lock; an entire workflow is not one transaction. Explicit snapshot replacement still replaces the selected data.

Translation cache writes overwrite existing keys only for translations generated by the current process since its last successful save. Unchanged entries from an older snapshot cannot revert another process's correction. If both processes generate a new value for the same key, the last commit wins. Snapshot replacement checks for an optional translated file while holding both file locks.

## Storage and observability

JSON is the default metadata backend and is appropriate for personal or low-frequency use:

```dotenv
STORAGE_BACKEND=json
```

For structured run and LLM-call metadata, enable SQLite:

```dotenv
STORAGE_BACKEND=sqlite
SQLITE_PATH=cache/xcrawler.db
```

Or select it for one invocation:

```bash
xcrawler analyze interest --user alice --storage sqlite
```

SQLite enables WAL mode, transactions, a busy timeout, structured `analysis_runs` and `llm_calls` tables, and query indexes. Raw posts, translations, charts, and reports remain ordinary local files. JSON and SQLite metadata are not migrated automatically when switching backends.

Analysis and translation workflows record operational metadata such as provider, model, timestamps, status, latency, token counts, failed batches, and optional cost estimates. Prompts and model response bodies are not stored in the metadata database.

## Installation profiles

| Profile | PyPI install | Source install | Includes |
|---|---|---|---|
| Base | `pip install xcrawler-ai` | `pip install -e .` | CLI, fetching, translation, export, demo |
| ML | `pip install "xcrawler-ai[ml]"` | `pip install -e ".[ml]"` | Embeddings and K-Means clustering |
| Visualization | `pip install "xcrawler-ai[viz]"` | `pip install -e ".[viz]"` | Matplotlib charts and reports |
| All | `pip install "xcrawler-ai[all]"` | `pip install -e ".[all]"` | ML and visualization features |
| Test | `pip install "xcrawler-ai[test]"` | `pip install -e ".[test]"` | pytest, coverage, Hypothesis |
| Development | `pip install "xcrawler-ai[dev]"` | `pip install -e ".[dev]"` | Tests, Ruff, mypy, build, Twine |

If the ML extra is absent, `xcrawler fetch` still saves fetched and translated data, then skips clustering with an actionable message. Visualization commands require the `viz` or `all` profile.

## Project structure

```text
xcrawler/
├── xcrawler/
│   ├── cli.py                    # Unified command-line interface
│   ├── config.py                 # Environment configuration
│   ├── paths.py                  # Safe paths and private permissions
│   ├── privacy_guard.py          # Sensitive-evidence redaction
│   ├── clients/                  # X API and LLM clients
│   ├── llm/                      # LLM provider abstraction
│   ├── services/                 # Fetch, translation, evidence, telemetry
│   ├── storage/
│   │   ├── base.py               # Storage contract
│   │   ├── factory.py            # Backend selection
│   │   ├── file_lock.py          # Cross-platform advisory locks
│   │   ├── json_store.py         # Atomic JSON persistence and recovery
│   │   └── sqlite_store.py       # Structured metadata storage
│   └── utils/                    # Validation, text, time, logging
├── main.py                       # Fetch, translate, and cluster workflow
├── fetch_more_history.py         # Incremental forward/backward fetching
├── translate_sync.py             # Incremental and forced translation
├── analyze_pro.py                # Interest profile analysis
├── analyze_behavior.py           # Behavior and life-event analysis
├── analyze_sentiment.py          # Sentiment analysis
├── analyze_network.py            # Hashtag and mention analysis
├── visualize.py                  # Charts and HTML reports
├── export_csv.py                 # Spreadsheet-safe CSV export
├── tests/                        # Unit, integration, property, and concurrency tests
├── pyproject.toml
└── .env.example
```

## Development and testing

```bash
git clone https://github.com/yuanrengu/xcrawler.git
cd xcrawler
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"

ruff check .
mypy xcrawler
python3 -m pytest
python3 -m build
```

The test suite covers text processing, translation contracts, CLI validation, privacy redaction, fetch transactions, pagination properties, JSON recovery and concurrency, SQLite compatibility, packaging, and coverage gates. CI runs pytest across Python 3.10–3.14 in addition to quality, coverage, and package jobs.

## Troubleshooting

### Missing optional dependency

Install the feature profile required by the command:

```bash
python3 -m pip install "xcrawler-ai[all]"
```

For source development, use `pip install -e ".[ml]"`, `pip install -e ".[viz]"`, or `pip install -e ".[all]"`.

### No cached input data

Confirm that `TARGET_USERNAME`, `--user`, and `--cache-dir` refer to the same user and directory used during fetching. Start with:

```bash
xcrawler fetch --user your_x_username --pages 1
```

### X API rate limits or HTTP 429

Begin with a small request budget and prefer incremental updates:

```bash
xcrawler fetch-more --user your_x_username --pages 3
```

The request engine uses bounded retries and respects rate-limit reset information when available.

### Translation failure

Check `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `LLM_MODEL`, then rerun with diagnostics:

```bash
xcrawler translate --user your_x_username --verbose
```

### Partial exit code 2

Exit code `2` means progress was safely persisted but the requested fetch range is incomplete. Automation should not treat it as complete success; rerun with an appropriate request budget.

### Directory permission warning

xcrawler does not modify a pre-existing parent directory. After confirming it should be private, tighten it manually on POSIX:

```bash
chmod 700 cache
```

## Responsible use and privacy

xcrawler is intended for learning, research, personal content review, and authorized social-media analysis of public content.

Privacy defaults include:

- sensitive life-event details and supporting tweet IDs are hidden by default;
- HTML reports hide sensitive-event source text unless `--include-sensitive-events` is passed;
- email addresses, phone numbers, and address-like evidence receive basic redaction;
- generated profiles are probabilistic summaries, not verified facts;
- local files use private permissions where the operating system supports them.

Review generated JSON, HTML, and CSV before sharing. Public source material can still contain personal or sensitive information even when automated redaction is enabled.

To remove local outputs:

```bash
rm -rf cache/
rm -rf cache_backup/
```

Report security or privacy vulnerabilities privately according to [SECURITY.md](https://github.com/yuanrengu/xcrawler/blob/main/SECURITY.md). Do not publish exploitable details in a public issue.

## Documentation and contributing

- [Quick start](https://github.com/yuanrengu/xcrawler/blob/main/QUICK_START.md)
- [Configuration guide](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md)
- [Incremental fetching](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md)
- [Behavior analysis](https://github.com/yuanrengu/xcrawler/blob/main/BEHAVIOR_ANALYSIS.md)
- [Changelog](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md)
- [Contributing guide](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md)
- [Security policy](https://github.com/yuanrengu/xcrawler/blob/main/SECURITY.md)
- [Release checklist](https://github.com/yuanrengu/xcrawler/blob/main/RELEASE_CHECKLIST.md)

Issues and pull requests are welcome. Please read the contributing and security guidance before proposing changes that affect persistence, privacy defaults, or generated evidence.

## License

[MIT](https://github.com/yuanrengu/xcrawler/blob/main/LICENSE)
