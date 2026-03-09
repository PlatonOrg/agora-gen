import { Component, input, computed, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AnyGeneration, ExoGenerationDetail, DiscussionGenerationDetail } from '../../../models/log.model';
import { truncate, fmtTime } from '../../../utils/log-format.utils';

const STATUS_LABELS: Record<string, string> = {
  completed:  'Terminé',
  error:      'Échoué',
  failed:     'Échoué',
  stopped:    'Interrompu',
  in_progress: 'En cours',
  pending:    'En attente',
};

@Component({
  selector: 'app-generation-list-item',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './generation-list-item.component.html',
  styleUrl: './generation-list-item.component.scss',
})
export class GenerationListItemComponent {
  gen = input.required<AnyGeneration>();
  readonly selected = output<AnyGeneration>();

  protected readonly isDiscussion = computed(() => this.gen().kind === 'discussion');
  protected readonly preview = computed(() => {
    const g = this.gen();
    const text = g.kind === 'exercise'
      ? (g as ExoGenerationDetail).request?.user_request
      : (g as DiscussionGenerationDetail).request?.user_request;
    return truncate(text, 90);
  });

  protected statusLabel(status: string | null | undefined): string {
    if (!status || status === 'completed') return '';
    return STATUS_LABELS[status] ?? status;
  }

  protected isErrorStatus(status: string | null | undefined): boolean {
    return status === 'error' || status === 'failed';
  }

  protected onSelect(): void {
    this.selected.emit(this.gen());
  }

  protected fmt(iso: string | null | undefined): string { return fmtTime(iso); }
}



