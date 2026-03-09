import { Component, input, OnInit, signal, inject, computed, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsService } from '../../../../core/logging/logs.service';
import { SessionDetail, ConversationDetail, AnyGeneration, ExoGenerationDetail, DiscussionGenerationDetail } from '../../models/log.model';
import { LogStatusViewComponent, LoadingState } from '../log-status-view/log-status-view.component';
import { LogBadgeComponent } from '../shared/log-badge/log-badge.component';
import { LogPaginationComponent } from '../shared/log-pagination/log-pagination.component';
import { GenerationListItemComponent } from '../shared/generation-list-item/generation-list-item.component';
import { ExoGenerationDetailComponent } from '../exo-generation-detail/exo-generation-detail.component';
import { DiscussionGenerationDetailComponent } from '../discussion-generation-detail/discussion-generation-detail.component';
import { fmtDateTime } from '../../utils/log-format.utils';
import { paginate, totalPages } from '../../utils/pagination.utils';

const PAGE_SIZE = 20;

type GenFilter = 'all' | 'exercise' | 'discussion';
type SortDir = 'asc' | 'desc';

interface DetailData {
  started_at: string | null;
  last_at: string | null;
  username: string | null;
  exo_generations: SessionDetail['exo_generations'];
  discussion_generations: SessionDetail['discussion_generations'];
}

@Component({
  selector: 'app-session-detail-view',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    LogStatusViewComponent, LogBadgeComponent,
    LogPaginationComponent, GenerationListItemComponent,
    ExoGenerationDetailComponent, DiscussionGenerationDetailComponent,
  ],
  templateUrl: './session-detail-view.component.html',
  styleUrls: ['../../logging.shared.scss', './session-detail-view.component.scss'],
})
export class SessionDetailViewComponent implements OnInit {
  sessionId = input.required<string>();
  readonly backRequested = output<void>();

  private readonly logsService = inject(LogsService);

  protected readonly detail = signal<DetailData | null>(null);
  protected readonly state = signal<LoadingState>('loading');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly filter = signal<GenFilter>('all');
  protected readonly sortDirection = signal<SortDir>('asc');
  protected readonly page = signal(1);
  protected readonly selectedGeneration = signal<AnyGeneration | null>(null);

  protected readonly allGenerations = computed<AnyGeneration[]>(() => {
    const d = this.detail();
    if (!d) return [];
    return [...d.exo_generations, ...d.discussion_generations]
      .sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''));
  });

  protected readonly filtered = computed<AnyGeneration[]>(() => {
    const f = this.filter();
    const dir = this.sortDirection();
    let list = f === 'all'
      ? this.allGenerations()
      : this.allGenerations().filter((g: AnyGeneration) => g.kind === f);
    return dir === 'desc' ? [...list].reverse() : list;
  });

  protected readonly totalPages = computed(() => totalPages(this.filtered().length, PAGE_SIZE));

  protected readonly paginated = computed(() =>
    paginate(this.filtered(), this.page(), PAGE_SIZE)
  );

  async ngOnInit(): Promise<void> {
    try {
      const id = this.sessionId();
      let data: ConversationDetail | SessionDetail;
      try {
        data = await this.logsService.getConversationDetail(id);
      } catch {
        data = await this.logsService.getSessionDetail(id);
      }
      this.detail.set({
        started_at: data.started_at,
        last_at: data.last_at,
        username: 'username' in data ? (data as ConversationDetail).username : null,
        exo_generations: data.exo_generations,
        discussion_generations: data.discussion_generations,
      });
      this.state.set('success');
    } catch (err: unknown) {
      this.state.set('error');
      this.errorMessage.set(err instanceof Error ? err.message : 'Erreur inconnue');
    }
  }

  protected setFilter(f: GenFilter): void {
    this.filter.set(f);
    this.page.set(1);
  }

  protected toggleSort(): void {
    this.sortDirection.set(this.sortDirection() === 'asc' ? 'desc' : 'asc');
    this.page.set(1);
  }

  protected openGeneration(gen: AnyGeneration): void {
    this.selectedGeneration.set(gen);
  }

  protected closeGeneration(): void {
    this.selectedGeneration.set(null);
  }

  protected isExoGeneration(gen: AnyGeneration): gen is ExoGenerationDetail {
    return gen.kind === 'exercise';
  }

  protected asExo(gen: AnyGeneration): ExoGenerationDetail {
    return gen as ExoGenerationDetail;
  }

  protected asDisc(gen: AnyGeneration): DiscussionGenerationDetail {
    return gen as DiscussionGenerationDetail;
  }

  protected fmtFull(iso: string | null | undefined): string { return fmtDateTime(iso); }
}


