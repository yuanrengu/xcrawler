"""End-to-end transaction matrix for the full-fetch command."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

OLD_RAW = [{"id": "old", "text": "existing tweet", "created_at": "2025-01-01T00:00:00Z"}]
OLD_TRANSLATED = [
    {
        "tweet_id": "old",
        "original": "existing tweet",
        "translated": "旧译文",
        "detected_language": "en",
        "created_at": "2025-01-01T00:00:00Z",
    }
]
NEW_RAW = [{"id": "new", "text": "long new english tweet", "created_at": "2026-01-01T00:00:00Z"}]


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("replace", [False, True], ids=["archive", "replace"])
@pytest.mark.parametrize("translate", [False, True], ids=["no-translate", "translate"])
@pytest.mark.parametrize(
    ("outcome", "expected_exit"),
    [("success", 0), ("partial", 2), ("failed", 1)],
)
def test_full_fetch_transaction_matrix(tmp_path, monkeypatch, replace, translate, outcome, expected_exit):
    """Every mode preserves or commits files according to the documented transaction contract."""
    import main

    raw_path = tmp_path / "alice_raw_tweets.json"
    translated_path = tmp_path / "alice_translated.json"
    raw_path.write_text(json.dumps(OLD_RAW), encoding="utf-8")
    translated_path.write_text(json.dumps(OLD_TRANSLATED, ensure_ascii=False), encoding="utf-8")

    args = SimpleNamespace(
        user="alice",
        pages=1,
        batch_size=10,
        model=None,
        cache_dir=str(tmp_path),
        analysis_limit=100,
        no_translate=not translate,
        replace=replace,
        storage_backend="json",
        sqlite_path=None,
    )
    monkeypatch.setattr(main, "parse_args", lambda: args)
    monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
    monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
    monkeypatch.setattr(main, "get_user_profile", lambda username: None)
    monkeypatch.setattr(main, "save_translation_cache", lambda cache: None)
    monkeypatch.setattr(main, "ml_analysis_available", lambda: False)

    translate_batch = MagicMock(
        side_effect=lambda texts, langs: ["新译文" if outcome != "failed" else None] * len(texts)
    )
    monkeypatch.setattr(main, "deepseek_translate_batch", translate_batch)
    if outcome == "failed" and not translate:
        monkeypatch.setattr(main, "fetch_tweets", MagicMock(side_effect=RuntimeError("fetch failed")))
    else:
        complete = outcome != "partial"
        monkeypatch.setattr(
            main,
            "fetch_tweets",
            lambda user_id: main.x_api.TweetFetchResult(
                NEW_RAW,
                complete,
                "no_next_token" if complete else "page_limit",
                1,
                1,
                0,
                None if complete else "still-more",
            ),
        )

    exit_code = main.main()

    assert exit_code == expected_exit
    raw = _read_json(raw_path)
    translated_data = _read_json(translated_path)

    fetch_failed = outcome == "failed" and not translate
    replace_rejected = replace and outcome in {"partial", "failed"}
    if fetch_failed or replace_rejected:
        assert raw == OLD_RAW
        assert translated_data == OLD_TRANSLATED
    elif replace:
        assert raw == NEW_RAW
        if translate:
            assert [item["tweet_id"] for item in translated_data] == ["new"]
        else:
            assert translated_data == []
    else:
        assert [item["id"] for item in raw] == ["new", "old"]
        expected_translation_ids = {"old"}
        if translate and outcome != "failed":
            expected_translation_ids.add("new")
        assert {item["tweet_id"] for item in translated_data} == expected_translation_ids

    if not translate or (replace and outcome == "partial") or fetch_failed:
        translate_batch.assert_not_called()


def test_empty_first_page_is_failed_without_touching_existing_files(tmp_path, monkeypatch):
    import main

    raw_path = tmp_path / "alice_raw_tweets.json"
    translated_path = tmp_path / "alice_translated.json"
    raw_path.write_text(json.dumps(OLD_RAW), encoding="utf-8")
    translated_path.write_text(json.dumps(OLD_TRANSLATED, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: SimpleNamespace(
            user="alice",
            pages=1,
            batch_size=10,
            model=None,
            cache_dir=str(tmp_path),
            analysis_limit=100,
            no_translate=False,
            replace=False,
            storage_backend="json",
            sqlite_path=None,
        ),
    )
    monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
    monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
    monkeypatch.setattr(main, "get_user_profile", lambda username: None)
    monkeypatch.setattr(
        main,
        "fetch_tweets",
        lambda user_id: main.x_api.TweetFetchResult([], True, "no_data", 0, 1, 0),
    )

    assert main.main() == 1
    assert _read_json(raw_path) == OLD_RAW
    assert _read_json(translated_path) == OLD_TRANSLATED
