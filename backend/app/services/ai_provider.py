"""
AI 提供商抽象层 - 支持多种 AI 服务商

支持的提供商：
- deepseek (Deep Seek)
- openai (OpenAI)
- anthropic (Claude) - 预留

使用方法：
    1. 在 .env 中设置 AI_PROVIDER=deepseek
    2. 设置对应的 API Key
"""
from abc import ABC, abstractmethod
from typing import Annotated
from openai import OpenAI
from sqlmodel import Session
from app.core.config import settings
from app.core.security import decrypt_api_key
from openai.types.chat import ChatCompletionMessageParam
import json
import re

class AIProviderError(RuntimeError):
    """把第三方 SDK 异常统一成业务异常，便于在 API 层转换成 HTTP 错误。"""


class BaseAIProvider(ABC):
    """AI 提供商基类"""

    def _read_stream(self, stream, max_tokens):
        """Keep safe diagnostics, never persist or expose reasoning text."""
        stats = {"finish_reason": None, "max_tokens": max_tokens,
                 "content_chars": 0, "reasoning_chars": 0}
        self.last_stream_diagnostics = stats
        try:
            for event in stream:
                usage = getattr(event, "usage", None)
                if usage:
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        value = getattr(usage, key, None)
                        if isinstance(value, int):
                            stats[key] = value
                choices = getattr(event, "choices", None)
                if not choices:
                    continue
                choice = choices[0]
                if choice.finish_reason:
                    stats["finish_reason"] = choice.finish_reason
                delta = choice.delta
                stats["reasoning_chars"] += len(getattr(delta, "reasoning_content", None) or "")
                content = getattr(delta, "content", None)
                if content:
                    stats["content_chars"] += len(content)
                    yield content
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        if stats["finish_reason"] == "length":
            raise AIProviderError("模型达到输出 token 上限，回答未完成。请缩短本次任务或提高设置中的输出上限。")
        if stats["finish_reason"] == "content_filter":
            raise AIProviderError("模型服务未完成回答：内容被服务商过滤。")
        if stats["finish_reason"] != "stop":
            raise AIProviderError("模型流未正常结束，请重试。")
    
    @abstractmethod
    def chat(self, messages:  list[ChatCompletionMessageParam], **kwargs) -> str:
        """发送聊天请求，返回内容"""
        pass

    @abstractmethod
    def stream_chat(self, messages: list[ChatCompletionMessageParam], **kwargs):
        """
        流式聊天：逐步产出文本片段（token/chunk）。

        返回一个可迭代对象（generator）。
        """
        raise NotImplementedError


class DeepSeekProvider(BaseAIProvider):
    """Deep Seek 提供商"""

    @property
    def supports_structured_writing(self):
        return self.model in {"deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro"}

    def _writing_options(self):
        # The app's output budget is for usable text, not hidden reasoning.
        # Avoid vendor-specific extensions for unknown/custom models.
        if self.supports_structured_writing:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {}
    
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        # 优先级：传入的 key > 环境变量中的 key
        final_key = api_key or settings.DEEPSEEK_API_KEY
        if not final_key:
            raise AIProviderError("未配置 DEEPSEEK_API_KEY")
        
        self.client = OpenAI(
            api_key=final_key,
            base_url=base_url or settings.DEEPSEEK_BASE_URL,
            timeout=30.0,
            max_retries=1,
        )
        self.model = model or settings.DEEPSEEK_MODEL
    
    def chat(self, messages: list[ChatCompletionMessageParam], **kwargs) -> str:
        tools = kwargs.get("tools")
        tool_choice = kwargs.get("tool_choice", "auto")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
                tools=tools,
                tool_choice=tool_choice,
                **self._writing_options(),
            )
            # 如果返回 tool_calls，序列化为 JSON 字符串返回
            if response.choices[0].message.tool_calls:
                tool_calls = []
                for i, tc in enumerate(response.choices[0].message.tool_calls):
                    tc_dict = tc.model_dump()
                    # DeepSeek 可能不返回 id，需要生成
                    if "id" not in tc_dict or not tc_dict["id"]:
                        tc_dict["id"] = f"call_{i}_{hash(tc_dict['function']['name']) % 10000:04d}"
                    tool_calls.append(tc_dict)
                return json.dumps(tool_calls)
            return response.choices[0].message.content or ""
        except Exception as e:
            raise AIProviderError(f"DeepSeek 调用失败: {e}") from e

    def stream_chat(self, messages: list[ChatCompletionMessageParam], **kwargs):
        # 调试日志
        import logging
        logging.debug(f"{self.__class__.__name__}.stream_chat called")
        structured = kwargs.get("structured_output", False) and self.supports_structured_writing
        options = self._writing_options()
        if structured:
            options["response_format"] = {"type": "json_object"}
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
                stream=True,
                **options,
            )
            logging.debug(f"{self.__class__.__name__}.stream_chat stream type: {type(stream)}")
            chunks = self._read_stream(stream, kwargs.get("max_tokens", 1000))
            if not structured:
                yield from chunks
                return
            # Buffer JSON until both fields and the finish marker are validated.
            # Neither partial JSON nor an unvalidated draft reaches the copy UI.
            raw = "".join(chunks)
            try:
                result = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise AIProviderError("模型返回的结构化内容无效，请重试。") from exc
            if (not isinstance(result, dict) or set(result) != {"reply", "copy"}
                    or not all(isinstance(result[key], str) for key in ("reply", "copy"))
                    or not result["reply"].strip() or not result["copy"].strip()
                    or any(re.search(r"</?NOVELCAT_", result[key], re.I) for key in ("reply", "copy"))):
                raise AIProviderError("模型未完整分离说明与可复制内容，请重试。")
            yield f"<NOVELCAT_REPLY>\n{result['reply'].strip()}\n</NOVELCAT_REPLY>\n<NOVELCAT_COPY>\n{result['copy'].strip()}\n</NOVELCAT_COPY>"
        except Exception as e:
            raise AIProviderError(f"DeepSeek 流式调用失败: {e}") from e


