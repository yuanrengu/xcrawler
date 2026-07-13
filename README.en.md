# xcrawler

[中文](https://github.com/yuanrengu/xcrawler/blob/main/README.md) | [English](https://github.com/yuanrengu/xcrawler/blob/main/README.en.md)

xcrawler turns a public X/Twitter timeline into a local, evidence-linked profile report. It fetches public posts, translates them, analyzes interests, behavior, sentiment, and social signals, then stores JSON, CSV, charts, and HTML reports on your machine.

> The project analyzes public content only. Generated profiles are probabilistic summaries, not verified facts. Follow the X API terms and applicable privacy laws.

## 60-second demo — no API key

```bash
python3 -m pip install xcrawler-ai
xcrawler demo
```

The demo writes fictional sample data and an evidence-linked HTML report to `demo_output/`. It makes no network or LLM requests.

## Full installation

```bash
python3 -m pip install "xcrawler-ai[all]"
touch .env
```

Configure `X_BEARER_TOKEN`, `DEEPSEEK_API_KEY`, and `TARGET_USERNAME` in `.env`, then run:

```bash
xcrawler fetch --user your_x_username
xcrawler report --user your_x_username
```

Base installation supports fetching, translation, export, and the no-key demo. If the `ml` extra is missing, `fetch` safely skips clustering after saving fetched and translated data. Install `.[ml]` for clustering and `.[viz]` for charts, or `.[all]` for both.

## Main commands

| Command | Purpose |
|---|---|
| `xcrawler demo` | Generate a local report from fictional data, without keys |
| `xcrawler fetch` | Fetch, translate, and optionally cluster public posts |
| `xcrawler fetch-more` | Incrementally fetch newer posts and older history |
| `xcrawler translate` | Synchronize or retranslate cached posts |
| `xcrawler analyze interest` | Build an evidence-linked interest profile |
| `xcrawler analyze behavior` | Analyze activity patterns and life-event signals |
| `xcrawler analyze sentiment` | Analyze sentiment distribution and trends |
| `xcrawler analyze network` | Analyze hashtag and mention signals |
| `xcrawler report` | Generate PNG charts and an HTML report |
| `xcrawler export csv` | Export local data to spreadsheet-safe CSV |

## Data safety

- Default full fetches use **archive mode**: fetched records are merged by tweet ID and locally retained history is not deleted when a post disappears remotely.
- `xcrawler fetch --replace` uses **snapshot mode**: a completely fetched result replaces local history. Replacement commits raw and translated files together only after every requested translation succeeds.
- A partially completed fetch or translation returns a non-zero exit status; successfully saved partial translations are reported explicitly.
- `fetch-more --pages` is a shared HTTP request budget for forward fetching, backward fetching, and retries. The latest incremental status is written to `{username}_fetch_status.json` with request, data-page, retry, stop-reason, and partial-state fields.
- Translation records include source-content and translation-configuration fingerprints so changed source text is retranslated instead of being skipped solely because its tweet ID already exists.
- `xcrawler translate --force` replaces the primary translation file only when every requested retranslation succeeds.
- JSON writes are atomic and retain a recovery backup. SQLite is available for structured run and LLM-call metadata.
- Sensitive life-event evidence is hidden from HTML reports unless explicitly enabled.

## Development

```bash
python3 -m pip install -e ".[test]"
ruff check .
pytest -ra
python3 -m build
```

See [CONTRIBUTING.md](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md), [SECURITY.md](https://github.com/yuanrengu/xcrawler/blob/main/SECURITY.md), and [CHANGELOG.md](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md) for project policies and release history.

## License

MIT
