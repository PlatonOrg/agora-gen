import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

export type SortField = 'started_at' | 'last_at' | 'count';
export type SortDir = 'asc' | 'desc';

export interface SortOption {
  field: SortField;
  label: string;
}

@Component({
  selector: 'app-log-sort-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-sort-bar.component.html',
  styleUrl: './log-sort-bar.component.scss',
})
export class LogSortBarComponent {
  readonly options = input.required<SortOption[]>();
  readonly activeField = input.required<SortField>();
  readonly direction = input<SortDir>('desc');
  readonly sortChanged = output<{ field: SortField; direction: SortDir }>();

  protected select(field: SortField): void {
    const currentDir = this.direction();
    const newDir: SortDir = this.activeField() === field
      ? (currentDir === 'asc' ? 'desc' : 'asc')
      : 'desc';
    this.sortChanged.emit({ field, direction: newDir });
  }
}

