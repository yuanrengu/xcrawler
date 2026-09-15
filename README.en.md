# xcrawler

[中文](https://github.com/yuanrengu/xcrawler/blob/main/README.md) | [English](https://github.com/yuanrengu/xcrawler/blob/main/README.en.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/yuanrengu/xcrawler/main/assets/note.png" alt="xcrawler feature illustration, not an actual report screenshot" width="800">
</p>

<p align="center">Feature illustration. Actual outputs are local JSON, CSV, PNG and HTML files.</p>

[![Tests](https://img.shields.io/github/actions/workflow/status/yuanrengu/xcrawler/test.yml?branch=main&label=tests)](https://github.com/yuanrengu/xcrawler/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/yuanrengu/xcrawler/blob/main/LICENSE)

**xcrawler** is a command-line tool for public X/Twitter timelines: fetch posts, translate them into Chinese, analyze interests and behavior, and export local reports for review.

- **Interests**: labels, model confidence and tweet-ID evidence; optional vector clustering.
- **Behavior and sentiment**: posting-time distributions, life-event detection and batch sentiment classification.
- **Content networks**: hashtag/mention frequencies and co-occurrence statistics.
- **Local outputs**: data, charts and reports, with incremental merging, translation caches and run records.

Use it for personal content reviews, authorized public-account research and content analysis. Evidence IDs make claims traceable; they do not prove that model conclusions are correct.

> Results are stored locally. Translation and AI analysis send text to the configured model service. The demo makes no network or model requests. Process only public content you are authorized to access; do not use this tool for harassment, stalking, doxxing or discriminatory profiling.

This document describes the current source. The inspected PyPI `0.4.2` wheel does not include the latest report privacy, sampled-evidence validation and analysis exit-code fixes described here. Use [source installation](#source-development) for those behaviors. The source also currently reports `0.4.2`, so `xcrawler --version` alone cannot identify these fixes. See the [changelog](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md); source additions are listed under `Unreleased`.

## Contents

- [No-key demo](#no-key-demo)
- [Analyze a real account](#analyze-a-real-account)
- [Commands and prerequisites](#commands-and-prerequisites)
- [Updates and snapshots](#updates-and-snapshots)
- [Outputs and evidence](#outputs-and-evidence)
- [Configuration and storage](#configuration-and-storage)
- [Privacy and data boundaries](#privacy-and-data-boundaries)
- [Troubleshooting](#troubleshooting)
- [Source development](#source-development)
- [Documentation and contributing](#documentation-and-contributing)

## No-key demo

Python 3.10+ is required. On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install xcrawler-ai
xcrawler demo
```

On Windows PowerShell, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`. Subsequent `python` and `xcrawler` commands are the same.

Open `demo_output/xcrawler_demo_report.html` in a browser. The demo generates JSON and evidence HTML from built-in fictional data. It performs no real analysis and generates no full PNG chart set; no API key, ML or visualization extra is needed.

```bash
xcrawler demo --output ./sample-report
xcrawler --help
```

The demo has only a few records and is not suitable as-is for interest or sentiment analysis, which require at least five texts.

## Analyze a real account

### Install the required extras

In the activated environment, add visualization support for the fetch, professional-interest and report workflow:

```bash
python -m pip install "xcrawler-ai[viz]"
```

| Installation | Purpose |
|---|---|
| `xcrawler-ai` | CLI, fetching, translation, AI analysis, CSV and demo |
| `xcrawler-ai[viz]` | Adds plotting required for reports, network and sentiment commands |
| `xcrawler-ai[ml]` | Adds vector-clustering dependencies |
| `xcrawler-ai[all]` | Adds both ML and visualization dependencies |

ML dependencies are large and the first clustering run may download a model. Without ML, clustering is skipped after successful full fetching and translation. Professional interest analysis (`analyze interest`) does not require ML.

### Configure credentials

Fetching requires an X API bearer token. Translation and default AI analysis require a DeepSeek or compatible-service key. Real requests may incur charges; access limits depend on your service account.

On macOS/Linux, replace the placeholders and set these variables in the current terminal:

```bash
export X_BEARER_TOKEN="your_x_bearer_token"
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export TARGET_USERNAME="your_x_username"
```

On Windows PowerShell:

```powershell
$env:X_BEARER_TOKEN="your_x_bearer_token"
$env:DEEPSEEK_API_KEY="your_deepseek_api_key"
$env:TARGET_USERNAME="your_x_username"
```

Credential entry may remain in shell history. Configure credentials in your own trusted environment; never commit keys, `.env` or analysis data.

**Current `.env` limitation:** the code calls `load_dotenv()` without a path. Discovery depends on the package location and does not reliably load an arbitrary working directory's `.env`. Prefer explicit environment variables for an independent installation. Source-root `.env` usage and precedence are covered in the [configuration guide](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md).

### Run the workflow

Run each command separately in the same configured terminal:

```bash
# Start with a small page limit; inspect output and exit status after each command
xcrawler fetch --pages 3

# Analyze existing translations
xcrawler analyze interest --limit 300
xcrawler analyze behavior

# Render existing results; this does not rerun analysis
xcrawler report
```

If more pages remain at the fetch limit, archive mode saves partial data and exits with `2`. Fetch more, or explicitly accept the current sample range before analyzing it. Interest analysis requires at least five usable texts. Fewer than ten translated records also causes clustering to be skipped after a complete fetch.

The report defaults to `cache/charts/{username}_report.html`. If you use `--user`, supply the same account to subsequent commands: a command-line override does not change defaults for the next invocation.

## Commands and prerequisites

Inputs below are local files for the selected account. Use `--cache-dir` to choose their directory; the demo instead uses `--output`.

| Command | Input/purpose | API configuration | Optional dependency |
|---|---|---|---|
| `demo` | Fictional data → evidence HTML | None | None |
| `fetch` | X timeline → raw, translations; clustering when applicable | X + DeepSeek-compatible configuration | `ml` for clustering |
| `fetch --no-translate` | Fetch raw only; skip translation and analysis | X | None |
| `fetch-more` | Update raw; can also start fetching without prior data | X | None |
| `translate` | Raw → missing or stale translations | DeepSeek-compatible configuration when translation calls are needed | None |
| `analyze interest` | Translations → professional interests; at least five texts | DeepSeek, or OpenAI when the DeepSeek key is empty | None |
| `analyze behavior` | Raw + translations → time statistics, events and summary | DeepSeek-compatible configuration | None |
| `analyze sentiment` | Translations → sentiment; at least five texts | DeepSeek-compatible configuration | `viz` |
| `analyze network` | Raw → tag/mention frequencies, co-occurrence and bar charts | None | `viz` |
| `report` | Raw required; adds available translations, interests and events | None | `viz` |
| `export csv` | Existing raw, translations or interest profile | None | None |

```bash
xcrawler fetch --user alice --pages 10 --batch-size 10 --analysis-limit 500
xcrawler analyze interest --user alice --limit 100 --temperature 0
xcrawler analyze network --user alice --top 20
xcrawler analyze sentiment --user alice --top 10
xcrawler report --user alice --format png --output ./charts
xcrawler export csv --user alice --type translations --output ./csv
xcrawler fetch --help
```

Leaf commands support `--verbose`. Not all commands support `--model` or storage options; check their `--help`. Record limits are not token budgets, so long texts can still exceed model context limits.

## Updates and snapshots

### Routine updates

```bash
xcrawler fetch-more --pages 10 --target-date 2024-01-01
xcrawler translate
xcrawler analyze interest
xcrawler analyze behavior
xcrawler report
```

Check each result and rerun the analyses you need. `fetch-more` only updates raw data; skipping translation or analysis can leave old conclusions in a newly rendered report. Its `--pages` budget is shared across forward fetching, backward fetching and retries; a request is not guaranteed to return 100 posts.

Neither a target date nor pagination completion guarantees all account history. Available data depends on API scope, permissions, deleted content and request budgets.

### Merge versus replacement

- `fetch` merges by tweet ID by default. Remote deletion does not automatically remove local history.
- `fetch --replace` explicitly replaces a snapshot: raw and translated files are committed after complete pagination and successful translation. Incomplete pagination does not overwrite them.
- `fetch --replace --no-translate` performs no translation. After a complete fetch, it replaces raw and removes existing translated records whose IDs are absent from the new snapshot; it does not create a missing translation file.
- The source wrapper `./refetch_data.sh` dispatches to `fetch --replace`; `./refetch_data.sh -i` dispatches to `fetch-more`. It does not add `cache_backup/` backups, install dependencies or validate data. Prefer the CLI for new workflows.

### Exit status

| Command/situation | Exit code and result |
|---|---|
| `fetch`, complete fetch and successful translation | `0`; missing ML or fewer than ten translations can also skip clustering and return `0` |
| `fetch`, page limit with more pages remaining | `2`; archive saves partial data, replacement refuses overwrite |
| `fetch`, partial translation failure | `1`; archive can retain successful work, replacement preserves the old snapshot |
| `fetch-more` | Complete `0`, failure `1`, safely saved but incomplete range `2` |
| `analyze interest` | Success `0`, analysis or persistence failure `1` |
| `analyze behavior` | Complete `0`; useful time statistics but failed events/summary `2`; execution or persistence failure `1` |
| `analyze sentiment` | Complete `0`, partial batches `2`; all batches fail `1`, preserving old results and charts |
| `translate` | Complete/nothing to update `0`; unresolved translation failures `1` |

A file's existence does not prove a successful run. CSV export may exit normally even when no input was available; inspect messages and actual artifacts. See the [fetch guide](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md) for recovery details.

## Outputs and evidence

Paths are relative to the working directory; change the cache root with `CACHE_DIR` or `--cache-dir`.

| Default path | Contents |
|---|---|
| `cache/{username}_raw_tweets.json` | Preserved raw tweet records |
| `cache/{username}_translated.json` | Cleaned source text, Chinese translation, ID, timestamp and fingerprints |
| `cache/{username}_interest_profile.json` | Professional interest profile used by reports and interest CSV |
| `cache/{username}_profile.json` | Fetched account information |
| `cache/{username}_analysis.json` | Optional clustering and summary, distinct from the professional profile |
| `cache/{username}_behavior.json` | Time statistics, life events and summary |
| `cache/{username}_sentiment.json` | Labels, distribution and failed batch count |
| `cache/{username}_network.json` | Hashtag, mention and co-occurrence statistics |
| `cache/{username}_fetch_status.json` | Incremental range and phase status |
| `cache/charts/` | PNG and HTML; supported commands accept `--output` |
| `cache/csv/` | CSV; change with `export csv --output` |
| `cache/analysis_runs.json`, `cache/llm_calls.json` | Run/call metadata; replaced by a database in SQLite mode |

Reports contain hourly, weekday, language and professional-interest charts as inputs permit, plus existing interest/event evidence. Network and sentiment charts are not automatically embedded. HTML references PNG files relatively; copy those images with the HTML when sharing.

This is a **fictional interest-item excerpt**, not a complete result file:

```json
{
  "tag": "Open-source tools",
  "level": "core",
  "confidence": 0.8,
  "keywords": ["Python", "open source"],
  "evidence_count": 2,
  "evidence_tweet_ids": ["1740000000000000001", "1740000000000000002"]
}
```

`evidence_count` counts valid evidence IDs. `confidence` is model judgment, not a calibrated statistical probability. Current interest/event analysis accepts only IDs from actual prompt samples and records `sampling.sample_tweet_ids`; valid IDs do not establish semantic support.

Translation `original` may have URLs and @mentions removed and whitespace normalized. Use raw data for the preserved source text. Text shorter than six characters after cleaning is skipped for translation, so raw and translated counts can differ.

CSV cells with dangerous formula prefixes receive an apostrophe; long tweet IDs are protected as text. Other CSV readers may display the apostrophe. Failed sentiment batches remain `unknown`, not `neutral`.

## Configuration and storage

- Defaults: `TARGET_USERNAME=MiracleHe`, `CACHE_DIR=cache`, `TIMEZONE_OFFSET=8`, `LLM_MODEL=deepseek-chat`. Set your intended account before real requests.
- Professional interest analysis prefers a nonempty `DEEPSEEK_API_KEY`; it selects OpenAI only when that key is empty. This is not failover after a failed request. Set a model supported by the selected OpenAI service.
- Translation batch size defaults to ten. Batching and caching reduce repeated overhead but do not guarantee a fixed cost reduction.
- Interest analysis defaults to at most 300 records, life-event detection to 200 and post-fetch clustering to 1,000. Sampling is evenly spaced over record order, not necessarily evenly distributed over time intervals.
- `STORAGE_BACKEND=sqlite` changes only run/call metadata storage; tweets, translations, caches and reports remain files. Backends do not migrate automatically.

```bash
xcrawler analyze interest --storage sqlite
xcrawler analyze sentiment --storage sqlite --sqlite-path state/xcrawler.db
```

See the [configuration guide](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md) for all variables, providers, cache migration, retranslation and locking details.

## Privacy and data boundaries

Fetching excludes retweets and replies by default; it does not represent all user interactions.

Behavior analysis hides descriptions and evidence IDs of events identified as sensitive by default. Reports apply filtering again, including to legacy events. Detection uses categories, flags and keywords; it is not complete anonymization. Interest and ordinary-event evidence may expose original text or personal information. Review reports before sharing.

To display sensitive events intentionally, enable the option both when producing behavior data and when rendering the report. A report flag cannot recover details already removed from saved results:

```bash
xcrawler analyze behavior --include-sensitive-events
xcrawler report --include-sensitive-events
```

Raw data, translations and model inputs are not automatically anonymized by report filtering. Evidence identifies a cited source; models can misinterpret it. Posting timestamps do not prove sleep habits or location.

New POSIX directories default to `0700`, managed files to `0600`; existing parent permissions are not automatically changed. Use appropriate filesystem access controls on Windows. JSON updates use locks, atomic writes and `.bak` recovery, but a whole fetch/analysis workflow is not one transaction.

Before cleanup, stop related processes and inspect custom outputs, `.bak` files, shared translation/embedding caches, metadata, SQLite databases and old backups. Deleting `{username}_*.json` does not remove all associated content; shared records cannot safely be cleared by username filenames alone. Do not delete `.lock` files while processes are running.

## Troubleshooting

| Symptom | Check |
|---|---|
| `xcrawler` not found | Activate the installation environment; inspect `python -m pip show xcrawler-ai` |
| `.env` ignored/missing key | Use explicit environment variables; check discovery location and existing environment precedence |
| Missing input | Align `--user` and `--cache-dir`; fetch, translate and analyze first. Analysis commands are not read-only viewers |
| Missing matplotlib | `python -m pip install "xcrawler-ai[viz]"` |
| Clustering skipped | Check ML installation, at least ten translations, and fetch completeness |
| Too few interest/sentiment inputs | At least five usable texts; interest `--limit` must also allow enough inputs |
| HTTP 401/403 | Check the token and account access; retries do not grant permissions |
| HTTP 429 | Reduce budgets and check service quotas; the program stops beyond its wait limit rather than waiting forever |
| Exit code `2` | Inspect output and, for incremental fetches, the fetch-status file for unfinished scope |
| Translation/model error | Check key, endpoint, model and input size; cache migration can also increase calls |
| Old report conclusions | `report` does not rerun analysis; refresh needed analyses after translation |
| Missing images after sharing | Copy the HTML together with its referenced PNG files |

## Source development

This is an alternative to PyPI installation and requires Git:

```bash
git clone https://github.com/yuanrengu/xcrawler.git
cd xcrawler
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
# Add plotting if needed; clustering is optional via .[ml] or .[all]
python -m pip install -e ".[viz]"
ruff check .
mypy xcrawler
python -m pytest
```

Use the Windows activation command above where applicable. Editable installation runs the current source; see [CONTRIBUTING](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md).

```text
xcrawler/       Configuration, CLI, clients, services, storage and utilities
main.py         Fetch/translation/clustering compatibility entry point
analyze_*.py    Analysis implementations and legacy script entry points
tests/          Regression tests split by responsibility
.github/        CI, dependency updates and PR template
```

## Documentation and contributing

Detailed topic guides below are in Chinese; the English README covers the primary workflows and limitations.

- [Quick start](https://github.com/yuanrengu/xcrawler/blob/main/QUICK_START.md): minimal workflows.
- [Configuration](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md): environment, providers, storage and translation recovery.
- [Incremental fetching](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md): budgets, replacement and status.
- [Behavior analysis](https://github.com/yuanrengu/xcrawler/blob/main/BEHAVIOR_ANALYSIS.md): sampling, privacy and interpretation.
- [Changelog](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md) and [release checklist](https://github.com/yuanrengu/xcrawler/blob/main/RELEASE_CHECKLIST.md).
- [Contributing](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md): associate an issue, then submit a branch and PR.
- [Security](https://github.com/yuanrengu/xcrawler/blob/main/SECURITY.md): report credential/privacy issues privately as directed.

Licensed under the [MIT License](https://github.com/yuanrengu/xcrawler/blob/main/LICENSE). Follow service rules and applicable laws; do not use the tool for unauthorized profiling or off-platform advertising targeting.