class OpenAIProvider(BaseAIProvider):
    """OpenAI 提供商"""
    
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        # 优先级：传入的 key > 环境变量中的 key
        final_key = api_key or settings.OPENAI_API_KEY
        if not final_key:
            raise AIProviderError("未配置 OPENAI_API_KEY")

        self.client = OpenAI(
            api_key=final_key,
            base_url=base_url or settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
            timeout=30.0,
            max_retries=1,
        )
        self.model = model or settings.OPENAI_MODEL or "gpt-3.5-turbo"
    
    def chat(self, messages: list[ChatCompletionMessageParam], **kwargs) -> str:
        tools = kwargs.get("tools")
        tool_choice = kwargs.get("tool_choice", "auto")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
                tools=tools,
                tool_choice=tool_choice,
            )
            # 如果返回 tool_calls，序列化为 JSON 字符串返回
            if response.choices[0].message.tool_calls:
                tool_calls = []
                for i, tc in enumerate(response.choices[0].message.tool_calls):
                    tc_dict = tc.model_dump()
                    # 确保有 id 字段
                    if "id" not in tc_dict or not tc_dict["id"]:
                        tc_dict["id"] = f"call_{i}_{hash(tc_dict['function']['name']) % 10000:04d}"
                    tool_calls.append(tc_dict)
                return json.dumps(tool_calls)
            return response.choices[0].message.content or ""
        except Exception as e:
            raise AIProviderError(f"OpenAI 调用失败: {e}") from e

    def stream_chat(self, messages: list[ChatCompletionMessageParam], **kwargs):
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
                stream=True,
            )
            yield from self._read_stream(stream, kwargs.get("max_tokens", 1000))
        except Exception as e:
            raise AIProviderError(f"OpenAI 流式调用失败: {e}") from e


class AIProviderFactory:
    """AI 提供商工厂"""
    
    _providers = {
        "deepseek": DeepSeekProvider,
        "openai": OpenAIProvider,
        "openai_compatible": OpenAIProvider,
    }
    
    @classmethod
    def get_provider(
        cls, 
        provider_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> BaseAIProvider:
        """获取 AI 提供商实例"""
        if provider_name is None:
            provider_name = settings.AI_PROVIDER
        
        provider_class = cls._providers.get(provider_name)
        
        if provider_class is None:
            raise AIProviderError(f"不支持的 AI 提供商: {provider_name}")
        
        return provider_class(api_key=api_key, base_url=base_url, model=model)


def discover_provider_models(
    *,
    api_key: str,
    base_url: str,
) -> list[str]:
    """Read an OpenAI-compatible model catalog and return stable, sorted IDs."""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=20.0,
            max_retries=0,
        )
        response = client.models.list()
        return sorted({item.id for item in response.data if getattr(item, "id", None)})
    except Exception as exc:
        raise AIProviderError(f"读取模型列表失败: {exc}") from exc


def get_ai_provider(session: Session | None = None, user_id: str = "default_user") -> BaseAIProvider:
    """获取当前配置的 AI 提供商"""
    from app.crud.settings_crud import get_settings
    
    api_key = None
    provider_name = settings.AI_PROVIDER

    if session:
        from app.crud.ai_provider_config_crud import (
            ensure_legacy_provider_configs,
            get_active_provider_config,
            resolve_provider_api_key,
        )

        ensure_legacy_provider_configs(session, user_id)
        provider_config = get_active_provider_config(session, user_id)
        if provider_config:
            api_key, _source = resolve_provider_api_key(provider_config)
            if not api_key:
                if provider_config.api_key_enc:
                    raise AIProviderError("当前 AI 服务的密钥无法解密，请重新填写 API Key")
                raise AIProviderError(f"当前 AI 服务“{provider_config.name}”还没有配置 API Key")
            return AIProviderFactory.get_provider(
                provider_config.provider,
                api_key=api_key,
                base_url=provider_config.base_url,
                model=provider_config.model,
            )

        db_settings = get_settings(session, user_id=user_id)
        if db_settings:
            # 1. 优先使用数据库中的供应商设置
            provider_name = db_settings.ai_provider or settings.AI_PROVIDER
            
            # 2. 尝试从数据库读取加密的 Key
            if provider_name == "deepseek" and db_settings.deepseek_api_key_enc:
                api_key = decrypt_api_key(db_settings.deepseek_api_key_enc)
            elif provider_name == "openai" and db_settings.openai_api_key_enc:
                api_key = decrypt_api_key(db_settings.openai_api_key_enc)

    return AIProviderFactory.get_provider(provider_name, api_key=api_key)
