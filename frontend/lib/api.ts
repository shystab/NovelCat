import {
  Chapter,
  ChapterCreate,
  ChapterUpdate,
  ChapterRevision,
  Book,
  BookCreate,
  BookUpdate,
  Conversation,
  ConversationCreate,
  ConversationUpdate,
  AgentEditPlan,
  AgentEditRequest,
  Settings,
  SettingsUpdate,
  KnowledgeBase,
  KnowledgeHealth,
  KnowledgeReindexResult,
  Persona,
  PersonaCreate,
  PersonaUpdate,
  AuthResponse,
  AuthUser,
  AdminUserUpdate,
  DirectMessage,
  InviteCode,
  ShowcaseCard,
  ShowcaseCardCreate,
  ShowcaseCardUpdate,
  UserProfile,
  UserProfileUpdate,
  WritingPreset,
  WritingPresetListResponse,
  AIProviderConfig,
  AIProviderConfigCreate,
  AIProviderConfigList,
  AIProviderConfigUpdate,
  AIProviderModelDiscoveryRequest,
  AIProviderModelList,
  AIProviderTestResult,
} from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const ACCESS_TOKEN = process.env.NEXT_PUBLIC_APP_ACCESS_TOKEN || "";

const USER_ID = "default_user";
const PROJECT_ID = "default_project";
const AUTH_TOKEN_KEY = "chatnovel-auth-token";
const AUTH_USER_KEY = "chatnovel-auth-user";

function getAuthToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function setAuthSession(auth: AuthResponse) {
  if (typeof window === "undefined") return;
  localStorage.setItem(AUTH_TOKEN_KEY, auth.access_token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(auth.user));
}

export function setStoredUser(user: AuthUser) {
  if (typeof window === "undefined") return;
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function clearAuthSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function withAccessToken(url: string) {
  const parsed = new URL(url, window.location.origin);
  if (ACCESS_TOKEN) parsed.searchParams.set("access_token", ACCESS_TOKEN);
  const authToken = getAuthToken();
  if (authToken) parsed.searchParams.set("auth_token", authToken);
  return parsed.toString();
}

function assetUrl(url: string, version?: string | number | null) {
  const parsed = new URL(url, typeof window === "undefined" ? "http://localhost" : window.location.origin);
  if (version !== undefined && version !== null && version !== "") {
    parsed.searchParams.set("v", String(version));
  }
  return withAccessToken(parsed.toString());
}

export function authHeaders(headers?: HeadersInit): HeadersInit {
  const authToken = getAuthToken();
  return {
    ...(headers || {}),
    ...(ACCESS_TOKEN ? { "X-App-Token": ACCESS_TOKEN } : {}),
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };
}

async function req<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: authHeaders(init?.headers),
  });
  if (!res.ok) {
    const inputText = typeof input === "string" ? input : input.toString();
    const isAuthEndpoint = inputText.includes("/auth/login") || inputText.includes("/auth/register");
    if (res.status === 401 && !isAuthEndpoint && typeof window !== "undefined") {
      clearAuthSession();
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.href = `/login?next=${encodeURIComponent(next)}`;
    }
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

function filenameFromDisposition(value: string | null, fallback: string) {
  if (!value) return fallback;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const asciiMatch = value.match(/filename="?([^";]+)"?/);
  return asciiMatch?.[1] || fallback;
}

