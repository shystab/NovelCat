import unittest
from app.models.ai import AIWSRequest
from app.services.ai_provider import AIProviderError
from app.services.draft_revision import revision_range, assemble_revision


def output(text):
    return f"<NOVELCAT_REPLY>模型说明</NOVELCAT_REPLY><NOVELCAT_COPY>{text}</NOVELCAT_COPY>"


class DraftRevisionTests(unittest.TestCase):
    def test_first_two_preserve_third_sentence_and_all_whitespace(self):
        source = "第一句。第二句！第三句不能删。\n\n  末段保持空格。\n"
        revision = revision_range(source, "opening_two")
        self.assertEqual(revision.target, "第一句。第二句！")
        result = assemble_revision(output("新第一句。新第二句！"), revision)
        self.assertIn("新第一句。新第二句！第三句不能删。\n\n  末段保持空格。\n", result)

    def test_quoted_sentence_boundary(self):
        revision = revision_range('“走吗？”她问。“走。”他说。', "opening_two")
        self.assertEqual(revision.target, '“走吗？”她问。')

    def test_last_paragraph_preserves_prefix_exactly(self):
        source = "  开头不动。\r\n\r\n第二段。\r\n\r\n末段。\n"
        revision = revision_range(source, "last_paragraph")
        self.assertEqual(revision.target, "末段。")
        self.assertIn("  开头不动。\r\n\r\n第二段。\r\n\r\n新末段。\n", assemble_revision(output("新末段。"), revision))

    def test_whole_draft_returned_for_two_sentences_is_rejected(self):
        with self.assertRaisesRegex(AIProviderError, "超出"):
            assemble_revision(output("一。二。三。"), revision_range("甲。乙。丙。", "opening_two"))

    def test_trailing_unfinished_sentence_is_rejected(self):
        with self.assertRaises(AIProviderError):
            assemble_revision(output("一。二。还有"), revision_range("甲。乙。丙。", "opening_two"))

    def test_multiple_paragraphs_are_rejected(self):
        with self.assertRaises(AIProviderError):
            assemble_revision(output("一段。\n\n二段。"), revision_range("原稿。", "last_paragraph"))

    def test_incomplete_output_is_rejected(self):
        with self.assertRaises(AIProviderError):
            assemble_revision("<NOVELCAT_COPY>半段", revision_range("原稿。", "last_paragraph"))

    def test_extra_blocks_and_leaked_markers_are_rejected(self):
        for raw in (output("替换。") + output("另一份。"),
                    output("<NOVELCAT_PREVIOUS_COPY>原稿。</NOVELCAT_PREVIOUS_COPY>"),
                    "说明混在协议外面" + output("替换。"),
                    "<NOVELCAT_REPLY> </NOVELCAT_REPLY><NOVELCAT_COPY>替换。</NOVELCAT_COPY>"):
            with self.subTest(raw=raw), self.assertRaises(AIProviderError):
                assemble_revision(raw, revision_range("原稿。", "last_paragraph"))

    def test_insufficient_sentences_are_rejected(self):
        with self.assertRaises(AIProviderError):
            revision_range("只有一句。", "opening_two")

    def test_reference_limits(self):
        for reference in ({"label": "x", "text": "x", "scope": "delete"}, {"label": "x", "text": "x" * 24001}):
            with self.assertRaises(ValueError):
                AIWSRequest(draft_reference=reference)
