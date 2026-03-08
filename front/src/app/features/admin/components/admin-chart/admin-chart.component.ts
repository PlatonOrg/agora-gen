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
    domain: ['#3b82f6', '#10b981', '#ef4444', '#f59e0b'],
  };

  readonly chartData = computed<ChartSeries[]>(() => {
    const data = this.daily();
    if (!data || data.length === 0) return [];

    return [
      {
        name: 'Conversations',
        series: data.map((d) => ({
          name: new Date(d.date),
          value: d.conversations,
        })),
      },
      {
        name: 'Exercices publiés',
        series: data.map((d) => ({
          name: new Date(d.date),
          value: d.published_exercises,
        })),
      },
      {
        name: 'Échecs',
        series: data.map((d) => ({
          name: new Date(d.date),
          value: d.failures,
        })),
      },
      {
        name: 'Temps de réponse (s)',
        series: data.map((d) => ({
          name: new Date(d.date),
          value: d.avg_response_time_ms != null ? d.avg_response_time_ms / 1000 : 0,
        })),
      },
    ];
  });

  readonly hasData = computed(() => this.chartData().length > 0);
}
