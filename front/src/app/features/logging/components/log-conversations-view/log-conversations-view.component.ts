import { Component, OnInit, signal, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsService } from '../../../../core/logging/logs.service';
import { ConversationSummary } from '../../models/log.model';
import { LogStatusViewComponent, LoadingState } from '../log-status-view/log-status-view.component';
import { LogBadgeComponent } from '../shared/log-badge/log-badge.component';
import { LogPaginationComponent } from '../shared/log-pagination/log-pagination.component';
import { LogSortBarComponent, SortField, SortDir, SortOption } from '../shared/log-sort-bar/log-sort-bar.component';
import { SessionDetailViewComponent } from '../session-detail-view/session-detail-view.component';
import { fmtDateTime } from '../../utils/log-format.utils';
import { paginate, totalPages } from '../../utils/pagination.utils';

const PAGE_SIZE = 15;

const SORT_OPTIONS: SortOption[] = [
  { field: 'started_at', label: 'Date de création' },
  { field: 'last_at',    label: 'Dernière activité' },
  { field: 'count',      label: 'Nombre de requêtes' },
];

@Component({
  selector: 'app-log-conversations-view',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    LogStatusViewComponent, LogBadgeComponent,
    LogPaginationComponent, LogSortBarComponent,
    SessionDetailViewComponent,
  ],
  templateUrl: './log-conversations-view.component.html',
  styleUrls: ['../../logging.shared.scss', './log-conversations-view.component.scss'],
})
export class LogConversationsViewComponent implements OnInit {
  private readonly logsService = inject(LogsService);

  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly state = signal<LoadingState>('loading');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly selectedConversationId = signal<string | null>(null);

  protected readonly searchQuery = signal('');
  protected readonly page = signal(1);
  protected readonly sortField = signal<SortField>('last_at');
  protected readonly sortDirection = signal<SortDir>('desc');

  protected readonly dateFrom = signal('');
  protected readonly dateTo = signal('');

  /** Tracks which conversation is pending delete confirmation. */
  protected readonly pendingDeleteId = signal<string | null>(null);

  protected readonly sortOptions = SORT_OPTIONS;

  protected readonly processed = computed<ConversationSummary[]>(() => {
    const q = this.searchQuery().trim().toLowerCase();
    const field = this.sortField();
    const dir = this.sortDirection();
    const from = this.dateFrom();
    const to = this.dateTo();

    let list = this.conversations();

    // Text search filter
    if (q) {
      list = list.filter((c: ConversationSummary) =>
        (c.username ?? '').toLowerCase().includes(q) ||
        (c.conversation_id ?? '').toLowerCase().includes(q)
      );
    }

    // Date window filter
    if (from) {
      list = list.filter((c: ConversationSummary) => (c.started_at ?? '') >= from);
    }
    if (to) {
      const toExclusive = to + 'T23:59:59';
      list = list.filter((c: ConversationSummary) => (c.started_at ?? '') <= toExclusive);
    }

    list = [...list].sort((a, b) => {
      let va: string | number;
      let vb: string | number;
      if (field === 'count') {
        va = a.total_generation_count;
        vb = b.total_generation_count;
      } else {
        va = a[field] ?? '';
        vb = b[field] ?? '';
      }
      if (va < vb) return dir === 'asc' ? -1 : 1;
      if (va > vb) return dir === 'asc' ? 1 : -1;
      return 0;
    });

    return list;
  });

  protected readonly totalPages = computed(() => totalPages(this.processed().length, PAGE_SIZE));

  protected readonly paginated = computed(() =>
    paginate(this.processed(), this.page(), PAGE_SIZE)
  );

  /** Raw unfiltered count — used to distinguish "no data at all" from "filters excluded everything". */
  protected readonly totalCount = computed(() => this.conversations().length);

  async ngOnInit(): Promise<void> {
    try {
      const data = await this.logsService.getConversations();
      this.conversations.set(data);
      this.state.set('success');
    } catch (err: unknown) {
      this.state.set('error');
      this.errorMessage.set(err instanceof Error ? err.message : 'Erreur inconnue');
    }
  }

  protected onSearchChange(value: string): void {
    this.searchQuery.set(value);
    this.page.set(1);
  }

  protected onDateFromChange(value: string): void {
    this.dateFrom.set(value);
    this.page.set(1);
  }

  protected onDateToChange(value: string): void {
    this.dateTo.set(value);
    this.page.set(1);
  }

  protected clearDateFilter(): void {
    this.dateFrom.set('');
    this.dateTo.set('');
    this.page.set(1);
  }

  protected onSortChanged(event: { field: SortField; direction: SortDir }): void {
    this.sortField.set(event.field);
    this.sortDirection.set(event.direction);
    this.page.set(1);
  }

  protected confirmDelete(conversationId: string, event: MouseEvent): void {
    event.stopPropagation();
    this.pendingDeleteId.set(conversationId);
  }

  protected cancelDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.pendingDeleteId.set(null);
  }

  protected async executeDelete(conversationId: string, event: MouseEvent): Promise<void> {
    event.stopPropagation();
    try {
      await this.logsService.deleteConversation(conversationId);
      this.conversations.update((list: ConversationSummary[]) => list.filter((c: ConversationSummary) => c.conversation_id !== conversationId));
    } catch (err: unknown) {
      console.error('Failed to delete conversation', err);
    } finally {
      this.pendingDeleteId.set(null);
    }
  }

  protected formatDate(iso: string): string { return fmtDateTime(iso); }
}



