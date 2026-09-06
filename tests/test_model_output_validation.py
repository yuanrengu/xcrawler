from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xcrawler.llm.provider import OpenAICompatibleProvider
from xcrawler.services.profile import deepseek_profile_summary
from xcrawler.services.records import translation_record_is_current
from xcrawler.services.translation import parse_batch_response, translate_batch
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    get_cached_translation,
    new_translation_cache,
    set_cached_translation,
)


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.mark.parametrize('content', ['[1]\n[2]', '1.\n2.', '[1] 好\n[2]', '[1]  \n[2]  '])
def test_bare_labels_rejected(content):
    assert parse_batch_response(content, 2) == []


def test_invalid_batch_falls_back_without_caching_labels():
    cache = new_translation_cache()
    client = MagicMock()
    client.chat.completions.create.return_value = response('[1]\n[2]')
    fallback = MagicMock(return_value='恢复译文')
    result = translate_batch(
        ['hello', 'world'], detected_langs=['en', 'en'], use_cache=True, cache=cache,
        client_factory=lambda: client, model='fake', batch_size=2, max_retries=1,
        fallback_translate=fallback,
    )
    assert result == ['恢复译文', '恢复译文']
    assert fallback.call_count == 2
    assert cache['entries'] == {}


def test_legacy_label_is_cache_miss_and_record_is_stale():
    cache = new_translation_cache()
    context = TranslationCacheContext(provider='fake', model='fake')
    set_cached_translation(cache, 'hello', '你好', context)
    next(iter(cache['entries'].values()))['translated'] = '[1]'
    assert get_cached_translation(cache, 'hello', context) is None
    assert not translation_record_is_current(
        {'original': 'hello', 'translated': '[1]', 'config_fingerprint': context.fingerprint},
        'hello', context.fingerprint,
    )
    with pytest.raises(ValueError):
        set_cached_translation(cache, 'hello', '[1]', context)


def test_profile_retries_blank_before_recording_success(monkeypatch):
    monkeypatch.setattr('xcrawler.services.profile.time.sleep', lambda _: None)
    client = MagicMock()
    client.chat.completions.create.side_effect = [response('  '), response('有效画像')]
    recorder = MagicMock()
    assert deepseek_profile_summary('topic', client_factory=lambda: client, model='fake',
                                    call_recorder=recorder) == '有效画像'
    assert recorder.record_failure.call_count == 1
    assert recorder.record_success.call_count == 1


@pytest.mark.parametrize('content', [None, '', '  '])
def test_blank_profile_and_provider_fail(content):
    client = MagicMock()
    client.chat.completions.create.return_value = response(content)
    with pytest.raises(ValueError):
        deepseek_profile_summary('topic', client_factory=lambda: client, model='fake', max_retries=1)
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.client = client
    provider.name = 'fake'
    with pytest.raises(ValueError):
        provider.chat([], model='fake')
