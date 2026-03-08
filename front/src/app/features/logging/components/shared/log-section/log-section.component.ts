import { Component, input, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-log-section',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-section.component.html',
  styleUrl: './log-section.component.scss',
})
export class LogSectionComponent {
  title = input.required<string>();
  icon = input<string>('');
  protected readonly collapsed = signal(false);
  private readonly sanitizer = inject(DomSanitizer);
  protected safe(html: string): SafeHtml { return this.sanitizer.bypassSecurityTrustHtml(html); }
}


