import { Component, input } from '@angular/core';

export type BadgeVariant = 'exercise' | 'discussion' | 'neutral' | 'info' | 'success' | 'warn';

@Component({
  selector: 'app-log-badge',
  standalone: true,
  template: `<span class="badge badge--{{ variant() }}">{{ label() }}</span>`,
  styleUrl: './log-badge.component.scss',
})
export class LogBadgeComponent {
  label = input.required<string>();
  variant = input<BadgeVariant>('neutral');
}

