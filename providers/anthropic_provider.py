# -*- coding: utf-8 -*-
"""Anthropic 官方 SDK 实现。"""

from typing import Optional

from .base import LLMProvider, LLMProviderError, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None,
                 timeout: int = 120, max_tokens: int = 4096):
        super().__init__(api_key, model, base_url, timeout, max_tokens)
        try:
            import anthropic
        except ImportError as e:
            raise LLMProviderError(
                "未安装 anthropic 包，请运行: pip install anthropic", retryable=False, cause=e
            )
        kwargs = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._sdk = anthropic

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        try:
            kwargs = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            resp = self._client.messages.create(**kwargs)
        except self._sdk.RateLimitError as e:
            raise LLMProviderError(f"Anthropic 限流: {e}", retryable=True, cause=e)
        except self._sdk.APITimeoutError as e:
            raise LLMProviderError(f"Anthropic 超时: {e}", retryable=True, cause=e)
        except self._sdk.APIConnectionError as e:
            raise LLMProviderError(f"Anthropic 网络错误: {e}", retryable=True, cause=e)
        except self._sdk.AuthenticationError as e:
            raise LLMProviderError(f"Anthropic API Key 无效: {e}", retryable=False, cause=e)
        except self._sdk.APIStatusError as e:
            raise LLMProviderError(f"Anthropic API 错误 ({e.status_code}): {e}", retryable=False, cause=e)
        except Exception as e:
            raise LLMProviderError(f"Anthropic 调用异常: {e}", retryable=False, cause=e)

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        usage = None
        if getattr(resp, "usage", None):
            usage = {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
        return LLMResponse(text=text, model=resp.model, provider=self.provider_name,
                            usage=usage, raw=resp)
