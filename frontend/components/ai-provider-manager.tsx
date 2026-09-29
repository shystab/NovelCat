"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  KeyRound,
  Loader2,
  Plus,
  Power,
  RefreshCw,
  Save,
  Server,
  Trash2,
  Wifi,
} from "lucide-react";

import { api } from "@/lib/api";
import type { Theme } from "@/hooks/use-theme";
import type {
  AIProviderConfig,
  AIProviderConfigCreate,
  AIProviderConfigUpdate,
  AIProviderKind,
} from "@/types/api";


type Draft = {
  name: string;
  provider: AIProviderKind;
  base_url: string;
  model: string;
};

const PROVIDER_DEFAULTS: Record<AIProviderKind, Draft> = {
  deepseek: {
    name: "DeepSeek",
    provider: "deepseek",
    base_url: "https://api.deepseek.com",
    model: "",
  },
  openai: {
    name: "OpenAI",
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "",
  },
  openai_compatible: {
    name: "自定义服务",
    provider: "openai_compatible",
    base_url: "http://127.0.0.1:11434/v1",
    model: "",
  },
};

function providerLabel(provider: AIProviderKind) {
  if (provider === "deepseek") return "DeepSeek";
  if (provider === "openai") return "OpenAI";
  return "OpenAI 兼容";
}

function readableError(error: unknown) {
  if (!(error instanceof Error)) return "操作失败，请稍后重试";
  try {
    const parsed = JSON.parse(error.message) as { detail?: string | Array<{ msg?: string }> };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item) => item.msg).filter(Boolean).join("；");
  } catch {
    // The API can also return a plain-text error.
  }
  return error.message || "操作失败，请稍后重试";
}

