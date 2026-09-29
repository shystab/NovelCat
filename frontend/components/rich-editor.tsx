"use client";

import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Heading from "@tiptap/extension-heading";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import Blockquote from "@tiptap/extension-blockquote";
import Code from "@tiptap/extension-code";
import CodeBlock from "@tiptap/extension-code-block";
import { TextStyle } from "@tiptap/extension-text-style";
import { Chapter, EditorAppearance } from "@/types/api";
import type { Theme, ThemeColors } from "@/hooks/use-theme";
import {
  Save,
  AlignLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  Bold as BoldIcon,
  Italic as ItalicIcon,
  Heading1,
  Heading2,
  Plus,
  Quote,
  Code as CodeIcon,
  History,
  LocateFixed,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { useEffect, useCallback, useRef, useState } from "react";
import ChapterHistoryDialog from "@/components/chapter-history-dialog";

interface RichEditorProps {
  chapter: Chapter | null;
  content: string;
  status: string;
  onChangeContent: (content: string) => void;
  onSave: () => void;
  onRestoreChapter?: (chapter: Chapter) => void;
  previousChapter?: Chapter | null;
  nextChapter?: Chapter | null;
  onSelectChapter?: (id: number) => void;
  onCreateChapter?: () => void;
  theme: Theme;
  colors: ThemeColors;
  showLeft?: boolean;
  showRight?: boolean;
  onToggleLeft?: () => void;
  onToggleRight?: () => void;
  appearance?: EditorAppearance;
}

function wordCount(text: string) {
  const plain = text.replace(/<[^>]+>/g, "");
  const chinese = (plain.match(/[\u4e00-\u9fff]/g) || []).length;
  const english = (plain.match(/\b[a-zA-Z]+\b/g) || []).length;
  return chinese + english;
}

function estimateReadTime(words: number) {
  const mins = Math.ceil(words / 500);
  return mins < 1 ? "< 1 分钟" : `${mins} 分钟`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export default function RichEditor({
  chapter,
  content,
  status,
  onChangeContent,
  onSave,
  onRestoreChapter,
  previousChapter,
  nextChapter,
  onSelectChapter,
  onCreateChapter,
  theme,
  colors,
  showLeft = true,
  showRight = true,
  onToggleLeft,
  onToggleRight,
  appearance,
}: RichEditorProps) {
  const [showHistory, setShowHistory] = useState(false);
  const [glassPaper, setGlassPaper] = useState(() => {
    if (typeof window === "undefined") return true;
    try { return localStorage.getItem("novelcat-glass-paper") !== "false"; } catch { return true; }
  });
  const toggleGlassPaper = () => {
    const next = !glassPaper;
    setGlassPaper(next);
    try { localStorage.setItem("novelcat-glass-paper", String(next)); } catch {}
  };
  const [typewriterMode, setTypewriterMode] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return localStorage.getItem("novelcat-typewriter-mode") === "true";
    } catch {
      return false;
    }
  });
  const typewriterModeRef = useRef(typewriterMode);
  const scrollAreaRef = useRef<HTMLElement>(null);
  const caretFrameRef = useRef<number | null>(null);

  const toggleTypewriterMode = useCallback(() => {
    setTypewriterMode(current => {
      const next = !current;
      typewriterModeRef.current = next;
      try {
        localStorage.setItem("novelcat-typewriter-mode", String(next));
      } catch {}
      return next;
    });
  }, []);

  const focusMode = !showLeft && !showRight;
  const toggleFocusMode = useCallback(() => {
    if (focusMode) {
      onToggleLeft?.();
      onToggleRight?.();
      return;
    }
    if (showLeft) onToggleLeft?.();
    if (showRight) onToggleRight?.();
  }, [focusMode, onToggleLeft, onToggleRight, showLeft, showRight]);

  const keepCaretInComfortZone = useCallback((editorInstance: Editor) => {
    if (!typewriterModeRef.current || !editorInstance.isFocused) return;
    if (caretFrameRef.current !== null) cancelAnimationFrame(caretFrameRef.current);
    caretFrameRef.current = requestAnimationFrame(() => {
      caretFrameRef.current = null;
      const scrollArea = scrollAreaRef.current;
      if (!scrollArea || !typewriterModeRef.current) return;
      const bounds = scrollArea.getBoundingClientRect();
      const caret = editorInstance.view.coordsAtPos(editorInstance.state.selection.head);
      const upper = bounds.top + bounds.height * 0.28;
      const lower = bounds.top + bounds.height * 0.68;
      if (caret.top < upper || caret.bottom > lower) {
        scrollArea.scrollTop += caret.top - (bounds.top + bounds.height * 0.44);
      }
    });
  }, []);

  useEffect(() => () => {
    if (caretFrameRef.current !== null) cancelAnimationFrame(caretFrameRef.current);
  }, []);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: false,
        blockquote: false,
        bold: false,
        italic: false,
        code: false,
        codeBlock: false,
      }),
      Heading.configure({ levels: [1, 2, 3] }),
      Bold,
      Italic,
      Blockquote,
      Code,
      CodeBlock,
      TextStyle,
      Placeholder.configure({
        placeholder: "在这里开启你的创作篇章…",
      }),
    ],
    content: content,
    onUpdate: ({ editor }) => {
      onChangeContent(editor.getHTML());
      keepCaretInComfortZone(editor);
    },
    onSelectionUpdate: ({ editor }) => keepCaretInComfortZone(editor),
    editorProps: {
      attributes: {
        class: "novel-writing-surface prose focus:outline-none min-h-full max-w-none",
        spellcheck: "false",
      },
      transformPastedHTML: (html) => {
        // 把粘贴进来的 HTML 拍平成干净的段落结构，确保首行缩进和段落间距生效
        const doc = new DOMParser().parseFromString(html, "text/html");
        const body = doc.body;

        // 提取纯文本，按双换行分段
        const text = body.textContent || "";
        const paragraphs = text.split(/\n{2,}/).filter(p => p.trim());

        if (paragraphs.length > 0) {
          return paragraphs
            .map(p => `<p>${escapeHtml(p.trim()).replace(/\n/g, "<br>")}</p>`)
            .join("");
        }

        return html;
      },
    },
  });

  // 同步外部 content 变化到编辑器（如插入 AI 内容）
  useEffect(() => {
    if (editor && editor.getHTML() !== content) {
      editor.commands.setContent(content, { emitUpdate: false });
    }
  }, [content, editor]);

  // 章节切换时自动聚焦到编辑器末尾
  useEffect(() => {
    if (!editor || !chapter?.id) return;
    const timer = setTimeout(() => {
      editor.commands.focus("end");
    }, 50);
    return () => clearTimeout(timer);
  }, [chapter?.id, editor]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onSave();
    }
    if (e.key === "Tab") {
      e.preventDefault();
      editor?.commands.insertContent("　　");
    }
    if (e.key.toLowerCase() === "l" && e.shiftKey && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      toggleTypewriterMode();
    }
    if (e.key.toLowerCase() === "f" && e.shiftKey && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      toggleFocusMode();
    }
  }, [editor, onSave, toggleFocusMode, toggleTypewriterMode]);

  const paragraphs = content.replace(/<[^>]+>/g, "\n").split(/\n+/).filter(p => p.trim()).length;
  const words = wordCount(content);
  const chars = content.replace(/<[^>]+>/g, "").length;

  const borderClass = theme === 'dark' ? 'border-slate-700/60' : theme === 'sepia' ? 'border-amber-200/50' : 'border-slate-100';
  const textClass = theme === 'dark' ? 'text-slate-100' : theme === 'sepia' ? 'text-amber-950' : 'text-slate-950';
  const headingClass = theme === 'dark' ? 'text-slate-100' : theme === 'sepia' ? 'text-amber-900' : 'text-slate-800';
  const mutedClass = theme === 'dark' ? 'text-slate-500' : theme === 'sepia' ? 'text-amber-500/70' : 'text-slate-350';
  const toolbarBg = theme === 'dark' ? 'bg-slate-800/40' : theme === 'sepia' ? 'bg-amber-100/30' : 'bg-slate-50/80';
  const toolbarBtn = `p-1.5 rounded transition-all ${textClass}`;
  const toolbarBtnActive = theme === 'dark' ? 'bg-slate-700' : theme === 'sepia' ? 'bg-amber-200' : 'bg-slate-200';
  const navButtonClass = `p-1.5 rounded-lg transition-all ${mutedClass} ${
    theme === 'dark' ? 'hover:bg-slate-700/60 hover:text-slate-200 disabled:hover:bg-transparent' :
    theme === 'sepia' ? 'hover:bg-amber-100 hover:text-amber-900 disabled:hover:bg-transparent' :
    'hover:bg-slate-100 hover:text-slate-800 disabled:hover:bg-transparent'
  } disabled:opacity-35 disabled:cursor-not-allowed`;

  const hasBackground = Boolean(appearance?.background_url);
  const editorFontSize = Math.min(Math.max(appearance?.font_size ?? 18, 14), 28);
  const paperOpacity = hasBackground && glassPaper ? (theme === "dark" ? 0.7 : 0.5) : Math.min(Math.max(appearance?.editor_paper_opacity ?? 92, 55), 100) / 100;
  const paperBg = theme === 'dark'
    ? `rgba(15, 23, 42, ${paperOpacity})`
    : theme === 'sepia'
    ? `rgba(255, 251, 235, ${paperOpacity})`
    : hasBackground
    ? `rgba(255, 255, 255, ${paperOpacity})`
    : `rgba(255, 255, 255, ${paperOpacity})`;
  const chromeBg = hasBackground
    ? theme === 'dark' ? 'bg-slate-950/55 backdrop-blur-2xl' : theme === 'sepia' ? 'bg-amber-950/25 backdrop-blur-2xl' : 'bg-slate-950/32 backdrop-blur-2xl'
    : colors.editorBg;

  if (!chapter) {
    return (
      <div className={`flex-1 flex flex-col items-center justify-center ${hasBackground ? "bg-transparent" : colors.editorBg} space-y-6 h-full relative overflow-hidden`}>
        <div className={`relative z-10 w-16 h-16 rounded-lg ${theme === 'dark' ? 'bg-slate-800/80' : 'bg-slate-50/90'} flex items-center justify-center`}>
          <FileText size={28} strokeWidth={1.5} className={theme === 'dark' ? 'text-slate-600' : 'text-slate-300'} />
        </div>
        <div className="relative z-10 text-center space-y-1.5">
          <p className={`text-sm font-semibold ${theme === 'dark' ? 'text-slate-500' : 'text-slate-400'}`}>选择章节开始写作</p>
          <p className={`text-[11px] ${theme === 'dark' ? 'text-slate-600' : 'text-slate-300'}`}>从左侧目录选择或新建章节</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full ${hasBackground ? "bg-transparent" : colors.editorBg} relative overflow-hidden`}>
      {/* 顶部工具栏 */}
      <header className={`px-5 py-2.5 border-b ${borderClass} flex justify-between items-center ${chromeBg} z-30 shrink-0`}>
        {/* 左侧：章节标题 */}
        <div className="flex items-center space-x-2 min-w-0">
          <div className="flex items-center space-x-0.5 shrink-0">
            <button
              onClick={() => previousChapter && onSelectChapter?.(previousChapter.id)}
              disabled={!previousChapter}
              className={navButtonClass}
              type="button"
              title={previousChapter ? `上一章：${previousChapter.title}` : "没有上一章"}
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => nextChapter && onSelectChapter?.(nextChapter.id)}
              disabled={!nextChapter}
              className={navButtonClass}
              type="button"
              title={nextChapter ? `下一章：${nextChapter.title}` : "没有下一章"}
            >
              <ChevronRight size={14} />
            </button>
          </div>
          <h1 className={`font-bold ${headingClass} text-sm tracking-tight truncate max-w-[220px]`}>
            {chapter.title}
          </h1>
          <div className="flex items-center space-x-1.5 shrink-0">
            <div
              className={`w-1.5 h-1.5 rounded-full transition-all ${
                status === "已同步" ? "bg-emerald-400 shadow-sm shadow-emerald-400/50" :
                status === "保存中..." ? "bg-amber-400 animate-pulse shadow-sm shadow-amber-400/50" :
                status === "保存失败" ? "bg-red-400 shadow-sm shadow-red-400/50" :
                `${theme === 'dark' ? 'bg-slate-600' : 'bg-slate-300'} animate-pulse`
              }`}
            />
            <span className={`text-[10px] font-bold ${mutedClass} uppercase tracking-wider`}>{status}</span>
          </div>
        </div>

        {/* 右侧：编辑工具 + 统计 + 保存 */}
        <div className="flex items-center space-x-3 shrink-0">
          {/* 编辑工具栏 */}
          <div className={`hidden md:flex items-center space-x-0.5 p-1 rounded-lg ${toolbarBg}`}>
            <button
              onClick={() => editor?.chain().focus().toggleBold().run()}
              className={`${toolbarBtn} ${editor?.isActive('bold') ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="粗体 (Ctrl+B)" type="button"
            >
              <BoldIcon size={13} />
            </button>
            <button
              onClick={() => editor?.chain().focus().toggleItalic().run()}
              className={`${toolbarBtn} ${editor?.isActive('italic') ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="斜体 (Ctrl+I)" type="button"
            >
              <ItalicIcon size={13} />
            </button>
            <div className="w-px h-3.5 bg-current opacity-15 mx-0.5" />
            <button
              onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()}
              className={`${toolbarBtn} ${editor?.isActive('heading', { level: 1 }) ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="标题 1" type="button"
            >
              <Heading1 size={13} />
            </button>
            <button
              onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}
              className={`${toolbarBtn} ${editor?.isActive('heading', { level: 2 }) ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="标题 2" type="button"
            >
              <Heading2 size={13} />
            </button>
            <div className="w-px h-3.5 bg-current opacity-15 mx-0.5" />
            <button
              onClick={() => editor?.chain().focus().toggleBlockquote().run()}
              className={`${toolbarBtn} ${editor?.isActive('blockquote') ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="引用块" type="button"
            >
              <Quote size={13} />
            </button>
            <button
              onClick={() => editor?.chain().focus().toggleCode().run()}
              className={`${toolbarBtn} ${editor?.isActive('code') ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="行内代码" type="button"
            >
              <CodeIcon size={13} />
            </button>
            <div className="w-px h-3.5 bg-current opacity-15 mx-0.5" />
            <button
              onClick={toggleTypewriterMode}
              className={`${toolbarBtn} ${typewriterMode ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title="光标跟随模式 (Ctrl+Shift+L)"
              aria-label="切换光标跟随模式"
              aria-pressed={typewriterMode}
              type="button"
            >
              <LocateFixed size={13} />
            </button>
            <button
              onClick={toggleFocusMode}
              className={`${toolbarBtn} ${focusMode ? toolbarBtnActive : 'hover:bg-black/5'}`}
              title={`${focusMode ? "退出" : "进入"}专注模式 (Ctrl+Shift+F)`}
              aria-label={`${focusMode ? "退出" : "进入"}专注模式`}
              aria-pressed={focusMode}
              type="button"
            >
              {focusMode ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </div>

          {/* 统计信息 */}
          <div className={`hidden lg:flex items-center space-x-3 text-[10px] font-bold ${mutedClass} uppercase tracking-wider`}>
            <div className="flex items-center space-x-1">
              <AlignLeft size={10} />
              <span>{paragraphs} 段</span>
            </div>
            <span className="opacity-40">·</span>
            <span>{words.toLocaleString()} 字</span>
            <span className="opacity-40">·</span>
            <span>{estimateReadTime(words)}</span>
          </div>

          <button
            onClick={onCreateChapter}
            className={`hidden sm:flex items-center space-x-1.5 text-xs font-bold ${mutedClass} transition-all px-2.5 py-1.5 rounded-lg ${
              theme === 'dark' ? 'hover:bg-slate-700/60 hover:text-slate-200' :
              theme === 'sepia' ? 'hover:bg-amber-100 hover:text-amber-900' :
              'hover:bg-slate-100 hover:text-slate-800'
            }`}
            type="button"
            title="新建章节"
          >
            <Plus size={12} />
            <span>新章</span>
          </button>

          <button
            onClick={() => setShowHistory(true)}
            className={`flex items-center space-x-1.5 text-xs font-bold ${mutedClass} transition-all px-2.5 py-1.5 rounded-lg ${
              theme === 'dark' ? 'hover:bg-slate-700/60 hover:text-slate-200' :
              theme === 'sepia' ? 'hover:bg-amber-100 hover:text-amber-900' :
              'hover:bg-slate-100 hover:text-slate-800'
            }`}
            type="button"
            title="版本历史"
          >
            <History size={12} />
            <span className="hidden xl:inline">历史</span>
          </button>

          <button
            onClick={onSave}
            className={`flex items-center space-x-1.5 text-xs font-bold ${mutedClass} transition-all px-2.5 py-1.5 rounded-lg ${
              theme === 'dark' ? 'hover:bg-slate-700/60 hover:text-slate-200' :
              theme === 'sepia' ? 'hover:bg-amber-100 hover:text-amber-900' :
              'hover:bg-slate-100 hover:text-slate-800'
            }`}
            type="button"
          >
            <Save size={12} />
            <span>保存</span>
          </button>

        </div>
      </header>

      {/* 编辑区 — 舒适的阅读宽度 + 大行距 */}
      <main ref={scrollAreaRef} className="flex-1 overflow-y-auto custom-scrollbar relative z-10" onKeyDown={handleKeyDown}>
        <div className="w-full max-w-[860px] mx-auto py-8 sm:py-12 px-4 sm:px-8 min-h-full">
          <div
            className={`novelcat-manuscript-sheet min-h-[72vh] rounded-[10px] ${hasBackground ? 'border border-slate-400/25' : ''}`}
            data-theme={theme}
            style={{
              backgroundColor: hasBackground ? paperBg : 'transparent',
              backdropFilter: hasBackground ? (glassPaper ? 'blur(14px) saturate(0.85)' : 'blur(12px)') : undefined,
            }}
          >
          <style>{`
            .novel-writing-surface {
              font-size: ${editorFontSize}px;
              line-height: 2.1;
              letter-spacing: 0;
              text-rendering: optimizeLegibility;
              caret-color: currentColor;
              padding: ${hasBackground ? '2.5rem clamp(1.25rem, 3vw, 3.25rem)' : '0'};
            }
            .novel-writing-surface p {
              margin: 0 0 0.8em;
              text-indent: 2em;
            }
            .novel-writing-surface h1,
            .novel-writing-surface h2 {
              text-indent: 0;
              text-align: center;
            }
            .novel-writing-surface h1 { font-size: 1.45em; font-weight: 700; margin: 1.6em 0 1em; line-height: 1.5; }
            .novel-writing-surface h2 { font-size: 1.22em; font-weight: 700; margin: 1.3em 0 0.8em; line-height: 1.5; }
            .novel-writing-surface blockquote {
              border-left: 3px solid currentColor;
              opacity: 0.7;
              padding-left: 1em;
              margin: 1em 0;
              font-style: italic;
            }
            .novel-writing-surface p.is-editor-empty:first-child::before {
              color: #aaa;
              content: attr(data-placeholder);
              float: left;
              text-indent: 0;
              height: 0;
              pointer-events: none;
            }
          `}</style>
          <EditorContent
            editor={editor}
            className={`w-full min-h-[70vh] focus:outline-none ${textClass}`}
          />
          </div>
        </div>
      </main>

      {/* 底部状态栏 */}
      <div className={`px-6 py-2 border-t ${borderClass} flex items-center justify-between shrink-0 relative z-30 ${chromeBg}`}>
        <span className={`text-[10px] font-bold ${mutedClass} uppercase tracking-wider`}>{chars.toLocaleString()} 字符</span>
        <div className="flex items-center space-x-4">
          {hasBackground && <button type="button" onClick={toggleGlassPaper} aria-pressed={glassPaper}
            className="min-h-8 rounded-md px-2 text-xs text-slate-100 hover:bg-white/15"
            title="磨砂模式透出背景；清晰模式使用设置里的纸张不透明度">
            {glassPaper ? "背景磨砂" : "清晰纸张"}
          </button>}
          <button
            type="button"
            onClick={toggleTypewriterMode}
            className={`hidden sm:inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${typewriterMode ? textClass : mutedClass}`}
            aria-pressed={typewriterMode}
            title="输入时让光标保持在编辑区舒适位置"
          >
            <LocateFixed size={10} />
            光标跟随{typewriterMode ? "已开" : "已关"}
          </button>
          <span className={`text-[10px] ${mutedClass} hidden lg:block`}>Tab 缩进 · Ctrl+Enter 保存 · Ctrl+Shift+L 跟随 · Ctrl+Shift+F 专注</span>
        </div>
      </div>
      {showHistory && onRestoreChapter && (
        <ChapterHistoryDialog
          chapter={chapter}
          onClose={() => setShowHistory(false)}
          onRestore={onRestoreChapter}
        />
      )}
    </div>
  );
}
