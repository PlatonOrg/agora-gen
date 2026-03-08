export type GenerationStepState = 'pending' | 'in_progress' | 'completed' | 'error' | 'stopped';
export type GenerationDetailStatus = 'info' | 'start' | 'done' | 'error' | 'warning';

export interface GenerationTimelineDetailChild {
  text: string;
  url?: string;
}

export type AssistantMode = 'ask' | 'agent';

export interface GenerationTimelineDetail {
  id: string;
  text: string;
  status: GenerationDetailStatus;
  url?: string;
  children?: GenerationTimelineDetailChild[];
}

export interface GenerationTimelineData {
  steps: { key: string; label: string; state: GenerationStepState }[];
  details: GenerationTimelineDetail[];
  typingText: string;
  typingStatus: GenerationDetailStatus;
  isTyping: boolean;
}

export interface ComponentBadge {
  name: string;
  tag: string;
  type: 'formulaire' | 'widget';
}

export interface Message {
  id: string;
  role: 'user' | 'ai' | 'system';
  content: string;
  components: string[];
  timestamp: Date;
  state?: 'in_progress' | 'completed' | 'error' | 'stopped';
  attachedFields?: string[];
  attachedParameters?: string[];
  attachedFileNames?: string[];
  generationTimeline?: GenerationTimelineData;
  source?: 'generation' | 'discussion';
}

export interface CachedMessage {
  id: string;
  role: 'user' | 'ai' | 'system';
  content: string;
  components: string[];
  timestamp: string;
  state?: 'in_progress' | 'completed' | 'error' | 'stopped';
  attachedFields?: string[];
  attachedParameters?: string[];
  attachedFileNames?: string[];
  generationTimeline?: GenerationTimelineData;
  source?: 'generation' | 'discussion';
}

export interface DiscussionCachePayload {
  messages: CachedMessage[];
  componentBadges: ComponentBadge[];
  parameterBadges: { name: string; type: string }[];
  fieldBadges: { name: string }[];
  inputText: string;
  assistantMode?: AssistantMode;
  uploadedFiles?: import('../../../../core/llm/llm-capabilities.service').UploadedFileEntry[];
  forcePureExercise?: boolean;
  conversationId?: string;
}
