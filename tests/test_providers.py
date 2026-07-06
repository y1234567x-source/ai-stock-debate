# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from providers.base import LLMProvider, LLMProviderError
from providers.openai_compatible import DEFAULT_BASE_URLS, OpenAICompatibleProvider
from providers.factory import get_provider


class DummyConfig:
    def __init__(self, provider, api_key="sk-test", model="test-model", base_url=None,
                 timeout=120, max_tokens=4096):
        self.llm_provider = provider
        self.llm_api_key = api_key
        self.llm_model = model
        self.llm_base_url = base_url
        self.llm_timeout = timeout
        self.llm_max_tokens = max_tokens


def test_base_provider_rejects_empty_api_key():
    class Fake(LLMProvider):
        @property
        def provider_name(self):
            return "fake"

        def complete(self, prompt, system=None):
            raise NotImplementedError

    with pytest.raises(ValueError):
        Fake(api_key="", model="x")
    with pytest.raises(ValueError):
        Fake(api_key="sk-x", model="")


def test_openai_compatible_resolves_default_base_url():
    p = OpenAICompatibleProvider(api_key="sk-test", model="deepseek-chat", provider_label="deepseek")
    assert p.base_url == DEFAULT_BASE_URLS["deepseek"]
    assert p.provider_name == "deepseek"


def test_openai_compatible_custom_base_url_overrides_default():
    p = OpenAICompatibleProvider(
        api_key="sk-test", model="whatever", base_url="https://my-proxy.example.com/v1",
        provider_label="deepseek",
    )
    assert p.base_url == "https://my-proxy.example.com/v1"


def test_factory_dispatches_anthropic():
    provider = get_provider(DummyConfig("anthropic", model="claude-sonnet-4-5-20250929"))
    assert provider.provider_name == "anthropic"


def test_factory_dispatches_openai_compatible():
    provider = get_provider(DummyConfig("deepseek", model="deepseek-chat"))
    assert provider.provider_name == "deepseek"
    assert provider.base_url == DEFAULT_BASE_URLS["deepseek"]


def test_factory_custom_requires_base_url():
    with pytest.raises(ValueError):
        get_provider(DummyConfig("custom", model="whatever", base_url=None))


def test_factory_rejects_empty_provider():
    with pytest.raises(ValueError):
        get_provider(DummyConfig("", model="x"))
