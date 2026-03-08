export interface DailyMetrics {
  date: string;
  conversations: number;
  published_exercises: number;
  failures: number;
  avg_response_time_ms: number | null;
}

export interface SummaryMetrics {
  total_conversations: number;
  total_published_exercises: number;
  total_failures: number;
  avg_response_time_ms: number | null;
}

export interface AdminStatsResponse {
  summary: SummaryMetrics;
  daily: DailyMetrics[];
  date_from: string;
  date_to: string;
}

export type DateRangePreset = 'last_7_days' | 'last_30_days' | 'last_365_days' | 'custom';
