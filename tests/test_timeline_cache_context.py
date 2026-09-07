import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xcrawler.services.records import translation_record_is_current
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    get_cached_translation,
    new_translation_cache,
    set_cached_translation,
    translation_endpoint_id,
)
from xcrawler.services.tweets import merge_translated_tweets, merge_tweets
from xcrawler.storage.json_store import save_json


def tweets():
    return [
        {'id': '9', 'text': 'old', 'created_at': '2026-09-06T00:00:00Z'},
        {'id': '10', 'text': 'new', 'created_at': '2026-09-06T00:00:00.500Z'},
        {'id': '11', 'text': 'tie', 'created_at': '2026-09-06T00:00:00.500Z'},
    ]


def test_mixed_precision_and_numeric_id_order():
    assert [t['id'] for t in merge_tweets([], tweets())] == ['11', '10', '9']
    translated = [{'tweet_id': t['id'], 'created_at': t['created_at']} for t in tweets()]
    assert [t.get('tweet_id') for t in merge_translated_tweets([{}], translated)] == ['11', '10', '9', None]


def test_incremental_uses_chronological_boundaries(tmp_path, monkeypatch):
    import fetch_more_history as fetch

    for name in ('TARGET_USERNAME', 'MAX_PAGES', 'TARGET_DATE', 'REQUEST_INTERVAL', 'CACHE_DIR'):
        monkeypatch.setattr(fetch, name, getattr(fetch, name))
    monkeypatch.setattr(fetch, 'parse_args', lambda: SimpleNamespace(
        user='alice', pages=3, target_date='2026-09-01', interval=0, cache_dir=str(tmp_path),
    ))
    monkeypatch.setattr(fetch, 'auth_headers', lambda _: {})
    monkeypatch.setattr(fetch, 'get_user_id', lambda *args: 'uid')
    save_json(str(tmp_path / 'alice_raw_tweets.json'), tweets())
    result = fetch.FetchBatchResult([], False, 0, 1, 0, 'no_data', True, False)
    request = MagicMock(return_value=result)
    monkeypatch.setattr(fetch, 'fetch_tweets_generic', request)
    assert fetch.main() == 0
    assert request.call_args_list[0].kwargs['since_id'] == '11'
    assert request.call_args_list[1].kwargs['until_id'] == '9'


def context(url):
    return TranslationCacheContext(provider='deepseek', model='same', endpoint_id=translation_endpoint_id(url))


def test_endpoint_isolation_and_legacy_migration():
    first, second = context('https://a.example/v1'), context('https://b.example/v1')
    cache = new_translation_cache()
    set_cached_translation(cache, 'hello', '你好', first)
    assert get_cached_translation(cache, 'hello', second) is None
    assert not translation_record_is_current(
        {'original': 'hello', 'translated': '你好', 'config_fingerprint': first.fingerprint},
        'hello', second.fingerprint,
    )
    old = first.to_dict()
    del old['endpoint_id']
    payload = json.dumps(old, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    key = hashlib.sha256(f'{payload}\0hello'.encode()).hexdigest()
    legacy = new_translation_cache()
    legacy['entries'][key] = {'translated': '旧译文', 'context': old}
    assert get_cached_translation(legacy, 'hello', first) is None
    assert legacy['entries'][key]['translated'] == '旧译文'


def test_endpoint_normalization_and_secrets():
    first = context('https://user:secret@EXAMPLE.com:443/v1/?api_key=secret#secret')
    assert first == context('https://example.com/v1')
    assert 'secret' not in first.canonical_json()
    assert first != context('https://example.com/v2')
    assert first != context('https://example.com:444/v1')


@pytest.mark.parametrize('url', ['file:///tmp/api', 'not-a-url'])
def test_invalid_endpoint_rejected(url):
    with pytest.raises(ValueError):
        translation_endpoint_id(url)


def test_both_commands_include_endpoint(monkeypatch):
    import main
    import translate_sync

    monkeypatch.setattr(main, 'DEEPSEEK_BASE_URL', 'https://a.example')
    monkeypatch.setattr(translate_sync, '_config', SimpleNamespace(deepseek_base_url='https://a.example'))
    assert main._translation_cache_context().endpoint_id == translate_sync._translation_cache_context().endpoint_id
    before = main._translation_cache_context().fingerprint
    monkeypatch.setattr(main, 'DEEPSEEK_BASE_URL', 'https://b.example')
    assert main._translation_cache_context().fingerprint != before
