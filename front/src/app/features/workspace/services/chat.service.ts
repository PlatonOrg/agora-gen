import {Inject, Injectable, PLATFORM_ID, signal} from '@angular/core';
import {isPlatformBrowser} from '@angular/common';
import {
  TemplatePreviewRequest,
  TemplatePreviewResponse
} from '../models/template.model';
import { ChatRequest, ChatResponse, ExerciseData, ExerciseVariant } from '../models/exercise.model';
import { PublishExerciseRequest, PublishExerciseResponse } from '../models/publish.model';

export interface PlatonDocsSource {
  source_path: string;
  chunk_index: number;
  score?: number | null;
  excerpt: string;
}

export interface PlatonDocsQuestionResponse {
  answer?: string;
  sources: PlatonDocsSource[];
  error?: string;
}

/**
 * Interfaces for chat/generation events
 */
export interface GenerationStep {
  step: string;
  status: 'in_progress' | 'completed' | 'error';
  message: string;
  data?: any;
  timestamp?: Date;
}

export interface GenerationProgress {
  step: string;
  progress: number;
  message: string;
}

export interface TemplateParameter {
  name: string;
  type: 'string' | 'text' | 'number' | 'boolean' | 'array' | 'object' | 'select' | 'code';
  description: string;
  defaultValue: any;
  options?: string[]; // For 'select' type
}

export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
  isTemplate: boolean;
  parameters: TemplateParameter[];
}

export interface GenerationComplete {
  exerciseId: string;
  previewUrl:  string | null;
  message: string;
  components: string[];
  template: TemplateInfo | null;
  isTemplate: boolean;
  parameters: TemplateParameter[];
  timestamp: string;
}

export interface GenerationError {
  message: string;
  error?: string;
}

export interface GenerationVariants {
  variants: ExerciseVariant[];
  message?: string;
  conversation_mode?: string;
}

export type GenerationEvent =
  | { type: 'step'; data: GenerationStep }
  | { type: 'progress'; data: GenerationProgress }
  | { type: 'complete'; data: GenerationComplete }
  | { type: 'variants_generated'; data: GenerationVariants }
  | { type: 'error'; data: GenerationError };

/**
 * Chat Service for handling conversation and SSE streaming
 */
