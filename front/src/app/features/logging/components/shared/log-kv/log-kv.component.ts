import { Component, input } from '@angular/core';

@Component({
  selector: 'app-log-kv',
  standalone: true,
  template: `
    <div class="kv">
      <span class="kv__key">{{ key() }}</span>
      <span class="kv__value">{{ value() ?? '—' }}</span>
    </div>
  `,
  styleUrl: './log-kv.component.scss',
})
export class LogKvComponent {
  key = input.required<string>();
  value = input<string | number | null | undefined>(null);
}

