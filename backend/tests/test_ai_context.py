from __future__ import annotations

import unittest

from app.services.ai_context import (
    chapter_brief,
    clip_text,
    detect_output_shape,
    detect_memory_profile,
    is_explicit_author_decision,
    parse_structured_output,
    plain_text,
    requests_external_reference,
)


class AiContextTests(unittest.TestCase):
    def test_plain_text_and_brief_preserve_useful_novel_text(self) -> None:
        self.assertEqual(plain_text("<p>第一句。</p><p>最后一句。</p>"), "第一句。\n\n最后一句。")
        self.assertEqual(chapter_brief("", "<p>第一句。</p><p>最后一句。</p>"), "第一句。 最后一句。")
        self.assertEqual(clip_text("abcdef", 3), "abc...（已截断）")

    def test_memory_profile_routes_common_writing_requests(self) -> None:
        self.assertEqual(detect_memory_profile("帮我续写下一段").name, "draft")
        self.assertEqual(detect_memory_profile("检查全书结构和人物线").name, "structure")
        self.assertEqual(detect_memory_profile("把这段润色一下").name, "rewrite")
        self.assertEqual(detect_memory_profile("你好").name, "default")

    def test_external_reference_requires_explicit_intent(self) -> None:
        self.assertTrue(requests_external_reference("参考知识库里的设定"))
        self.assertFalse(requests_external_reference("看看本书前面的设定"))

    def test_output_shape_hints_are_lightweight(self) -> None:
        self.assertEqual(detect_output_shape("帮我润色这一段"), "revise")
        self.assertEqual(detect_output_shape("接着往下写"), "draft")
        self.assertEqual(detect_output_shape("评价这几章的节奏"), "review")
        self.assertEqual(detect_output_shape("整理一下全书大纲"), "outline")
        self.assertEqual(detect_output_shape("你好"), "chat")

    def test_structured_output_keeps_copy_content_clean(self) -> None:
        reply, copy_text = parse_structured_output(
            "<NOVELCAT_REPLY>调整了氛围。</NOVELCAT_REPLY>\n"
            "<NOVELCAT_COPY>```text\n她没有退开，只把呼吸放得更轻。\n```</NOVELCAT_COPY>"
        )
        self.assertEqual(reply, "调整了氛围。")
        self.assertEqual(copy_text, "她没有退开，只把呼吸放得更轻。")

    def test_structured_output_supports_legacy_separator(self) -> None:
        reply, copy_text = parse_structured_output("说明\n---\n最终正文")
        self.assertEqual(reply, "说明")
        self.assertEqual(copy_text, "最终正文")

    def test_structured_output_cleans_partial_stream_when_stopped(self) -> None:
        reply, copy_text = parse_structured_output(
            "<NOVELCAT_REPLY>简短说明</NOVELCAT_REPLY>\n<NOVELCAT_COPY>写到一半的正文"
        )
        self.assertEqual(reply, "简短说明")
        self.assertEqual(copy_text, "写到一半的正文")

    def test_structured_output_removes_private_previous_copy_marker(self) -> None:
        reply, copy_text = parse_structured_output(
            "<NOVELCAT_REPLY>已重新调整。</NOVELCAT_REPLY>\n"
            "<NOVELCAT_COPY><NOVELCAT_PREVIOUS_COPY>旧稿</NOVELCAT_PREVIOUS_COPY>新稿</NOVELCAT_COPY>"
        )
        self.assertEqual(reply, "已重新调整。")
        self.assertEqual(copy_text, "新稿")

    def test_explicit_author_decision_detection_is_conservative(self) -> None:
        self.assertTrue(is_explicit_author_decision("现在确认一项设定修改：林雾正式改为左撇子。"))
        self.assertTrue(is_explicit_author_decision("银色钥匙方案作废，以后仍然使用铜钥匙。"))
        self.assertFalse(is_explicit_author_decision("请帮我确认一下林雾是不是左撇子？"))
        self.assertFalse(is_explicit_author_decision("如果林雾是左撇子，会有什么影响？"))
        self.assertFalse(is_explicit_author_decision(
            "请显式搜索历史对话，查找作者是否说过‘林雾正式改为左撇子’，并告诉我当前采用哪项设定。"
        ))
        self.assertFalse(is_explicit_author_decision(
            "现在回查本次长对话的记忆：哪一项是我在本对话明确确认的新设定？"
        ))


if __name__ == "__main__":
    unittest.main()
