"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { flushSync } from "react-dom";
import { useWebSocket } from "@/hooks/use-websocket";
import { api } from "@/lib/api";
import { stripLeakedToolProtocol } from "@/lib/ai-tool-protocol";
import { Send, Square, Sparkles, ChevronDown, PanelRightClose, Library, Trash2, Plus, Copy, Check, History, SlidersHorizontal, X, Search } from "lucide-react";
import type { Theme, ThemeColors } from "@/hooks/use-theme";
import { AIAgentStep, Chapter, Conversation, WritingPreset } from "@/types/api";
import DocumentSelector from "@/components/document-selector";
import ConfirmDialog from "@/components/confirm-dialog";
import ModalSurface from "@/components/modal-surface";
import AnchoredPopover from "@/components/anchored-popover";

interface Message {
  role: 'user' | 'ai';
  content: string;
  isStreaming?: boolean;
  meta?: {
    book_id?: number | null;
    chapter_id?: number | null;
    tool_steps?: ToolStep[];
    copy_text?: string;
    copy_unavailable?: boolean;
    generation_failed?: boolean;
    source_label?: string;
    revision_scope?: string;
  };
}

interface AIChatProps {
  getEditorContent: () => string;
  theme: Theme;
  colors: ThemeColors;
  onToggleRight?: () => void;
  bookId?: number | null;
  chapters?: Chapter[];
  currentChapterId?: number | null;
  hasBackground?: boolean;
}

const CONV_ID_KEY = "ai-conversation-id";

function conversationPreview(conv: Conversation) {
  const last = [...(conv.messages ?? [])].reverse().find(m => m.content?.trim());
  if (!last) return conv.selected_doc_ids?.length ? "已选择参考文档" : "暂无消息";
  const prefix = last.role === "user" ? "我：" : "AI：";
  const content = stripLeakedToolProtocol(last.content).replace(/\s+/g, " ").trim();
  return `${prefix}${content.length > 24 ? content.slice(0, 24) + "…" : content}`;
}

function formatTokenEstimate(value: number) {
  if (value <= 0) return "";
  if (value >= 10000) return `~${(value / 10000).toFixed(1)} 万 tokens`;
  return `~${value} tokens`;
}

function conversationMeta(conv: Conversation) {
  const messageCount = conv.messages?.length ?? 0;
  const docCount = conv.selected_doc_ids?.length ?? 0;
  const date = new Date(conv.update_time);
  const time = Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const parts = [`${messageCount} 条消息`];
  if (docCount > 0) parts.push(`${docCount} 份参考`);
  const tokenText = formatTokenEstimate(conv.token_estimate);
  if (tokenText) parts.push(tokenText);
  if (time) parts.push(time);
  return parts.join(" · ");
}


const AGENT_LABELS: Record<string, string> = {
  layered_context: "自动分层上下文",
  get_current_chapter: "读取当前章节",
  get_nearby_chapters_summary: "读取附近章节摘要",
  get_recent_chapters: "读取最近章节正文",
  search_my_chapters: "检索本书章节",
  search_external_reference: "检索外部资料",
  get_book_structure: "读取书籍结构",
  get_book_outline: "读取全书提纲",
  search_chat_history: "搜索历史对话",
  extract_foreshadowing_candidates: "扫描伏笔候选",
};

const OUTPUT_TAGS_RE = /<\/?NOVELCAT_(?:REPLY|COPY)>/g;

