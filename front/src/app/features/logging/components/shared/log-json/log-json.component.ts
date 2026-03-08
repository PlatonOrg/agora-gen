import { Component, input, computed } from '@angular/core';

@Component({
  selector: 'app-log-json',
  standalone: true,
  template: `<pre class="json-view">{{ formatted() }}</pre>`,
  styleUrl: './log-json.component.scss',
})
export class LogJsonComponent {
  data = input.required<unknown>();
  protected readonly formatted = computed(() => {
    try {
      return JSON.stringify(this.data(), null, 2);
    } catch {
      return String(this.data());
    }
  });
}

