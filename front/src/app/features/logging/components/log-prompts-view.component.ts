import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogsService } from '../../../core/logging/logs.service';
import { PromptEntry } from '../models/log.model';
import { LogStatusViewComponent, LoadingState } from './log-status-view/log-status-view.component';

@Component({
  selector: 'app-log-prompts-view',
  standalone: true,
  imports: [CommonModule, LogStatusViewComponent],
  template: `
    <div class="prompts-view">
      <div class="prompts-view__header">
        <h2 class="prompts-view__title">Prompts système</h2>
        <span class="prompts-view__count" *ngIf="state() === 'success'">
          {{ prompts().length }} prompt{{ prompts().length !== 1 ? 's' : '' }}
        </span>
      </div>

      <app-log-status-view
        [state]="state()"
        [empty]="prompts().length === 0"
        [errorMessage]="errorMessage()"
        emptyMessage="Aucun prompt enregistré."
      />

      @if (state() === 'success' && prompts().length > 0) {
        <div class="prompts-view__list">
          @for (prompt of prompts(); track prompt.id) {
            <article
              class="prompt-card"
              [class.prompt-card--expanded]="expandedId() === prompt.id"
            >
              <button
                class="prompt-card__header"
                type="button"
                (click)="toggleExpand(prompt.id)"
                [attr.aria-expanded]="expandedId() === prompt.id"
              >
                <div class="prompt-card__name-row">
                  <span class="prompt-card__name">{{ prompt.name }}</span>
                  <span class="prompt-card__updated" *ngIf="prompt.updated_at">
                    Mis à jour {{ formatDate(prompt.updated_at) }}
                  </span>
                </div>
                <svg
                  class="prompt-card__chevron"
                  [class.prompt-card__chevron--open]="expandedId() === prompt.id"
                  xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2"
                >
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>

              @if (expandedId() === prompt.id) {
                <div class="prompt-card__content">
                  <pre class="prompt-card__pre">{{ prompt.content }}</pre>
                </div>
              }
            </article>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    .prompts-view {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    .prompts-view__header {
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
      padding: 1.25rem 1.5rem 1rem;
      border-bottom: 1px solid var(--brand-border-color);
      flex-shrink: 0;
    }

    .prompts-view__title {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
      color: var(--brand-text-primary);
    }

    .prompts-view__count {
      font-size: 0.8125rem;
      color: var(--brand-text-tertiary);
    }

    .prompts-view__list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 1rem 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .prompt-card {
      border: 1px solid var(--brand-border-color);
      border-radius: 8px;
      background: var(--brand-color-primary-contrast);
      overflow: hidden;
      transition: border-color 0.15s;
    }

    .prompt-card:hover {
      border-color: var(--brand-color-secondary);
    }

    .prompt-card__header {
      width: 100%;
      background: none;
      border: none;
      padding: 0.75rem 1rem;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      cursor: pointer;
      gap: 0.75rem;
      height: auto;
      min-height: 0;
    }

    .prompt-card__name-row {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.25rem;
      text-align: left;
      flex: 1;
      min-width: 0;
    }

    .prompt-card__name {
      font-size: 0.875rem;
      font-weight: 500;
      color: var(--brand-text-primary);
      font-family: monospace;
      word-break: break-word;
    }

    .prompt-card__updated {
      font-size: 0.75rem;
      color: var(--brand-text-tertiary);
      white-space: normal;
    }

    .prompt-card__chevron {
      flex-shrink: 0;
      margin-top: 2px;
      color: var(--brand-text-tertiary);
      transition: transform 0.2s;
    }

    .prompt-card__chevron--open {
      transform: rotate(180deg);
    }

    .prompt-card__content {
      border-top: 1px solid var(--brand-border-color);
      padding: 0.75rem 1rem;
      background: var(--brand-background-secondary, #f9fafb);
    }

    .prompt-card__pre {
      margin: 0;
      font-size: 0.75rem;
      font-family: 'Consolas', 'Fira Code', monospace;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--brand-text-primary);
      line-height: 1.6;
      max-height: 400px;
      overflow-y: auto;
    }
  `]
})
export class LogPromptsViewComponent implements OnInit {
  private readonly logsService = inject(LogsService);

  protected readonly prompts = signal<PromptEntry[]>([]);
  protected readonly state = signal<LoadingState>('loading');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly expandedId = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    try {
      const data = await this.logsService.getPrompts();
      this.prompts.set(data);
      this.state.set('success');
    } catch (err: unknown) {
      this.state.set('error');
      this.errorMessage.set(err instanceof Error ? err.message : 'Erreur inconnue');
    }
  }

  protected toggleExpand(id: string): void {
    this.expandedId.set(this.expandedId() === id ? null : id);
  }

  protected formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
  }
}