function stripInternalContextMarkers(content: string) {
  return (content || "")
    .replace(/<NOVELCAT_PREVIOUS_COPY>[\s\S]*?<\/NOVELCAT_PREVIOUS_COPY>/gi, "")
    .replace(/<\/?NOVELCAT_PREVIOUS_COPY>/gi, "")
    .replace(/^\s*【(?:此前给出的|本轮)可复制内容】\s*$/gmi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function cleanCopyText(content: string) {
  let text = stripInternalContextMarkers(content);
  const fenced = text.match(/^```(?:text|markdown|md)?\s*\n?([\s\S]*?)\n?```$/i);
  if (fenced) text = fenced[1].trim();
  return text
    .replace(/^(?:#{1,3}\s*)?(?:可复制内容|正文|润色后|改写后)\s*[:：]?\s*\n/i, "")
    .trim();
}

function parseStructuredAiOutput(content: string) {
  const text = stripLeakedToolProtocol(content || "").trim();
  const replyMatch = text.match(/<NOVELCAT_REPLY>\s*([\s\S]*?)\s*<\/NOVELCAT_REPLY>/);
  const copyMatch = text.match(/<NOVELCAT_COPY>\s*([\s\S]*?)\s*<\/NOVELCAT_COPY>/);
  if (!replyMatch || !copyMatch) {
    return { reply: stripInternalContextMarkers(text.replace(OUTPUT_TAGS_RE, "")), copyText: "" };
  }
  return {
    reply: stripInternalContextMarkers(replyMatch[1]),
    copyText: cleanCopyText(copyMatch[1]),
  };
}

function streamingDisplay(content: string) {
  return stripLeakedToolProtocol(content || "")
    .replace(OUTPUT_TAGS_RE, "")
    .trimStart();
}

function messageContentForContext(message: Message) {
  if (message.role !== "ai" || !message.meta?.copy_text?.trim()) return message.content;
  const copyText = message.meta.copy_text.trim();
  if (copyText === message.content.trim()) return message.content;
  return `<NOVELCAT_REPLY>\n${message.content}\n</NOVELCAT_REPLY>\n<NOVELCAT_COPY>\n${copyText}\n</NOVELCAT_COPY>`;
}

async function writeClipboard(content: string) {
  try {
    await navigator.clipboard.writeText(content);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = content;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("copy failed");
  }
}

type AIMessageContentProps = {
  message: Message;
  theme: Theme;
  textClass: string;
  mutedClass: string;
  draftLabel: string;
  onReference: (text: string) => void;
  busy: boolean;
};

type ToolStep = {
  title: string;
  detail?: string;
  status?: "running" | "completed" | "failed";
  elapsed_ms?: number;
  args?: Record<string, string | number | boolean>;
};

function formatElapsed(ms?: number) {
  if (!ms || ms < 0) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function AgentTimeline({
  steps,
  isStreaming,
  mutedClass,
  borderClass,
}: {
  steps: AIAgentStep[];
  isStreaming: boolean;
  mutedClass: string;
  borderClass: string;
}) {
  if (steps.length === 0) {
    if (!isStreaming) return null;
    return (
      <div className={`mb-2 rounded-md border px-2 py-1.5 ${borderClass}`}>
        <span className={`text-[10px] font-medium ${mutedClass}`}>准备中⋯</span>
      </div>
    );
  }

  return (
    <details className={`mb-2 rounded-md border px-2 py-1.5 ${borderClass}`}>
      <summary className={`cursor-pointer select-none text-[10px] font-medium ${mutedClass}`}>
        上下文与生成记录 · {steps.length} 项
      </summary>
      <ul className="mt-1.5 space-y-1.5">
        {steps.map(step => {
          const label = AGENT_LABELS[step.title] || step.title;
          const dot = step.status === "running" ? "●" : step.status === "failed" ? "✕" : "✓";
          const color = step.status === "running"
            ? "text-orange-500"
            : step.status === "failed"
              ? "text-red-500"
              : "text-emerald-500";
          const argsText = step.args
            ? Object.entries(step.args)
                .map(([key, value]) => `${key}=${value}`)
                .join(" ")
            : "";
          return (
            <li key={step.id} className="space-y-0.5">
              <div className="flex items-baseline gap-1.5 text-[10px] leading-4">
                <span className={`shrink-0 ${color}`}>{dot}</span>
                <span className={`font-medium ${color}`}>{label}</span>
                {formatElapsed(step.elapsed_ms) && (
                  <span className={`shrink-0 tabular-nums ${mutedClass}`}>{formatElapsed(step.elapsed_ms)}</span>
                )}
                <span className={`min-w-0 flex-1 truncate ${mutedClass}`}>
                  {step.detail}
                  {argsText ? `（${argsText}）` : ""}
                </span>
              </div>
              {step.content && (
                <p className={`ml-3.5 whitespace-pre-wrap text-[10px] leading-4 ${mutedClass}`}>
                  {step.content.length > 220 ? `${step.content.slice(0, 220)}…` : step.content}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function AgentStepSummary({ steps, mutedClass }: { steps: ToolStep[]; mutedClass: string }) {
  if (!steps || steps.length === 0) return null;
  const statusClass = (status?: string) => {
    if (status === "failed") return "text-red-500";
    if (status === "running") return "text-orange-500";
    return "text-emerald-500";
  };
  return (
    <details className="mb-2 py-1">
      <summary className={`cursor-pointer select-none text-[10px] font-medium ${mutedClass}`}>
        本次参考 · {steps.length} 项
      </summary>
      <ul className="mt-1.5 space-y-1">
        {steps.map((step, index) => (
          <li key={index} className="flex items-start gap-1.5 text-[10px] leading-4">
            <span className={`shrink-0 ${statusClass(step.status)}`}>
              {step.status === "failed" ? "✕" : step.status === "running" ? "●" : "✓"}
            </span>
            <span className={mutedClass}>
              {step.title}
              {step.detail ? `：${step.detail}` : ""}
              {step.elapsed_ms ? ` · ${formatElapsed(step.elapsed_ms)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function AIMessageContent({
  message,
  theme,
  textClass,
  mutedClass,
  draftLabel,
  onReference,
  busy,
}: AIMessageContentProps) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const parsed = message.isStreaming
    ? { reply: streamingDisplay(message.content), copyText: "" }
    : parseStructuredAiOutput(message.content);
  const reply = parsed.reply || (message.meta?.copy_text ? "已生成可复制内容。" : "");
  const copyContent = message.meta?.copy_unavailable
    ? ""
    : cleanCopyText(message.meta?.copy_text || parsed.copyText);

  const copyResult = async () => {
    if (!copyContent) return;
    setCopyError("");
    try {
      await writeClipboard(copyContent);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
      setCopyError("复制失败，请手动选择下方文字");
    }
  };

  if (message.isStreaming && message.content === "") {
    const dotClass = theme === "dark" ? "bg-slate-600" : "bg-slate-300";
    return (
      <div className="flex space-x-1 py-1" role="status" aria-label="AI 正在生成">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className={`h-1.5 w-1.5 animate-pulse rounded-full ${dotClass}`}
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <AgentStepSummary steps={message.meta?.tool_steps ?? []} mutedClass={mutedClass} />
      {reply && <div className={`text-sm leading-7 ${textClass} ${message.isStreaming ? "opacity-80" : ""}`}>
        <p className="whitespace-pre-wrap">
          {reply}
          {message.isStreaming && <span className={`ml-0.5 inline-block h-3.5 w-0.5 animate-caret align-middle ${theme === "dark" ? "bg-slate-400" : "bg-slate-500"}`} />}
        </p>
      </div>}
      {!message.isStreaming && copyContent && (
        <div className={`novelcat-copy-block rounded-lg border px-3.5 py-3 ${theme === "dark" ? "border-slate-700 bg-slate-900/55" : theme === "sepia" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-slate-50/80"}`}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span role="status" className={`text-xs font-medium ${copyError ? "text-red-500" : mutedClass}`}>
              {copyError || `${draftLabel} · ${copyContent.length} 字符`}
            </span>
            <button
              onClick={() => void copyResult()}
              className={`inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold transition-colors ${copied ? "text-emerald-600" : `${mutedClass} hover:bg-slate-500/10`}`}
              type="button"
              aria-label="复制可用内容"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? "已复制" : "复制内容"}
            </button>
          </div>
          <p className={`whitespace-pre-wrap text-sm leading-8 ${textClass}`}>{copyContent}</p>
          <div className={`mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-current/15 pt-3 text-xs ${mutedClass}`}>
            <span>{message.meta?.source_label ? `基于${message.meta.source_label}${message.meta.revision_scope === "opening_two" ? " · 开头两句" : message.meta.revision_scope === "last_paragraph" ? " · 最后一段" : ""}` : "未写入作品"}</span>
            <button type="button" disabled={busy || copyContent.length > 24000}
              onClick={() => onReference(copyContent)}
              className="min-h-8 rounded-md px-2 font-medium hover:bg-slate-500/10 disabled:opacity-40"
              title={copyContent.length > 24000 ? "稿件过长，请复制所需片段到输入框" : "将这份内容固定为下一轮讨论依据"}>
              引用稿件
            </button>
          </div>
        </div>
      )}
      {!message.isStreaming && message.meta?.copy_unavailable && (
        <p role="status" className={`text-xs ${mutedClass}`}>
          本次回答未完整分离正文与说明，已保留原文。请让 AI 重新输出完整正文后再复制。
        </p>
      )}
    </div>
  );
}

export default function AIChat({ getEditorContent, theme: configuredTheme, hasBackground = false, onToggleRight, bookId, chapters = [], currentChapterId = null }: AIChatProps) {
  const theme = hasBackground ? "dark" : configuredTheme;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [draftReference, setDraftReference] = useState<{ label: string; text: string; scope: "whole" | "opening_two" | "last_paragraph" } | null>(null);
  const [detailedAnalysis, setDetailedAnalysis] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const historyButtonRef = useRef<HTMLButtonElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isStreaming, connect, disconnect } = useWebSocket();
  const streamBufferRef = useRef("");
  const streamFrameRef = useRef<number | null>(null);
  const isFirstExchangeRef = useRef(true);
  const isFirstBookEffectRef = useRef(true);
  const [presets, setPresets] = useState<WritingPreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);

  // ── 对话持久化（后端） ────────────────────────────
  const convIdRef = useRef<number | null>(null);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationTitle, setConversationTitle] = useState("新对话");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [showConvDropdown, setShowConvDropdown] = useState(false);
  const [showChatSettings, setShowChatSettings] = useState(false);
  const [cleanupStatus, setCleanupStatus] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [deletingConversation, setDeletingConversation] = useState(false);
  const [convSearch, setConvSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [draftMode, setDraftMode] = useState(false);

  // ── 文档选择 ──────────────────────────────────
  const [showDocSelector, setShowDocSelector] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<number[]>([]);
  const [agentSteps, setAgentSteps] = useState<AIAgentStep[]>([]);
  const agentStepsRef = useRef<AIAgentStep[]>([]);
  const pendingSaveRef = useRef<{ id: number; msgs: Message[] } | null>(null);
  const savingConversationRef = useRef(false);

  const loadConversations = useCallback(async (targetBookId?: number | null, includeArchived = false) => {
    try {
      const list = await api.listConversations(targetBookId, includeArchived);
      setConversations(list);
    } catch {}
  }, []);

  const loadPresets = useCallback(async () => {
    try {
      const data = await api.listWritingPresets();
      setPresets(data.items);
      const enabled = data.items.find(p => p.is_enabled);
      setSelectedPresetId(enabled?.id ?? null);
    } catch {}
  }, []);

  const resetDraftConversation = useCallback(() => {
    setDraftReference(null);
    setShowChatSettings(false);
    setIsEditingTitle(false);
    disconnect();
    setDraftMode(false);
    setMessages([]);
    convIdRef.current = null;
    setCurrentConversationId(null);
    setConversationTitle("新对话");
    setSelectedDocIds([]);
    isFirstExchangeRef.current = true;
    localStorage.removeItem(CONV_ID_KEY);
    localStorage.removeItem("ai-chat-messages:v1");
  }, [disconnect]);

  const ensureConversation = useCallback(async () => {
    if (convIdRef.current) return convIdRef.current;
    const conv = await api.createConversation({ title: "新对话", book_id: bookId ?? undefined });
    convIdRef.current = conv.id;
    setCurrentConversationId(conv.id);
    setDraftMode(false);
    setConversationTitle(conv.title || "新对话");
    localStorage.setItem(CONV_ID_KEY, String(conv.id));
    setConversations(prev => [conv, ...prev.filter(item => item.id !== conv.id)]);
    return conv.id;
  }, [bookId]);

  // 启动时：从后端恢复对话
  useEffect(() => {
    async function initConversation() {
      await loadConversations(bookId);

      // 尝试读取上次的对话 ID
      const storedId = localStorage.getItem(CONV_ID_KEY);
      if (storedId) {
        try {
          const conv = await api.getConversation(parseInt(storedId, 10));
          if (bookId && !conv.book_id) {
            await api.updateConversation(conv.id, { book_id: bookId });
            conv.book_id = bookId;
          }
          if (bookId && conv.book_id && conv.book_id !== bookId) {
            resetDraftConversation();
            return;
          }
          if (conv && (conv.messages?.length > 0 || conv.selected_doc_ids?.length > 0 || conv.title !== "新对话")) {
            setMessages((conv.messages as Message[]).map(message => ({
              ...message,
              content: stripLeakedToolProtocol(message.content),
            })).filter(message => message.role === "user" || message.content));
            convIdRef.current = conv.id;
            setCurrentConversationId(conv.id);
            setConversationTitle(conv.title || "新对话");
            setSelectedDocIds(conv.selected_doc_ids ?? []);
            isFirstExchangeRef.current = (conv.messages?.length ?? 0) === 0;
            return;
          }
        } catch {
          // 对话不存在，降级为草稿
        }
      }

      const saved = localStorage.getItem("ai-chat-messages:v1");
      resetDraftConversation();
      if (saved) {
        try {
          const draft = JSON.parse(saved) as Message[];
          setMessages(draft.map(message => ({
            ...message,
            content: stripLeakedToolProtocol(message.content),
          })).filter(message => message.role === "user" || message.content));
        } catch {}
      }
    }
    void initConversation();
  }, [bookId, loadConversations, resetDraftConversation]);

  // 切换书籍时切到该书的对话列表，并清掉旧书的草稿
  useEffect(() => {
    if (isFirstBookEffectRef.current) {
      isFirstBookEffectRef.current = false;
      return;
    }
    resetDraftConversation();
    void loadConversations(bookId);
  }, [bookId, loadConversations, resetDraftConversation]);

  const switchConversation = async (conv: Conversation) => {
    setDraftReference(null);
    followLatestRef.current = true;
    setShowLatestButton(false);
    setShowConvDropdown(false);
    try {
      const full = await api.getConversation(conv.id);
      if (bookId && !full.book_id) {
        await api.updateConversation(full.id, { book_id: bookId });
        full.book_id = bookId;
      }
      if (full.archived) {
        await api.updateConversation(full.id, { archived: false });
        full.archived = false;
      }
      const msgs = ((full.messages ?? []) as Message[]).map(message => ({
        ...message,
        content: stripLeakedToolProtocol(message.content),
      })).filter(message => message.role === "user" || message.content);
      setMessages(msgs);
      convIdRef.current = full.id;
      setCurrentConversationId(full.id);
      setConversationTitle(full.title || "新对话");
      setSelectedDocIds(full.selected_doc_ids ?? []);
      localStorage.setItem(CONV_ID_KEY, String(full.id));
      setConversations(prev => prev.map(c => c.id === full.id ? { ...c, archived: false } : c));
      // 已有消息则不再自动生成标题
      isFirstExchangeRef.current = msgs.length === 0;
    } catch {}
  };

  const renameCurrentConversation = async (newTitle: string) => {
    setIsEditingTitle(false);
    const title = newTitle.trim();
    if (!title) return;
    setConversationTitle(title);
    try {
      const id = await ensureConversation();
      await api.updateConversation(id, { title });
      setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c));
    } catch {}
  };

  // 保存对话到后端：串行队列，始终保存最新快照，避免并发请求乱序覆盖
  const persistMessages = (msgs: Message[]) => {
    const id = convIdRef.current;
    if (!id) {
      localStorage.setItem("ai-chat-messages:v1", JSON.stringify(msgs));
      return;
    }
    pendingSaveRef.current = { id, msgs };
    if (savingConversationRef.current) return;
    savingConversationRef.current = true;

    const run = async () => {
      while (true) {
        const pending = pendingSaveRef.current;
        if (!pending) {
          savingConversationRef.current = false;
          return;
        }
        try {
          const updated = await api.updateConversation(pending.id, {
            messages: pending.msgs.map(m => ({
              role: m.role,
              content: m.content,
              ...(m.meta ? { meta: m.meta } : {}),
            })),
          });
          setConversations(prev => [updated, ...prev.filter(conv => conv.id !== updated.id)]);
          if (pendingSaveRef.current === pending) {
            pendingSaveRef.current = null;
            savingConversationRef.current = false;
            return;
          }
        } catch {
          // 降级到 localStorage
          if (pendingSaveRef.current === pending) {
            localStorage.setItem("ai-chat-messages:v1", JSON.stringify(pending.msgs));
          }
          pendingSaveRef.current = null;
          savingConversationRef.current = false;
          return;
        }
      }
    };
    void run();
  };

  useEffect(() => {
    void Promise.resolve().then(loadPresets);
  }, [loadPresets]);

  const followLatestRef = useRef(true);
  const [showLatestButton, setShowLatestButton] = useState(false);
  const scrollToBottom = () => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    followLatestRef.current = true;
    setShowLatestButton(false);
  };
  useEffect(() => {
    if (followLatestRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // 自动调整 textarea 高度
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }, [input]);

  const addAiMessage = (content: string, isStreaming = false) => {
    setMessages(prev => [...prev, { role: "ai", content, isStreaming }]);
  };

  const updateLastAiMessage = (content: string, isStreaming = true, meta?: Message["meta"]) => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last?.role === "ai") {
        const next = [...prev.slice(0, -1), {
          role: "ai" as const,
          content,
          isStreaming,
          meta: meta ?? last.meta,
        }];
        return next;
      }
      return prev;
    });
  };

  const finalizeAiMessage = (content: string, meta?: Message["meta"]) => {
    let next: Message[] | null = null;
    flushSync(() => {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.role !== "ai") return prev;
        next = [...prev.slice(0, -1), {
          role: "ai" as const,
          content,
          isStreaming: false,
          meta: meta ?? last.meta,
        }];
        return next;
      });
    });
    if (next) persistMessages(next);
  };

  useEffect(() => {
    return () => {
      if (streamFrameRef.current !== null) cancelAnimationFrame(streamFrameRef.current);
    };
  }, []);

  const getAiUnavailableMessage = async () => {
    try {
      const health = await api.getAiHealth();
      if (health.configured) return null;
      const providerName = (health.provider || "AI").toUpperCase();
      return `还没有配置 ${providerName} API Key。请先进入设置页填写 API Key，然后再使用 AI 聊天。`;
    } catch {
      return "后端服务暂时不可用。请确认 start-web.cmd 已正常启动，或查看 .run/logs 日志。";
    }
  };


  const startStream = (request: Parameters<typeof connect>[0]) => {
    streamBufferRef.current = "";
    setAgentSteps([]);
    agentStepsRef.current = [];
    addAiMessage("", true);
    const currentEditorContent = getEditorContent();
    const withExtras = {
      ...request,
      ...(selectedPresetId ? { preset_id: selectedPresetId } : {}),
      ...(bookId ? { book_id: bookId } : {}),
      ...(convIdRef.current ? { conversation_id: convIdRef.current } : {}),
      project_id: bookId ? String(bookId) : "default_project",
      ...(currentChapterId ? { current_chapter_id: currentChapterId } : {}),
      ...(selectedDocIds.length > 0 ? { selected_doc_ids: selectedDocIds } : {}),
      detailed_analysis: detailedAnalysis,
      ...(currentEditorContent && !request.content ? { content: currentEditorContent } : {}),
    };

    connect(withExtras, {
      onToken: (token) => {
        streamBufferRef.current += token;
        flushSync(() => {
          updateLastAiMessage(streamingDisplay(streamBufferRef.current), true);
        });
      },
      onAgentStep: (step) => {
        const current = agentStepsRef.current;
        const index = current.findIndex((item) => item.id === step.id);
        const next = index < 0
          ? [...current, step]
          : current.map((item, i) => i === index ? { ...item, ...step } : item);
        agentStepsRef.current = next;
        setAgentSteps(next);
      },
      onDone: () => {
        const parsedOutput = parseStructuredAiOutput(streamBufferRef.current);
        const finalContent = parsedOutput.reply
          || (parsedOutput.copyText ? "已生成可复制内容。" : "AI 没有完成这次内容读取，请重新生成一次。");
        const finishedSteps = agentStepsRef.current.map(step =>
          step.status === "running" ? { ...step, status: "completed" as const } : step
        );
        agentStepsRef.current = finishedSteps;
        if (streamFrameRef.current !== null) {
          cancelAnimationFrame(streamFrameRef.current);
          streamFrameRef.current = null;
        }
        finalizeAiMessage(finalContent, {
          source_label: request.draft_reference?.label,
          revision_scope: request.draft_reference?.scope,
          book_id: bookId ?? null,
          chapter_id: currentChapterId ?? null,
          copy_text: parsedOutput.copyText,
          copy_unavailable: !parsedOutput.copyText,
          tool_steps: finishedSteps
            .filter(step => step.phase === "tool" || step.phase === "context")
            .slice(-12)
            .map(step => ({
              title: step.title,
              detail: step.detail || step.query || "",
              status: step.status,
              elapsed_ms: step.elapsed_ms,
              args: step.args,
            })),
        });
        setAgentSteps([]);

        // 首次对话自动生成标题
        if (isFirstExchangeRef.current) {
          isFirstExchangeRef.current = false;
          setMessages(prev => {
            const firstUser = prev.find(m => m.role === "user");
            if (firstUser) generateAutoTitle(firstUser.content);
            return prev;
          });
        }
      },
      onError: (message) => {
        const failedSteps = agentStepsRef.current.map(step =>
          step.status === "running" ? { ...step, status: "failed" as const, detail: message } : step
        );
        agentStepsRef.current = failedSteps;
        if (streamFrameRef.current !== null) {
          cancelAnimationFrame(streamFrameRef.current);
          streamFrameRef.current = null;
        }
        const partialOutput = parseStructuredAiOutput(streamBufferRef.current);
        const partialText = [partialOutput.reply, partialOutput.copyText].filter(Boolean).join("\n\n");
        finalizeAiMessage(`${partialText ? `${partialText}\n\n` : ""}生成未完成：${message}`, {
          generation_failed: true,
          copy_unavailable: true,
          book_id: bookId ?? null,
          chapter_id: currentChapterId ?? null,
          tool_steps: failedSteps
            .filter(step => step.phase === "tool" || step.phase === "context")
            .slice(-12)
            .map(step => ({
              title: step.title,
              detail: step.detail || step.query || "",
              status: step.status,
              elapsed_ms: step.elapsed_ms,
              args: step.args,
            })),
        });
        setAgentSteps(failedSteps);
      },
    });
  };

  const handleStop = () => {
    if (!isStreaming) return;
    disconnect();
    const stoppedSteps = agentStepsRef.current.map(step => (
      step.status === "running"
        ? { ...step, status: "failed" as const, detail: step.detail ? `${step.detail}（已停止）` : "已手动停止" }
        : step
    ));
    agentStepsRef.current = stoppedSteps;
    const partial = parseStructuredAiOutput(streamBufferRef.current);
    const partialReply = partial.reply || (partial.copyText ? "已保留停止前生成的内容。" : "已停止生成。");
    finalizeAiMessage(partialReply, {
      book_id: bookId ?? null,
      chapter_id: currentChapterId ?? null,
      copy_text: partial.copyText,
      copy_unavailable: !partial.copyText,
      tool_steps: stoppedSteps
        .filter(step => step.phase === "tool" || step.phase === "context")
        .slice(-12)
        .map(step => ({
          title: step.title,
          detail: step.detail || step.query || "",
          status: step.status,
          elapsed_ms: step.elapsed_ms,
          args: step.args,
        })),
    });
    setAgentSteps(stoppedSteps);
  };

  const handleSend = async (text: string = input) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    followLatestRef.current = true;
    setShowLatestButton(false);

    try { await ensureConversation(); } catch {}
    setDraftMode(false);

    const userMsg: Message = { role: "user", content: trimmed, meta: {
      source_label: draftReference?.label, revision_scope: draftReference?.scope,
    } };
    const pendingMessages: Message[] = [...messages, userMsg];
    setMessages(pendingMessages);
    persistMessages(pendingMessages);
    setInput("");

    const unavailableMessage = await getAiUnavailableMessage();
    if (unavailableMessage) {
      const finalMessages: Message[] = [...pendingMessages, { role: "ai", content: unavailableMessage }];
      setMessages(finalMessages);
      persistMessages(finalMessages);
      return;
    }

    const historyMessages = messages.filter(m => !m.meta?.generation_failed).map(m => ({
      role: m.role === "ai" ? "assistant" : m.role,
      content: messageContentForContext(m),
    }));
    historyMessages.push({ role: "user", content: trimmed });

    startStream({
      type: "chat",
      ...(draftReference ? { draft_reference: draftReference } : {}),
      messages: historyMessages,
      use_memory: false,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const openDocSelector = async () => {
    try {
      setShowConvDropdown(false);
      await ensureConversation();
      setShowDocSelector(true);
    } catch {}
  };

  const handleDocumentSelectionSave = (ids: number[]) => {
    setSelectedDocIds(ids);
    if (!convIdRef.current) return;
    setConversations(prev =>
      prev.map(conv =>
        conv.id === convIdRef.current ? { ...conv, selected_doc_ids: ids } : conv
      )
    );
  };

  const handleUseDefaultPreset = async () => {
    const activeId = selectedPresetId;
    setSelectedPresetId(null);
    if (!activeId) return;
    try {
      await api.toggleWritingPreset(activeId);
      await loadPresets();
    } catch {
      await loadPresets();
    }
  };

  const activatePreset = async (presetId: number) => {
    setSelectedPresetId(presetId);
    if (selectedPresetId === presetId) return;
    try {
      await api.toggleWritingPreset(presetId);
      await loadPresets();
    } catch {
      await loadPresets();
    }
  };

  const startNewConversation = () => {
    resetDraftConversation();
    setDraftMode(true);
    setShowConvDropdown(false);
  };

  const generateAutoTitle = async (firstUserMsg: string) => {
    if (!convIdRef.current) return;
    let title = firstUserMsg.trim();
    // 截取前 15 字
    if (title.length > 15) title = title.slice(0, 15) + "…";
    if (!title) return;
    setConversationTitle(title);
    try {
      await api.updateConversation(convIdRef.current, { title });
      setConversations(prev => prev.map(c => c.id === convIdRef.current ? { ...c, title } : c));
    } catch {}
  };


  const deleteConversation = async (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteTarget(conv);
  };

  const archiveConversation = async (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.updateConversation(conv.id, { archived: true });
      setConversations(prev => prev.filter(c => c.id !== conv.id));
      if (conv.id === convIdRef.current) resetDraftConversation();
    } catch {}
  };

  const restoreConversation = async (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.updateConversation(conv.id, { archived: false });
      setConversations(prev => prev.filter(c => c.id !== conv.id));
    } catch {}
  };

  const confirmDeleteConversation = async () => {
    if (!deleteTarget) return;
    setDeletingConversation(true);
    try {
      await api.deleteConversation(deleteTarget.id);
      setConversations(prev => prev.filter(c => c.id !== deleteTarget.id));
      if (deleteTarget.id === convIdRef.current) {
        resetDraftConversation();
      }
      setDeleteTarget(null);
    } catch {
    } finally {
      setDeletingConversation(false);
    }
  };

  const cleanupEmptyConversations = async () => {
    setCleanupStatus("清理中...");
    try {
      const result = await api.cleanupEmptyConversations();
      if (currentConversationId && result.deleted_ids.includes(currentConversationId)) {
        resetDraftConversation();
      }
      await loadConversations(bookId, showArchived);
      setCleanupStatus(result.deleted_count > 0 ? `已清理 ${result.deleted_count} 个空对话` : "没有空对话");
    } catch {
      setCleanupStatus("清理失败");
    }
  };

  const busy = isStreaming;

  // ── 主题相关样式 ──────────────────────────────────────────────────────────────
  const borderClass = theme === 'dark' ? 'border-slate-700/60' : theme === 'sepia' ? 'border-amber-200' : 'border-slate-100';
  const bgClass = theme === 'dark' ? 'bg-slate-900' : theme === 'sepia' ? 'bg-amber-50' : 'bg-white';
  const mutedClass = theme === 'dark' ? 'text-slate-400' : theme === 'sepia' ? 'text-amber-800' : 'text-slate-600';
  const textClass = theme === 'dark' ? 'text-slate-300' : theme === 'sepia' ? 'text-amber-700' : 'text-slate-700';
  const headingClass = theme === 'dark' ? 'text-slate-100' : theme === 'sepia' ? 'text-amber-900' : 'text-slate-800';
  const hoverBgClass = theme === 'dark' ? 'hover:bg-slate-800' : theme === 'sepia' ? 'hover:bg-amber-100' : 'hover:bg-slate-50';
  const inputBgClass = theme === 'dark' ? 'bg-slate-800 border-slate-700 text-slate-200 placeholder:text-slate-400 focus:border-slate-500' : theme === 'sepia' ? 'bg-amber-50 border-amber-200 text-amber-900 placeholder:text-amber-800 focus:border-amber-600' : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-slate-500 focus:bg-white';
  const sendBtnClass = theme === 'dark' ? 'bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600' : theme === 'sepia' ? 'bg-amber-800 hover:bg-amber-700 disabled:bg-amber-200 disabled:text-amber-400' : 'bg-slate-900 hover:bg-slate-700 disabled:bg-slate-100 disabled:text-slate-300';
  const dropdownItemHover = theme === 'dark' ? 'hover:bg-slate-700' : theme === 'sepia' ? 'hover:bg-amber-100' : 'hover:bg-slate-50';
  const userMsgBg = theme === 'dark' ? 'bg-slate-700 text-slate-100' : theme === 'sepia' ? 'bg-amber-800 text-white' : 'bg-slate-900 text-white';
  const inputAreaBg = theme === 'dark' ? 'bg-slate-900 border-slate-700/60' : theme === 'sepia' ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-100';
  const selectedDropdownBg = theme === 'dark' ? 'bg-slate-700/70' : theme === 'sepia' ? 'bg-amber-100/80' : 'bg-slate-100';
  const currentChapter = currentChapterId ? chapters.find(chapter => chapter.id === currentChapterId) ?? null : null;
  const quickPrompts = currentChapter
    ? ["润色本章最后一段，保留情节和原有语气", "讨论接下来的走向，给我三个不同建议", "检查本章与已有设定是否矛盾"]
    : ["帮我梳理故事主线", "设计一个有冲突感的开场", "整理主要人物关系"];
  const convQuery = convSearch.trim().toLowerCase();
  const visibleConversations = conversations.filter(conv => {
    if (!convQuery) return true;
    const haystack = `${conv.title || "新对话"} ${conversationPreview(conv)}`.toLowerCase();
    return haystack.includes(convQuery);
  });

  return (
    <div ref={panelRef} data-theme={theme} onKeyDown={e => {
      if (e.key === "Escape" && !showDocSelector && !deleteTarget) {
        setShowConvDropdown(false); setShowChatSettings(false);
      }
    }} className={`novelcat-ai-panel flex flex-col h-full min-h-0 ${bgClass} border-l ${borderClass}`}>

      <header className="novelcat-chat-header shrink-0 px-4 pt-4 pb-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className={`text-base font-semibold ${headingClass}`}>写作对话</h2>
          <div className="flex items-center gap-1">
            <button type="button" onClick={startNewConversation} disabled={busy} className="novelcat-chat-action"
              title="新对话只依据作品，不继承其他聊天"><Plus size={16} />新对话</button>
            {onToggleRight && <button type="button" onClick={onToggleRight} className="novelcat-chat-action"
              aria-label="收起 AI 面板" title="收起 AI 面板"><PanelRightClose size={17} /></button>}
          </div>
        </div>
        <p className={`mt-1 truncate text-xs ${mutedClass}`} title={currentChapter?.title}>
          {currentChapter ? `正在参考 · ${currentChapter.title}` : "依据作品和当前对话，不自动修改原稿"}
        </p>
        <nav aria-label="对话导航" className="mt-3 flex gap-2">
          <button ref={historyButtonRef} type="button" className="novelcat-chat-action" aria-expanded={showConvDropdown} aria-haspopup="dialog"
            aria-controls="chat-history-panel" disabled={busy}
            onClick={() => { setShowConvDropdown(v => !v); setShowChatSettings(false); }}><History size={15} />历史对话</button>
          <button type="button" className="novelcat-chat-action" aria-expanded={showChatSettings} aria-haspopup="dialog"
            aria-controls="chat-settings-panel" disabled={busy}
            onClick={() => { setShowChatSettings(v => !v); setShowConvDropdown(false); }}><SlidersHorizontal size={15} />对话设置</button>
        </nav>
      </header>
      <AnchoredPopover open={showConvDropdown} onClose={() => setShowConvDropdown(false)} anchorRef={historyButtonRef}
        boundaryRef={panelRef} id="chat-history-panel" label="历史对话" theme={theme}>
        <div className="shrink-0 px-4 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className={`text-sm font-semibold ${headingClass}`}>历史对话</h3>
          <button type="button" className="novelcat-chat-action" aria-label="关闭历史对话" onClick={() => { historyButtonRef.current?.focus({ preventScroll: true }); setShowConvDropdown(false); }}><X size={16} /></button>
        </div>
        <div className="relative">
        <Search size={15} aria-hidden="true" className="absolute left-3 top-3 text-[var(--chat-muted)] pointer-events-none" />
        <input aria-label="搜索对话" value={convSearch} onChange={e => setConvSearch(e.target.value)} placeholder="搜索标题或最近消息"
          className={`w-full rounded-md border pl-9 pr-3 py-2 text-sm ${inputBgClass}`} />
        </div>
        <div className="my-1 flex items-center justify-between">
          <span className={`text-xs ${mutedClass}`}>{showArchived ? "已归档" : "最近对话"}</span>
          <button type="button" className="novelcat-chat-action" onClick={() => {
            const next = !showArchived; setShowArchived(next); void loadConversations(bookId, next);
          }}>{showArchived ? "查看最近" : "查看归档"}</button>
        </div>
        </div>
        <div className="novelcat-history-list min-h-0 overflow-y-auto overscroll-contain px-2">
        {visibleConversations.length === 0 && <p className={`py-8 text-center text-sm ${mutedClass}`}>没有找到对话</p>}
        {visibleConversations.map(conv => <div key={conv.id} className="novelcat-history-row">
          <button type="button" onClick={() => switchConversation(conv)} aria-current={conv.id === currentConversationId ? "true" : undefined}
            className={`w-full rounded-lg px-2 py-3 text-left ${dropdownItemHover} ${conv.id === currentConversationId ? selectedDropdownBg : ""}`}>
            <div className={`flex items-start gap-2 text-sm font-medium ${headingClass}`}><span className="min-w-0 flex-1 break-words line-clamp-2" title={conv.title || "新对话"}>{conv.title || "新对话"}</span>{conv.id === currentConversationId && <Check size={15} className="mt-0.5 shrink-0 text-[var(--chat-accent)]" />}</div>
            <div className={`mt-1 truncate text-xs ${mutedClass}`}>{conversationPreview(conv)}</div>
            <div className={`mt-2 break-words text-xs ${mutedClass}`}>{conversationMeta(conv)}</div>
          </button>
          <div className="flex justify-end gap-2 pb-2">
            <button type="button" className="novelcat-chat-action" aria-label={`${showArchived ? "恢复" : "归档"}对话 ${conv.title || "新对话"}`}
              onClick={e => showArchived ? restoreConversation(conv, e) : archiveConversation(conv, e)}>{showArchived ? "恢复" : "归档"}</button>
            <button type="button" className="novelcat-chat-action" aria-label={`删除对话 ${conv.title || "新对话"}`}
              onClick={e => deleteConversation(conv, e)}><Trash2 size={14} />删除</button>
          </div>
        </div>)}
        </div>
        <div className="shrink-0 border-t border-[var(--chat-line)] px-3 py-2"><button type="button" onClick={cleanupEmptyConversations} className="novelcat-chat-action">清理空对话</button>
          {cleanupStatus && <p role="status" className={`mt-2 text-xs ${mutedClass}`}>{cleanupStatus}</p>}
        </div>
      </AnchoredPopover>
      <ModalSurface open={showChatSettings} onClose={() => setShowChatSettings(false)} label="对话设置" wide>
      <section id="chat-settings-panel" data-theme={theme} className="novelcat-ai-panel novelcat-settings-dialog novelcat-chat-secondary">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--chat-line)] px-6 py-5">
          <div><h3 className={`text-lg font-semibold ${headingClass}`}>对话设置</h3><p className={`mt-1 text-xs leading-5 ${mutedClass}`}>调整当前对话的回答方式和参考资料</p></div>
          <button type="button" className="novelcat-chat-action" aria-label="关闭对话设置" onClick={() => setShowChatSettings(false)}><X size={18} /></button>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain space-y-6 px-6 py-5">
          {currentConversationId && <div>
            <label htmlFor="chat-conversation-name" className={`mb-2 block text-sm font-medium ${textClass}`}>对话名称</label>
            <div className="flex gap-2">
              <input id="chat-conversation-name" value={conversationTitle} onChange={e => { setConversationTitle(e.target.value); setIsEditingTitle(true); }}
                onKeyDown={e => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); void renameCurrentConversation(conversationTitle); } }}
                className={`min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm ${inputBgClass}`} />
              <button type="button" disabled={!isEditingTitle || !conversationTitle.trim()} className="novelcat-chat-action"
                onClick={() => void renameCurrentConversation(conversationTitle)}>保存</button>
            </div>
            <button type="button" className="novelcat-chat-action mt-2" disabled={!messages.some(m => m.role === "user")}
              onClick={() => { const first = messages.find(m => m.role === "user"); if (first) void generateAutoTitle(first.content); }}>根据内容生成名称</button>
          </div>}
          <div>
            <label htmlFor="chat-persona" className={`mb-2 block text-sm font-medium ${textClass}`}>写作人格</label>
            <select id="chat-persona" value={selectedPresetId ?? ""} className={`w-full rounded-lg border px-3 py-2.5 text-sm ${inputBgClass}`}
              onChange={e => { if (e.target.value) void activatePreset(Number(e.target.value)); else void handleUseDefaultPreset(); }}>
              <option value="">默认写作助手</option>{presets.map(preset => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
            </select>
            <p className={`mt-2 text-xs leading-5 ${mutedClass}`}>影响回答风格，不改变作品设定。</p>
          </div>
          <div>
            <p className={`text-sm font-medium ${textClass}`}>外部参考资料</p>
            <p className={`my-2 text-xs leading-5 ${mutedClass}`}>作品内容会自动参考；这里选择额外语料。</p>
            <button type="button" onClick={openDocSelector} className="novelcat-chat-action"><Library size={15} />{selectedDocIds.length ? `已选 ${selectedDocIds.length} 份 · 管理资料` : "选择参考资料"}</button>
          </div>
          <label className={`flex cursor-pointer items-start gap-3 text-sm ${textClass}`}>
            <input type="checkbox" className="mt-1 size-4 accent-orange-700" checked={detailedAnalysis} onChange={e => setDetailedAnalysis(e.target.checked)} />
            <span className="flex-1"><span className="font-medium">详细分析</span><span className={`mt-1 block text-xs leading-5 ${mutedClass}`}>展开说明写作思路和修改理由，回复会更长。</span></span>
          </label>
          <p className={`border-t pt-4 text-xs leading-6 ${borderClass} ${mutedClass}`}>只参考作品与当前聊天。新对话不会继承其他聊天里的讨论，所有稿件由你复制采用。</p>
        </div>
        <div className="flex shrink-0 justify-end border-t border-[var(--chat-line)] px-6 py-3">
          <button type="button" className="novelcat-chat-action novelcat-settings-done" onClick={() => setShowChatSettings(false)}>返回对话</button>
        </div>
      </section>
      </ModalSurface>

      <DocumentSelector
        conversationId={currentConversationId}
        isOpen={showDocSelector}
        onClose={() => setShowDocSelector(false)}
        initialSelectedIds={selectedDocIds}
        onSave={handleDocumentSelectionSave}
        theme={theme}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除对话"
        description={`确定要删除“${deleteTarget?.title || "新对话"}”吗？这个操作不可撤销。`}
        confirmLabel="删除"
        tone="danger"
        theme={theme}
        busy={deletingConversation}
        onConfirm={confirmDeleteConversation}
        onCancel={() => setDeleteTarget(null)}
      />
      {/* 消息区 */}
      <div ref={scrollRef} aria-label="对话消息" onScroll={() => {
        const el = scrollRef.current;
        if (!el) return;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 72;
        followLatestRef.current = nearBottom;
        setShowLatestButton(!nearBottom);
      }} className="flex-1 min-h-0 overflow-y-auto px-4 py-5 space-y-7 custom-scrollbar">
        {messages.length === 0 && !isStreaming && (
          !currentConversationId && !draftMode ? (
            <div className="h-full flex flex-col items-center justify-center space-y-4 py-8">
              <div className={`w-9 h-9 rounded-2xl ${theme === 'dark' ? 'bg-slate-800' : theme === 'sepia' ? 'bg-amber-100' : 'bg-slate-50'} flex items-center justify-center`}>
                <Sparkles size={16} className={mutedClass} />
              </div>
              <div className="text-center space-y-1">
                <p className={`text-xs font-semibold ${textClass}`}>还没有选择对话</p>
                <p className={`text-[10px] ${mutedClass}`}>选择历史对话，或开始一个新对话</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={startNewConversation}
                  className={`inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-[10px] font-semibold ${textClass} ${borderClass} ${hoverBgClass} transition-colors`}
                  type="button"
                >
                  <Plus size={11} />
                  新建对话
                </button>
                <button
                  onClick={() => setShowConvDropdown(true)}
                  className={`inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-[10px] font-semibold ${textClass} ${borderClass} ${hoverBgClass} transition-colors`}
                  type="button"
                >
                  <ChevronDown size={11} />
                  选择历史对话
                </button>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center space-y-4 py-8">
              <div className={`w-9 h-9 rounded-2xl ${theme === 'dark' ? 'bg-slate-800' : theme === 'sepia' ? 'bg-amber-100' : 'bg-slate-50'} flex items-center justify-center`}>
                <Sparkles size={16} className={mutedClass} />
              </div>
              <div className="text-center space-y-1">
                <p className={`text-base font-semibold ${textClass}`}>一起打磨这一段</p>
                <p className={`text-xs leading-6 ${mutedClass}`}>贴一段正文，或说说你卡在哪里。<br />依据作品和当前对话讨论，由你决定采用。</p>
              </div>
              <div className="flex max-w-[18rem] flex-wrap justify-center gap-1.5">
                {quickPrompts.map(prompt => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => { setInput(prompt); textareaRef.current?.focus(); }}
                    className={`w-full rounded-md border px-3 py-2.5 text-left text-xs leading-5 ${borderClass} ${textClass} ${hoverBgClass}`}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )
        )}

        {messages.map((msg, i) => {
          return (
          <div key={i} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
            {msg.role === 'ai' && i === messages.length - 1 && (agentSteps.length > 0 || msg.isStreaming) && (
              <AgentTimeline
                steps={agentSteps}
                isStreaming={msg.isStreaming || false}
                mutedClass={mutedClass}
                borderClass={borderClass}
              />
            )}
            {msg.role === "user" ? (
              <div className={`max-w-[94%] ${userMsgBg} text-sm px-3.5 py-3 rounded-xl rounded-tr-sm leading-7`}>
                {msg.meta?.source_label && <p className="mb-1 text-xs opacity-80">引用 {msg.meta.source_label} · {msg.meta.revision_scope === "opening_two" ? "只改开头两句" : msg.meta.revision_scope === "last_paragraph" ? "只改最后一段" : "整稿讨论"}</p>}
                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{msg.content}</p>
              </div>
            ) : (
              <div className="group w-full min-w-0 space-y-2 [overflow-wrap:anywhere]">
                <AIMessageContent
                  message={msg}
                  theme={theme}
                  textClass={textClass}
                  mutedClass={mutedClass}
                  draftLabel={`回复稿 ${messages.slice(0, i + 1).filter(item => item.role === "ai").length}`}
                  busy={busy}
                  onReference={(text) => {
                    setDraftReference({ label: `回复稿 ${messages.slice(0, i + 1).filter(item => item.role === "ai").length}`, text, scope: "whole" });
                    textareaRef.current?.focus();
                  }}
                />
                {i === messages.length - 1 && !busy && (msg.meta?.copy_unavailable || msg.meta?.generation_failed) && (
                  <button type="button"
                    onClick={() => { setInput("请重新完成上一条请求，保留原有要求；完整分离说明与可复制内容，不输出内部标记。"); textareaRef.current?.focus(); }}
                    className={`min-h-8 rounded-md border px-3 py-1.5 text-xs ${borderClass} ${textClass} ${hoverBgClass}`}>
                    准备重试
                  </button>
                )}
              </div>
            )}
          </div>
        );
        })}
      </div>

      {/* 输入区 */}
      {showLatestButton && !showConvDropdown && !showChatSettings && <button type="button" onClick={scrollToBottom}
        className={`self-center my-2 rounded-md border px-3 py-1.5 text-xs ${borderClass} ${textClass} ${hoverBgClass}`}>回到最新回复 ↓</button>}
      <div className={`novelcat-chat-composer p-4 border-t ${inputAreaBg} relative shrink-0`}>
        {draftReference && <div className={`novelcat-draft-reference mb-3 border-b ${borderClass} pb-3 ${textClass}`}>
          <div className="flex items-center justify-between gap-2 text-xs font-medium">
            <span>正在引用 · {draftReference.label}</span>
            <button type="button" disabled={busy} onClick={() => setDraftReference(null)} className="min-h-9 rounded px-2 hover:bg-slate-500/10 disabled:opacity-40">取消引用</button>
          </div>
          <p className={`my-2 truncate text-xs ${mutedClass}`}>{draftReference.text}</p>
          <label className="flex flex-wrap items-center gap-2 text-xs">
            修改范围
            <select aria-label="修改范围" disabled={busy} value={draftReference.scope}
              onChange={e => setDraftReference({ ...draftReference, scope: e.target.value as typeof draftReference.scope })}
              className={`min-h-8 flex-1 rounded-md border px-2 ${inputBgClass}`}>
              <option value="whole">整稿讨论</option>
              <option value="opening_two">只改开头两句</option>
              <option value="last_paragraph">只改最后一段</option>
            </select>
          </label>
          {draftReference.scope !== "whole" && <p className={`mt-2 text-xs leading-5 ${mutedClass}`}>范围外原文不动。以此处范围为准；句末标点划句，空行分段。</p>}
        </div>}
        <div className="novelcat-compose-box">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            aria-label="写作需求"
            placeholder={busy ? "正在生成，可随时停止" : "贴一段文字，或聊聊你的想法…"}
            disabled={busy}
            rows={2}
            className={`w-full border-0 bg-transparent px-3 py-3 text-sm focus:outline-none resize-none leading-6 disabled:opacity-50 ${textClass}`}
            style={{ minHeight: "76px", maxHeight: "120px" }}
          />
          <button
            onClick={() => busy ? handleStop() : void handleSend()}
            disabled={!busy && !input.trim()}
            data-busy={busy}
            className={`novelcat-ai-send ml-auto mr-2 mb-2 min-h-9 px-3 flex items-center justify-center gap-2 rounded-lg text-white transition-colors ${busy ? "bg-red-500 hover:bg-red-600" : sendBtnClass}`}
            type="button"
            title={busy ? "停止生成" : "发送"}
            aria-label={busy ? "停止生成" : "发送"}
          >
            {busy ? <Square size={12} fill="currentColor" /> : <Send size={14} />}<span className="text-xs font-medium">{busy ? "停止" : "发送"}</span>
          </button>
        </div>
        <div className={`mt-2 flex flex-wrap justify-between gap-1 text-xs ${mutedClass}`}>
          <span>Enter 发送 · Shift + Enter 换行</span>
          <span>不会修改作品</span>
        </div>
      </div>
    </div>
  );
}
