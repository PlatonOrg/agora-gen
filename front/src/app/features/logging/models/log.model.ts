export interface PromptEntry {
  id: string;
  name: string;
  content: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface LlmCallRecord {
  call_type: string;
  provider: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  system_prompt_chars: number | null;
  user_prompt_chars: number | null;
}

export interface ConversationSummary {
  conversation_id: string;
  session_id: string | null;
  username: string | null;
  exo_generation_count: number;
  discussion_generation_count: number;
  total_generation_count: number;
  started_at: string | null;
  last_at: string | null;
}

export interface SessionSummary {
  session_id: string;
  exo_generation_count: number;
  discussion_generation_count: number;
  total_generation_count: number;
  started_at: string | null;
  last_at: string | null;
}

export interface RagSearchResult {
  rank: number;
  platon_id: string | null;
  resource_name: string | null;
  kind: string | null;
  score: number | null;
}

export interface RagSearchInfo {
  query: string;
  embedding_model: string;
  vector_table: string;
  created_at: string | null;
  results: RagSearchResult[];
}

export interface DocChunkResult {
  rank: number;
  chunk_text: string | null;
  source_path: string | null;
  score: number | null;
}

export interface DocRagSearchInfo {
  query: string;
  embedding_model: string;
  vector_table: string;
  created_at: string | null;
  chunks: DocChunkResult[];
}

export interface FileSummaryEntry {
  file_id?: string;
  filename: string;
  text_excerpt: string | null;
  summary: string | null;
}

export interface ExoRequestInfo {
  id: string;
  user_request: string;
  session_id: string | null;
  fields_to_modify: string[] | null;
  variables: Record<string, unknown> | null;
  file_names: string[] | null;
  file_summaries: FileSummaryEntry[] | null;
  conversation_history: unknown[] | null;
  current_exercise_state: Record<string, unknown> | null;
  components: string[];
  created_at: string | null;
}

export interface LlmResultInfo {
  system_prompt_name: string;
  system_prompt_content: string | null;
  examples_used: unknown[] | null;
  llm_output: Record<string, unknown> | null;
  llm_provider: string;
  llm_model: string;
  preview_url: string | null;
  retry_count: number | null;
  retry_errors: string[] | null;
  created_at: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  llm_request_count: number | null;
  llm_calls: LlmCallRecord[] | null;
}

export interface ComponentSelectionInfo {
  user_priority_tags: string[];
  selected_tags: string[];
  llm_provider: string;
  llm_model: string;
  reasoning: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string | null;
}

export interface DiscussionRequestInfo {
  id: string;
  user_request: string;
  session_id: string | null;
  created_at: string | null;
}

export interface DiscussionLlmResultInfo {
  system_prompt_name: string;
  system_prompt_content: string | null;
  chunks_used: unknown[] | null;
  llm_output: string | null;
  llm_provider: string;
  llm_model: string;
  created_at: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface ExoGenerationDetail {
  id: string;
  kind: 'exercise';
  created_at: string | null;
  status: string | null;
  username: string | null;
  request: ExoRequestInfo | null;
  rag_search: RagSearchInfo | null;
  llm_result: LlmResultInfo | null;
  component_selection: ComponentSelectionInfo | null;
}

export interface DiscussionGenerationDetail {
  id: string;
  kind: 'discussion';
  created_at: string | null;
  status: string | null;
  username: string | null;
  request: DiscussionRequestInfo | null;
  rag_search: DocRagSearchInfo | null;
  llm_result: DiscussionLlmResultInfo | null;
}

export type AnyGeneration = ExoGenerationDetail | DiscussionGenerationDetail;

export interface ConversationDetail {
  conversation_id: string;
  session_id: string | null;
  username: string | null;
  started_at: string | null;
  last_at: string | null;
  exo_generations: ExoGenerationDetail[];
  discussion_generations: DiscussionGenerationDetail[];
}

export interface SessionDetail {
  session_id: string;
  started_at: string | null;
  last_at: string | null;
  exo_generations: ExoGenerationDetail[];
  discussion_generations: DiscussionGenerationDetail[];
}

export interface GenerationStatsEntry {
  kind: string;
  embedding_model: string;
  llm_provider: string;
  llm_model: string;
  count: number;
}

export interface GenerationStats {
  exo: GenerationStatsEntry[];
  discussion: GenerationStatsEntry[];
}

export interface AppConfig {
  embedding_model: string;
}

export interface LLMOptionEntry {
  provider: string;
  model: string;
}

export interface LLMOptionsResponse {
  options: LLMOptionEntry[];
  current_provider: string;
  current_model: string;
}

export interface SetLLMConfigRequest {
  provider: string;
  model: string;
}

export interface SetLLMConfigResponse {
  provider: string;
  model: string;
}

export interface RuntimeSettingEntry {
  key: string;
  value: string;
  value_type: 'float' | 'int' | 'str' | 'bool';
  description: string;
  default: string;
  min_value: number | null;
  max_value: number | null;
  options: string[] | null;
}

export interface RuntimeSettingsResponse {
  settings: RuntimeSettingEntry[];
}

export interface UpdateRuntimeSettingsRequest {
  settings: Record<string, string>;
}

export interface UpdateRuntimeSettingsResponse {
  updated: Record<string, string>;
}

