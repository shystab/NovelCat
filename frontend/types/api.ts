// ── 书籍 ──────────────────────────────────────────
export interface Book {
  id: number;
  title: string;
  description?: string;
  user_id: string;
  cover_url?: string;
  chapter_count: number;
  create_time: string;
  update_time: string;
}

export interface BookCreate {
  title: string;
  description?: string;
  user_id?: string;
  cover_url?: string;
}

export interface BookUpdate {
  title?: string;
  description?: string;
  cover_url?: string;
}

// ── 章节 ──────────────────────────────────────────
export interface Chapter {
  id: number;
  title: string;
  content: string;
  summary?: string;
  order: number;
  kind?: "outline" | "prose" | "note" | "reference";
  book_id?: number;
  create_time: string;
  update_time: string;
}

export interface ChapterCreate {
  title: string;
  content: string;
  order?: number;
  kind?: "outline" | "prose" | "note" | "reference";
}

export interface ChapterUpdate {
  title?: string;
  content?: string;
  order?: number;
  kind?: "outline" | "prose" | "note" | "reference";
}

export interface ChapterRevision {
  id: number;
  chapter_id: number;
  book_id: number;
  title: string;
  content: string;
  created_at: string;
}

// ── 对话 ──────────────────────────────────────────
export interface ConversationMessage {
  role: string;
  content: string;
  meta?: Record<string, unknown>;
}

export interface Conversation {
  id: number;
  user_id: string;
  book_id?: number | null;
  title: string;
  messages: ConversationMessage[];
  selected_doc_ids: number[];
  archived: boolean;
  token_estimate: number;
  create_time: string;
  update_time: string;
}

export interface ConversationCreate {
  title?: string;
  user_id?: string;
  book_id?: number | null;
  messages?: ConversationMessage[];
}

export interface ConversationUpdate {
  title?: string;
  messages?: ConversationMessage[];
  selected_doc_ids?: number[];
  book_id?: number | null;
  archived?: boolean;
  token_estimate?: number;
}

// ── Auth ────────────────────────────────────────
export interface AuthUser {
  username: string;
  display_name?: string | null;
  bio?: string | null;
  current_work?: string | null;
  avatar_color?: string;
  avatar_image_path?: string | null;
  show_background_on_profile?: boolean;
  is_admin: boolean;
}

