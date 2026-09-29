from __future__ import annotations

import os
from typing import Iterable, TYPE_CHECKING

from app.core.config import settings

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except Exception:
    chromadb = None
    ChromaSettings = None

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


def _chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)

    # 简单 overlap：把上一块尾部拼到下一块开头
    if overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = []
        prev_tail = ""
        for c in chunks:
            merged = (prev_tail + "\n" + c).strip() if prev_tail else c
            overlapped.append(merged)
            prev_tail = c[-overlap:]
        chunks = overlapped

    return chunks


class KnowledgeService:
    def __init__(self, persist_dir: str | None = None, model_name: str | None = None):
        persist_dir = persist_dir or os.environ.get("NOVEL_CHROMA_DIR") or ".chroma"
        model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.persist_dir = persist_dir
        self.model_name = model_name
        self.client = None
        self.embedding_model: SentenceTransformer | None = None
        self._embedding_failed = False

        if not settings.ENABLE_LOCAL_EMBEDDINGS or chromadb is None or ChromaSettings is None:
            return

        os.makedirs(self.persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    @property
    def vector_enabled(self) -> bool:
        return self.client is not None and self.embedding_model is not None

    def ensure_ready(self) -> bool:
        """按需加载 embedding 模型，失败后缓存结果避免重复冷启动。"""
        if self.vector_enabled:
            return True
        if self._embedding_failed or self.client is None:
            return False
        if settings.EMBEDDING_LOCAL_FILES_ONLY:
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        try:
            from sentence_transformers import SentenceTransformer

            self.embedding_model = SentenceTransformer(
                self.model_name,
                device=settings.EMBEDDING_DEVICE,
                local_files_only=settings.EMBEDDING_LOCAL_FILES_ONLY,
            )
            return True
        except Exception:
            self._embedding_failed = True
            self.embedding_model = None
            return False

    def status(self) -> dict:
        return {
            "enabled": settings.ENABLE_LOCAL_EMBEDDINGS,
            "vector_ready": self.vector_enabled,
            "model": self.model_name,
            "persist_dir": self.persist_dir,
            "local_files_only": settings.EMBEDDING_LOCAL_FILES_ONLY,
            "device": settings.EMBEDDING_DEVICE,
        }

    def _collection_name(self, user_id: str, project_id: str) -> str:
        """旧版集合命名（保持兼容性）"""
        safe_user = user_id.replace(":", "_").replace("/", "_")
        safe_proj = project_id.replace(":", "_").replace("/", "_")
        return f"kb_{safe_user}_{safe_proj}"

    def _external_collection_name(self, user_id: str, project_id: str) -> str:
        """外部知识库集合命名"""
        safe_user = user_id.replace(":", "_").replace("/", "_")
        safe_proj = project_id.replace(":", "_").replace("/", "_")
        return f"external_kb_{safe_user}_{safe_proj}"

    def _chapter_collection_name(self, user_id: str, book_id: int) -> str:
        """全书章节集合命名"""
        safe_user = user_id.replace(":", "_").replace("/", "_")
        return f"chapters_{safe_user}_{book_id}"

    def upsert_document(
        self,
        *,
        user_id: str,
        project_id: str,
        document_id: int,
        chunks: Iterable[tuple[int, str]],
    ) -> int:
        if not self.ensure_ready():
            return 0
        col = self.client.get_or_create_collection(self._external_collection_name(user_id, project_id))

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []

        for chunk_id, text in chunks:
            ids.append(f"chunk:{chunk_id}")
            texts.append(text)
            metadatas.append({"document_id": document_id, "chunk_id": chunk_id})

        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        ).tolist()
        col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(ids)

    def delete_document_chunks(self, *, user_id: str, project_id: str, chunk_ids: Iterable[int]) -> int:
        ids = [f"chunk:{chunk_id}" for chunk_id in chunk_ids]
        if not ids:
            return 0

        if self.client is None:
            return 0

        deleted = 0
        for collection_name in (
            self._external_collection_name(user_id, project_id),
            self._collection_name(user_id, project_id),
        ):
            try:
                col = self.client.get_collection(collection_name)
                col.delete(ids=ids)
                deleted += len(ids)
            except Exception:
                continue
        return deleted

    def search(self, *, user_id: str, project_id: str, query: str, top_k: int = 5) -> list[dict]:
        """旧版搜索（保持兼容性）"""
        if not self.ensure_ready():
            return []
        col = self.client.get_or_create_collection(self._collection_name(user_id, project_id))
        q_emb = self.embedding_model.encode([query], normalize_embeddings=True).tolist()
        res = col.query(query_embeddings=q_emb, n_results=top_k, include=["documents", "metadatas", "distances"])

        out: list[dict] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({"text": doc, "meta": meta, "distance": dist})
        return out

    def search_external(
        self,
        *,
        user_id: str,
        project_id: str,
        query: str,
        top_k: int = 5,
        weight: int = 30,
        document_ids: list[int] | None = None,
    ) -> list[dict]:
        """搜索外部知识库（带权重过滤）"""
        if not self.ensure_ready():
            return []
        # 尝试新集合，回退到旧集合
        try:
            col = self.client.get_collection(self._external_collection_name(user_id, project_id))
        except Exception:
            # 回退到旧集合
            col = self.client.get_or_create_collection(self._collection_name(user_id, project_id))
        q_emb = self.embedding_model.encode([query], normalize_embeddings=True).tolist()
        n_results = top_k * 4 if document_ids else top_k
        res = col.query(query_embeddings=q_emb, n_results=n_results, include=["documents", "metadatas", "distances"])

        out: list[dict] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            # 过滤掉 source_type 为 chapter 的条目
            if meta.get("source_type") == "chapter":
                continue
            if document_ids and meta.get("document_id") not in document_ids:
                continue
            out.append({"text": doc, "meta": meta, "distance": dist})
        return out[:top_k]

    def search_chapters(
        self,
        *,
        user_id: str,
        book_id: int,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """搜索全书章节"""
        if not self.ensure_ready():
            return []
        # 尝试新集合，回退到旧集合（book_ 前缀）
        try:
            col = self.client.get_collection(self._chapter_collection_name(user_id, book_id))
        except Exception:
            # 回退到旧集合命名：kb_{user}_book_{book_id}
            old_project_id = f"book_{book_id}"
            col = self.client.get_or_create_collection(self._collection_name(user_id, old_project_id))
        q_emb = self.embedding_model.encode([query], normalize_embeddings=True).tolist()
        # 只检索 source_type 为 chapter 的条目
        res = col.query(
            query_embeddings=q_emb,
            n_results=top_k * 2,  # 多取一些以便过滤
            include=["documents", "metadatas", "distances"],
            where={"source_type": "chapter"} if col.count() > 0 else None,
        )

        out: list[dict] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({"text": doc, "meta": meta, "distance": dist})
        # 按距离排序并限制数量
        out.sort(key=lambda x: x["distance"])
        return out[:top_k]

    def delete_chapter(self, *, user_id: str, book_id: int, chapter_id: int) -> int:
        """删除章节的所有向量"""
        try:
            col = self.client.get_collection(self._chapter_collection_name(user_id, book_id))
            results = col.get(where={"chapter_id": chapter_id})
            if results and results.get("ids"):
                col.delete(ids=results["ids"])
                return len(results["ids"])
        except Exception:
            # 尝试旧集合
            old_project_id = f"book_{book_id}"
            try:
                col = self.client.get_collection(self._collection_name(user_id, old_project_id))
                results = col.get(where={"chapter_id": chapter_id, "source_type": "chapter"})
                if results and results.get("ids"):
                    col.delete(ids=results["ids"])
                    return len(results["ids"])
            except Exception:
                pass
        return 0

    def upsert_chapter(
        self,
        *,
        user_id: str,
        book_id: int,
        chapter_id: int,
        chunks: Iterable[tuple[int, str]],
        chapter_title: str,
        chapter_kind: str = "prose",
    ) -> int:
        """插入/更新章节向量"""
        if not self.ensure_ready():
            return 0
        # 先删除旧向量
        self.delete_chapter(user_id=user_id, book_id=book_id, chapter_id=chapter_id)
        # 插入新向量
        col = self.client.get_or_create_collection(self._chapter_collection_name(user_id, book_id))
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []
        for chunk_idx, text in chunks:
            chunk_id = f"chapter_{chapter_id}_chunk_{chunk_idx}"
            ids.append(chunk_id)
            texts.append(text)
            metadatas.append({
                "chapter_id": chapter_id,
                "book_id": book_id,
                "chapter_title": chapter_title,
                "chapter_kind": chapter_kind,
                "chunk_index": chunk_idx,
                "source_type": "chapter",
            })
        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        ).tolist()
        col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(ids)


_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


__all__ = ["KnowledgeService", "get_knowledge_service", "_chunk_text"]

