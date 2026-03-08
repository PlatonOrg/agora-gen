import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from '../../../core/api/api.service';
import { AdminStatsResponse } from '../models/admin-statistics.model';

@Injectable({ providedIn: 'root' })
export class AdminStatisticsService {
  private readonly api = inject(ApiService);

  readonly stats = signal<AdminStatsResponse | null>(null);
  readonly loading = signal<boolean>(false);
  readonly error = signal<string | null>(null);

  async getStats(dateFrom: string, dateTo: string): Promise<AdminStatsResponse> {
    return this.api.get<AdminStatsResponse>(`/admin/stats?date_from=${dateFrom}&date_to=${dateTo}`);
  }

  async loadStats(dateFrom: string, dateTo: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const data = await this.getStats(dateFrom, dateTo);
      this.stats.set(data);
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      this.loading.set(false);
    }
  }
}
