# -*- coding: utf-8 -*-
"""
配置加载与校验。启动时立即校验必填项，缺失时给出清晰引导，
不要等数据拉完、Agent 跑到一半才发现 API Key 没填。
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: Optional[str] = None
    llm_max_tokens: int = 4096
    llm_timeout: int = 120
    llm_max_retries: int = 1


class ConfigError(Exception):
    pass


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        # python-dotenv 未装时静默跳过，允许纯环境变量方式配置
        pass


def load_config() -> Config:
    _load_dotenv()

    provider = os.environ.get("LLM_PROVIDER", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()

    missing = [name for name, val in
               [("LLM_PROVIDER", provider), ("LLM_API_KEY", api_key), ("LLM_MODEL", model)]
               if not val]
    if missing:
        raise ConfigError(
            "缺少必填配置项: " + ", ".join(missing) + "\n"
            "请复制 .env.example 为 .env 并填写，或设置对应环境变量。\n"
            "支持的 LLM_PROVIDER: anthropic / openai / deepseek / moonshot / kimi / "
            "qwen / glm / minimax / custom"
        )

    def _int_env(name, default):
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ConfigError(f"{name} 必须是整数，当前值: {raw!r}")

    return Config(
        llm_provider=provider,
        llm_api_key=api_key,
        llm_model=model,
        llm_base_url=os.environ.get("LLM_BASE_URL", "").strip() or None,
        llm_max_tokens=_int_env("LLM_MAX_TOKENS", 4096),
        llm_timeout=_int_env("LLM_TIMEOUT", 120),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 1),
    )


def load_config_or_exit() -> Config:
    try:
        return load_config()
    except ConfigError as e:
        print(f"\n[配置错误] {e}\n", file=sys.stderr)
        sys.exit(1)
