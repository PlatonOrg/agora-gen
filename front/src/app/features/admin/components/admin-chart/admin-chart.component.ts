import { Component, computed, input } from '@angular/core';
import { LineChartModule, Color, ScaleType } from '@swimlane/ngx-charts';
import { DailyMetrics } from '../../models/admin-statistics.model';

interface ChartSeries {
  name: string;
  series: { name: Date; value: number }[];
}

@Component({
  selector: 'app-admin-chart',
  standalone: true,
  imports: [LineChartModule],
  templateUrl: './admin-chart.component.html',
  styleUrl: './admin-chart.component.scss',
})
export class AdminChartComponent {
  readonly daily = input<DailyMetrics[]>([]);
  readonly animate = input<boolean>(true);

  readonly colorScheme: Color = {
    name: 'custom',
    selectable: true,
    group: ScaleType.Ordinal,
    domain: ['#3b82f6', '#10b981', '#22c55e', '#f59e0b', '#ef4444', '#dc2626', '#8b5cf6'],
  };

  readonly chartData = computed<ChartSeries[]>(() => {
    const data = this.daily();
    if (!data || data.length === 0) return [];

    return [
      {
        name: 'Conversations',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.conversations,
        })),
      },
      {
        name: 'Exercices publiés',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.published_exercises,
        })),
      },
      {
        name: 'Sans erreur',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.clean_generations,
        })),
      },
      {
        name: 'Corrigées (retry)',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.recovered_generations,
        })),
      },
      {
        name: 'Échecs fatals',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.fatal_generations,
        })),
      },
      {
        name: 'Erreurs internes',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.internal_error_generations,
        })),
      },
      {
        name: 'Temps de réponse (s)',
        series: data.map((d: DailyMetrics) => ({
          name: new Date(d.date),
          value: d.avg_response_time_ms != null ? d.avg_response_time_ms / 1000 : 0,
        })),
      },
    ];
  });

  readonly hasData = computed(() => this.chartData().length > 0);
}
