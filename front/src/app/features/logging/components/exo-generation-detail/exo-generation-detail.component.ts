import { Component, input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ExoGenerationDetail, LlmCallRecord } from '../../models/log.model';
import { LogSectionComponent } from '../shared/log-section/log-section.component';
import { LogKvComponent } from '../shared/log-kv/log-kv.component';
import { LogJsonComponent } from '../shared/log-json/log-json.component';
import { LogBadgeComponent } from '../shared/log-badge/log-badge.component';
import { LOG_ICONS } from '../../utils/log-icons';
import { fmtDateTime } from '../../utils/log-format.utils';

@Component({
  selector: 'app-exo-generation-detail',
  standalone: true,
  imports: [CommonModule, LogSectionComponent, LogKvComponent, LogJsonComponent, LogBadgeComponent],
  templateUrl: './exo-generation-detail.component.html',
  styleUrls: ['../../logging.shared.scss', './exo-generation-detail.component.scss'],
})
export class ExoGenerationDetailComponent {
  gen = input.required<ExoGenerationDetail>();
  protected readonly icons = LOG_ICONS;
  private readonly sanitizer = inject(DomSanitizer);
  protected fmt(iso: string | null | undefined): string { return fmtDateTime(iso); }
  protected safe(html: string): SafeHtml { return this.sanitizer.bypassSecurityTrustHtml(html); }

  sumTokens(calls: LlmCallRecord[], kind: 'input' | 'output' | 'total'): number {
    return calls.reduce((sum, c) => {
      const input = c.input_tokens ?? 0;
      const output = c.output_tokens ?? 0;
      return sum + (kind === 'input' ? input : kind === 'output' ? output : input + output);
    }, 0);
  }
}


