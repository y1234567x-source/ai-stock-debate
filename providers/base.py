# -*- coding: utf-8 -*-
"""
LLM Provider 抽象层。

设计原则：只暴露"单轮 prompt in -> text out"的同步接口。agents/prompts.py
里的五份 Agent prompt 本身就是"一次性长文本指令"风格，不需要多轮对话或
工具调用，天然适配这个简单的 complete() 语义——这样任何一家新模型接入，
只需要实现一个 complete() 方法，不需要理解各家 SDK 里 messages/tools 的
具体差异。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: Optional[dict] = None
    raw: Any = field(default=None, repr=False)


class LLMProviderError(Exception):
    """Provider 调用失败的统一异常类型，orchestrator 据此判断是否重试/降级。"""

    def __init__(self, message: str, retryable: bool = False, cause: Exception = None):
        super().__init__(message)
        self.retryable = retryable
        self.cause = cause


class LLMProvider(ABC):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None,
                 timeout: int = 120, max_tokens: int = 4096):
        if not api_key:
            raise ValueError("api_key 不能为空")
        if not model:
            raise ValueError("model 不能为空")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        """
        同步单轮调用。子类必须实现。
        失败时应抛出 LLMProviderError（区分 retryable 是否值得重试）。
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError
