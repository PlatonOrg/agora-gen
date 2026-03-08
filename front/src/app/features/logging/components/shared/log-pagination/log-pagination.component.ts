import { Component, input, output, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { pageRange } from '../../../utils/pagination.utils';

@Component({
  selector: 'app-log-pagination',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-pagination.component.html',
  styleUrl: './log-pagination.component.scss',
})
export class LogPaginationComponent {
  readonly page = input.required<number>();
  readonly totalPages = input.required<number>();
  readonly pageChanged = output<number>();

  protected readonly pages = computed(() => pageRange(this.page(), this.totalPages()));

  protected goto(p: number | '...'): void {
    if (p === '...' || p === this.page()) return;
    this.pageChanged.emit(p as number);
  }

  protected isNumber(v: number | '...'): v is number {
    return typeof v === 'number';
  }
}

