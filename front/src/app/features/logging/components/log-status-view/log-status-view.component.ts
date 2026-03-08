import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type LoadingState = 'idle' | 'loading' | 'error' | 'success';

@Component({
  selector: 'app-log-status-view',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-status-view.component.html',
  styleUrl: './log-status-view.component.scss',
})
export class LogStatusViewComponent {
  state = input.required<LoadingState>();
  empty = input<boolean>(false);
  errorMessage = input<string | null>(null);
  emptyMessage = input<string | null>(null);
}

