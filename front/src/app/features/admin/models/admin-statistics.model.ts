export interface DailyMetrics {
  date: string;
  conversations: number;
  published_exercises: number;
  clean_generations: number;
  recovered_generations: number;
  fatal_generations: number;
  internal_error_generations: number;
  avg_response_time_ms: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface SummaryMetrics {
  total_conversations: number;
  total_published_exercises: number;
  clean_generations: number;
  recovered_generations: number;
  fatal_generations: number;
  internal_error_generations: number;
  avg_response_time_ms: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_tokens_per_generation: number | null;
}

export interface AdminStatsResponse {
  summary: SummaryMetrics;
  daily: DailyMetrics[];
  date_from: string;
  date_to: string;
}

export type DateRangePreset = 'last_7_days' | 'last_30_days' | 'last_365_days' | 'custom';
