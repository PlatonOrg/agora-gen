import { Injectable, inject } from '@angular/core';
import { ApiService } from '../api/api.service';
import {
  PromptEntry,
  PromptPatchRequest,
  SessionSummary,
  SessionDetail,
  ConversationSummary,
  ConversationDetail,
  GenerationStats,
  AppConfig,
  LLMOptionsResponse,
  SetLLMConfigRequest,
  SetLLMConfigResponse,
  RuntimeSettingsResponse,
  UpdateRuntimeSettingsRequest,
  UpdateRuntimeSettingsResponse,
} from '../../features/logging/models/log.model';

@Injectable({ providedIn: 'root' })
export class LogsService {
  private readonly api = inject(ApiService);

  async getPrompts(): Promise<PromptEntry[]> {
    return this.api.get<PromptEntry[]>('/logs/prompts');
  }

  async patchPrompt(promptId: string, updates: PromptPatchRequest): Promise<PromptEntry> {
    return this.api.patch<PromptEntry>(`/logs/prompts/${encodeURIComponent(promptId)}`, updates);
  }

  async getConversations(): Promise<ConversationSummary[]> {
    return this.api.get<ConversationSummary[]>('/logs/conversations');
  }

  async getConversationDetail(conversationId: string): Promise<ConversationDetail> {
    return this.api.get<ConversationDetail>(`/logs/conversations/${encodeURIComponent(conversationId)}`);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    await this.api.delete(`/logs/conversations/${encodeURIComponent(conversationId)}`);
  }

  async getSessions(): Promise<SessionSummary[]> {
    return this.api.get<SessionSummary[]>('/logs/sessions');
  }

  async getSessionDetail(sessionId: string): Promise<SessionDetail> {
    return this.api.get<SessionDetail>(`/logs/sessions/${encodeURIComponent(sessionId)}`);
  }

  async getStats(): Promise<GenerationStats> {
    return this.api.get<GenerationStats>('/logs/stats');
  }

  async getConfig(): Promise<AppConfig> {
    return this.api.get<AppConfig>('/logs/config');
  }

  async getLlmOptions(): Promise<LLMOptionsResponse> {
    return this.api.get<LLMOptionsResponse>('/admin/llm-options');
  }

  async setLlmConfig(request: SetLLMConfigRequest): Promise<SetLLMConfigResponse> {
    return this.api.put<SetLLMConfigResponse>('/admin/llm-config', request);
  }

  async getRuntimeSettings(): Promise<RuntimeSettingsResponse> {
    return this.api.get<RuntimeSettingsResponse>('/admin/settings');
  }

  async updateRuntimeSettings(request: UpdateRuntimeSettingsRequest): Promise<UpdateRuntimeSettingsResponse> {
    return this.api.put<UpdateRuntimeSettingsResponse>('/admin/settings', request);
  }
}
