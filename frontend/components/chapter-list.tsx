"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import Link from "next/link";
import { Chapter } from "@/types/api";
import { api, authHeaders, withAccessToken } from "@/lib/api";
import { ArrowDown, ArrowUp, Check, ChevronDown, Download, FileText, GripVertical, PanelLeftClose, Pencil, Plus, Search, Settings, Trash2, X } from "lucide-react";
import type { Theme, ThemeColors } from "@/hooks/use-theme";
import ConfirmDialog from "@/components/confirm-dialog";

interface ChapterListProps {
  bookId: number | null;
  chapters: Chapter[];
  onChaptersChange: (chapters: Chapter[]) => void;
  onChapterSelect: (id: number) => void;
  selectedChapterId: number | null;
  theme: Theme;
  colors: ThemeColors;
  onToggleLeft: () => void;
  bookSelector?: React.ReactNode;
}

function plainText(html: string) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function countNovelChars(value: string) {
  return plainText(value).replace(/\s/g, "").length;
}

function formatCount(value: number) {
  if (value >= 10000) return `${(value / 10000).toFixed(value >= 100000 ? 0 : 1)} 万`;
  return value.toLocaleString();
}

type ChapterKind = NonNullable<Chapter["kind"]>;

const CHAPTER_KINDS: Array<{ value: ChapterKind; label: string }> = [
  { value: "outline", label: "大纲" },
  { value: "prose", label: "正文" },
  { value: "note", label: "笔记" },
  { value: "reference", label: "资料" },
];

const CHAPTER_KIND_ORDER: ChapterKind[] = ["outline", "prose", "note", "reference"];

