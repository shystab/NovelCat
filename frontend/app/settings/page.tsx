"use client";

import React, { useState, useEffect } from "react";
import { Settings, SettingsUpdate, KnowledgeBase, AuthUser, InviteCode, KnowledgeHealth } from "@/types/api";
import { api, withAccessToken } from "@/lib/api";
import Link from "next/link";
import {
  ChevronLeft,
  Save,
  Cpu,
  Settings as SettingsIcon,
  CheckCircle2,
  AlertCircle,
  Thermometer,
  Hash,
  Sparkles,
  Palette,
  Database,
  Upload,
  Trash2,
  FileText,
  Loader2,
  Archive,
  Image as ImageIcon,
  Copy,
  UserPlus,
  ShieldCheck,
} from "lucide-react";
import PersonaManager from "@/components/persona-manager";
import { useTheme } from "@/hooks/use-theme";
import ConfirmDialog from "@/components/confirm-dialog";
import AppBackgroundLayers from "@/components/app-background-layers";
import AIProviderManager from "@/components/ai-provider-manager";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2000);
  const [activeTab, setActiveTab] = useState<"model" | "persona" | "knowledge" | "appearance">("model");
  const [summaryAutoGenerate, setSummaryAutoGenerate] = useState(true);
  const [summaryGenerationStyle, setSummaryGenerationStyle] = useState("concise");
  const [autoSaveInterval, setAutoSaveInterval] = useState(30);
  const [workspaceDir, setWorkspaceDir] = useState("./workspace");
  const [workspaceSyncStatus, setWorkspaceSyncStatus] = useState("");
  const [workspaceSyncing, setWorkspaceSyncing] = useState(false);
  const [backupStatus, setBackupStatus] = useState("");
  const [backuping, setBackuping] = useState(false);
  const [workspaceImportStatus, setWorkspaceImportStatus] = useState("");
  const [workspaceImporting, setWorkspaceImporting] = useState(false);
  const [backgroundBlur, setBackgroundBlur] = useState(0);
  const [backgroundDim, setBackgroundDim] = useState(22);
  const [editorPaperOpacity, setEditorPaperOpacity] = useState(92);
  const [backgroundStatus, setBackgroundStatus] = useState("");
  const [backgroundUploading, setBackgroundUploading] = useState(false);
  const [backgroundVersion, setBackgroundVersion] = useState(0);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [showBackgroundOnProfile, setShowBackgroundOnProfile] = useState(false);
  const [inviteMaxUses, setInviteMaxUses] = useState(1);
  const [inviteExpiresDays, setInviteExpiresDays] = useState(14);
  const [inviteCreating, setInviteCreating] = useState(false);
  const [lastInvite, setLastInvite] = useState<InviteCode | null>(null);

  // 分层记忆和检索设置
  const [currentChapterChars, setCurrentChapterChars] = useState(4000);
  const [nearbyChapterCount, setNearbyChapterCount] = useState(3);
  const [injectNearbySummaries, setInjectNearbySummaries] = useState(true);
  const [injectChapterRag, setInjectChapterRag] = useState(true);
  const [suggestUseExternalRag, setSuggestUseExternalRag] = useState(false);
  const [chatUseChapterRag, setChatUseChapterRag] = useState(true);
  const [externalRagWeight, setExternalRagWeight] = useState(30);

  // 知识库状态
  const [kbItems, setKbItems] = useState<KnowledgeBase[]>([]);
  const [kbLoading, setKbLoading] = useState(false);
  const [kbUploading, setKbUploading] = useState(false);
  const [kbError, setKbError] = useState<string | null>(null);
  const [kbDeleteTarget, setKbDeleteTarget] = useState<KnowledgeBase | null>(null);
  const [kbDeleting, setKbDeleting] = useState(false);
  const [kbHealth, setKbHealth] = useState<KnowledgeHealth | null>(null);
  const [kbHealthLoading, setKbHealthLoading] = useState(false);
  const [kbReindexing, setKbReindexing] = useState(false);
  const [kbReindexStatus, setKbReindexStatus] = useState("");

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    loadSettings();
    api.me().then((user) => {
      setCurrentUser(user);
      setShowBackgroundOnProfile(user.show_background_on_profile ?? false);
    }).catch(() => setCurrentUser(null));
  }, []);

  // 切换到知识库 Tab 时加载
  useEffect(() => {
    if (activeTab === "knowledge") {
      loadKnowledgeBases();
      loadKnowledgeHealth();
    }
  }, [activeTab]);

  const loadSettings = async () => {
    try {
      const data = await api.getSettings();
      setSettings(data);
      setTemperature(data.temperature ?? 0.7);
      setMaxTokens(data.max_tokens ?? 2000);
      setSummaryAutoGenerate(data.summary_auto_generate ?? true);
      setSummaryGenerationStyle(data.summary_generation_style || "concise");
      setAutoSaveInterval(data.auto_save_interval ?? 30);
      setWorkspaceDir(data.workspace_dir || "./workspace");
      setBackgroundBlur(data.background_blur ?? 0);
      setBackgroundDim(data.background_dim ?? 22);
      setEditorPaperOpacity(data.editor_paper_opacity ?? 92);
      // 分层记忆和检索设置
      setCurrentChapterChars(data.current_chapter_chars ?? 4000);
      setNearbyChapterCount(data.nearby_chapter_count ?? 3);
      setInjectNearbySummaries(data.inject_nearby_summaries ?? true);
      setInjectChapterRag(data.inject_chapter_rag ?? true);
      setSuggestUseExternalRag(data.suggest_use_external_rag ?? false);
      setChatUseChapterRag(data.chat_use_chapter_rag ?? true);
      setExternalRagWeight(data.external_rag_weight ?? 30);
    } catch {}
    finally { setLoading(false); }
  };

  const loadKnowledgeBases = async () => {
    setKbLoading(true);
    setKbError(null);
    try {
      const data = await api.getKnowledgeBases();
      setKbItems(data);
    } catch { setKbError("无法获取知识库列表"); }
    finally { setKbLoading(false); }
  };

  const handleKbUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setKbUploading(true);
    setKbError(null);
    try {
      await api.uploadKnowledgeBase(file);
      await loadKnowledgeBases();
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setKbError(message.includes("向量") || message.includes("embedding")
        ? "外部语料需要向量模型。请先安装向量依赖并确认模型已加载。"
        : "上传失败，请确保格式正确（txt/pdf/docx）");
    }
    finally { setKbUploading(false); e.target.value = ""; }
  };

  const handleKbDelete = async () => {
    if (!kbDeleteTarget) return;
    setKbDeleting(true);
    try {
      await api.deleteKnowledgeBase(kbDeleteTarget.id);
      await loadKnowledgeBases();
      setKbDeleteTarget(null);
    }
    catch { setKbError("删除失败"); }
    finally { setKbDeleting(false); }
  };

  const loadKnowledgeHealth = async () => {
    setKbHealthLoading(true);
    try {
      const data = await api.getKnowledgeHealth();
      setKbHealth(data);
    } catch {
      setKbHealth(null);
    } finally {
      setKbHealthLoading(false);
    }
  };

  const handleKnowledgeReindex = async () => {
    setKbReindexing(true);
    setKbReindexStatus("");
    setKbError(null);
    try {
      const result = await api.reindexKnowledge();
      setKbReindexStatus(`已重建 ${result.documents} 个文档，写入 ${result.vectorized_chunks} 个向量切片`);
      await loadKnowledgeHealth();
      await loadKnowledgeBases();
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setKbError(message.includes("向量") || message.includes("embedding")
        ? "向量模型未就绪。请先运行 download-vector-model.cmd，然后重启后端。"
        : "重建索引失败");
    } finally {
      setKbReindexing(false);
    }
  };

  const handleCreateInvite = async () => {
    setInviteCreating(true);
    try {
      const invite = await api.createInvite(
        Math.max(1, inviteMaxUses || 1),
        inviteExpiresDays > 0 ? inviteExpiresDays : null,
      );
      setLastInvite(invite);
      showToast("邀请码已生成", true);
    } catch {
      showToast("生成邀请码失败，请确认当前账号是管理员", false);
    } finally {
      setInviteCreating(false);
    }
  };

  const handleCopyInvite = async () => {
    if (!lastInvite?.code) return;
    try {
      await navigator.clipboard.writeText(lastInvite.code);
      showToast("邀请码已复制", true);
    } catch {
      showToast("复制失败，请手动选中复制", false);
    }
  };

  const handleProfileBackgroundVisibility = async (visible: boolean) => {
    const previous = showBackgroundOnProfile;
    setShowBackgroundOnProfile(visible);
    try {
      const updated = await api.updateMyProfile({ show_background_on_profile: visible });
      setCurrentUser((current) => current ? {
        ...current,
        show_background_on_profile: updated.show_background_on_profile,
      } : current);
      showToast(visible ? "个人主页背景已公开" : "个人主页背景已隐藏", true);
    } catch {
      setShowBackgroundOnProfile(previous);
      showToast("背景公开设置保存失败，请重试", false);
    }
  };

  const handleSave = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setSaving(true);
    try {
      const update: SettingsUpdate = {
        temperature,
        max_tokens: maxTokens,
        summary_auto_generate: summaryAutoGenerate,
        summary_generation_style: summaryGenerationStyle,
        auto_save_interval: autoSaveInterval,
        workspace_dir: workspaceDir.trim() || "./workspace",
        background_blur: backgroundBlur,
        background_dim: backgroundDim,
        editor_paper_opacity: editorPaperOpacity,
        // 分层记忆和检索设置
        current_chapter_chars: currentChapterChars,
        nearby_chapter_count: nearbyChapterCount,
        inject_nearby_summaries: injectNearbySummaries,
        inject_chapter_rag: injectChapterRag,
        suggest_use_external_rag: suggestUseExternalRag,
        chat_use_chapter_rag: chatUseChapterRag,
        external_rag_weight: externalRagWeight,
      };
      await api.updateSettings(update);
      await loadSettings();
      showToast("配置已保存", true);
      return true;
    } catch {
      showToast("保存失败，请重试", false);
      return false;
    }
    finally { setSaving(false); }
  };

  const handleBackgroundUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBackgroundUploading(true);
    setBackgroundStatus("正在上传背景图...");
    try {
      const updated = await api.uploadBackgroundImage(file);
      setSettings(updated);
      setBackgroundVersion(Date.now());
      setBackgroundStatus("背景图已更新");
    } catch {
      setBackgroundStatus("背景图上传失败");
    } finally {
      setBackgroundUploading(false);
      e.target.value = "";
    }
  };

  const handleBackgroundClear = async () => {
    setBackgroundUploading(true);
    setBackgroundStatus("正在清除背景图...");
    try {
      const updated = await api.clearBackgroundImage();
      setSettings(updated);
      setBackgroundVersion(Date.now());
      setBackgroundStatus("背景图已清除");
    } catch {
      setBackgroundStatus("清除失败");
    } finally {
      setBackgroundUploading(false);
    }
  };

  const handleWorkspaceSync = async () => {
    setWorkspaceSyncing(true);
    setWorkspaceSyncStatus("正在同步作品库...");
    try {
      const saved = await handleSave();
      if (!saved) {
        setWorkspaceSyncStatus("设置保存失败，未同步作品库");
        return;
      }
      const result = await api.syncWorkspaceLibrary();
      setWorkspaceSyncStatus(`已同步 ${result.book_count} 本书、${result.chapter_count} 章到 ${result.workspace}`);
    } catch {
      setWorkspaceSyncStatus("作品库同步失败");
    } finally {
      setWorkspaceSyncing(false);
    }
  };

  const handleWorkspaceBackup = async () => {
    setBackuping(true);
    setBackupStatus("正在生成备份...");
    try {
      const saved = await handleSave();
      if (!saved) {
        setBackupStatus("设置保存失败，未生成备份");
        return;
      }
      const filename = await api.backupWorkspaceLibrary();
      setBackupStatus(`已下载 ${filename}`);
    } catch {
      setBackupStatus("备份失败");
    } finally {
      setBackuping(false);
    }
  };

  const handleWorkspaceScan = async () => {
    setWorkspaceImporting(true);
    setWorkspaceImportStatus("正在扫描作品文件夹...");
    try {
      const saved = await handleSave();
      if (!saved) {
        setWorkspaceImportStatus("设置保存失败，未扫描作品文件夹");
        return;
      }
      const result = await api.scanWorkspaceLibrary();
      setWorkspaceImportStatus(`发现 ${result.book_count} 本书、${result.chapter_count} 章、${result.char_count} 字符`);
    } catch {
      setWorkspaceImportStatus("扫描失败");
    } finally {
      setWorkspaceImporting(false);
    }
  };

  const handleWorkspaceImport = async () => {
    setWorkspaceImporting(true);
    setWorkspaceImportStatus("正在从作品文件夹导入...");
    try {
      const saved = await handleSave();
      if (!saved) {
        setWorkspaceImportStatus("设置保存失败，未导入");
        return;
      }
      const result = await api.importWorkspaceLibrary();
      setWorkspaceImportStatus(
        `导入完成：新增 ${result.created_books} 本书/${result.created_chapters} 章，更新 ${result.updated_books} 本书/${result.updated_chapters} 章`
      );
    } catch {
      setWorkspaceImportStatus("导入失败");
    } finally {
      setWorkspaceImporting(false);
    }
  };

  // ── 主题相关样式 ─────────────────────────────────────────────────────────────
  const isDark = theme === 'dark';
  const isSepia = theme === 'sepia';
  const pageBg = isDark ? 'bg-slate-950' : isSepia ? 'bg-[#f7f2e8]' : 'bg-slate-100';
  const headerBg = isDark ? 'bg-slate-950/90 border-slate-800' : isSepia ? 'bg-[#f7f2e8]/90 border-amber-200' : 'bg-slate-100/90 border-slate-200';
  const cardBg = isDark ? 'bg-slate-900/70 border-slate-800' : isSepia ? 'bg-[#fbf7ed] border-amber-200' : 'bg-white border-slate-200';
  const headingTxt = isDark ? 'text-slate-100' : isSepia ? 'text-amber-950' : 'text-slate-900';
  const bodyTxt = isDark ? 'text-slate-300' : isSepia ? 'text-amber-800' : 'text-slate-700';
  const mutedTxt = isDark ? 'text-slate-500' : isSepia ? 'text-amber-600' : 'text-slate-500';
  const hoverTxt = isDark ? 'hover:text-slate-100' : isSepia ? 'hover:text-amber-950' : 'hover:text-slate-900';
  const groupHoverTxt = isDark ? 'group-hover:text-slate-100' : isSepia ? 'group-hover:text-amber-950' : 'group-hover:text-slate-900';
  const borderCls = isDark ? 'border-slate-800' : isSepia ? 'border-amber-200' : 'border-slate-200';
  const accentBar = isDark ? 'bg-slate-500' : isSepia ? 'bg-amber-700' : 'bg-slate-900';
  const navActive = isDark ? 'bg-slate-800 text-slate-100' : isSepia ? 'bg-amber-100 text-amber-950' : 'bg-white text-slate-900 border-slate-200';
  const navInactive = isDark ? 'text-slate-400 hover:bg-slate-900 hover:text-slate-200' : isSepia ? 'text-amber-700 hover:bg-amber-100 hover:text-amber-950' : 'text-slate-600 hover:bg-white hover:text-slate-900';
  const inputCls = isDark ? 'bg-slate-950/40 border-slate-700 text-slate-200 placeholder:text-slate-600 focus:border-slate-500' : isSepia ? 'bg-white/60 border-amber-200 text-amber-950 placeholder:text-amber-400 focus:border-amber-500' : 'bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400';
  const primaryBtn = isDark ? 'bg-slate-200 hover:bg-white text-slate-950' : isSepia ? 'bg-amber-900 hover:bg-amber-800 text-white' : 'bg-slate-900 hover:bg-slate-800 text-white';
  const secondaryBtn = isDark ? 'bg-slate-900 text-slate-300 hover:bg-slate-800 border-slate-700' : isSepia ? 'bg-[#f7f2e8] text-amber-800 hover:bg-amber-100 border-amber-200' : 'bg-white text-slate-700 hover:bg-slate-50 border-slate-200';
  const hoverRow = isDark ? 'hover:bg-slate-900' : isSepia ? 'hover:bg-amber-100/60' : 'hover:bg-slate-50';
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  const backgroundPreviewUrl = settings?.background_image_path
    ? withAccessToken(`${apiBase}/settings/background?v=${backgroundVersion}`)
    : "";

  return (
    <div className={`relative min-h-screen ${backgroundPreviewUrl ? "bg-slate-950" : pageBg} flex flex-col ${bodyTxt}`}>
      <AppBackgroundLayers url={backgroundPreviewUrl} blur={backgroundBlur} dim={68} mode="page" />
      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-5 left-1/2 -translate-x-1/2 z-[2000] px-4 py-2 rounded-md text-sm font-semibold flex items-center space-x-2 border transition-all ${toast.ok ? "bg-slate-950 text-white border-slate-800" : "bg-red-600 text-white border-red-700"}`}>
          <span>{toast.ok ? "✓" : "✕"}</span>
          <span>{toast.msg}</span>
        </div>
      )}

      {/* 顶部导航 */}
      <header className={`sticky top-0 z-[100] flex items-center justify-between gap-3 border-b px-4 py-3 backdrop-blur-md sm:px-6 ${headerBg}`}>
        <div className="flex min-w-0 items-center space-x-3 sm:space-x-6">
          <Link href="/" className={`group flex items-center space-x-2 ${mutedTxt} ${hoverTxt} transition-all`}>
            <div className={`p-1.5 rounded-md ${hoverRow} transition-colors`}>
              <ChevronLeft size={18} />
            </div>
            <span className="hidden text-sm font-medium sm:inline">返回编辑器</span>
          </Link>
          <div className={`h-4 w-px ${borderCls}`} />
          <div className="flex items-center space-x-2">
            <SettingsIcon size={18} className={mutedTxt} />
            <h1 className={`font-bold text-base tracking-tight ${headingTxt}`}>设置</h1>
          </div>
        </div>
        <button
          onClick={() => handleSave()}
          disabled={saving}
          className={`flex shrink-0 items-center space-x-2 rounded-md px-3 py-2 sm:px-4 ${primaryBtn} disabled:opacity-40 transition-all font-semibold text-sm`}
        >
          {saving ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Save size={16} />}
          <span>{saving ? "正在同步..." : "保存更改"}</span>
        </button>
      </header>

      <main className="relative z-10 mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-8 lg:py-8">
        {/* 左侧导航 */}
        <aside className="min-w-0">
          <nav className="flex gap-2 overflow-x-auto pb-1 lg:sticky lg:top-28 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
            <p className={`mb-2 hidden px-3 text-xs font-bold ${mutedTxt} lg:block`}>设置</p>
            {[
              { key: "model", icon: <Cpu size={16} />, label: "AI 模型服务" },
              { key: "persona", icon: <Sparkles size={16} />, label: "人格预设" },
              { key: "knowledge", icon: <Database size={16} />, label: "知识库 (RAG)" },
              { key: "appearance", icon: <Palette size={16} />, label: "外观主题" },
            ].map(({ key, icon, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as typeof activeTab)}
                className={`flex shrink-0 items-center space-x-2 rounded-md border border-transparent px-3 py-2 text-sm font-semibold transition-all lg:w-full lg:space-x-3 ${activeTab === key ? navActive : navInactive}`}
              >
                {icon}
                <span>{label}</span>
              </button>
            ))}
            {currentUser?.is_admin && (
              <Link
                href="/admin"
                className={`flex shrink-0 items-center space-x-2 rounded-md border border-transparent px-3 py-2 text-sm font-semibold transition-all lg:mt-4 lg:w-full lg:space-x-3 ${navInactive}`}
              >
                <ShieldCheck size={16} />
                <span>管理员中心</span>
              </Link>
            )}
          </nav>
        </aside>

        {/* 右侧主配置区 */}
        <div className="min-w-0 space-y-6 pb-16">
          {loading && activeTab === 'model' ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className={`w-10 h-10 border-4 ${isDark ? 'border-slate-700 border-t-slate-400' : 'border-slate-200 border-t-slate-900'} rounded-full animate-spin`} />
              <p className={`text-sm ${mutedTxt} font-medium`}>正在读取配置...</p>
            </div>
          ) : (
            <>
              {/* ── AI 模型服务 ── */}
              {activeTab === "model" && (
                <>
                  <AIProviderManager theme={theme} />

                  {currentUser?.is_admin && (
                    <section className="space-y-5">
                      <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                        <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                        <h2 className={`text-lg font-bold ${headingTxt}`}>邀请朋友</h2>
                      </div>
                      <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                        <div className="flex items-start gap-4">
                          <div className={`p-2 ${isDark ? 'bg-slate-800' : isSepia ? 'bg-amber-100' : 'bg-slate-100'} rounded-md ${mutedTxt}`}>
                            <UserPlus size={18} />
                          </div>
                          <div className="flex-1 space-y-4">
                            <div>
                              <div className={`text-sm font-bold ${headingTxt}`}>生成邀请码</div>
                              <p className={`text-xs ${mutedTxt} mt-1`}>第一个注册的人会自动成为管理员，之后新用户需要管理员生成的邀请码。</p>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3">
                              <label className="space-y-1">
                                <span className={`text-xs font-bold ${mutedTxt}`}>可使用次数</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={20}
                                  value={inviteMaxUses}
                                  onChange={(e) => setInviteMaxUses(parseInt(e.target.value) || 1)}
                                  className={`w-full border rounded-md px-3 py-2 text-sm outline-none transition-all ${inputCls}`}
                                />
                              </label>
                              <label className="space-y-1">
                                <span className={`text-xs font-bold ${mutedTxt}`}>有效天数</span>
                                <input
                                  type="number"
                                  min={0}
                                  max={365}
                                  value={inviteExpiresDays}
                                  onChange={(e) => setInviteExpiresDays(parseInt(e.target.value) || 0)}
                                  className={`w-full border rounded-md px-3 py-2 text-sm outline-none transition-all ${inputCls}`}
                                />
                              </label>
                              <button
                                type="button"
                                onClick={handleCreateInvite}
                                disabled={inviteCreating}
                                className={`self-end flex items-center justify-center gap-2 px-4 py-2 rounded-md ${primaryBtn} disabled:opacity-50 transition-all font-semibold text-sm`}
                              >
                                {inviteCreating ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                                生成
                              </button>
                            </div>
                            {lastInvite && (
                              <div className={`flex flex-col sm:flex-row sm:items-center gap-3 rounded-md border ${borderCls} p-3 ${isDark ? 'bg-slate-950/40' : isSepia ? 'bg-white/40' : 'bg-slate-50'}`}>
                                <code className={`flex-1 text-sm font-mono font-bold break-all ${headingTxt}`}>{lastInvite.code}</code>
                                <button
                                  type="button"
                                  onClick={handleCopyInvite}
                                  className={`inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md border text-xs font-bold ${secondaryBtn}`}
                                >
                                  <Copy size={14} />
                                  复制
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </section>
                  )}

                  {/* 生成参数 */}
                  <section className="space-y-5">
                    <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                      <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                      <h2 className={`text-lg font-bold ${headingTxt}`}>生成参数控制</h2>
                    </div>
                    <div className="grid grid-cols-2 gap-6">
                      <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                        <div className="flex justify-between items-center">
                          <div className={`flex items-center space-x-3 ${headingTxt} font-bold text-sm`}>
                            <Thermometer size={18} className="text-orange-500" />
                            <span>采样温度</span>
                          </div>
                          <span className={`${headingTxt} font-semibold text-sm px-2 py-1 ${isDark ? 'bg-slate-800' : 'bg-slate-100'} rounded-md`}>{temperature}</span>
                        </div>
                        <input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(parseFloat(e.target.value))} className={`w-full h-2 rounded-lg appearance-none cursor-pointer ${isDark ? 'bg-slate-700 accent-slate-400' : 'bg-slate-100 accent-slate-900'}`} />
                        <div className={`flex justify-between text-xs ${mutedTxt} font-bold`}><span>严谨精确</span><span>更具创意</span></div>
                      </div>
                      <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                        <div className="flex justify-between items-center">
                          <div className={`flex items-center space-x-3 ${headingTxt} font-bold text-sm`}>
                            <Hash size={18} className="text-emerald-500" />
                            <span>最大生成长度</span>
                          </div>
                          <span className={`${headingTxt} font-semibold text-sm px-2 py-1 ${isDark ? 'bg-slate-800' : 'bg-slate-100'} rounded-md`}>{maxTokens}</span>
                        </div>
                        <input type="range" min="100" max="4000" step="100" value={maxTokens} onChange={(e) => setMaxTokens(parseInt(e.target.value))} className={`w-full h-2 rounded-lg appearance-none cursor-pointer ${isDark ? 'bg-slate-700 accent-slate-400' : 'bg-slate-100 accent-slate-900'}`} />
                        <div className={`flex justify-between text-xs ${mutedTxt} font-bold`}><span>短建议</span><span>长篇大论</span></div>
                      </div>
                    </div>
                  </section>

                  {/* 章节总结设置 */}
                  <section className="space-y-5">
                    <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                      <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                      <h2 className={`text-lg font-bold ${headingTxt}`}>章节总结设置</h2>
                    </div>
                    <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className={`text-sm font-bold ${headingTxt}`}>自动生成摘要</div>
                          <div className={`text-xs ${mutedTxt} mt-0.5`}>保存章节时自动生成 AI 摘要，用于分层记忆上下文</div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSummaryAutoGenerate(v => !v)}
                          className={`relative w-12 h-6 rounded-full transition-colors ${summaryAutoGenerate ? (isDark ? 'bg-slate-400' : 'bg-slate-900') : (isDark ? 'bg-slate-700' : 'bg-slate-200')}`}
                        >
                          <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${summaryAutoGenerate ? 'translate-x-7' : 'translate-x-1'}`} />
                        </button>
                      </div>
                      {summaryAutoGenerate && (
                        <div className="space-y-3">
                          <label className={`text-sm font-bold ${headingTxt}`}>摘要生成风格</label>
                          <select
                            value={summaryGenerationStyle}
                            onChange={(e) => setSummaryGenerationStyle(e.target.value)}
                            className={`w-full border rounded-md px-3 py-2 text-sm outline-none transition-all ${inputCls}`}
                          >
                            <option value="concise">简洁 - 一两句话概括核心情节</option>
                            <option value="detailed">详细 - 完整记录人物、事件与转折</option>
                            <option value="extract_first">提取首段 - 直接使用章节开头作为摘要</option>
                          </select>
                        </div>
                      )}
                    </div>
                  </section>

                  {/* 保存行为设置 */}
                  <section className="space-y-5">
                    <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                      <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                      <h2 className={`text-lg font-bold ${headingTxt}`}>保存与文件</h2>
                    </div>
                    <div className={`p-5 rounded-lg border ${cardBg} space-y-5`}>
                      <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-6">
                        <div>
                          <label className={`text-sm font-bold ${headingTxt}`}>自动保存</label>
                          <p className={`text-xs ${mutedTxt} mt-1 mb-4`}>停止输入后保存；0 为关闭。</p>
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              min={0}
                              max={300}
                              value={autoSaveInterval}
                              onChange={(e) => setAutoSaveInterval(parseInt(e.target.value) || 0)}
                              className={`w-24 border rounded-md px-3 py-2 text-sm outline-none transition-all ${inputCls}`}
                            />
                            <span className={`text-xs ${mutedTxt}`}>秒</span>
                          </div>
                        </div>

                        <div>
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <label className={`text-sm font-bold ${headingTxt}`}>作品文件夹</label>
                              <p className={`text-xs ${mutedTxt} mt-1`}>章节 TXT、作品索引和备份都围绕这个目录工作。</p>
                            </div>
                            <Database size={18} className={mutedTxt} />
                          </div>
                          <input
                            type="text"
                            value={workspaceDir}
                            onChange={(e) => setWorkspaceDir(e.target.value)}
                            placeholder="D:\\Novels\\NovelCat"
                            className={`w-full border rounded-md px-3 py-2 mt-3 text-sm outline-none transition-all font-mono ${inputCls}`}
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <button
                          type="button"
                          onClick={handleWorkspaceSync}
                          disabled={workspaceSyncing}
                          className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-xs font-bold transition-all disabled:opacity-50 ${primaryBtn}`}
                        >
                          <FileText size={15} />
                          {workspaceSyncing ? "同步中..." : "同步整个作品库"}
                        </button>
                        <button
                          type="button"
                          onClick={handleWorkspaceBackup}
                          disabled={backuping}
                          className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-xs font-bold transition-all disabled:opacity-50 ${primaryBtn}`}
                        >
                          <Archive size={15} />
                          {backuping ? "备份中..." : "下载备份 ZIP"}
                        </button>
                        <button
                          type="button"
                          onClick={handleWorkspaceScan}
                          disabled={workspaceImporting}
                          className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-xs font-bold transition-all disabled:opacity-50 ${primaryBtn}`}
                        >
                          <Database size={15} />
                          {workspaceImporting ? "处理中..." : "扫描作品文件夹"}
                        </button>
                        <button
                          type="button"
                          onClick={handleWorkspaceImport}
                          disabled={workspaceImporting}
                          className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-xs font-bold transition-all disabled:opacity-50 ${primaryBtn}`}
                        >
                          <Upload size={15} />
                          {workspaceImporting ? "处理中..." : "从文件夹导入"}
                        </button>
                      </div>

                      {(workspaceSyncStatus || backupStatus || workspaceImportStatus) && (
                        <div className={`text-[11px] ${mutedTxt} space-y-1`}>
                          {workspaceSyncStatus && <p>{workspaceSyncStatus}</p>}
                          {backupStatus && <p>{backupStatus}</p>}
                          {workspaceImportStatus && <p>{workspaceImportStatus}</p>}
                        </div>
                      )}
                    </div>
                  </section>

                  {/* 分层记忆强度 */}
                  <section className="space-y-5">
                    <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                      <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                      <h2 className={`text-lg font-bold ${headingTxt}`}>分层记忆强度</h2>
                    </div>
                    <div className={`p-5 rounded-lg border ${cardBg} space-y-5`}>
                      <div className="space-y-2">
                        <div className="flex justify-between items-center">
                          <label className={`text-sm font-bold ${headingTxt}`}>当前章节注入长度</label>
                          <span className={`text-sm font-mono ${mutedTxt}`}>{currentChapterChars} 字符</span>
                        </div>
                        <p className={`text-xs ${mutedTxt}`}>续写时注入当前章节的最大字符数</p>
                        <input
                          type="range" min={500} max={8000} step={500}
                          value={currentChapterChars}
                          onChange={e => setCurrentChapterChars(parseInt(e.target.value))}
                          className="w-full accent-slate-900"
                        />
                        <div className={`flex justify-between text-[10px] ${mutedTxt}`}>
                          <span>500</span><span>8000</span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between items-center">
                          <label className={`text-sm font-bold ${headingTxt}`}>附近章节数量</label>
                          <span className={`text-sm font-mono ${mutedTxt}`}>{nearbyChapterCount} 章</span>
                        </div>
                        <p className={`text-xs ${mutedTxt}`}>注入当前章节前后各多少章的摘要</p>
                        <input
                          type="range" min={1} max={5} step={1}
                          value={nearbyChapterCount}
                          onChange={e => setNearbyChapterCount(parseInt(e.target.value))}
                          className="w-full accent-slate-900"
                        />
                        <div className={`flex justify-between text-[10px] ${mutedTxt}`}>
                          <span>1</span><span>5</span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className={`text-sm font-bold ${headingTxt}`}>注入附近章节摘要</p>
                          <p className={`text-xs ${mutedTxt} mt-0.5`}>将附近章节的摘要注入 AI 上下文</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setInjectNearbySummaries(v => !v)}
                          className={`relative w-11 h-6 rounded-full transition-colors ${injectNearbySummaries ? 'bg-slate-900' : isDark ? 'bg-slate-700' : 'bg-slate-200'}`}
                        >
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${injectNearbySummaries ? 'translate-x-5' : ''}`} />
                        </button>
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className={`text-sm font-bold ${headingTxt}`}>注入全书检索结果</p>
                          <p className={`text-xs ${mutedTxt} mt-0.5`}>从全书章节中检索相关内容注入上下文</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setInjectChapterRag(v => !v)}
                          className={`relative w-11 h-6 rounded-full transition-colors ${injectChapterRag ? 'bg-slate-900' : isDark ? 'bg-slate-700' : 'bg-slate-200'}`}
                        >
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${injectChapterRag ? 'translate-x-5' : ''}`} />
                        </button>
                      </div>
                    </div>
                  </section>

                  {/* 检索行为 */}
                  <section className="space-y-5">
                    <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                      <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                      <h2 className={`text-lg font-bold ${headingTxt}`}>检索行为</h2>
                    </div>
                    <div className={`p-5 rounded-lg border ${cardBg} space-y-5`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className={`text-sm font-bold ${headingTxt}`}>续写时默认使用外部语料 RAG</p>
                          <p className={`text-xs ${mutedTxt} mt-0.5`}>关闭可防止 AI 直接复制上传的文档内容</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSuggestUseExternalRag(v => !v)}
                          className={`relative w-11 h-6 rounded-full transition-colors ${suggestUseExternalRag ? 'bg-slate-900' : isDark ? 'bg-slate-700' : 'bg-slate-200'}`}
                        >
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${suggestUseExternalRag ? 'translate-x-5' : ''}`} />
                        </button>
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className={`text-sm font-bold ${headingTxt}`}>对话中自动检索全书</p>
                          <p className={`text-xs ${mutedTxt} mt-0.5`}>对话时自动从自己的全书章节中检索相关内容；这是分层记忆的一层，不是外部 RAG。</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setChatUseChapterRag(v => !v)}
                          className={`relative w-11 h-6 rounded-full transition-colors ${chatUseChapterRag ? 'bg-slate-900' : isDark ? 'bg-slate-700' : 'bg-slate-200'}`}
                        >
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${chatUseChapterRag ? 'translate-x-5' : ''}`} />
                        </button>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between items-center">
                          <label className={`text-sm font-bold ${headingTxt}`}>外部语料权重</label>
                          <span className={`text-sm font-mono ${mutedTxt}`}>{externalRagWeight}</span>
                        </div>
                        <p className={`text-xs ${mutedTxt}`}>值越高，AI 越倾向于参考上传的外部文档风格</p>
                        <input
                          type="range" min={0} max={100} step={5}
                          value={externalRagWeight}
                          onChange={e => setExternalRagWeight(parseInt(e.target.value))}
                          className="w-full accent-slate-900"
                        />
                        <div className={`flex justify-between text-[10px] ${mutedTxt}`}>
                          <span>0（忽略）</span><span>100（强参考）</span>
                        </div>
                      </div>
                    </div>
                  </section>

                  {/* 隐私声明 */}
                  <div className={`${isDark ? 'bg-slate-900 border-slate-800 text-slate-300' : isSepia ? 'bg-[#fbf7ed] border-amber-200 text-amber-800' : 'bg-white border-slate-200 text-slate-700'} border rounded-lg p-5`}>
                    <div className="flex items-start space-x-3">
                      <div className={`p-2 ${isDark ? 'bg-slate-800' : 'bg-slate-100'} rounded-md`}><AlertCircle size={18} /></div>
                      <div>
                        <h3 className={`font-bold text-sm mb-1 ${headingTxt}`}>本地优先</h3>
                        <p className={`text-xs leading-relaxed ${mutedTxt}`}>除向您选择的 AI 服务商发送必要提示词外，写作内容默认保存在本机。</p>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* ── 人格预设 ── */}
              {activeTab === "persona" && <PersonaManager />}

              {/* ── 知识库 ── */}
              {activeTab === "knowledge" && (
                <section className="space-y-6">
                  <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                    <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                    <h2 className={`text-lg font-bold ${headingTxt}`}>知识库 (RAG)</h2>
                  </div>

                  {kbError && (
                    <div className={`p-3 ${isDark ? 'bg-red-950/40 border-red-900 text-red-300' : 'bg-red-50 border-red-200 text-red-700'} border rounded-md flex items-center space-x-3 text-sm`}>
                      <AlertCircle size={16} />
                      <span>{kbError}</span>
                    </div>
                  )}

                  <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="flex items-start gap-3">
                        <div className={`p-2 rounded-md ${kbHealth?.vector_ready ? 'bg-emerald-100 text-emerald-700' : isDark ? 'bg-red-950/50 text-red-300' : 'bg-red-50 text-red-600'}`}>
                          {kbHealthLoading ? <Loader2 size={18} className="animate-spin" /> : kbHealth?.vector_ready ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                        </div>
                        <div>
                          <h3 className={`text-sm font-bold ${headingTxt}`}>
                            {kbHealth?.vector_ready ? "向量引擎已就绪" : "向量引擎未就绪"}
                          </h3>
                          <p className={`text-xs ${mutedTxt} mt-1`}>
                            {kbHealth?.model || "BAAI/bge-small-zh-v1.5"} · {kbHealth?.device || "cpu"} · {kbHealth?.local_files_only ? "本地缓存" : "允许下载"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={loadKnowledgeHealth}
                          disabled={kbHealthLoading}
                          className={`inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md border text-xs font-bold ${secondaryBtn} disabled:opacity-50`}
                        >
                          {kbHealthLoading ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
                          刷新状态
                        </button>
                        <button
                          type="button"
                          onClick={handleKnowledgeReindex}
                          disabled={kbReindexing || !kbHealth?.vector_ready}
                          className={`inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md text-xs font-bold ${primaryBtn} disabled:opacity-50`}
                        >
                          {kbReindexing ? <Loader2 size={14} className="animate-spin" /> : <Archive size={14} />}
                          重建索引
                        </button>
                      </div>
                    </div>
                    {kbReindexStatus && (
                      <div className={`text-xs ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>{kbReindexStatus}</div>
                    )}
                    {!kbHealth?.vector_ready && (
                      <div className={`text-xs leading-relaxed ${mutedTxt}`}>
                        运行 download-vector-model.cmd 后重启后端；外部语料只使用向量检索。
                      </div>
                    )}
                  </div>

                  {/* 上传区 */}
                  <div className={`p-5 rounded-lg border ${cardBg}`}>
                    <label className="relative group cursor-pointer block">
                      <input type="file" className="hidden" onChange={handleKbUpload} disabled={kbUploading || !kbHealth?.vector_ready} accept=".txt,.pdf,.docx" />
                      <div className={`border border-dashed rounded-lg p-8 flex flex-col items-center justify-center transition-all ${
                        kbUploading
                          ? `${isDark ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-200'}`
                          : !kbHealth?.vector_ready
                          ? `${isDark ? 'border-red-900 bg-red-950/20' : 'border-red-200 bg-red-50/60'} cursor-not-allowed`
                          : `${isDark ? 'border-slate-700 hover:border-slate-500 hover:bg-slate-800/50' : 'border-slate-200 hover:border-slate-400 hover:bg-slate-50'}`
                      }`}>
                        {kbUploading ? (
                          <Loader2 size={32} className={`${isDark ? 'text-slate-400' : 'text-slate-600'} animate-spin mb-4`} />
                        ) : (
                          <Upload size={32} className={`${mutedTxt} ${groupHoverTxt} transition-colors mb-4`} />
                        )}
                        <span className={`text-sm font-bold ${headingTxt}`}>
                          {kbUploading ? "正在解析并向量化..." : kbHealth?.vector_ready ? "点击或拖拽上传写作语料" : "向量引擎就绪后才能上传"}
                        </span>
                        <span className={`mt-2 text-xs ${mutedTxt}`}>支持 TXT, PDF, DOCX · 纯向量检索</span>
                      </div>
                    </label>
                  </div>

                  {/* 已上传列表 */}
                  <div className={`p-5 rounded-lg border ${cardBg} space-y-4`}>
                    <h3 className={`text-xs font-bold ${mutedTxt} uppercase tracking-widest`}>已加载的知识片段</h3>
                    {kbLoading ? (
                      <div className="py-10 flex justify-center"><Loader2 className={`animate-spin ${mutedTxt}`} size={28} /></div>
                    ) : kbItems.length === 0 ? (
                      <div className={`py-8 text-center ${mutedTxt} italic text-sm border border-dotted ${borderCls} rounded-lg`}>
                        暂无知识语料，上传文件以开启 RAG 增强
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {kbItems.map((item) => (
                          <div key={item.id} className={`group p-3 rounded-md border ${borderCls} flex justify-between items-center ${hoverRow} transition-all`}>
                            <div className="flex items-center space-x-4">
                              <div className={`p-2 ${isDark ? 'bg-slate-800' : 'bg-slate-50'} rounded-md ${mutedTxt}`}>
                                <FileText size={18} />
                              </div>
                              <div>
                                <div className={`text-sm font-bold ${headingTxt} truncate max-w-[320px]`}>{item.title}</div>
                                <div className={`text-[10px] ${mutedTxt} font-medium mt-0.5`}>
                                  {item.chunk_count} 个知识切片 · {item.created_at ? new Date(item.created_at).toLocaleDateString() : '刚刚'}
                                </div>
                              </div>
                            </div>
                            <button
                              onClick={() => setKbDeleteTarget(item)}
                              className={`p-1.5 ${mutedTxt} hover:text-red-500 rounded-md transition-all opacity-0 group-hover:opacity-100`}
                              title="删除文档"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className={`${isDark ? 'bg-slate-900 border-slate-800' : isSepia ? 'bg-[#fbf7ed] border-amber-200' : 'bg-white border-slate-200'} border rounded-lg p-4`}>
                    <div className="flex items-start space-x-3">
                      <AlertCircle size={18} className={isDark ? 'text-slate-400' : 'text-blue-500'} />
                      <p className={`text-xs ${isDark ? 'text-slate-300' : 'text-blue-700'} leading-relaxed`}>
                        知识库通过 RAG (检索增强生成) 技术工作。续写时，AI 助手面板中的 RAG 开关开启后，系统会自动检索最相关的片段注入 AI 上下文，帮助 AI 学习您的措辞、人设或世界观。
                      </p>
                    </div>
                  </div>
                </section>
              )}

              {/* ── 外观主题 ── */}
              {activeTab === "appearance" && (
                <section className="space-y-6">
                  <div className={`flex items-center space-x-2 border-b ${borderCls} pb-4`}>
                    <div className={`w-1.5 h-6 ${accentBar} rounded-full`} />
                    <h2 className={`text-lg font-bold ${headingTxt}`}>外观与写作</h2>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { key: "light", label: "浅色模式", desc: "经典白色背景", preview: "from-white to-slate-100", previewBorder: "border-slate-200", ring: "border-slate-900 bg-white", normal: "border-slate-200 bg-white hover:border-slate-300" },
                      { key: "dark", label: "深色模式", desc: "夜间写作", preview: "from-slate-800 to-slate-950", previewBorder: "border-slate-700", ring: "border-slate-500 bg-slate-900", normal: "border-slate-700 bg-slate-900 hover:border-slate-500" },
                      { key: "sepia", label: "护眼模式", desc: "暖色纸张", preview: "from-amber-50 to-amber-100", previewBorder: "border-amber-200", ring: "border-amber-800 bg-[#fbf7ed]", normal: "border-amber-200 bg-[#fbf7ed] hover:border-amber-300" },
                    ].map(t => (
                      <button
                        key={t.key}
                        type="button"
                        onClick={() => setTheme(t.key as "light" | "dark" | "sepia")}
                        className={`relative p-4 rounded-lg border text-left transition-all ${theme === t.key ? t.ring : t.normal}`}
                      >
                        <div className={`aspect-video bg-gradient-to-br ${t.preview} border ${t.previewBorder} rounded-lg mb-4`} />
                        <div className={`font-bold text-sm ${headingTxt}`}>{t.label}</div>
                        <div className={`text-xs ${mutedTxt} mt-1`}>{t.desc}</div>
                        {theme === t.key && (
                          <div className="absolute top-3 right-3 bg-slate-900 text-white p-1 rounded-md"><CheckCircle2 size={14} /></div>
                        )}
                      </button>
                    ))}
                  </div>

                  <div className={`p-5 rounded-lg border ${cardBg} space-y-5`}>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className={`text-sm font-bold ${headingTxt}`}>我的应用背景</h3>
                        <p className={`text-xs ${mutedTxt} mt-1`}>这张图片会用于写作、设置、伙伴与聊天页面，并独立保存在你的用户空间中。</p>
                      </div>
                      <ImageIcon size={18} className={mutedTxt} />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-6">
                      <div className={`aspect-[4/3] rounded-lg overflow-hidden border ${borderCls} ${isDark ? 'bg-slate-800' : 'bg-slate-100'} flex items-center justify-center`}>
                        {backgroundPreviewUrl ? (
                          <div
                            className="w-full h-full bg-cover bg-center"
                            style={{ backgroundImage: `url(${backgroundPreviewUrl})` }}
                          />
                        ) : (
                          <ImageIcon size={28} className={mutedTxt} />
                        )}
                      </div>

                      <div className="space-y-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-md text-xs font-bold cursor-pointer transition-all ${primaryBtn}`}>
                            <Upload size={14} />
                            {backgroundUploading ? "处理中..." : "上传背景图"}
                            <input
                              type="file"
                              accept="image/*"
                              className="hidden"
                              disabled={backgroundUploading}
                              onChange={handleBackgroundUpload}
                            />
                          </label>
                          <button
                            type="button"
                            onClick={handleBackgroundClear}
                            disabled={backgroundUploading || !settings?.background_image_path}
                            className={`px-4 py-2 rounded-md text-xs font-bold transition-all disabled:opacity-40 border ${secondaryBtn}`}
                          >
                            清除背景
                          </button>
                          {backgroundStatus && <span className={`text-xs ${mutedTxt}`}>{backgroundStatus}</span>}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <div className="flex justify-between text-xs mb-2">
                              <span className={`font-bold ${headingTxt}`}>模糊</span>
                              <span className={mutedTxt}>{backgroundBlur}px</span>
                            </div>
                            <input type="range" min={0} max={24} value={backgroundBlur} onChange={e => setBackgroundBlur(parseInt(e.target.value))} className="w-full accent-slate-900" />
                          </div>
                          <div>
                            <div className="flex justify-between text-xs mb-2">
                              <span className={`font-bold ${headingTxt}`}>暗度</span>
                              <span className={mutedTxt}>{backgroundDim}%</span>
                            </div>
                            <input type="range" min={0} max={85} value={backgroundDim} onChange={e => setBackgroundDim(parseInt(e.target.value))} className="w-full accent-slate-900" />
                          </div>
                          <div>
                            <div className="flex justify-between text-xs mb-2">
                              <span className={`font-bold ${headingTxt}`}>纸张</span>
                              <span className={mutedTxt}>{editorPaperOpacity}%</span>
                            </div>
                            <input type="range" min={55} max={100} value={editorPaperOpacity} onChange={e => setEditorPaperOpacity(parseInt(e.target.value))} className="w-full accent-slate-900" />
                          </div>
                        </div>
                        <label className={`flex items-center justify-between gap-4 rounded-md border px-3 py-3 ${isDark ? "border-slate-700 bg-slate-950/35" : "border-slate-200 bg-white/65"}`}>
                          <span>
                            <span className={`block text-xs font-bold ${headingTxt}`}>在个人主页展示这张背景</span>
                            <span className={`mt-1 block text-xs leading-5 ${mutedTxt}`}>切换后立即保存。关闭时，你和其他用户查看公开主页都会看到 NovelCat 默认背景。</span>
                          </span>
                          <input
                            type="checkbox"
                            checked={showBackgroundOnProfile}
                            onChange={(event) => void handleProfileBackgroundVisibility(event.target.checked)}
                            className="h-4 w-4 shrink-0 accent-orange-500"
                          />
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className={`${isDark ? 'bg-slate-900 border-slate-800' : isSepia ? 'bg-[#fbf7ed] border-amber-200' : 'bg-white border-slate-200'} border rounded-lg p-4`}>
                    <div className="flex items-start space-x-3">
                      <AlertCircle size={18} className={isDark ? 'text-slate-400' : 'text-blue-500'} />
                      <p className={`text-xs ${isDark ? 'text-slate-300' : 'text-blue-700'} leading-relaxed`}>
                        每位用户拥有独立的背景与外观偏好。个人主页是否展示背景由上方隐私开关控制。
                      </p>
                    </div>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </main>
      <ConfirmDialog
        open={Boolean(kbDeleteTarget)}
        title="删除知识库文档"
        description={`确定要删除“${kbDeleteTarget?.title || "这个文档"}”吗？相关知识切片也会一起移除。`}
        confirmLabel="删除"
        tone="danger"
        theme={theme}
        busy={kbDeleting}
        onConfirm={handleKbDelete}
        onCancel={() => setKbDeleteTarget(null)}
      />
    </div>
  );
}