export const api = {
  // ── Books ──────────────────────────────────────
  login: async (username: string, password: string) => {
    const auth = await req<AuthResponse>(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    setAuthSession(auth);
    return auth;
  },
  register: async (username: string, password: string, inviteCode?: string) => {
    const auth = await req<AuthResponse>(`${BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, invite_code: inviteCode || null }),
    });
    setAuthSession(auth);
    return auth;
  },
  me: () => req<AuthUser>(`${BASE}/auth/me`),
  logout: () => clearAuthSession(),
  createInvite: (maxUses: number = 1, expiresDays: number | null = 14) =>
    req<InviteCode>(`${BASE}/auth/invites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_uses: maxUses, expires_days: expiresDays }),
    }),
  listInvites: () => req<InviteCode[]>(`${BASE}/auth/invites`),
  listAdminUsers: () => req<UserProfile[]>(`${BASE}/admin/users`),
  updateAdminUser: (username: string, data: AdminUserUpdate) =>
    req<UserProfile>(`${BASE}/admin/users/${encodeURIComponent(username)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  uploadLoginCover: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<{ updated: boolean; filename: string }>(`${BASE}/admin/login-cover`, {
      method: "POST",
      body: form,
    });
  },
  clearLoginCover: () => req<void>(`${BASE}/admin/login-cover`, { method: "DELETE" }),
  loginCoverUrl: (version?: string | number | null) =>
    assetUrl(`${BASE}/admin/login-cover`, version),
  listUsers: () => req<UserProfile[]>(`${BASE}/users/`),
  getMyProfile: () => req<UserProfile>(`${BASE}/users/me`),
  updateMyProfile: (profile: UserProfileUpdate) =>
    req<UserProfile>(`${BASE}/users/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }),
  uploadMyAvatar: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<UserProfile>(`${BASE}/users/me/avatar`, {
      method: "POST",
      body: form,
    });
  },
  deleteMyAvatar: () =>
    req<UserProfile>(`${BASE}/users/me/avatar`, { method: "DELETE" }),
  getUserProfile: (username: string) =>
    req<UserProfile>(`${BASE}/users/${encodeURIComponent(username)}/profile`),
  listUserShowcases: (username: string) =>
    req<ShowcaseCard[]>(`${BASE}/users/${encodeURIComponent(username)}/showcases`),
  listMyShowcases: () => req<ShowcaseCard[]>(`${BASE}/users/showcases/me`),
  createShowcase: (data: ShowcaseCardCreate) =>
    req<ShowcaseCard>(`${BASE}/users/showcases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateShowcase: (id: number, data: ShowcaseCardUpdate) =>
    req<ShowcaseCard>(`${BASE}/users/showcases/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteShowcase: (id: number) =>
    req<void>(`${BASE}/users/showcases/${id}`, { method: "DELETE" }),
  uploadShowcaseCover: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<ShowcaseCard>(`${BASE}/users/showcases/${id}/cover`, {
      method: "POST",
      body: form,
    });
  },
  avatarUrl: (username: string, version?: string | number | null) =>
    assetUrl(`${BASE}/users/${encodeURIComponent(username)}/avatar`, version),
  userBackgroundUrl: (username: string, version?: string | number | null) =>
    assetUrl(`${BASE}/users/${encodeURIComponent(username)}/background`, version),
  showcaseCoverUrl: (id: number, version?: string | number | null) =>
    assetUrl(`${BASE}/users/showcases/${id}/cover`, version),
  listDirectMessages: (withUser: string, limit: number = 80) =>
    req<DirectMessage[]>(
      `${BASE}/users/messages?with_user=${encodeURIComponent(withUser)}&limit=${limit}`
    ),
  sendDirectMessage: (toUser: string, content: string) =>
    req<DirectMessage>(`${BASE}/users/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_user: toUser, content }),
    }),

  // ── Books ──────────────────────────────────────
  listBooks: () => req<Book[]>(`${BASE}/books/`),
  getBook: (id: number) => req<Book>(`${BASE}/books/${id}`),
  createBook: (book: BookCreate) =>
    req<Book>(`${BASE}/books/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(book),
    }),
  updateBook: (id: number, book: BookUpdate) =>
    req<Book>(`${BASE}/books/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(book),
    }),
  deleteBook: (id: number) =>
    req<void>(`${BASE}/books/${id}`, { method: "DELETE" }),

  // ── Chapters (书籍作用域) ───────────────────────
  listChapters: (bookId: number) =>
    req<Chapter[]>(`${BASE}/books/${bookId}/chapters/`),
  getChapterInBook: (bookId: number, chapterId: number) =>
    req<Chapter>(`${BASE}/books/${bookId}/chapters/${chapterId}`),
  createChapterInBook: (bookId: number, chapter: ChapterCreate) =>
    req<Chapter>(`${BASE}/books/${bookId}/chapters/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chapter),
    }),
  updateChapterInBook: (bookId: number, chapterId: number, chapter: ChapterUpdate) =>
    req<Chapter>(`${BASE}/books/${bookId}/chapters/${chapterId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chapter),
    }),
  deleteChapterInBook: (bookId: number, chapterId: number) =>
    req<void>(`${BASE}/books/${bookId}/chapters/${chapterId}`, { method: "DELETE" }),
  reorderChapters: (bookId: number, chapterIds: number[]) =>
    req<{ reordered: number }>(`${BASE}/books/${bookId}/chapters/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter_ids: chapterIds }),
    }),
  listChapterRevisions: (bookId: number, chapterId: number) =>
    req<ChapterRevision[]>(`${BASE}/books/${bookId}/chapters/${chapterId}/revisions`),
  restoreChapterRevision: (bookId: number, chapterId: number, revisionId: number) =>
    req<Chapter>(`${BASE}/books/${bookId}/chapters/${chapterId}/revisions/${revisionId}/restore`, {
      method: "POST",
    }),

  // ── Chapters (旧接口，向后兼容) ────────────────
  getChapters: () => req<Chapter[]>(`${BASE}/chapters/`),
  getChapter: (id: number) => req<Chapter>(`${BASE}/chapters/${id}`),
  createChapter: (chapter: ChapterCreate) =>
    req<Chapter>(`${BASE}/chapters/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chapter),
    }),
  updateChapter: (id: number, chapter: ChapterUpdate) =>
    req<Chapter>(`${BASE}/chapters/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chapter),
    }),
  deleteChapter: (id: number) =>
    req<void>(`${BASE}/chapters/${id}`, { method: "DELETE" }),

  // ── Conversations ──────────────────────────────
  listConversations: (bookId?: number | null, includeArchived = false) => {
    const params = new URLSearchParams();
    if (bookId) params.set("book_id", String(bookId));
    if (includeArchived) params.set("include_archived", "true");
    const query = params.toString();
    return req<Conversation[]>(`${BASE}/conversations/${query ? `?${query}` : ""}`);
  },
  getConversation: (id: number) => req<Conversation>(`${BASE}/conversations/${id}`),
  createConversation: (data: ConversationCreate) =>
    req<Conversation>(`${BASE}/conversations/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateConversation: (id: number, data: ConversationUpdate) =>
    req<Conversation>(`${BASE}/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteConversation: (id: number) =>
    req<void>(`${BASE}/conversations/${id}`, { method: "DELETE" }),
  cleanupEmptyConversations: () =>
    req<{ deleted_count: number; deleted_ids: number[] }>(`${BASE}/conversations/empty`, { method: "DELETE" }),
  updateConversationDocs: (id: number, docIds: number[]) =>
    req<Conversation>(`${BASE}/conversations/${id}/docs`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(docIds),
    }),

  // ── Export ────────────────────────────────────
  exportTxt: () => { window.location.href = withAccessToken(`${BASE}/chapters/export/txt`); },
  exportDocx: () => { window.location.href = withAccessToken(`${BASE}/chapters/export/docx`); },

  // ── Workspace ─────────────────────────────────
  syncWorkspaceLibrary: () =>
    req<{ workspace: string; readme: string; manifest: string; book_count: number; chapter_count: number }>(
      `${BASE}/books/workspace/sync`,
      { method: "POST" }
    ),
  scanWorkspaceLibrary: () =>
    req<{ workspace: string; book_count: number; chapter_count: number; char_count: number }>(
      `${BASE}/books/workspace/scan`
    ),
  importWorkspaceLibrary: () =>
    req<{
      workspace: string;
      book_count: number;
      chapter_count: number;
      created_books: number;
      updated_books: number;
      created_chapters: number;
      updated_chapters: number;
    }>(`${BASE}/books/workspace/import`, { method: "POST" }),
  backupWorkspaceLibrary: async () => {
    const res = await fetch(`${BASE}/books/workspace/backup`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(text || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const filename = filenameFromDisposition(
      res.headers.get("Content-Disposition"),
      `VibeWriter-backup-${new Date().toISOString().slice(0, 10)}.zip`
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return filename;
  },

  // ── Settings ──────────────────────────────────
  getSettings: () => req<Settings>(`${BASE}/settings/`),
  updateSettings: (s: SettingsUpdate) =>
    req<Settings>(`${BASE}/settings/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(s),
    }),
  uploadBackgroundImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<Settings>(`${BASE}/settings/background`, {
      method: "POST",
      body: form,
    });
  },
  clearBackgroundImage: () =>
    req<Settings>(`${BASE}/settings/background`, { method: "DELETE" }),

  // ── AI Agent ──────────────────────────────────
  getAiHealth: () =>
    req<{
      provider: string;
      profile_id?: number | null;
      profile_name?: string;
      configured: boolean;
      verified?: boolean;
      status?: string;
      model: string;
      base_url: string;
      key_source?: string;
    }>(`${BASE}/ai/health`),

  listAIProviders: () =>
    req<AIProviderConfigList>(`${BASE}/ai/providers/`),
  createAIProvider: (data: AIProviderConfigCreate) =>
    req<AIProviderConfig>(`${BASE}/ai/providers/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateAIProvider: (id: number, data: AIProviderConfigUpdate) =>
    req<AIProviderConfig>(`${BASE}/ai/providers/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteAIProvider: (id: number) =>
    req<void>(`${BASE}/ai/providers/${id}`, { method: "DELETE" }),
  activateAIProvider: (id: number) =>
    req<AIProviderConfig>(`${BASE}/ai/providers/${id}/activate`, { method: "POST" }),
  testAIProvider: (id: number) =>
    req<AIProviderTestResult>(`${BASE}/ai/providers/${id}/test`, { method: "POST" }),
  listAIProviderModels: (id: number) =>
    req<AIProviderModelList>(`${BASE}/ai/providers/${id}/models`),
  discoverAIProviderModels: (data: AIProviderModelDiscoveryRequest) =>
    req<AIProviderModelList>(`${BASE}/ai/providers/discover-models`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  listWritingPresets: () =>
    req<WritingPresetListResponse>(`${BASE}/presets/`),

  toggleWritingPreset: (id: number) =>
    req<WritingPreset>(`${BASE}/presets/${id}/toggle`, { method: "PATCH" }),

  createAgentEditPlan: (data: AgentEditRequest) =>
    req<AgentEditPlan>(`${BASE}/ai/agent/edit-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // ── Knowledge Base ────────────────────────────
  getKnowledgeBases: () =>
    req<{items: KnowledgeBase[], total: number}>(`${BASE}/knowledge/documents?user_id=${USER_ID}&project_id=${PROJECT_ID}`)
      .then(res => res.items),
  getKnowledgeHealth: () =>
    req<KnowledgeHealth>(`${BASE}/knowledge/health`),
  reindexKnowledge: () =>
    req<KnowledgeReindexResult>(`${BASE}/knowledge/reindex?project_id=${PROJECT_ID}`, { method: "POST" }),

  uploadKnowledgeBase: async (file: File) => {
    const text = await file.text();
    return req<{document_id: number, chunks: number}>(`${BASE}/knowledge/upload/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: USER_ID,
        project_id: PROJECT_ID,
        title: file.name,
        text: text
      }),
    });
  },

  deleteKnowledgeBase: (id: number) =>
    req<void>(`${BASE}/knowledge/documents/${id}`, { method: "DELETE" }),

  searchKnowledge: (query: string, topK: number = 5) =>
    req<{results: Array<{text: string, score: number}>}>(`${BASE}/knowledge/search?user_id=${USER_ID}&project_id=${PROJECT_ID}&q=${encodeURIComponent(query)}&top_k=${topK}`),

  // ── Persona (人格预设) ─────────────────────────
  listPersonas: () =>
    req<Persona[]>(`${BASE}/memory/presets?user_id=${USER_ID}&project_id=${PROJECT_ID}`),

  createPersona: (data: PersonaCreate) =>
    req<Persona>(`${BASE}/memory/presets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  updatePersona: (id: number, data: PersonaUpdate) =>
    req<Persona>(`${BASE}/memory/presets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  enablePersona: (id: number) =>
    req<Persona>(
      `${BASE}/memory/presets/${id}/enable?user_id=${USER_ID}&project_id=${PROJECT_ID}`,
      { method: "POST" }
    ),

  disableAllPersonas: () =>
    req<void>(
      `${BASE}/memory/presets/disable-all?user_id=${USER_ID}&project_id=${PROJECT_ID}`,
      { method: "POST" }
    ),

  deletePersona: (id: number) =>
    req<void>(`${BASE}/memory/presets/${id}?user_id=${USER_ID}`, { method: "DELETE" }),

  getEnabledPersona: () =>
    req<Persona | null>(`${BASE}/memory/preset?user_id=${USER_ID}&project_id=${PROJECT_ID}`),
};
