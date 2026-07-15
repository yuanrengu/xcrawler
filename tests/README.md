# Test suite

The suite is grouped by responsibility so changes to fetch correctness can be reviewed independently:

- `test_fetching.py`: full and incremental fetch behavior and raw-record validation
- `test_fetch_transactions.py`: archive/replace, translate/no-translate, and success/partial/failure transaction matrix
- `test_timeline_contract.py`: X timeline response contract and property-based pagination checks
- `test_translation.py`: translation, cache, and translated-record behavior
- `test_analysis.py`: analysis, evidence, privacy, and visualization behavior
- `test_storage_cli.py`: storage, CLI, configuration, paths, and export behavior
- `test_coverage_gate.py`: critical-module coverage floor enforcement

Run the suite with:

```bash
python -m pytest
```

The CI coverage job additionally runs `scripts/check_critical_coverage.py` so a high aggregate percentage cannot hide regressions in `main.py`, `fetch_more_history.py`, or `xcrawler/clients/x_api.py`.
