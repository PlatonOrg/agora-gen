export interface ExerciseMetadata {
  levels: string[];
  topics: string[];
  readme?: string;
}

export interface ComponentInstance {
  id: string;
  selector: string;
  componentName: string;
  instanceName: string;
  category: 'Formulaire' | 'Widget';
  properties: { [key: string]: any };
  collapsed?: boolean;
}

export interface ExerciseData {
  name?: string;
  description?: string;
  titre?: string;
  enonce?: string;
  forme?: string;
  solution?: string;
  indications?: string[];
  theories?: { title: string; url: string }[];
  components?: string[]; // Keep for backward compatibility
  component_instances?: ComponentInstance[]; // New detailed components
  sandbox?: string;
  construction?: string;
  evaluation?: string;
  template_id?: string;
  exercise_id?: string;
  config_variables?: { [key: string]: any };
  sandbox_variables?: { [key: string]: any };
  metadata?: ExerciseMetadata;
}

export interface ChatMessage {
  role: 'user' | 'ai' | 'system';
  content: string;
  components: string[];
}

export interface ChatRequest {
  exercise_state: ExerciseData;
  user_request: string;
  user_selected_components: string[];
  conversation_history: ChatMessage[];
  fields_to_modify?: string[];
  conversation_mode?: string;
  force_pure_exercise?: boolean;
  conversation_id?: string;
}

export interface ChatResponse {
  exercise_data?: ExerciseData;
  url?: string;
  message?: string;
  error?: string;
  conversation_mode?: string;
}