@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private readonly API_BASE_URL = '/api/v1';
  private isBrowser: boolean;

  // Current generation state
  private currentEventSource: EventSource | null = null;
  private currentAbortController: AbortController | null = null;

  // Signals for reactive state
  public isGenerating = signal<boolean>(false);
  public currentSteps = signal<GenerationStep[]>([]);
  public currentProgress = signal<GenerationProgress | null>(null);
  public lastResult = signal<GenerationComplete | null>(null);
  public error = signal<GenerationError | null>(null);

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  /**
   * Create a new conversation
   */
  async createConversation(): Promise<string> {
    const response = await fetch(`${this.API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include' // Include cookies for session
    });

    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }

    const data = await response.json();
    return data.id;
  }

  private humanize(eventType: string): string {
    return eventType
      .replace(/_/g, ' ')
      .replace('started', '')
      .replace('completed', '')
      .trim()
      .replace(/\b\w/g, l => l.toUpperCase());
  }


  /**
   * Send a message and stream the generation response
   * Returns an observable-like callback system for events
   */
  async sendMessage(
    conversationId: string,
    message: string,
    onEvent: (event: GenerationEvent) => void
  ): Promise<void> {
    if (!this.isBrowser) return;

    this.isGenerating.set(true);
    this.currentSteps.set([]);
    this.currentProgress.set(null);
    this.lastResult.set(null);
    this.error.set(null);

    try {
      const response = await fetch(
        `${this.API_BASE_URL}/chat/${conversationId}/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({ message }),
        }
      );

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let eventType = '';
        let eventData = '';

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.replace('event:', '').trim();
          } else if (line.startsWith('data:')) {
            eventData = line.replace('data:', '').trim();
          } else if (line === '' && eventType && eventData) {
            this.processSSEEvent(eventType, eventData, onEvent);
            eventType = '';
            eventData = '';
          }
        }
      }
    } catch (err: any) {
      onEvent({
        type: 'error',
        data: { message: 'Erreur serveur', error: err.message },
      });
    } finally {
      this.isGenerating.set(false);
    }
  }

  /**
   * Process a single SSE event
   */
  private processSSEEvent(
    eventType: string,
    dataStr: string,
    onEvent: (event: GenerationEvent) => void
  ): void {
    try {
      const data = JSON.parse(dataStr);
      console.log(`[ChatService] SSE Event: ${eventType}`, data);

      // 1) Specific events FIRST (no generic suffix catch)
      if (eventType === 'generation_started') {
        this.lastResult.set({
          exerciseId: '',
          previewUrl: null,
          message: '',
          components: [],
          template: null,
          isTemplate: false,
          parameters: [],
          timestamp: new Date().toISOString(),
        });

        onEvent({
          type: 'step',
          data: {
            step: 'generation',
            status: 'in_progress',
            message: 'Génération de l’exercice',
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      if (eventType === 'generation_completed') {
        // optionally show a completed step if you want
        onEvent({
          type: 'step',
          data: {
            step: 'generation',
            status: 'completed',
            message: 'Exercice généré',
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      if (eventType === 'preview_started') {
        onEvent({
          type: 'step',
          data: {
            step: 'preview',
            status: 'in_progress',
            message: 'Génération de l’aperçu',
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      if (eventType === 'preview_completed') {
        const previewUrl = data.previewUrl;

        if (!previewUrl) {
          onEvent({
            type: 'step',
            data: {
              step: 'preview',
              status: 'error',
              message: 'Erreur lors de la génération de l’aperçu',
              data,
              timestamp: new Date(),
            },
          });

          onEvent({
            type: 'error',
            data: { message: 'La génération de l’aperçu a échoué' },
          });
          return;
        }

        // store url (lastResult MUST exist now)
        this.lastResult.update(r => (r ? { ...r, previewUrl } : r));

        onEvent({
          type: 'step',
          data: {
            step: 'preview',
            status: 'completed',
            message: 'Aperçu généré',
            data,
            timestamp: new Date(),
          },
        });

        return;
      }

      if (eventType === 'done') {
        this.isGenerating.set(false);

        const result = this.lastResult();

        if (result?.previewUrl) {
          onEvent({
            type: 'complete',
            data: {
              ...result,
              message: 'Exercice généré avec succès',
            },
          });
        } else {
          onEvent({
            type: 'error',
            data: { message: 'Échec de la génération de l’aperçu' },
          });
        }

        return;
      }

      if (eventType === 'sandbox_retry') {
        onEvent({
          type: 'step',
          data: {
            step: 'sandbox_retry',
            status: 'in_progress',
            message: `Erreur de compilation -- correction automatique (tentative ${data.attempt}/${data.max_attempts})...`,
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      if (eventType === 'error') {
        onEvent({ type: 'error', data });
        return;
      }

      // 2) Generic mapping LAST
      if (eventType.endsWith('_started')) {
        onEvent({
          type: 'step',
          data: {
            step: eventType.replace('_started', ''),
            status: 'in_progress',
            message: this.humanize(eventType),
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      if (eventType.endsWith('_completed')) {
        onEvent({
          type: 'step',
          data: {
            step: eventType.replace('_completed', ''),
            status: 'completed',
            message: this.humanize(eventType),
            data,
            timestamp: new Date(),
          },
        });
        return;
      }

      console.warn('[ChatService] Unhandled SSE event:', eventType);
    } catch (err) {
      console.error('[ChatService] SSE parse error:', err, dataStr);
    }
  }



  /**
   * Close the current SSE connection
   */
  closeConnection(): void {
    if (this.currentEventSource) {
      this.currentEventSource.close();
      this.currentEventSource = null;
    }
  }

  /**
   * Preview a template with given variables
   */
  async previewTemplate(
    templateId: string,
    variables: { [key: string]: any }
  ): Promise<TemplatePreviewResponse> {
    const request: TemplatePreviewRequest = {
      template_id: templateId,
      variables: variables
    };

    const response = await fetch(`${this.API_BASE_URL}/context/template_preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include', // Include cookies for session
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Preview an exercise with given ExerciseData
   */
  async previewExercise(
    exerciseData: ExerciseData
  ): Promise<{ preview_url: string }> {
    const response = await fetch(`${this.API_BASE_URL}/context/preview_exercise`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(exerciseData),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  async publishExercise(
    exerciseId: string,
    publishRequest: PublishExerciseRequest
  ): Promise<PublishExerciseResponse> {
    const response = await fetch(`${this.API_BASE_URL}/exercises/publish/${exerciseId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(publishRequest),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json() as Promise<PublishExerciseResponse>;
  }

  /**
   * Send a chat request and stream the response events
   * Returns an observable-like callback system for events
   */
  async sendChatRequest(
    exerciseState: any,
    userRequest: string,
    userSelectedComponents: string[],
    conversationHistory: { role: 'user' | 'ai' | 'system'; content: string; components: string[] }[],
    fieldsToModify: string[],
    onEvent: (event: { type: string; data: any }) => void,
    fileIds?: string[],
    conversationMode?: string,
    forcePureExercise?: boolean,
    conversationId?: string,
    generationContext?: import('../models/exercise.model').ExerciseGenerationContext,
  ): Promise<void> {
    const request: ChatRequest & { file_ids?: string[] } = {
      exercise_state: exerciseState,
      user_request: userRequest,
      user_selected_components: userSelectedComponents,
      conversation_history: conversationHistory,
      fields_to_modify: fieldsToModify,
      ...(fileIds && fileIds.length > 0 ? { file_ids: fileIds } : {}),
      ...(conversationMode ? { conversation_mode: conversationMode } : {}),
      ...(forcePureExercise ? { force_pure_exercise: true } : {}),
      ...(conversationId ? { conversation_id: conversationId } : {}),
      ...(generationContext ? { generation_context: generationContext } : {}),
    };

    this.currentAbortController = new AbortController();

    const response = await fetch(`${this.API_BASE_URL}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(request),
      signal: this.currentAbortController.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let eventType = '';
    let eventData = '';

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.replace('event:', '').trim();
          } else if (line.startsWith('data:')) {
            eventData = line.replace('data:', '').trim();
          } else if (line === '' && eventType && eventData) {
            try {
              const data = JSON.parse(eventData);
              onEvent({ type: eventType, data });
            } catch (e) {
              console.error('Failed to parse SSE data:', eventData);
            }
            eventType = '';
            eventData = '';
          }
        }
      }
    } finally {
      this.currentAbortController = null;
    }
  }

  /**
   * Request the backend to cancel the running generation by setting the stop
   * flag in Redis.  The SSE connection is intentionally kept open so that the
   * backend can send the `stopped` event back to the client, giving it a
   * chance to update the UI before the stream closes naturally.
   *
   * Use `forceAbort()` instead when the connection must be dropped immediately
   * (e.g. inside a `beforeunload` handler or on component destruction).
   */
  stopGeneration(): void {
    if (!this.isBrowser || !this.isGenerating()) {
      return;
    }
    try {
      fetch(`${this.API_BASE_URL}/chat/stop`, {
        method: 'POST',
        credentials: 'include',
        keepalive: true,
      });
    } catch {
      // Best-effort only.
    }
  }

  /**
   * Forcefully drop the SSE connection without waiting for a graceful stop
   * event.  Used inside `beforeunload` handlers and `ngOnDestroy` where we
   * cannot await an async response.
   */
  forceAbort(): void {
    if (!this.isBrowser) {
      return;
    }
    if (this.currentAbortController) {
      this.currentAbortController.abort();
      this.currentAbortController = null;
    }
    if (!this.isGenerating()) {
      return;
    }
    try {
      fetch(`${this.API_BASE_URL}/chat/stop`, {
        method: 'POST',
        credentials: 'include',
        keepalive: true,
      });
    } catch {
      // Best-effort only.
    }
  }

  async askPlatonDocs(
    question: string,
    topK = 5,
    conversationId?: string,
  ): Promise<PlatonDocsQuestionResponse> {
    this.currentAbortController = new AbortController();
    try {
      const response = await fetch(`${this.API_BASE_URL}/chat/platon-docs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ question, top_k: topK, conversation_id: conversationId ?? null }),
        signal: this.currentAbortController.signal,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data?.error || data?.detail || `HTTP ${response.status}`);
      }

      return {
        answer: data.answer,
        sources: Array.isArray(data.sources) ? data.sources : [],
        error: data.error,
      };
    } finally {
      this.currentAbortController = null;
    }
  }

  /**
   * Get the PLE content for an exercise
   */
  async getPleContent(
    exerciseData: ExerciseData
  ): Promise<{ ple_content: string }> {
    const response = await fetch(`${this.API_BASE_URL}/context/ple_content`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include', // Include cookies for session
      body: JSON.stringify(exerciseData)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  async getTags(): Promise<{ topics: { id: string; name: string }[]; levels: { id: string; name: string }[] }> {
    const response = await fetch(`${this.API_BASE_URL}/exercises/tags`, {
      method: 'GET',
      credentials: 'include',
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
  }

  /**
   * Reset the generation state
   */
  reset(): void {
    this.closeConnection();
    this.isGenerating.set(false);
    this.currentSteps.set([]);
    this.currentProgress.set(null);
    this.lastResult.set(null);
    this.error.set(null);
  }
}
