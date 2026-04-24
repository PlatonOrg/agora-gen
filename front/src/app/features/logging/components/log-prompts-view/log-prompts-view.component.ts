import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogsService } from '../../../../core/logging/logs.service';
import { PromptEntry } from '../../models/log.model';
import { LogStatusViewComponent, LoadingState } from '../log-status-view/log-status-view.component';

@Component({
  selector: 'app-log-prompts-view',
  standalone: true,
  imports: [CommonModule, LogStatusViewComponent],
  templateUrl: './log-prompts-view.component.html',
  styleUrl: './log-prompts-view.component.scss',
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