function chapterKindLabel(kind: ChapterKind | undefined) {
  return CHAPTER_KINDS.find(item => item.value === (kind || "prose"))?.label || "正文";
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightedText(text: string, terms: string[], highlightClass: string) {
  const cleanTerms = terms.filter(Boolean);
  if (cleanTerms.length === 0) return text;

  const pattern = cleanTerms.map(escapeRegExp).join("|");
  const parts = text.split(new RegExp(`(${pattern})`, "gi"));
  return parts.map((part, index) => {
    const isMatch = cleanTerms.some(term => part.toLowerCase() === term.toLowerCase());
    return isMatch ? (
      <mark key={`${part}-${index}`} className={highlightClass}>
        {part}
      </mark>
    ) : part;
  });
}

function searchSnippet(chapter: Chapter, terms: string[]) {
  if (terms.length === 0) return null;

  const sources = [
    { label: "标题", text: chapter.title },
    { label: "摘要", text: chapter.summary || "" },
    { label: "正文", text: plainText(chapter.content) },
  ];

  for (const source of sources) {
    const lower = source.text.toLowerCase();
    let firstMatch: number | undefined;
    for (const term of terms) {
      const index = lower.indexOf(term);
      if (index >= 0 && (firstMatch === undefined || index < firstMatch)) {
        firstMatch = index;
      }
    }

    if (firstMatch === undefined) continue;

    const start = Math.max(0, firstMatch - 24);
    const end = Math.min(source.text.length, firstMatch + 64);
    const prefix = start > 0 ? "..." : "";
    const suffix = end < source.text.length ? "..." : "";
    return {
      label: source.label,
      text: `${prefix}${source.text.slice(start, end)}${suffix}`,
    };
  }

  return null;
}

// ── 导出弹窗 ──────────────────────────────────────────────────────────────────
interface ExportModalProps {
  bookId: number | null;
  chapters: Chapter[];
  onClose: () => void;
  theme: Theme;
}

function ExportModal({ bookId, chapters, onClose, theme }: ExportModalProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set(chapters.map(c => c.id)));
  const [fmt, setFmt] = useState<"txt" | "docx">("txt");
  const [syncStatus, setSyncStatus] = useState("");

  const toggle = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(prev => prev.size === chapters.length ? new Set() : new Set(chapters.map(c => c.id)));
  };

  const handleExport = () => {
    const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    const ids = Array.from(selected).join(",");
    if (!ids) return;
    const path = bookId ? `books/${bookId}/export/${fmt}` : `chapters/export/${fmt}`;
    window.location.href = withAccessToken(`${BASE}/${path}?ids=${ids}`);
    onClose();
  };

  const handleSyncWorkspace = async () => {
    if (!bookId) return;
    const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    setSyncStatus("同步中...");
    try {
      const res = await fetch(`${BASE}/books/${bookId}/workspace/sync`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSyncStatus(`已同步 ${data.chapter_count ?? 0} 章到作品文件夹`);
    } catch {
      setSyncStatus("同步失败");
    }
  };

  const bg = theme === 'dark' ? 'bg-slate-900' : theme === 'sepia' ? 'bg-amber-50' : 'bg-white';
  const headerBg = theme === 'dark' ? 'bg-slate-800' : theme === 'sepia' ? 'bg-amber-100/60' : 'bg-slate-50';
  const border = theme === 'dark' ? 'border-slate-700' : theme === 'sepia' ? 'border-amber-200' : 'border-slate-200';
  const text = theme === 'dark' ? 'text-slate-200' : theme === 'sepia' ? 'text-amber-900' : 'text-slate-800';
  const muted = theme === 'dark' ? 'text-slate-400' : theme === 'sepia' ? 'text-amber-600' : 'text-slate-500';
  const rowHover = theme === 'dark' ? 'hover:bg-slate-800' : theme === 'sepia' ? 'hover:bg-amber-100/60' : 'hover:bg-slate-50';
  const btnActive = theme === 'dark' ? 'bg-slate-700 text-slate-100' : theme === 'sepia' ? 'bg-amber-800 text-white' : 'bg-slate-900 text-white';
  const btnInactive = theme === 'dark' ? 'bg-slate-800 text-slate-400 hover:bg-slate-700' : theme === 'sepia' ? 'bg-amber-200 text-amber-700 hover:bg-amber-300' : 'bg-slate-100 text-slate-500 hover:bg-slate-200';

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className={`${bg} flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-lg border shadow-lg ${border}`}
        onClick={e => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className={`px-6 py-4 border-b ${border} ${headerBg} flex justify-between items-center shrink-0`}>
          <div className="flex items-center space-x-3">
            <div className={`rounded-md p-2 ${theme === 'dark' ? 'bg-slate-700' : theme === 'sepia' ? 'bg-amber-800' : 'bg-slate-900'} text-white`}>
              <Download size={16} />
            </div>
            <div>
              <div className={`font-bold text-sm ${text}`}>导出章节</div>
              <div className={`text-xs ${muted}`}>勾选要导出的章节</div>
            </div>
          </div>
          <button onClick={onClose} className={`rounded-md p-1.5 ${rowHover} ${muted} transition-colors`} type="button" aria-label="关闭导出窗口">
            <X size={16} />
          </button>
        </div>

        {/* 格式选择 */}
        <div className={`px-6 py-3 border-b ${border} flex items-center space-x-2 shrink-0`}>
          <span className={`mr-2 text-xs font-bold ${muted}`}>格式</span>
          <button
            onClick={() => setFmt("txt")}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${fmt === "txt" ? btnActive : btnInactive}`}
            type="button"
          >TXT</button>
          <button
            onClick={() => setFmt("docx")}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${fmt === "docx" ? btnActive : btnInactive}`}
            type="button"
          >DOCX</button>
        </div>

        {/* 全选行 */}
        <div className={`px-6 py-2.5 border-b ${border} shrink-0`}>
          <label className={`flex items-center space-x-3 cursor-pointer ${rowHover} rounded-lg px-1 py-1 transition-colors`}>
            <input
              type="checkbox"
              checked={selected.size === chapters.length}
              onChange={toggleAll}
              className="w-3.5 h-3.5 accent-slate-900 cursor-pointer"
            />
            <span className={`text-xs font-bold ${text}`}>全选 ({chapters.length} 章)</span>
          </label>
        </div>

        {/* 章节列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-3 space-y-0.5">
          {chapters.map(c => (
            <label key={c.id} className={`flex items-center space-x-3 cursor-pointer ${rowHover} rounded-lg px-1 py-2 transition-colors`}>
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
                className="w-3.5 h-3.5 accent-slate-900 cursor-pointer shrink-0"
              />
              <FileText size={12} className={muted} />
              <span className={`text-xs truncate ${text}`}>{c.title}</span>
            </label>
          ))}
        </div>

        {/* 底部操作 */}
        <div className={`px-6 py-4 border-t ${border} flex items-center justify-between shrink-0`}>
          <span className={`text-[10px] ${muted}`}>
            {syncStatus || `已选 ${selected.size} / ${chapters.length} 章`}
          </span>
          <div className="flex items-center space-x-2">
            {bookId && (
              <button
                onClick={handleSyncWorkspace}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${btnInactive}`}
                type="button"
              >
                同步文件夹
              </button>
            )}
            <button
              onClick={onClose}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${btnInactive}`}
              type="button"
            >取消</button>
            <button
              onClick={handleExport}
              disabled={selected.size === 0}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${btnActive} disabled:opacity-40 disabled:cursor-not-allowed`}
              type="button"
            >
              导出 {selected.size > 0 ? `${selected.size} 章` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 主组件 ─────────────────────────────────────────────────────────────────────
export default function ChapterList({ bookId, chapters, onChaptersChange, onChapterSelect, selectedChapterId, theme, onToggleLeft, bookSelector }: ChapterListProps) {
  const [loading] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Chapter | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [movingId, setMovingId] = useState<number | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [dragOverId, setDragOverId] = useState<number | null>(null);
  const [kindMenuChapterId, setKindMenuChapterId] = useState<number | null>(null);
  const [kindMenuRect, setKindMenuRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId !== null && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleCreateChapter = async () => {
    if (!bookId) return;
    const nextOrder = Math.max(0, ...chapters.map(chapter => chapter.order || 0)) + 1;
    try {
      const newChapter = await api.createChapterInBook(bookId, {
        title: `第 ${nextOrder} 章`,
        content: "",
        order: nextOrder,
        kind: "prose",
      });
      onChaptersChange([...chapters, newChapter]);
      onChapterSelect(newChapter.id);
      setEditingId(newChapter.id);
      setEditingTitle(newChapter.title);
    } catch (error) {
      console.error("Failed to create chapter", error);
    }
  };

  const startEdit = (chapter: Chapter, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(chapter.id);
    setEditingTitle(chapter.title);
  };

  const confirmEdit = async () => {
    if (!editingId) return;
    const trimmed = editingTitle.trim();
    if (!trimmed) { cancelEdit(); return; }
    try {
      if (bookId) {
        await api.updateChapterInBook(bookId, editingId, { title: trimmed });
      } else {
        await api.updateChapter(editingId, { title: trimmed });
      }
      onChaptersChange(chapters.map(c => c.id === editingId ? { ...c, title: trimmed } : c));
    } catch (error) {
      console.error("Failed to rename chapter", error);
    } finally {
      setEditingId(null);
    }
  };

  const cancelEdit = () => { setEditingId(null); setEditingTitle(""); };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") confirmEdit();
    if (e.key === "Escape") cancelEdit();
  };

  const handleDelete = async (chapter: Chapter, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteTarget(chapter);
  };

  const handleMoveChapter = async (chapter: Chapter, direction: "up" | "down", e: React.MouseEvent) => {
    e.stopPropagation();
    if (!bookId || movingId) return;

    const ordered = [...chapters].sort((a, b) => (a.order || 0) - (b.order || 0));
    const index = ordered.findIndex(item => item.id === chapter.id);
    const neighbor = direction === "up" ? ordered[index - 1] : ordered[index + 1];
    if (!neighbor) return;

    setMovingId(chapter.id);
    try {
      await Promise.all([
        api.updateChapterInBook(bookId, chapter.id, { order: neighbor.order }),
        api.updateChapterInBook(bookId, neighbor.id, { order: chapter.order }),
      ]);
      onChaptersChange(
        chapters
          .map(item => {
            if (item.id === chapter.id) return { ...item, order: neighbor.order };
            if (item.id === neighbor.id) return { ...item, order: chapter.order };
            return item;
          })
          .sort((a, b) => (a.order || 0) - (b.order || 0))
      );
    } catch (error) {
      console.error("Failed to move chapter", error);
    } finally {
      setMovingId(null);
    }
  };

  const handleKindChange = async (chapter: Chapter, kind: ChapterKind) => {
    try {
      if (bookId) {
        await api.updateChapterInBook(bookId, chapter.id, { kind });
      } else {
        await api.updateChapter(chapter.id, { kind });
      }
      onChaptersChange(chapters.map(c => c.id === chapter.id ? { ...c, kind } : c));
    } catch (error) {
      console.error("Failed to change chapter kind", error);
    }
  };

  const closeKindMenu = () => {
    setKindMenuChapterId(null);
    setKindMenuRect(null);
  };

  const openKindMenu = (chapter: Chapter, e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    if (kindMenuChapterId === chapter.id) {
      closeKindMenu();
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    setKindMenuChapterId(chapter.id);
    setKindMenuRect({
      top: rect.bottom + 4,
      left: rect.left,
      width: Math.max(rect.width, 104),
    });
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (bookId) {
        await api.deleteChapterInBook(bookId, deleteTarget.id);
      } else {
        await api.deleteChapter(deleteTarget.id);
      }
      onChaptersChange(chapters.filter(c => c.id !== deleteTarget.id));
      if (selectedChapterId === deleteTarget.id) onChapterSelect(-1);
      setDeleteTarget(null);
    } catch (error) {
      console.error("Failed to delete chapter", error);
    } finally {
      setDeleting(false);
    }
  };

  const orderedChapters = [...chapters].sort((a, b) => (a.order || 0) - (b.order || 0));
  const query = searchQuery.trim().toLowerCase();
  const queryTerms = query.split(/\s+/).filter(Boolean);
  const visibleChapters = query
    ? orderedChapters.filter(chapter => {
        const haystack = `${chapter.title} ${chapter.summary || ""} ${plainText(chapter.content)}`.toLowerCase();
        return queryTerms.every(term => haystack.includes(term));
      })
    : orderedChapters;
  const kindSections = CHAPTER_KIND_ORDER
    .map(kind => ({
      kind,
      label: chapterKindLabel(kind),
      items: visibleChapters.filter(chapter => (chapter.kind || "prose") === kind),
    }))
    .filter(section => section.items.length > 0);
  const kindMenuChapter = kindMenuChapterId !== null
    ? chapters.find(chapter => chapter.id === kindMenuChapterId) ?? null
    : null;
  const totalChars = chapters.reduce((sum, chapter) => sum + countNovelChars(chapter.content), 0);

  // ── 拖拽排序 ─────────────────────────────────────
  const handleDragStart = (chapterId: number) => {
    setDragId(chapterId);
  };

  const handleDragOver = (e: React.DragEvent, chapterId: number) => {
    e.preventDefault();
    setDragOverId(chapterId);
  };

  const handleDragLeave = () => {
    setDragOverId(null);
  };

  const handleDrop = useCallback(async (e: React.DragEvent, targetId: number) => {
    e.preventDefault();
    setDragOverId(null);
    const sourceId = dragId;
    if (!sourceId || sourceId === targetId || !bookId) return;
    setDragId(null);

    // 把 source 移到 target 的位置
    const ids = orderedChapters.map(c => c.id);
    const srcIdx = ids.indexOf(sourceId);
    const tgtIdx = ids.indexOf(targetId);
    if (srcIdx < 0 || tgtIdx < 0) return;

    ids.splice(srcIdx, 1);
    ids.splice(tgtIdx, 0, sourceId);

    // 乐观更新 UI
    const reordered = ids.map((id, idx) => {
      const ch = chapters.find(c => c.id === id)!;
      return { ...ch, order: idx + 1 };
    });
    onChaptersChange(reordered);

    try {
      await api.reorderChapters(bookId, ids);
    } catch {
      // 失败时回退
      onChaptersChange(chapters);
    }
  }, [dragId, bookId, orderedChapters, chapters, onChaptersChange]);

  const handleDragEnd = () => {
    setDragId(null);
    setDragOverId(null);
  };

  const renderChapterRow = (chapter: Chapter) => {
    const fullIndex = orderedChapters.findIndex(item => item.id === chapter.id);
    const isFirst = fullIndex <= 0;
    const isLast = fullIndex === orderedChapters.length - 1;
    const charCount = countNovelChars(chapter.content);
    const summary = chapter.summary?.trim();
    const snippet = query ? searchSnippet(chapter, queryTerms) : null;

    return (
      <li
        key={chapter.id}
        role="button"
        tabIndex={0}
        draggable={editingId !== chapter.id}
        onDragStart={() => handleDragStart(chapter.id)}
        onDragOver={(e) => handleDragOver(e, chapter.id)}
        onDragLeave={handleDragLeave}
        onDrop={(e) => { void handleDrop(e, chapter.id); }}
        onDragEnd={handleDragEnd}
        onClick={() => editingId !== chapter.id && onChapterSelect(chapter.id)}
        onKeyDown={(event) => {
          if (editingId === chapter.id) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onChapterSelect(chapter.id);
          }
        }}
        className={`group relative px-3 py-2 cursor-pointer rounded-lg transition-all ${
          selectedChapterId === chapter.id
            ? `${selectedBgClass} shadow-sm ring-1`
            : dragOverId === chapter.id
              ? `${hoverBgClass} ring-1 ring-blue-400/50`
              : hoverBgClass
        }`}
      >
        {editingId === chapter.id ? (
          <div className="flex items-center space-x-1" onClick={e => e.stopPropagation()}>
            <input
              ref={editInputRef}
              value={editingTitle}
              onChange={e => setEditingTitle(e.target.value)}
              onKeyDown={handleEditKeyDown}
              className={`flex-1 text-xs bg-transparent border-b ${theme === 'dark' ? 'border-slate-600' : theme === 'sepia' ? 'border-amber-500' : 'border-slate-400'} focus:outline-none ${headingClass} py-0.5`}
            />
            <button onClick={confirmEdit} className="p-1 text-emerald-500 hover:text-emerald-700" type="button"><Check size={12} /></button>
            <button onClick={cancelEdit} className={`p-1 ${mutedClass}`} type="button"><X size={12} /></button>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <GripVertical size={12} className={`shrink-0 opacity-30 group-hover:opacity-60 transition-opacity cursor-grab active:cursor-grabbing ${mutedClass}`} />
              <span className={`text-[10px] font-bold shrink-0 w-4 text-right ${
                selectedChapterId === chapter.id ? textClass : mutedClass
              }`}>
                {String(fullIndex + 1).padStart(2, "0")}
              </span>
              <span className={`flex-1 text-xs truncate ${
                selectedChapterId === chapter.id ? `${headingClass} font-semibold` : textClass
              }`}>
                {chapter.title}
                {chapter.kind && chapter.kind !== "prose" ? ` · ${chapterKindLabel(chapter.kind)}` : ""}
              </span>
              <span className={`text-[10px] tabular-nums shrink-0 ${mutedClass}`}>
                {formatCount(charCount)}
              </span>
              <div className="flex shrink-0 items-center space-x-0.5 opacity-55 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <button
                  onClick={(e) => openKindMenu(chapter, e)}
                  className={`inline-flex h-5 shrink-0 items-center gap-0.5 rounded border px-1 text-[9px] font-medium ${mutedClass} ${borderClass} transition-colors ${hoverTextClass}`}
                  title="章节类型"
                  aria-label={`设置章节类型：${chapter.title}`}
                  type="button"
                >
                  {chapterKindLabel(chapter.kind)}
                  <ChevronDown size={9} className={`transition-transform ${kindMenuChapterId === chapter.id ? "rotate-180" : ""}`} />
                </button>
                <button
                  onClick={(e) => handleMoveChapter(chapter, "up", e)}
                  disabled={isFirst || movingId === chapter.id}
                  className={`p-1 ${mutedClass} ${hoverTextClass} rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed`}
                  type="button"
                  title="上移"
                >
                  <ArrowUp size={10} />
                </button>
                <button
                  onClick={(e) => handleMoveChapter(chapter, "down", e)}
                  disabled={isLast || movingId === chapter.id}
                  className={`p-1 ${mutedClass} ${hoverTextClass} rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed`}
                  type="button"
                  title="下移"
                >
                  <ArrowDown size={10} />
                </button>
                <button
                  onClick={(e) => startEdit(chapter, e)}
                  className={`p-1 ${mutedClass} ${hoverTextClass} rounded transition-colors`}
                  type="button"
                  title="重命名"
                >
                  <Pencil size={10} />
                </button>
                <button
                  onClick={(e) => handleDelete(chapter, e)}
                  className={`p-1 ${mutedClass} hover:text-red-500 rounded transition-colors`}
                  type="button"
                  title="删除"
                >
                  <Trash2 size={10} />
                </button>
              </div>
            </div>
            {snippet ? (
              <div className={`ml-6 line-clamp-2 text-[10px] leading-4 ${mutedClass}`}>
                <span className="font-semibold">{snippet.label}：</span>
                {highlightedText(snippet.text, queryTerms, markClass)}
              </div>
            ) : summary && (
              <div className={`ml-6 line-clamp-2 text-[10px] leading-4 ${mutedClass}`}>
                {summary}
              </div>
            )}
          </div>
        )}
      </li>
    );
  };

  const bgClass = theme === 'dark' ? 'bg-slate-900' : theme === 'sepia' ? 'bg-amber-50/80' : 'bg-slate-50/60';
  const borderClass = theme === 'dark' ? 'border-slate-800' : theme === 'sepia' ? 'border-amber-200' : 'border-slate-100';
  const cardBgClass = theme === 'dark' ? 'bg-slate-800/80' : theme === 'sepia' ? 'bg-amber-100/50' : 'bg-white/90';
  const textClass = theme === 'dark' ? 'text-slate-300' : theme === 'sepia' ? 'text-amber-700' : 'text-slate-600';
  const headingClass = theme === 'dark' ? 'text-slate-100' : theme === 'sepia' ? 'text-amber-900' : 'text-slate-900';
  const mutedClass = theme === 'dark' ? 'text-slate-500' : theme === 'sepia' ? 'text-amber-500' : 'text-slate-400';
  const hoverTextClass = theme === 'dark' ? 'hover:text-slate-300' : theme === 'sepia' ? 'hover:text-amber-700' : 'hover:text-slate-600';
  const hoverBgClass = theme === 'dark' ? 'hover:bg-slate-800' : theme === 'sepia' ? 'hover:bg-amber-100/80' : 'hover:bg-white/80';
  const selectedBgClass = theme === 'dark' ? 'bg-slate-800 ring-slate-700' : theme === 'sepia' ? 'bg-amber-100 ring-amber-300' : 'bg-white ring-slate-200';
  const inputBgClass = theme === 'dark' ? 'bg-slate-950/40' : theme === 'sepia' ? 'bg-amber-50/80' : 'bg-white/80';
  const markClass = theme === 'dark' ? 'bg-amber-400/30 text-amber-100' : theme === 'sepia' ? 'bg-amber-300/60 text-amber-950' : 'bg-yellow-200/80 text-slate-900';

  return (
    <div className={`flex flex-col h-full ${bgClass} border-r ${borderClass}`}>
      {/* 顶部品牌栏 */}
      <div className={`px-4 py-3 border-b ${borderClass} flex justify-between items-center ${cardBgClass} shrink-0`}>
        <div className="flex items-center space-x-2">
          <Image src="/icon.svg" alt="" width={24} height={24} className="rounded-md shadow-sm" priority />
          <span className={`font-bold ${headingClass} text-sm tracking-tight`}>NovelCat</span>
        </div>
        <div className="flex items-center space-x-1">
          <button
            onClick={handleCreateChapter}
            className={`w-7 h-7 flex items-center justify-center ${hoverBgClass} rounded-lg ${textClass} transition-colors`}
            title="新建章节"
            type="button"
          >
            <Plus size={15} />
          </button>
          <button
            onClick={onToggleLeft}
            className={`w-7 h-7 flex items-center justify-center ${hoverBgClass} rounded-lg ${mutedClass} transition-colors`}
            title="收起目录"
            type="button"
          >
            <PanelLeftClose size={15} />
          </button>
        </div>
      </div>

      {/* 作品概览与搜索 */}
      {bookSelector}

      <div className={`px-3 py-3 border-b ${borderClass} ${cardBgClass} shrink-0 space-y-2`}>
        <div className={`grid grid-cols-2 gap-2 text-[10px] ${mutedClass}`}>
          <div className={`rounded-md px-2 py-1.5 ${inputBgClass}`}>
            <div className="font-bold text-[11px] tabular-nums">{chapters.length}</div>
            <div>章节</div>
          </div>
          <div className={`rounded-md px-2 py-1.5 ${inputBgClass}`}>
            <div className="font-bold text-[11px] tabular-nums">{formatCount(totalChars)}</div>
            <div>字数</div>
          </div>
        </div>
        <label className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md border ${borderClass} ${inputBgClass}`}>
          <Search size={12} className={mutedClass} />
          <input
            value={searchQuery}
            onChange={event => setSearchQuery(event.target.value)}
            placeholder="搜索章节、摘要、正文"
            className={`min-w-0 flex-1 bg-transparent text-xs outline-none ${textClass} placeholder:${mutedClass}`}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className={`shrink-0 ${mutedClass} ${hoverTextClass}`}
              type="button"
              title="清空搜索"
            >
              <X size={12} />
            </button>
          )}
        </label>
      </div>

      {/* 章节列表 */}
      <div className={`flex-1 overflow-y-auto custom-scrollbar py-2 px-2`}>
        {loading ? (
          <div className="px-3 py-6 space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className={`h-8 ${theme === 'dark' ? 'bg-slate-800' : theme === 'sepia' ? 'bg-amber-100' : 'bg-slate-100'} rounded-lg animate-pulse`} />
            ))}
          </div>
        ) : chapters.length === 0 ? (
          <div className="px-4 py-10 text-center space-y-2">
            <p className={`text-xs ${mutedClass}`}>暂无章节</p>
            <p className={`text-xs ${mutedClass} opacity-70`}>点击右上角 + 开始创作</p>
          </div>
        ) : visibleChapters.length === 0 ? (
          <div className="px-4 py-10 text-center space-y-2">
            <p className={`text-xs ${mutedClass}`}>没有匹配的章节</p>
            <p className={`text-xs ${mutedClass} opacity-70`}>换个关键词试试</p>
          </div>
        ) : (
          <ul className="space-y-1">
            {kindSections.map(section => (
              <li key={section.kind}>
                <div className={`px-2 pb-1 pt-2 text-[10px] font-medium ${mutedClass}`}>
                  {section.label}
                  <span className="ml-1 opacity-60 tabular-nums">{section.items.length}</span>
                </div>
                <ul className="space-y-0.5">
                  {section.items.map(renderChapterRow)}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 底部工具栏 */}
      <div className={`p-2 border-t ${borderClass} ${cardBgClass} space-y-0.5 shrink-0`}>
        <Link
          href="/settings"
          className={`flex items-center space-x-2.5 px-3 py-2 text-xs ${textClass} ${hoverBgClass} rounded-lg transition-all`}
        >
          <Settings size={13} className={`${mutedClass} shrink-0`} />
          <span className="font-medium">设置 / 知识库</span>
        </Link>
        <button
          onClick={() => setIsExportOpen(true)}
          className={`w-full flex items-center space-x-2.5 px-3 py-2 text-xs ${textClass} ${hoverBgClass} rounded-lg transition-all`}
          type="button"
        >
          <Download size={13} className={`${mutedClass} shrink-0`} />
          <span className="font-medium">导出章节</span>
        </button>
      </div>

      {isExportOpen && (
        <ExportModal
          bookId={bookId}
          chapters={chapters}
          onClose={() => setIsExportOpen(false)}
          theme={theme}
        />
      )}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除章节"
        description={`确定删除「${deleteTarget?.title || "未命名章节"}」吗？这个操作不可撤销。`}
        confirmLabel="删除"
        tone="danger"
        theme={theme}
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {kindMenuChapter && kindMenuRect && document.body && createPortal(
        <>
          <div className="fixed inset-0 z-[9998]" onClick={closeKindMenu} />
          <div
            className="fixed z-[9999] overflow-hidden rounded-lg border shadow-lg"
            style={{
              top: kindMenuRect.top,
              left: kindMenuRect.left,
              width: kindMenuRect.width,
              backgroundColor: theme === 'dark' ? '#1e293b' : theme === 'sepia' ? '#fffbeb' : '#ffffff',
              borderColor: theme === 'dark' ? '#334155' : theme === 'sepia' ? '#fde68a' : '#e2e8f0',
            }}
          >
            {CHAPTER_KINDS.map(item => {
              const active = (kindMenuChapter.kind || "prose") === item.value;
              return (
                <button
                  key={item.value}
                  onClick={() => {
                    void handleKindChange(kindMenuChapter, item.value);
                    closeKindMenu();
                  }}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs transition-colors ${
                    active
                      ? theme === 'dark' ? 'bg-slate-800 text-slate-100' : theme === 'sepia' ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-800'
                      : theme === 'dark' ? 'text-slate-300 hover:bg-slate-800' : theme === 'sepia' ? 'text-amber-700 hover:bg-amber-100' : 'text-slate-600 hover:bg-slate-50'
                  }`}
                  type="button"
                >
                  <span>{item.label}</span>
                  {active && <Check size={11} className="shrink-0 text-emerald-500" />}
                </button>
              );
            })}
          </div>
        </>,
        document.body
      )}
    </div>
  );
}
