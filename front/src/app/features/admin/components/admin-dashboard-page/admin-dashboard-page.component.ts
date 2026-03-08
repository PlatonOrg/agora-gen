import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminStatisticsService } from '../../services/admin-statistics.service';
import { UserProfileService } from '../../../../core/auth/user-profile.service';
import { AdminChartComponent } from '../admin-chart/admin-chart.component';
import { DateRangePreset } from '../../models/admin-statistics.model';

@Component({
  selector: 'app-admin-dashboard-page',
  standalone: true,
  imports: [CommonModule, FormsModule, AdminChartComponent],
  templateUrl: './admin-dashboard-page.component.html',
  styleUrl: './admin-dashboard-page.component.scss',
})
export class AdminDashboardPageComponent implements OnInit {
  private readonly router = inject(Router);
  protected readonly statsService = inject(AdminStatisticsService);
  protected readonly userProfile = inject(UserProfileService);

  protected readonly selectedPreset = signal<DateRangePreset>('last_7_days');
  protected customDateFrom = '';
  protected customDateTo = '';

  async ngOnInit(): Promise<void> {
    await this.applyPreset('last_7_days');
  }

  protected async applyPreset(preset: DateRangePreset): Promise<void> {
    this.selectedPreset.set(preset);

    if (preset === 'custom') return;

    const today = new Date();
    const dateTo = this.formatDate(today);
    let dateFrom: string;

    switch (preset) {
      case 'last_7_days':
        dateFrom = this.formatDate(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000));
        break;
      case 'last_30_days':
        dateFrom = this.formatDate(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000));
        break;
      case 'last_365_days':
        dateFrom = this.formatDate(new Date(Date.now() - 365 * 24 * 60 * 60 * 1000));
        break;
    }

    this.customDateFrom = dateFrom;
    this.customDateTo = dateTo;
    await this.statsService.loadStats(dateFrom, dateTo);
  }

  protected async applyCustomRange(): Promise<void> {
    if (!this.customDateFrom || !this.customDateTo) return;
    this.selectedPreset.set('custom');
    await this.statsService.loadStats(this.customDateFrom, this.customDateTo);
  }

  protected formatResponseTime(ms: number | null): string {
    if (ms === null) return 'N/A';
    return (ms / 1000).toFixed(2) + 's';
  }

  protected goBack(): void {
    this.router.navigate(['/workspace']);
  }

  private formatDate(d: Date): string {
    return d.toISOString().split('T')[0];
  }
}
