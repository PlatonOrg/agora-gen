import { Injectable, inject, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { LogsService } from '../logging/logs.service';
import { LLMOptionEntry } from '../../features/logging/models/log.model';

const POLL_INTERVAL_MS = 10 * 60 * 1000;

@Injectable({ providedIn: 'root' })
export class LlmOptionsPollingService {
  private readonly logsService = inject(LogsService);
  private readonly isBrowser: boolean;

  readonly options = signal<LLMOptionEntry[]>([]);
  readonly currentProviderName = signal<string>('');
  readonly currentModelName = signal<string>('');
  readonly isRefreshing = signal<boolean>(false);

  private pollSubscription: Subscription | null = null;

  constructor(@Inject(PLATFORM_ID) platformId: object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async loadOnce(): Promise<void> {
    if (!this.isBrowser) return;
    await this.fetchAndApply();
  }

  startPolling(): void {
    if (!this.isBrowser || this.pollSubscription) return;

    this.pollSubscription = interval(POLL_INTERVAL_MS)
      .pipe(switchMap(() => this.fetchAndApply()))
      .subscribe();
  }

  stopPolling(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = null;
  }

  private async fetchAndApply(): Promise<void> {
    this.isRefreshing.set(true);
    try {
      const response = await this.logsService.getLlmOptions();
      this.options.set(response.options);
      this.currentProviderName.set(response.current_provider);
      this.currentModelName.set(response.current_model);
    } catch {
    } finally {
      this.isRefreshing.set(false);
    }
  }
}

