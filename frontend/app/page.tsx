"use client";

/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import Link from "next/link";
import ChapterList from "@/components/chapter-list";
import NovelEditor from "@/components/novel-editor";
import AIChat from "@/components/ai-chat";
import BookSelector from "@/components/book-selector";
import { api, getStoredUser, withAccessToken } from "@/lib/api";
import { AuthUser, Book, Chapter, EditorAppearance } from "@/types/api";
import { LogOut, PanelLeftOpen, PanelRightOpen, ShieldCheck, Users } from "lucide-react";
import { useTheme } from "@/hooks/use-theme";
import AppBackgroundLayers from "@/components/app-background-layers";
import { clearChapterDraft, loadChapterDraft, saveChapterDraft } from "@/lib/chapter-drafts";

const SESSION_KEY = "novelcat_session";
const ACTIVE_BOOK_KEY = "novelcat_active_book";

interface SessionState {
  selectedChapterId: number | null;
  content: string;
  showLeft: boolean;
  showRight: boolean;
}

function saveSession(state: SessionState) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
  } catch {}
}

function loadSession(): SessionState | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function userInitials(user: AuthUser) {
  return (user.display_name || user.username || "?").slice(0, 2).toUpperCase();
}

export default function Home() {
  // ── 书籍状态 ──────────────────────────────────────
  const [books, setBooks] = useState<Book[]>([]);
  const [activeBookId, setActiveBookId] = useState<number | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);

  // ── 编辑器状态 ────────────────────────────────────
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [content, setContent] = useState("");
  const [status, setStatus] = useState("闲置");
  const [autoSaveInterval, setAutoSaveInterval] = useState(2);
  const [editorAppearance, setEditorAppearance] = useState<EditorAppearance>({
    background_blur: 0,
    background_dim: 22,
    editor_paper_opacity: 92,
    font_size: 18,
  });
  const lastSavedRef = useRef("");
  const draftUserRef = useRef("default_user");

  const [showLeft, setShowLeft] = useState(true);
  const [showRight, setShowRight] = useState(true);
  const [leftWidth, setLeftWidth] = useState(300);
  const [rightWidth, setRightWidth] = useState(380);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const { theme, colors } = useTheme();

  // ── 启动序列 ──────────────────────────────────────
  useEffect(() => {
    async function init() {
      const storedUser = getStoredUser();
      setCurrentUser(storedUser);
      draftUserRef.current = storedUser?.username || "default_user";
      // 1. 恢复面板状态
      const savedSession = loadSession();
      if (savedSession) {
        setShowLeft(savedSession.showLeft);
        setShowRight(savedSession.showRight);
      }

      try {
        const user = await api.me().catch(() => null);
        if (user) {
          setCurrentUser(user);
          draftUserRef.current = user.username;
        }
      } catch {}

      try {
        const settings = await api.getSettings();
        setAutoSaveInterval(Math.max(0, settings.auto_save_interval ?? 2));
        const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
        setEditorAppearance({
          background_image_path: settings.background_image_path,
          background_blur: settings.background_blur ?? 0,
          background_dim: settings.background_dim ?? 22,
          editor_paper_opacity: settings.editor_paper_opacity ?? 92,
          font_size: settings.font_size ?? 18,
          background_url: settings.background_image_path ? withAccessToken(`${apiBase}/settings/background?v=${encodeURIComponent(settings.background_image_path)}`) : undefined,
        });
      } catch {
        console.error("加载自动保存设置失败");
      }

      // 2. 加载书籍列表
      let bookList: Book[] = [];
      try {
        bookList = await api.listBooks();
        setBooks(bookList);
      } catch {
        console.error("加载书籍列表失败");
        return;
      }

      if (bookList.length === 0) return;

      // 3. 确定活跃书籍（读 localStorage → 找到就用，否则用第一本）
      let targetBookId = bookList[0].id;
      try {
        const storedId = localStorage.getItem(ACTIVE_BOOK_KEY);
        if (storedId) {
          const parsedId = parseInt(storedId, 10);
          if (bookList.some((b) => b.id === parsedId)) {
            targetBookId = parsedId;
          }
        }
      } catch {}

      setActiveBookId(targetBookId);

      // 4. 加载该书籍的章节
      let chapterList: Chapter[] = [];
      try {
        chapterList = await api.listChapters(targetBookId);
        setChapters(chapterList);
      } catch {
        console.error("加载章节列表失败");
      }

      // 5. 恢复上次选中的章节（仅属于当前书籍时才恢复）
      if (savedSession?.selectedChapterId) {
        const belongs = chapterList.some(
          (c) => c.id === savedSession.selectedChapterId
        );
        if (belongs) {
          setSelectedChapterId(savedSession.selectedChapterId);
          try {
            const data = await api.getChapterInBook(
              targetBookId,
              savedSession.selectedChapterId
            );
            setChapter(data);
            const persistentDraft = loadChapterDraft(draftUserRef.current, targetBookId, data.id);
            const recoveredContent = persistentDraft?.content || savedSession.content;
            if (recoveredContent && recoveredContent !== data.content) {
              setContent(recoveredContent);
              lastSavedRef.current = data.content;
              setStatus("已恢复草稿");
            } else {
              setContent(data.content);
              lastSavedRef.current = data.content;
              setStatus("已同步");
            }
          } catch {
            setStatus("加载失败");
          }
        }
      }
    }
    void init();
  }, []);

  // ── 切回页面时刷新（跨设备同步） ────────────────
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (!activeBookId) return;

      api.listBooks().then(bookList => {
        setBooks(bookList);
        if (bookList.length > 0 && !bookList.some(b => b.id === activeBookId)) {
          const firstId = bookList[0].id;
          setActiveBookId(firstId);
          api.listChapters(firstId).then(chapters => setChapters(chapters)).catch(() => {});
          return;
        }
        if (bookList.length === 0) {
          setActiveBookId(null);
          setChapters([]);
          setSelectedChapterId(null);
          setChapter(null);
          setContent("");
          return;
        }
      }).catch(() => {});

      api.listChapters(activeBookId).then(chapters => {
        setChapters(chapters);
        setSelectedChapterId(prev => {
          if (prev && !chapters.some(c => c.id === prev)) {
            const first = chapters[0];
            if (first) {
              api.getChapterInBook(activeBookId, first.id).then(data => {
                setChapter(data);
                setContent(data.content);
                lastSavedRef.current = data.content;
                setStatus("已同步");
              }).catch(() => {});
              return first.id;
            }
            return null;
          }
          return prev;
        });
      }).catch(() => {});
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [activeBookId]);

  const handleLogout = useCallback(() => {
    api.logout();
    try {
      sessionStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(ACTIVE_BOOK_KEY);
    } catch {}
    window.location.href = "/login";
  }, []);

  // ── 持久化 session ────────────────────────────────
  useEffect(() => {
    saveSession({ selectedChapterId, content, showLeft, showRight });
  }, [selectedChapterId, content, showLeft, showRight]);

  // ── 书籍切换 ──────────────────────────────────────
  const handleBookSwitch = useCallback(async (bookId: number) => {
    setActiveBookId(bookId);
    try { localStorage.setItem(ACTIVE_BOOK_KEY, String(bookId)); } catch {}

    // 清空编辑器
    setSelectedChapterId(null);
    setChapter(null);
    setContent("");
    lastSavedRef.current = "";
    setStatus("闲置");

    // 加载新书的章节
    try {
      const newChapters = await api.listChapters(bookId);
      setChapters(newChapters);
    } catch {
      console.error("切换书籍时加载章节失败");
    }
  }, []);

  const handleBooksChange = useCallback((newBooks: Book[]) => {
    setBooks(newBooks);
  }, []);

  const updateCurrentChapterContent = useCallback((chapterId: number, nextContent: string) => {
    setChapter((current) => (
      current?.id === chapterId ? { ...current, content: nextContent } : current
    ));
    setChapters((current) => current.map((item) => (
      item.id === chapterId ? { ...item, content: nextContent } : item
    )));
  }, []);

  const saveCurrentChapter = useCallback(async () => {
    if (!selectedChapterId) return true;
    if (content === lastSavedRef.current) return true;

    setStatus("保存中...");
    try {
      let savedChapter: Chapter;
      if (activeBookId) {
        savedChapter = await api.updateChapterInBook(activeBookId, selectedChapterId, { content });
      } else {
        savedChapter = await api.updateChapter(selectedChapterId, { content });
      }
      setChapter(savedChapter);
      setChapters((current) => current.map((item) => (
        item.id === selectedChapterId ? { ...item, ...savedChapter } : item
      )));
      lastSavedRef.current = content;
      if (activeBookId) {
        clearChapterDraft(draftUserRef.current, activeBookId, selectedChapterId);
      }
      setStatus("已同步");
      return true;
    } catch {
      setStatus("保存失败");
      return false;
    }
  }, [selectedChapterId, content, activeBookId]);

  // ── 章节操作 ──────────────────────────────────────
  const loadChapter = useCallback(
    async (id: number) => {
      if (id === -1) {
        setChapter(null);
        setContent("");
        setSelectedChapterId(null);
        lastSavedRef.current = "";
        setStatus("闲置");
        return;
      }
      setStatus("加载中...");
      try {
        // 优先用书籍作用域接口，fallback 旧接口
        let data: Chapter;
        if (activeBookId) {
          data = await api.getChapterInBook(activeBookId, id);
        } else {
          data = await api.getChapter(id);
        }
        setChapter(data);
        const persistentDraft = activeBookId
          ? loadChapterDraft(draftUserRef.current, activeBookId, data.id)
          : null;
        setContent(persistentDraft?.content || data.content);
        lastSavedRef.current = data.content;
        setStatus(persistentDraft?.content && persistentDraft.content !== data.content ? "已恢复草稿" : "已同步");
      } catch {
        setStatus("加载失败");
      }
    },
    [activeBookId]
  );

  const handleChapterSelect = async (id: number) => {
    const saved = await saveCurrentChapter();
    if (!saved) return;
    setSelectedChapterId(id === -1 ? null : id);
    await loadChapter(id);
  };

  // 章节列表变化时（新建/删除），同步刷新
  const handleChaptersChange = useCallback(
    async (newChapters: Chapter[]) => {
      setChapters(newChapters);
    },
    []
  );

  const getEditorContent = useCallback(() => content, [content]);

  const syncCurrentChapterDraft = useCallback((nextContent: string) => {
    if (!selectedChapterId) return;
    updateCurrentChapterContent(selectedChapterId, nextContent);
  }, [selectedChapterId, updateCurrentChapterContent]);

  const handleContentChange = useCallback((nextContent: string) => {
    setContent(nextContent);
    syncCurrentChapterDraft(nextContent);
    if (selectedChapterId && nextContent !== lastSavedRef.current) {
      setStatus("未保存");
    }
  }, [selectedChapterId, syncCurrentChapterDraft]);

  useEffect(() => {
    if (!activeBookId || !selectedChapterId) return;
    if (content === lastSavedRef.current) {
      clearChapterDraft(draftUserRef.current, activeBookId, selectedChapterId);
      return;
    }
    saveChapterDraft(draftUserRef.current, activeBookId, selectedChapterId, content);
  }, [activeBookId, selectedChapterId, content]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!selectedChapterId || content === lastSavedRef.current) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [content, selectedChapterId]);

  const handleSave = useCallback(async () => {
    await saveCurrentChapter();
  }, [saveCurrentChapter]);

  const handleRestoreChapter = useCallback((restored: Chapter) => {
    setChapter(restored);
    setContent(restored.content);
    setChapters((current) => current.map((item) => item.id === restored.id ? restored : item));
    lastSavedRef.current = restored.content;
    if (restored.book_id) {
      clearChapterDraft(draftUserRef.current, restored.book_id, restored.id);
    }
    setStatus("已恢复历史版本");
  }, []);

  const orderedChapters = [...chapters].sort((a, b) => (a.order || 0) - (b.order || 0));
  const currentChapterIndex = selectedChapterId
    ? orderedChapters.findIndex((item) => item.id === selectedChapterId)
    : -1;
  const previousChapter = currentChapterIndex > 0 ? orderedChapters[currentChapterIndex - 1] : null;
  const nextChapter = currentChapterIndex >= 0 && currentChapterIndex < orderedChapters.length - 1
    ? orderedChapters[currentChapterIndex + 1]
    : null;

  const handleCreateChapterFromEditor = useCallback(async () => {
    if (!activeBookId) return;
    const saved = await saveCurrentChapter();
    if (!saved) return;

    const nextOrder = Math.max(0, ...chapters.map(item => item.order || 0)) + 1;
    try {
      const newChapter = await api.createChapterInBook(activeBookId, {
        title: `第 ${nextOrder} 章`,
        content: "",
        order: nextOrder,
        kind: "prose",
      });
      setChapters((current) => [...current, newChapter]);
      setSelectedChapterId(newChapter.id);
      setChapter(newChapter);
      setContent("");
      lastSavedRef.current = "";
      setStatus("已同步");
    } catch {
      setStatus("新建失败");
    }
  }, [activeBookId, chapters, saveCurrentChapter]);

  // 自动保存（按设置页配置的秒数防抖；0 表示关闭）
  useEffect(() => {
    if (!selectedChapterId) return;
    if (autoSaveInterval <= 0) return;
    if (content === lastSavedRef.current) return;
    const timer = setTimeout(() => {
      void handleSave();
    }, autoSaveInterval * 1000);
    return () => clearTimeout(timer);
  }, [content, selectedChapterId, autoSaveInterval, handleSave]);

  const toggleLeft = () => {
    if (window.innerWidth < 1120) setShowRight(false);
    setShowLeft((v) => !v);
  };
  const toggleRight = () => {
    if (window.innerWidth < 1120) setShowLeft(false);
    setShowRight((v) => !v);
  };

  useEffect(() => {
    const collapseForViewport = () => {
      if (window.innerWidth < 1120) setShowRight(false);
      if (window.innerWidth < 760) setShowLeft(false);
    };
    collapseForViewport();
    window.addEventListener("resize", collapseForViewport);
    return () => window.removeEventListener("resize", collapseForViewport);
  }, []);
  const resizeLineClass =
    theme === "dark"
      ? "bg-slate-700 group-hover:bg-slate-500"
      : theme === "sepia"
        ? "bg-amber-200 group-hover:bg-amber-400"
        : "bg-slate-200 group-hover:bg-slate-400";

  const startResize = useCallback((
    side: "left" | "right",
    event: ReactMouseEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const startLeftWidth = leftWidth;
    const startRightWidth = rightWidth;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      if (side === "left") {
        setLeftWidth(Math.min(460, Math.max(240, startLeftWidth + delta)));
      } else {
        setRightWidth(Math.min(580, Math.max(300, startRightWidth - delta)));
      }
    };

    const onMouseUp = () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, [leftWidth, rightWidth]);

  const resizeHandle = (id: string, side: "left" | "right") => (
    <div
      id={id}
      role="separator"
      aria-orientation="vertical"
      tabIndex={-1}
      className="group relative h-full w-2 cursor-col-resize outline-none"
      onMouseDown={(event) => startResize(side, event)}
    >
      <div className={`absolute left-1/2 top-0 h-full w-px -translate-x-1/2 transition-colors ${resizeLineClass}`} />
    </div>
  );

  const gridTemplateColumns = [
    showLeft ? `${leftWidth}px` : "",
    showLeft ? "8px" : "",
    "minmax(420px, 1fr)",
    showRight ? "8px" : "",
    showRight ? `${rightWidth}px` : "",
  ].filter(Boolean).join(" ");
  const hasWorkspaceBackground = Boolean(editorAppearance.background_url);
  const backgroundDim = Math.min(Math.max(editorAppearance.background_dim ?? 22, 0), 85) / 100;
  const glassTextClass = hasWorkspaceBackground
    ? "text-slate-100"
    : colors.text;
  const avatarUrl = currentUser?.avatar_image_path
    ? api.avatarUrl(currentUser.username, currentUser.avatar_image_path)
    : "";

  return (
    <main className={`relative flex min-h-screen h-screen overflow-hidden ${glassTextClass} ${hasWorkspaceBackground ? "novelcat-glass-workspace" : colors.bg} flex-col`}>
      <AppBackgroundLayers
        url={editorAppearance.background_url}
        blur={editorAppearance.background_blur}
        dim={backgroundDim * 100}
        mode="workspace"
        position="absolute"
      />
      <div
        className="novelcat-workspace-grid relative z-10 grid flex-1 min-h-0 w-full"
        style={{ gridTemplateColumns }}
      >

        {/* 左侧：书籍选择器 + 章节列表 */}
        {showLeft && (
          <>
            <aside id="left-sidebar" className={`min-w-0 overflow-hidden ${hasWorkspaceBackground ? "p-2 pr-0" : ""}`}>
              <div className="flex flex-col h-full">
                {/* 章节列表 */}
                <div className="flex-1 min-h-0">
                  <ChapterList
                    bookId={activeBookId}
                    chapters={chapters}
                    onChaptersChange={handleChaptersChange}
                    onChapterSelect={handleChapterSelect}
                    selectedChapterId={selectedChapterId}
                    theme={theme}
                    colors={colors}
                    onToggleLeft={toggleLeft}
                    bookSelector={(
                      <BookSelector
                        books={books}
                        activeBookId={activeBookId}
                        onSwitch={handleBookSwitch}
                        onBooksChange={handleBooksChange}
                        theme={theme}
                        colors={colors}
                      />
                    )}
                  />
                </div>
                {currentUser && (
                  <div
                    className={`flex shrink-0 items-center gap-1 border-t px-2 py-2 ${
                      theme === "dark"
                        ? "border-slate-700 bg-slate-900 text-slate-300"
                        : theme === "sepia"
                        ? "border-amber-200 bg-amber-50 text-amber-800"
                        : "border-slate-200 bg-white text-slate-700"
                    }`}
                  >
                    <Link
                      href="/people/me"
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1.5 hover:bg-black/5"
                      title="我的主页"
                    >
                      <div
                        className="relative h-7 w-7 shrink-0 overflow-hidden rounded-md text-[10px] font-bold text-white"
                        style={{ backgroundColor: currentUser.avatar_color || "#f97316" }}
                      >
                        <div className="flex h-full w-full items-center justify-center">{userInitials(currentUser)}</div>
                        {avatarUrl && (
                          <img
                            src={avatarUrl}
                            alt=""
                            onError={(event) => {
                              event.currentTarget.style.display = "none";
                            }}
                            className="absolute inset-0 h-full w-full object-cover"
                          />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-semibold">
                          {currentUser.display_name || currentUser.username}
                        </div>
                        <div className="truncate text-[10px] opacity-60">我的主页</div>
                      </div>
                    </Link>
                    <Link
                      href="/people"
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md opacity-65 hover:bg-black/5 hover:opacity-100"
                      title="伙伴与聊天"
                    >
                      <Users size={15} />
                    </Link>
                    {currentUser.is_admin && (
                      <Link
                        href="/admin"
                        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md opacity-65 hover:bg-black/5 hover:opacity-100"
                        title="管理员中心"
                      >
                        <ShieldCheck size={15} />
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md opacity-65 hover:bg-red-500/10 hover:text-red-500 hover:opacity-100"
                      title="退出登录"
                    >
                      <LogOut size={15} />
                    </button>
                  </div>
                )}
              </div>
            </aside>
            {resizeHandle("left-resize", "left")}
          </>
        )}

        {/* 中间：编辑器 */}
        <section id="editor" className="min-w-0 overflow-hidden">
          <div className="flex flex-col h-full relative">
            <NovelEditor
              chapter={chapter}
              content={content}
              status={status}
              onChangeContent={handleContentChange}
              onSave={handleSave}
              onRestoreChapter={handleRestoreChapter}
              previousChapter={previousChapter}
              nextChapter={nextChapter}
              onSelectChapter={(id) => { void handleChapterSelect(id); }}
              onCreateChapter={handleCreateChapterFromEditor}
              theme={theme}
              colors={colors}
              showLeft={showLeft}
              showRight={showRight}
              onToggleLeft={toggleLeft}
              onToggleRight={toggleRight}
              appearance={editorAppearance}
            />
          </div>
        </section>

        {/* 右侧：AI 对话（折叠时 display:none 不卸载组件，保留 WebSocket 连接） */}
        {showRight && resizeHandle("right-resize", "right")}
        <aside
          id="ai-sidebar"
          className={`min-w-0 overflow-hidden ${hasWorkspaceBackground ? "p-2 pl-0" : ""}`}
          style={{ display: showRight ? undefined : "none" }}
        >
          <AIChat
            hasBackground={Boolean(editorAppearance.background_url)}
            getEditorContent={getEditorContent}
            theme={theme}
            colors={colors}
            onToggleRight={toggleRight}
            bookId={activeBookId}
            chapters={chapters}
            currentChapterId={selectedChapterId}
          />
        </aside>

      </div>

      {/* 左侧面板收起时，显示展开按钮（固定在左边缘） */}
      {!showLeft && (
        <button
          onClick={toggleLeft}
          className={`fixed left-0 top-1/2 -translate-y-1/2 z-[200] py-3 px-1.5 rounded-r-lg shadow-md transition-all ${
            theme === 'dark'
              ? 'bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              : theme === 'sepia'
              ? 'bg-amber-100 text-amber-600 hover:text-amber-900 hover:bg-amber-200'
              : 'bg-white text-slate-400 hover:text-slate-700 hover:bg-slate-50'
          }`}
          title="显示目录"
          type="button"
        >
          <PanelLeftOpen size={15} />
        </button>
      )}

      {/* 右侧面板收起时，显示展开按钮（固定在右边缘） */}
      {!showRight && (
        <button
          onClick={toggleRight}
          className={`fixed right-0 top-1/2 -translate-y-1/2 z-[200] py-3 px-1.5 rounded-l-lg shadow-md transition-all ${
            theme === 'dark'
              ? 'bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              : theme === 'sepia'
              ? 'bg-amber-100 text-amber-600 hover:text-amber-900 hover:bg-amber-200'
              : 'bg-white text-slate-400 hover:text-slate-700 hover:bg-slate-50'
          }`}
          title="显示 AI"
          type="button"
        >
          <PanelRightOpen size={15} />
        </button>
      )}
    </main>
  );
}
