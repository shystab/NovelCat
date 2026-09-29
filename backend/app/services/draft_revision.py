"""Pure, copy-only scoped revisions. Never touches stored chapters."""
import re
from dataclasses import dataclass

from app.services.ai_provider import AIProviderError


@dataclass(frozen=True)
class RevisionRange:
    source: str
    start: int
    end: int
    scope: str

    @property
    def target(self):
        return self.source[self.start:self.end]


def revision_range(source: str, scope: str) -> RevisionRange:
    if not source.strip():
        raise AIProviderError("引用稿件为空，请重新选择。")
    if scope == "opening_two":
        endings = list(re.finditer(r'[。！？!?]+[”’」』\"]*', source))
        if len(endings) < 2:
            raise AIProviderError("这份稿件不足两句，请选择整稿讨论。")
        return RevisionRange(source, 0, endings[1].end(), scope)
    if scope == "last_paragraph":
        end = len(source.rstrip())
        separators = list(re.finditer(r"\n[ \t\r]*\n", source[:end]))
        start = separators[-1].end() if separators else 0
        return RevisionRange(source, start, end, scope)
    if scope != "whole":
        raise AIProviderError("未知修改范围。")
    return RevisionRange(source, 0, len(source), scope)


def assemble_revision(raw: str, revision: RevisionRange) -> str:
    blocks = re.fullmatch(
        r"\s*<NOVELCAT_REPLY>([\s\S]*?)</NOVELCAT_REPLY>\s*"
        r"<NOVELCAT_COPY>([\s\S]*?)</NOVELCAT_COPY>\s*", raw,
    )
    if not blocks or not all(part.strip() for part in blocks.groups()) or any(
        re.search(r"</?NOVELCAT_", part) for part in blocks.groups()
    ):
        raise AIProviderError("局部修改未返回完整内容，请重试；原稿未改变。")
    replacement = blocks[2].strip()
    if revision.scope == "opening_two":
        endings = list(re.finditer(r'[。！？!?]+[”’」』\"]*', replacement))
        if len(endings) != 2 or replacement[endings[-1].end():].strip():
            raise AIProviderError("模型超出了两句的修改范围，已阻止生成整稿，请重试。")
    elif revision.scope == "last_paragraph" and re.search(r"\n\s*\n", replacement):
        raise AIProviderError("模型返回了多个段落，已阻止超范围修改，请重试。")
    merged = revision.source[:revision.start] + replacement + revision.source[revision.end:]
    # Describe the verified operation, not the model's unverified claim.
    label = "开头两句" if revision.scope == "opening_two" else "最后一段"
    return f"<NOVELCAT_REPLY>\n已替换{label}，范围外原文逐字保留。以下是合并后的完整稿件，尚未写入作品。\n</NOVELCAT_REPLY>\n<NOVELCAT_COPY>\n{merged}\n</NOVELCAT_COPY>"
