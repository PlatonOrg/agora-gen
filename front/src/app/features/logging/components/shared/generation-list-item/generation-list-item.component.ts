import { Component, input, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AnyGeneration, ExoGenerationDetail, DiscussionGenerationDetail } from '../../../models/log.model';
import { ExoGenerationDetailComponent } from '../../exo-generation-detail/exo-generation-detail.component';
import { DiscussionGenerationDetailComponent } from '../../discussion-generation-detail/discussion-generation-detail.component';
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
  imports: [CommonModule, ExoGenerationDetailComponent, DiscussionGenerationDetailComponent],
  templateUrl: './generation-list-item.component.html',
  styleUrl: './generation-list-item.component.scss',
})
export class GenerationListItemComponent {
  gen = input.required<AnyGeneration>();
  protected readonly open = signal(false);
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

  protected asExo(): ExoGenerationDetail { return this.gen() as ExoGenerationDetail; }
  protected asDisc(): DiscussionGenerationDetail { return this.gen() as DiscussionGenerationDetail; }
  protected fmt(iso: string | null | undefined): string { return fmtTime(iso); }
}