export interface UserProfile {
  username: string;
  display_name?: string | null;
  bio?: string | null;
  current_work?: string | null;
  avatar_color: string;
  avatar_image_path?: string | null;
  show_background_on_profile: boolean;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface UserProfileUpdate {
  display_name?: string | null;
  bio?: string | null;
  current_work?: string | null;
  avatar_color?: string | null;
  show_background_on_profile?: boolean;
}

export interface AdminUserUpdate {
  is_admin?: boolean;
  is_active?: boolean;
}

export interface DirectMessage {
  id: number;
  sender_username: string;
  recipient_username: string;
  content: string;
  created_at: string;
  read_at?: string | null;
}

export interface ShowcaseCard {
  id: number;
  user_id: string;
  title: string;
  subtitle?: string | null;
  excerpt: string;
  content: string;
  cover_image_path?: string | null;
  is_public: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ShowcaseCardCreate {
  title: string;
  subtitle?: string | null;
  excerpt?: string | null;
  content?: string | null;
  is_public?: boolean;
  sort_order?: number;
}

export interface ShowcaseCardUpdate {
  title?: string | null;
  subtitle?: string | null;
  excerpt?: string | null;
  content?: string | null;
  is_public?: boolean;
  sort_order?: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface InviteCode {
  code: string;
  max_uses: number;
  uses: number;
  is_active: boolean;
  created_at: string;
  expires_at?: string | null;
}

// ── AI 章节上下文 ──────────────────────────────────
export interface ChapterContextItem {
  chapter_id: number;
  title: string;
  content: string;
}

export interface AISuggestRequest {
  content: string;
  max_length?: number;
  user_id?: string;
  project_id?: string;
  use_rag?: boolean;
  use_memory?: boolean;
}

export interface AISuggestResponse {
  suggestion: string;
  reason: string;
}

export type AgentEditAction =
  | "append"
  | "prepend"
  | "replace_all"
  | "insert_before"
  | "insert_after"
  | "replace_text";

export interface AgentEditOperation {
  action: AgentEditAction;
  content: string;
  anchor?: string | null;
  find_text?: string | null;
  reason?: string | null;
}

export interface AgentEditPlan {
  reply?: string;
  summary: string;
  risk: "low" | "medium" | "high";
  operations: AgentEditOperation[];
}

export interface AgentEditRequest {
  instruction: string;
  messages?: Array<{ role: string; content: string }>;
  user_id?: string;
  project_id?: string;
  current_chapter_id?: number | null;
  book_id?: number | null;
  selected_doc_ids?: number[];
  content?: string;
  use_memory?: boolean;
}

export interface Settings {
  id: number;
  theme: string;
  font_size: number;
  auto_save_interval: number;
  language: string;
  editor_mode: string;
  has_deepseek_key: boolean;
  has_openai_key: boolean;
  ai_provider: string;
  temperature?: number;
  max_tokens?: number;
  summary_auto_generate: boolean;
  summary_generation_style: string;
  workspace_dir: string;
  background_image_path?: string | null;
  background_blur: number;
  background_dim: number;
  editor_paper_opacity: number;
  // 分层记忆
  current_chapter_chars?: number;
  nearby_chapter_count?: number;
  inject_nearby_summaries?: boolean;
  inject_chapter_rag?: boolean;
  // 检索行为：external 是外部语料 RAG，chapter 是内部全书检索
  suggest_use_external_rag?: boolean;
  chat_use_chapter_rag?: boolean;
  external_rag_weight?: number;
}

export interface SettingsUpdate {
  theme?: string;
  font_size?: number;
  auto_save_interval?: number;
  language?: string;
  editor_mode?: string;
  deepseek_api_key?: string;
  openai_api_key?: string;
  ai_provider?: string;
  temperature?: number;
  max_tokens?: number;
  summary_auto_generate?: boolean;
  summary_generation_style?: string;
  workspace_dir?: string;
  background_image_path?: string | null;
  background_blur?: number;
  background_dim?: number;
  editor_paper_opacity?: number;
  // 分层记忆
  current_chapter_chars?: number;
  nearby_chapter_count?: number;
  inject_nearby_summaries?: boolean;
  inject_chapter_rag?: boolean;
  // 检索行为：external 是外部语料 RAG，chapter 是内部全书检索
  suggest_use_external_rag?: boolean;
  chat_use_chapter_rag?: boolean;
  external_rag_weight?: number;
}

export interface EditorAppearance {
  background_image_path?: string | null;
  background_blur: number;
  background_dim: number;
  editor_paper_opacity: number;
  font_size?: number;
  background_url?: string;
}

export type AIProviderKind = "deepseek" | "openai" | "openai_compatible";
export type AIProviderTestStatus = "untested" | "success" | "failed";

export interface AIProviderConfig {
  id: number;
  name: string;
  provider: AIProviderKind;
  base_url: string;
  model: string;
  is_active: boolean;
  has_api_key: boolean;
  api_key_hint?: string | null;
  key_source: "stored" | "environment" | "missing";
  last_test_status: AIProviderTestStatus;
  last_test_message?: string | null;
  last_tested_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIProviderConfigList {
  items: AIProviderConfig[];
  active_id?: number | null;
}

export interface AIProviderConfigCreate {
  name: string;
  provider: AIProviderKind;
  base_url: string;
  model: string;
  api_key?: string;
  activate?: boolean;
}

export interface AIProviderConfigUpdate {
  name?: string;
  provider?: AIProviderKind;
  base_url?: string;
  model?: string;
  api_key?: string;
}

export interface AIProviderTestResult {
  ok: boolean;
  message: string;
  model_count: number;
  tested_at: string;
}

export interface AIProviderModelList {
  items: string[];
  selected_model: string;
}

export interface AIProviderModelDiscoveryRequest {
  config_id?: number;
  base_url: string;
  api_key?: string;
}

export interface AIWSRequest {
  draft_reference?: { label: string; text: string; scope: "whole" | "opening_two" | "last_paragraph" };
  type: "suggest" | "chat";
  task?: string;
  content?: string;
  messages?: Array<{ role: string; content: string }>;
  max_length?: number;
  analysis_enabled?: boolean;
  analysis_interval_chars?: number;
  analysis_types?: string[];
  user_id?: string;
  project_id?: string;
  use_rag?: boolean;
  use_memory?: boolean;
  detailed_analysis?: boolean;
  use_layered_memory?: boolean;
  use_external_rag?: boolean;
  use_chapter_rag?: boolean;
  external_rag_weight?: number;
  current_chapter_id?: number;
  conversation_id?: number;
  selected_doc_ids?: number[];
  preset_id?: number;
  book_id?: number;
  chapter_contexts?: ChapterContextItem[];
}

export interface KnowledgeBase {
  id: number;
  title: string;
  user_id: string;
  project_id: string;
  created_at: string | null;
  chunk_count: number;
}

export interface KnowledgeHealth {
  enabled: boolean;
  vector_ready: boolean;
  model: string;
  persist_dir: string;
  local_files_only: boolean;
  device: string;
  retrieval_mode: "vector";
  user_id: string;
}

export interface KnowledgeReindexResult {
  documents: number;
  vectorized_chunks: number;
  vector_ready: boolean;
  retrieval_mode: "vector";
}

export interface AIAgentStep {
  id: string;
  phase: "context" | "planning" | "tool" | "generating";
  status: "running" | "completed" | "failed";
  title: string;
  detail?: string;
  query?: string;
  args?: Record<string, string | number | boolean>;
  elapsed_ms?: number;
  content?: string;
}

export type AIWSMessage =
  | { type: "token"; text: string }
  | { type: "analysis"; data: unknown }
  | { type: "agent_step"; step: AIAgentStep }
  | { type: "done" }
  | { type: "error"; message: string };

// ── 人格预设 ─────────────────────────────────────
export interface Persona {
  id: number;
  name: string;
  system_prompt: string;
  enabled: boolean;
  user_id: string;
  project_id: string;
  created_at: string;
  updated_at: string;
}

export interface PersonaCreate {
  name: string;
  system_prompt: string;
  enabled?: boolean;
  user_id: string;
  project_id: string;
}

export interface PersonaUpdate {
  name?: string;
  system_prompt?: string;
  enabled?: boolean;
}

// 设置页与 AI 面板使用的全局写作人格。
export interface WritingPreset {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WritingPresetListResponse {
  items: WritingPreset[];
  total: number;
}