export default function AIProviderManager({ theme }: { theme: Theme }) {
  const [providers, setProviders] = useState<AIProviderConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>({ ...PROVIDER_DEFAULTS.deepseek });
  const [apiKey, setApiKey] = useState("");
  const [clearSavedKey, setClearSavedKey] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "test" | "models" | "activate" | "delete" | null>(null);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [deleteArmed, setDeleteArmed] = useState(false);

  const selected = useMemo(
    () => providers.find((item) => item.id === selectedId) ?? null,
    [providers, selectedId],
  );
  const hasUnsavedChanges = useMemo(() => {
    if (!selected) return selectedId === "new";
    return draft.name.trim() !== selected.name
      || draft.provider !== selected.provider
      || draft.base_url.trim().replace(/\/+$/, "") !== selected.base_url
      || draft.model.trim() !== selected.model
      || Boolean(apiKey.trim())
      || clearSavedKey;
  }, [apiKey, clearSavedKey, draft, selected, selectedId]);

  const isDark = theme === "dark";
  const isSepia = theme === "sepia";
  const surface = isDark
    ? "border-slate-700 bg-slate-900"
    : isSepia
      ? "border-amber-200 bg-[#fbf7ed]"
      : "border-slate-200 bg-white";
  const subtleSurface = isDark
    ? "border-slate-700 bg-slate-950/45"
    : isSepia
      ? "border-amber-200 bg-amber-50/60"
      : "border-slate-200 bg-slate-50/80";
  const heading = isDark ? "text-slate-100" : isSepia ? "text-amber-950" : "text-slate-900";
  const body = isDark ? "text-slate-300" : isSepia ? "text-amber-800" : "text-slate-700";
  const muted = isDark ? "text-slate-400" : isSepia ? "text-amber-700" : "text-slate-500";
  const input = isDark
    ? "border-slate-700 bg-slate-950 text-slate-100 placeholder:text-slate-500 focus:border-orange-500"
    : isSepia
      ? "border-amber-200 bg-white/70 text-amber-950 placeholder:text-amber-700 focus:border-orange-500"
      : "border-slate-300 bg-white text-slate-900 placeholder:text-slate-500 focus:border-orange-500";
  const secondaryButton = isDark
    ? "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
    : isSepia
      ? "border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100"
      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50";

  const applyProvider = (provider: AIProviderConfig) => {
    setDraft({
      name: provider.name,
      provider: provider.provider,
      base_url: provider.base_url,
      model: provider.model,
    });
    setApiKey("");
    setClearSavedKey(false);
    setModels([]);
    setDeleteArmed(false);
  };

  const refreshProviders = async (preferredId?: number | null) => {
    const result = await api.listAIProviders();
    setProviders(result.items);
    const nextId = preferredId
      ?? (typeof selectedId === "number" && result.items.some((item) => item.id === selectedId) ? selectedId : null)
      ?? result.active_id
      ?? result.items[0]?.id
      ?? null;
    setSelectedId(nextId);
    const next = result.items.find((item) => item.id === nextId);
    if (next) applyProvider(next);
    return result;
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const result = await api.listAIProviders();
        if (cancelled) return;
        setProviders(result.items);
        const next = result.items.find((item) => item.id === result.active_id) ?? result.items[0] ?? null;
        setSelectedId(next?.id ?? null);
        if (next) applyProvider(next);
      } catch (error) {
        if (!cancelled) setMessage({ text: readableError(error), ok: false });
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const chooseProvider = (provider: AIProviderConfig) => {
    setSelectedId(provider.id);
    applyProvider(provider);
    setMessage(null);
  };

  const startNew = () => {
    setSelectedId("new");
    setDraft({ ...PROVIDER_DEFAULTS.deepseek });
    setApiKey("");
    setClearSavedKey(false);
    setModels([]);
    setDeleteArmed(false);
    setMessage(null);
  };

  const changeProviderKind = (provider: AIProviderKind) => {
    const defaults = PROVIDER_DEFAULTS[provider];
    setDraft({ ...defaults });
    setModels([]);
    setApiKey("");
    setClearSavedKey(false);
  };

  const validateDraft = () => {
    if (!draft.name.trim()) return "请填写配置名称";
    if (!draft.base_url.trim()) return "请填写 Base URL";
    if (!/^https?:\/\//i.test(draft.base_url.trim())) return "Base URL 必须以 http:// 或 https:// 开头";
    if (!draft.model.trim()) return "请填写模型名称";
    return null;
  };

  const saveProvider = async () => {
    const validation = validateDraft();
    if (validation) {
      setMessage({ text: validation, ok: false });
      return;
    }
    setBusy("save");
    setMessage(null);
    try {
      const base = {
        name: draft.name.trim(),
        provider: draft.provider,
        base_url: draft.base_url.trim().replace(/\/+$/, ""),
        model: draft.model.trim(),
      };
      let saved: AIProviderConfig;
      if (selectedId === "new" || selectedId === null) {
        const payload: AIProviderConfigCreate = {
          ...base,
          api_key: apiKey.trim() || undefined,
          activate: providers.length === 0,
        };
        saved = await api.createAIProvider(payload);
      } else {
        const payload: AIProviderConfigUpdate = { ...base };
        if (clearSavedKey) payload.api_key = "";
        else if (apiKey.trim()) payload.api_key = apiKey.trim();
        saved = await api.updateAIProvider(selectedId, payload);
      }
      await refreshProviders(saved.id);
      setMessage({ text: "服务配置已保存", ok: true });
    } catch (error) {
      setMessage({ text: readableError(error), ok: false });
    } finally {
      setBusy(null);
    }
  };

  const testConnection = async () => {
    if (!selected) {
      setMessage({ text: "请先保存配置，再测试连接", ok: false });
      return;
    }
    if (hasUnsavedChanges) {
      setMessage({ text: "请先保存当前修改，再测试连接", ok: false });
      return;
    }
    setBusy("test");
    setMessage(null);
    try {
      const result = await api.testAIProvider(selected.id);
      await refreshProviders(selected.id);
      setMessage({ text: result.message, ok: result.ok });
    } catch (error) {
      setMessage({ text: readableError(error), ok: false });
    } finally {
      setBusy(null);
    }
  };

  const fetchModels = async () => {
    const baseUrl = draft.base_url.trim().replace(/\/+$/, "");
    if (!baseUrl) {
      setMessage({ text: "请先填写 Base URL", ok: false });
      return;
    }
    if (!/^https?:\/\//i.test(baseUrl)) {
      setMessage({ text: "Base URL 必须以 http:// 或 https:// 开头", ok: false });
      return;
    }
    const canUseSavedKey = Boolean(
      selected?.has_api_key
      && !clearSavedKey
      && selected.provider === draft.provider,
    );
    if (!apiKey.trim() && !canUseSavedKey) {
      setMessage({ text: "请先填写 API Key，再获取模型列表", ok: false });
      return;
    }
    setBusy("models");
    setMessage(null);
    try {
      const result = await api.discoverAIProviderModels({
        config_id: canUseSavedKey ? selected?.id : undefined,
        base_url: baseUrl,
        api_key: apiKey.trim() || undefined,
      });
      setModels(result.items);
      setMessage({
        text: result.items.length ? `已读取 ${result.items.length} 个模型` : "服务商没有返回模型列表，可以继续手动填写",
        ok: true,
      });
    } catch (error) {
      setMessage({ text: `${readableError(error)}。仍可手动填写模型名称。`, ok: false });
    } finally {
      setBusy(null);
    }
  };

  const activateProvider = async () => {
    if (!selected) return;
    if (hasUnsavedChanges) {
      setMessage({ text: "请先保存当前修改，再切换服务", ok: false });
      return;
    }
    setBusy("activate");
    setMessage(null);
    try {
      await api.activateAIProvider(selected.id);
      await refreshProviders(selected.id);
      setMessage({ text: `已切换到“${selected.name}”`, ok: true });
    } catch (error) {
      setMessage({ text: readableError(error), ok: false });
    } finally {
      setBusy(null);
    }
  };

  const deleteProvider = async () => {
    if (!selected) return;
    if (!deleteArmed) {
      setDeleteArmed(true);
      setMessage({ text: "再次点击“确认删除”即可移除这条配置", ok: false });
      return;
    }
    setBusy("delete");
    try {
      await api.deleteAIProvider(selected.id);
      setDeleteArmed(false);
      const result = await refreshProviders(null);
      if (!result.items.length) startNew();
      setMessage({ text: "服务配置已删除", ok: true });
    } catch (error) {
      setMessage({ text: readableError(error), ok: false });
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <section className={`rounded-lg border p-5 ${surface}`} aria-busy="true">
        <div className="flex items-center gap-3">
          <Loader2 size={18} className="animate-spin text-orange-500" />
          <span className={`text-sm ${body}`}>正在读取 AI 服务配置…</span>
        </div>
      </section>
    );
  }

  return (
    <section className={`overflow-hidden rounded-lg border ${surface}`}>
      <div className={`flex flex-col gap-3 border-b px-4 py-4 sm:flex-row sm:items-end sm:justify-between ${isDark ? "border-slate-700" : isSepia ? "border-amber-200" : "border-slate-200"}`}>
        <div>
          <h2 className={`text-lg font-bold ${heading}`}>AI 服务</h2>
          <p className={`mt-1 max-w-2xl text-sm leading-relaxed ${muted}`}>
            保存多个服务并随时切换。密钥只在后端加密保存，不会返回到浏览器。
          </p>
        </div>
        <button
          type="button"
          onClick={startNew}
          className={`inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm font-semibold ${secondaryButton}`}
        >
          <Plus size={15} />
          添加服务
        </button>
      </div>

      <div className="grid min-h-[420px] lg:grid-cols-[250px_minmax(0,1fr)]">
          <div className={`border-b p-3 lg:border-b-0 lg:border-r ${isDark ? "border-slate-700" : isSepia ? "border-amber-200" : "border-slate-200"}`}>
            {providers.length === 0 ? (
              <button
                type="button"
                onClick={startNew}
                className={`flex w-full flex-col items-center justify-center rounded-md border border-dashed px-4 py-8 text-center ${subtleSurface}`}
              >
                <Server size={22} className="mb-3 text-orange-500" />
                <span className={`text-sm font-semibold ${heading}`}>添加第一个 AI 服务</span>
                <span className={`mt-1 text-xs leading-relaxed ${muted}`}>填写 API Key、模型和服务地址后即可使用 AI 对话。</span>
              </button>
            ) : (
              <div className="space-y-1" role="list" aria-label="已保存的 AI 服务">
                {providers.map((provider) => {
                  const isSelected = provider.id === selectedId;
                  return (
                    <button
                      key={provider.id}
                      type="button"
                      onClick={() => chooseProvider(provider)}
                      className={`w-full rounded-md px-3 py-3 text-left transition-colors ${isSelected
                        ? isDark
                          ? "bg-slate-800 text-white"
                          : isSepia
                            ? "bg-amber-100 text-amber-950"
                            : "bg-slate-100 text-slate-950"
                        : `${body} hover:bg-black/5`
                        }`}
                      aria-current={provider.is_active ? "true" : undefined}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-sm font-semibold">{provider.name}</span>
                        {provider.is_active && (
                          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">当前</span>
                        )}
                      </span>
                      <span className={`mt-1 flex items-center gap-1.5 text-xs ${isSelected ? "opacity-75" : muted}`}>
                        {provider.last_test_status === "success" ? (
                          <CheckCircle2 size={12} className="text-emerald-500" />
                        ) : provider.last_test_status === "failed" ? (
                          <AlertCircle size={12} className="text-red-500" />
                        ) : (
                          <Circle size={10} className="text-slate-400" />
                        )}
                        <span className="truncate">{provider.model}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="p-4 sm:p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5">
                <span className={`text-xs font-semibold ${body}`}>配置名称</span>
                <input
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  className={`h-10 w-full rounded-md border px-3 text-sm outline-none ${input}`}
                  placeholder="例如：写作主力"
                />
              </label>
              <label className="space-y-1.5">
                <span className={`text-xs font-semibold ${body}`}>服务类型</span>
                <select
                  value={draft.provider}
                  onChange={(event) => changeProviderKind(event.target.value as AIProviderKind)}
                  className={`h-10 w-full rounded-md border px-3 text-sm outline-none ${input}`}
                >
                  <option value="deepseek">DeepSeek</option>
                  <option value="openai">OpenAI</option>
                  <option value="openai_compatible">OpenAI 兼容服务</option>
                </select>
              </label>

              <label className="space-y-1.5 sm:col-span-2">
                <span className={`text-xs font-semibold ${body}`}>Base URL</span>
                <input
                  value={draft.base_url}
                  onChange={(event) => setDraft((current) => ({ ...current, base_url: event.target.value }))}
                  className={`h-10 w-full rounded-md border px-3 font-mono text-sm outline-none ${input}`}
                  placeholder="https://api.example.com/v1"
                  spellCheck={false}
                />
              </label>

              <label className="space-y-1.5 sm:col-span-2">
                <span className="flex items-center justify-between gap-3">
                  <span className={`text-xs font-semibold ${body}`}>模型</span>
                  <button
                    type="button"
                    onClick={fetchModels}
                    disabled={busy !== null}
                    className={`inline-flex items-center gap-1 text-xs font-semibold text-orange-600 hover:text-orange-700 disabled:cursor-not-allowed disabled:opacity-45`}
                  >
                    {busy === "models" ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    获取模型列表
                  </button>
                </span>
                <input
                  value={draft.model}
                  onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))}
                  className={`h-10 w-full rounded-md border px-3 font-mono text-sm outline-none ${input}`}
                  placeholder="手动输入模型名称"
                  spellCheck={false}
                />
                {models.length > 0 && (
                  <div className={`rounded-md border p-3 ${subtleSurface}`}>
                    <label htmlFor="available-ai-models" className={`flex items-center justify-between gap-3 text-xs font-semibold ${body}`}>
                      <span>服务商返回的模型</span>
                      <span className={`font-normal ${muted}`}>{models.length} 个可选</span>
                    </label>
                    <select
                      id="available-ai-models"
                      value={models.includes(draft.model) ? draft.model : ""}
                      onChange={(event) => {
                        if (event.target.value) {
                          setDraft((current) => ({ ...current, model: event.target.value }));
                        }
                      }}
                      className={`mt-2 h-10 w-full rounded-md border px-3 font-mono text-sm outline-none ${input}`}
                    >
                      <option value="">选择一个模型…</option>
                      {models.map((model) => <option key={model} value={model}>{model}</option>)}
                    </select>
                    {!models.includes(draft.model) && (
                      <p className="mt-2 text-xs leading-relaxed text-amber-700">
                        当前填写的“{draft.model}”不在返回列表中。选择新模型后请保存配置。
                      </p>
                    )}
                  </div>
                )}
              </label>

              <div className="space-y-1.5 sm:col-span-2">
                <div className="flex items-center justify-between gap-3">
                  <label htmlFor="ai-provider-key" className={`text-xs font-semibold ${body}`}>API Key</label>
                  {selected?.has_api_key && (
                    <span className={`text-xs ${muted}`}>
                      {selected.key_source === "environment"
                        ? "来自服务器环境变量"
                        : selected.api_key_hint
                          ? `已保存，末尾 ${selected.api_key_hint}`
                          : "已加密保存"}
                    </span>
                  )}
                </div>
                <div className="relative">
                  <KeyRound size={15} className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 ${muted}`} />
                  <input
                    id="ai-provider-key"
                    type="password"
                    value={apiKey}
                    onChange={(event) => {
                      setApiKey(event.target.value);
                      if (event.target.value) setClearSavedKey(false);
                    }}
                    disabled={clearSavedKey}
                    className={`h-10 w-full rounded-md border py-2 pl-9 pr-3 font-mono text-sm outline-none disabled:opacity-50 ${input}`}
                    placeholder={selected?.has_api_key ? "留空表示不更换" : "填写服务商提供的 API Key"}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
                {selected?.key_source === "stored" && (
                  <label className={`inline-flex cursor-pointer items-center gap-2 text-xs ${muted}`}>
                    <input
                      type="checkbox"
                      checked={clearSavedKey}
                      onChange={(event) => {
                        setClearSavedKey(event.target.checked);
                        if (event.target.checked) setApiKey("");
                      }}
                      className="accent-orange-600"
                    />
                    保存时删除已有密钥
                  </label>
                )}
              </div>
            </div>

            {message && (
              <div
                className={`mt-4 flex items-start gap-2 rounded-md border px-3 py-2.5 text-xs leading-relaxed ${message.ok
                  ? isDark ? "border-emerald-900 bg-emerald-950/30 text-emerald-300" : "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : isDark ? "border-red-900 bg-red-950/30 text-red-300" : "border-red-200 bg-red-50 text-red-700"
                  }`}
                role="status"
              >
                {message.ok ? <CheckCircle2 size={15} className="mt-0.5 shrink-0" /> : <AlertCircle size={15} className="mt-0.5 shrink-0" />}
                <span>{message.text}</span>
              </div>
            )}

            {selected?.last_test_message && !message && (
              <p className={`mt-4 text-xs leading-relaxed ${selected.last_test_status === "failed" ? "text-red-600" : muted}`}>
                上次检测：{selected.last_test_message}
              </p>
            )}

            <div className={`mt-5 flex flex-wrap items-center gap-2 border-t pt-4 ${isDark ? "border-slate-800" : isSepia ? "border-amber-200" : "border-slate-100"}`}>
              <button
                type="button"
                onClick={saveProvider}
                disabled={busy !== null}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-100 dark:text-slate-950"
              >
                {busy === "save" ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                保存配置
              </button>
              <button
                type="button"
                onClick={testConnection}
                disabled={busy !== null || !selected}
                className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${secondaryButton}`}
              >
                {busy === "test" ? <Loader2 size={15} className="animate-spin" /> : <Wifi size={15} />}
                测试连接
              </button>
              {selected && !selected.is_active && (
                <button
                  type="button"
                  onClick={activateProvider}
                  disabled={busy !== null}
                  className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold disabled:opacity-45 ${secondaryButton}`}
                >
                  {busy === "activate" ? <Loader2 size={15} className="animate-spin" /> : <Power size={15} />}
                  设为当前服务
                </button>
              )}
              {selected && (
                <button
                  type="button"
                  onClick={deleteProvider}
                  disabled={busy !== null}
                  className={`ml-auto inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold disabled:opacity-45 ${deleteArmed
                    ? "border-red-600 bg-red-600 text-white hover:bg-red-700"
                    : isDark ? "border-slate-700 text-red-400 hover:bg-red-950/30" : "border-slate-300 text-red-600 hover:bg-red-50"
                    }`}
                >
                  {busy === "delete" ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                  {deleteArmed ? "确认删除" : "删除配置"}
                </button>
              )}
            </div>

            <p className={`mt-3 text-xs leading-relaxed ${muted}`}>
              {providerLabel(draft.provider)} 使用 OpenAI 兼容接口。获取模型列表失败时，不影响手动填写模型名称。
            </p>
          </div>
      </div>
    </section>
  );
}
