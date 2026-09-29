from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock

from app.services.ai_provider import AIProviderError, DeepSeekProvider, OpenAIProvider


def event(content=None, reasoning=None, finish=None):
    return NS(choices=[NS(delta=NS(content=content, reasoning_content=reasoning), finish_reason=finish)], usage=None)


class ProviderStreamTests(TestCase):
    def provider(self, cls=DeepSeekProvider, model="deepseek-flash"):
        provider = object.__new__(cls)
        provider.model = model
        provider.client = Mock()
        return provider

    def test_usage_only_event_and_reasoning_are_not_displayed(self):
        provider = self.provider()
        stream = Mock()
        stream.__iter__ = Mock(return_value=iter([
            event(reasoning="private reasoning"), event(content="正文"), event(finish="stop"),
            NS(choices=[], usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
        ]))
        self.assertEqual(list(provider._read_stream(stream, 2000)), ["正文"])
        self.assertEqual(provider.last_stream_diagnostics["reasoning_chars"], 17)
        self.assertEqual(provider.last_stream_diagnostics["completion_tokens"], 5)
        self.assertNotIn("private reasoning", str(provider.last_stream_diagnostics))
        stream.close.assert_called_once()

    def test_length_does_not_report_success(self):
        provider = self.provider()
        stream = provider._read_stream(iter([event(content="未完成"), event(finish="length")]), 100)
        self.assertEqual(next(stream), "未完成")
        with self.assertRaisesRegex(AIProviderError, "上限"):
            list(stream)

    def test_missing_finish_marker_is_failure(self):
        with self.assertRaisesRegex(AIProviderError, "未正常结束"):
            list(self.provider()._read_stream(iter([event(content="半段")]), 100))

    def test_content_filter_is_failure(self):
        with self.assertRaisesRegex(AIProviderError, "过滤"):
            list(self.provider()._read_stream(iter([event(finish="content_filter")]), 100))

    def test_known_deepseek_models_disable_default_thinking(self):
        for model in ("deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro"):
            provider = self.provider(model=model)
            provider.client.chat.completions.create.return_value = iter([event(content="正文", finish="stop")])
            self.assertEqual(list(provider.stream_chat([])), ["正文"])
            self.assertEqual(provider.client.chat.completions.create.call_args.kwargs["extra_body"],
                             {"thinking": {"type": "disabled"}})

    def test_unknown_and_other_providers_have_no_vendor_extension(self):
        for provider in (self.provider(model="custom-model"), self.provider(OpenAIProvider)):
            provider.client.chat.completions.create.return_value = iter([event(content="正文", finish="stop")])
            list(provider.stream_chat([]))
            self.assertNotIn("extra_body", provider.client.chat.completions.create.call_args.kwargs)

    def test_non_streaming_uses_same_mode(self):
        provider = self.provider()
        provider.client.chat.completions.create.return_value = NS(choices=[NS(message=NS(content="标题", tool_calls=None))])
        self.assertEqual(provider.chat([]), "标题")
        self.assertEqual(provider.client.chat.completions.create.call_args.kwargs["extra_body"],
                         {"thinking": {"type": "disabled"}})

    def test_json_writing_is_validated_and_converted(self):
        provider = self.provider()
        provider.client.chat.completions.create.return_value = iter([
            event(content='{"reply":"修改说明",'),
            event(content='"copy":"第一段\\n\\n第二段"}', finish="stop"),
        ])
        text = "".join(provider.stream_chat([], structured_output=True))
        self.assertEqual(text, "<NOVELCAT_REPLY>\n修改说明\n</NOVELCAT_REPLY>\n<NOVELCAT_COPY>\n第一段\n\n第二段\n</NOVELCAT_COPY>")
        self.assertEqual(provider.client.chat.completions.create.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_invalid_json_never_becomes_copyable_text(self):
        for raw in ('{}', '{"reply":"a","copy":null}', '{"reply":"a","copy":""}',
                    '{"reply":"a","copy":"<NOVELCAT_COPY>正文"}', '{"reply":"a"'):
            provider = self.provider()
            provider.client.chat.completions.create.return_value = iter([event(content=raw, finish="stop")])
            output = provider.stream_chat([], structured_output=True)
            with self.assertRaises(AIProviderError):
                next(output)

    def test_truncated_valid_json_is_still_failure(self):
        provider = self.provider()
        provider.client.chat.completions.create.return_value = iter([
            event(content='{"reply":"说明","copy":"正文"}', finish="length")])
        with self.assertRaisesRegex(AIProviderError, "上限"):
            next(provider.stream_chat([], structured_output=True))
