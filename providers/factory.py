# -*- coding: utf-8 -*-
"""按配置返回对应的 LLMProvider 实例。"""

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .openai_compatible import OpenAICompatibleProvider

ANTHROPIC_LABELS = {"anthropic", "claude"}


def get_provider(config) -> LLMProvider:
    """
    config: config.Config 实例（或任意有同名属性的对象），需要提供
    llm_provider / llm_api_key / llm_model / llm_base_url / llm_timeout / llm_max_tokens
    """
    label = (config.llm_provider or "").strip().lower()
    if not label:
        raise ValueError(
            "未配置 LLM_PROVIDER。请复制 .env.example 为 .env 并填写 LLM_PROVIDER"
            "（anthropic / openai / deepseek / moonshot / qwen / glm / minimax / custom）"
        )

    if label in ANTHROPIC_LABELS:
        return AnthropicProvider(
            api_key=config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
            timeout=config.llm_timeout,
            max_tokens=config.llm_max_tokens,
        )

    # 其余一律走 OpenAI 兼容协议（openai / deepseek / moonshot / kimi / qwen /
    # dashscope / glm / zhipu / minimax / custom）。custom 必须自带 LLM_BASE_URL。
    if label == "custom" and not config.llm_base_url:
        raise ValueError("LLM_PROVIDER=custom 时必须同时填写 LLM_BASE_URL")

    return OpenAICompatibleProvider(
        api_key=config.llm_api_key,
        model=config.llm_model,
        base_url=config.llm_base_url,
        timeout=config.llm_timeout,
        max_tokens=config.llm_max_tokens,
        provider_label=label,
    )
