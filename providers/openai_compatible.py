# -*- coding: utf-8 -*-
"""
OpenAI SDK + 可配置 base_url 实现。

覆盖 OpenAI 官方，以及所有声明"兼容 OpenAI Chat Completions 协议"的国内模型
（DeepSeek / Moonshot·Kimi / 通义千问 / 智谱GLM 等）。用户只需要在 .env 里
填 provider 名字，不用记各家的 base_url；也可以用 LLM_BASE_URL 覆盖默认值
（对接非内置列表的模型，或代理网关时用）。

注意：各家"OpenAI 兼容"的严格程度不完全一致（部分只兼容请求体格式，鉴权头
或个别字段可能有差异），接入新模型时建议先用 --dry-run 之外的一次真实小额
调用验证，不要只凭文档假设能跑通。
"""

from typing import Optional

from .base import LLMProvider, LLMProviderError, LLMResponse

# provider 名 -> 默认 base_url。用户填 provider 名即可，不用记 URL。
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    # MiniMax 官方文档声明其 v2 接口兼容 OpenAI chat/completions，但历史上
    # 有过自定义协议版本共存的情况。接入前请对照 MiniMax 最新官方文档核实
    # base_url 和鉴权方式，不要仅凭这里的默认值假设一定能跑通。
    "minimax": "https://api.minimax.chat/v1",
}


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None,
                 timeout: int = 120, max_tokens: int = 4096, provider_label: str = "openai"):
        resolved_base_url = base_url or DEFAULT_BASE_URLS.get(provider_label)
        super().__init__(api_key, model, resolved_base_url, timeout, max_tokens)
        self._provider_label = provider_label
        try:
            import openai
        except ImportError as e:
            raise LLMProviderError(
                "未安装 openai 包，请运行: pip install openai", retryable=False, cause=e
            )
        kwargs = {"api_key": api_key, "timeout": timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = openai.OpenAI(**kwargs)
        self._sdk = openai

    @property
    def provider_name(self) -> str:
        return self._provider_label

    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
            )
        except self._sdk.RateLimitError as e:
            raise LLMProviderError(f"{self._provider_label} 限流: {e}", retryable=True, cause=e)
        except self._sdk.APITimeoutError as e:
            raise LLMProviderError(f"{self._provider_label} 超时: {e}", retryable=True, cause=e)
        except self._sdk.APIConnectionError as e:
            raise LLMProviderError(f"{self._provider_label} 网络错误: {e}", retryable=True, cause=e)
        except self._sdk.AuthenticationError as e:
            raise LLMProviderError(f"{self._provider_label} API Key 无效: {e}", retryable=False, cause=e)
        except self._sdk.APIStatusError as e:
            raise LLMProviderError(
                f"{self._provider_label} API 错误 ({e.status_code}): {e}", retryable=False, cause=e
            )
        except Exception as e:
            raise LLMProviderError(f"{self._provider_label} 调用异常: {e}", retryable=False, cause=e)

        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = None
        if getattr(resp, "usage", None):
            usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
            }
        return LLMResponse(text=text, model=resp.model or self.model,
                            provider=self.provider_name, usage=usage, raw=resp)
